"""
Activity Log API routes
Admin-only endpoints for viewing audit trail.
"""

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import ActivityLog
from backend.api.v1.admin import require_admin

router = APIRouter(prefix="/activity-logs", tags=["activity-logs"])


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards in user input."""
    return value.replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_activity_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str = Query(None),
    user_email: str = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """List activity logs with pagination and filters."""
    query = select(ActivityLog)
    count_query = select(func.count(ActivityLog.id))

    if action:
        safe_action = _escape_like(action)
        query = query.where(ActivityLog.action.ilike(f"%{safe_action}%"))
        count_query = count_query.where(ActivityLog.action.ilike(f"%{safe_action}%"))
    if user_email:
        safe_email = _escape_like(user_email)
        query = query.where(ActivityLog.user_email.ilike(f"%{safe_email}%"))
        count_query = count_query.where(ActivityLog.user_email.ilike(f"%{safe_email}%"))

    # Total count
    total = (await db.execute(count_query)).scalar() or 0

    # Paginated results
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": str(log.id),
                "user_email": log.user_email,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() + "Z",
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }
