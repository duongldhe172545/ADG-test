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
# Departments (Phòng ban)
# =============================================================================

class Department(Base):
    """
    Organizational departments / divisions.
    Hierarchical: Khối → Phòng.
    """
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    drive_folder_id = Column(String(255), nullable=True)  # Google Drive folder for this dept
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    parent = relationship("Department", remote_side=[id], backref="children")
    user_departments = relationship("UserDepartment", back_populates="department", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_departments_parent", "parent_id"),
        Index("ix_departments_name", "name"),
    )

    def __repr__(self):
        return f"<Department {self.name}>"


class UserDepartment(Base):
    """
    User ↔ Department assignment.
    is_head=True means this user is the Manager (trưởng phòng) of the department.
    """
    __tablename__ = "user_departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    is_head = Column(Boolean, default=False, nullable=False)  # True = Manager of this dept

    # Relationships
    user = relationship("User")
    department = relationship("Department", back_populates="user_departments")

    __table_args__ = (
        UniqueConstraint("user_id", "department_id", name="uq_user_department"),
        Index("ix_user_departments_user", "user_id"),
        Index("ix_user_departments_dept", "department_id"),
    )


class FolderGrant(Base):
    """
    Admin grants a user access to view another department's folders/files.
    """
    __tablename__ = "folder_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    department = relationship("Department")
    granter = relationship("User", foreign_keys=[granted_by])

    __table_args__ = (
        UniqueConstraint("user_id", "department_id", name="uq_folder_grant"),
        Index("ix_folder_grants_user", "user_id"),
    )


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
    Document approval workflow with 2-step support.
    Step 1: Manager (trưởng phòng) reviews
    Step 2: Admin (trưởng khối) reviews
    """
    __tablename__ = "approval_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(UUID(as_uuid=True), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    
    # What action needs approval
    action_type = Column(String(50), nullable=False)  # upload, edit, delete, publish
    status = Column(String(20), default="pending", nullable=False)  # pending, manager_approved, approved, rejected, cancelled
    
    # 2-step approval
    approval_step = Column(Integer, default=1, nullable=False)  # 1 = waiting for Manager, 2 = waiting for Admin
    manager_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    manager_approved_at = Column(DateTime, nullable=True)
    
    # Additional data
    extra_data = Column(JSONB, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    
    # Final reviewer info (Admin)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note = Column(Text, nullable=True)
    
    # Relationships
    requester = relationship("User", foreign_keys=[requester_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    manager = relationship("User", foreign_keys=[manager_id])
    resource = relationship("Resource")
    department = relationship("Department")
    
    __table_args__ = (
        Index("ix_approval_status", "status"),
        Index("ix_approval_requester", "requester_id"),
        Index("ix_approval_step", "approval_step"),
    )
    
    def __repr__(self):
        return f"<ApprovalRequest {self.id} - step {self.approval_step} - {self.status}>"


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


# =============================================================================
# Document Tracking (file versioning & management)
# =============================================================================

class Document(Base):
    """
    Tracks all files managed by the system.
    Syncs with Google Drive — Drive is source of truth for content,
    this table tracks metadata, versions, and indexing status.
    """
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drive_file_id = Column(String(255), nullable=False, unique=True)
    file_name = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    folder_id = Column(String(255), nullable=True, index=True)
    folder_path = Column(String(1000), nullable=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)

    # Versioning
    version = Column(Integer, default=1, nullable=False)
    old_drive_id = Column(String(255), nullable=True)
    change_note = Column(Text, nullable=True)

    # Tracking
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)

    # RAG indexing
    indexed_at = Column(DateTime, nullable=True)

    # Status
    status = Column(String(20), default="active", nullable=False)

    # Relationships
    uploader = relationship("User", foreign_keys=[uploaded_by])
    approver = relationship("User", foreign_keys=[approved_by])
    department = relationship("Department")

    __table_args__ = (
        Index("ix_document_drive_file_id", "drive_file_id"),
        Index("ix_document_folder_id", "folder_id"),
        Index("ix_document_status", "status"),
    )

    def __repr__(self):
        return f"<Document {self.file_name} v{self.version}>"


# =============================================================================
# Document Chunks (for RAG / pgvector)
# =============================================================================

class DocumentChunk(Base):
    """
    Stores document text chunks with vector embeddings for RAG search.
    Uses pgvector extension for similarity search.
    """
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(String(255), nullable=False, index=True)
    file_name = Column(String(500), nullable=False)
    folder_id = Column(String(255), index=True)
    folder_path = Column(String(1000))
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer)
    metadata_ = Column("metadata", JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("file_id", "chunk_index", name="uq_chunk_file_index"),
        Index("ix_document_chunks_file_id", "file_id"),
        Index("ix_document_chunks_folder_id", "folder_id"),
    )

    def __repr__(self):
        return f"<DocumentChunk {self.file_name}[{self.chunk_index}]>"
