"""Auth API router — login, register, check."""
import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from backend.auth.jwt import create_access_token
from backend.config import get_config
from backend.database import AsyncSession, User, get_db
from backend.utils.responses import APIException, rate_limited, get_correlation_id

router = APIRouter()

# ── Progressive login lockout ─────────────────────────────────────────────────
# Tracks per-IP failure counts and optional lockout expiry.
_login_failures: dict[str, int] = defaultdict(int)
_login_lockout_until: dict[str, float] = {}

_LOCKOUT_POLICY = [
    # (failures_threshold, lockout_seconds)
    (10, 30 * 60),   # 10+ failures  → 30 min lockout
    (5,   5 * 60),   # 5–9 failures  →  5 min lockout
]


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()

    # Check if currently locked out
    until = _login_lockout_until.get(ip, 0)
    if now < until:
        remaining = int(until - now)
        raise rate_limited(
            message=f"Too many failed login attempts. Try again in {remaining} seconds.",
            details={"remaining_seconds": remaining},
            correlation_id=get_correlation_id(),
        )


def _record_login_failure(ip: str) -> None:
    now = time.monotonic()
    _login_failures[ip] += 1
    failures = _login_failures[ip]

    for threshold, duration in _LOCKOUT_POLICY:
        if failures >= threshold:
            _login_lockout_until[ip] = now + duration
            break


def _record_login_success(ip: str) -> None:
    """Reset failure count on successful login."""
    _login_failures.pop(ip, None)
    _login_lockout_until.pop(ip, None)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


class RegisterRequest(BaseModel):
    username: str
    password: str


@router.get("/check")
async def check_auth_status(db: AsyncSession = Depends(get_db)):
    """
    GET /api/v1/auth/check
    Returns whether any user exists (used by setup wizard).
    Does NOT require authentication.
    """
    result = await db.execute(select(User))
    has_user = result.scalars().first() is not None
    return {"has_user": has_user, "setup_required": not has_user}


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from passlib.hash import bcrypt
    _check_rate_limit(request.client.host if request.client else "unknown")

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    ip = request.client.host if request.client else "unknown"
    if not user or not bcrypt.verify(body.password, user.password_hash):
        _record_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _record_login_success(ip)
    config = get_config()
    token = create_access_token(
        user.username,
        config.auth.secret_key,
        config.auth.session_timeout_hours,
    )
    return LoginResponse(token=token, username=user.username)


@router.post("/register", response_model=LoginResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    First-run only. If any user already exists, registration is blocked.
    """
    from passlib.hash import bcrypt

    result = await db.execute(select(User))
    if result.scalars().first() is not None:
        raise HTTPException(status_code=403, detail="Registration is disabled after first user is created.")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    hashed = bcrypt.hash(body.password)
    user = User(username=body.username, password_hash=hashed)
    db.add(user)
    await db.commit()

    config = get_config()
    token = create_access_token(
        user.username,
        config.auth.secret_key,
        config.auth.session_timeout_hours,
    )
    return LoginResponse(token=token, username=user.username)
