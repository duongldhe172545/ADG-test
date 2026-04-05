"""
Page Routes
HTML page serving routes for the application.
Uses Jinja2 templates with base.html inheritance for pages that have been migrated.
"""

import os
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


# Template directory
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "templates"
)

# Jinja2 template engine
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _serve(template_name: str):
    """Serve an HTML template by name (legacy - raw file serving)."""
    path = os.path.join(TEMPLATES_DIR, template_name)
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse(f"<h1>ADG KMS - {template_name} not found</h1>")


def register_page_routes(app: FastAPI):
    """Register all HTML page routes on the FastAPI app."""

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return _serve("landing.html")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        return _serve("login.html")

    @app.get("/sources", response_class=HTMLResponse)
    async def sources_page(request: Request):
        return templates.TemplateResponse("sources.html", {"request": request, "active_page": "sources"})

    @app.get("/upload", response_class=HTMLResponse)
    async def upload_page(request: Request):
        return templates.TemplateResponse("upload.html", {"request": request, "active_page": "upload"})

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})

    @app.get("/approval-history", response_class=HTMLResponse)
    async def approval_history_page(request: Request):
        return templates.TemplateResponse("approval_history.html", {"request": request, "active_page": "approval_history"})

    # Admin pages
    @app.get("/admin-dashboard", response_class=HTMLResponse)
    async def admin_dashboard_page(request: Request):
        return templates.TemplateResponse("admin_dashboard.html", {"request": request, "active_page": "admin_dashboard"})

    @app.get("/admin/users", response_class=HTMLResponse)
    async def admin_users_page(request: Request):
        return templates.TemplateResponse("admin_users.html", {"request": request, "active_page": "admin_users"})

    @app.get("/admin-users")
    async def admin_users_page_alias():
        """Redirect to canonical /admin/users URL"""
        return RedirectResponse(url="/admin/users", status_code=302)

    @app.get("/admin/approvals", response_class=HTMLResponse)
    async def admin_approvals_page(request: Request):
        return templates.TemplateResponse("admin_approvals.html", {"request": request, "active_page": "admin_approvals"})

    @app.get("/admin/folders", response_class=HTMLResponse)
    async def admin_folders_page(request: Request):
        return templates.TemplateResponse("admin_folders.html", {"request": request, "active_page": "admin_folders"})

    @app.get("/admin/activity-logs", response_class=HTMLResponse)
    async def admin_activity_logs_page(request: Request):
        return templates.TemplateResponse("admin_activity_logs.html", {"request": request, "active_page": "admin_activity_logs"})
