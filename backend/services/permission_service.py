"""
Permission Service for RBAC
Checks user permissions on resources with inheritance.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repositories.user_repo import UserRepository
from backend.db.repositories.role_repo import RoleRepository


async def check_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_code: str,
    resource_type: str = None,
    resource_id: str = None,
) -> bool:
    """
    Check if user has permission. Resolution order:
    1. Explicit permission on resource -> allow/deny
    2. Inherited from parent resource -> allow/deny
    3. Role-based permission -> allow
    4. Default -> deny
    """
    role_repo = RoleRepository(db)
    user_repo = UserRepository(db)

    # Get permission type
    perm_type = await role_repo.get_permission_type_by_code(permission_code)
    if not perm_type:
        return False

    # Check user roles first to see if super_admin
    roles = await user_repo.get_roles(user_id)
    if "super_admin" in roles:
        return True  # Super admin has all permissions

    # If resource specified, check granular permissions
    if resource_type and resource_id:
        result = await role_repo.check_resource_permission(
            user_id, perm_type.id, resource_type, resource_id
        )
        if result is not None:
            return result

    # Fall back to role-based permissions
    return await role_repo.check_role_has_permission(user_id, perm_type.id)


# =============================================================================
# FastAPI Dependency - require_permission
# =============================================================================

from functools import wraps
from fastapi import Depends, HTTPException, Request
from backend.db.connection import get_db
from backend.services.auth_service import decode_access_token
from backend.db.models import User
from sqlalchemy import select


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """
    FastAPI dependency to get current authenticated user from JWT.
    Reads token from cookie or Authorization header.
    """
    token = None

    # Try cookie first
    token = request.cookies.get("access_token")

    # Then try Authorization header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Verify user still exists and is active
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    return {
        "id": payload["sub"],
        "email": payload["email"],
        "roles": payload["roles"],
    }


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Like get_current_user but returns None instead of 401.
    Use for endpoints that work both with and without auth.
    """
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


def require_permission(permission_code: str, resource_type: str = None):
    """
    Decorator factory for permission-protected endpoints.
    
    Usage:
        @router.get("/protected")
        async def endpoint(
            current_user: dict = Depends(require_permission("view", "folder"))
        ):
            ...
    """
    async def permission_checker(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        user = await get_current_user(request, db)

        # Get resource_id from path/query if applicable
        resource_id = request.path_params.get("resource_id") or request.query_params.get("resource_id")

        has_permission = await check_permission(
            db,
            UUID(user["id"]),
            permission_code,
            resource_type,
            resource_id,
        )

        if not has_permission:
            raise HTTPException(
                status_code=403, 
                detail=f"Permission denied: {permission_code}"
            )

        return user

    return Depends(permission_checker)

