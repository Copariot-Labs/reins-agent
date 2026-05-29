from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from reins.api.home import get_reins_home


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

    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate() -> None:
    ensure_finance_dir()

    migrations_dir = get_migrations_dir()

    if not migrations_dir.exists():
        raise RuntimeError(f"Finance migrations directory not found: {migrations_dir}")

    with connect() as connection:
        for migration_file in sorted(migrations_dir.glob("*.sql")):
            sql = migration_file.read_text(encoding="utf-8")
            connection.executescript(sql)

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

    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM finance_transactions"
        ).fetchone()

    count = int(row["count"]) if row else 0
    print(f"Transactions:      {count}")
    print("Status:            OK")

    return 0