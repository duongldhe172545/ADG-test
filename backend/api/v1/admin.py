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
from backend.db.models import User, Role, UserRole, PermissionType, Resource, Permission
from backend.services.permission_service import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Request/Response Models
# =============================================================================

class AddUserRequest(BaseModel):
    email: str
    name: Optional[str] = None
    roles: List[str] = ["viewer"]  # Default role
    department_id: Optional[str] = None  # UUID of department

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[List[str]] = None
    department_id: Optional[str] = None  # UUID of department, or "" to clear

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

async def require_admin_or_manager(current_user: dict = Depends(get_current_user)):
    """Ensure current user is admin, super_admin, or manager"""
    if not any(r in ["admin", "super_admin", "manager"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Admin or Manager access required")
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
    
    from backend.db.models import UserDepartment, Department
    
    user_list = []
    for user in users:
        # Get roles
        role_result = await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
        roles = [r[0] for r in role_result.all()]
        
        # Get department
        dept_result = await db.execute(
            select(Department.id, Department.name).join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(UserDepartment.user_id == user.id)
        )
        dept_row = dept_result.first()
        
        user_list.append({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "roles": roles,
            "department": dept_row[1] if dept_row else None,
            "department_id": str(dept_row[0]) if dept_row else None,
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
    
    # Assign department if provided
    if req.department_id:
        from backend.db.models import UserDepartment, Department
        dept_result = await db.execute(select(Department).where(Department.id == req.department_id))
        dept = dept_result.scalars().first()
        if dept:
            ud = UserDepartment(user_id=user.id, department_id=dept.id)
            db.add(ud)
            # Auto-grant view permission to dept's drive folder
            if dept.drive_folder_id:
                await _ensure_view_permission_type(db)
                from backend.db.models import Resource, Permission, PermissionType
                pt_result = await db.execute(select(PermissionType).where(PermissionType.code == "view"))
                view_pt = pt_result.scalars().first()
                if view_pt:
                    res_result = await db.execute(
                        select(Resource).where(
                            Resource.resource_id == dept.drive_folder_id,
                            Resource.resource_type == "folder"
                        )
                    )
                    resource = res_result.scalars().first()
                    if resource:
                        perm = Permission(
                            user_id=user.id,
                            resource_id=resource.id,
                            permission_type_id=view_pt.id,
                            is_granted=True
                        )
                        db.add(perm)
    
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
    
    # Update department if provided (with auto folder permissions)
    if req.department_id is not None:
        from backend.db.models import UserDepartment, Department
        
        # Get OLD department's drive_folder_id (to remove permission)
        old_dept_result = await db.execute(
            select(Department).join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(UserDepartment.user_id == user.id)
        )
        old_dept = old_dept_result.scalars().first()
        
        # Remove old dept folder permission if exists
        if old_dept and old_dept.drive_folder_id:
            old_resource = await db.execute(
                select(Resource).where(
                    Resource.resource_type == "folder",
                    Resource.resource_id == old_dept.drive_folder_id,
                )
            )
            old_res = old_resource.scalars().first()
            if old_res:
                view_pt = await _ensure_view_permission_type(db)
                await db.execute(
                    delete(Permission).where(
                        Permission.user_id == user.id,
                        Permission.resource_id == old_res.id,
                        Permission.permission_type_id == view_pt.id,
                    )
                )
        
        # Remove existing department assignments
        await db.execute(delete(UserDepartment).where(UserDepartment.user_id == user.id))
        
        # Assign new department (if not empty)
        if req.department_id:
            dept_result = await db.execute(select(Department).where(Department.id == req.department_id))
            dept = dept_result.scalars().first()
            if dept:
                ud = UserDepartment(user_id=user.id, department_id=dept.id)
                db.add(ud)
                
                # Auto-add new dept folder permission
                if dept.drive_folder_id:
                    new_resource = await db.execute(
                        select(Resource).where(
                            Resource.resource_type == "folder",
                            Resource.resource_id == dept.drive_folder_id,
                        )
                    )
                    new_res = new_resource.scalars().first()
                    if new_res:
                        view_pt = await _ensure_view_permission_type(db)
                        # Check if permission already exists
                        existing_perm = await db.execute(
                            select(Permission).where(
                                Permission.user_id == user.id,
                                Permission.resource_id == new_res.id,
                                Permission.permission_type_id == view_pt.id,
                            )
                        )
                        if not existing_perm.scalars().first():
                            perm = Permission(
                                user_id=user.id,
                                resource_id=new_res.id,
                                permission_type_id=view_pt.id,
                                is_granted=True,
                            )
                            db.add(perm)
    
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
# Departments
# =============================================================================

@router.get("/departments")
async def list_departments(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """List all departments"""
    from backend.db.models import Department
    result = await db.execute(select(Department).order_by(Department.name))
    depts = result.scalars().all()
    return {
        "departments": [
            {"id": str(d.id), "name": d.name, "parent_id": str(d.parent_id) if d.parent_id else None}
            for d in depts
        ]
    }


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
    admin: dict = Depends(require_admin_or_manager),
):
    """
    Create a new folder on Google Drive (admin only).
    Also registers as a resource in the RBAC system.
    """
    from backend.api.v1.documents import get_gdrive_service
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


# =============================================================================
# Folder Permissions (Admin Only)
# =============================================================================

class SetFolderPermissionsRequest(BaseModel):
    folder_ids: List[str]  # List of Google Drive folder IDs to grant view access


async def _ensure_view_permission_type(db: AsyncSession):
    """Get or create the 'view' permission type."""
    result = await db.execute(select(PermissionType).where(PermissionType.code == "view"))
    pt = result.scalars().first()
    if not pt:
        pt = PermissionType(code="view", name="View", description="View folder contents")
        db.add(pt)
        await db.flush()
    return pt


@router.get("/permissions/folders")
async def list_folder_permissions(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    List all registered folders and which users have view permission.
    Returns a matrix: {folders: [...], users_permissions: {user_id: [folder_resource_ids]}}
    """
    # Get all folder resources
    folder_result = await db.execute(
        select(Resource)
        .where(Resource.resource_type == "folder")
        .order_by(Resource.name)
    )
    folders = folder_result.scalars().all()
    
    # Get view permission type
    view_pt = await _ensure_view_permission_type(db)
    
    # Get all folder view permissions
    perm_result = await db.execute(
        select(Permission)
        .where(
            Permission.permission_type_id == view_pt.id,
            Permission.is_granted == True,
        )
    )
    perms = perm_result.scalars().all()
    
    # Build user → folder mapping
    users_permissions = {}
    for p in perms:
        uid = str(p.user_id)
        if uid not in users_permissions:
            users_permissions[uid] = []
        users_permissions[uid].append(str(p.resource_id))
    
    return {
        "folders": [
            {
                "id": str(f.id),
                "resource_id": f.resource_id,  # Google Drive ID
                "name": f.name,
                "parent_id": str(f.parent_id) if f.parent_id else None,
            }
            for f in folders
        ],
        "users_permissions": users_permissions,
    }


@router.get("/permissions/folders/{user_id}")
async def get_user_folder_permissions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Get which folders a specific user has view access to.
    Returns list of Google Drive folder IDs.
    """
    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    view_pt = await _ensure_view_permission_type(db)
    
    # Get user's folder permissions
    perm_result = await db.execute(
        select(Resource.resource_id)
        .join(Permission, Permission.resource_id == Resource.id)
        .where(
            Permission.user_id == user.id,
            Permission.permission_type_id == view_pt.id,
            Permission.is_granted == True,
            Resource.resource_type == "folder",
        )
    )
    folder_ids = [row[0] for row in perm_result.all()]
    
    return {
        "user_id": str(user.id),
        "email": user.email,
        "folder_ids": folder_ids,  # Google Drive folder IDs
    }


@router.put("/permissions/folders/{user_id}")
async def set_user_folder_permissions(
    user_id: str,
    req: SetFolderPermissionsRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Set which folders a user can view. Replaces all existing folder view permissions.
    Body: {folder_ids: ["gdrive_folder_id_1", "gdrive_folder_id_2"]}
    """
    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    view_pt = await _ensure_view_permission_type(db)
    
    # Get all folder resource IDs for cleanup
    folder_resource_result = await db.execute(
        select(Resource.id).where(Resource.resource_type == "folder")
    )
    folder_resource_ids = [row[0] for row in folder_resource_result.all()]
    
    # Delete existing folder view permissions for this user
    if folder_resource_ids:
        await db.execute(
            delete(Permission).where(
                Permission.user_id == user.id,
                Permission.permission_type_id == view_pt.id,
                Permission.resource_id.in_(folder_resource_ids),
            )
        )
    
    # Add new permissions
    granted_count = 0
    for gdrive_folder_id in req.folder_ids:
        # Find the resource by Google Drive ID
        res_result = await db.execute(
            select(Resource).where(
                Resource.resource_type == "folder",
                Resource.resource_id == gdrive_folder_id,
            )
        )
        resource = res_result.scalars().first()
        if resource:
            perm = Permission(
                user_id=user.id,
                resource_id=resource.id,
                permission_type_id=view_pt.id,
                is_granted=True,
            )
            db.add(perm)
            granted_count += 1
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Granted view access to {granted_count} folders for {user.email}",
        "granted_count": granted_count,
    }


@router.post("/permissions/sync-folders")
async def sync_drive_folders_to_resources(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Sync Google Drive folder structure into the resources table.
    Creates Resource entries for any folders not yet registered.
    """
    from backend.api.v1.documents import get_gdrive_service
    from backend.config import settings
    
    root_id = settings.GDRIVE_ROOT_FOLDER_ID
    if not root_id:
        raise HTTPException(status_code=500, detail="GDRIVE_ROOT_FOLDER_ID not configured")
    
    try:
        gdrive = get_gdrive_service()
        synced = 0
        skipped = 0
        
        # Recursive function to sync folders
        async def sync_folder(parent_drive_id: str, parent_resource_id=None):
            nonlocal synced, skipped
            
            query = f"'{parent_drive_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = gdrive.service.files().list(
                q=query,
                fields="files(id, name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=100,
            ).execute()
            
            folders = results.get("files", [])
            
            for folder in folders:
                # Skip _OLD and _PENDING folders
                if folder["name"].startswith("_"):
                    continue
                
                # Check if already registered
                existing = await db.execute(
                    select(Resource).where(
                        Resource.resource_type == "folder",
                        Resource.resource_id == folder["id"],
                    )
                )
                resource = existing.scalars().first()
                
                if resource:
                    # Update name if changed
                    if resource.name != folder["name"]:
                        resource.name = folder["name"]
                    skipped += 1
                else:
                    resource = Resource(
                        resource_type="folder",
                        resource_id=folder["id"],
                        name=folder["name"],
                        parent_id=parent_resource_id,
                    )
                    db.add(resource)
                    await db.flush()
                    synced += 1
                
                # Recurse into children
                await sync_folder(folder["id"], resource.id)
        
        # Ensure root folder is registered
        root_result = await db.execute(
            select(Resource).where(
                Resource.resource_type == "folder",
                Resource.resource_id == root_id,
            )
        )
        root_resource = root_result.scalars().first()
        if not root_resource:
            root_resource = Resource(
                resource_type="folder",
                resource_id=root_id,
                name="ADG_Marketing (Root)",
            )
            db.add(root_resource)
            await db.flush()
            synced += 1
        
        await sync_folder(root_id, root_resource.id)
        await db.commit()
        
        return {
            "success": True,
            "message": f"Sync complete: {synced} new, {skipped} existing",
            "synced": synced,
            "skipped": skipped,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
