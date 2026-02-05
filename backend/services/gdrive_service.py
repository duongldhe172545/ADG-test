"""
Google Drive Service
Handles all Google Drive API operations for the KMS
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Google Drive MIME types
MIME_FOLDER = 'application/vnd.google-apps.folder'


class GoogleDriveService:
    """
    Service for Google Drive API operations.
    
    Supports both OAuth credentials (user-based) and Service Account credentials.
    OAuth is preferred for user operations to use their quota.
    """
    
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    def __init__(
        self, 
        service_account_file: Optional[str] = None, 
        credentials: Optional[Credentials] = None
    ):
        """
        Initialize Google Drive service.
        
        Args:
            service_account_file: Path to service account JSON key file (optional)
            credentials: OAuth2 credentials object (optional)
        """
        self.service_account_file = service_account_file
        self._credentials = credentials
        self._service = None
    
    @classmethod
    def from_oauth_credentials(cls, credentials: Credentials) -> 'GoogleDriveService':
        """
        Create GoogleDriveService from OAuth2 credentials.
        
        Args:
            credentials: google.oauth2.credentials.Credentials object
            
        Returns:
            GoogleDriveService instance using OAuth credentials
        """
        return cls(credentials=credentials)
    
    @classmethod
    def from_service_account(cls, file_path: str) -> 'GoogleDriveService':
        """
        Create GoogleDriveService from service account file.
        
        Args:
            file_path: Path to service account JSON file
            
        Returns:
            GoogleDriveService instance using service account
        """
        return cls(service_account_file=file_path)
    
    @property
    def service(self):
        """Get or create Drive service"""
        if self._service is None:
            if self._credentials:
                # Use OAuth credentials
                self._service = build('drive', 'v3', credentials=self._credentials)
            elif self.service_account_file:
                # Fall back to service account
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file, 
                    scopes=self.SCOPES
                )
                self._service = build('drive', 'v3', credentials=creds)
            else:
                raise ValueError("No credentials provided. Use OAuth or service account.")
        return self._service
    
    # ==========================================================================
    # Folder Operations
    # ==========================================================================
    
    def create_folder(
        self, 
        name: str, 
        parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a folder in Google Drive.
        
        Args:
            name: Folder name
            parent_id: Parent folder ID (optional)
            
        Returns:
            Dict with folder info {'id': 'xxx', 'name': '...', 'webViewLink': '...'}
        """
        file_metadata = {
            'name': name,
            'mimeType': MIME_FOLDER
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        folder = self.service.files().create(
            body=file_metadata,
            fields='id, name, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        print(f"✅ Created folder: {name} (ID: {folder.get('id')})")
        return folder
    
    def list_folders(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        List folders in a parent folder.
        
        Args:
            parent_id: Parent folder ID
            
        Returns:
            List of folder dicts
        """
        results = self.service.files().list(
            q=f"'{parent_id}' in parents and mimeType='{MIME_FOLDER}' and trashed=false",
            fields="files(id, name, mimeType)",
            orderBy="name",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        return results.get('files', [])
    
    def list_files(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        List all files and folders in a parent folder.
        
        Args:
            parent_id: Parent folder ID
            
        Returns:
            List of file/folder dicts
        """
        results = self.service.files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            fields="files(id, name, mimeType, size, modifiedTime)",
            orderBy="name",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        return results.get('files', [])
    
    # ==========================================================================
    # File Operations
    # ==========================================================================
    
    def upload_file(
        self, 
        file_path: str, 
        parent_id: Optional[str] = None,
        mime_type: Optional[str] = None, 
        custom_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Local file path
            parent_id: Parent folder ID (optional)
            mime_type: File MIME type (auto-detected if not provided)
            custom_name: Custom filename (uses file_path name if not provided)
            
        Returns:
            Dict with file info {'id': 'xxx', 'name': '...', 'webViewLink': '...'}
        """
        file_name = custom_name or Path(file_path).name
        
        file_metadata = {'name': file_name}
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink, mimeType',
            supportsAllDrives=True
        ).execute()
        
        print(f"✅ Uploaded file: {file_name} (ID: {file.get('id')})")
        return file
    
    def share_file_public(self, file_id: str) -> bool:
        """
        Share a file publicly with "Anyone with the link can view" permission.
        
        This is required for NotebookLM to access files from Google Drive.
        
        Args:
            file_id: ID of the file to share
            
        Returns:
            True if successful, False otherwise
        """
        try:
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            self.service.permissions().create(
                fileId=file_id,
                body=permission,
                supportsAllDrives=True
            ).execute()
            print(f"🔓 Shared file publicly: {file_id}")
            return True
        except Exception as e:
            print(f"⚠️ Failed to share file: {e}")
            return False
    
    def delete_file(self, file_id: str) -> None:
        """Delete a file or folder by ID"""
        self.service.files().delete(
            fileId=file_id,
            supportsAllDrives=True
        ).execute()
        print(f"🗑️ Deleted file: {file_id}")
    
    def move_file(
        self, 
        file_id: str, 
        new_parent_id: str, 
        old_parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Move a file to a different folder.
        
        Args:
            file_id: ID of file to move
            new_parent_id: ID of destination folder
            old_parent_id: ID of current parent (optional, will be fetched if not provided)
            
        Returns:
            Updated file metadata
        """
        if not old_parent_id:
            # Get current parents
            file = self.service.files().get(
                fileId=file_id,
                fields='parents',
                supportsAllDrives=True
            ).execute()
            old_parent_id = file.get('parents', [None])[0]
        
        file = self.service.files().update(
            fileId=file_id,
            addParents=new_parent_id,
            removeParents=old_parent_id,
            fields='id, name, parents',
            supportsAllDrives=True
        ).execute()
        
        print(f"📁 Moved file {file_id} to {new_parent_id}")
        return file
    
    # ==========================================================================
    # Folder Structure Operations
    # ==========================================================================
    
    def create_folder_structure(
        self, 
        structure: Dict[str, Any], 
        parent_id: str
    ) -> Dict[str, str]:
        """
        Create nested folder structure.
        
        Args:
            structure: Dict with folder structure, e.g.
                       {'Folder1': {'Sub1': {}, 'Sub2': {}}, 'Folder2': {}}
            parent_id: Root parent folder ID
            
        Returns:
            Dict mapping folder paths to IDs
        """
        folder_ids = {}
        
        def create_recursive(struct: Dict, parent: str, path: str = ""):
            for name, children in struct.items():
                current_path = f"{path}/{name}" if path else name
                folder = self.create_folder(name, parent)
                folder_ids[current_path] = folder['id']
                
                if children:
                    create_recursive(children, folder['id'], current_path)
        
        create_recursive(structure, parent_id)
        return folder_ids
