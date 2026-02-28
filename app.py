from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import uuid
import shutil

# Import each service's logic
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

# Ensure uploads directory exists
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

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

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_extension = file.filename.split(".")[-1]
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Return the URL to access the file
    # Note: In production, this should be the full Render URL
    return {"url": f"/uploads/{file_name}", "filename": file_name}

# Include the routers with prefixes
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(chat_router, prefix="/chat", tags=["Chat"])
app.include_router(call_router, prefix="/call", tags=["Call"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "ChatSphere Unified Backend is Live"}
