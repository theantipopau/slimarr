"""Newznab protocol indexer client."""
from __future__ import annotations

from typing import Optional

import httpx
from lxml import etree

from backend.config import IndexerConfig


class NewznabClient:
    def __init__(self, indexer: IndexerConfig) -> None:
        self.name = indexer.name
        self.url = indexer.url.rstrip("/")
        self.api_key = indexer.api_key
        self.categories = indexer.categories

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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.url}/api", params=params)
            resp.raise_for_status()

        results = []
        try:
            root = etree.fromstring(resp.content)
        except Exception:
            return results

        ns = {"newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/"}

        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")

            size = 0
            enc = item.find("enclosure")
            if enc is not None:
                try:
                    size = int(enc.get("length", 0))
                except (ValueError, TypeError):
                    pass

            attrs: dict[str, str] = {}
            for attr in item.findall("newznab:attr", ns):
                attrs[attr.get("name", "")] = attr.get("value", "")

            if size == 0:
                try:
                    size = int(attrs.get("size", 0))
                except (ValueError, TypeError):
                    pass

            results.append({
                "indexer_name": self.name,
                "release_title": title,
                "nzb_url": link,
                "size": size,
                "imdb_id": attrs.get("imdb", ""),
                "pub_date": pub_date,
                "grabs": int(attrs.get("grabs", 0) or 0),
            })

        return results

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/api",
                    params={"t": "caps", "apikey": self.api_key},
                )
                resp.raise_for_status()
            root = etree.fromstring(resp.content)
            server_el = root.find(".//server")
            title = server_el.get("title", "Connected") if server_el is not None else "Connected"
            return {"success": True, "indexer": self.name, "server": title}
        except Exception as e:
            return {"success": False, "indexer": self.name, "error": str(e)}
