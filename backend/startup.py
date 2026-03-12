"""
Startup script — replaces start.sh to avoid CRLF/line-ending issues on Windows→Linux deploy.
Runs: service account setup → alembic migrations → table sync → seed → uvicorn
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(cmd, cwd=None, fatal=True):
    """Run a command, print output, optionally exit on failure."""
    print(f"  → {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if result.returncode != 0:
        if fatal:
            print(f"  ✗ Command failed (exit {result.returncode})")
            sys.exit(result.returncode)
        else:
            print(f"  ⚠️ Command had issues (exit {result.returncode}), continuing...")


def main():
    print("=== ADG KMS Starting ===")

    # Write service account JSON from env var to file (if provided)
    sa_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        with open("/app/service-account.json", "w") as f:
            f.write(sa_json)
        os.environ["GDRIVE_SERVICE_ACCOUNT_FILE"] = "/app/service-account.json"
        print("✅ Service account file created from env var")

    # Run Alembic migrations
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        print("🔄 Running database migrations...")
        run("alembic upgrade head", cwd="/app/backend")
        print("✅ Migrations complete")

        # Sync tables: create any new tables from models.py
        print("🔄 Syncing database tables...")
        run("python -m backend.db.sync_tables", cwd="/app", fatal=False)
        print("✅ Table sync complete")

        # Seed database
        print("🌱 Seeding database...")
        run("python -m backend.db.seed", cwd="/app")
        print("✅ Seed complete")
    else:
        print("⚠️ DATABASE_URL not set, skipping migrations")

    # Start uvicorn
    port = os.environ.get("PORT", "8080")
    print(f"🚀 Starting server on port {port}...")
    os.execvp("uvicorn", [
        "uvicorn", "backend.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--workers", "1",
        "--log-level", "info",
    ])


if __name__ == "__main__":
    main()
