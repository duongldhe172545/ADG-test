"""
Approval Workflow — Query Endpoints
Read-only endpoints: pending, history, my-requests, preview.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import ApprovalRequest, User
from backend.services.permission_service import get_current_user
from backend.api.v1.documents import get_gdrive_service
from backend.api.v1.approval_submit import _get_user_department_id

router = APIRouter(prefix="/approvals", tags=["Approval Workflow"])


# =============================================================================
# Guard
# =============================================================================

async def require_approver(current_user: dict = Depends(get_current_user)):
    """Ensure user has approve permission"""
    if not any(r in ["admin", "super_admin", "manager"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Approver access required")
    return current_user


# =============================================================================
# Pending Approvals
# =============================================================================

@router.get("/pending")
async def list_pending(
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """List pending approval requests based on role.
    Manager sees 'pending' (Step 1). Admin sees 'manager_approved' (Step 2).
    """
    roles = approver.get("roles", [])
    is_admin = any(r in ["admin", "super_admin"] for r in roles)
    is_manager = "manager" in roles
    
    # Determine which statuses this user can act on
    if is_admin and is_manager:
        # Has both roles — show both queues
        statuses = ["pending", "manager_approved"]
    elif is_admin:
        # Admin only sees manager-approved items (Step 2)
        statuses = ["manager_approved"]
    else:
        # Manager/approver sees pending items (Step 1)
        statuses = ["pending"]
    
    query = select(ApprovalRequest).where(ApprovalRequest.status.in_(statuses))

    # Manager (non-admin) only sees approvals from their own department
    if is_manager and not is_admin:
        mgr_dept_id = await _get_user_department_id(db, approver["id"])
        if mgr_dept_id:
            query = query.where(ApprovalRequest.department_id == mgr_dept_id)

    result = await db.execute(
        query.order_by(ApprovalRequest.created_at.desc())
    )
    requests = result.scalars().all()
    
    items = []
    for req in requests:
        # Get requester info
        user_result = await db.execute(select(User).where(User.id == req.requester_id))
        requester = user_result.scalars().first()
        
        # Get manager reviewer info if manager_approved
        manager_reviewer_info = None
        if req.status == "manager_approved" and req.reviewer_id:
            mgr_result = await db.execute(select(User).where(User.id == req.reviewer_id))
            mgr = mgr_result.scalars().first()
            if mgr:
                manager_reviewer_info = {"email": mgr.email, "name": mgr.name}
        
        items.append({
            "id": str(req.id),
            "requester": {
                "id": str(requester.id) if requester else None,
                "email": requester.email if requester else "Unknown",
                "name": requester.name if requester else "Unknown",
            },
            "action_type": req.action_type,
            "status": req.status,
            "extra_data": req.extra_data or {},
            "created_at": req.created_at.isoformat() + "Z",
            "manager_reviewer": manager_reviewer_info,
        })
    
    return {"pending": items, "count": len(items)}


# =============================================================================
# History
# =============================================================================

@router.get("/history")
async def list_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """List approval history (approved/rejected/manager_approved)"""
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status.in_(["approved", "rejected", "manager_approved"]))
        .order_by(ApprovalRequest.reviewed_at.desc())
        .limit(limit)
    )
    requests = result.scalars().all()
    
    items = []
    for req in requests:
        user_result = await db.execute(select(User).where(User.id == req.requester_id))
        requester = user_result.scalars().first()
        
        reviewer_info = None
        if req.reviewer_id:
            reviewer_result = await db.execute(select(User).where(User.id == req.reviewer_id))
            reviewer = reviewer_result.scalars().first()
            if reviewer:
                reviewer_info = {"email": reviewer.email, "name": reviewer.name}
        
        items.append({
            "id": str(req.id),
            "requester": {
                "email": requester.email if requester else "Unknown",
                "name": requester.name if requester else "Unknown",
            },
            "action_type": req.action_type,
            "status": req.status,
            "extra_data": req.extra_data or {},
            "reviewer": reviewer_info,
            "review_note": req.review_note,
            "created_at": req.created_at.isoformat() + "Z",
            "reviewed_at": (req.reviewed_at.isoformat() + "Z") if req.reviewed_at else None,
        })
    
    return {"history": items}


# =============================================================================
# My Requests (for editors to track status)
# =============================================================================

@router.get("/my-requests")
async def list_my_requests(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's own approval requests (for editors to track status)"""
    user_id = UUID(current_user["id"])
    
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.requester_id == user_id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(limit)
    )
    requests = result.scalars().all()
    
    items = []
    for req in requests:
        reviewer_info = None
        if req.reviewer_id:
            reviewer_result = await db.execute(select(User).where(User.id == req.reviewer_id))
            reviewer = reviewer_result.scalars().first()
            if reviewer:
                reviewer_info = {"email": reviewer.email, "name": reviewer.name}
        
        items.append({
            "id": str(req.id),
            "action_type": req.action_type,
            "status": req.status,
            "extra_data": req.extra_data or {},
            "reviewer": reviewer_info,
            "review_note": req.review_note,
            "created_at": req.created_at.isoformat() + "Z",
            "reviewed_at": (req.reviewed_at.isoformat() + "Z") if req.reviewed_at else None,
        })
    
    return {"requests": items}


# =============================================================================
# Preview File
# =============================================================================

@router.get("/preview/{file_id}")
async def preview_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get a Google Drive preview URL for a pending file.
    Shares the file publicly (read-only) so the preview iframe can load.
    Admin/super_admin only.
    """
    roles = current_user.get("roles", [])
    if "admin" not in roles and "super_admin" not in roles and "manager" not in roles:
        raise HTTPException(status_code=403, detail="Admin/Manager only")
    
    try:
        gdrive = get_gdrive_service()
        
        # Share file so preview iframe can access it
        gdrive.share_file_public(file_id)
        
        # Return Google Drive embed preview URL
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
        
        return {
            "success": True,
            "preview_url": preview_url,
            "file_id": file_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")
