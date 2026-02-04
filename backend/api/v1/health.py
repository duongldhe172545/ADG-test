"""
Health Check API Routes
System health and monitoring endpoints
"""

from fastapi import APIRouter

from backend.services.notebooklm_service import get_notebooklm_service
from backend.services.scheduler_service import get_scheduler_service
from backend.models.responses import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Check authentication and server health.
    
    Returns status of NotebookLM authentication and system health.
    """
    scheduler = get_scheduler_service()
    health = scheduler.health_checker
    
    try:
        notebooklm = get_notebooklm_service()
        notebooks = notebooklm.list_notebooks()
        
        return HealthResponse(
            status="healthy",
            notebooklm_auth="valid",
            last_refresh=health.last_refresh_time,
            notebook_count=len(notebooks) if notebooks else 0
        )
        
    except Exception as e:
        return HealthResponse(
            status="degraded",
            notebooklm_auth=f"error: {str(e)}",
            last_refresh=health.last_refresh_time,
            notebook_count=None
        )


@router.get("/ping")
async def ping():
    """Simple ping endpoint for load balancer health checks"""
    return {"status": "ok"}


@router.get("/scheduler")
async def scheduler_status():
    """Get scheduler status and last refresh info"""
    scheduler = get_scheduler_service()
    health = scheduler.health_checker
    
    return {
        "status": health.last_status,
        "last_refresh": health.last_refresh_time,
        "consecutive_failures": health.consecutive_failures
    }
