"""
Pydantic Models for API Responses
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="Service status")
    drive_auth: str = Field("unknown", description="Google Drive auth status")


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



# Update forward refs for recursive models
FolderItem.model_rebuild()
