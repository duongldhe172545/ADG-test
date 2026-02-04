"""
Google Drive API Client for KMS (Knowledge Management System)
Handles folder creation and file uploads to Google Drive
"""

import os
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

# Google Drive MIME types
MIME_FOLDER = 'application/vnd.google-apps.folder'


class GoogleDriveClient:
    """Client for Google Drive API operations"""
    
    SCOPES = ['https://www.googleapis.com/auth/drive']  # Full access for shared folders
    
    def __init__(self, service_account_file: str = None, credentials=None):
        """
        Initialize Google Drive client.
        
        Args:
            service_account_file: Path to service account JSON key file (optional)
            credentials: OAuth2 credentials object (optional)
        """
        self.service_account_file = service_account_file
        self._credentials = credentials
        self._service = None
    
    @classmethod
    def from_oauth_credentials(cls, credentials):
        """
        Create GoogleDriveClient from OAuth2 credentials.
        
        Args:
            credentials: google.oauth2.credentials.Credentials object
            
        Returns:
            GoogleDriveClient instance using OAuth credentials
        """
        client = cls()
        client._credentials = credentials
        return client
    
    @property
    def service(self):
        """Get or create Drive service"""
        if self._service is None:
            if self._credentials:
                # Use OAuth credentials
                self._service = build('drive', 'v3', credentials=self._credentials)
            elif self.service_account_file:
                # Use Service Account
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file, 
                    scopes=self.SCOPES
                )
                self._service = build('drive', 'v3', credentials=creds)
            else:
                raise ValueError("No credentials provided")
        return self._service
    
    def create_folder(self, name: str, parent_id: Optional[str] = None) -> dict:
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
    
    def upload_file(self, file_path: str, parent_id: Optional[str] = None, 
                    mime_type: Optional[str] = None, custom_name: Optional[str] = None) -> dict:
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Local file path
            parent_id: Parent folder ID (optional)
            mime_type: File MIME type (auto-detected if not provided)
            custom_name: Custom filename to use (uses file_path name if not provided)
            
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
    
    def list_folders(self, parent_id: str) -> list:
        """
        List folders in a parent folder.
        
        Args:
            parent_id: Parent folder ID
            
        Returns:
            List of folder dicts
        """
        query = f"'{parent_id}' in parents and mimeType='{MIME_FOLDER}' and trashed=false"
        
        results = self.service.files().list(
            q=query,
            fields='files(id, name, webViewLink)',
            orderBy='name',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        return results.get('files', [])
    
    def list_files(self, parent_id: str) -> list:
        """
        List all files and folders in a parent folder.
        
        Args:
            parent_id: Parent folder ID
            
        Returns:
            List of file/folder dicts
        """
        query = f"'{parent_id}' in parents and trashed=false"
        
        results = self.service.files().list(
            q=query,
            fields='files(id, name, mimeType, webViewLink)',
            orderBy='name',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        return results.get('files', [])
    
    def delete_file(self, file_id: str):
        """Delete a file or folder by ID"""
        self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        print(f"🗑️ Deleted: {file_id}")
    
    def create_folder_structure(self, structure: dict, parent_id: str) -> dict:
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
        
        def create_recursive(struct: dict, parent: str, path: str = ""):
            for name, children in struct.items():
                current_path = f"{path}/{name}" if path else name
                folder = self.create_folder(name, parent)
                folder_ids[current_path] = folder['id']
                
                if children:
                    create_recursive(children, folder['id'], current_path)
        
        create_recursive(structure, parent_id)
        return folder_ids


# =============================================================================
# Test script
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Find service account JSON file
    base_dir = Path(__file__).parent
    json_files = list(base_dir.glob("*.json"))
    
    service_account_file = None
    for f in json_files:
        if f.name.startswith("test-adg") or "service" in f.name.lower():
            service_account_file = str(f)
            break
    
    if not service_account_file:
        print("❌ No service account JSON file found!")
        print(f"   Expected in: {base_dir}")
        sys.exit(1)
    
    print(f"📁 Using service account: {service_account_file}")
    
    # Initialize client
    client = GoogleDriveClient(service_account_file)
    
    # Test: List shared folder contents
    # You need to replace this with your actual folder ID
    NOTEBOOKLM_SOURCES_FOLDER_ID = input("🔑 Enter NotebookLM-Sources folder ID: ").strip()
    
    if not NOTEBOOKLM_SOURCES_FOLDER_ID:
        print("❌ Folder ID is required!")
        print("   Get it from the URL: https://drive.google.com/drive/folders/XXXX")
        print("   The XXXX part is the folder ID")
        sys.exit(1)
    
    print("\n📂 Listing current contents...")
    files = client.list_files(NOTEBOOKLM_SOURCES_FOLDER_ID)
    if files:
        print(f"   Found {len(files)} items:")
        for f in files:
            icon = "📁" if f['mimeType'] == MIME_FOLDER else "📄"
            print(f"   {icon} {f['name']}")
    else:
        print("   (empty folder)")
    
    # Test: Create a test folder
    print("\n📝 Creating test folder...")
    test_folder = client.create_folder("_TEST_API_FOLDER", NOTEBOOKLM_SOURCES_FOLDER_ID)
    print(f"   View: {test_folder.get('webViewLink')}")
    
    # Cleanup
    cleanup = input("\n🗑️ Delete test folder? (y/N): ").strip().lower()
    if cleanup == 'y':
        client.delete_file(test_folder['id'])
        print("   Cleaned up!")
    
    print("\n✅ Google Drive API test completed successfully!")
