"""
RBAC Authentication API Routes
Google OAuth login with whitelist check and JWT tokens.
"""

from urllib.parse import urlparse, urlencode

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


def _get_rbac_redirect_uri() -> str:
    """Derive RBAC callback URI from OAUTH_REDIRECT_URI setting"""
    parsed = urlparse(settings.OAUTH_REDIRECT_URI)
    return f"{parsed.scheme}://{parsed.netloc}/api/v1/rbac/callback"


@router.get("/login")
async def rbac_login(request: Request):
    """
    Start RBAC login flow.
    Redirects to Google OAuth — manually constructed URL (no PKCE).
    """
    oauth_service = get_oauth_service()
    
    if not settings.is_oauth_configured():
        raise HTTPException(status_code=500, detail="OAuth not configured")
    
    rbac_redirect_uri = _get_rbac_redirect_uri()
    print(f"🔑 RBAC redirect URI: {rbac_redirect_uri}")
    
    # Build scopes
    rbac_scopes = list(set(oauth_service.SCOPES + ['openid']))
    
    # Construct OAuth URL manually — no PKCE
    params = {
        'client_id': settings.OAUTH_CLIENT_ID,
        'redirect_uri': rbac_redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(rbac_scopes),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
    }
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def rbac_callback(
    request: Request,
    code: str = None, 
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle OAuth callback for RBAC login.
    Exchanges code via direct HTTP POST (no PKCE).
    """
    if error:
        return RedirectResponse(url=f"/login?error={error}")
    
    if not code:
        return RedirectResponse(url="/login?error=no_code")
    
    try:
        import httpx
        
        rbac_redirect_uri = _get_rbac_redirect_uri()
        
        # Exchange authorization code for tokens via direct HTTP POST
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code': code,
                    'client_id': settings.OAUTH_CLIENT_ID,
                    'client_secret': settings.OAUTH_CLIENT_SECRET,
                    'redirect_uri': rbac_redirect_uri,
                    'grant_type': 'authorization_code',
                }
            )
        
        if token_response.status_code != 200:
            error_data = token_response.json()
            error_msg = error_data.get('error_description', error_data.get('error', 'Token exchange failed'))
            print(f"❌ Token exchange failed: {error_data}")
            return RedirectResponse(url=f"/login?error={error_msg}")
        
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        
        # Get user info from Google using access token
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'}
            )
        
        if userinfo_response.status_code != 200:
            return RedirectResponse(url="/login?error=failed_to_get_user_info")
        
        user_info = userinfo_response.json()
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
        if 'super_admin' in roles:
            redirect_url = "/admin/users"
        else:
            redirect_url = "/dashboard"
        
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key="access_token",
            value=result["token"],
            httponly=True,
            secure=True,
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
