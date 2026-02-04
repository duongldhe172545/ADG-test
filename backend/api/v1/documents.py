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
async def list_folders():
    """
    List folder structure from Google Drive.
    
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
    
    try:
        def build_folder_tree(parent_id: str, depth: int = 0, max_depth: int = 5) -> List[Dict[str, Any]]:
            """Recursively build folder tree"""
            if depth >= max_depth:
                return []
            
            folders = gdrive.list_folders(parent_id)
            result = []
            
            for folder in folders:
                item = {
                    "id": folder['id'],
                    "name": folder['name'],
                    "children": build_folder_tree(folder['id'], depth + 1, max_depth)
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


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    folder_id: str = Form(...)
):
    """
    Upload file to Google Drive.
    
    Uses OAuth credentials to upload to user's Drive storage.
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
            
            return UploadResponse(
                success=True,
                id=result.get('id'),
                name=result.get('name'),
                mimeType=result.get('mimeType'),
                webViewLink=result.get('webViewLink')
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
