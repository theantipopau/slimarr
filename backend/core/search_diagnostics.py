"""In-memory search pipeline diagnostics and degradation detection."""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from backend.realtime.events import emit_event

MAX_EVENTS = 500
MAX_WARNINGS = 100
RAW_PREVIEW_LIMIT = 20000
HISTORY_MAX_ROWS = 5000
HISTORY_FILE = os.path.join("data", "logs", "search-diagnostics-history.jsonl")
SENSITIVE_QUERY_KEYS = {"apikey", "api_key", "x-api-key", "token", "password", "pass", "r", "apikeys"}
SENSITIVE_TEXT_PATTERNS = [
    # URL query params: apikey=secret
    re.compile(r"(?i)\b(apikey|api_key|token|password|pass|x-api-key)(=)([^&\s\"'<]+)"),
    # JSON and dict-style: "apikey":"secret" or apikey:secret or apikey = secret
    re.compile(r"(?i)\b(apikey|api_key|token|password|pass|x-api-key)([\"']?\s*[:=]\s*[\"']?)([^\"'\s<>&,}]+)"),
    # Authorization headers: Authorization: Bearer token or Authorization:Bearer token or "Authorization":"Bearer token"
    re.compile(r"(?i)(authorization)([\"']?\s*[:=]\s*[\"']?)(bearer|basic)(\s+[\"']?)([^\"'\s<>&,}]+)", re.IGNORECASE),
]


class SearchPipelineDegraded(RuntimeError):
    """Raised when automation should stop because search is effectively down."""


_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_warnings: deque[dict[str, Any]] = deque(maxlen=MAX_WARNINGS)
_indexer_metrics: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "requests": 0,
        "successes": 0,
        "failures": 0,
        "timeouts": 0,
        "empty": 0,
        "malformed": 0,
        "http_errors": 0,
        "total_latency_ms": 0.0,
        "last_status_code": None,
        "last_error": None,
        "last_success_at": None,
        "last_request_at": None,
    }
)
_failure_heatmap: Counter[str] = Counter()
_consecutive_zero_searches = 0
_consecutive_failed_searches = 0
_last_successful_search: dict[str, Any] | None = None
_lock = RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_url(url: str) -> str:
    try:
        parts = urlsplit(str(url))
        netloc = parts.netloc
        if "@" in netloc:
            netloc = f"***@{netloc.rsplit('@', 1)[-1]}"
        redacted = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            redacted.append((key, "***" if key.lower() in SENSITIVE_QUERY_KEYS else value))
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(redacted), parts.fragment))
    except Exception:
        return str(url)


def redact_text(text: str) -> str:
    redacted = str(text)
    for i, pattern in enumerate(SENSITIVE_TEXT_PATTERNS):
        if i == 2:  # Authorization pattern with 5 groups
            redacted = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}***", redacted)
        elif pattern.groups >= 4:
            redacted = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)} ***", redacted)
        else:
            redacted = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}***", redacted)
    return redacted


def normalize_exception(exc: BaseException, *, timeout_seconds: float | None = None) -> str:
    message = str(exc).strip()
    cls_name = exc.__class__.__name__
    if isinstance(exc, httpx.TimeoutException):
        if not message:
            if timeout_seconds:
                message = f"request timed out after {timeout_seconds:.0f}s"
            else:
                message = "request timed out"
        return f"{cls_name}: {message}"
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        body = response.text[:500] if response is not None else ""
        return f"{cls_name}: HTTP {response.status_code if response else '?'} {body}".strip()
    return f"{cls_name}: {message or repr(exc)}"


def raw_preview(content: bytes | str | None, limit: int = RAW_PREVIEW_LIMIT) -> str:
    if content is None:
        return ""
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content
    return redact_text(text[:limit])


def _append_event(event: dict[str, Any]) -> dict[str, Any]:
    event.setdefault("timestamp", utc_now())
    with _lock:
        _events.appendleft(event)
    _append_history_record("event", event)
    return event


def _append_history_record(kind: str, payload: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        row = {
            "kind": kind,
            "timestamp": payload.get("timestamp") or utc_now(),
            "payload": payload,
        }
        with open(HISTORY_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

        # Keep file bounded to avoid unbounded growth.
        with open(HISTORY_FILE, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        if len(lines) > HISTORY_MAX_ROWS:
            with open(HISTORY_FILE, "w", encoding="utf-8") as handle:
                handle.writelines(lines[-HISTORY_MAX_ROWS:])
    except Exception:
        # Diagnostics persistence must not break search flow.
        pass


def record_indexer_request(
    *,
    indexer_name: str,
    provider: str,
    query: str,
    request_url: str,
    categories: list[int] | None = None,
) -> dict[str, Any]:
    return _append_event(
        {
            "type": "indexer_request",
            "indexer_name": indexer_name,
            "provider": provider,
            "query": query,
            "request_url": redact_url(request_url),
            "categories": categories or [],
            "status": "started",
        }
    )


async def emit_search_warning(message: str, detail: dict[str, Any] | None = None) -> None:
    detail = detail or {}
    with _lock:
        for existing in list(_warnings)[:10]:
            if existing.get("message") == message and existing.get("detail") == detail:
                return
        warning = {"timestamp": utc_now(), "message": message, "detail": detail}
        _warnings.appendleft(warning)
    _append_history_record("warning", warning)
    await emit_event("search:warning", warning)


def record_indexer_response(
    *,
    indexer_name: str,
    provider: str,
    query: str,
    request_url: str,
    status_code: int | None,
    latency_ms: float,
    raw_count: int = 0,
    parsed_count: int = 0,
    categories: list[int] | None = None,
    error: str | None = None,
    malformed: bool = False,
    raw_response: str | None = None,
) -> dict[str, Any]:
    safe_raw_preview = raw_preview(raw_response) if raw_response else ""
    with _lock:
        metrics = _indexer_metrics[indexer_name]
        metrics["requests"] += 1
        metrics["last_request_at"] = utc_now()
        metrics["total_latency_ms"] += latency_ms
        metrics["last_status_code"] = status_code
        if status_code and status_code >= 400:
            metrics["http_errors"] += 1

        if error:
            metrics["failures"] += 1
            metrics["last_error"] = error
            if "timeout" in error.lower() or "timed out" in error.lower():
                metrics["timeouts"] += 1
                _failure_heatmap[f"{indexer_name}:timeout"] += 1
            elif malformed:
                metrics["malformed"] += 1
                _failure_heatmap[f"{indexer_name}:malformed"] += 1
            elif status_code and status_code >= 400:
                _failure_heatmap[f"{indexer_name}:http_{status_code}"] += 1
            else:
                _failure_heatmap[f"{indexer_name}:error"] += 1
        else:
            metrics["successes"] += 1
            metrics["last_error"] = None
            metrics["last_success_at"] = utc_now()
            if raw_count == 0:
                metrics["empty"] += 1

    return _append_event(
        {
            "type": "indexer_response",
            "indexer_name": indexer_name,
            "provider": provider,
            "query": query,
            "request_url": redact_url(request_url),
            "status_code": status_code,
            "latency_ms": round(latency_ms, 1),
            "raw_count": raw_count,
            "parsed_count": parsed_count,
            "categories": categories or [],
            "error": error,
            "malformed": malformed,
            "raw_preview": safe_raw_preview,
        }
    )


def record_filter_summary(
    *,
    movie_id: int,
    title: str,
    raw_count: int,
    unique_count: int,
    stored_count: int,
    accepted_count: int,
    rejected_count: int,
    rejection_reasons: dict[str, int],
) -> None:
    _append_event(
        {
            "type": "filter_summary",
            "movie_id": movie_id,
            "title": title,
            "raw_count": raw_count,
            "unique_count": unique_count,
            "stored_count": stored_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "rejection_reasons": rejection_reasons,
        }
    )


async def record_movie_search_completed(
    *,
    movie_id: int,
    title: str,
    raw_count: int,
    accepted_count: int,
    indexer_attempts: int,
    indexer_failures: int,
    configured_sources: int,
) -> None:
    global _consecutive_zero_searches, _consecutive_failed_searches, _last_successful_search

    with _lock:
        if raw_count > 0:
            _consecutive_zero_searches = 0
            _consecutive_failed_searches = 0
            _last_successful_search = {
                "movie_id": movie_id,
                "title": title,
                "raw_count": raw_count,
                "accepted_count": accepted_count,
                "timestamp": utc_now(),
            }
        else:
            _consecutive_zero_searches += 1
            if configured_sources == 0 or (indexer_attempts > 0 and indexer_failures >= indexer_attempts):
                _consecutive_failed_searches += 1
            else:
                _consecutive_failed_searches = 0
        zero_searches = _consecutive_zero_searches
        failed_searches = _consecutive_failed_searches

    _append_event(
        {
            "type": "movie_search_completed",
            "movie_id": movie_id,
            "title": title,
            "raw_count": raw_count,
            "accepted_count": accepted_count,
            "indexer_attempts": indexer_attempts,
            "indexer_failures": indexer_failures,
            "configured_sources": configured_sources,
            "consecutive_zero_searches": zero_searches,
            "consecutive_failed_searches": failed_searches,
        }
    )

    if configured_sources == 0:
        await emit_search_warning(
            "Search is not configured: no enabled Prowlarr instance and no direct indexers.",
            {"movie_id": movie_id, "title": title},
        )
    elif zero_searches == 100:
        await emit_search_warning(
            "Search pipeline has returned zero raw results for 100 consecutive movies.",
            {"movie_id": movie_id, "title": title},
        )
    elif failed_searches == 10:
        await emit_search_warning(
            "All attempted search providers are failing repeatedly.",
            {"movie_id": movie_id, "title": title},
        )


def degradation_status() -> dict[str, Any]:
    with _lock:
        zero_searches = _consecutive_zero_searches
        failed_searches = _consecutive_failed_searches
        last_success = _last_successful_search
    warning_reasons: list[str] = []
    blocking_reasons: list[str] = []
    if zero_searches >= 100:
        warning_reasons.append("100+ consecutive zero-result searches")
    if failed_searches >= 10:
        blocking_reasons.append("all configured search providers failing")
    return {
        "degraded": bool(warning_reasons or blocking_reasons),
        "blocking": bool(blocking_reasons),
        "reasons": [*blocking_reasons, *warning_reasons],
        "warning_reasons": warning_reasons,
        "blocking_reasons": blocking_reasons,
        "consecutive_zero_searches": zero_searches,
        "consecutive_failed_searches": failed_searches,
        "last_successful_search": last_success,
    }


def raise_if_degraded() -> None:
    status = degradation_status()
    if status["blocking"]:
        raise SearchPipelineDegraded("; ".join(status["blocking_reasons"]))


def snapshot() -> dict[str, Any]:
    with _lock:
        reliability = {}
        for name, data in _indexer_metrics.items():
            requests = int(data["requests"] or 0)
            successes = int(data["successes"] or 0)
            reliability[name] = {
                **data,
                "success_rate": round((successes / requests) * 100, 1) if requests else None,
                "avg_latency_ms": round((data["total_latency_ms"] / requests), 1) if requests else None,
            }
        events = list(_events)
        warnings = list(_warnings)
        heatmap = dict(_failure_heatmap.most_common(50))
    return {
        "checked_at": utc_now(),
        "degradation": degradation_status(),
        "recent_events": events,
        "warnings": warnings,
        "failure_heatmap": heatmap,
        "indexer_reliability": reliability,
        "last_successful_search": _last_successful_search,
    }


def history(
    *,
    page: int = 1,
    per_page: int = 50,
    event_type: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = max(1, min(200, int(per_page or 50)))
    event_type_l = (event_type or "").strip().lower()
    query_l = (query or "").strip().lower()

    rows: list[dict[str, Any]] = []
    if os.path.isfile(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict):
                            rows.append(row)
                    except Exception:
                        continue
        except Exception:
            rows = []

    # Newest first for UI pagination.
    rows.reverse()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict):
            continue
        payload_type = str(payload.get("type") or row.get("kind") or "").lower()
        if event_type_l and payload_type != event_type_l:
            continue
        if query_l:
            haystack = json.dumps(payload, ensure_ascii=True).lower()
            if query_l not in haystack:
                continue
        filtered.append(payload)

    total = len(filtered)
    pages = max(1, (total + per_page - 1) // per_page)
    if page > pages:
        page = pages
    start = (page - 1) * per_page
    end = start + per_page
    items = filtered[start:end]

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "items": items,
    }


def reset() -> None:
    global _consecutive_zero_searches, _consecutive_failed_searches, _last_successful_search
    with _lock:
        _events.clear()
        _warnings.clear()
        _indexer_metrics.clear()
        _failure_heatmap.clear()
        _consecutive_zero_searches = 0
        _consecutive_failed_searches = 0
        _last_successful_search = None
