"""
RAG API Router
REST endpoints for RAG indexing and chat with persistent history.
"""

import os
import time
from collections import defaultdict
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.rag_service import get_rag_service
from backend.db.connection import get_db
from backend.db.repositories.chat_repo import ChatRepository
from backend.services.permission_service import get_current_user
from backend.api.v1.admin import require_admin


router = APIRouter(prefix="/rag", tags=["RAG"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None  # If None, creates new session
    folder_ids: Optional[List[str]] = None
    file_ids: Optional[List[str]] = None  # Specific files to search in
    top_k: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str = ""
    citations: List[dict] = []
    chunks_used: int = 0
    elapsed_seconds: float = 0


class IndexFileRequest(BaseModel):
    file_id: str
    file_name: str
    mime_type: Optional[str] = None
    folder_id: Optional[str] = None
    folder_path: Optional[str] = None


class IndexResponse(BaseModel):
    success: bool
    file_id: str = ""
    file_name: str = ""
    chunks_count: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = 0
    error: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    total_chunks: int = 0
    total_files: int = 0
    vector_db: str = ""
    error: Optional[str] = None


# ============================================================================
# Rate Limiter (10 requests/minute per user)
# ============================================================================

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60  # seconds


async def check_rate_limit(current_user: dict = Depends(get_current_user)):
    """Enforce rate limit on RAG chat: max 10 requests per minute per user."""
    user_id = current_user["id"]
    now = time.time()
    # Clean old entries
    _rate_limit_store[user_id] = [t for t in _rate_limit_store[user_id] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[user_id]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_MAX} requests per minute. Please wait."
        )
    _rate_limit_store[user_id].append(now)
    return current_user


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def rag_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(check_rate_limit),
):
    """
    RAG Chat: Ask a question and get an AI answer with citations.
    Automatically saves messages to chat history per user.
    If session_id is not provided, creates a new session.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        repo = ChatRepository(db)
        user_id = current_user["id"]

        # Get or create session
        if request.session_id:
            session = await repo.get_session(request.session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            if str(session.user_id) != user_id:
                raise HTTPException(status_code=403, detail="Not your session")
            session_id = str(session.id)

            # Load chat history from DB for context
            messages = await repo.get_messages(session_id)
            chat_history = [
                {"role": m.role, "content": m.content}
                for m in messages[-10:]  # Last 10 messages for context
            ]
        else:
            # Create new session with question as title
            title = request.question[:80] + ("..." if len(request.question) > 80 else "")
            session = await repo.create_session(user_id=user_id, title=title)
            session_id = str(session.id)
            chat_history = []

        # Save user message to DB
        await repo.add_message(
            session_id=session_id,
            role="user",
            content=request.question,
        )

        # RAG query
        rag = get_rag_service()
        result = await rag.query(
            question=request.question,
            top_k=request.top_k,
            folder_ids=request.folder_ids,
            file_ids=request.file_ids,
            chat_history=chat_history,
        )

        # Save assistant message to DB (with citation info)
        citation_source_ids = [
            c.get("file_id", "") for c in result.get("citations", [])
        ]
        await repo.add_message(
            session_id=session_id,
            role="assistant",
            content=result.get("answer", ""),
            source_ids=citation_source_ids if citation_source_ids else None,
        )

        # Update session title if first message (auto-title)
        if not request.session_id:
            # Use first 80 chars of question as title
            title = request.question[:80] + ("..." if len(request.question) > 80 else "")
            await repo.update_session_title(session_id, title)

        return ChatResponse(
            answer=result.get("answer", ""),
            session_id=session_id,
            citations=result.get("citations", []),
            chunks_used=result.get("chunks_used", 0),
            elapsed_seconds=result.get("elapsed_seconds", 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {e}")


@router.post("/chat-stream")
async def rag_chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(check_rate_limit),
):
    """
    Streaming RAG Chat via Server-Sent Events.
    Sends: meta (citations), text chunks, done event.
    Saves chat history to DB after streaming completes.
    """
    import json

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    rag = get_rag_service()
    repo = ChatRepository(db)
    user_id = current_user["id"]
    session_id = request.session_id
    chat_history = []

    # Get or create session (same logic as /chat)
    if session_id:
        session = await repo.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if str(session.user_id) != user_id:
            raise HTTPException(status_code=403, detail="Not your session")
        session_id = str(session.id)
        messages = await repo.get_messages(session_id)
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in messages[-10:]
        ]
    else:
        title = request.question[:80] + ("..." if len(request.question) > 80 else "")
        session = await repo.create_session(user_id=user_id, title=title)
        session_id = str(session.id)

    # Save user message immediately
    await repo.add_message(
        session_id=session_id,
        role="user",
        content=request.question,
    )

    async def event_generator():
        full_answer = ""
        citations = []
        async for event in rag.smart_query_stream(
            question=request.question,
            chat_history=chat_history,
            file_ids=request.file_ids,
            folder_ids=request.folder_ids,
        ):
            event_type = event.get("type", "")
            if event_type == "meta":
                citations = event.get("citations", [])
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event_type == "status":
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event_type == "text":
                full_answer += event.get("chunk", "")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event_type == "done":
                event["session_id"] = session_id
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # Save assistant message to DB after streaming completes
                if full_answer:
                    try:
                        citation_source_ids = [c.get("file_id", "") for c in citations]
                        await repo.add_message(
                            session_id=session_id,
                            role="assistant",
                            content=full_answer,
                            source_ids=citation_source_ids if citation_source_ids else None,
                        )
                    except Exception:
                        pass  # Don't break stream if DB save fails

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/index", response_model=IndexResponse)
async def index_file(request: IndexFileRequest, admin: dict = Depends(require_admin)):
    """
    Index a file from Google Drive for RAG.
    Downloads the file, parses text, chunks it, generates embeddings,
    and stores in the vector database.
    """
    try:
        rag = get_rag_service()
        result = await rag.index_file_from_drive(
            file_id=request.file_id,
            file_name=request.file_name,
            mime_type=request.mime_type,
            folder_id=request.folder_id,
            folder_path=request.folder_path,
        )
        return IndexResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")


@router.post("/reindex")
async def reindex_folder(folder_id: str = Body(..., embed=True), admin: dict = Depends(require_admin)):
    """
    Re-index all files in a Google Drive folder.
    """
    try:
        from backend.services.gdrive_service import GoogleDriveService

        gdrive = GoogleDriveService()
        files = gdrive.list_files(folder_id)

        rag = get_rag_service()
        results = []

        for f in files:
            mime = f.get('mimeType', '')
            name = f.get('name', '')
            fid = f.get('id', '')

            if mime == 'application/vnd.google-apps.folder':
                continue
            if not DocumentParser.is_supported(name, mime):
                results.append({"file_id": fid, "file_name": name, "skipped": True, "reason": "unsupported format"})
                continue

            result = await rag.index_file_from_drive(
                file_id=fid,
                file_name=name,
                mime_type=mime,
                folder_id=folder_id,
            )
            results.append(result)

        success_count = len([r for r in results if r.get("success")])
        return {
            "total_files": len(results),
            "indexed": success_count,
            "skipped": len(results) - success_count,
            "details": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")


@router.get("/status", response_model=StatusResponse)
async def get_status(admin: dict = Depends(require_admin)):
    """Get RAG indexing status and statistics."""
    try:
        rag = get_rag_service()
        return StatusResponse(**(await rag.get_status()))
    except Exception as e:
        return StatusResponse(status="error", error=str(e))


@router.delete("/chunks/{file_id}")
async def delete_file_chunks(file_id: str, admin: dict = Depends(require_admin)):
    """Delete all indexed chunks for a specific file."""
    try:
        rag = get_rag_service()
        result = await rag.delete_file(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


# Import DocumentParser for reindex endpoint
from backend.services.document_parser import DocumentParser


@router.get("/indexed/{file_id}")
async def check_file_indexed(file_id: str):
    """Check if a file is already indexed in pgvector."""
    try:
        rag = get_rag_service()
        result = await rag.is_file_indexed(file_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check failed: {e}")
