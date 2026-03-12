"""
Notification Service
Helper functions for in-app notifications.
"""

from uuid import UUID
from typing import Optional, List
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Notification


async def create_notification(
    db: AsyncSession,
    user_id,
    title: str,
    message: str,
    type: str,
    link: Optional[str] = None,
):
    """
    Create a notification for a user.
    Does NOT commit — relies on the caller's transaction.
    """
    if isinstance(user_id, str):
        user_id = UUID(user_id)

    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        link=link,
    )
    db.add(notif)
    return notif


async def get_unread_count(db: AsyncSession, user_id) -> int:
    """Get count of unread notifications for a user."""
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
    )
    return result.scalar() or 0


async def get_notifications(db: AsyncSession, user_id, limit: int = 30):
    """Get recent notifications for a user."""
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def mark_read(db: AsyncSession, notification_id, user_id):
    """Mark a single notification as read."""
    if isinstance(notification_id, str):
        notification_id = UUID(notification_id)
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    await db.execute(
        update(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        ).values(is_read=True)
    )


async def mark_all_read(db: AsyncSession, user_id):
    """Mark all notifications as read for a user."""
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    await db.execute(
        update(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        ).values(is_read=True)
    )
