"""
Admin API - Department Management
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import Department
from backend.api.v1.admin_users import require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/departments")
async def list_departments(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """List all departments"""
    result = await db.execute(select(Department).order_by(Department.name))
    depts = result.scalars().all()
    return {
        "departments": [
            {"id": str(d.id), "name": d.name, "parent_id": str(d.parent_id) if d.parent_id else None}
            for d in depts
        ]
    }
