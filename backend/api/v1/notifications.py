"""
Notifications API routes
User-facing endpoints for in-app notifications.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from backend.db.connection import get_db
from backend.services.permission_service import get_current_user
from backend.services.notification_service import (
    get_notifications, get_unread_count, mark_read, mark_all_read,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkReadRequest(BaseModel):
    notification_id: Optional[str] = None  # None = mark all


@router.get("")
async def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get user's notifications."""
    user_id = current_user["id"]
    notifs = await get_notifications(db, user_id, limit=limit)
    unread = await get_unread_count(db, user_id)

    return {
        "notifications": [
            {
                "id": str(n.id),
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() + "Z",
            }
            for n in notifs
        ],
        "unread_count": unread,
    }


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get just the unread count (for polling)."""
    count = await get_unread_count(db, current_user["id"])
    return {"unread_count": count}


@router.post("/mark-read")
async def mark_notifications_read(
    req: MarkReadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark one or all notifications as read."""
    user_id = current_user["id"]
    if req.notification_id:
        await mark_read(db, req.notification_id, user_id)
    else:
        await mark_all_read(db, user_id)
    await db.commit()
    return {"success": True}
