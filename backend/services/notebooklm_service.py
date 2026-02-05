"""
NotebookLM Service
Handles integration with NotebookLM API for chat and notebook operations
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Any

from notebooklm_mcp.api_client import NotebookLMClient
from notebooklm_mcp.auth import load_cached_tokens

from backend.config import settings
from backend.services.response_modifier import get_response_modifier


class NotebookLMService:
    """
    Service for NotebookLM API operations.
    
    Handles client creation, authentication, and notebook queries.
    """
    
    def __init__(self):
        self._client: Optional[NotebookLMClient] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._notebook_cache: Optional[List[Any]] = None
    
    def get_client(self) -> NotebookLMClient:
        """
        Get or create authenticated NotebookLM client.
        
        Returns:
            Authenticated NotebookLMClient
            
        Raises:
            Exception if not authenticated
        """
        if self._client is None:
            cached = load_cached_tokens()
            if not cached:
                raise Exception("Not authenticated. Please run 'notebooklm-mcp-auth' first.")
            
            self._client = NotebookLMClient(
                cookies=cached.cookies,
                csrf_token=cached.csrf_token,
                session_id=cached.session_id
            )
        
        return self._client
    
    def refresh_client(self) -> NotebookLMClient:
        """Force refresh the client with new tokens"""
        self._client = None
        self._notebook_cache = None
        return self.get_client()
    
    async def query_async(
        self,
        notebook_id: str,
        message: str,
        source_ids: Optional[List[str]] = None
    ) -> str:
        """
        Query a notebook asynchronously.
        
        Args:
            notebook_id: ID of the notebook to query
            message: User's question/message
            source_ids: Optional list of source IDs to limit context
            
        Returns:
            AI response text (properly extracted and formatted)
        """
        def sync_query():
            client = self.get_client()
            modifier = get_response_modifier()
            
            params = {
                "query_text": message,
                "notebook_id": notebook_id
            }
            if source_ids:
                params["source_ids"] = source_ids
            
            response = client.query(**params)
            
            # Use ResponseModifier to extract and format the answer
            return modifier.modify(response)
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(self._executor, sync_query)
        return response
    
    def list_notebooks(self) -> List[Any]:
        """
        List all available notebooks.
        
        Returns:
            List of notebook objects
        """
        client = self.get_client()
        
        if self._notebook_cache is None:
            self._notebook_cache = client.list_notebooks() or []
        
        return self._notebook_cache
    
    def get_sources(self, notebook_id: str) -> List[dict]:
        """
        Get sources/documents in a notebook.
        
        Args:
            notebook_id: ID of the notebook
            
        Returns:
            List of source objects with id, title, type
        """
        try:
            client = self.get_client()
            # Use correct API method
            sources = client.get_notebook_sources_with_types(notebook_id) or []
            
            # Transform to simple dict format
            result = []
            for source in sources:
                # Determine title
                title = "Untitled"
                if hasattr(source, 'title'): title = source.title
                elif hasattr(source, 'name'): title = source.name
                elif isinstance(source, dict):
                    title = source.get('title', source.get('name', 'Untitled'))
                
                # Determine type
                src_type = "unknown"
                if hasattr(source, 'source_type_name'): src_type = source.source_type_name
                elif hasattr(source, 'type'): src_type = source.type
                elif isinstance(source, dict):
                    src_type = source.get('source_type_name', source.get('type', source.get('source_type', 'unknown')))
                
                # Determine ID
                src_id = ""
                if hasattr(source, 'id'): src_id = source.id
                elif isinstance(source, dict): src_id = source.get('id', '')
                
                result.append({
                    'id': src_id,
                    'title': title,
                    'type': src_type
                })
                
                if title == "Untitled" or src_type == "unknown":
                    print(f"⚠️ Found Untitled/Unknown source: {source}")
                
            print(f"✅ Processed {len(result)} sources for notebook {notebook_id}")
            if len(result) > 0:
                print(f"🔍 Sample source: {result[0]}")
            return result
        except Exception as e:
            print(f"⚠️ Error getting sources: {e}")
            return []
    
    async def add_drive_source(
        self, 
        notebook_id: str, 
        document_id: str, 
        title: str,
        mime_type: str = 'application/pdf'
    ) -> dict:
        """
        Add a Google Drive file as a source to a notebook.
        
        Args:
            notebook_id: ID of the notebook to add source to
            document_id: Google Drive file ID
            title: Title/filename for the source
            mime_type: MIME type of the file
            
        Returns:
            Dict with source info or error
        """
        def sync_add():
            try:
                client = self.get_client()
                # Use add_drive_source method for Google Drive files
                result = client.add_drive_source(
                    notebook_id=notebook_id,
                    document_id=document_id,
                    title=title,
                    mime_type=mime_type
                )
                print(f"✅ Added Drive source to notebook {notebook_id}: {title}")
                return {"success": True, "source": result}
            except AttributeError as ae:
                # Method might not exist in client version
                print(f"⚠️ add_drive_source not available: {ae}")
                return {"success": False, "error": "Method not available"}
            except Exception as e:
                print(f"⚠️ Error adding source: {e}")
                return {"success": False, "error": str(e)}
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, sync_add)
        return result
    
    def is_authenticated(self) -> bool:
        """Check if NotebookLM is properly authenticated"""
        try:
            client = self.get_client()
            notebooks = client.list_notebooks()
            return notebooks is not None
        except Exception:
            return False
    
    def clear_cache(self):
        """Clear notebook cache"""
        self._notebook_cache = None


# Singleton instance
_notebooklm_service: Optional[NotebookLMService] = None


def get_notebooklm_service() -> NotebookLMService:
    """Get or create NotebookLM service singleton"""
    global _notebooklm_service
    if _notebooklm_service is None:
        _notebooklm_service = NotebookLMService()
    return _notebooklm_service

