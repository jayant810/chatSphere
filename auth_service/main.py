from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List, Optional
import os
from jose import JWTError, jwt

from google.oauth2 import id_token
from google.auth.transport import requests

# Use relative imports as it will be run from backend/app.py
from .db import get_db
from .models import User
from .schemas import UserCreate, UserResponse, Token, UserUpdate
from .auth import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM

# Google Client ID from environment variables
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

auth_router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

@auth_router.post("/auth/google")
def auth_google(data: dict, db: Session = Depends(get_db)):
    token = data.get("id_token")
    try:
      # Verify the ID token
      id_info = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)

      email = id_info['email']
      name = id_info.get('name', '')
      picture = id_info.get('picture', '')

      # Check if user exists, otherwise create
      db_user = db.query(User).filter(User.email == email).first()
      if not db_user:
          db_user = User(
              name=name,
              email=email,
              password_hash="google_auth",
              profile_pic_url=picture
          )
          db.add(db_user)
      else:
          # Update profile pic if it changed
          db_user.profile_pic_url = picture
      
      db.commit()
      db.refresh(db_user)

      access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
      access_token = create_access_token(
          data={"sub": db_user.email}, expires_delta=access_token_expires
      )
      return {
          "access_token": access_token, 
          "token_type": "bearer",
          "user_id": str(db_user.id),
          "name": db_user.name,
          "profile_pic_url": db_user.profile_pic_url
      }
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=401, detail="Invalid Google Token")

@auth_router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        name=user.name,
        email=user.email,
        password_hash=hashed_password,
        about=user.about or "Available"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@auth_router.post("/login", response_model=Token)
def login(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_id": str(db_user.id)
    }

@auth_router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@auth_router.post("/update", response_model=UserResponse)
def update_profile(user_update: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_update.name is not None:
        current_user.name = user_update.name
    if user_update.about is not None:
        current_user.about = user_update.about
    if user_update.profile_pic_url is not None:
        current_user.profile_pic_url = user_update.profile_pic_url
    
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
