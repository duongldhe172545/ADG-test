"""
Pydantic Models for API Requests
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoints"""
    message: str = Field(..., description="User's message/question")
    notebook_id: Optional[str] = Field(None, description="Notebook ID to query")
    source_ids: Optional[List[str]] = Field(None, description="Limit to specific sources")


class UploadRequest(BaseModel):
    """Request model for file uploads (metadata only, file sent separately)"""
    folder_id: str = Field(..., description="Destination folder ID")
    custom_name: Optional[str] = Field(None, description="Custom filename")
