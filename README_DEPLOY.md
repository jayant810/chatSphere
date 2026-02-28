# ChatSphere Backend Deployment Guide

This repository contains the microservices for ChatSphere.

## Services
1. **Auth Service**: Port 8001 (Handles Google Login & JWT)
2. **Chat Service**: Port 8002 (Handles WebSockets & Persistence)
3. **Call Service**: Port 8003 (Handles WebRTC Signaling)

## Deployment on Render.com
For each service, create a new **Web Service** on Render:

### 1. Auth Service
- **Root Directory**: `backend/auth_service`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `DATABASE_URL`: [Your Neon Postgres URL]
  - `SECRET_KEY`: [A random string]
  - `GOOGLE_CLIENT_ID`: [Your Google OAuth Client ID]

### 2. Chat Service
- **Root Directory**: `backend/chat_service`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `DATABASE_URL`: [Your Neon Postgres URL]
  - `REDIS_URL`: [Your Upstash Redis URL]

### 3. Call Service
- **Root Directory**: `backend/call_service`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `REDIS_URL`: [Your Upstash Redis URL]
