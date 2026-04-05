"""
Admin API - User Management
User CRUD, role assignment, department assignment, and combined page-data endpoint.
"""

import math
from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_db
from backend.db.models import (
    User, Role, UserRole, PermissionType, Resource, Permission,
    UserDepartment, Department,
)
from backend.services.permission_service import get_current_user
from backend.services.auth_service import get_user_roles
from backend.services.activity_service import log_activity
from backend.services.notification_service import create_notification

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Request/Response Models
# =============================================================================

class AddUserRequest(BaseModel):
    email: str
    name: Optional[str] = None
    roles: List[str] = ["employer"]  # Default role (single role only)
    department_id: Optional[str] = None  # UUID of department

    @property
    def validated_roles(self):
        if len(self.roles) > 1:
            raise ValueError("Each user can only have 1 role")
        return self.roles

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[List[str]] = None  # Single role only
    department_id: Optional[str] = None  # UUID of department, or "" to clear

class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    is_active: bool
    roles: List[str]
    last_login: Optional[str]
    created_at: str


# =============================================================================
# Admin Guards (shared across admin modules)
# =============================================================================

async def require_admin(current_user: dict = Depends(get_current_user)):
    """Ensure current user is admin or super_admin"""
    if not any(r in ["admin", "super_admin"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def require_admin_or_manager(current_user: dict = Depends(get_current_user)):
    """Ensure current user is admin, super_admin, or manager"""
    if not any(r in ["admin", "super_admin", "manager"] for r in current_user.get("roles", [])):
        raise HTTPException(status_code=403, detail="Admin or Manager access required")
    return current_user


# =============================================================================
# Helpers
# =============================================================================

async def _ensure_view_permission_type(db: AsyncSession):
    """Get or create the 'view' permission type."""
    result = await db.execute(select(PermissionType).where(PermissionType.code == "view"))
    pt = result.scalars().first()
    if not pt:
        pt = PermissionType(code="view", name="View", description="View folder contents")
        db.add(pt)
        await db.flush()
    return pt


# =============================================================================
# User Management
# =============================================================================

@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin_or_manager)
):
    """List all users with their roles (paginated). Managers see only their department."""
    is_manager_only = (
        "manager" in admin.get("roles", [])
        and "admin" not in admin.get("roles", [])
        and "super_admin" not in admin.get("roles", [])
    )
    
    # For manager: find their department, filter users by same department
    dept_filter_user_ids = None
    if is_manager_only:
        import uuid as _uuid
        mgr_id = _uuid.UUID(admin["id"]) if isinstance(admin["id"], str) else admin["id"]
        mgr_dept = await db.execute(
            select(UserDepartment.department_id).where(UserDepartment.user_id == mgr_id)
        )
        mgr_dept_id = mgr_dept.scalar()
        if mgr_dept_id:
            dept_users = await db.execute(
                select(UserDepartment.user_id).where(UserDepartment.department_id == mgr_dept_id)
            )
            dept_filter_user_ids = [r[0] for r in dept_users.all()]
        else:
            # Manager not in any department -> show only themselves
            dept_filter_user_ids = [mgr_id]
    
    # Build query
    query = select(User)
    if dept_filter_user_ids is not None:
        query = query.where(User.id.in_(dept_filter_user_ids))
    
    # Count total users
    count_q = select(func.count(User.id))
    if dept_filter_user_ids is not None:
        count_q = count_q.where(User.id.in_(dept_filter_user_ids))
    count_result = await db.execute(count_q)
    total = count_result.scalar()
    
    # Paginate
    offset = (max(1, page) - 1) * page_size
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()
    
    user_list = []
    for user in users:
        # Get roles
        role_result = await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
        roles = [r[0] for r in role_result.all()]
        
        # Get department
        dept_result = await db.execute(
            select(Department.id, Department.name).join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(UserDepartment.user_id == user.id)
        )
        dept_row = dept_result.first()
        
        user_list.append({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "roles": roles,
            "department": dept_row[1] if dept_row else None,
            "department_id": str(dept_row[0]) if dept_row else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat(),
        })
    
    return {
        "users": user_list,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 1,
    }


@router.post("/users")
async def add_user(
    req: AddUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Add a new user to the whitelist"""
    # Check if user already exists
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Create user
    user = User(email=req.email, name=req.name, is_active=True)
    db.add(user)
    await db.flush()
    
    # Validate single role
    if len(req.roles) > 1:
        raise HTTPException(status_code=400, detail="Each user can only have 1 role")

    # Assign role
    for role_name in req.roles:
        role_result = await db.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalars().first()
        if role:
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db.add(user_role)
    
    # Assign department if provided
    if req.department_id:
        dept_result = await db.execute(select(Department).where(Department.id == req.department_id))
        dept = dept_result.scalars().first()
        if dept:
            ud = UserDepartment(user_id=user.id, department_id=dept.id)
            db.add(ud)
            # Auto-grant view permission to dept's drive folder
            if dept.drive_folder_id:
                await _ensure_view_permission_type(db)
                pt_result = await db.execute(select(PermissionType).where(PermissionType.code == "view"))
                view_pt = pt_result.scalars().first()
                if view_pt:
                    res_result = await db.execute(
                        select(Resource).where(
                            Resource.resource_id == dept.drive_folder_id,
                            Resource.resource_type == "folder"
                        )
                    )
                    resource = res_result.scalars().first()
                    if resource:
                        perm = Permission(
                            user_id=user.id,
                            resource_id=resource.id,
                            permission_type_id=view_pt.id,
                            is_granted=True
                        )
                        db.add(perm)
    
    await db.commit()
    
    return {"success": True, "user_id": str(user.id), "message": f"User {req.email} added"}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Update user info or roles"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get target user's current roles
    target_roles = await get_user_roles(db, user.id)
    is_target_sa = "super_admin" in target_roles
    is_caller_sa = "super_admin" in admin.get("roles", [])
    
    # Super Admin users cannot be modified by non-super_admin
    if is_target_sa and not is_caller_sa:
        raise HTTPException(status_code=403, detail="Không được phép chỉnh sửa Super Admin")
    
    # Super Admin's role cannot be changed by anyone
    if is_target_sa and req.roles is not None:
        raise HTTPException(status_code=403, detail="Không được đổi role của Super Admin")
    
    # Update basic info
    if req.name is not None:
        user.name = req.name
    if req.is_active is not None:
        user.is_active = req.is_active
    
    # Update roles if provided (single role only)
    if req.roles is not None:
        if len(req.roles) > 1:
            raise HTTPException(status_code=400, detail="Each user can only have 1 role")

        # Cannot assign super_admin role
        if "super_admin" in req.roles:
            raise HTTPException(status_code=403, detail="Không được gán role super_admin")

        # Remove existing roles
        await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
        
        # Add new role
        new_is_admin = any(r in ["admin", "super_admin"] for r in req.roles)
        for role_name in req.roles:
            role_result = await db.execute(select(Role).where(Role.name == role_name))
            role = role_result.scalars().first()
            if role:
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db.add(user_role)
        
        # When role changes: clear ALL folder permissions
        # Then re-grant only the department folder permission
        view_pt = await _ensure_view_permission_type(db)
        await db.execute(
            delete(Permission).where(
                Permission.user_id == user.id,
                Permission.permission_type_id == view_pt.id,
            )
        )
        
        # Re-grant department folder permission (unless new role is admin)
        if not new_is_admin:
            dept_result = await db.execute(
                select(Department).join(UserDepartment, UserDepartment.department_id == Department.id)
                .where(UserDepartment.user_id == user.id)
            )
            user_dept = dept_result.scalars().first()
            if user_dept and user_dept.drive_folder_id:
                res_result = await db.execute(
                    select(Resource).where(
                        Resource.resource_type == "folder",
                        Resource.resource_id == user_dept.drive_folder_id,
                    )
                )
                res = res_result.scalars().first()
                if res:
                    perm = Permission(
                        user_id=user.id,
                        resource_id=res.id,
                        permission_type_id=view_pt.id,
                        is_granted=True,
                    )
                    db.add(perm)
    
    # Update department if provided (with auto folder permissions)
    if req.department_id is not None:
        
        # Get OLD department's drive_folder_id (to remove permission)
        old_dept_result = await db.execute(
            select(Department).join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(UserDepartment.user_id == user.id)
        )
        old_dept = old_dept_result.scalars().first()
        
        # Remove old dept folder permission if exists
        if old_dept and old_dept.drive_folder_id:
            old_resource = await db.execute(
                select(Resource).where(
                    Resource.resource_type == "folder",
                    Resource.resource_id == old_dept.drive_folder_id,
                )
            )
            old_res = old_resource.scalars().first()
            if old_res:
                view_pt = await _ensure_view_permission_type(db)
                await db.execute(
                    delete(Permission).where(
                        Permission.user_id == user.id,
                        Permission.resource_id == old_res.id,
                        Permission.permission_type_id == view_pt.id,
                    )
                )
        
        # Remove existing department assignments
        await db.execute(delete(UserDepartment).where(UserDepartment.user_id == user.id))
        
        # Assign new department (if not empty)
        if req.department_id:
            dept_result = await db.execute(select(Department).where(Department.id == req.department_id))
            dept = dept_result.scalars().first()
            if dept:
                ud = UserDepartment(user_id=user.id, department_id=dept.id)
                db.add(ud)
                
                # Auto-add new dept folder permission
                if dept.drive_folder_id:
                    new_resource = await db.execute(
                        select(Resource).where(
                            Resource.resource_type == "folder",
                            Resource.resource_id == dept.drive_folder_id,
                        )
                    )
                    new_res = new_resource.scalars().first()
                    if new_res:
                        view_pt = await _ensure_view_permission_type(db)
                        # Check if permission already exists
                        existing_perm = await db.execute(
                            select(Permission).where(
                                Permission.user_id == user.id,
                                Permission.resource_id == new_res.id,
                                Permission.permission_type_id == view_pt.id,
                            )
                        )
                        if not existing_perm.scalars().first():
                            perm = Permission(
                                user_id=user.id,
                                resource_id=new_res.id,
                                permission_type_id=view_pt.id,
                                is_granted=True,
                            )
                            db.add(perm)
    
    await db.commit()
    
    # Log activity + notify
    try:
        details = {}
        if req.roles is not None:
            details["roles"] = req.roles
            await log_activity(db, admin["id"], admin["email"], "user.role_change",
                               target_type="user", target_id=str(user.id),
                               details={"target_email": user.email, "new_roles": req.roles})
            await create_notification(db, user.id, "🔄 Role đã thay đổi",
                f"Vai trò của bạn đã được cập nhật thành: {', '.join(req.roles)}",
                "role_changed", link="/dashboard")
        if req.department_id is not None:
            await log_activity(db, admin["id"], admin["email"], "user.dept_change",
                               target_type="user", target_id=str(user.id),
                               details={"target_email": user.email, "dept_id": str(req.department_id)})
    except Exception:
        pass
    
    return {"success": True, "message": f"User {user.email} updated"}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Deactivate user (soft delete)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if target is super_admin
    target_roles = await get_user_roles(db, user.id)
    if "super_admin" in target_roles:
        raise HTTPException(status_code=403, detail="Không được vô hiệu Super Admin")
    
    user.is_active = False
    await db.commit()
    
    return {"success": True, "message": f"User {user.email} deactivated"}


# =============================================================================
# Combined Page Data
# =============================================================================

@router.get("/page-data/users")
async def users_page_data(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Combined endpoint: returns users + roles + departments in one response.
    Reduces 3 API calls to 1, saving ~360ms on production.
    Supports pagination via page/page_size query params.
    """
    
    # Count total users
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar()
    
    # Paginate users
    offset = (max(1, page) - 1) * page_size
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()
    
    user_list = []
    for user in users:
        role_result = await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
        roles = [r[0] for r in role_result.all()]
        dept_result = await db.execute(
            select(Department.id, Department.name)
            .join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(UserDepartment.user_id == user.id)
        )
        dept_row = dept_result.first()
        user_list.append({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "roles": roles,
            "department": dept_row[1] if dept_row else None,
            "department_id": str(dept_row[0]) if dept_row else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat(),
        })
    
    # Roles + Departments (not paginated)
    role_result = await db.execute(select(Role).order_by(Role.priority.desc()))
    all_roles = role_result.scalars().all()
    dept_result = await db.execute(select(Department).order_by(Department.name))
    all_depts = dept_result.scalars().all()
    
    return {
        "users": user_list,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 1,
        "roles": [{"id": str(r.id), "name": r.name, "description": r.description, "priority": r.priority} for r in all_roles],
        "departments": [{"id": str(d.id), "name": d.name, "parent_id": str(d.parent_id) if d.parent_id else None} for d in all_depts],
    }
