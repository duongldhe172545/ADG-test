"""
Seed data for RBAC system.
Run this after migrations to populate default roles and permission types.
"""

import asyncio
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.connection import get_async_session_factory
from backend.db.models import Role, PermissionType


# =============================================================================
# Default Roles
# =============================================================================
DEFAULT_ROLES = [
    {"name": "super_admin", "description": "Full system access", "priority": 100},
    {"name": "admin", "description": "Manage users, approve, edit, view", "priority": 90},
    {"name": "approver", "description": "Approve documents, view", "priority": 70},
    {"name": "editor", "description": "Upload, edit, view", "priority": 50},
    {"name": "viewer", "description": "View only", "priority": 10},
]


# =============================================================================
# Default Permission Types
# =============================================================================
DEFAULT_PERMISSION_TYPES = [
    {"code": "view", "name": "View", "description": "View documents and notebooks"},
    {"code": "upload", "name": "Upload", "description": "Upload new documents"},
    {"code": "edit", "name": "Edit", "description": "Edit existing documents"},
    {"code": "delete", "name": "Delete", "description": "Delete documents"},
    {"code": "approve", "name": "Approve", "description": "Approve pending documents"},
    {"code": "manage_users", "name": "Manage Users", "description": "Add/edit/deactivate users"},
    {"code": "manage_permissions", "name": "Manage Permissions", "description": "Assign permissions"},
]


# =============================================================================
# Role -> Permission Mappings
# =============================================================================
ROLE_PERMISSIONS = {
    "super_admin": ["view", "upload", "edit", "delete", "approve", "manage_users", "manage_permissions"],
    "admin": ["view", "upload", "edit", "delete", "approve", "manage_users"],
    "approver": ["view", "approve"],
    "editor": ["view", "upload", "edit"],
    "viewer": ["view"],
}


async def seed_roles_and_permissions():
    """Seed default roles and permission types"""
    AsyncSessionLocal = get_async_session_factory()
    
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        from sqlalchemy import select
        
        existing_roles = await session.execute(select(Role))
        if existing_roles.scalars().first():
            print("⚠️ Roles already exist, skipping seed")
            return
        
        # Create permission types
        permission_map = {}
        for pt_data in DEFAULT_PERMISSION_TYPES:
            pt = PermissionType(**pt_data)
            session.add(pt)
            permission_map[pt_data["code"]] = pt
        
        # Create roles
        role_map = {}
        for role_data in DEFAULT_ROLES:
            role = Role(**role_data)
            session.add(role)
            role_map[role_data["name"]] = role
        
        await session.commit()
        
        # Create role-permission mappings
        from backend.db.models import RolePermission
        
        for role_name, perm_codes in ROLE_PERMISSIONS.items():
            role = role_map[role_name]
            for perm_code in perm_codes:
                pt = permission_map[perm_code]
                rp = RolePermission(role_id=role.id, permission_type_id=pt.id)
                session.add(rp)
        
        await session.commit()
        print("✅ Seeded default roles and permission types")


async def create_initial_admin(email: str, name: str = None):
    """Create the first admin user"""
    from sqlalchemy import select
    from backend.db.models import User, UserRole
    
    AsyncSessionLocal = get_async_session_factory()
    
    async with AsyncSessionLocal() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if user:
            print(f"⚠️ User {email} already exists")
            return user
        
        # Get super_admin role
        result = await session.execute(select(Role).where(Role.name == "super_admin"))
        admin_role = result.scalars().first()
        
        if not admin_role:
            print("❌ super_admin role not found. Run seed_roles_and_permissions first.")
            return None
        
        # Create user
        user = User(email=email, name=name or email.split("@")[0], is_active=True)
        session.add(user)
        await session.commit()
        
        # Assign super_admin role
        user_role = UserRole(user_id=user.id, role_id=admin_role.id)
        session.add(user_role)
        await session.commit()
        
        print(f"✅ Created admin user: {email}")
        return user


if __name__ == "__main__":
    import sys
    
    async def main():
        await seed_roles_and_permissions()
        
        # If email provided as argument, create admin
        if len(sys.argv) > 1:
            email = sys.argv[1]
            name = sys.argv[2] if len(sys.argv) > 2 else None
            await create_initial_admin(email, name)
    
    asyncio.run(main())
