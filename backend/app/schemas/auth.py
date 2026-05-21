"""Auth-related Pydantic schemas."""

from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    # Plain str — login is authenticated by password match; email is just the lookup key.
    # Using EmailStr would reject reserved TLDs like `.local` that users may have on purpose.
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role: str = "user"


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: UUID
    # Plain str on output — existing users may have reserved TLDs like `.local`
    # (e.g. the bootstrap admin) that EmailStr would reject during serialization.
    email: str
    role: str
    full_name: str | None
    is_active: bool

    model_config = {"from_attributes": True}
