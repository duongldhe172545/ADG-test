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
