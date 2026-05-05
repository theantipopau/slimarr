"""FastAPI auth dependencies."""
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.jwt import decode_access_token
from backend.config import get_config
from backend.utils.responses import get_correlation_id, unauthorized

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    Authenticate via:
    1. X-Api-Key header (programmatic access)
    2. Bearer JWT token (UI login)
    Returns the username string on success.
    """
    from typing import Optional  # local import avoids top-level issues

    config = get_config()

    # API key check
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        if api_key == config.auth.api_key and config.auth.api_key:
            return "api_user"
        raise unauthorized("Invalid API key", correlation_id=get_correlation_id())

    # JWT bearer token check
    if credentials and credentials.credentials:
        try:
            payload = decode_access_token(credentials.credentials, config.auth.secret_key)
            return payload["sub"]
        except Exception:
            raise unauthorized("Invalid or expired token", correlation_id=get_correlation_id())

    raise unauthorized("Authentication required", correlation_id=get_correlation_id())


# Re-export for convenience
from typing import Optional  # noqa: E402
