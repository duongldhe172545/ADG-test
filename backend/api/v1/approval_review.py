"""
Approval Workflow — Review Endpoints
Approve, reject, cancel, and batch operations.
"""

from uuid import UUID
from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import ApprovalRequest, User
from backend.services.activity_service import log_activity
from backend.services.notification_service import create_notification
from backend.api.v1.documents import get_gdrive_service
from backend.db.repositories.document_repo import DocumentRepository
from backend.config import settings
from backend.logger import get_logger
from backend.api.v1.approval_queries import require_approver
from backend.api.v1.approval_submit import _get_user_department_id

logger = get_logger("approvals.review")

router = APIRouter(prefix="/approvals", tags=["Approval Workflow"])


# =============================================================================
# Approval action handlers
# =============================================================================

async def _handle_delete_approval(approval, extra_data, approver, note, db):
    """Handle delete file approval: remove from Google Drive."""
    gdrive = get_gdrive_service()

    file_id = extra_data.get("file_id")
    file_name = extra_data.get("file_name", "Unknown")

    gdrive.delete_file(file_id)
    logger.info(f"Deleted file via approval: {file_id} ({file_name})")

    approval.status = "approved"
    approval.reviewer_id = UUID(approver["id"])
    approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    approval.review_note = note

    return {"success": True, "message": f"File '{file_name}' has been deleted", "file_id": file_id}


async def _handle_update_approval(approval, extra_data, approver, note, db):
    """Handle update file approval: move old to _OLD/, move new to target."""
    gdrive = get_gdrive_service()

    file_id = extra_data.get("file_id")
    replace_file_id = extra_data.get("replace_file_id")
    target_folder_id = extra_data.get("target_folder_id")
    change_note = extra_data.get("change_note", "")
    pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID

    if not file_id or not target_folder_id or not replace_file_id:
        raise HTTPException(status_code=400, detail="Missing file, target folder, or replace file info")

    # 1. Find or create _OLD subfolder
    old_query = gdrive.service.files().list(
        q=f"name='_OLD' and '{target_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)"
    ).execute()
    old_files = old_query.get("files", [])
    if old_files:
        old_folder_id = old_files[0]["id"]
    else:
        old_folder = gdrive.service.files().create(
            body={"name": "_OLD", "mimeType": "application/vnd.google-apps.folder", "parents": [target_folder_id]},
            fields="id"
        ).execute()
        old_folder_id = old_folder["id"]

    # 2. Move old file to _OLD/
    old_file_info = gdrive.service.files().get(fileId=replace_file_id, fields="parents").execute()
    old_parents = ",".join(old_file_info.get("parents", []))
    gdrive.service.files().update(
        fileId=replace_file_id, addParents=old_folder_id, removeParents=old_parents, fields="id, name"
    ).execute()

    # 3. Move new file from _PENDING to target
    move_result = gdrive.service.files().update(
        fileId=file_id, addParents=target_folder_id, removeParents=pending_folder_id,
        fields="id, parents, name, mimeType"
    ).execute()
    file_name = move_result.get("name", extra_data.get("file_name", ""))

    # 4. Track in documents table
    doc_repo = DocumentRepository(db)
    existing_doc = await doc_repo.get_by_drive_id(replace_file_id)
    if existing_doc:
        await doc_repo.update_version(
            drive_file_id=replace_file_id, new_drive_file_id=file_id,
            new_file_name=file_name, change_note=change_note,
            uploaded_by=approval.requester_id, approved_by=UUID(approver["id"]),
        )
    else:
        await doc_repo.create(
            drive_file_id=file_id, file_name=file_name,
            mime_type=extra_data.get("mime_type"), file_size=extra_data.get("file_size"),
            folder_id=target_folder_id, folder_path=extra_data.get("target_folder_name", ""),
            version=2, old_drive_id=replace_file_id, change_note=change_note,
            uploaded_by=approval.requester_id, approved_by=UUID(approver["id"]),
            approved_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    # 5. Update approval
    approval.status = "approved"
    approval.reviewer_id = UUID(approver["id"])
    approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    approval.review_note = note

    return {"success": True, "message": f"File '{file_name}' updated (old version moved to _OLD/)", "file_id": file_id}


async def _handle_upload_approval(approval, extra_data, approver, note, db):
    """Handle upload file approval: move from pending to target folder."""
    gdrive = get_gdrive_service()

    file_id = extra_data.get("file_id")
    target_folder_id = extra_data.get("target_folder_id")

    if not file_id or not target_folder_id:
        raise HTTPException(status_code=400, detail="Missing file or target folder info")

    pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID
    move_result = gdrive.service.files().update(
        fileId=file_id, addParents=target_folder_id, removeParents=pending_folder_id,
        fields="id, parents, name, mimeType, webViewLink"
    ).execute()
    file_name = move_result.get("name", extra_data.get("file_name", ""))

    doc_repo = DocumentRepository(db)
    await doc_repo.create(
        drive_file_id=file_id, file_name=file_name,
        mime_type=extra_data.get("mime_type"), file_size=extra_data.get("file_size"),
        folder_id=target_folder_id, folder_path=extra_data.get("target_folder_name", ""),
        uploaded_by=approval.requester_id, approved_by=UUID(approver["id"]),
        approved_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    approval.status = "approved"
    approval.reviewer_id = UUID(approver["id"])
    approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    approval.review_note = note

    # Log + notify requester
    await log_activity(db, approver["id"], approver["email"], "file.approve",
        target_type="approval", target_id=str(approval.id),
        details={"step": 2, "file_name": file_name, "action": "final_approve"})
    await create_notification(db, approval.requester_id,
        "✅ File đã được duyệt",
        f"File '{file_name}' đã được duyệt và di chuyển vào thư mục đích.",
        "approved", link="/sources")

    return {"success": True, "message": f"File '{file_name}' approved and moved to target folder", "file_id": file_id}


# =============================================================================
# Approve endpoint (orchestrator)
# =============================================================================

@router.post("/{approval_id}/approve")
async def approve_request(
    approval_id: str,
    note: str = "",
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """
    Approve a pending request. 2-step workflow:
    Step 1 (Manager): pending → manager_approved
    Step 2 (Admin): manager_approved → approved (file moves)
    """
    result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    approval = result.scalars().first()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status not in ("pending", "manager_approved"):
        raise HTTPException(status_code=400, detail=f"Request already {approval.status}")
    
    roles = approver.get("roles", [])
    is_admin = any(r in ["admin", "super_admin"] for r in roles)
    is_manager = "manager" in roles
    
    # Step 1: Manager approves pending → manager_approved
    if approval.status == "pending":
        if not is_manager and not is_admin:
            raise HTTPException(status_code=403, detail="Manager approval required for Step 1")
        
        if is_admin and not is_manager:
            pass  # Admin can skip Step 1, fall through to full approval
        else:
            # Manager must be in the same department as the requester
            mgr_dept_id = await _get_user_department_id(db, approver["id"])
            req_dept_id = approval.department_id
            if mgr_dept_id and req_dept_id and mgr_dept_id != req_dept_id:
                raise HTTPException(
                    status_code=403,
                    detail="Bạn chỉ được duyệt file trong phòng ban của mình"
                )

            approval.status = "manager_approved"
            approval.reviewer_id = UUID(approver["id"])
            approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            approval.review_note = note or "Manager approved (Step 1)"

            await log_activity(db, approver["id"], approver["email"], "file.approve",
                target_type="approval", target_id=str(approval.id),
                details={"step": 1, "file_name": (approval.extra_data or {}).get("file_name")})

            # Notify admins that Step 1 is complete
            from backend.db.models import UserRole, Role
            admin_result = await db.execute(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name.in_(["admin", "super_admin"]))
            )
            for row in admin_result.all():
                await create_notification(
                    db, row[0],
                    "📝 Chờ duyệt Bước 2",
                    f"Manager đã duyệt file '{(approval.extra_data or {}).get('file_name', '')}'. Chờ Admin duyệt Bước 2.",
                    "approval_needed",
                    link="/admin/approvals",
                )

            return {
                "success": True,
                "message": f"✅ Manager đã duyệt (Bước 1). Chờ Admin duyệt (Bước 2).",
                "status": "manager_approved",
            }
    
    # Step 2: Admin final approval
    if approval.status == "manager_approved" and not is_admin:
        raise HTTPException(status_code=403, detail="Admin approval required for Step 2")
    
    extra_data = approval.extra_data or {}
    action_type = approval.action_type or "upload"
    
    # Dispatch to handler by action type
    try:
        if action_type == "delete":
            return await _handle_delete_approval(approval, extra_data, approver, note, db)
        elif action_type == "update":
            return await _handle_update_approval(approval, extra_data, approver, note, db)
        else:
            return await _handle_upload_approval(approval, extra_data, approver, note, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


# =============================================================================
# Reject
# =============================================================================

@router.post("/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    note: str = "",
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """
    Reject a pending request.
    Optionally deletes the file from pending folder.
    """
    result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    approval = result.scalars().first()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status not in ("pending", "manager_approved"):
        raise HTTPException(status_code=400, detail=f"Request already {approval.status}")
    
    # Update approval record
    approval.status = "rejected"
    approval.reviewer_id = UUID(approver["id"])
    approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    approval.review_note = note

    # Log + notify requester
    file_name = (approval.extra_data or {}).get("file_name", "")
    await log_activity(db, approver["id"], approver["email"], "file.reject",
        target_type="approval", target_id=str(approval.id),
        details={"file_name": file_name, "reason": note})
    await create_notification(db, approval.requester_id,
        "❌ Yêu cầu bị từ chối",
        f"File '{file_name}' đã bị từ chối." + (f" Lý do: {note}" if note else ""),
        "rejected", link="/approval-history")

    return {
        "success": True,
        "message": f"Request rejected",
        "review_note": note,
    }


# =============================================================================
# Batch Operations
# =============================================================================

class BatchActionRequest(BaseModel):
    approval_ids: List[str]
    note: str = ""


@router.post("/batch-approve")
async def batch_approve(
    body: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """
    Approve multiple requests at once.
    Reuses the same 2-step workflow logic per item.
    Returns success/fail counts and error details.
    """
    roles = approver.get("roles", [])
    is_admin = any(r in ["admin", "super_admin"] for r in roles)
    is_manager = "manager" in roles

    results = {"success": 0, "fail": 0, "errors": []}

    for aid in body.approval_ids:
        try:
            result = await db.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == aid)
            )
            approval = result.scalars().first()

            if not approval:
                results["fail"] += 1
                results["errors"].append({"id": aid, "error": "Not found"})
                continue

            if approval.status not in ("pending", "manager_approved"):
                results["fail"] += 1
                results["errors"].append({"id": aid, "error": f"Already {approval.status}"})
                continue

            # Step 1: Manager approves pending → manager_approved
            if approval.status == "pending":
                if not is_manager and not is_admin:
                    results["fail"] += 1
                    results["errors"].append({"id": aid, "error": "Manager required for Step 1"})
                    continue

                if is_admin and not is_manager:
                    pass  # Admin skips Step 1
                else:
                    # Manager must be in the same department as the requester
                    mgr_dept_id = await _get_user_department_id(db, approver["id"])
                    req_dept_id = approval.department_id
                    if mgr_dept_id and req_dept_id and mgr_dept_id != req_dept_id:
                        results["fail"] += 1
                        results["errors"].append({"id": aid, "error": "Không cùng phòng ban"})
                        continue

                    approval.status = "manager_approved"
                    approval.reviewer_id = UUID(approver["id"])
                    approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    approval.review_note = body.note or "Manager approved (Step 1 - batch)"
                    results["success"] += 1
                    continue

            # Step 2: Admin final approval
            if approval.status == "manager_approved" and not is_admin:
                results["fail"] += 1
                results["errors"].append({"id": aid, "error": "Admin required for Step 2"})
                continue

            extra_data = approval.extra_data or {}
            action_type = approval.action_type or "upload"

            if action_type == "delete":
                await _handle_delete_approval(approval, extra_data, approver, body.note, db)
            elif action_type == "update":
                await _handle_update_approval(approval, extra_data, approver, body.note, db)
            else:
                await _handle_upload_approval(approval, extra_data, approver, body.note, db)

            results["success"] += 1

        except Exception as e:
            results["fail"] += 1
            results["errors"].append({"id": aid, "error": str(e)})

    await db.commit()
    return results


@router.post("/batch-reject")
async def batch_reject(
    body: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """
    Reject multiple requests at once.
    """
    results = {"success": 0, "fail": 0, "errors": []}

    for aid in body.approval_ids:
        try:
            result = await db.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == aid)
            )
            approval = result.scalars().first()

            if not approval:
                results["fail"] += 1
                results["errors"].append({"id": aid, "error": "Not found"})
                continue

            if approval.status not in ("pending", "manager_approved"):
                results["fail"] += 1
                results["errors"].append({"id": aid, "error": f"Already {approval.status}"})
                continue

            approval.status = "rejected"
            approval.reviewer_id = UUID(approver["id"])
            approval.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            approval.review_note = body.note
            results["success"] += 1

        except Exception as e:
            results["fail"] += 1
            results["errors"].append({"id": aid, "error": str(e)})

    await db.commit()
    return results
