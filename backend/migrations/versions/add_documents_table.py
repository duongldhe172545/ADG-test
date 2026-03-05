"""Add documents table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2024-03-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only create if not exists (safe for environments that already have it)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'documents' not in existing_tables:
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


def downgrade() -> None:
    op.drop_table('documents')
