"""
Dashboard API — Stats and file management endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.repositories.document_repo import DocumentRepository
from backend.services.permission_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get dashboard overview statistics."""
    repo = DocumentRepository(db)
    stats = await repo.get_stats()
    return stats


@router.get("/files")
async def list_managed_files(
    status: str = "active",
    folder_id: str = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all managed files with metadata."""
    repo = DocumentRepository(db)
    docs = await repo.list_all(status=status, folder_id=folder_id, limit=limit, offset=offset)
    return [
        {
            "id": str(d.id),
            "drive_file_id": d.drive_file_id,
            "file_name": d.file_name,
            "mime_type": d.mime_type,
            "file_size": d.file_size,
            "folder_id": d.folder_id,
            "folder_path": d.folder_path,
            "version": d.version,
            "change_note": d.change_note,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "approved_at": d.approved_at.isoformat() if d.approved_at else None,
            "indexed_at": d.indexed_at.isoformat() if d.indexed_at else None,
            "status": d.status,
        }
        for d in docs
    ]
