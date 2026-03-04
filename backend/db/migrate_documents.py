"""
Migration: Create documents table for file versioning & management.
Run: python -m backend.db.migrate_documents
"""

import asyncio
from sqlalchemy import text
from backend.db.connection import get_async_session_factory


STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        drive_file_id VARCHAR(255) NOT NULL UNIQUE,
        file_name VARCHAR(500) NOT NULL,
        mime_type VARCHAR(100),
        file_size INTEGER,
        folder_id VARCHAR(255),
        folder_path VARCHAR(1000),
        version INTEGER DEFAULT 1 NOT NULL,
        old_drive_id VARCHAR(255),
        change_note TEXT,
        uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
        approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
        uploaded_at TIMESTAMP DEFAULT NOW() NOT NULL,
        approved_at TIMESTAMP,
        indexed_at TIMESTAMP,
        status VARCHAR(20) DEFAULT 'active' NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_document_drive_file_id ON documents(drive_file_id)",
    "CREATE INDEX IF NOT EXISTS ix_document_folder_id ON documents(folder_id)",
    "CREATE INDEX IF NOT EXISTS ix_document_status ON documents(status)",
]


async def run_migration():
    factory = get_async_session_factory()
    async with factory() as session:
        for stmt in STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
        print("✅ Created 'documents' table")


if __name__ == "__main__":
    asyncio.run(run_migration())
