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
        
        # Service already returns formatted dictionaries
        return {"sources": sources, "count": len(sources)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/{notebook_id}/{source_id}/content")
async def get_source_content(notebook_id: str, source_id: str):
    """
    Get full text content of a source document.
    
    Returns the complete text content of the specified source.
    """
    try:
        notebooklm = get_notebooklm_service()
        client = notebooklm.get_client()
        # API only takes source_id, returns dict
        result = client.get_source_fulltext(source_id)
        
        # Extract content from result dict - key is 'content' not 'text'
        content = result.get('content', '') if isinstance(result, dict) else str(result)
        
        return {
            "source_id": source_id,
            "notebook_id": notebook_id,
            "content": content,
            "type": "fulltext"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/{notebook_id}/{source_id}/guide")
async def get_source_guide(notebook_id: str, source_id: str):
    """
    Get AI-generated guide/summary of a source document.
    
    Returns a structured summary and key points from the source.
    """
    try:
        notebooklm = get_notebooklm_service()
        client = notebooklm.get_client()
        # API only takes source_id
        result = client.get_source_guide(source_id)
        
        # Extract guide from result
        guide = result.get('guide', '') if isinstance(result, dict) else str(result)
        
        return {
            "source_id": source_id,
            "notebook_id": notebook_id,
            "guide": guide,
            "type": "guide"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

