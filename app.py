from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os

# Import each service's logic
# Note: Since they are in subdirectories, we will treat them as modules
from auth_service.main import auth_router
from chat_service.main import chat_router
from call_service.main import call_router

# Import database setup
from auth_service.db import engine as auth_engine, Base as auth_Base
from chat_service.models import engine as chat_engine, Base as chat_Base

# Create all tables on startup
auth_Base.metadata.create_all(bind=auth_engine)
chat_Base.metadata.create_all(bind=chat_engine)

app = FastAPI(title="ChatSphere Unified Backend")

# Import redis manager from chat_service
from chat_service.redis_manager import redis_manager

@app.on_event("startup")
async def startup_event():
    await redis_manager.connect()

# Enable CORS for Flutter app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the routers with prefixes
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(chat_router, prefix="/chat", tags=["Chat"])
app.include_router(call_router, prefix="/call", tags=["Call"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "ChatSphere Unified Backend is Live"}
