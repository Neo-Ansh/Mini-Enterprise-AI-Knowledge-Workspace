# app/models.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# ── Auth models ───────────────────────────────────────────────────────

class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    status: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class RegisterResponse(BaseModel):
    message: str
    name: str
    email: str
    status: str


class PendingUserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    status: str
    created_at: datetime


# ── Workspace membership models ── Phase 5.5-B ────────────────────────

class AssignMemberRequest(BaseModel):
    user_id: str
    workspace_role: str = "member"   # "member" or "viewer"


class WorkspaceMemberResponse(BaseModel):
    user_id: str
    name: str
    email: str
    workspace_role: str
    added_at: datetime


# ── Document models ───────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    session_id: str
    pdf_name: str
    size_bytes: int
    uploaded_by: str
    uploaded_by_name: str
    workspace_id: Optional[str]
    created_at: datetime