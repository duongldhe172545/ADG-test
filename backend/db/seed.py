"""
Seed data for RBAC system.
Run this after migrations to populate/sync roles, permissions, users, and departments.

This seed is IDEMPOTENT and performs FULL SYNC:
  - CREATE missing data
  - UPDATE existing data
  - DELETE stale data (roles, permissions not in definitions)
"""

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_async_session_factory
from backend.db.models import (
    Role, PermissionType, RolePermission, User, UserRole,
    Department, UserDepartment,
)


# =============================================================================
# DATA DEFINITIONS — Edit these to change what gets synced to all environments
# =============================================================================

# Roles (4 roles)
ROLES = [
    {"name": "super_admin", "description": "Quản trị hệ thống (kỹ thuật)", "priority": 100},
    {"name": "admin", "description": "Trưởng khối — quản lý tài liệu, folder, users", "priority": 90},
    {"name": "manager", "description": "Trưởng phòng — quản lý phòng mình", "priority": 70},
    {"name": "employer", "description": "Nhân viên — upload, xem tài liệu", "priority": 10},
]

# Permission types
PERMISSION_TYPES = [
    {"code": "view", "name": "View", "description": "Xem tài liệu"},
    {"code": "upload", "name": "Upload", "description": "Upload tài liệu"},
    {"code": "edit", "name": "Edit", "description": "Sửa tài liệu"},
    {"code": "delete", "name": "Delete", "description": "Xóa tài liệu"},
    {"code": "approve_step1", "name": "Approve Step 1", "description": "Duyệt bước 1 (trưởng phòng)"},
    {"code": "approve_step2", "name": "Approve Step 2", "description": "Duyệt bước 2 (trưởng khối)"},
    {"code": "manage_users", "name": "Manage Users", "description": "Quản lý users"},
    {"code": "manage_folders", "name": "Manage Folders", "description": "Quản lý folders"},
    {"code": "manage_system", "name": "Manage System", "description": "Quản lý hệ thống"},
]

# Role → permissions mapping
ROLE_PERMISSIONS = {
    "super_admin": ["manage_users", "manage_system"],
    "admin": ["view", "upload", "edit", "delete", "approve_step2", "manage_users", "manage_folders"],
    "manager": ["view", "upload", "edit", "approve_step1", "manage_folders"],
    "employer": ["view", "upload"],
}

# Departments (hierarchy) with Google Drive folder IDs
DEPARTMENTS = [
    {"name": "Khối Marketing", "description": "Marketing Division", "parent": None,
     "drive_folder_id": "1uCvrvjSeT7vOTMDx30eKYbqkqC5-zVTV", "children": [
        {"name": "MarCom", "description": "Marketing Communications",
         "drive_folder_id": "1fKk7oDiodRLyRoUqTjbKBM7Ew3rFUWZr"},
        {"name": "Product Marketing", "description": "Product Marketing Team",
         "drive_folder_id": "1IX8ak0YuU9ksO2gMidUbjKLpSd5jWHNL"},
        {"name": "Marketing Hybrid Team", "description": "Marketing Hybrid Team",
         "drive_folder_id": "1UF6-vjVQwFAT4A3bbIlJyay-ehPreOim"},
        {"name": "Growth & Performance", "description": "Growth & Performance Team",
         "drive_folder_id": "1HNUaLwOs0PIYhVw44U-_KvzDnstJjtix"},
    ]},
]

# Initial users (email → role, department)
SEED_USERS = [
    {"email": "duongldhe172545@fpt.edu.vn", "name": "Admin", "role": "super_admin", "department": None},
    {"email": "ledinhduongltn@gmail.com", "name": "Le Dinh Duong", "role": "admin", "department": "Khối Marketing"},
    {"email": "ducanh2207123@gmail.com", "name": "Nguyen Van Gay", "role": "employer", "department": "MarCom"},
]


# =============================================================================
# SYNC FUNCTIONS
# =============================================================================

async def sync_roles(session: AsyncSession):
    """Sync roles: create missing, update existing, DELETE stale."""
    desired_names = {r["name"] for r in ROLES}

    for role_data in ROLES:
        result = await session.execute(select(Role).where(Role.name == role_data["name"]))
        existing = result.scalars().first()
        if existing:
            existing.description = role_data["description"]
            existing.priority = role_data["priority"]
        else:
            session.add(Role(**role_data))
            print(f"  ✅ Created role: {role_data['name']}")

    # DELETE stale roles
    all_roles = (await session.execute(select(Role))).scalars().all()
    for role in all_roles:
        if role.name not in desired_names:
            await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
            await session.execute(delete(UserRole).where(UserRole.role_id == role.id))
            await session.delete(role)
            print(f"  🗑️ Deleted role: {role.name}")

    await session.commit()
    print("  📋 Roles synced")


async def sync_permission_types(session: AsyncSession):
    """Sync permission types: create missing, update existing, DELETE stale."""
    desired_codes = {pt["code"] for pt in PERMISSION_TYPES}

    for pt_data in PERMISSION_TYPES:
        result = await session.execute(select(PermissionType).where(PermissionType.code == pt_data["code"]))
        existing = result.scalars().first()
        if existing:
            existing.name = pt_data["name"]
            existing.description = pt_data["description"]
        else:
            session.add(PermissionType(**pt_data))
            print(f"  ✅ Created permission type: {pt_data['name']}")

    # DELETE stale
    all_pts = (await session.execute(select(PermissionType))).scalars().all()
    for pt in all_pts:
        if pt.code not in desired_codes:
            await session.execute(delete(RolePermission).where(RolePermission.permission_type_id == pt.id))
            await session.delete(pt)
            print(f"  🗑️ Deleted permission type: {pt.name}")

    await session.commit()
    print("  📋 Permission types synced")


async def sync_role_permissions(session: AsyncSession):
    """Sync role-permission mappings: add missing, remove extra."""
    roles = {r.name: r for r in (await session.execute(select(Role))).scalars().all()}
    perms = {p.code: p for p in (await session.execute(select(PermissionType))).scalars().all()}

    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        role = roles.get(role_name)
        if not role:
            continue
        existing = await session.execute(select(RolePermission).where(RolePermission.role_id == role.id))
        existing_perm_ids = {rp.permission_type_id for rp in existing.scalars().all()}
        desired_perm_ids = {perms[code].id for code in perm_codes if code in perms}

        for perm_id in desired_perm_ids - existing_perm_ids:
            session.add(RolePermission(role_id=role.id, permission_type_id=perm_id))
        for perm_id in existing_perm_ids - desired_perm_ids:
            await session.execute(delete(RolePermission).where(
                RolePermission.role_id == role.id, RolePermission.permission_type_id == perm_id,
            ))

    await session.commit()
    print("  📋 Role permissions synced")


async def sync_departments(session: AsyncSession):
    """Sync departments: create missing hierarchy."""
    for dept_group in DEPARTMENTS:
        # Parent department
        result = await session.execute(select(Department).where(Department.name == dept_group["name"]))
        parent = result.scalars().first()
        if not parent:
            parent = Department(
                name=dept_group["name"],
                description=dept_group.get("description"),
                drive_folder_id=dept_group.get("drive_folder_id"),
            )
            session.add(parent)
            await session.commit()
            print(f"  ✅ Created department: {dept_group['name']}")
        else:
            # Always sync drive_folder_id
            if dept_group.get("drive_folder_id"):
                parent.drive_folder_id = dept_group["drive_folder_id"]

        # Children
        for child_data in dept_group.get("children", []):
            result = await session.execute(select(Department).where(Department.name == child_data["name"]))
            child = result.scalars().first()
            if not child:
                child = Department(
                    name=child_data["name"],
                    description=child_data.get("description"),
                    parent_id=parent.id,
                    drive_folder_id=child_data.get("drive_folder_id"),
                )
                session.add(child)
                print(f"  ✅ Created department: {child_data['name']} (under {dept_group['name']})")
            else:
                # Always sync drive_folder_id
                if child_data.get("drive_folder_id"):
                    child.drive_folder_id = child_data["drive_folder_id"]

    await session.commit()
    print("  📋 Departments synced")


async def sync_users(session: AsyncSession):
    """Sync seed users: create missing, set role and department."""
    roles = {r.name: r for r in (await session.execute(select(Role))).scalars().all()}
    depts = {d.name: d for d in (await session.execute(select(Department))).scalars().all()}

    for user_data in SEED_USERS:
        email = user_data["email"]
        role_name = user_data["role"]

        # Find or create user
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user:
            user = User(email=email, name=user_data.get("name", email.split("@")[0]), is_active=True)
            session.add(user)
            await session.commit()
            print(f"  ✅ Created user: {email}")

        # Set role (single role per user in new system)
        role = roles.get(role_name)
        if role:
            result = await session.execute(select(UserRole).where(UserRole.user_id == user.id))
            current_roles = {ur.role_id for ur in result.scalars().all()}

            if role.id not in current_roles or len(current_roles) > 1:
                await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
                session.add(UserRole(user_id=user.id, role_id=role.id))
                await session.commit()
                print(f"  ✅ Set role '{role_name}' for {email}")

        # Set department
        dept_name = user_data.get("department")
        if dept_name:
            dept = depts.get(dept_name)
            if dept:
                result = await session.execute(select(UserDepartment).where(
                    UserDepartment.user_id == user.id, UserDepartment.department_id == dept.id,
                ))
                if not result.scalars().first():
                    is_head = role_name == "manager"
                    session.add(UserDepartment(user_id=user.id, department_id=dept.id, is_head=is_head))
                    await session.commit()
                    print(f"  ✅ Assigned {email} to {dept_name}")

    print("  📋 Users synced")


async def run_seed():
    """Run all sync operations."""
    print("🌱 Starting database seed/sync...")

    AsyncSessionLocal = get_async_session_factory()

    async with AsyncSessionLocal() as session:
        await sync_roles(session)
        await sync_permission_types(session)
        await sync_role_permissions(session)
        await sync_departments(session)
        await sync_users(session)

    print("🌱 Seed/sync complete!")


if __name__ == "__main__":
    asyncio.run(run_seed())
