"""
JWT Authentication Service for RBAC
Handles JWT token creation/validation and user whitelist checking.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.db.models import User, UserRole, Role, RolePermission, PermissionType


# =============================================================================
# JWT Token Management
# =============================================================================

def create_access_token(user_id: str, email: str, roles: list[str]) -> str:
    """Create JWT access token"""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "roles": roles,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


# =============================================================================
# User Whitelist & Login
# =============================================================================

async def check_whitelist(db: AsyncSession, email: str) -> Optional[User]:
    """
    Check if email is in whitelist (users table).
    Returns User if whitelisted and active, None otherwise.
    """
    result = await db.execute(
        select(User).where(User.email == email, User.is_active == True)
    )
    return result.scalars().first()


async def get_user_roles(db: AsyncSession, user_id: UUID) -> list[str]:
    """Get all role names for a user"""
    result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def get_user_with_roles(db: AsyncSession, user_id: UUID) -> Optional[dict]:
    """Get user with their roles"""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()
    if not user:
        return None
    
    roles = await get_user_roles(db, user.id)
    
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "roles": roles,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


async def login_user(db: AsyncSession, email: str, name: str = None, avatar_url: str = None) -> Optional[dict]:
    """
    Process user login:
    1. Check whitelist
    2. Update last_login and user info
    3. Generate JWT token
    
    Returns dict with token and user info, or None if not whitelisted.
    """
    user = await check_whitelist(db, email)
    
    if not user:
        return None
    
    # Update user info from Google
    user.last_login = datetime.utcnow()
    if name and not user.name:
        user.name = name
    if avatar_url:
        user.avatar_url = avatar_url
    
    await db.commit()
    
    # Get roles
    roles = await get_user_roles(db, user.id)
    
    # Generate JWT
    token = create_access_token(str(user.id), user.email, roles)
    
    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "roles": roles,
        }
    }


async def get_role_permissions(db: AsyncSession, role_names: list[str]) -> list[str]:
    """Get all permission codes for given roles"""
    result = await db.execute(
        select(PermissionType.code)
        .distinct()
        .join(RolePermission, RolePermission.permission_type_id == PermissionType.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name.in_(role_names))
    )
    return [row[0] for row in result.all()]
