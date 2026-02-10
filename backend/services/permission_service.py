"""
Permission Service for RBAC
Checks user permissions on resources with inheritance.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    User, Role, UserRole, Permission, PermissionType, 
    Resource, RolePermission
)


async def check_permission(
    db: AsyncSession,
    user_id: UUID,
    permission_code: str,
    resource_type: str = None,
    resource_id: str = None,
) -> bool:
    """
    Check if user has permission. Resolution order:
    1. Explicit permission on resource → allow/deny
    2. Inherited from parent resource → allow/deny
    3. Role-based permission → allow
    4. Default → deny
    """
    
    # Get permission type
    pt_result = await db.execute(
        select(PermissionType).where(PermissionType.code == permission_code)
    )
    perm_type = pt_result.scalars().first()
    if not perm_type:
        return False
    
    # Check user roles first to see if super_admin
    roles = await _get_user_roles(db, user_id)
    if "super_admin" in roles:
        return True  # Super admin has all permissions
    
    # If resource specified, check granular permissions
    if resource_type and resource_id:
        result = await _check_resource_permission(
            db, user_id, perm_type.id, resource_type, resource_id
        )
        if result is not None:
            return result
    
    # Fall back to role-based permissions
    return await _check_role_permission(db, user_id, perm_type.id)


async def _get_user_roles(db: AsyncSession, user_id: UUID) -> list[str]:
    """Get role names for user"""
    result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def _check_resource_permission(
    db: AsyncSession,
    user_id: UUID,
    perm_type_id: UUID,
    resource_type: str,
    resource_id: str,
) -> Optional[bool]:
    """
    Check permission on specific resource.
    Walks up the parent chain for inheritance.
    Returns True/False if found, None if no explicit permission.
    """
    # Find resource
    res_result = await db.execute(
        select(Resource).where(
            Resource.resource_type == resource_type,
            Resource.resource_id == resource_id,
        )
    )
    resource = res_result.scalars().first()
    
    if not resource:
        return None  # Resource not registered, fall through to role
    
    # Check permission on this resource
    perm_result = await db.execute(
        select(Permission).where(
            Permission.user_id == user_id,
            Permission.resource_id == resource.id,
            Permission.permission_type_id == perm_type_id,
        )
    )
    perm = perm_result.scalars().first()
    
    if perm:
        return perm.is_granted  # Explicit allow or deny
    
    # Check parent resource (inheritance)
    if resource.parent_id:
        parent_result = await db.execute(
            select(Resource).where(Resource.id == resource.parent_id)
        )
        parent = parent_result.scalars().first()
        if parent:
            return await _check_resource_permission(
                db, user_id, perm_type_id,
                parent.resource_type, parent.resource_id,
            )
    
    return None  # No explicit permission found


async def _check_role_permission(
    db: AsyncSession,
    user_id: UUID,
    perm_type_id: UUID,
) -> bool:
    """Check if any of user's roles grant this permission"""
    result = await db.execute(
        select(RolePermission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            RolePermission.permission_type_id == perm_type_id,
        )
    )
    return result.scalars().first() is not None


# =============================================================================
# FastAPI Dependency - require_permission
# =============================================================================

from functools import wraps
from fastapi import Depends, HTTPException, Request
from backend.db.connection import get_db
from backend.services.auth_service import decode_access_token


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
    user_result = await db.execute(
        select(User).where(User.id == payload["sub"], User.is_active == True)
    )
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    
    return {
        "id": payload["sub"],
        "email": payload["email"],
        "roles": payload["roles"],
    }


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
