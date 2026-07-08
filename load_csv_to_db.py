"""
Bulk-loads my_projects.csv into the `projects` table on Supabase Postgres.

The original version of this script connected directly to a local MySQL
instance with a hardcoded root password ("Care@123") baked into the source
file. That's a plaintext-credential leak risk the moment this file is ever
committed anywhere, and it won't work against Postgres/Supabase in any case
(different driver, different DB engine). This version reads the connection
string from DATABASE_URL and uses SQLAlchemy so it works against whatever
Postgres instance you point it at.

Usage:
    DATABASE_URL="postgresql://...supabase connection string..." python scripts/load_csv_to_db.py
"""
from sqlalchemy import create_engine, text
import pandas as pd
import os
import sys
from dotenv import load_dotenv

load_dotenv()


CSV_PATH = os.path.join(os.path.dirname(__file__), "my_projects.csv")


def normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: set DATABASE_URL to your Supabase connection string first.")
        sys.exit(1)

    print("Reading CSV file...")
    df = pd.read_csv(CSV_PATH)

    engine = create_engine(normalize_db_url(db_url))

    with engine.begin() as conn:
        print("Emptying old project data (projects + dependent rows)...")
        # ON DELETE CASCADE on the FKs (see app.py models) means clearing
        # `projects` also clears step_completions/user_projects tied to them.
        conn.execute(text("TRUNCATE TABLE projects RESTART IDENTITY CASCADE"))

        print(f"Importing {len(df)} projects...")
        records = df.assign(status="Available").to_dict("records")
        conn.execute(
            text("""
                INSERT INTO projects
                    (title, description, interest, type, level, language,
                     status, expected_output, duration_days, steps)
                VALUES
                    (:title, :description, :interest, :type, :level, :language,
                     :status, :expected_output, :duration_days, :steps)
            """),
            records,
        )

    print(f"[OK] Success! {len(df)} projects loaded into Supabase Postgres.")


if __name__ == "__main__":
    main()
