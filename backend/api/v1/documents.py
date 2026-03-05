"""
Documents API Routes
File upload and Google Drive operations
"""

import os
import tempfile
import shutil
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends

from backend.config import settings
from backend.services.gdrive_service import GoogleDriveService
from backend.models.responses import FolderTreeResponse, UploadResponse
from backend.services.permission_service import get_current_user, get_current_user_optional
from backend.db.connection import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/documents", tags=["Documents"])


def _build_credentials_from_env():
    """
    Build Google OAuth credentials from GDRIVE_REFRESH_TOKEN in .env.
    This is the production-ready, zero-login method.
    
    Returns:
        Credentials object or None
    """
    if not settings.GDRIVE_REFRESH_TOKEN:
        return None
    
    if not settings.OAUTH_CLIENT_ID or not settings.OAUTH_CLIENT_SECRET:
        return None
    
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    
    credentials = Credentials(
        token=None,  # Will be refreshed automatically
        refresh_token=settings.GDRIVE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.OAUTH_CLIENT_ID,
        client_secret=settings.OAUTH_CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
    )
    
    # Refresh to get a valid access token
    try:
        credentials.refresh(Request())
        return credentials
    except Exception as e:
        print(f"⚠️ Failed to refresh Drive token from .env: {e}")
        return None


def get_gdrive_service():
    """
    Get Google Drive service for all operations.
    
    Priority:
      1. GDRIVE_REFRESH_TOKEN from .env (production-ready, zero-login)
      2. Service Account (read-only fallback for Shared Drives)
    """
    # Priority 1: Refresh token from .env
    credentials = _build_credentials_from_env()
    if credentials:
        return GoogleDriveService.from_oauth_credentials(credentials)
    
    # Priority 2: Service account fallback
    if settings.GDRIVE_SERVICE_ACCOUNT_FILE:
        service_file = settings.GDRIVE_SERVICE_ACCOUNT_FILE
        if os.path.exists(service_file):
            return GoogleDriveService.from_service_account(service_file)
    
    raise HTTPException(
        status_code=500,
        detail="Google Drive not configured. Set GDRIVE_REFRESH_TOKEN in .env (run: python scripts/generate_drive_token.py)"
    )


def get_gdrive_service_for_read():
    """
    Get Google Drive service for reading. Returns None instead of raising.
    """
    try:
        return get_gdrive_service()
    except:
        return None


@router.get("/folders")
async def list_folders(
    depth: int = 5,
    parent_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional),
):
    """
    List folder structure from Google Drive.
    
    Args:
        depth: Maximum folder depth to load (default 5 for comprehensive loading)
        parent_id: Optional parent folder ID - if provided, returns contents (files + folders) of that folder
    
    Returns a tree structure of folders for the upload destination selector.
    When parent_id is provided, returns items (files + folders) in that folder.
    """
    gdrive = get_gdrive_service_for_read()
    
    if not gdrive:
        raise HTTPException(
            status_code=503,
            detail="Google Drive not available. Please authenticate."
        )
    
    root_folder_id = settings.GDRIVE_ROOT_FOLDER_ID
    if not root_folder_id:
        raise HTTPException(
            status_code=500,
            detail="GDRIVE_ROOT_FOLDER_ID not configured"
        )
    
    try:
        # If parent_id is provided, return files and folders in that parent (lazy loading mode)
        if parent_id:
            items = gdrive.list_files(parent_id)  # Returns both files and folders
            
            # ─── Permission filter for lazy-loaded items ───
            if current_user and not any(r in ['admin', 'super_admin'] for r in current_user.get('roles', [])):
                from backend.db.models import Resource, Permission, PermissionType
                import uuid as uuid_mod
                
                user_uuid = current_user['id']
                if isinstance(user_uuid, str):
                    user_uuid = uuid_mod.UUID(user_uuid)
                
                pt_result = await db.execute(select(PermissionType).where(PermissionType.code == "view"))
                view_pt = pt_result.scalars().first()
                
                if view_pt:
                    perm_result = await db.execute(
                        select(Resource.resource_id)
                        .join(Permission, Permission.resource_id == Resource.id)
                        .where(
                            Permission.user_id == user_uuid,
                            Permission.permission_type_id == view_pt.id,
                            Permission.is_granted == True,
                            Resource.resource_type == "folder",
                        )
                    )
                    allowed_ids = set(row[0] for row in perm_result.all())
                    
                    # Check if parent_id is a descendant of any allowed folder
                    # Walk up the parent chain via Drive API
                    is_inside_allowed = parent_id in allowed_ids
                    if not is_inside_allowed:
                        check_id = parent_id
                        for _ in range(10):  # max tree depth
                            try:
                                info = gdrive.service.files().get(
                                    fileId=check_id, fields='parents',
                                    supportsAllDrives=True
                                ).execute()
                                parents = info.get('parents', [])
                                if not parents:
                                    break
                                check_id = parents[0]
                                if check_id in allowed_ids:
                                    is_inside_allowed = True
                                    break
                            except:
                                break
                    
                    # Only filter if parent is NOT inside an allowed folder tree
                    if not is_inside_allowed:
                        items = [item for item in items 
                                 if item.get('mimeType') != 'application/vnd.google-apps.folder' 
                                 or item.get('id') in allowed_ids]
            
            return {
                "parent_id": parent_id,
                "items": items,
                "folders": [item for item in items if item.get('mimeType') == 'application/vnd.google-apps.folder']
            }
        
        # Otherwise, build the full folder tree from root
        # OPTIMIZED: Single API call to get ALL folders, then build tree in-memory
        # Instead of N recursive API calls (1 per folder), we do 1 call total
        
        all_folders = []
        page_token = None
        
        while True:
            results = gdrive.service.files().list(
                q="mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="nextPageToken, files(id, name, parents)",
                pageSize=1000,
                orderBy="name",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()
            
            all_folders.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break
        
        # Build parent→children index
        children_map: Dict[str, list] = {}
        for folder in all_folders:
            for parent in folder.get("parents", []):
                children_map.setdefault(parent, []).append(folder)
        
        # Recursively build tree starting from root
        max_depth = min(depth, 10)
        
        def build_tree(folder_id: str, current_depth: int = 0) -> List[Dict[str, Any]]:
            if current_depth >= max_depth:
                return []
            kids = children_map.get(folder_id, [])
            result = []
            for f in sorted(kids, key=lambda x: x["name"]):
                children = build_tree(f["id"], current_depth + 1)
                result.append({
                    "id": f["id"],
                    "name": f["name"],
                    "children": children,
                    "hasChildren": len(children) > 0 or current_depth >= max_depth - 1,
                })
            return result
        
        folders = build_tree(root_folder_id)
        
        # ─── Permission filter: non-admin users only see allowed folders ───
        if current_user and not any(r in ['admin', 'super_admin'] for r in current_user.get('roles', [])):
            from backend.db.models import Resource, Permission, PermissionType
            import uuid as uuid_mod
            
            user_uuid = current_user['id']
            if isinstance(user_uuid, str):
                user_uuid = uuid_mod.UUID(user_uuid)
            
            # Get the 'view' permission type
            pt_result = await db.execute(select(PermissionType).where(PermissionType.code == "view"))
            view_pt = pt_result.scalars().first()
            
            if view_pt:
                # Get allowed Google Drive folder IDs for this user
                perm_result = await db.execute(
                    select(Resource.resource_id)
                    .join(Permission, Permission.resource_id == Resource.id)
                    .where(
                        Permission.user_id == user_uuid,
                        Permission.permission_type_id == view_pt.id,
                        Permission.is_granted == True,
                        Resource.resource_type == "folder",
                    )
                )
                allowed_ids = set(row[0] for row in perm_result.all())
                
                # Filter the tree — show only allowed folders and their descendants
                def filter_tree(nodes, parent_allowed=False):
                    filtered = []
                    for node in nodes:
                        is_allowed = node['id'] in allowed_ids or parent_allowed
                        if is_allowed:
                            # This folder (and all descendants) are allowed
                            filtered.append(node)  # Keep children as-is
                        else:
                            # Not directly allowed — check if any descendants are allowed
                            filtered_children = filter_tree(node.get('children', []), False)
                            if filtered_children:
                                node['children'] = filtered_children
                                node['hasChildren'] = len(filtered_children) > 0
                                filtered.append(node)
                    return filtered
                
                folders = filter_tree(folders)
            else:
                # No 'view' permission type exists → no permissions set → show nothing
                folders = []
        
        
        return {
            "root_id": root_folder_id,
            "folders": folders
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_files(q: str, max_results: int = 50):
    """
    Search for files and folders by name.
    
    Args:
        q: Search query string (min 2 chars)
        max_results: Maximum results (default 50)
    
    Only returns results within the Knowledge Management folder tree.
    """
    if not q or len(q.strip()) < 2:
        return {"results": [], "query": q, "total": 0}
    
    gdrive = get_gdrive_service_for_read()
    
    if not gdrive:
        raise HTTPException(
            status_code=503,
            detail="Google Drive not available. Please authenticate."
        )
    
    try:
        results = gdrive.search_files(q.strip(), max_results=max_results)
        
        folders = [r for r in results if r.get('mimeType') == 'application/vnd.google-apps.folder']
        files = [r for r in results if r.get('mimeType') != 'application/vnd.google-apps.folder']
        
        return {
            "query": q,
            "results": results,
            "folders": folders,
            "files": files,
            "total": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folders/{folder_id}/children")
async def get_folder_children(folder_id: str):
    """
    Get immediate children of a folder (lazy loading).
    
    Use this to load subfolders on-demand when user expands a folder.
    """
    gdrive = get_gdrive_service_for_read()
    
    if not gdrive:
        raise HTTPException(
            status_code=503,
            detail="Google Drive not available"
        )
    
    try:
        folders = gdrive.list_folders(folder_id)
        
        children = [
            {
                "id": folder['id'],
                "name": folder['name'],
                "hasChildren": True
            }
            for folder in folders
        ]
        
        return {
            "parent_id": folder_id,
            "children": children
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    folder_id: str = Form(...),
):
    """
    Upload file to Google Drive.
    
    Uses GDRIVE_REFRESH_TOKEN from .env for authentication.
    """
    tmp_path = None
    try:
        gdrive = get_gdrive_service()
        
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        # Upload to Google Drive with original filename
        result = gdrive.upload_file(
            tmp_path, 
            folder_id, 
            custom_name=file.filename
        )
        
        return UploadResponse(
            success=True,
            id=result.get('id'),
            name=result.get('name'),
            mimeType=result.get('mimeType'),
            webViewLink=result.get('webViewLink')
        )
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup temp file (safe for Windows)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.get("/files/{folder_id}")
async def list_files(folder_id: str):
    """
    List files in a folder.
    
    Returns all files and subfolders in the specified folder.
    """
    try:
        gdrive = get_gdrive_service_for_read()
        
        if not gdrive:
            raise HTTPException(
                status_code=503,
                detail="Google Drive not available"
            )
        
        files = gdrive.list_files(folder_id)
        
        return {
            "folder_id": folder_id,
            "files": files,
            "count": len(files)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Delete File/Folder (Admin Only - Direct Delete)
# =============================================================================

@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a file from Google Drive (admin only, direct delete).
    """
    # Check admin role
    user_roles = current_user.get("roles", [])
    if not any(r in ["admin", "super_admin"] for r in user_roles):
        raise HTTPException(status_code=403, detail="Only admins can delete files directly")
    
    try:
        gdrive = get_gdrive_service()
        
        # Get file info first for confirmation
        file_info = gdrive.service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, parents",
            supportsAllDrives=True
        ).execute()
        
        file_name = file_info.get("name", "Unknown")
        is_folder = file_info.get("mimeType") == "application/vnd.google-apps.folder"
        
        # Delete the file/folder
        gdrive.delete_file(file_id)
        
        return {
            "success": True,
            "message": f"{'Folder' if is_folder else 'File'} '{file_name}' deleted successfully",
            "file_id": file_id,
            "file_name": file_name,
            "was_folder": is_folder,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

