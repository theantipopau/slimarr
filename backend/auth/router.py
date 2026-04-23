"""Auth API router — login, register, check."""
import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from backend.auth.jwt import create_access_token
from backend.config import get_config
from backend.database import AsyncSession, User, get_db

router = APIRouter()

# Simple in-memory rate limiter: {ip: [timestamps]}
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60   # seconds
_RATE_MAX    = 10   # attempts per window


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    attempts = _login_attempts[ip]
    # Purge old entries
    _login_attempts[ip] = [t for t in attempts if now - t < _RATE_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _login_attempts[ip].append(now)


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
    if not user or not bcrypt.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

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

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

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
