from sqlalchemy import Column, String, Boolean, DateTime, UUID, ForeignKey, JSON
import uuid
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/chatsphere")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Chat(Base):
    __tablename__ = "chats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    is_group = Column(Boolean, default=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMember(Base):
    __tablename__ = "chat_members"
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), primary_key=True)
    role = Column(String, default="member") # admin/member

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), index=True)
    sender_id = Column(UUID(as_uuid=True), index=True)
    content = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    message_type = Column(String, default="text") # text/image/file
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    reactions = Column(JSON, default={}) # {emoji: [user_ids]}
    reply_to_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    reply_to_content = Column(String, nullable=True)
    deleted_for_users = Column(JSON, default=[]) # list of user_ids who deleted for themselves

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
