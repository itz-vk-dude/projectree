"""
Run this ONCE against your Supabase database before your first deploy
(and again after any model changes), instead of relying on db.create_all()
running at app startup - that hook only fires in the `if __name__ == "__main__"`
block, which never executes on Vercel's serverless runtime.

Usage:
    DATABASE_URL="postgresql://...supabase connection string..." python scripts/init_db.py

For anything beyond this initial create-all, use a real migration tool
(Flask-Migrate/Alembic) so future schema changes don't require dropping data.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app, db  # noqa: E402


def main():
    if not os.getenv("DATABASE_URL"):
        print("ERROR: set DATABASE_URL to your Supabase connection string first.")
        sys.exit(1)

    with app.app_context():
        db.create_all()
        print("[OK] All tables created (or already existed) in the target database.")


if __name__ == "__main__":
    main()
