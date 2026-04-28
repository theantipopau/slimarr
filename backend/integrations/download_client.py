"""Download client abstraction and factory."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional, Protocol

from backend.config import get_config


@dataclass(frozen=True)
class DownloadClientCapabilities:
    submit_url: bool
    queue_status: bool
    history_status: bool
    purge: bool
    categories: bool
    pause_resume: bool
    storage_path_lookup: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


_CLIENT_CAPABILITIES: dict[str, DownloadClientCapabilities] = {
    "sabnzbd": DownloadClientCapabilities(
        submit_url=True,
        queue_status=True,
        history_status=True,
        purge=True,
        categories=True,
        pause_resume=False,
        storage_path_lookup=True,
    ),
    "nzbget": DownloadClientCapabilities(
        submit_url=True,
        queue_status=True,
        history_status=True,
        purge=True,
        categories=True,
        pause_resume=False,
        storage_path_lookup=True,
    ),
}


class DownloadClient(Protocol):
    name: str

    async def submit_url(self, url: str, title: str = "") -> str:
        """Submit a URL and return the client-specific job identifier."""

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """Return a normalized job status or None if the job cannot be found."""

    async def test_connection(self) -> dict:
        """Quick connectivity check for the configured client."""

    async def purge_job(self, job_id: str) -> bool:
        """Remove job from queue/history. Returns True if successful."""


def get_active_download_client_name() -> str:
    config = get_config()
    client_name = getattr(config, "download_client", "sabnzbd") or "sabnzbd"
    return str(client_name).strip().lower() or "sabnzbd"


def get_download_client_capabilities(client_name: str | None = None) -> DownloadClientCapabilities:
    name = (client_name or get_active_download_client_name()).strip().lower() or "sabnzbd"
    try:
        return _CLIENT_CAPABILITIES[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported download client: {name}") from exc


def list_download_client_capabilities() -> dict[str, dict[str, bool]]:
    return {
        name: capabilities.to_dict()
        for name, capabilities in sorted(_CLIENT_CAPABILITIES.items())
    }


def encode_job_id(client_name: str, job_id: str) -> str:
    return f"{client_name}:{job_id}"


def decode_job_id(raw_job_id: str | None, fallback_client: str | None = None) -> tuple[str, str]:
    fallback = (fallback_client or get_active_download_client_name()).strip().lower() or "sabnzbd"
    if not raw_job_id:
        return fallback, ""
    if ":" not in raw_job_id:
        return fallback, raw_job_id
    client_name, job_id = raw_job_id.split(":", 1)
    return (client_name or fallback).strip().lower(), job_id


def get_download_client(client_name: str | None = None) -> DownloadClient:
    name = (client_name or get_active_download_client_name()).strip().lower() or "sabnzbd"
    if name == "sabnzbd":
        from backend.integrations.sabnzbd import SABnzbdClient
        return SABnzbdClient()
    if name == "nzbget":
        from backend.integrations.nzbget import NZBGetClient
        return NZBGetClient()
    raise ValueError(f"Unsupported download client: {name}")
