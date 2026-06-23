import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import json

DB_PATH = Path.home() / ".reins" / "workmode.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        message TEXT,
        issue_type TEXT,
        priority TEXT,
        location TEXT,
        workflow TEXT,
        status TEXT,
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        type TEXT,
        message TEXT,
        data TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS artifacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        type TEXT,
        title TEXT,
        content TEXT,
        created_at TEXT
    );
    """)

    conn.commit()
    conn.close()


def save_case(case: dict):
    init_db()
    conn = get_conn()

    conn.execute("""
    INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        case["case_id"],
        case.get("message"),
        case.get("issue_type"),
        case.get("priority"),
        case.get("location"),
        case.get("workflow"),
        case.get("status", "running"),
        case.get("created_at"),
        case.get("updated_at"),
    ))

    conn.commit()
    conn.close()


def save_event(case_id: str, event_type: str, message: str, data: dict):
    init_db()
    conn = get_conn()

    conn.execute("""
    INSERT INTO events (case_id, type, message, data, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (
        case_id,
        event_type,
        message,
        json.dumps(data),
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    conn.close()


def save_artifact(case_id: str, artifact: dict):
    init_db()
    conn = get_conn()

    conn.execute("""
    INSERT INTO artifacts (case_id, type, title, content, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (
        case_id,
        artifact.get("type"),
        artifact.get("title"),
        artifact.get("content"),
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    conn.close()