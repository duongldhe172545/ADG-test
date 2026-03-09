"""
Health Check API Routes
System health and monitoring endpoints
"""

from fastapi import APIRouter, Depends

from backend.models.responses import HealthResponse
from backend.api.v1.admin import require_admin

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Check system health and Google Drive auth status.
    """
    try:
        from backend.api.v1.documents import get_gdrive_service_for_read
        gdrive = get_gdrive_service_for_read()
        drive_status = "connected" if gdrive else "not_configured"
    except Exception as e:
        drive_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy",
        drive_auth=drive_status,
    )


@router.get("/ping")
async def ping():
    """Simple ping endpoint for load balancer health checks"""
    return {"status": "ok"}


@router.get("/db-tables")
async def db_tables(admin: dict = Depends(require_admin)):
    """Show all tables in the database (admin only diagnostic endpoint)"""
    try:
        from backend.db.connection import get_async_engine
        from sqlalchemy import text
        engine = get_async_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            ))
            tables = [row[0] for row in result.fetchall()]

            # Also get alembic version
            try:
                ver = await conn.execute(text("SELECT version_num FROM alembic_version"))
                version = ver.scalar()
            except Exception:
                version = "no alembic_version table"

        return {"tables": tables, "count": len(tables), "alembic_version": version}
    except Exception as e:
        return {"error": str(e)}

