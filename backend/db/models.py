"""
RBAC Models - Users, Roles, Permissions
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, ForeignKey,
    UniqueConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from backend.db.connection import Base


# =============================================================================
# Users
# =============================================================================

class User(Base):
    """
    Whitelisted users who can login via Google OAuth.
    Admin must add users before they can login.
    """
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    avatar_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    permissions = relationship("Permission", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"


# =============================================================================
# Roles
# =============================================================================

class Role(Base):
    """
    System roles with priority.
    Higher priority roles take precedence.
    """
    __tablename__ = "roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    priority = Column(Integer, default=0, nullable=False)  # Higher = more powerful
    
    # Relationships
    user_roles = relationship("UserRole", back_populates="role")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Role {self.name}>"


class UserRole(Base):
    """
    Many-to-many: Users can have multiple roles.
    """
    __tablename__ = "user_roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")
    
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )


# =============================================================================
# Permission Types
# =============================================================================

class PermissionType(Base):
    """
    Available permission types.
    Examples: view, upload, edit, delete, approve, manage_users
    """
    __tablename__ = "permission_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    
    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission_type")
    permissions = relationship("Permission", back_populates="permission_type")
    
    def __repr__(self):
        return f"<PermissionType {self.code}>"


class RolePermission(Base):
    """
    Permissions assigned to a role.
    All users with this role get these permissions (unless overridden).
    """
    __tablename__ = "role_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_type_id = Column(UUID(as_uuid=True), ForeignKey("permission_types.id", ondelete="CASCADE"), nullable=False)
    
    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission_type = relationship("PermissionType", back_populates="role_permissions")
    
    __table_args__ = (
        UniqueConstraint("role_id", "permission_type_id", name="uq_role_permission"),
    )


# =============================================================================
# Resources (Folders, Notebooks, Documents)
# =============================================================================

class Resource(Base):
    """
    Resources that can be protected.
    Hierarchical: folders contain documents, etc.
    """
    __tablename__ = "resources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type = Column(String(50), nullable=False, index=True)  # folder, notebook, document, system
    resource_id = Column(String(255), nullable=False)  # Google Drive ID or '*' for system
    name = Column(String(255), nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    parent = relationship("Resource", remote_side=[id], backref="children")
    permissions = relationship("Permission", back_populates="resource", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_resource"),
        Index("ix_resource_type_id", "resource_type", "resource_id"),
    )
    
    def __repr__(self):
        return f"<Resource {self.resource_type}:{self.resource_id}>"


# =============================================================================
# Granular Permissions
# =============================================================================

class Permission(Base):
    """
    Granular permissions: User + Resource + PermissionType.
    Can explicitly grant or deny.
    """
    __tablename__ = "permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    permission_type_id = Column(UUID(as_uuid=True), ForeignKey("permission_types.id", ondelete="CASCADE"), nullable=False)
    is_granted = Column(Boolean, default=True, nullable=False)  # True = allow, False = explicit deny
    expires_at = Column(DateTime, nullable=True)  # Optional expiration
    
    # Relationships
    user = relationship("User", back_populates="permissions")
    resource = relationship("Resource", back_populates="permissions")
    permission_type = relationship("PermissionType", back_populates="permissions")
    
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", "permission_type_id", name="uq_user_resource_permission"),
        Index("ix_permission_user_resource", "user_id", "resource_id"),
    )


# =============================================================================
# Approval Workflow
# =============================================================================

class ApprovalRequest(Base):
    """
    Document approval workflow.
    """
    __tablename__ = "approval_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    
    # What action needs approval
    action_type = Column(String(50), nullable=False)  # upload, edit, delete, publish
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected, cancelled
    
    # Additional data
    extra_data = Column(JSONB, nullable=True)  # Store extra info (file details, changes, etc.)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    
    # Reviewer info
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note = Column(Text, nullable=True)
    
    # Relationships
    requester = relationship("User", foreign_keys=[requester_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    resource = relationship("Resource")
    
    __table_args__ = (
        Index("ix_approval_status", "status"),
        Index("ix_approval_requester", "requester_id"),
    )
    
    def __repr__(self):
        return f"<ApprovalRequest {self.id} - {self.status}>"


# =============================================================================
# Chat History
# =============================================================================

class ChatSession(Base):
    """
    A chat conversation session.
    Groups messages for a user within a specific notebook context.
    """
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notebook_id = Column(String(255), nullable=True)  # Optional context ID
    title = Column(String(500), default="New Chat", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")

    __table_args__ = (
        Index("ix_chat_session_user", "user_id"),
        Index("ix_chat_session_updated", "updated_at"),
    )

    def __repr__(self):
        return f"<ChatSession {self.id} - {self.title}>"


class ChatMessage(Base):
    """
    A single message in a chat session.
    Role is either 'user' or 'assistant'.
    """
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    source_ids = Column(JSONB, nullable=True)  # Optional: selected source IDs for this message
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_message_session", "session_id"),
    )

    def __repr__(self):
        return f"<ChatMessage {self.id} - {self.role}>"
