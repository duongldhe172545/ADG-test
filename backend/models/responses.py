"""
Pydantic Models for API Responses
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ChatResponse(BaseModel):
    """Response model for chat endpoints"""
    response: str = Field(..., description="AI response text")
    sources: List[Any] = Field(default=[], description="Sources used")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="Service status")
    notebooklm_auth: str = Field(..., description="NotebookLM auth status")
    last_refresh: Optional[str] = Field(None, description="Last auth refresh time")
    notebook_count: Optional[int] = Field(None, description="Number of accessible notebooks")


class AuthStatusResponse(BaseModel):
    """Response model for OAuth status"""
    authenticated: bool
    email: Optional[str] = None
    has_refresh_token: Optional[bool] = None


class FolderItem(BaseModel):
    """Model for folder tree items"""
    id: str
    name: str
    children: List['FolderItem'] = []


class FolderTreeResponse(BaseModel):
    """Response model for folder listing"""
    root_id: str
    folders: List[FolderItem]


class UploadResponse(BaseModel):
    """Response model for file uploads"""
    success: bool
    id: Optional[str] = None
    name: Optional[str] = None
    mimeType: Optional[str] = None
    webViewLink: Optional[str] = None


class NotebookInfo(BaseModel):
    """Model for notebook information"""
    id: str
    title: str
    source_count: int = 0
    url: Optional[str] = None


# Update forward refs for recursive models
FolderItem.model_rebuild()
