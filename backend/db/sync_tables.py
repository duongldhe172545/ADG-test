"""
DB Sync Script — runs at deploy time.
Creates any tables defined in models.py that don't yet exist in the database.
Safe to run repeatedly. Handles orphaned indexes gracefully.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from backend.config import settings

# Import ALL models so Base.metadata knows about every table
from backend.db.models import Base  # noqa


def sync():
    url = settings.DATABASE_URL
    if not url:
        print("⚠️  DATABASE_URL not set, skipping DB sync")
        return

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(url)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    defined = set(Base.metadata.tables.keys())
    missing = defined - existing

    if not missing:
        print("✅ All tables already exist")
        engine.dispose()
        return

    print(f"📦 Creating {len(missing)} missing table(s): {', '.join(sorted(missing))}")

    # Create missing tables one by one to handle partial failures
    for table_name in sorted(missing):
        table = Base.metadata.tables[table_name]
        try:
            table.create(engine, checkfirst=True)
            print(f"  ✅ {table_name}")
        except Exception as e:
            # Handle orphaned indexes or other partial-create issues
            err_msg = str(e).lower()
            if "already exists" in err_msg:
                print(f"  ⚠️ {table_name} — has orphaned objects, creating with raw SQL...")
                _create_table_raw(engine, table_name, table)
            else:
                print(f"  ❌ {table_name} — {e}")

    engine.dispose()


def _create_table_raw(engine, table_name, table):
    """Fallback: create table using CREATE TABLE IF NOT EXISTS, skip existing indexes."""
    try:
        with engine.connect() as conn:
            # Create just the table (no indexes) using raw DDL
            cols = []
            for col in table.columns:
                col_type = col.type.compile(engine.dialect)
                nullable = "" if col.nullable else " NOT NULL"
                default = ""
                if col.server_default:
                    default = f" DEFAULT {col.server_default.arg}"
                pk = " PRIMARY KEY" if col.primary_key else ""
                cols.append(f'"{col.name}" {col_type}{nullable}{default}{pk}')

            # Add foreign keys
            for fk in table.foreign_keys:
                cols.append(
                    f'FOREIGN KEY ("{fk.parent.name}") REFERENCES '
                    f'"{fk.column.table.name}"("{fk.column.name}") '
                    f'ON DELETE {fk.ondelete or "NO ACTION"}'
                )

            ddl = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(cols)})'
            conn.execute(text(ddl))
            conn.commit()
            print(f"  ✅ {table_name} (raw DDL)")
    except Exception as e2:
        print(f"  ❌ {table_name} raw DDL failed: {e2}")


if __name__ == "__main__":
    sync()
