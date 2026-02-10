"""
API Router
Combines all API route modules
"""

from fastapi import APIRouter, UploadFile, File, Form

from backend.api.v1 import auth, chat, documents, health
from backend.api.v1 import rbac_auth, admin, approvals
from backend.models.requests import ChatRequest

# Create main API router
api_router = APIRouter(prefix="/api/v1")

# Include all route modules
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(health.router)

# RBAC routes
api_router.include_router(rbac_auth.router)
api_router.include_router(admin.router)
api_router.include_router(approvals.router)


# =============================================================================
# Legacy routes for backward compatibility
# These map old /api/* endpoints to new /api/v1/* endpoints
# =============================================================================
legacy_router = APIRouter(prefix="/api")


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@legacy_router.get("/health")
async def legacy_health():
    """Legacy: /api/health -> /api/v1/health"""
    return await health.health_check()


# -----------------------------------------------------------------------------
# OAuth / Drive Auth
# -----------------------------------------------------------------------------
@legacy_router.get("/drive/oauth/login")
async def legacy_oauth_login():
    """Legacy: Redirect to new auth endpoint"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/v1/auth/login")

@legacy_router.get("/drive/oauth/callback")
async def legacy_oauth_callback(code: str = None, error: str = None):
    """Legacy: Redirect to new auth endpoint"""
    from fastapi.responses import RedirectResponse
    params = []
    if code:
        params.append(f"code={code}")
    if error:
        params.append(f"error={error}")
    query = "&".join(params)
    return RedirectResponse(url=f"/api/v1/auth/callback?{query}")

@legacy_router.get("/drive/oauth/status")
async def legacy_oauth_status():
    """Legacy: /api/drive/oauth/status -> /api/v1/auth/status"""
    return await auth.status()

@legacy_router.post("/drive/oauth/logout")
async def legacy_oauth_logout():
    """Legacy: /api/drive/oauth/logout -> /api/v1/auth/logout"""
    return await auth.logout()


# -----------------------------------------------------------------------------
# Drive Auth (alternative path used by sources.html)
# -----------------------------------------------------------------------------
@legacy_router.get("/drive/auth/status")
async def legacy_drive_auth_status():
    """Legacy: /api/drive/auth/status -> /api/v1/auth/status"""
    return await auth.status()

@legacy_router.get("/drive/auth/login")
async def legacy_drive_auth_login():
    """Legacy: /api/drive/auth/login -> /api/v1/auth/login"""
    return await auth.login()

@legacy_router.post("/drive/auth/logout")
async def legacy_drive_auth_logout():
    """Legacy: /api/drive/auth/logout -> /api/v1/auth/logout"""
    return await auth.logout()


# -----------------------------------------------------------------------------
# Google Drive Folders & Upload
# -----------------------------------------------------------------------------
@legacy_router.get("/drive/folders")
async def legacy_folders(parent_id: str = None):
    """Legacy: /api/drive/folders -> /api/v1/documents/folders"""
    return await documents.list_folders(parent_id=parent_id)

@legacy_router.post("/drive/upload")
async def legacy_upload(file: UploadFile = File(...), folder_id: str = Form(...)):
    """Legacy: /api/drive/upload -> /api/v1/documents/upload"""
    return await documents.upload_file(file=file, folder_id=folder_id)


# -----------------------------------------------------------------------------
# NotebookLM Chat
# -----------------------------------------------------------------------------
@legacy_router.get("/notebooks")
async def legacy_notebooks():
    """Legacy: /api/notebooks -> /api/v1/chat/notebooks"""
    return await chat.list_notebooks()

@legacy_router.get("/sources/{notebook_id}")
async def legacy_sources(notebook_id: str):
    """Legacy: /api/sources/{id} -> /api/v1/chat/sources/{id}"""
    return await chat.get_sources(notebook_id)

@legacy_router.post("/chat")
async def legacy_chat(request: ChatRequest):
    """Legacy: /api/chat -> /api/v1/chat"""
    return await chat.chat_sync(request)

@legacy_router.post("/chat/stream")
async def legacy_chat_stream(request: ChatRequest):
    """Legacy: /api/chat/stream -> /api/v1/chat/stream"""
    return await chat.chat_stream(request)

