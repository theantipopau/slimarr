"""Shared "use the pooled client, or fall back to a private one" decision,
used by every integration client that supports connection reuse via the
app-wide httpx.AsyncClient (see backend.main.get_http_client).

This was previously copy-pasted into tmdb.py, radarr.py, and sonarr.py
independently (see docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md, finding A5) -
a single implementation here means a future change to the reuse policy only
needs to happen once. Each module keeps its own thin `_shared_client()`
wrapper so existing tests can still patch it per-module; only the actual
decision logic lives here now.
"""
from __future__ import annotations

import httpx


def get_shared_client(*, tls_verify: bool = True) -> httpx.AsyncClient | None:
    """Return the app-wide pooled httpx client if it's usable for this call,
    else None (the caller should open its own private client instead).

    The shared client is always built with verify=True. A caller whose own
    instance is configured with tls_verify=False (self-signed certs, common
    on a NAS/homelab setup) must never have that silently overridden by
    reusing a client that ignores it - so pooling is only used when the two
    agree. Callers with no such per-instance TLS setting (e.g. TMDB, always
    a fixed HTTPS endpoint) simply never pass tls_verify=False.
    """
    if not tls_verify:
        return None
    try:
        from backend.main import get_http_client

        return get_http_client()
    except Exception:
        return None
