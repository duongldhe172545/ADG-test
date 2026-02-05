"""
ADG Knowledge Management System
FastAPI Application Entry Point

This is the main entry point for the application.
All routes, middleware, and configuration are set up here.
"""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from backend.config import settings
from backend.api.router import api_router, legacy_router
from backend.services.scheduler_service import get_scheduler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    print("🚀 Starting ADG Knowledge Management System...")
    
    # Start background scheduler
    scheduler = get_scheduler_service()
    scheduler.start()
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")
    scheduler.stop()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Knowledge Management System powered by NotebookLM",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)


# =============================================================================
# Middleware
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# API Routes
# =============================================================================

# New versioned API routes
app.include_router(api_router)

# Legacy routes for backward compatibility
app.include_router(legacy_router)


# =============================================================================
# Page Routes (HTML)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the landing page"""
    template_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "frontend", "templates", "landing.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Landing page not found</h1>")


@app.get("/chatbot", response_class=HTMLResponse)
async def chatbot_page():
    """Serve the chatbot UI with 3-panel layout"""
    template_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "frontend", "templates", "chatbot.html"
    )
    
    # Fallback to index.html if chatbot.html doesn't exist yet
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "frontend", "templates", "index.html"
        )
    
    # Fallback to old location
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "web_chatbot", "static", "index.html"
        )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Chat UI not found</h1>")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page():
    """Serve the upload wizard UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "upload.html"
    )
    
    # Fallback to old location if new doesn't exist
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..", "web_chatbot", "static", "upload.html"
        )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Upload UI not found</h1>")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """Serve the dashboard UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "dashboard.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Dashboard UI not found</h1>")


@app.get("/sources", response_class=HTMLResponse)
async def sources_page():
    """Serve the source selection UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "sources.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Sources UI not found</h1>")


@app.get("/document", response_class=HTMLResponse)
async def document_page():
    """Serve the document viewer UI"""
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..", "frontend", "templates", "document.html"
    )
    
    if os.path.exists(template_path):
        return FileResponse(template_path)
    
    return HTMLResponse("<h1>ADG KMS - Document Viewer not found</h1>")


# =============================================================================
# Static Files
# =============================================================================

# Try new static location first, fallback to old
static_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")
if not os.path.exists(static_path):
    static_path = os.path.join(os.path.dirname(__file__), "..", "web_chatbot", "static")

if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


# =============================================================================
# Run Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
