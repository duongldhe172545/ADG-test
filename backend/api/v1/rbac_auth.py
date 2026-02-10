"""
RBAC Authentication API Routes
Google OAuth login with whitelist check and JWT tokens.
"""

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth.oauth import get_oauth_service
from backend.db.connection import get_db
from backend.services.auth_service import (
    login_user, decode_access_token, get_user_with_roles
)
from backend.services.permission_service import get_current_user
from backend.config import settings

router = APIRouter(prefix="/rbac", tags=["RBAC Authentication"])


@router.get("/login")
async def rbac_login(request: Request):
    """
    Start RBAC login flow.
    Redirects to Google OAuth with user info scope.
    """
    oauth_service = get_oauth_service()
    
    try:
        # Derive RBAC redirect URI from existing OAuth setting
        parsed = urlparse(settings.OAUTH_REDIRECT_URI)
        rbac_redirect_uri = f"{parsed.scheme}://{parsed.netloc}/api/v1/rbac/callback"
        print(f"🔑 RBAC redirect URI: {rbac_redirect_uri}")
        
        from google_auth_oauthlib.flow import Flow
        
        # Add openid scope (Google adds it automatically, must match)
        rbac_scopes = list(oauth_service.SCOPES) + ['openid']
        rbac_scopes = list(set(rbac_scopes))  # deduplicate
        
        flow = Flow.from_client_config(
            oauth_service.get_client_config(),
            scopes=rbac_scopes,
            redirect_uri=rbac_redirect_uri,
        )
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
        )
        return RedirectResponse(url=auth_url)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def rbac_callback(
    request: Request,
    code: str = None, 
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle OAuth callback for RBAC login.
    1. Exchange code for Google credentials
    2. Get user info from Google
    3. Check whitelist
    4. Generate JWT
    5. Set cookie and redirect
    """
    if error:
        return RedirectResponse(url=f"/login?error={error}")
    
    if not code:
        return RedirectResponse(url="/login?error=no_code")
    
    oauth_service = get_oauth_service()
    
    try:
        # Derive RBAC redirect URI from existing OAuth setting
        parsed = urlparse(settings.OAUTH_REDIRECT_URI)
        rbac_redirect_uri = f"{parsed.scheme}://{parsed.netloc}/api/v1/rbac/callback"
        
        from google_auth_oauthlib.flow import Flow
        
        rbac_scopes = list(oauth_service.SCOPES) + ['openid']
        rbac_scopes = list(set(rbac_scopes))
        
        flow = Flow.from_client_config(
            oauth_service.get_client_config(),
            scopes=rbac_scopes,
            redirect_uri=rbac_redirect_uri,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Get user info from Google
        from googleapiclient.discovery import build
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        
        email = user_info.get('email')
        name = user_info.get('name')
        avatar_url = user_info.get('picture')
        
        print(f"🔍 RBAC callback - Google email: {email}, name: {name}")
        
        if not email:
            return RedirectResponse(url="/login?error=no_email")
        
        # Check whitelist and login
        result = await login_user(db, email, name, avatar_url)
        
        if not result:
            print(f"❌ User {email} NOT in whitelist")
            return RedirectResponse(
                url=f"/login?error=not_whitelisted&email={email}"
            )
        
        print(f"✅ User {email} logged in, roles: {result['user']['roles']}")
        
        # Redirect based on role
        roles = result['user']['roles']
        if 'super_admin' in roles or 'admin' in roles:
            redirect_url = "/admin-dashboard"
        else:
            redirect_url = "/"
        
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key="access_token",
            value=result["token"],
            httponly=True,
            max_age=60 * 60 * 24,  # 24 hours
            samesite="lax",
        )
        return response
        
    except Exception as e:
        print(f"❌ RBAC login error: {e}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(url=f"/login?error={str(e)}")


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    return current_user


@router.post("/logout")
async def rbac_logout():
    """Logout: clear JWT cookie"""
    response = JSONResponse(content={"success": True, "message": "Logged out"})
    response.delete_cookie("access_token")
    return response


@router.get("/check")
async def check_auth(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Quick auth check - returns whether user is authenticated.
    Queries FRESH roles from database (not stale JWT payload).
    """
    token = request.cookies.get("access_token")
    if not token:
        return {"authenticated": False}
    
    payload = decode_access_token(token)
    if not payload:
        return {"authenticated": False}
    
    # Query fresh roles from database (not JWT payload)
    from uuid import UUID
    user_data = await get_user_with_roles(db, UUID(payload["sub"]))
    if not user_data or not user_data.get("is_active"):
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "email": user_data["email"],
        "roles": user_data["roles"],
    }
