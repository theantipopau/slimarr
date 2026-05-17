"""Newznab protocol indexer client."""
from __future__ import annotations

import xml.etree.ElementTree as ET
import time
from typing import Any

import httpx

from backend.config import IndexerConfig
from backend.core.search_diagnostics import (
    emit_search_warning,
    is_rate_limit_signal,
    normalize_exception,
    raw_preview,
    record_indexer_request,
    record_indexer_response,
)


class NewznabSearchError(RuntimeError):
    """Raised when an indexer returns an explicit Newznab error payload."""


class NewznabParserError(RuntimeError):
    """Raised when an indexer returns a malformed XML payload."""


class NewznabClient:
    def __init__(self, indexer: IndexerConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.name = indexer.name
        self.url = indexer.url.rstrip("/")
        self.api_key = indexer.api_key
        self.categories = indexer.categories
        self._transport = transport

    def _cat_str(self) -> str:
        return ",".join(str(c) for c in self.categories)

    async def search_by_imdb(self, imdb_id: str) -> list[dict]:
        # Strip leading "tt" if present for some indexers, keep both versions
        clean_id = imdb_id.lstrip("tt") if imdb_id.startswith("tt") else imdb_id
        params = {
            "t": "movie",
            "imdbid": clean_id,
            "apikey": self.api_key,
            "cat": self._cat_str(),
            "limit": 100,
        }
        return await self._do_search(params)

    async def search_by_query(self, query: str) -> list[dict]:
        params = {
            "t": "search",
            "q": query,
            "apikey": self.api_key,
            "cat": self._cat_str(),
            "limit": 100,
        }
        return await self._do_search(params)

    async def _do_search(self, params: dict) -> list[dict]:
        detail = await self.search_detailed(params)
        if detail.get("error"):
            raise detail["exception"]
        return detail["parsed_results"]

    async def search_detailed(self, params: dict, *, include_raw: bool = False) -> dict[str, Any]:
        start = time.perf_counter()
        timeout_seconds = 30.0
        resp: httpx.Response | None = None
        request_url = f"{self.url}/api"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, transport=self._transport) as client:
                request = client.build_request("GET", f"{self.url}/api", params=params)
                request_url = str(request.url)
                record_indexer_request(
                    indexer_name=self.name,
                    provider="newznab",
                    query=str(params.get("q") or params.get("imdbid") or ""),
                    request_url=request_url,
                    categories=self.categories,
                )
                resp = await client.send(request)
                resp.raise_for_status()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            error = normalize_exception(exc, timeout_seconds=timeout_seconds)
            preview = raw_preview(resp.content if resp is not None else None)
            rate_limited = is_rate_limit_signal(
                status_code=resp.status_code if resp else None,
                error=error,
                body=preview,
            )
            record_indexer_response(
                indexer_name=self.name,
                provider="newznab",
                query=str(params.get("q") or params.get("imdbid") or ""),
                request_url=request_url,
                status_code=resp.status_code if resp else None,
                latency_ms=elapsed_ms,
                error=error,
                raw_response=preview if include_raw else None,
                rate_limited=rate_limited,
            )
            if rate_limited:
                await emit_search_warning(
                    "Indexer API quota or rate limit reached.",
                    {
                        "indexer": self.name,
                        "provider": "newznab",
                        "status_code": resp.status_code if resp else None,
                        "error": error,
                    },
                )
            return {
                "indexer_name": self.name,
                "provider": "newznab",
                "request_url": request_url,
                "status_code": resp.status_code if resp else None,
                "latency_ms": round(elapsed_ms, 1),
                "raw_count": 0,
                "parsed_count": 0,
                "parsed_results": [],
                "raw_response": preview if include_raw else "",
                "error": error,
                "exception": exc,
            }

        results = []
        try:
            root = ET.fromstring(resp.content)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            error = normalize_exception(NewznabParserError(f"XML parse failed: {exc}"))
            record_indexer_response(
                indexer_name=self.name,
                provider="newznab",
                query=str(params.get("q") or params.get("imdbid") or ""),
                request_url=request_url,
                status_code=resp.status_code,
                latency_ms=elapsed_ms,
                error=error,
                malformed=True,
                raw_response=raw_preview(resp.content) if include_raw else None,
            )
            parser_exc = NewznabParserError(f"XML parse failed: {exc}")
            return {
                "indexer_name": self.name,
                "provider": "newznab",
                "request_url": request_url,
                "status_code": resp.status_code,
                "latency_ms": round(elapsed_ms, 1),
                "raw_count": 0,
                "parsed_count": 0,
                "parsed_results": [],
                "raw_response": raw_preview(resp.content) if include_raw else "",
                "error": str(parser_exc),
                "exception": parser_exc,
            }

        error_el = _find_first_by_local_name(root, "error")
        if error_el is not None:
            code = error_el.get("code", "unknown")
            description = error_el.get("description", "Newznab error")
            elapsed_ms = (time.perf_counter() - start) * 1000
            exc = NewznabSearchError(f"code={code} description={description}")
            rate_limited = is_rate_limit_signal(
                status_code=resp.status_code,
                error=str(exc),
                body=description,
            )
            record_indexer_response(
                indexer_name=self.name,
                provider="newznab",
                query=str(params.get("q") or params.get("imdbid") or ""),
                request_url=request_url,
                status_code=resp.status_code,
                latency_ms=elapsed_ms,
                error=str(exc),
                raw_response=raw_preview(resp.content) if include_raw else None,
                rate_limited=rate_limited,
            )
            if rate_limited:
                await emit_search_warning(
                    "Indexer API quota or rate limit reached.",
                    {
                        "indexer": self.name,
                        "provider": "newznab",
                        "status_code": resp.status_code,
                        "error": str(exc),
                    },
                )
            return {
                "indexer_name": self.name,
                "provider": "newznab",
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

        for item in _iter_by_local_name(root, "item"):
            title = _find_text_by_local_name(item, "title")
            link = _find_text_by_local_name(item, "link")
            pub_date = _find_text_by_local_name(item, "pubDate")

            size = 0
            enc = item.find("enclosure")
            if enc is not None:
                try:
                    size = int(enc.get("length", 0))
                except (ValueError, TypeError):
                    pass

            attrs: dict[str, str] = {}
            for attr in _iter_by_local_name(item, "attr"):
                attrs[attr.get("name", "")] = attr.get("value", "")

            if size == 0:
                try:
                    size = int(attrs.get("size", 0))
                except (ValueError, TypeError):
                    pass

            item_categories: list[int] = []
            for value in [attrs.get("category", "")] + [_element_text(c) for c in _iter_by_local_name(item, "category")]:
                for part in str(value).replace("|", ",").split(","):
                    try:
                        item_categories.append(int(part.strip()))
                    except (TypeError, ValueError):
                        pass

            results.append({
                "indexer_name": self.name,
                "release_title": title,
                "nzb_url": link,
                "size": size,
                "imdb_id": attrs.get("imdb", ""),
                "pub_date": pub_date,
                "grabs": int(attrs.get("grabs", 0) or 0),
                "categories": sorted(set(item_categories)),
            })

        elapsed_ms = (time.perf_counter() - start) * 1000
        record_indexer_response(
            indexer_name=self.name,
            provider="newznab",
            query=str(params.get("q") or params.get("imdbid") or ""),
            request_url=request_url,
            status_code=resp.status_code,
            latency_ms=elapsed_ms,
            raw_count=len(results),
            parsed_count=len(results),
            categories=self.categories,
            raw_response=raw_preview(resp.content) if include_raw else None,
        )

        return {
            "indexer_name": self.name,
            "provider": "newznab",
            "request_url": request_url,
            "status_code": resp.status_code,
            "latency_ms": round(elapsed_ms, 1),
            "raw_count": len(results),
            "parsed_count": len(results),
            "parsed_results": results,
            "raw_response": raw_preview(resp.content) if include_raw else "",
            "error": None,
            "exception": None,
        }

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
                resp = await client.get(
                    f"{self.url}/api",
                    params={"t": "caps", "apikey": self.api_key},
                )
                resp.raise_for_status()
            root = ET.fromstring(resp.content)
            server_el = root.find(".//server")
            title = server_el.get("title", "Connected") if server_el is not None else "Connected"
            return {"success": True, "indexer": self.name, "server": title}
        except Exception as e:
            return {"success": False, "indexer": self.name, "error": normalize_exception(e, timeout_seconds=10.0)}


def _find_first_by_local_name(root: ET.Element, local_name: str) -> ET.Element | None:
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] == local_name:
            return item
    return None


def _iter_by_local_name(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == local_name]


def _element_text(element: ET.Element | None) -> str:
    return element.text or "" if element is not None else ""


def _find_text_by_local_name(root: ET.Element, local_name: str) -> str:
    return _element_text(_find_first_by_local_name(root, local_name))
