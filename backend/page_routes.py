"""
Page Routes
HTML page serving routes for the application.
"""

import os
from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse


# Template directory
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "templates"
)


def _serve(template_name: str):
    """Serve an HTML template by name."""
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
    async def sources_page():
        return _serve("sources.html")

    @app.get("/upload", response_class=HTMLResponse)
    async def upload_page():
        return _serve("upload.html")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page():
        return _serve("dashboard.html")

    @app.get("/approval-history", response_class=HTMLResponse)
    async def approval_history_page():
        return _serve("approval_history.html")

    # Admin pages
    @app.get("/admin-dashboard", response_class=HTMLResponse)
    async def admin_dashboard_page():
        return _serve("admin_dashboard.html")

    @app.get("/admin/users", response_class=HTMLResponse)
    async def admin_users_page():
        return _serve("admin_users.html")

    @app.get("/admin/approvals", response_class=HTMLResponse)
    async def admin_approvals_page():
        return _serve("admin_approvals.html")

    @app.get("/admin/folders", response_class=HTMLResponse)
    async def admin_folders_page():
        return _serve("admin_folders.html")
