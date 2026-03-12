"""Add notifications and activity_logs tables

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import inspect

# revision identifiers
revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    # ── activity_logs ────────────────────────────────────────────
    if 'activity_logs' not in existing_tables:
        op.create_table(
            'activity_logs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('user_email', sa.String(255), nullable=False),
            sa.Column('action', sa.String(100), nullable=False),
            sa.Column('target_type', sa.String(50), nullable=True),
            sa.Column('target_id', sa.String(255), nullable=True),
            sa.Column('details', JSONB, nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.text("(now() at time zone 'utc')"), nullable=False),
        )
        op.create_index('ix_activity_user', 'activity_logs', ['user_id', 'created_at'])
        op.create_index('ix_activity_action', 'activity_logs', ['action', 'created_at'])

    # ── notifications ────────────────────────────────────────────
    if 'notifications' not in existing_tables:
        op.create_table(
            'notifications',
            sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('message', sa.Text, nullable=False),
            sa.Column('type', sa.String(50), nullable=False),
            sa.Column('link', sa.String(500), nullable=True),
            sa.Column('is_read', sa.Boolean, server_default='false', nullable=False),
            sa.Column('created_at', sa.DateTime, server_default=sa.text("(now() at time zone 'utc')"), nullable=False),
        )
        op.create_index('ix_notif_user', 'notifications', ['user_id', 'is_read', 'created_at'])


def downgrade() -> None:
    op.drop_table('notifications')
    op.drop_table('activity_logs')
