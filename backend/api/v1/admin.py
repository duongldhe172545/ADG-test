"""
Admin API - User & Permission Management
Only accessible by admin/super_admin roles.
"""

from uuid import UUID
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import User, Role, UserRole, PermissionType
from backend.services.permission_service import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Request/Response Models
# =============================================================================

class AddUserRequest(BaseModel):
    email: str
    name: Optional[str] = None
    roles: List[str] = ["viewer"]  # Default role

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[List[str]] = None

class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    is_active: bool
    roles: List[str]
    last_login: Optional[str]
    created_at: str


# =============================================================================
# Admin Guard
# =============================================================================

async def require_admin(current_user: dict = Depends(get_current_user)):
    """Ensure current user is admin or super_admin"""
    if not any(r in ["admin", "super_admin"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# =============================================================================
# User Management
# =============================================================================

@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """List all users with their roles"""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    
    user_list = []
    for user in users:
        # Get roles
        role_result = await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
        roles = [r[0] for r in role_result.all()]
        
        user_list.append({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "roles": roles,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat(),
        })
    
    return {"users": user_list}


@router.post("/users")
async def add_user(
    req: AddUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Add a new user to the whitelist"""
    # Check if user already exists
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Create user
    user = User(email=req.email, name=req.name, is_active=True)
    db.add(user)
    await db.flush()
    
    # Assign roles
    for role_name in req.roles:
        role_result = await db.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalars().first()
        if role:
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db.add(user_role)
    
    await db.commit()
    
    return {"success": True, "user_id": str(user.id), "message": f"User {req.email} added"}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Update user info or roles"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update basic info
    if req.name is not None:
        user.name = req.name
    if req.is_active is not None:
        user.is_active = req.is_active
    
    # Update roles if provided
    if req.roles is not None:
        # Remove existing roles
        await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
        
        # Add new roles
        for role_name in req.roles:
            role_result = await db.execute(select(Role).where(Role.name == role_name))
            role = role_result.scalars().first()
            if role:
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db.add(user_role)
    
    await db.commit()
    
    return {"success": True, "message": f"User {user.email} updated"}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Deactivate user (soft delete)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = False
    await db.commit()
    
    return {"success": True, "message": f"User {user.email} deactivated"}


# =============================================================================
# Roles & Permissions
# =============================================================================

@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
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


# =============================================================================
# Folder Management (Admin Only)
# =============================================================================

class CreateFolderRequest(BaseModel):
    name: str
    parent_folder_id: Optional[str] = None  # GDrive parent folder ID


@router.post("/folders")
async def create_folder(
    req: CreateFolderRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Create a new folder on Google Drive (admin only).
    Also registers as a resource in the RBAC system.
    """
    from backend.services.gdrive_service import get_gdrive_service
    from backend.db.models import Resource
    from backend.config import settings
    
    parent_id = req.parent_folder_id or settings.GDRIVE_ROOT_FOLDER_ID
    
    try:
        gdrive = get_gdrive_service()
        
        # Create folder on Google Drive
        file_metadata = {
            "name": req.name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = gdrive.service.files().create(
            body=file_metadata, fields="id, name"
        ).execute()
        
        # Register as resource in RBAC
        # Find parent resource if exists
        parent_resource = None
        if req.parent_folder_id:
            parent_result = await db.execute(
                select(Resource).where(
                    Resource.resource_type == "folder",
                    Resource.resource_id == req.parent_folder_id,
                )
            )
            parent_resource = parent_result.scalars().first()
        
        resource = Resource(
            resource_type="folder",
            resource_id=folder["id"],
            name=req.name,
            parent_id=parent_resource.id if parent_resource else None,
        )
        db.add(resource)
        await db.commit()
        
        return {
            "success": True,
            "folder": {
                "id": folder["id"],
                "name": folder["name"],
                "resource_id": str(resource.id),
            },
            "message": f"Folder '{req.name}' created",
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Folder creation failed: {str(e)}")

