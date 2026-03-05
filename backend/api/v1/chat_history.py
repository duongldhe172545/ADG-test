"""
Chat History API Routes
CRUD endpoints for chat sessions and messages
"""

from uuid import UUID
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.repositories.chat_repo import ChatRepository
from backend.services.permission_service import get_current_user

router = APIRouter(prefix="/chat-history", tags=["Chat History"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateSessionRequest(BaseModel):
    title: str = Field(default="New Chat")
    notebook_id: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str
    source_ids: Optional[List[str]] = None


class UpdateTitleRequest(BaseModel):
    title: str


# =============================================================================
# Routes
# =============================================================================

@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all chat sessions for current user"""
    repo = ChatRepository(db)
    sessions = await repo.get_user_sessions(current_user["id"])
    return {
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "notebook_id": s.notebook_id,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.post("/sessions")
async def create_session(
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new chat session"""
    repo = ChatRepository(db)
    session = await repo.create_session(
        user_id=current_user["id"],
        title=req.title,
        notebook_id=req.notebook_id,
    )
    return {
        "id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a chat session with its messages"""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership
    if str(session.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your session")

    messages = await repo.get_messages(session_id)
    
    # Resolve file names for source_ids
    all_file_ids = set()
    for m in messages:
        if m.source_ids:
            all_file_ids.update(m.source_ids)
    
    source_names = {}
    if all_file_ids:
        try:
            import asyncpg
            from backend.config import settings
            conn = await asyncpg.connect(settings.NEON_DATABASE_URL)
            rows = await conn.fetch(
                "SELECT DISTINCT file_id, file_name FROM document_chunks WHERE file_id = ANY($1)",
                list(all_file_ids)
            )
            await conn.close()
            source_names = {row["file_id"]: row["file_name"] for row in rows}
        except Exception:
            pass
    
    return {
        "id": str(session.id),
        "title": session.title,
        "notebook_id": session.notebook_id,
        "source_names": source_names,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "source_ids": m.source_ids,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.post("/sessions/{session_id}/messages")
async def add_message(
    session_id: str,
    req: AddMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Add a message to a session"""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your session")

    message = await repo.add_message(
        session_id=session_id,
        role=req.role,
        content=req.content,
        source_ids=req.source_ids,
    )
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    req: UpdateTitleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update session title"""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your session")

    updated = await repo.update_session_title(session_id, req.title)
    return {"id": str(updated.id), "title": updated.title}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a chat session"""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your session")

    await repo.delete_session(session_id)
    return {"success": True}
