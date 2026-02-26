"""
ADG Knowledge Management System
FastAPI Application Entry Point

This is the main entry point for the application.
All routes, middleware, and configuration are set up here.
"""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from backend.config import settings
from backend.api.router import api_router, legacy_router
from backend.services.scheduler_service import get_scheduler_service
from backend.services.auth_service import decode_access_token


# Pages that don't require authentication
PUBLIC_PAGES = {"/", "/login", "/docs", "/redoc", "/openapi.json"}

# Page → allowed roles mapping
# Pages not listed here are open to all authenticated users
PAGE_ROLES = {
    "/admin-dashboard": ["admin", "super_admin"],
    "/admin/users":     ["admin", "super_admin"],
    "/admin/approvals": ["admin", "super_admin"],
    "/admin/folders":   ["admin", "super_admin"],
    "/upload":          ["editor", "admin", "super_admin"],
    "/approval-history":["viewer", "editor", "approver", "admin", "super_admin"],
    "/dashboard":       ["viewer", "editor", "approver", "admin", "super_admin"],
    "/sources":         ["viewer", "editor", "approver", "admin", "super_admin"],
    "/chatbot":         ["viewer", "editor", "approver", "admin", "super_admin"],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    print("🚀 Starting ADG Knowledge Management System...")
    
    # Start background scheduler
    scheduler = get_scheduler_service()
    scheduler.start()
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")
    scheduler.stop()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Knowledge Management System powered by NotebookLM",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)


# =============================================================================
# Middleware
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth guard middleware for page routes
@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """Protect page routes - redirect to /login if not authenticated"""
    path = request.url.path
    
    # Skip: public pages, API routes, static files
    if (path in PUBLIC_PAGES
        or path.startswith("/api/")
        or path.startswith("/static/")
        or path.startswith("/favicon")
    ):
        return await call_next(request)
    
    # Check JWT cookie for protected pages
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    
    payload = decode_access_token(token)
    if not payload:
        response = RedirectResponse(url="/login", status_code=302)
        response.delete_cookie("access_token")
        return response
    
    # Page-level role check (use JWT roles for speed)
    allowed_roles = PAGE_ROLES.get(path)
    if allowed_roles:
        user_roles = payload.get("roles", [])
        if not any(r in allowed_roles for r in user_roles):
            # No permission → redirect to home
            return RedirectResponse(url="/", status_code=302)
    
    return await call_next(request)


# =============================================================================
# API Routes
# =============================================================================

# New versioned API routes
app.include_router(api_router)

# Legacy routes for backward compatibility
app.include_router(legacy_router)


# =============================================================================
# Page Routes (HTML)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the landing page"""
    template_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "frontend", "templates", "landing.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Landing page not found</h1>")


@app.get("/chatbot", response_class=HTMLResponse)
async def chatbot_page():
    """Serve the chatbot UI with 3-panel layout"""
    template_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "frontend", "templates", "chatbot.html"
    )
    
    # Fallback to index.html if chatbot.html doesn't exist yet
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "frontend", "templates", "index.html"
        )
    
    # Fallback to old location
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "web_chatbot", "static", "index.html"
        )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Chat UI not found</h1>")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page():
    """Serve the upload wizard UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "upload.html"
    )
    
    # Fallback to old location if new doesn't exist
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "web_chatbot", "static", "upload.html"
        )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Upload UI not found</h1>")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """Serve the dashboard UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "dashboard.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Dashboard UI not found</h1>")


@app.get("/sources", response_class=HTMLResponse)
async def sources_page():
    """Serve the source selection UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "sources.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Sources UI not found</h1>")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve the RBAC login page"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "login.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Login page not found</h1>")


@app.get("/admin-dashboard")
async def admin_dashboard_redirect():
    """Redirect old admin dashboard to new URL"""
    return RedirectResponse(url="/admin/users", status_code=302)


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page():
    """Serve the admin users page"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "admin_users.html"
    )
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return HTMLResponse("<h1>ADG KMS - Admin Users not found</h1>")


@app.get("/admin/approvals", response_class=HTMLResponse)
async def admin_approvals_page():
    """Serve the admin approvals page"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "admin_approvals.html"
    )
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return HTMLResponse("<h1>ADG KMS - Admin Approvals not found</h1>")


@app.get("/admin/folders", response_class=HTMLResponse)
async def admin_folders_page():
    """Serve the admin folders page"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "admin_folders.html"
    )
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return HTMLResponse("<h1>ADG KMS - Admin Folders not found</h1>")


@app.get("/approval-history", response_class=HTMLResponse)
async def approval_history_page():
    """Serve the approval history page"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "approval_history.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Approval History not found</h1>")


# =============================================================================
# Static Files
# =============================================================================

# Try new static location first, fallback to old
static_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")
if not os.path.exists(static_path):
    static_path = os.path.join(os.path.dirname(__file__), "..", "web_chatbot", "static")

if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


# =============================================================================
# Run Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
