"""
Document Repository — CRUD for the 'documents' table.
Supports versioning, indexing tracking, and dashboard stats.
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Document, ApprovalRequest


class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> Document:
        doc = Document(**kwargs)
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def get_by_drive_id(self, drive_file_id: str) -> Optional[Document]:
        result = await self.db.execute(
            select(Document).where(Document.drive_file_id == drive_file_id)
        )
        return result.scalars().first()

    async def get_by_id(self, doc_id: str) -> Optional[Document]:
        result = await self.db.execute(
            select(Document).where(Document.id == doc_id)
        )
        return result.scalars().first()

    async def list_all(
        self,
        status: str = "active",
        folder_id: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Document]:
        query = select(Document).where(Document.status == status)
        if folder_id:
            query = query.where(Document.folder_id == folder_id)
        query = query.order_by(Document.uploaded_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count(self, status: str = "active") -> int:
        result = await self.db.execute(
            select(func.count(Document.id)).where(Document.status == status)
        )
        return result.scalar() or 0

    async def count_indexed(self) -> int:
        result = await self.db.execute(
            select(func.count(Document.id)).where(
                Document.status == "active",
                Document.indexed_at.isnot(None),
            )
        )
        return result.scalar() or 0

    async def update_version(
        self,
        drive_file_id: str,
        new_drive_file_id: str,
        new_file_name: str,
        change_note: str,
        uploaded_by=None,
        approved_by=None,
    ) -> Optional[Document]:
        """Increment version when file is updated."""
        doc = await self.get_by_drive_id(drive_file_id)
        if not doc:
            return None
        doc.old_drive_id = drive_file_id
        doc.drive_file_id = new_drive_file_id
        doc.file_name = new_file_name
        doc.version += 1
        doc.change_note = change_note
        if uploaded_by:
            doc.uploaded_by = uploaded_by
        if approved_by:
            doc.approved_by = approved_by
        doc.approved_at = datetime.utcnow()
        doc.indexed_at = None  # Needs re-indexing
        await self.db.flush()
        return doc

    async def mark_indexed(self, drive_file_id: str):
        await self.db.execute(
            update(Document)
            .where(Document.drive_file_id == drive_file_id)
            .values(indexed_at=datetime.utcnow())
        )

    async def mark_deleted(self, drive_file_id: str):
        await self.db.execute(
            update(Document)
            .where(Document.drive_file_id == drive_file_id)
            .values(status="deleted")
        )

    async def get_stats(self) -> dict:
        """Dashboard statistics."""
        total = await self.count("active")
        indexed = await self.count_indexed()

        # Pending approvals count
        pending_result = await self.db.execute(
            select(func.count(ApprovalRequest.id)).where(
                ApprovalRequest.status == "pending"
            )
        )
        pending = pending_result.scalar() or 0

        # Recent activity (last 20 approval actions)
        activity_result = await self.db.execute(
            select(ApprovalRequest)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(20)
        )
        activities = activity_result.scalars().all()

        return {
            "total_files": total,
            "indexed_files": indexed,
            "pending_approvals": pending,
            "unindexed_files": total - indexed,
            "recent_activity": [
                {
                    "id": str(a.id),
                    "action": a.action_type,
                    "status": a.status,
                    "file_name": (a.extra_data or {}).get("file_name", "Unknown"),
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
                }
                for a in activities
            ],
        }
