"""
Seed data for RBAC system.
Run this after migrations to populate/sync default roles, permissions, and users.

This seed is IDEMPOTENT — safe to run multiple times.
It will CREATE missing data, UPDATE existing data, and optionally REMOVE stale data.
"""

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_async_session_factory
from backend.db.models import Role, PermissionType, RolePermission, User, UserRole


# =============================================================================
# DATA DEFINITIONS — Edit these to change what gets synced to all environments
# =============================================================================

# Roles (name must be unique)
ROLES = [
    {"name": "super_admin", "description": "Full system access", "priority": 100},
    {"name": "admin", "description": "Manage users, approve, edit, view", "priority": 90},
    {"name": "approver", "description": "Approve documents, view", "priority": 70},
    {"name": "editor", "description": "Upload, edit, view", "priority": 50},
    {"name": "viewer", "description": "View only", "priority": 10},
]

# Permission types (code must be unique)
PERMISSION_TYPES = [
    {"code": "view", "name": "View", "description": "View documents and notebooks"},
    {"code": "upload", "name": "Upload", "description": "Upload new documents"},
    {"code": "edit", "name": "Edit", "description": "Edit existing documents"},
    {"code": "delete", "name": "Delete", "description": "Delete documents"},
    {"code": "approve", "name": "Approve", "description": "Approve pending documents"},
    {"code": "manage_users", "name": "Manage Users", "description": "Add/edit/deactivate users"},
    {"code": "manage_permissions", "name": "Manage Permissions", "description": "Assign permissions"},
]

# Role → permissions mapping
ROLE_PERMISSIONS = {
    "super_admin": ["view", "upload", "edit", "delete", "approve", "manage_users", "manage_permissions"],
    "admin": ["view", "upload", "edit", "delete", "approve", "manage_users"],
    "approver": ["view", "approve"],
    "editor": ["view", "upload", "edit"],
    "viewer": ["view"],
}

# Initial users to seed (email → roles)
# These users will be CREATED if they don't exist, roles will be SET/UPDATED
SEED_USERS = [
    {"email": "duongldhe172545@fpt.edu.vn", "name": "Admin", "roles": ["super_admin", "admin", "editor", "viewer"]},
    {"email": "ledinhduongltn@gmail.com", "name": "Le Dinh Duong", "roles": ["super_admin"]},
    {"email": "ducanh2207123@gmail.com", "name": "Nguyen Van gay", "roles": ["editor", "viewer"]},
]


# =============================================================================
# SYNC FUNCTIONS
# =============================================================================

async def sync_roles(session: AsyncSession):
    """Sync roles: create missing, update existing."""
    role_names = {r["name"] for r in ROLES}
    
    for role_data in ROLES:
        result = await session.execute(
            select(Role).where(Role.name == role_data["name"])
        )
        existing = result.scalars().first()
        
        if existing:
            # Update description and priority if changed
            existing.description = role_data["description"]
            existing.priority = role_data["priority"]
        else:
            session.add(Role(**role_data))
            print(f"  ✅ Created role: {role_data['name']}")
    
    await session.commit()
    print("  📋 Roles synced")


async def sync_permission_types(session: AsyncSession):
    """Sync permission types: create missing, update existing."""
    for pt_data in PERMISSION_TYPES:
        result = await session.execute(
            select(PermissionType).where(PermissionType.code == pt_data["code"])
        )
        existing = result.scalars().first()
        
        if existing:
            existing.name = pt_data["name"]
            existing.description = pt_data["description"]
        else:
            session.add(PermissionType(**pt_data))
            print(f"  ✅ Created permission type: {pt_data['name']}")
    
    await session.commit()
    print("  📋 Permission types synced")


async def sync_role_permissions(session: AsyncSession):
    """Sync role-permission mappings: add missing, remove extra."""
    # Get all roles and permission types
    roles = {r.name: r for r in (await session.execute(select(Role))).scalars().all()}
    perms = {p.code: p for p in (await session.execute(select(PermissionType))).scalars().all()}
    
    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        role = roles.get(role_name)
        if not role:
            continue
        
        # Get existing permissions for this role
        existing = await session.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        )
        existing_perm_ids = {rp.permission_type_id for rp in existing.scalars().all()}
        desired_perm_ids = {perms[code].id for code in perm_codes if code in perms}
        
        # Add missing
        for perm_id in desired_perm_ids - existing_perm_ids:
            session.add(RolePermission(role_id=role.id, permission_type_id=perm_id))
        
        # Remove extra
        for perm_id in existing_perm_ids - desired_perm_ids:
            await session.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_type_id == perm_id,
                )
            )
    
    await session.commit()
    print("  📋 Role permissions synced")


async def sync_users(session: AsyncSession):
    """Sync seed users: create missing, set exact roles."""
    roles = {r.name: r for r in (await session.execute(select(Role))).scalars().all()}
    
    for user_data in SEED_USERS:
        email = user_data["email"]
        role_names = user_data["roles"]
        
        # Find or create user
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if not user:
            user = User(email=email, name=user_data.get("name", email.split("@")[0]), is_active=True)
            session.add(user)
            await session.commit()
            print(f"  ✅ Created user: {email}")
        
        # Get desired role IDs
        desired_role_ids = set()
        for rn in role_names:
            role = roles.get(rn)
            if role:
                desired_role_ids.add(role.id)
            else:
                print(f"  ⚠️ Role '{rn}' not found for {email}")
        
        # Get current role IDs
        result = await session.execute(
            select(UserRole).where(UserRole.user_id == user.id)
        )
        current_role_ids = {ur.role_id for ur in result.scalars().all()}
        
        # Add missing roles
        for role_id in desired_role_ids - current_role_ids:
            session.add(UserRole(user_id=user.id, role_id=role_id))
        
        # Remove extra roles
        for role_id in current_role_ids - desired_role_ids:
            await session.execute(
                delete(UserRole).where(
                    UserRole.user_id == user.id,
                    UserRole.role_id == role_id,
                )
            )
        
        if desired_role_ids != current_role_ids:
            await session.commit()
            print(f"  ✅ Synced roles for {email}: {role_names}")
    
    print("  📋 Users synced")


async def run_seed():
    """Run all sync operations."""
    print("🌱 Starting database seed/sync...")
    
    AsyncSessionLocal = get_async_session_factory()
    
    async with AsyncSessionLocal() as session:
        await sync_roles(session)
        await sync_permission_types(session)
        await sync_role_permissions(session)
        await sync_users(session)
    
    print("🌱 Seed/sync complete!")


if __name__ == "__main__":
    asyncio.run(run_seed())
