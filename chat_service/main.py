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

@chat_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    
    try:
        u_id = uuid.UUID(user_id)
    except ValueError:
        u_id = user_id

    # Subscribe to all chats the user is a member of
    db: Session = next(get_db())
    member_chats = db.query(ChatMember.chat_id).filter(ChatMember.user_id == u_id).all()
    chat_ids = [str(c[0]) for c in member_chats]
    
    pubsub = redis_manager.get_pubsub()
    for cid in chat_ids:
        await pubsub.subscribe(f"chat_{cid}")
    
    # Add a personal channel for direct events (like new chat notifications)
    await pubsub.subscribe(f"user_{user_id}")

    async def broadcast_handler():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_text(json.dumps(data))
        except Exception as e:
            print(f"Broadcast error for {user_id}: {e}")

    broadcast_task = asyncio.create_task(broadcast_handler())

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            event_type = message_data.get("type", "message")
            chat_id = message_data.get("chat_id")
            
            # Use a fresh DB session for each message to avoid stale connections
            db_msg: Session = next(get_db())
            try:
                if event_type == "typing":
                    await redis_manager.publish(f"chat_{chat_id}", {
                        "type": "typing",
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "is_typing": message_data.get("is_typing")
                    })
                elif event_type == "read_receipt":
                    msg_id = message_data.get("message_id")
                    db_m = db_msg.query(Message).filter(Message.id == msg_id).first()
                    if db_m:
                        db_m.is_read = True
                        db_msg.commit()

                    await redis_manager.publish(f"chat_{chat_id}", {
                        "type": "read_receipt",
                        "message_id": msg_id,
                        "chat_id": chat_id,
                        "user_id": user_id
                    })
                elif event_type == "delete_message":
                    msg_id = message_data.get("message_id")
                    for_everyone = message_data.get("for_everyone", False)
                    db_m = db_msg.query(Message).filter(Message.id == msg_id).first()
                    
                    if db_m:
                        if for_everyone and str(db_m.sender_id) == user_id:
                            db_m.content = "This message was deleted"
                            db_m.message_type = "deleted"
                            db_msg.commit()
                            await redis_manager.publish(f"chat_{chat_id}", {
                                "type": "delete_message",
                                "message_id": msg_id,
                                "chat_id": chat_id,
                                "for_everyone": True
                            })
                        else:
                            # Delete for me
                            current_deleted = list(db_m.deleted_for_users or [])
                            if user_id not in current_deleted:
                                current_deleted.append(user_id)
                                db_m.deleted_for_users = current_deleted
                                db_msg.commit()
                            
                            await websocket.send_text(json.dumps({
                                "type": "delete_message",
                                "message_id": msg_id,
                                "chat_id": chat_id,
                                "for_everyone": False
                            }))

                elif event_type == "reaction":
                    msg_id = message_data.get("message_id")
                    emoji = message_data.get("emoji")
                    db_m = db_msg.query(Message).filter(Message.id == msg_id).first()
                    if db_m:
                        current_reactions = dict(db_m.reactions or {})
                        if emoji in current_reactions:
                            if user_id in current_reactions[emoji]:
                                current_reactions[emoji].remove(user_id)
                            else:
                                current_reactions[emoji].append(user_id)
                        else:
                            current_reactions[emoji] = [user_id]
                        
                        db_m.reactions = current_reactions
                        db_msg.add(db_m)
                        db_msg.commit()

                        await redis_manager.publish(f"chat_{chat_id}", {
                            "type": "reaction",
                            "message_id": msg_id,
                            "chat_id": chat_id,
                            "user_id": user_id,
                            "emoji": emoji,
                            "reactions": db_m.reactions
                        })
                else:
                    try:
                        c_id = uuid.UUID(chat_id)
                        u_id = uuid.UUID(user_id)
                    except ValueError:
                        c_id = chat_id
                        u_id = user_id
                        
                    new_msg = Message(
                        sender_id=u_id,
                        chat_id=c_id,
                        content=message_data.get("content"),
                        message_type=message_data.get("message_type", "text"),
                        file_url=message_data.get("file_url"),
                        reply_to_id=message_data.get("reply_to_id"),
                        reply_to_content=message_data.get("reply_to_content")
                    )
                    db_msg.add(new_msg)
                    db_msg.commit()
                    db_msg.refresh(new_msg)

                    await redis_manager.publish(f"chat_{chat_id}", {
                        "type": "message",
                        "id": str(new_msg.id),
                        "sender_id": user_id,
                        "chat_id": chat_id,
                        "content": new_msg.content,
                        "message_type": new_msg.message_type,
                        "file_url": new_msg.file_url,
                        "timestamp": new_msg.timestamp.isoformat(),
                        "reply_to_id": str(new_msg.reply_to_id) if new_msg.reply_to_id else None,
                        "reply_to_content": new_msg.reply_to_content
                    })
            finally:
                db_msg.close()
            
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        broadcast_task.cancel()
        await pubsub.unsubscribe()
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(user_id)
        broadcast_task.cancel()
        await pubsub.unsubscribe()
    finally:
        db.close()

@chat_router.get("/history/{chat_id}")
def get_chat_history(chat_id: str, user_id: str, db: Session = Depends(get_db)):
    try:
        c_id = uuid.UUID(chat_id)
    except ValueError:
        c_id = chat_id

    messages = db.query(Message).filter(
        Message.chat_id == c_id
    ).order_by(Message.timestamp.desc()).limit(50).all()
    
    # Filter out messages deleted "for me"
    visible_messages = [m for m in messages if user_id not in (m.deleted_for_users or [])]
    
    return [{
        "id": str(m.id),
        "sender_id": str(m.sender_id),
        "content": m.content,
        "message_type": m.message_type,
        "file_url": m.file_url,
        "timestamp": m.timestamp.isoformat(),
        "is_read": m.is_read,
        "reactions": m.reactions,
        "reply_to_id": str(m.reply_to_id) if m.reply_to_id else None,
        "reply_to_content": m.reply_to_content
    } for m in visible_messages]

@chat_router.get("/conversations/{user_id}")
def get_user_conversations(user_id: str, db: Session = Depends(get_db)):
    try:
        u_id = uuid.UUID(user_id)
    except ValueError:
        u_id = user_id

    chat_ids = db.query(ChatMember.chat_id).filter(ChatMember.user_id == u_id).all()
    chat_ids = [c[0] for c in chat_ids]
    
    chats = db.query(Chat).filter(Chat.id.in_(chat_ids)).all()
    
    # Importing User here to avoid circular dependency and handle separate Base classes
    from auth_service.models import User
    
    results = []
    for chat in chats:
        name = chat.name
        if not chat.is_group:
            # Find the other member's name
            other_member = db.query(ChatMember).filter(
                ChatMember.chat_id == chat.id,
                ChatMember.user_id != u_id
            ).first()
            if other_member:
                u = db.query(User).filter(User.id == other_member.user_id).first()
                if u:
                    name = u.name

        results.append({
            "id": str(chat.id),
            "name": name,
            "is_group": chat.is_group,
            "created_at": chat.created_at.isoformat()
        })
    return results

@chat_router.post("/chats/create")
def create_chat(data: dict, db: Session = Depends(get_db)):
    is_group = data.get("is_group", False)
    members = data.get("members", [])
    
    # For 1-on-1 chats, check if one already exists
    if not is_group and len(members) == 2:
        try:
            u1, u2 = uuid.UUID(members[0]), uuid.UUID(members[1])
        except ValueError:
            u1, u2 = members[0], members[1]
        
        # Find chat IDs that u1 is a member of
        u1_chats = db.query(ChatMember.chat_id).filter(ChatMember.user_id == u1).all()
        u1_chat_ids = [c[0] for c in u1_chats]
        
        # Find which of those u2 is ALSO a member of, and is NOT a group chat
        existing_chat = db.query(Chat).join(ChatMember).filter(
            Chat.id == ChatMember.chat_id,
            Chat.id.in_(u1_chat_ids),
            ChatMember.user_id == u2,
            Chat.is_group == False
        ).first()
        
        if existing_chat:
            return {"id": str(existing_chat.id), "status": "existing"}

    new_chat = Chat(
        name=data.get("name"),
        is_group=is_group
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    for user_id in members:
        try:
            u_id = uuid.UUID(user_id)
        except ValueError:
            u_id = user_id
        member = ChatMember(chat_id=new_chat.id, user_id=u_id)
        db.add(member)
    db.commit()
    
    return {"id": str(new_chat.id), "status": "created"}
