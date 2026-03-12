"""
Activity Log Service
Helper functions for audit trail logging.
"""

from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ActivityLog


async def log_activity(
    db: AsyncSession,
    user_id,
    user_email: str,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """
    Record an activity log entry.
    Call this inside any endpoint that should be audited.
    Does NOT commit — relies on the caller's transaction.
    """
    if isinstance(user_id, str):
        user_id = UUID(user_id)

    log = ActivityLog(
        user_id=user_id,
        user_email=user_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(log)
