from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import List, Dict
import json
import uuid
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

# Relative imports
from .models import Chat, Message, ChatMember, get_db
from .redis_manager import redis_manager

chat_router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

# This is a bit tricky with APIRouter, better to handle in app.py or with a lifespan
# For now we'll keep it here but call it from somewhere or ensure it's called
# await redis_manager.connect() is handled in app.py's lifespan or startup

@chat_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            event_type = message_data.get("type", "message")
            chat_id = message_data.get("chat_id")
            
            if event_type == "typing":
                await redis_manager.publish(f"chat_{chat_id}", {
                    "type": "typing",
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "is_typing": message_data.get("is_typing")
                })
            elif event_type == "read_receipt":
                db: Session = next(get_db())
                msg_id = message_data.get("message_id")
                db_msg = db.query(Message).filter(Message.id == msg_id).first()
                if db_msg:
                    db_msg.is_read = True
                    db.commit()

                await redis_manager.publish(f"chat_{chat_id}", {
                    "type": "read_receipt",
                    "message_id": msg_id,
                    "chat_id": chat_id,
                    "user_id": user_id
                })
            elif event_type == "reaction":
                db: Session = next(get_db())
                msg_id = message_data.get("message_id")
                emoji = message_data.get("emoji")
                db_msg = db.query(Message).filter(Message.id == msg_id).first()
                if db_msg:
                    current_reactions = dict(db_msg.reactions or {})
                    if emoji in current_reactions:
                        if user_id in current_reactions[emoji]:
                            current_reactions[emoji].remove(user_id)
                        else:
                            current_reactions[emoji].append(user_id)
                    else:
                        current_reactions[emoji] = [user_id]
                    
                    db_msg.reactions = current_reactions
                    db.add(db_msg)
                    db.commit()

                await redis_manager.publish(f"chat_{chat_id}", {
                    "type": "reaction",
                    "message_id": msg_id,
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "emoji": emoji,
                    "reactions": db_msg.reactions if db_msg else {}
                })
            else:
                db: Session = next(get_db())
                new_msg = Message(
                    sender_id=user_id,
                    chat_id=chat_id,
                    content=message_data.get("content"),
                    message_type=message_data.get("message_type", "text"),
                    file_url=message_data.get("file_url")
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                await redis_manager.publish(f"chat_{chat_id}", {
                    "type": "message",
                    "id": str(new_msg.id),
                    "sender_id": user_id,
                    "chat_id": chat_id,
                    "content": new_msg.content,
                    "message_type": new_msg.message_type,
                    "file_url": new_msg.file_url,
                    "timestamp": new_msg.timestamp.isoformat()
                })
            
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(user_id)

@chat_router.get("/history/{chat_id}", response_model=List[dict])
def get_chat_history(chat_id: str, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.timestamp.desc()).limit(50).all()
    return [{
        "id": str(m.id),
        "sender_id": str(m.sender_id),
        "content": m.content,
        "message_type": m.message_type,
        "file_url": m.file_url,
        "timestamp": m.timestamp.isoformat(),
        "is_read": m.is_read,
        "reactions": m.reactions
    } for m in messages]

@chat_router.get("/conversations/{user_id}", response_model=List[dict])
def get_user_conversations(user_id: str, db: Session = Depends(get_db)):
    chat_ids = db.query(ChatMember.chat_id).filter(ChatMember.user_id == user_id).all()
    chat_ids = [c[0] for c in chat_ids]
    
    chats = db.query(Chat).filter(Chat.id.in_(chat_ids)).all()
    return [{
        "id": str(c.id),
        "name": c.name,
        "is_group": c.is_group,
        "created_at": c.created_at.isoformat()
    } for c in chats]

@chat_router.post("/chats/create")
def create_chat(data: dict, db: Session = Depends(get_db)):
    new_chat = Chat(
        name=data.get("name"),
        is_group=data.get("is_group", False)
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    for user_id in data.get("members", []):
        member = ChatMember(chat_id=new_chat.id, user_id=user_id)
        db.add(member)
    db.commit()
    
    return {"id": str(new_chat.id), "status": "created"}
