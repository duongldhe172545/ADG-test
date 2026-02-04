"""
OAuth2 Configuration for Google Drive Upload
Manages OAuth tokens with auto-refresh capability
"""

import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

# OAuth2 Configuration - Use full drive access to read existing folders and upload files
SCOPES = ['https://www.googleapis.com/auth/drive']

# Token storage directory
TOKEN_DIR = Path.home() / '.adg-upload'
TOKEN_FILE = TOKEN_DIR / 'oauth_token.json'

# OAuth Client credentials (set via environment or direct)
OAUTH_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID', '')
OAUTH_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET', '')
OAUTH_REDIRECT_URI = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:8080/api/drive/oauth/callback')


def get_client_config() -> dict:
    """Get OAuth client configuration"""
    return {
        "web": {
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [OAUTH_REDIRECT_URI]
        }
    }


def create_auth_flow() -> Flow:
    """Create OAuth2 flow for authorization"""
    flow = Flow.from_client_config(
        get_client_config(),
        scopes=SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI
    )
    return flow


def get_authorization_url() -> tuple[str, str]:
    """
    Get the authorization URL for user login.
    Returns: (auth_url, state)
    """
    flow = create_auth_flow()
    auth_url, state = flow.authorization_url(
        access_type='offline',  # Get refresh_token
        include_granted_scopes='true',
        prompt='consent'  # Force consent to always get refresh_token
    )
    return auth_url, state


def exchange_code_for_tokens(code: str) -> Credentials:
    """
    Exchange authorization code for tokens.
    Returns: Credentials object
    """
    flow = create_auth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Save tokens
    save_tokens(credentials)
    
    return credentials


def save_tokens(credentials: Credentials):
    """Save OAuth tokens to file"""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    
    token_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': list(credentials.scopes) if credentials.scopes else SCOPES,
        'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
        'saved_at': datetime.now().isoformat()
    }
    
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)
    
    print(f"✅ OAuth tokens saved to {TOKEN_FILE}")


def load_tokens() -> Optional[Credentials]:
    """
    Load OAuth tokens from file.
    Returns: Credentials object or None if not found/invalid
    """
    if not TOKEN_FILE.exists():
        return None
    
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
        
        credentials = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_data.get('client_id', OAUTH_CLIENT_ID),
            client_secret=token_data.get('client_secret', OAUTH_CLIENT_SECRET),
            scopes=token_data.get('scopes', SCOPES)
        )
        
        # Check if token needs refresh
        if credentials.expired and credentials.refresh_token:
            print("🔄 Access token expired, refreshing...")
            credentials.refresh(Request())
            save_tokens(credentials)  # Save refreshed tokens
            print("✅ Token refreshed successfully!")
        
        return credentials
        
    except Exception as e:
        print(f"❌ Error loading tokens: {e}")
        return None


def get_valid_credentials() -> Optional[Credentials]:
    """
    Get valid OAuth credentials.
    Returns: Valid Credentials or None if user needs to login
    """
    credentials = load_tokens()
    
    if not credentials:
        return None
    
    # If expired and has refresh token, try to refresh
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            save_tokens(credentials)
        except Exception as e:
            print(f"❌ Token refresh failed: {e}")
            return None
    
    return credentials


def is_authenticated() -> bool:
    """Check if user is authenticated with valid tokens"""
    credentials = get_valid_credentials()
    return credentials is not None and credentials.valid


def clear_tokens():
    """Clear saved tokens (logout)"""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print("🗑️ OAuth tokens cleared")


def get_user_email(credentials: Credentials) -> Optional[str]:
    """Get the email of the authenticated user"""
    try:
        from googleapiclient.discovery import build
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        return user_info.get('email')
    except Exception:
        return None
