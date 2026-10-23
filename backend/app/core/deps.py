"""FastAPI dependencies: database session, current user, rate limiting."""
from __future__ import annotations

import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


class SlidingWindowLimiter:
    """Tiny in-process limiter for the AI endpoints (per user, per minute)."""

    def __init__(self) -> None:
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def check(self, key: int, limit: int, window: float = 60.0, cost: int = 1) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window:
            q.popleft()
        cost = max(1, min(cost, limit))  # a request bigger than the budget still goes through once the window is clear
        if len(q) + cost > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down for a minute")
        q.extend([now] * cost)


ai_limiter = SlidingWindowLimiter()


def charge_ai(user: User, cost: int = 1) -> None:
    """Count `cost` model calls against the user's per-minute AI budget (429 when it is spent)."""
    settings = get_settings()
    if settings.app_env != "test" and cost > 0:
        ai_limiter.check(user.id, settings.ai_rate_limit_per_minute, cost=cost)


def ai_rate_limit(request: Request, user: User = Depends(get_current_user)) -> User:
    charge_ai(user)
    return user
