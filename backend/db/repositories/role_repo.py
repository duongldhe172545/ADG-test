"""
Role Repository - Database operations for roles and permissions
"""

from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    Role, PermissionType, RolePermission, UserRole,
    Permission, Resource
)


class RoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_permission_type_by_code(self, code: str) -> Optional[PermissionType]:
        """Get permission type by its code"""
        result = await self.db.execute(
            select(PermissionType).where(PermissionType.code == code)
        )
        return result.scalars().first()

    async def check_resource_permission(
        self,
        user_id,
        perm_type_id,
        resource_type: str,
        resource_id: str,
    ) -> Optional[bool]:
        """
        Check if user has explicit permission on a resource.
        Returns True (granted), False (denied), or None (no explicit permission).
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(perm_type_id, str):
            perm_type_id = UUID(perm_type_id)

        # Find the resource
        res_result = await self.db.execute(
            select(Resource).where(
                Resource.resource_type == resource_type,
                Resource.resource_id == resource_id,
            )
        )
        resource = res_result.scalars().first()
        if not resource:
            return None

        # Check explicit permission
        perm_result = await self.db.execute(
            select(Permission).where(
                Permission.user_id == user_id,
                Permission.resource_id == resource.id,
                Permission.permission_type_id == perm_type_id,
            )
        )
        perm = perm_result.scalars().first()

        if perm:
            return perm.is_granted

        # Check parent resource (inheritance)
        if resource.parent_id:
            parent_result = await self.db.execute(
                select(Resource).where(Resource.id == resource.parent_id)
            )
            parent = parent_result.scalars().first()
            if parent:
                return await self.check_resource_permission(
                    user_id, perm_type_id,
                    parent.resource_type, parent.resource_id,
                )

        return None

    async def check_role_has_permission(
        self,
        user_id,
        perm_type_id,
    ) -> bool:
        """Check if any of user's roles grant this permission"""
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(perm_type_id, str):
            perm_type_id = UUID(perm_type_id)

        result = await self.db.execute(
            select(RolePermission)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.user_id == user_id,
                RolePermission.permission_type_id == perm_type_id,
            )
        )
        return result.scalars().first() is not None
