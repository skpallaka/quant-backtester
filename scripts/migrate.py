"""Apply pending SQL migrations from migrations/ in filename order.

Tracks what's already been applied in a `schema_migrations` table, so
re-running is a no-op once everything is applied. Same script targets
local Docker Postgres or RDS -- it only cares about DATABASE_URL.

Run with:  python scripts/migrate.py
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from quant_backtester.data.loader import get_database_url

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def main() -> None:
    engine = create_engine(get_database_url())

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        applied = {row[0] for row in conn.execute(text("SELECT filename FROM schema_migrations"))}

    pending = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.name not in applied)
    if not pending:
        print("Nothing to apply -- schema is up to date.")
        return

    for path in pending:
        print(f"Applying {path.name} ...")
        sql = path.read_text()
        with engine.begin() as conn:
            conn.execute(text(sql))
            conn.execute(text("INSERT INTO schema_migrations (filename) VALUES (:f)"), {"f": path.name})
        print(f"  done.")


if __name__ == "__main__":
    main()
