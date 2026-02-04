"""
Chat API Routes
NotebookLM chat and query endpoints
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.models.requests import ChatRequest
from backend.models.responses import ChatResponse
from backend.services.notebooklm_service import get_notebooklm_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    Real-time chat endpoint with SSE streaming.
    
    Streams the AI response as Server-Sent Events for real-time display.
    """
    notebook_id = request.notebook_id or settings.NOTEBOOK_ID
    
    if not notebook_id:
        raise HTTPException(status_code=400, detail="No notebook_id provided")
    
    async def generate():
        try:
            notebooklm = get_notebooklm_service()
            
            # Query notebook
            response = await notebooklm.query_async(
                notebook_id=notebook_id,
                message=request.message,
                source_ids=request.source_ids
            )
            
            # Stream response in chunks
            chunk_size = 20
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                yield {
                    "event": "message",
                    "data": chunk
                }
            
            # Done event
            yield {
                "event": "done",
                "data": "[DONE]"
            }
            
        except Exception as e:
            yield {
                "event": "error",
                "data": str(e)
            }
    
    return EventSourceResponse(generate())


@router.post("", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """
    Synchronous chat endpoint (non-streaming).
    
    Useful for simple integrations or when SSE is not supported.
    """
    notebook_id = request.notebook_id or settings.NOTEBOOK_ID
    
    if not notebook_id:
        raise HTTPException(status_code=400, detail="No notebook_id provided")
    
    try:
        notebooklm = get_notebooklm_service()
        
        response = await notebooklm.query_async(
            notebook_id=notebook_id,
            message=request.message,
            source_ids=request.source_ids
        )
        
        return ChatResponse(
            response=response,
            sources=[],
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notebooks")
async def list_notebooks():
    """
    List all available notebooks.
    
    Returns list of notebooks accessible to the authenticated user.
    """
    try:
        notebooklm = get_notebooklm_service()
        notebooks = notebooklm.list_notebooks()
        
        result = []
        for nb in notebooks:
            result.append({
                "id": nb.id if hasattr(nb, 'id') else str(nb),
                "title": nb.title if hasattr(nb, 'title') else "Untitled",
                "source_count": len(nb.sources) if hasattr(nb, 'sources') else 0,
                "url": nb.url if hasattr(nb, 'url') else None
            })
        
        return {"notebooks": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/{notebook_id}")
async def get_sources(notebook_id: str):
    """
    Get sources/documents in a notebook.
    
    Returns list of source documents available in the specified notebook.
    """
    try:
        notebooklm = get_notebooklm_service()
        sources = notebooklm.get_sources(notebook_id)
        
        result = []
        for src in sources:
            result.append({
                "id": src.id if hasattr(src, 'id') else str(src),
                "title": src.title if hasattr(src, 'title') else "Untitled",
                "type": src.type if hasattr(src, 'type') else "unknown"
            })
        
        return {"sources": result, "count": len(result)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
