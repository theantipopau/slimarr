"""JWT helpers for Slimarr authentication."""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt


def create_access_token(username: str, secret_key: str, hours: int = 72) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=hours)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_access_token(token: str, secret_key: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, secret_key, algorithms=["HS256"])
