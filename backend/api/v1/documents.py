"""
Documents API Routes
File upload and Google Drive operations
"""

import os
import tempfile
import shutil
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from backend.config import settings
from backend.core.auth.oauth import get_oauth_service
from backend.services.gdrive_service import GoogleDriveService
from backend.models.responses import FolderTreeResponse, UploadResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


def get_gdrive_service():
    """
    Get Google Drive service using OAuth credentials.
    
    Raises:
        HTTPException if not authenticated
    """
    oauth_service = get_oauth_service()
    credentials = oauth_service.get_valid_credentials()
    
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login with Google first."
        )
    
    return GoogleDriveService.from_oauth_credentials(credentials)


def get_gdrive_service_for_read():
    """
    Get Google Drive service for reading (OAuth preferred, fallback to service account).
    
    Returns:
        GoogleDriveService or None
    """
    oauth_service = get_oauth_service()
    credentials = oauth_service.get_valid_credentials()
    
    if credentials:
        return GoogleDriveService.from_oauth_credentials(credentials)
    
    # Fallback to service account for reading
    if settings.GDRIVE_SERVICE_ACCOUNT_FILE:
        service_file = settings.GDRIVE_SERVICE_ACCOUNT_FILE
        if os.path.exists(service_file):
            return GoogleDriveService.from_service_account(service_file)
    
    return None


@router.get("/folders")
async def list_folders(depth: int = 5):
    """
    List folder structure from Google Drive.
    
    Args:
        depth: Maximum folder depth to load (default 5 for comprehensive loading)
    
    Returns a tree structure of folders for the upload destination selector.
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
    
    # Allow deeper nesting for full folder tree
    max_depth = min(depth, 10)
    
    try:
        def build_folder_tree(parent_id: str, current_depth: int = 0) -> List[Dict[str, Any]]:
            """Recursively build folder tree with limited depth"""
            if current_depth >= max_depth:
                return []
            
            folders = gdrive.list_folders(parent_id)
            result = []
            
            for folder in folders:
                # Always try to load children if we haven't reached max depth
                children = build_folder_tree(folder['id'], current_depth + 1)
                item = {
                    "id": folder['id'],
                    "name": folder['name'],
                    "children": children,
                    "hasChildren": len(children) > 0 or current_depth >= max_depth - 1
                }
                result.append(item)
            
            return result
        
        folders = build_folder_tree(root_folder_id)
        
        return {
            "root_id": root_folder_id,
            "folders": folders
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
    notebook_ids: str = Form(None)  # Comma-separated notebook IDs
):
    """
    Upload file to Google Drive and sync to NotebookLM.
    
    Uses OAuth credentials to upload to user's Drive storage.
    Syncs to notebooks via:
    1. Manual selection (notebook_ids parameter)
    2. Auto-mapping (FOLDER_NOTEBOOK_MAPPING)
    """
    try:
        gdrive = get_gdrive_service()
        
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        try:
            # Upload to Google Drive with original filename
            result = gdrive.upload_file(
                tmp_path, 
                folder_id, 
                custom_name=file.filename
            )
            
            web_view_link = result.get('webViewLink')
            file_name = result.get('name')
            file_id = result.get('id')
            
            # Share file publicly so NotebookLM can access it
            if file_id:
                gdrive.share_file_public(file_id)
            
            # Auto-sync to NotebookLM if folder is mapped
            notebook_sync_result = None
            synced_notebooks = set()  # Track synced notebooks to avoid duplicates
            try:
                from backend.config.folder_notebook_mapping import FOLDER_NOTEBOOK_MAPPING
                from backend.services.notebooklm_service import get_notebooklm_service
                
                print(f"🔍 Checking sync for folder_id: {folder_id}")
                print(f"📋 Available mappings: {list(FOLDER_NOTEBOOK_MAPPING.keys())[:5]}...")
                
                # Check if this folder is mapped
                notebook_id = FOLDER_NOTEBOOK_MAPPING.get(folder_id)
                
                # If not directly mapped, try to find parent folder in mapping
                if not notebook_id:
                    print(f"⚠️ Folder {folder_id} not in mapping, checking parents...")
                    try:
                        # Get file info to find parent folders
                        file_info = gdrive.service.files().get(
                            fileId=folder_id,
                            fields='parents'
                        ).execute()
                        
                        parents = file_info.get('parents', [])
                        for parent_id in parents:
                            print(f"🔍 Checking parent: {parent_id}")
                            notebook_id = FOLDER_NOTEBOOK_MAPPING.get(parent_id)
                            if notebook_id:
                                print(f"✅ Found parent mapping: {parent_id} -> {notebook_id}")
                                break
                            
                            # Also check grandparent (2 levels deep)
                            try:
                                grandparent_info = gdrive.service.files().get(
                                    fileId=parent_id,
                                    fields='parents'
                                ).execute()
                                for gp_id in grandparent_info.get('parents', []):
                                    notebook_id = FOLDER_NOTEBOOK_MAPPING.get(gp_id)
                                    if notebook_id:
                                        print(f"✅ Found grandparent mapping: {gp_id} -> {notebook_id}")
                                        break
                                if notebook_id:
                                    break
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"⚠️ Could not get parent folders: {e}")
                
                if notebook_id and file_id:
                    print(f"🚀 Syncing to notebook: {notebook_id}")
                    notebooklm = get_notebooklm_service()
                    notebook_sync_result = await notebooklm.add_drive_source(
                        notebook_id=notebook_id,
                        document_id=file_id,
                        title=file_name,
                        mime_type=result.get('mimeType', 'application/pdf')
                    )
                    synced_notebooks.add(notebook_id)  # Track synced notebook
                    print(f"📚 NotebookLM sync: {notebook_sync_result}")
                else:
                    print(f"⏭️ No mapping found for folder {folder_id}, skipping auto-sync")
            except ImportError as ie:
                print(f"⚠️ Folder mapping not configured: {ie}")
            except Exception as sync_error:
                print(f"⚠️ NotebookLM sync error (non-blocking): {sync_error}")
            
            # Manual notebook sync (from selected checkboxes)
            if notebook_ids and web_view_link:
                try:
                    from backend.services.notebooklm_service import get_notebooklm_service
                    notebooklm = get_notebooklm_service()
                    
                    selected_notebooks = [nb.strip() for nb in notebook_ids.split(',') if nb.strip()]
                    # Filter out already-synced notebooks
                    new_notebooks = [nb for nb in selected_notebooks if nb not in synced_notebooks]
                    
                    if len(selected_notebooks) != len(new_notebooks):
                        skipped = set(selected_notebooks) - set(new_notebooks)
                        print(f"⏭️ Skipping already-synced notebooks: {skipped}")
                    
                    print(f"📝 Manual sync to notebooks: {new_notebooks}")
                    
                    for nb_id in new_notebooks:
                        try:
                            sync_result = await notebooklm.add_drive_source(
                                notebook_id=nb_id,
                                document_id=file_id,
                                title=file_name,
                                mime_type=result.get('mimeType', 'application/pdf')
                            )
                            synced_notebooks.add(nb_id)
                            print(f"✅ Synced to notebook {nb_id}: {sync_result}")
                        except Exception as nb_err:
                            print(f"⚠️ Failed to sync to notebook {nb_id}: {nb_err}")
                except Exception as manual_sync_error:
                    print(f"⚠️ Manual sync error (non-blocking): {manual_sync_error}")
            
            return UploadResponse(
                success=True,
                id=result.get('id'),
                name=file_name,
                mimeType=result.get('mimeType'),
                webViewLink=web_view_link
            )
        finally:
            # Cleanup temp file
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
