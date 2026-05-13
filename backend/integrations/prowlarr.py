"""Prowlarr unified indexer proxy client."""
from __future__ import annotations

import httpx
import time
from typing import Any

from backend.config import get_config
from backend.core.search_diagnostics import (
    normalize_exception,
    raw_preview,
    record_indexer_request,
    record_indexer_response,
)


class ProwlarrParserError(RuntimeError):
    """Raised when Prowlarr returns an unexpected search payload."""


class ProwlarrClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        config = get_config()
        self.url = config.prowlarr.url.rstrip("/")
        self.api_key = config.prowlarr.api_key
        self._transport = transport

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key}

    async def get_indexers(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            resp = await client.get(f"{self.url}/api/v1/indexer", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def search(self, query: str = "", imdb_id: str = "",
                     categories: list[int] | None = None) -> list[dict]:
        detail = await self.search_detailed(query=query, imdb_id=imdb_id, categories=categories)
        if detail.get("error"):
            raise detail["exception"]
        return detail["parsed_results"]

    async def search_detailed(
        self,
        query: str = "",
        imdb_id: str = "",
        categories: list[int] | None = None,
        *,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        params: dict = {"type": "movie"}
        if query:
            params["query"] = query
        if imdb_id:
            params["imdbId"] = imdb_id.lstrip("tt")
        if categories:
            params["categories"] = ",".join(str(c) for c in categories)

        start = time.perf_counter()
        timeout_seconds = 30.0
        resp: httpx.Response | None = None
        request_url = f"{self.url}/api/v1/search"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, transport=self._transport) as client:
                request = client.build_request(
                    "GET",
                    f"{self.url}/api/v1/search",
                    params=params,
                    headers=self._headers(),
                )
                request_url = str(request.url)
                record_indexer_request(
                    indexer_name="Prowlarr",
                    provider="prowlarr",
                    query=query or imdb_id,
                    request_url=request_url,
                    categories=categories or [],
                )
                resp = await client.send(request)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            error = normalize_exception(exc, timeout_seconds=timeout_seconds)
            malformed = resp is not None and exc.__class__.__name__ == "JSONDecodeError"
            record_indexer_response(
                indexer_name="Prowlarr",
                provider="prowlarr",
                query=query or imdb_id,
                request_url=request_url,
                status_code=resp.status_code if resp else None,
                latency_ms=elapsed_ms,
                error=error,
                malformed=malformed,
                raw_response=raw_preview(resp.content if resp is not None else None) if include_raw else None,
            )
            return {
                "indexer_name": "Prowlarr",
                "provider": "prowlarr",
                "request_url": request_url,
                "status_code": resp.status_code if resp else None,
                "latency_ms": round(elapsed_ms, 1),
                "raw_count": 0,
                "parsed_count": 0,
                "parsed_results": [],
                "raw_response": raw_preview(resp.content if resp is not None else None) if include_raw else "",
                "error": error,
                "exception": exc,
            }

        if not isinstance(payload, list):
            elapsed_ms = (time.perf_counter() - start) * 1000
            exc = ProwlarrParserError(f"Expected list response, got {type(payload).__name__}")
            record_indexer_response(
                indexer_name="Prowlarr",
                provider="prowlarr",
                query=query or imdb_id,
                request_url=request_url,
                status_code=resp.status_code,
                latency_ms=elapsed_ms,
                error=str(exc),
                malformed=True,
                raw_response=raw_preview(resp.content) if include_raw else None,
            )
            return {
                "indexer_name": "Prowlarr",
                "provider": "prowlarr",
                "request_url": request_url,
                "status_code": resp.status_code,
                "latency_ms": round(elapsed_ms, 1),
                "raw_count": 0,
                "parsed_count": 0,
                "parsed_results": [],
                "raw_response": raw_preview(resp.content) if include_raw else "",
                "error": str(exc),
                "exception": exc,
            }

        parsed_results = [
            {
                "indexer_name": r.get("indexer", "Prowlarr"),
                "release_title": r.get("title", ""),
                "nzb_url": r.get("downloadUrl") or r.get("guid", ""),
                "size": r.get("size", 0),
                "imdb_id": str(r.get("imdbId", "")),
                "pub_date": r.get("publishDate", ""),
                "grabs": r.get("grabs", 0),
                "categories": _extract_categories(r),
            }
            for r in payload
        ]
        elapsed_ms = (time.perf_counter() - start) * 1000
        queried_indexers = sorted({item["indexer_name"] for item in parsed_results if item.get("indexer_name")})
        record_indexer_response(
            indexer_name="Prowlarr",
            provider="prowlarr",
            query=query or imdb_id,
            request_url=request_url,
            status_code=resp.status_code,
            latency_ms=elapsed_ms,
            raw_count=len(payload),
            parsed_count=len(parsed_results),
            categories=categories or [],
            raw_response=raw_preview(resp.content) if include_raw else None,
        )
        return {
            "indexer_name": "Prowlarr",
            "provider": "prowlarr",
            "request_url": request_url,
            "status_code": resp.status_code,
            "latency_ms": round(elapsed_ms, 1),
            "raw_count": len(payload),
            "parsed_count": len(parsed_results),
            "parsed_results": parsed_results,
            "queried_indexers": queried_indexers,
            "raw_response": raw_preview(resp.content) if include_raw else "",
            "error": None,
            "exception": None,
        }

    async def test_connection(self) -> dict:
        try:
            indexers = await self.get_indexers()
            return {
                "success": True,
                "indexer_count": len(indexers),
                "indexers": [i.get("name") for i in indexers],
            }
        except Exception as e:
            return {"success": False, "error": normalize_exception(e, timeout_seconds=10.0)}


def _extract_categories(result: dict[str, Any]) -> list[int]:
    values: list[Any] = []
    for key in ("categories", "category"):
        value = result.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value is not None:
            values.append(value)

    parsed: list[int] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("id") or value.get("category") or value.get("name")
        for part in str(value).replace("|", ",").split(","):
            try:
                parsed.append(int(part.strip()))
            except (TypeError, ValueError):
                pass
    return sorted(set(parsed))
