from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import SlidingWindowLimiter, get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User, UserSettings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UpdateProfileRequest, UserOut, UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])
login_limiter = SlidingWindowLimiter()
LOGIN_ATTEMPTS_PER_MINUTE = 10


def user_out(db: Session, user: User) -> UserOut:
    settings = db.execute(select(UserSettings).where(UserSettings.user_id == user.id)).scalar_one_or_none()
    profile = UserProfile()
    if settings:
        profile = UserProfile(
            answer_mode=settings.answer_mode,
            semester=settings.semester,
            branch=settings.branch,
            daily_goal_minutes=settings.daily_goal_minutes,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
        )
    return UserOut(id=user.id, email=user.email, name=user.name, created_at=user.created_at, last_login_at=user.last_login_at, profile=profile)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled on this server")
    email = payload.email.lower().strip()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=payload.name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=user_out(db, user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower().strip()
    if get_settings().app_env != "test":
        login_limiter.check(hash(email), LOGIN_ATTEMPTS_PER_MINUTE)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id), user=user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(payload: UpdateProfileRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    settings = db.execute(select(UserSettings).where(UserSettings.user_id == user.id)).scalar_one_or_none()
    if settings is None:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
    if payload.name:
        user.name = payload.name.strip()
    if payload.answer_mode:
        settings.answer_mode = payload.answer_mode
    if "semester" in payload.model_fields_set:  # explicit null clears it
        settings.semester = payload.semester
    if payload.branch is not None:
        settings.branch = payload.branch
    if payload.daily_goal_minutes is not None:
        settings.daily_goal_minutes = payload.daily_goal_minutes
    db.commit()
    db.refresh(user)
    return user_out(db, user)
