"""
Approval Workflow — Submit Endpoints
Upload, update, and delete submission flows.
"""

import os
import tempfile
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import ApprovalRequest, User, UserDepartment
from backend.services.permission_service import get_current_user
from backend.services.activity_service import log_activity
from backend.services.notification_service import create_notification
from backend.api.v1.documents import get_gdrive_service
from backend.config import settings
from backend.logger import get_logger

logger = get_logger("approvals.submit")

router = APIRouter(prefix="/approvals", tags=["Approval Workflow"])


# =============================================================================
# Helpers (shared with other approval modules)
# =============================================================================

async def _get_user_department_id(db: AsyncSession, user_id) -> Optional[UUID]:
    """Look up the user's department_id from user_departments table."""
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    result = await db.execute(
        select(UserDepartment.department_id).where(UserDepartment.user_id == user_id)
    )
    row = result.first()
    return row[0] if row else None


async def _notify_department_approvers(db: AsyncSession, department_id, file_name: str, requester_email: str):
    """Notify managers and admins in the same department about a new submission."""
    from backend.db.models import UserRole, Role
    # Find managers in the same department
    mgr_result = await db.execute(
        select(UserDepartment.user_id)
        .join(UserRole, UserRole.user_id == UserDepartment.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserDepartment.department_id == department_id,
            Role.name.in_(["manager", "admin", "super_admin"]),
        )
    )
    approver_ids = set(row[0] for row in mgr_result.all())
    for uid in approver_ids:
        await create_notification(
            db, uid,
            "📄 File mới cần duyệt",
            f"{requester_email} đã gửi file '{file_name}' cần duyệt.",
            "approval_needed",
            link="/admin/approvals",
        )


# =============================================================================
# Submit for Approval (Upload to Pending)
# =============================================================================

@router.post("/submit")
async def submit_for_approval(
    file: UploadFile = File(...),
    target_folder_id: str = Form(...),
    target_folder_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload file to Pending folder and create approval request.
    File is uploaded to _PENDING_ folder, NOT to the target folder yet.
    """
    pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID
    if not pending_folder_id:
        raise HTTPException(status_code=500, detail="Pending folder not configured")

    tmp_path = None
    try:
        file_content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        file_size = len(file_content)

        gdrive = get_gdrive_service()
        uploaded_file = gdrive.upload_file(
            file_path=tmp_path,
            parent_id=pending_folder_id,
            mime_type=file.content_type,
            custom_name=file.filename,
        )

        # Look up user's department
        dept_id = await _get_user_department_id(db, current_user["id"])

        approval = ApprovalRequest(
            requester_id=UUID(current_user["id"]),
            department_id=dept_id,
            action_type="upload",
            status="pending",
            extra_data={
                "file_id": uploaded_file.get("id"),
                "file_name": file.filename,
                "mime_type": file.content_type,
                "target_folder_id": target_folder_id,
                "target_folder_name": target_folder_name,
                "file_size": file_size,
            }
        )
        db.add(approval)

        # Activity log
        await log_activity(db, current_user["id"], current_user["email"], "file.upload",
            target_type="file", target_id=uploaded_file.get("id"),
            details={"file_name": file.filename, "target_folder": target_folder_name})

        # Notify department approvers (managers/admins)
        if dept_id:
            await _notify_department_approvers(db, dept_id, file.filename, current_user["email"])

        return {
            "success": True,
            "approval_id": str(approval.id),
            "message": f"File '{file.filename}' submitted for approval",
            "status": "pending",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# =============================================================================
# Submit Update for Approval (Replace existing file)
# =============================================================================

@router.post("/submit-update")
async def submit_update_for_approval(
    file: UploadFile = File(...),
    target_folder_id: str = Form(...),
    target_folder_name: str = Form(""),
    replace_file_id: str = Form(...),
    replace_file_name: str = Form(""),
    change_note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload updated file to Pending folder and create approval request.
    When approved, old file moves to _OLD/ subfolder and new file takes its place.
    """
    pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID
    if not pending_folder_id:
        raise HTTPException(status_code=500, detail="Pending folder not configured")

    tmp_path = None
    try:
        file_content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        file_size = len(file_content)

        gdrive = get_gdrive_service()
        uploaded_file = gdrive.upload_file(
            file_path=tmp_path,
            parent_id=pending_folder_id,
            mime_type=file.content_type,
            custom_name=file.filename,
        )

        dept_id = await _get_user_department_id(db, current_user["id"])

        approval = ApprovalRequest(
            requester_id=UUID(current_user["id"]),
            department_id=dept_id,
            action_type="update",
            status="pending",
            extra_data={
                "file_id": uploaded_file.get("id"),
                "file_name": file.filename,
                "mime_type": file.content_type,
                "target_folder_id": target_folder_id,
                "target_folder_name": target_folder_name,
                "file_size": file_size,
                "replace_file_id": replace_file_id,
                "replace_file_name": replace_file_name,
                "change_note": change_note,
            }
        )
        db.add(approval)

        # Activity log + notify
        await log_activity(db, current_user["id"], current_user["email"], "file.submit_update",
            target_type="file", target_id=uploaded_file.get("id"),
            details={"file_name": file.filename, "replaces": replace_file_name})
        if dept_id:
            await _notify_department_approvers(db, dept_id, file.filename, current_user["email"])

        return {
            "success": True,
            "approval_id": str(approval.id),
            "message": f"Update '{file.filename}' (replacing '{replace_file_name}') submitted for approval",
            "status": "pending",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update submit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# =============================================================================
# Submit Delete Request for Approval
# =============================================================================

@router.post("/submit-delete")
async def submit_delete_request(
    file_id: str = Form(...),
    file_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Submit a delete request for approval.
    Non-admin users request file deletion, admin approves.
    """
    try:
        dept_id = await _get_user_department_id(db, current_user["id"])

        approval = ApprovalRequest(
            requester_id=UUID(current_user["id"]),
            department_id=dept_id,
            action_type="delete",
            status="pending",
            extra_data={
                "file_id": file_id,
                "file_name": file_name or "Unknown",
            }
        )
        db.add(approval)

        await log_activity(db, current_user["id"], current_user["email"], "file.submit_delete",
            target_type="file", target_id=file_id,
            details={"file_name": file_name})
        if dept_id:
            await _notify_department_approvers(db, dept_id, file_name or file_id, current_user["email"])

        return {
            "success": True,
            "approval_id": str(approval.id),
            "message": f"Delete request for '{file_name or file_id}' submitted",
            "status": "pending",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete submit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Submit failed: {str(e)}")
