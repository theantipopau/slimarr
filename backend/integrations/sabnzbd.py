"""SABnzbd download client."""
from __future__ import annotations

from typing import Optional

import httpx

from backend.config import get_config


class SABnzbdClient:
    def __init__(self) -> None:
        config = get_config()
        self.url = config.sabnzbd.url.rstrip("/")
        self.api_key = config.sabnzbd.api_key
        self.category = config.sabnzbd.category

    async def _api(self, mode: str, extra: dict | None = None) -> dict:
        params: dict = {"mode": mode, "apikey": self.api_key, "output": "json"}
        if extra:
            params.update(extra)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.url}/api", params=params)
            resp.raise_for_status()
            return resp.json()

    async def add_nzb_url(self, nzb_url: str, title: str = "") -> str:
        """Returns the nzo_id."""
        result = await self._api("addurl", {
            "name": nzb_url,
            "nzbname": title,
            "cat": self.category,
        })
        nzo_ids = result.get("nzo_ids", [])
        if not nzo_ids:
            raise RuntimeError(f"SABnzbd addurl failed: {result}")
        return nzo_ids[0]

    async def get_queue(self) -> list[dict]:
        result = await self._api("queue")
        slots = result.get("queue", {}).get("slots", [])
        return [
            {
                "nzo_id": s["nzo_id"],
                "filename": s.get("filename", ""),
                "status": s.get("status", ""),
                "percentage": float(s.get("percentage", 0)),
                "size": s.get("size", ""),
                "sizeleft": s.get("sizeleft", ""),
                "speed": s.get("speed", ""),
                "timeleft": s.get("timeleft", ""),
                "category": s.get("cat", ""),
            }
            for s in slots
        ]

    async def get_history(self, limit: int = 50) -> list[dict]:
        result = await self._api("history", {"limit": limit})
        slots = result.get("history", {}).get("slots", [])
        return [
            {
                "nzo_id": s["nzo_id"],
                "name": s.get("name", ""),
                "status": s.get("status", ""),
                "storage": s.get("storage", ""),
                "size": s.get("bytes", 0),
                "completed": s.get("completed", 0),
                "category": s.get("category", ""),
            }
            for s in slots
        ]

    async def get_job_status(self, nzo_id: str) -> Optional[dict]:
        queue = await self.get_queue()
        for item in queue:
            if item["nzo_id"] == nzo_id:
                return {**item, "location": "queue"}
        history = await self.get_history(limit=100)
        for item in history:
            if item["nzo_id"] == nzo_id:
                return {**item, "location": "history"}
        return None

    async def test_connection(self) -> dict:
        try:
            result = await self._api("version")
            version = result.get("version", "unknown")
            return {"success": True, "version": version}
        except Exception as e:
            return {"success": False, "error": str(e)}
