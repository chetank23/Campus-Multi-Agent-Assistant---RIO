from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserAdminResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Literal["ADMIN", "FACULTY", "STUDENT"]
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserAdminCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    role: Literal["ADMIN", "FACULTY", "STUDENT"]
    department_id: Optional[int] = None


class UserAdminUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    role: Optional[Literal["ADMIN", "FACULTY", "STUDENT"]] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


class UserListResponse(BaseModel):
    items: List[UserAdminResponse]
    total: int
    skip: int
    limit: int

