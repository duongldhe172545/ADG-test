"""
Middleware Configuration
Auth guard and CORS middleware for the application.
"""

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.config import settings
from backend.services.auth_service import decode_access_token


# Pages that don't require authentication
PUBLIC_PAGES = {"/", "/login", "/docs", "/redoc", "/openapi.json"}

# Page → allowed roles mapping
PAGE_ROLES = {
    "/admin-dashboard": ["super_admin"],
    "/admin/users":     ["super_admin", "admin"],
    "/admin/approvals": ["admin", "manager"],
    "/admin/folders":   ["admin", "manager"],
    "/upload":          ["admin", "manager", "employer"],
    "/approval-history":["admin", "manager", "employer"],
    "/dashboard":       ["super_admin", "admin", "manager", "employer"],
    "/sources":         ["admin", "manager", "employer"],
}


def setup_middleware(app: FastAPI):
    """Configure all middleware for the application."""

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth guard
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

        # Page-level role check — query DB for fresh roles
        allowed_roles = PAGE_ROLES.get(path)
        if allowed_roles:
            try:
                from backend.db.connection import get_async_session_factory
                from backend.services.auth_service import get_user_roles
                AsyncSessionLocal = get_async_session_factory()
                async with AsyncSessionLocal() as db:
                    user_roles = await get_user_roles(db, UUID(payload["sub"]))
                if not any(r in allowed_roles for r in user_roles):
                    return RedirectResponse(url="/", status_code=302)
            except Exception:
                # Fallback to JWT roles if DB unavailable
                user_roles = payload.get("roles", [])
                if not any(r in allowed_roles for r in user_roles):
                    return RedirectResponse(url="/", status_code=302)

        return await call_next(request)
