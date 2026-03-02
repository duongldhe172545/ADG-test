"""
Reset database for account migration.
- Truncates user data tables (preserves roles, permission_types, role_permissions)
- Re-adds new admin user with super_admin role

Usage:
    python scripts/reset_db.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from backend.db.connection import get_async_session_factory
from backend.db.seed import seed_roles_and_permissions, create_initial_admin


NEW_ADMIN_EMAIL = "ledinhduongltn@gmail.com"


async def reset_user_data():
    """Truncate user-specific tables, keep structural tables (roles, permission_types, role_permissions)."""
    AsyncSessionLocal = get_async_session_factory()
    
    async with AsyncSessionLocal() as session:
        # Tables to clear (order matters due to FK constraints)
        tables_to_clear = [
            "chat_messages",       # FK -> chat_sessions
            "chat_sessions",       # FK -> users
            "approval_requests",   # FK -> users, resources
            "permissions",         # FK -> users, resources, permission_types
            "user_roles",          # FK -> users, roles
            "users",               # User data
            "resources",           # Resource references
        ]
        
        print("🗑️  Clearing user data tables...")
        for table in tables_to_clear:
            try:
                await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
                print(f"   ✅ {table}")
            except Exception as e:
                print(f"   ⚠️ {table}: {e}")
        
        await session.commit()
        print("\n✅ User data cleared!")
        
        # Verify structural tables are intact
        result = await session.execute(text("SELECT COUNT(*) FROM roles"))
        role_count = result.scalar()
        result = await session.execute(text("SELECT COUNT(*) FROM permission_types"))
        pt_count = result.scalar()
        result = await session.execute(text("SELECT COUNT(*) FROM role_permissions"))
        rp_count = result.scalar()
        
        print(f"\n📊 Structural data preserved:")
        print(f"   Roles: {role_count}")
        print(f"   Permission types: {pt_count}")
        print(f"   Role-permission mappings: {rp_count}")
        
        if role_count == 0:
            print("\n⚠️ Roles table is empty! Re-seeding...")
            await session.commit()
            return True  # Need to re-seed
        
        return False  # No re-seed needed


async def main():
    print("=" * 60)
    print("  ADG KMS - Database Reset for Account Migration")
    print("=" * 60)
    print(f"\n  New admin: {NEW_ADMIN_EMAIL}")
    print(f"  Keeping: roles, permission_types, role_permissions")
    print(f"  Clearing: users, user_roles, permissions, resources,")
    print(f"            approval_requests, chat_sessions, chat_messages\n")
    
    needs_reseed = await reset_user_data()
    
    if needs_reseed:
        await seed_roles_and_permissions()
    
    # Create new admin
    print(f"\n👤 Creating admin user: {NEW_ADMIN_EMAIL}")
    await create_initial_admin(NEW_ADMIN_EMAIL, "Le Dinh Duong")
    
    print("\n" + "=" * 60)
    print("  ✅ Database reset complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
