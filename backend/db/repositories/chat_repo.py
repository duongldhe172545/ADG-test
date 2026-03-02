"""
Chat Repository - Database operations for chat sessions and messages
"""

from uuid import UUID
from typing import Optional, List

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ChatSession, ChatMessage


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self, user_id, title: str = "New Chat", notebook_id: str = None
    ) -> ChatSession:
        """Create a new chat session"""
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        session = ChatSession(
            user_id=user_id, title=title, notebook_id=notebook_id
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id) -> Optional[ChatSession]:
        """Get a chat session by ID"""
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        return result.scalars().first()

    async def get_user_sessions(self, user_id, limit: int = 50) -> List[ChatSession]:
        """Get all chat sessions for a user, most recent first"""
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatSession.updated_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def add_message(
        self, session_id, role: str, content: str, source_ids: list = None
    ) -> ChatMessage:
        """Add a message to a chat session"""
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            source_ids=source_ids,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(self, session_id) -> List[ChatMessage]:
        """Get all messages for a session"""
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return result.scalars().all()

    async def delete_session(self, session_id) -> bool:
        """Delete a chat session and its messages"""
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        session = await self.get_session(session_id)
        if not session:
            return False
        await self.db.delete(session)
        await self.db.commit()
        return True

    async def update_session_title(self, session_id, title: str) -> Optional[ChatSession]:
        """Update a session's title"""
        if isinstance(session_id, str):
            session_id = UUID(session_id)
        session = await self.get_session(session_id)
        if not session:
            return None
        session.title = title
        await self.db.commit()
        await self.db.refresh(session)
        return session
