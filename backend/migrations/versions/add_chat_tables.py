"""Add documents, chat_sessions and chat_messages tables

Revision ID: a1b2c3d4e5f6
Revises: 35f29486e6f4
Create Date: 2024-03-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = '35f29486e6f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('drive_file_id', sa.String(255), nullable=False, unique=True),
        sa.Column('file_name', sa.String(500), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('file_size', sa.Integer, nullable=True),
        sa.Column('folder_id', sa.String(255), nullable=True),
        sa.Column('folder_path', sa.String(1000), nullable=True),
        sa.Column('version', sa.Integer, server_default='1', nullable=False),
        sa.Column('old_drive_id', sa.String(255), nullable=True),
        sa.Column('change_note', sa.Text, nullable=True),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('uploaded_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('indexed_at', sa.DateTime, nullable=True),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
    )
    op.create_index('ix_document_drive_file_id', 'documents', ['drive_file_id'])
    op.create_index('ix_document_folder_id', 'documents', ['folder_id'])
    op.create_index('ix_document_status', 'documents', ['status'])

    # Create chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('notebook_id', sa.String(255), nullable=True),
        sa.Column('title', sa.String(500), server_default='New Chat', nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_chat_session_user', 'chat_sessions', ['user_id'])
    op.create_index('ix_chat_session_updated', 'chat_sessions', ['updated_at'])

    # Create chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('source_ids', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_chat_message_session', 'chat_messages', ['session_id'])


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('documents')
