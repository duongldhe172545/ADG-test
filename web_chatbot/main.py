"""
NotebookLM Web Chatbot - FastAPI Server
Real-time SSE streaming with auto re-auth support
"""

import os
import json
import asyncio
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Local imports
from scheduler import start_scheduler, AuthHealthChecker
from response_modifier import ResponseModifier

# Load environment variables
load_dotenv()

# NotebookLM SDK imports
from notebooklm_mcp.api_client import NotebookLMClient, extract_cookies_from_chrome_export
from notebooklm_mcp.auth import load_cached_tokens

# Configuration
NOTEBOOK_ID = os.getenv("NOTEBOOK_ID", "")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")

app = FastAPI(
    title="NotebookLM Web Chatbot",
    description="Real-time chat interface for NotebookLM Ultra",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Response modifier instance
response_modifier = ResponseModifier()

# Auth health checker
auth_checker = AuthHealthChecker()


class ChatRequest(BaseModel):
    message: str
    notebook_id: Optional[str] = None
    source_ids: Optional[list] = None  # Filter by specific sources


class ChatResponse(BaseModel):
    response: str
    sources: list = []
    timestamp: str


def get_notebooklm_client() -> Optional[NotebookLMClient]:
    """Get authenticated NotebookLM client"""
    cookie_header = os.environ.get("NOTEBOOKLM_COOKIES", "")
    csrf_token = os.environ.get("NOTEBOOKLM_CSRF_TOKEN", "")
    session_id = os.environ.get("NOTEBOOKLM_SESSION_ID", "")

    if cookie_header:
        cookies = extract_cookies_from_chrome_export(cookie_header)
    else:
        cached = load_cached_tokens()
        if cached:
            cookies = cached.cookies
            csrf_token = csrf_token or cached.csrf_token
            session_id = session_id or cached.session_id
        else:
            return None

    return NotebookLMClient(cookies=cookies, csrf_token=csrf_token, session_id=session_id)


async def query_notebook_async(client: NotebookLMClient, notebook_id: str, message: str, source_ids: list = None) -> dict:
    """Query NotebookLM notebook asynchronously"""
    loop = asyncio.get_event_loop()
    
    def sync_query():
        try:
            # Use the client's query method with correct parameter name
            query_kwargs = {'notebook_id': notebook_id, 'query_text': message}
            if source_ids:
                query_kwargs['source_ids'] = source_ids
            response = client.query(**query_kwargs)
            
            # Parse response - API returns dict with 'answer' key
            if isinstance(response, dict):
                answer_text = response.get('answer', str(response))
                # Sources might be in response or empty
                sources = response.get('sources', [])
            elif hasattr(response, 'text'):
                answer_text = response.text
                sources = response.sources if hasattr(response, 'sources') else []
            else:
                answer_text = str(response)
                sources = []
            
            return {
                "success": True,
                "response": answer_text,
                "sources": sources
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    result = await loop.run_in_executor(None, sync_query)
    return result


@app.on_event("startup")
async def startup_event():
    """Start background scheduler on app startup"""
    start_scheduler()
    print("🚀 NotebookLM Web Chatbot started")
    print(f"📓 Default Notebook ID: {NOTEBOOK_ID or 'Not set - will need to provide in request'}")


@app.get("/")
async def root():
    """Serve the chat UI"""
    return FileResponse("static/index.html")


@app.get("/api/health")
async def health_check():
    """Check authentication and server health"""
    client = get_notebooklm_client()
    auth_valid = client is not None
    
    return {
        "status": "ok" if auth_valid else "auth_required",
        "auth_valid": auth_valid,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/sources/{notebook_id}")
async def get_sources(notebook_id: str):
    """Get sources/documents in a notebook"""
    client = get_notebooklm_client()
    if not client:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Get sources for the notebook
        sources = client.get_notebook_sources_with_types(notebook_id)
        
        if sources:
            return {
                "notebook_id": notebook_id,
                "sources": [
                    {
                        "id": s.get('id', ''),
                        "title": s.get('title', 'Untitled'),
                        "type": s.get('type', 'unknown'),
                        "source_type": s.get('source_type', 'unknown')
                    }
                    for s in sources
                ]
            }
        else:
            return {"notebook_id": notebook_id, "sources": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Real-time chat endpoint with SSE streaming
    """
    notebook_id = request.notebook_id or NOTEBOOK_ID
    
    if not notebook_id:
        raise HTTPException(
            status_code=400, 
            detail="notebook_id is required. Set NOTEBOOK_ID env var or provide in request."
        )
    
    client = get_notebooklm_client()
    if not client:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please run 'notebooklm-mcp-auth' first."
        )
    
    async def generate():
        """Generate SSE stream"""
        try:
            # Send initial "thinking" status
            yield f"data: {json.dumps({'type': 'status', 'message': 'Đang xử lý câu hỏi...'})}\n\n"
            
            # Query NotebookLM
            result = await query_notebook_async(client, notebook_id, request.message, request.source_ids)
            
            if not result["success"]:
                yield f"data: {json.dumps({'type': 'error', 'message': result['error']})}\n\n"
                return
            
            # Modify response if configured
            modified_response = response_modifier.modify(result["response"])
            
            # Stream the response - split by lines to preserve formatting
            lines = modified_response.split('\n')
            
            for i, line in enumerate(lines):
                # Send each line with newline preserved
                content = line + ('\n' if i < len(lines) - 1 else '')
                yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"
                await asyncio.sleep(0.02)  # Small delay for streaming effect
            
            # Send completion with sources
            yield f"data: {json.dumps({'type': 'done', 'sources': result.get('sources', [])})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/chat/sync")
async def chat_sync(request: ChatRequest):
    """
    Synchronous chat endpoint (non-streaming)
    Useful for simple integrations
    """
    notebook_id = request.notebook_id or NOTEBOOK_ID
    
    if not notebook_id:
        raise HTTPException(status_code=400, detail="notebook_id is required")
    
    client = get_notebooklm_client()
    if not client:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    result = await query_notebook_async(client, notebook_id, request.message)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    
    modified_response = response_modifier.modify(result["response"])
    
    return ChatResponse(
        response=modified_response,
        sources=result.get("sources", []),
        timestamp=datetime.now().isoformat()
    )


@app.get("/api/notebooks")
async def list_notebooks():
    """List all available notebooks"""
    client = get_notebooklm_client()
    if not client:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        notebooks = client.list_notebooks()
        return {
            "notebooks": [
                {
                    "id": nb.id,
                    "title": nb.title,
                    "source_count": nb.source_count,
                    "url": f"https://notebooklm.google.com/notebook/{nb.id}"
                }
                for nb in notebooks
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Upload Page Route
# =============================================================================

@app.get("/upload")
async def upload_page():
    """Serve the upload wizard UI"""
    return FileResponse("static/upload.html")


# =============================================================================
# Google Drive API Endpoints
# =============================================================================

# Google Drive folder ID for root
GDRIVE_ROOT_FOLDER_ID = os.getenv("GDRIVE_ROOT_FOLDER_ID", "1I_NuYcJcDFxff-7x3oJseXqe3NFZ_9Ca")


def get_gdrive_client_for_read():
    """Get Google Drive client for reading (Service Account or OAuth)"""
    from gdrive_client import GoogleDriveClient
    import oauth_config
    
    # Try OAuth first (user's credentials)
    credentials = oauth_config.get_valid_credentials()
    if credentials:
        return GoogleDriveClient.from_oauth_credentials(credentials)
    
    # Fallback to Service Account for folder listing
    service_file = os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE", "test-adg-486208-bd963fa46e5e.json")
    if not os.path.exists(service_file):
        parent_path = os.path.join(os.path.dirname(__file__), "..", service_file)
        if os.path.exists(parent_path):
            service_file = parent_path
    
    if os.path.exists(service_file):
        return GoogleDriveClient(service_file)
    
    return None


@app.get("/api/drive/folders")
async def list_drive_folders():
    """List folder structure from Google Drive"""
    try:
        gdrive = get_gdrive_client_for_read()
        if not gdrive:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        def build_folder_tree(parent_id: str, depth: int = 0, max_depth: int = 5) -> list:
            """Recursively build folder tree"""
            if depth >= max_depth:
                return []
            
            folders = gdrive.list_folders(parent_id)
            result = []
            for folder in folders:
                children = build_folder_tree(folder['id'], depth + 1, max_depth)
                result.append({
                    'id': folder['id'],
                    'name': folder['name'],
                    'children': children
                })
            return result
        
        # Build tree starting from root
        tree = build_folder_tree(GDRIVE_ROOT_FOLDER_ID)
        
        return {
            "root_folder_id": GDRIVE_ROOT_FOLDER_ID,
            "folders": tree
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from fastapi import UploadFile, File, Form
import tempfile
import shutil


# =============================================================================
# OAuth2 Endpoints for Google Drive
# =============================================================================

from fastapi.responses import RedirectResponse
import oauth_config


@app.get("/api/drive/oauth/login")
async def oauth_login():
    """Redirect user to Google OAuth login"""
    if not oauth_config.OAUTH_CLIENT_ID or not oauth_config.OAUTH_CLIENT_SECRET:
        raise HTTPException(
            status_code=500, 
            detail="OAuth not configured. Set OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET in .env"
        )
    
    auth_url, state = oauth_config.get_authorization_url()
    return RedirectResponse(url=auth_url)


@app.get("/api/drive/oauth/callback")
async def oauth_callback(code: str = None, error: str = None):
    """Handle OAuth callback from Google"""
    if error:
        return RedirectResponse(url=f"/upload?error={error}")
    
    if not code:
        return RedirectResponse(url="/upload?error=no_code")
    
    try:
        credentials = oauth_config.exchange_code_for_tokens(code)
        email = oauth_config.get_user_email(credentials)
        
        # Redirect back to upload page with success
        return RedirectResponse(url=f"/upload?auth=success&email={email or 'user'}")
    except Exception as e:
        return RedirectResponse(url=f"/upload?error={str(e)}")


@app.get("/api/drive/oauth/status")
async def oauth_status():
    """Check OAuth authentication status"""
    credentials = oauth_config.get_valid_credentials()
    
    if credentials and credentials.valid:
        email = oauth_config.get_user_email(credentials)
        return {
            "authenticated": True,
            "email": email,
            "has_refresh_token": bool(credentials.refresh_token)
        }
    
    return {"authenticated": False}


@app.post("/api/drive/oauth/logout")
async def oauth_logout():
    """Clear OAuth tokens"""
    oauth_config.clear_tokens()
    return {"success": True, "message": "Logged out"}


def get_gdrive_client_oauth():
    """Get Google Drive client using OAuth credentials"""
    from gdrive_client import GoogleDriveClient
    
    credentials = oauth_config.get_valid_credentials()
    if not credentials:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated. Please login with Google first."
        )
    
    return GoogleDriveClient.from_oauth_credentials(credentials)


# Main upload endpoint using OAuth
@app.post("/api/drive/upload")
async def upload_to_drive(
    file: UploadFile = File(...),
    folder_id: str = Form(...)
):
    """Upload file to Google Drive using OAuth (user's quota)"""
    try:
        gdrive = get_gdrive_client_oauth()
        
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        try:
            # Upload to Google Drive with original filename
            result = gdrive.upload_file(tmp_path, folder_id, custom_name=file.filename)
            
            return {
                "success": True,
                "id": result.get('id'),
                "name": result.get('name'),
                "mimeType": result.get('mimeType'),
                "webViewLink": result.get('webViewLink')
            }
        finally:
            # Cleanup temp file
            import os
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mount static files (must be after routes)
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=True)
