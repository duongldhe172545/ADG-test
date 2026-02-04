"""
NotebookLM Service
Handles integration with NotebookLM API for chat and notebook operations
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Any

from notebooklm_mcp.api_client import NotebookLMClient
from notebooklm_mcp.auth import load_cached_tokens


class NotebookLMService:
    """
    Service for NotebookLM API operations.
    
    Handles client creation, authentication, and notebook queries.
    """
    
    def __init__(self):
        self._client: Optional[NotebookLMClient] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
    
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
            AI response text
        """
        def sync_query():
            client = self.get_client()
            
            params = {
                "query": message,
                "notebook_id": notebook_id
            }
            if source_ids:
                params["source_ids"] = source_ids
            
            response = client.ask(**params)
            
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'answer'):
                return response.answer
            elif isinstance(response, str):
                return response
            else:
                return str(response)
        
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
        return client.list_notebooks() or []
    
    def get_sources(self, notebook_id: str) -> List[Any]:
        """
        Get sources/documents in a notebook.
        
        Args:
            notebook_id: ID of the notebook
            
        Returns:
            List of source objects
        """
        client = self.get_client()
        return client.list_sources(notebook_id) or []
    
    def is_authenticated(self) -> bool:
        """Check if NotebookLM is properly authenticated"""
        try:
            client = self.get_client()
            notebooks = client.list_notebooks()
            return notebooks is not None
        except Exception:
            return False


# Singleton instance
_notebooklm_service: Optional[NotebookLMService] = None


def get_notebooklm_service() -> NotebookLMService:
    """Get or create NotebookLM service singleton"""
    global _notebooklm_service
    if _notebooklm_service is None:
        _notebooklm_service = NotebookLMService()
    return _notebooklm_service
