"""
DB Sync Script — runs at deploy time (in start.sh).
Creates any tables defined in models.py that don't yet exist in the database.
Safe to run repeatedly: create_all only adds NEW tables, never drops or alters existing ones.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect
from backend.config import settings

# Import ALL models so Base.metadata knows about every table
from backend.db.models import Base  # noqa — triggers all model registration


def sync():
    url = settings.DATABASE_URL
    if not url:
        print("⚠️  DATABASE_URL not set, skipping DB sync")
        return

    # Use sync driver
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(url)

    # Show what's new
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    defined = set(Base.metadata.tables.keys())
    missing = defined - existing

    if missing:
        print(f"📦 Creating {len(missing)} missing table(s): {', '.join(sorted(missing))}")
    else:
        print("✅ All tables already exist")

    # create_all is idempotent — only creates tables that don't exist
    Base.metadata.create_all(engine)

    if missing:
        print("✅ Tables created successfully")

    engine.dispose()


if __name__ == "__main__":
    sync()
