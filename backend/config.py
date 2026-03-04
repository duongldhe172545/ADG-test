"""
Centralized Configuration for ADG Knowledge Management System
All settings loaded from environment variables with validation
"""

import os
from typing import List, Optional, Union
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ==========================================================================
    # Application Settings
    # ==========================================================================
    APP_NAME: str = "ADG Knowledge Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    SECRET_KEY: str = Field(default="change-me-in-production", description="Secret key for security")
    
    # ==========================================================================
    # Server Settings
    # ==========================================================================
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    
    # ==========================================================================
    # CORS Settings
    # ==========================================================================
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Allowed CORS origins (comma-separated)"
    )
    
    @property
    def cors_origins_list(self) -> list:
        """Parse CORS_ORIGINS into list"""
        if not self.CORS_ORIGINS:
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(',') if origin.strip()]
    
    # ==========================================================================
    # OAuth2 / Google Authentication
    # ==========================================================================
    OAUTH_CLIENT_ID: str = Field(default="", description="Google OAuth Client ID")
    OAUTH_CLIENT_SECRET: str = Field(default="", description="Google OAuth Client Secret")
    OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8080/api/v1/auth/callback",
        description="OAuth callback URL"
    )
    OAUTH_SCOPES: str = Field(
        default="https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/userinfo.profile",
        description="OAuth scopes to request (comma-separated)"
    )
    
    @property
    def oauth_scopes_list(self) -> list:
        """Parse OAUTH_SCOPES into list"""
        if not self.OAUTH_SCOPES:
            return ["https://www.googleapis.com/auth/drive"]
        return [scope.strip() for scope in self.OAUTH_SCOPES.split(',') if scope.strip()]
    
    # ==========================================================================
    # Google Drive Settings
    # ==========================================================================
    GDRIVE_ROOT_FOLDER_ID: str = Field(
        default="",
        description="Root folder ID for document storage"
    )
    GDRIVE_SERVICE_ACCOUNT_FILE: Optional[str] = Field(
        default=None,
        description="Path to service account JSON (optional, for fallback)"
    )
    GDRIVE_SERVICE_ACCOUNT_JSON: Optional[str] = Field(
        default=None,
        description="Service account JSON content as string (for Railway/cloud deployment)"
    )
    GDRIVE_PENDING_FOLDER_ID: str = Field(
        default="",
        description="Folder ID for pending uploads (awaiting approval)"
    )
    GDRIVE_REFRESH_TOKEN: str = Field(
        default="",
        description="Google Drive refresh token (generated via scripts/generate_drive_token.py)"
    )
    
    # ==========================================================================
    # Token Storage
    # ==========================================================================
    TOKEN_STORAGE_DIR: str = Field(
        default="~/.adg-kms",
        description="Directory for storing OAuth tokens"
    )
    
    # ==========================================================================
    # Database Settings
    # ==========================================================================
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (postgresql://user:pass@host:port/db)"
    )
    RAG_DATABASE_URL: Optional[str] = Field(
        default=None,
        description="RAG vector DB URL (defaults to DATABASE_URL if not set)"
    )
    
    # ==========================================================================
    # JWT Settings
    # ==========================================================================
    JWT_SECRET_KEY: str = Field(
        default="change-me-in-production-jwt-secret",
        description="Secret key for JWT tokens"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = Field(
        default=1440,  # 24 hours
        description="JWT token expiration in minutes"
    )
    
    # ==========================================================================
    # Response Settings
    # ==========================================================================
    ENABLE_BRANDING: bool = False
    BRANDING_TEXT: str = "🤖 Powered by ADG KMS"
    FILTER_PATTERNS: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars
    
    @property
    def token_storage_path(self) -> str:
        """Get expanded token storage path"""
        return os.path.expanduser(self.TOKEN_STORAGE_DIR)
    
    def is_oauth_configured(self) -> bool:
        """Check if OAuth is properly configured"""
        return bool(self.OAUTH_CLIENT_ID and self.OAUTH_CLIENT_SECRET)

    def validate_critical(self) -> list:
        """Check critical settings at startup. Returns list of warnings."""
        warnings = []
        if not self.DATABASE_URL:
            warnings.append("DATABASE_URL not set — database features will not work")
        if not self.OAUTH_CLIENT_ID or not self.OAUTH_CLIENT_SECRET:
            warnings.append("OAUTH_CLIENT_ID/SECRET not set — Google login will not work")
        if not self.GDRIVE_REFRESH_TOKEN:
            warnings.append("GDRIVE_REFRESH_TOKEN not set — Drive access will not work")
        return warnings


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Using lru_cache ensures settings are only loaded once.
    """
    return Settings()


# Convenience alias
settings = get_settings()
