from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    name: str
    email: EmailStr
    about: Optional[str] = "Available"

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    about: Optional[str] = None
    profile_pic_url: Optional[str] = None

class UserResponse(UserBase):
    id: UUID
    is_online: bool
    last_seen: datetime
    created_at: datetime
    profile_pic_url: Optional[str] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str

class TokenData(BaseModel):
    email: Optional[str] = None
