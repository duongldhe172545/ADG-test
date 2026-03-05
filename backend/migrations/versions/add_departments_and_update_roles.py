"""Add departments, folder_grants, and update approval workflow for 4-role RBAC

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2024-03-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect

# revision identifiers
revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    # ── departments ──────────────────────────────────────────────
    if 'departments' not in existing_tables:
        op.create_table(
            'departments',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True),
            sa.Column('drive_folder_id', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        )
        op.create_index('ix_departments_parent', 'departments', ['parent_id'])
        op.create_index('ix_departments_name', 'departments', ['name'])

    # ── user_departments ─────────────────────────────────────────
    if 'user_departments' not in existing_tables:
        op.create_table(
            'user_departments',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('is_head', sa.Boolean, server_default='false', nullable=False),
        )
        op.create_index('ix_user_departments_user', 'user_departments', ['user_id'])
        op.create_index('ix_user_departments_dept', 'user_departments', ['department_id'])
        op.create_unique_constraint('uq_user_department', 'user_departments', ['user_id', 'department_id'])

    # ── folder_grants ────────────────────────────────────────────
    if 'folder_grants' not in existing_tables:
        op.create_table(
            'folder_grants',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('granted_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        )
        op.create_index('ix_folder_grants_user', 'folder_grants', ['user_id'])
        op.create_unique_constraint('uq_folder_grant', 'folder_grants', ['user_id', 'department_id'])

    # ── documents: add department_id ─────────────────────────────
    if 'documents' in existing_tables:
        existing_cols = [c['name'] for c in inspector.get_columns('documents')]
        if 'department_id' not in existing_cols:
            op.add_column('documents', sa.Column(
                'department_id', UUID(as_uuid=True),
                sa.ForeignKey('departments.id', ondelete='SET NULL'),
                nullable=True,
            ))
            op.create_index('ix_document_department', 'documents', ['department_id'])

    # ── approval_requests: add 2-step workflow columns ───────────
    if 'approval_requests' in existing_tables:
        existing_cols = [c['name'] for c in inspector.get_columns('approval_requests')]
        if 'approval_step' not in existing_cols:
            op.add_column('approval_requests', sa.Column(
                'approval_step', sa.Integer, server_default='1', nullable=False,
            ))
        if 'manager_id' not in existing_cols:
            op.add_column('approval_requests', sa.Column(
                'manager_id', UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ))
        if 'manager_approved_at' not in existing_cols:
            op.add_column('approval_requests', sa.Column(
                'manager_approved_at', sa.DateTime, nullable=True,
            ))
        if 'department_id' not in existing_cols:
            op.add_column('approval_requests', sa.Column(
                'department_id', UUID(as_uuid=True),
                sa.ForeignKey('departments.id', ondelete='SET NULL'),
                nullable=True,
            ))


def downgrade() -> None:
    op.drop_column('approval_requests', 'department_id')
    op.drop_column('approval_requests', 'manager_approved_at')
    op.drop_column('approval_requests', 'manager_id')
    op.drop_column('approval_requests', 'approval_step')
    op.drop_column('documents', 'department_id')
    op.drop_table('folder_grants')
    op.drop_table('user_departments')
    op.drop_table('departments')
