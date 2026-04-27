"""NZBGet download client."""
from __future__ import annotations

from typing import Any, Optional

import httpx
from loguru import logger

from backend.config import get_config


class NZBGetClient:
    name = "nzbget"

    def __init__(self) -> None:
        config = get_config()
        self.url = config.nzbget.url.rstrip("/")
        self.username = config.nzbget.username
        self.password = config.nzbget.password
        self.category = config.nzbget.category

    def _rpc_url(self) -> str:
        return f"{self.url}/jsonrpc"

    def _auth(self) -> tuple[str, str] | None:
        if self.username or self.password:
            return self.username, self.password
        return None

    async def _rpc(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {
            "version": "1.1",
            "method": method,
            "params": params or [],
            "id": 1,
        }
        async with httpx.AsyncClient(timeout=20.0, auth=self._auth()) as client:
            resp = await client.post(self._rpc_url(), json=payload)
            resp.raise_for_status()
            data = resp.json()
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data.get("result")

    @staticmethod
    def _status_success(status: str) -> bool:
        normalized = status.upper()
        return normalized.startswith("SUCCESS") or normalized.startswith("WARNING")

    @staticmethod
    def _storage_path(item: dict[str, Any]) -> str:
        return str(item.get("FinalDir") or item.get("DestDir") or "")

    async def submit_url(self, url: str, title: str = "") -> str:
        name = title if title.lower().endswith(".nzb") else f"{title or 'slimarr'}.nzb"
        result = await self._rpc("append", [
            name,
            url,
            self.category,
            0,
            False,
            False,
            "",
            0,
            "SCORE",
            [],
        ])
        if result in (None, False):
            raise RuntimeError("NZBGet append failed")
        return str(result)

    async def list_groups(self) -> list[dict[str, Any]]:
        result = await self._rpc("listgroups", [0])
        return result if isinstance(result, list) else []

    async def history(self, hidden: bool = False) -> list[dict[str, Any]]:
        result = await self._rpc("history", [hidden])
        return result if isinstance(result, list) else []

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        groups = await self.list_groups()
        for item in groups:
            if str(item.get("NZBID", "")) != str(job_id):
                continue
            total_mb = float(item.get("FileSizeMB") or 0)
            remaining_mb = float(item.get("RemainingSizeMB") or 0)
            progress_pct = 0.0
            if total_mb > 0:
                progress_pct = max(0.0, min(100.0, ((total_mb - remaining_mb) / total_mb) * 100.0))
            return {
                "location": "queue",
                "status": str(item.get("Status", "downloading")),
                "percentage": progress_pct,
                "speed": "",
                "timeleft": "",
                "storage": self._storage_path(item),
            }

        history = await self.history(False)
        for item in history:
            if str(item.get("NZBID", "")) != str(job_id):
                continue
            return {
                "location": "history",
                "status": str(item.get("Status", "")),
                "percentage": 100.0,
                "speed": "",
                "timeleft": "",
                "storage": self._storage_path(item),
            }
        return None

    async def test_connection(self) -> dict:
        try:
            result = await self._rpc("version")
            return {"success": True, "version": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def purge_job(self, job_id: str) -> bool:
        """Remove job from NZBGet queue/history."""
        try:
            await self._rpc("editqueue", ["GroupOperation", 0, "GroupDelete", job_id])
            logger.info(f"NZBGet purged job {job_id}")
            return True
        except Exception as e:
            logger.warning(f"NZBGet purge failed for {job_id}: {e}")
            return False