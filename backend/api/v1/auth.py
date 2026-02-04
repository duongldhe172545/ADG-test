"""
Authentication API Routes
OAuth2 endpoints for Google authentication
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from backend.core.auth.oauth import get_oauth_service
from backend.models.responses import AuthStatusResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login")
async def login():
    """
    Redirect user to Google OAuth login.
    
    Initiates the OAuth2 authorization flow by redirecting
    the user to Google's consent screen.
    """
    oauth_service = get_oauth_service()
    
    try:
        auth_url, state = oauth_service.get_authorization_url()
        return RedirectResponse(url=auth_url)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def callback(code: str = None, error: str = None):
    """
    Handle OAuth callback from Google.
    
    Exchanges the authorization code for tokens and redirects
    back to the upload page with success/error status.
    """
    if error:
        return RedirectResponse(url=f"/upload?error={error}")
    
    if not code:
        return RedirectResponse(url="/upload?error=No authorization code received")
    
    oauth_service = get_oauth_service()
    
    try:
        credentials = oauth_service.exchange_code(code)
        email = oauth_service.get_user_email(credentials)
        return RedirectResponse(url=f"/upload?auth=success&email={email or 'user'}")
    except Exception as e:
        return RedirectResponse(url=f"/upload?error={str(e)}")


@router.get("/status", response_model=AuthStatusResponse)
async def status():
    """
    Check OAuth authentication status.
    
    Returns whether the user is authenticated and their email if available.
    """
    oauth_service = get_oauth_service()
    return oauth_service.get_status()


@router.post("/logout")
async def logout():
    """
    Clear OAuth tokens (logout).
    
    Removes saved tokens so user must re-authenticate.
    """
    oauth_service = get_oauth_service()
    oauth_service.clear_tokens()
    return {"success": True, "message": "Logged out"}
