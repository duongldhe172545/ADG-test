"""
OAuth2 Service for Google Authentication
Handles token management, authorization flows, and credentials
"""

import os
import json
from pathlib import Path
from typing import Optional, Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from backend.config import settings


class OAuthService:
    """
    Service for handling Google OAuth2 authentication.
    
    Manages the OAuth flow, token storage, and credential refreshing.
    """
    
    SCOPES = settings.oauth_scopes_list
    
    def __init__(self):
        self._token_file = Path(settings.token_storage_path) / "oauth_token.json"
        self._ensure_token_dir()
    
    def _ensure_token_dir(self):
        """Ensure token storage directory exists"""
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
    
    # ==========================================================================
    # Authorization Flow
    # ==========================================================================
    
    def get_client_config(self) -> dict:
        """Get OAuth client configuration from settings"""
        if not settings.is_oauth_configured():
            raise ValueError("OAuth not configured. Set OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET")
        
        return {
            "web": {
                "client_id": settings.OAUTH_CLIENT_ID,
                "client_secret": settings.OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.OAUTH_REDIRECT_URI]
            }
        }
    
    def create_flow(self) -> Flow:
        """Create OAuth2 flow for authorization"""
        flow = Flow.from_client_config(
            self.get_client_config(),
            scopes=self.SCOPES,
            redirect_uri=settings.OAUTH_REDIRECT_URI
        )
        return flow
    
    def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate Google OAuth authorization URL.
        
        Returns:
            Tuple of (authorization_url, state)
        """
        flow = self.create_flow()
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent to get refresh token
        )
        return authorization_url, state
    
    def exchange_code(self, code: str) -> Credentials:
        """
        Exchange authorization code for credentials.
        
        Args:
            code: Authorization code from OAuth callback
            
        Returns:
            Google Credentials object
        """
        flow = self.create_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Save tokens for future use
        self._save_tokens(credentials)
        
        return credentials
    
    # ==========================================================================
    # Token Management
    # ==========================================================================
    
    def _save_tokens(self, credentials: Credentials) -> None:
        """Save OAuth tokens to file"""
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes) if credentials.scopes else self.SCOPES
        }
        
        with open(self._token_file, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print(f"✅ OAuth tokens saved to {self._token_file}")
    
    def _load_tokens(self) -> Optional[Credentials]:
        """Load OAuth tokens from file"""
        if not self._token_file.exists():
            return None
        
        try:
            with open(self._token_file, 'r') as f:
                token_data = json.load(f)
            
            credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=token_data.get('client_id', settings.OAUTH_CLIENT_ID),
                client_secret=token_data.get('client_secret', settings.OAUTH_CLIENT_SECRET),
                scopes=token_data.get('scopes', self.SCOPES)
            )
            
            return credentials
        except Exception as e:
            print(f"⚠️ Error loading tokens: {e}")
            return None
    
    def get_valid_credentials(self) -> Optional[Credentials]:
        """
        Get valid credentials, refreshing if needed.
        
        Returns:
            Valid Credentials object or None if not authenticated
        """
        credentials = self._load_tokens()
        
        if not credentials:
            return None
        
        # Refresh if expired
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._save_tokens(credentials)
                print("🔄 Access token refreshed")
            except Exception as e:
                print(f"❌ Token refresh failed: {e}")
                return None
        
        return credentials if credentials.valid else None
    
    def clear_tokens(self) -> None:
        """Clear all saved tokens (logout)"""
        if self._token_file.exists():
            self._token_file.unlink()
            print("🗑️ OAuth tokens cleared")
    
    # ==========================================================================
    # Status & User Info
    # ==========================================================================
    
    def get_status(self) -> dict:
        """
        Get current authentication status.
        
        Returns:
            Dict with authenticated status and user info
        """
        credentials = self.get_valid_credentials()
        
        if credentials and credentials.valid:
            email = self.get_user_email(credentials)
            return {
                "authenticated": True,
                "email": email,
                "has_refresh_token": bool(credentials.refresh_token)
            }
        
        return {"authenticated": False}
    
    def get_user_email(self, credentials: Credentials) -> Optional[str]:
        """
        Get user's email from Google.
        
        Args:
            credentials: Valid OAuth credentials
            
        Returns:
            User's email address or None
        """
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info.get('email')
        except Exception as e:
            print(f"⚠️ Could not get user email: {e}")
            return None
    
    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated"""
        credentials = self.get_valid_credentials()
        return credentials is not None and credentials.valid


# Singleton instance
_oauth_service: Optional[OAuthService] = None


def get_oauth_service() -> OAuthService:
    """Get or create OAuth service singleton"""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service
