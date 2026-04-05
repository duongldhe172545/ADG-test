"""
Admin API - Roles & Permission Types
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import Role, PermissionType
from backend.api.v1.admin_users import require_admin, require_admin_or_manager

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin_or_manager)
):
    """List all available roles"""
    result = await db.execute(select(Role).order_by(Role.priority.desc()))
    roles = result.scalars().all()
    
    return {
        "roles": [
            {"id": str(r.id), "name": r.name, "description": r.description, "priority": r.priority}
            for r in roles
        ]
    }


@router.get("/permission-types")
async def list_permission_types(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """List all permission types"""
    result = await db.execute(select(PermissionType))
    types = result.scalars().all()
    
    return {
        "permission_types": [
            {"id": str(t.id), "code": t.code, "name": t.name, "description": t.description}
            for t in types
        ]
    }
