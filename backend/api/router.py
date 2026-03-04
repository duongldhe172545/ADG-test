"""
API Router
Combines all API route modules
"""

from fastapi import APIRouter

from backend.api.v1 import auth, documents, health
from backend.api.v1 import rbac_auth, admin, approvals, chat_history
from backend.api.v1 import rag
from backend.api.v1 import dashboard

# Create main API router
api_router = APIRouter(prefix="/api/v1")

# Include all route modules
api_router.include_router(auth.router)

api_router.include_router(chat_history.router)
api_router.include_router(documents.router)
api_router.include_router(health.router)

# RBAC routes
api_router.include_router(rbac_auth.router)
api_router.include_router(admin.router)
api_router.include_router(approvals.router)

# RAG routes
api_router.include_router(rag.router)

# Dashboard routes
api_router.include_router(dashboard.router)




