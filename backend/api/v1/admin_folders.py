"""
Admin API - Folder Management & Permissions
Google Drive folder CRUD and RBAC folder permission management.
"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import (
    User, Role, UserRole, PermissionType, Resource, Permission,
    UserDepartment, Department,
)
from backend.api.v1.admin_users import require_admin, require_admin_or_manager, _ensure_view_permission_type
from backend.services.activity_service import log_activity

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Request Models
# =============================================================================

class CreateFolderRequest(BaseModel):
    name: str
    parent_folder_id: Optional[str] = None  # GDrive parent folder ID


class SetFolderPermissionsRequest(BaseModel):
    folder_ids: List[str]  # List of Google Drive folder IDs to grant view access


# =============================================================================
# Folder Management (Admin Only)
# =============================================================================

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
# Folder Permissions
# =============================================================================

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
    Returns EFFECTIVE folder IDs (permission table + department folder tree).
    """
    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    view_pt = await _ensure_view_permission_type(db)
    
    # Get user's explicit folder permissions from permissions table
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
    folder_ids = set(row[0] for row in perm_result.all())
    
    # Also include department folder + all child folders
    dept_result = await db.execute(
        select(Department.drive_folder_id)
        .join(UserDepartment, UserDepartment.department_id == Department.id)
        .where(UserDepartment.user_id == user.id)
    )
    dept_row = dept_result.first()
    if dept_row and dept_row[0]:
        dept_folder_id = dept_row[0]
        folder_ids.add(dept_folder_id)
        
        # Find the Resource record for dept folder, then get all children recursively
        dept_res = await db.execute(
            select(Resource).where(
                Resource.resource_type == "folder",
                Resource.resource_id == dept_folder_id,
            )
        )
        dept_resource = dept_res.scalars().first()
        if dept_resource:
            # Get ALL folder resources and walk the tree
            all_folders_result = await db.execute(
                select(Resource).where(Resource.resource_type == "folder")
            )
            all_folders = all_folders_result.scalars().all()
            
            # Build parent->children map using parent_id
            children_map = {}
            for f in all_folders:
                pid = f.parent_id
                if pid not in children_map:
                    children_map[pid] = []
                children_map[pid].append(f)
            
            # Walk tree from dept folder to collect all descendant IDs
            def collect_children(parent_id):
                for child in children_map.get(parent_id, []):
                    folder_ids.add(child.resource_id)
                    collect_children(child.id)
            
            collect_children(dept_resource.id)
    
    # Also return user's roles so frontend can detect admin
    role_result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    user_roles = [r[0] for r in role_result.all()]
    
    return {
        "user_id": str(user.id),
        "email": user.email,
        "folder_ids": list(folder_ids),
        "roles": user_roles,
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
    
    # Log folder permission change
    try:
        await log_activity(db, admin["id"], admin["email"], "folder.permission",
            target_type="user", target_id=str(user.id),
            details={"target_email": user.email, "folder_count": granted_count})
    except Exception:
        pass
    
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
