"""
API Router
Combines all API route modules
"""

from fastapi import APIRouter

from backend.api.v1 import documents, health
from backend.api.v1 import rbac_auth, admin_users, admin_departments, admin_roles, admin_folders
from backend.api.v1 import approval_submit, approval_queries, approval_review
from backend.api.v1 import chat_history
from backend.api.v1 import rag
from backend.api.v1 import dashboard
from backend.api.v1 import activity_logs, notifications

# Create main API router
api_router = APIRouter(prefix="/api/v1")

# Include all route modules
api_router.include_router(chat_history.router)
api_router.include_router(documents.router)
api_router.include_router(health.router)

# RBAC routes
api_router.include_router(rbac_auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_departments.router)
api_router.include_router(admin_roles.router)
api_router.include_router(admin_folders.router)
api_router.include_router(approval_submit.router)
api_router.include_router(approval_queries.router)
api_router.include_router(approval_review.router)

# RAG routes
api_router.include_router(rag.router)

# Dashboard routes
api_router.include_router(dashboard.router)

# Activity logs & notifications
api_router.include_router(activity_logs.router)
api_router.include_router(notifications.router)
