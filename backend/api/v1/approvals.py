"""
Approval Workflow API
Upload to pending folder → Admin approves → Move to target folder
"""

from uuid import UUID
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import ApprovalRequest, Resource, User
from backend.services.permission_service import get_current_user
from backend.config import settings

router = APIRouter(prefix="/approvals", tags=["Approval Workflow"])


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
    import tempfile, shutil, os
    from backend.api.v1.documents import get_gdrive_service
    
    pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID
    if not pending_folder_id:
        raise HTTPException(status_code=500, detail="Pending folder not configured")
    
    tmp_path = None
    try:
        # Read file content first (async), then save to temp
        file_content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        file_size = len(file_content)
        
        # Upload to pending folder using correct API
        gdrive = get_gdrive_service()
        uploaded_file = gdrive.upload_file(
            file_path=tmp_path,
            parent_id=pending_folder_id,
            mime_type=file.content_type,
            custom_name=file.filename,
        )
        
        # Create approval request
        approval = ApprovalRequest(
            requester_id=UUID(current_user["id"]),
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
        await db.commit()
        
        return {
            "success": True,
            "approval_id": str(approval.id),
            "message": f"File '{file.filename}' submitted for approval",
            "status": "pending",
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass  # Windows may lock the file briefly


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
    import tempfile, os
    from backend.api.v1.documents import get_gdrive_service

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

        approval = ApprovalRequest(
            requester_id=UUID(current_user["id"]),
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
        await db.commit()

        return {
            "success": True,
            "approval_id": str(approval.id),
            "message": f"Update '{file.filename}' (replacing '{replace_file_name}') submitted for approval",
            "status": "pending",
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# =============================================================================
# Preview File (Admin only — shares file and returns embed URL)
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
        from backend.api.v1.documents import get_gdrive_service
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
        # Create approval request for deletion
        approval = ApprovalRequest(
            requester_id=UUID(current_user["id"]),
            action_type="delete",
            status="pending",
            extra_data={
                "file_id": file_id,
                "file_name": file_name,
            }
        )
        db.add(approval)
        await db.commit()
        
        return {
            "success": True,
            "approval_id": str(approval.id),
            "message": f"Delete request for '{file_name}' submitted for approval",
            "status": "pending",
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Submit delete request failed: {str(e)}")


# =============================================================================
# Approval Queue (Admin)
# =============================================================================

async def require_approver(current_user: dict = Depends(get_current_user)):
    """Ensure user has approve permission"""
    if not any(r in ["admin", "super_admin", "approver", "manager"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Approver access required")
    return current_user


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
    
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status.in_(statuses))
        .order_by(ApprovalRequest.created_at.desc())
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


@router.get("/my-requests")
async def list_my_requests(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's own approval requests (for editors to track status)"""
    from uuid import UUID as PyUUID
    user_id = PyUUID(current_user["id"])
    
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
# Approve / Reject
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
        
        # If admin approves directly (skip manager step), go straight to full approval
        if is_admin and not is_manager:
            pass  # Fall through to full approval logic below
        else:
            # Manager Step 1: mark as manager_approved, don't move file yet
            approval.status = "manager_approved"
            approval.reviewer_id = UUID(approver["id"])
            approval.reviewed_at = datetime.utcnow()
            approval.review_note = note or "Manager approved (Step 1)"
            await db.commit()
            return {
                "success": True,
                "message": f"✅ Manager đã duyệt (Bước 1). Chờ Admin duyệt (Bước 2).",
                "status": "manager_approved",
            }
    
    # Step 2: Admin approves manager_approved → approved (file moves)
    if approval.status == "manager_approved":
        if not is_admin:
            raise HTTPException(status_code=403, detail="Admin approval required for Step 2")
    
    extra_data = approval.extra_data or {}
    file_id = extra_data.get("file_id")
    action_type = approval.action_type or "upload"
    
    # Handle delete approval
    if action_type == "delete":
        try:
            from backend.api.v1.documents import get_gdrive_service
            gdrive = get_gdrive_service()
            
            file_name = extra_data.get("file_name", "Unknown")
            
            # Delete from Google Drive
            gdrive.delete_file(file_id)
            print(f"🗑️ [Approval] Deleted file: {file_id} ({file_name})")
            
            # Update approval record
            approval.status = "approved"
            approval.reviewer_id = UUID(approver["id"])
            approval.reviewed_at = datetime.utcnow()
            approval.review_note = note
            
            await db.commit()
            
            return {
                "success": True,
                "message": f"File '{file_name}' has been deleted",
                "file_id": file_id,
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Delete approval failed: {str(e)}")
    
    # Handle update approval (move old → _OLD, move new → target)
    if action_type == "update":
        replace_file_id = extra_data.get("replace_file_id")
        target_folder_id = extra_data.get("target_folder_id")
        change_note = extra_data.get("change_note", "")

        if not file_id or not target_folder_id or not replace_file_id:
            raise HTTPException(status_code=400, detail="Missing file, target folder, or replace file info")

        try:
            from backend.api.v1.documents import get_gdrive_service
            from backend.db.repositories.document_repo import DocumentRepository
            gdrive = get_gdrive_service()
            pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID

            # 1. Find or create _OLD subfolder in target folder
            old_query = gdrive.service.files().list(
                q=f"name='_OLD' and '{target_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id)"
            ).execute()
            old_files = old_query.get("files", [])

            if old_files:
                old_folder_id = old_files[0]["id"]
            else:
                old_folder_meta = {
                    "name": "_OLD",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [target_folder_id],
                }
                old_folder = gdrive.service.files().create(body=old_folder_meta, fields="id").execute()
                old_folder_id = old_folder["id"]

            # 2. Move old file to _OLD/
            old_file_info = gdrive.service.files().get(fileId=replace_file_id, fields="parents").execute()
            old_parents = ",".join(old_file_info.get("parents", []))
            gdrive.service.files().update(
                fileId=replace_file_id,
                addParents=old_folder_id,
                removeParents=old_parents,
                fields="id, name"
            ).execute()

            # 3. Move new file from _PENDING to target folder
            move_result = gdrive.service.files().update(
                fileId=file_id,
                addParents=target_folder_id,
                removeParents=pending_folder_id,
                fields="id, parents, name, mimeType"
            ).execute()

            file_name = move_result.get("name", extra_data.get("file_name", ""))

            # 4. Track in documents table
            doc_repo = DocumentRepository(db)
            existing_doc = await doc_repo.get_by_drive_id(replace_file_id)
            if existing_doc:
                await doc_repo.update_version(
                    drive_file_id=replace_file_id,
                    new_drive_file_id=file_id,
                    new_file_name=file_name,
                    change_note=change_note,
                    uploaded_by=approval.requester_id,
                    approved_by=UUID(approver["id"]),
                )
            else:
                await doc_repo.create(
                    drive_file_id=file_id,
                    file_name=file_name,
                    mime_type=extra_data.get("mime_type"),
                    file_size=extra_data.get("file_size"),
                    folder_id=target_folder_id,
                    folder_path=extra_data.get("target_folder_name", ""),
                    version=2,
                    old_drive_id=replace_file_id,
                    change_note=change_note,
                    uploaded_by=approval.requester_id,
                    approved_by=UUID(approver["id"]),
                    approved_at=datetime.utcnow(),
                )

            # 5. Update approval record
            approval.status = "approved"
            approval.reviewer_id = UUID(approver["id"])
            approval.reviewed_at = datetime.utcnow()
            approval.review_note = note

            await db.commit()

            return {
                "success": True,
                "message": f"File '{file_name}' updated (old version moved to _OLD/)",
                "file_id": file_id,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Update approval failed: {str(e)}")

    # Handle upload approval (existing flow)
    target_folder_id = extra_data.get("target_folder_id")
    
    if not file_id or not target_folder_id:
        raise HTTPException(status_code=400, detail="Missing file or target folder info")
    
    try:
        # Move file from pending to target folder
        from backend.api.v1.documents import get_gdrive_service
        from backend.db.repositories.document_repo import DocumentRepository
        gdrive = get_gdrive_service()
        
        pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID
        
        move_result = gdrive.service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=pending_folder_id,
            fields="id, parents, name, mimeType, webViewLink"
        ).execute()
        
        file_name = move_result.get("name", extra_data.get("file_name", ""))
        
        # Track in documents table
        doc_repo = DocumentRepository(db)
        await doc_repo.create(
            drive_file_id=file_id,
            file_name=file_name,
            mime_type=extra_data.get("mime_type"),
            file_size=extra_data.get("file_size"),
            folder_id=target_folder_id,
            folder_path=extra_data.get("target_folder_name", ""),
            uploaded_by=approval.requester_id,
            approved_by=UUID(approver["id"]),
            approved_at=datetime.utcnow(),
        )

        # Update approval record
        approval.status = "approved"
        approval.reviewer_id = UUID(approver["id"])
        approval.reviewed_at = datetime.utcnow()
        approval.review_note = note
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"File '{file_name}' approved and moved to target folder",
            "file_id": file_id,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


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
    approval.reviewed_at = datetime.utcnow()
    approval.review_note = note
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Request rejected",
        "review_note": note,
    }
