from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import OptUtcDatetime, ORMModel, UtcDatetime


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    answer_mode: str = "exam"
    semester: int | None = None
    branch: str | None = None
    daily_goal_minutes: int = 60
    llm_provider: str | None = None
    llm_model: str | None = None


class UserOut(ORMModel):
    id: int
    email: str
    name: str
    created_at: UtcDatetime
    last_login_at: OptUtcDatetime = None
    profile: UserProfile = UserProfile()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    answer_mode: str | None = None
    semester: int | None = Field(default=None, ge=1, le=8)
    branch: str | None = Field(default=None, max_length=40)
    daily_goal_minutes: int | None = Field(default=None, ge=10, le=720)
