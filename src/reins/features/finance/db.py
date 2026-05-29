from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from reins.api.home import get_reins_home


MIGRATIONS_TABLE = "finance_schema_migrations"


def get_finance_dir() -> Path:
    return get_reins_home() / "finance"


def get_db_path() -> Path:
    return get_finance_dir() / "finance.sqlite"


def get_migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def ensure_finance_dir() -> Path:
    finance_dir = get_finance_dir()
    finance_dir.mkdir(parents=True, exist_ok=True)
    (finance_dir / "export").mkdir(parents=True, exist_ok=True)
    (finance_dir / "backups").mkdir(parents=True, exist_ok=True)
    return finance_dir


def connect() -> sqlite3.Connection:
    ensure_finance_dir()

    connection = sqlite3.connect(get_db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        connection.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise

    return connection


def _ensure_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _migration_applied(connection: sqlite3.Connection, migration_id: str) -> bool:
    row = connection.execute(
        f"SELECT 1 FROM {MIGRATIONS_TABLE} WHERE id = ?",
        (migration_id,),
    ).fetchone()
    return row is not None


def _mark_migration_applied(
    connection: sqlite3.Connection,
    migration_id: str,
) -> None:
    connection.execute(
        f"""
        INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (id, applied_at)
        VALUES (?, ?)
        """,
        (migration_id, datetime.now(timezone.utc).isoformat()),
    )


def migrate() -> None:
    ensure_finance_dir()

    migrations_dir = get_migrations_dir()

    if not migrations_dir.exists():
        raise RuntimeError(f"Finance migrations directory not found: {migrations_dir}")

    with closing(connect()) as connection:
        _ensure_migrations_table(connection)

        for migration_file in sorted(migrations_dir.glob("*.sql")):
            migration_id = migration_file.name

            if _migration_applied(connection, migration_id):
                continue

            sql = migration_file.read_text(encoding="utf-8")
            connection.executescript(sql)
            _mark_migration_applied(connection, migration_id)

        connection.commit()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    connection = connect()

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def doctor() -> int:
    finance_dir = ensure_finance_dir()
    db_path = get_db_path()
    migrations_dir = get_migrations_dir()

    migrate()

    print("Reins Finance doctor")
    print(f"Finance directory: {finance_dir}")
    print(f"Database path:     {db_path}")
    print(f"Migrations path:   {migrations_dir}")
    print(f"Database exists:   {db_path.exists()}")

    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM finance_transactions"
        ).fetchone()

    count = int(row["count"]) if row else 0
    print(f"Transactions:      {count}")
    print("Status:            OK")

    return 0
