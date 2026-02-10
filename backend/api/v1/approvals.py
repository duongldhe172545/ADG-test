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
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# =============================================================================
# Approval Queue (Admin)
# =============================================================================

async def require_approver(current_user: dict = Depends(get_current_user)):
    """Ensure user has approve permission"""
    if not any(r in ["admin", "super_admin", "approver"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Approver access required")
    return current_user


@router.get("/pending")
async def list_pending(
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """List all pending approval requests"""
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at.desc())
    )
    requests = result.scalars().all()
    
    items = []
    for req in requests:
        # Get requester info
        user_result = await db.execute(select(User).where(User.id == req.requester_id))
        requester = user_result.scalars().first()
        
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
        })
    
    return {"pending": items, "count": len(items)}


@router.get("/history")
async def list_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    approver: dict = Depends(require_approver),
):
    """List approval history (approved/rejected)"""
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status.in_(["approved", "rejected"]))
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
    Approve a pending request.
    Moves file from Pending folder to target folder.
    """
    result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    approval = result.scalars().first()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {approval.status}")
    
    extra_data = approval.extra_data or {}
    file_id = extra_data.get("file_id")
    target_folder_id = extra_data.get("target_folder_id")
    
    if not file_id or not target_folder_id:
        raise HTTPException(status_code=400, detail="Missing file or target folder info")
    
    try:
        # Move file from pending to target folder
        from backend.api.v1.documents import get_gdrive_service
        gdrive = get_gdrive_service()
        
        pending_folder_id = settings.GDRIVE_PENDING_FOLDER_ID
        
        move_result = gdrive.service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=pending_folder_id,
            fields="id, parents, name, mimeType, webViewLink"
        ).execute()
        
        file_name = move_result.get("name", extra_data.get("file_name", ""))
        file_mime = move_result.get("mimeType", "application/pdf")
        
        # Share file publicly so NotebookLM can access it
        try:
            gdrive.share_file_public(file_id)
            print(f"🔓 Shared file publicly: {file_id}")
        except Exception as share_err:
            print(f"⚠️ Could not share file publicly: {share_err}")
        
        # Sync to NotebookLM (matching direct upload logic)
        notebook_sync_result = None
        try:
            from backend.config.folder_notebook_mapping import FOLDER_NOTEBOOK_MAPPING
            from backend.services.notebooklm_service import get_notebooklm_service
            
            print(f"🔍 [Approval] Checking NotebookLM sync for folder: {target_folder_id}")
            
            # Check if target folder is mapped
            notebook_id = FOLDER_NOTEBOOK_MAPPING.get(target_folder_id)
            
            # If not directly mapped, try parent folders
            if not notebook_id:
                try:
                    folder_info = gdrive.service.files().get(
                        fileId=target_folder_id,
                        fields='parents'
                    ).execute()
                    
                    for parent_id in folder_info.get('parents', []):
                        notebook_id = FOLDER_NOTEBOOK_MAPPING.get(parent_id)
                        if notebook_id:
                            print(f"✅ Found parent mapping: {parent_id} -> {notebook_id}")
                            break
                        
                        # Also check grandparent (2 levels deep)
                        try:
                            gp_info = gdrive.service.files().get(
                                fileId=parent_id,
                                fields='parents'
                            ).execute()
                            for gp_id in gp_info.get('parents', []):
                                notebook_id = FOLDER_NOTEBOOK_MAPPING.get(gp_id)
                                if notebook_id:
                                    print(f"✅ Found grandparent mapping: {gp_id} -> {notebook_id}")
                                    break
                            if notebook_id:
                                break
                        except Exception:
                            pass
                except Exception as e:
                    print(f"⚠️ Could not traverse parent folders: {e}")
            
            if notebook_id and file_id:
                print(f"🚀 [Approval] Syncing to notebook: {notebook_id}")
                notebooklm = get_notebooklm_service()
                notebook_sync_result = await notebooklm.add_drive_source(
                    notebook_id=notebook_id,
                    document_id=file_id,
                    title=file_name,
                    mime_type=file_mime
                )
                print(f"📚 [Approval] NotebookLM sync: {notebook_sync_result}")
            else:
                print(f"⏭️ No mapping found for folder {target_folder_id}, skipping NotebookLM sync")
        except ImportError as ie:
            print(f"⚠️ Folder mapping not configured: {ie}")
        except Exception as sync_error:
            print(f"⚠️ NotebookLM sync error (non-blocking): {sync_error}")
        
        # Update approval record
        approval.status = "approved"
        approval.reviewer_id = UUID(approver["id"])
        approval.reviewed_at = datetime.utcnow()
        approval.review_note = note
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"File '{file_name}' approved, moved, and synced to NotebookLM",
            "file_id": file_id,
            "notebook_sync": notebook_sync_result,
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
    if approval.status != "pending":
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
