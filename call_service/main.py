from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
import json
import os
import aioredis

app = FastAPI(title="ChatSphere Call Signaling Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CallConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(data)

manager = CallConnectionManager()

@app.websocket("/ws/call/{user_id}")
async def call_websocket(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            target_user_id = data.get("target_user_id")
            event_type = data.get("type") # offer, answer, ice-candidate, call-request
            
            # Relay signaling data to target user
            if target_user_id:
                await manager.send_to_user(target_user_id, {
                    "from_user_id": user_id,
                    "type": event_type,
                    "payload": data.get("payload")
                })
                
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        print(f"Call Signaling error: {e}")
        manager.disconnect(user_id)

@app.get("/health")
def health_check():
    return {"status": "ok"}
