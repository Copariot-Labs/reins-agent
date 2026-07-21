from __future__ import annotations

from collections import Counter
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from reins.api.home import get_reins_home
from reins.features.wecom.xlsx import write_xlsx


BASE_RECORD_HEADERS = [
    "id",
    "created_at",
    "kind",
    "status",
    "sender_id",
    "sender_name",
    "chat_id",
    "chat_type",
    "message",
    "selected_meaning",
    "matched_faq_id",
    "reply",
    "ai_fallback",
]

WORK_ORDER_METADATA_HEADERS = [
    "external_id",
    "ticket_created_at",
    "title",
    "description",
    "resident_ref",
    "resident_name",
    "resident_contact",
    "location",
    "category",
    "original_category",
    "priority",
    "original_priority",
    "assigned_role",
    "assigned_role_label",
    "source_channel",
    "assignee",
    "due_at",
    "upstream_status",
    "customer_assessment",
    "handling_requirements",
    "people_involved",
    "current_danger",
    "assignment_reason",
    "priority_reason",
    "notification_status",
    "notification_target",
    "notification_channel",
    "notification_recipients",
    "notification_message_id",
    "notification_error",
    "last_staff_reply",
    "last_staff_reply_at",
    "last_staff_responder",
]

RECORD_HEADERS = [
    *BASE_RECORD_HEADERS,
    *WORK_ORDER_METADATA_HEADERS,
    "metadata",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_wecom_dir() -> Path:
    return get_reins_home() / "wecom"


def ensure_wecom_dir() -> Path:
    directory = get_wecom_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_db_path() -> Path:
    return ensure_wecom_dir() / "wecom.sqlite"


def get_faq_path() -> Path:
    return ensure_wecom_dir() / "faq.json"


def get_records_xlsx_path() -> Path:
    return ensure_wecom_dir() / "records.xlsx"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        connection.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise
    return connection


def migrate() -> None:
    ensure_wecom_dir()
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS wecom_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                sender_id TEXT NOT NULL DEFAULT '',
                sender_name TEXT NOT NULL DEFAULT '',
                chat_id TEXT NOT NULL DEFAULT '',
                chat_type TEXT NOT NULL DEFAULT '',
                inbound_message TEXT NOT NULL,
                reply TEXT NOT NULL,
                matched_faq_id TEXT NOT NULL DEFAULT '',
                selected_meaning TEXT NOT NULL DEFAULT '',
                route TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS wecom_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                sender_id TEXT NOT NULL DEFAULT '',
                sender_name TEXT NOT NULL DEFAULT '',
                chat_id TEXT NOT NULL DEFAULT '',
                chat_type TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                selected_meaning TEXT NOT NULL DEFAULT '',
                matched_faq_id TEXT NOT NULL DEFAULT '',
                reply TEXT NOT NULL DEFAULT '',
                ai_fallback INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        connection.commit()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    migrate()
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "ai_fallback" in data:
        data["ai_fallback"] = bool(data["ai_fallback"])
    if "metadata_json" in data:
        try:
            metadata = json.loads(data.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        data["metadata"] = metadata if isinstance(metadata, dict) else {}
    return data


def add_reply(
    *,
    sender_id: str = "",
    sender_name: str = "",
    chat_id: str = "",
    chat_type: str = "",
    inbound_message: str,
    reply: str,
    matched_faq_id: str = "",
    selected_meaning: str = "",
    route: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    created_at = now_iso()

    with transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO wecom_replies (
                created_at, sender_id, sender_name, chat_id, chat_type,
                inbound_message, reply, matched_faq_id, selected_meaning,
                route, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                sender_id,
                sender_name,
                chat_id,
                chat_type,
                inbound_message,
                reply,
                matched_faq_id,
                selected_meaning,
                route,
                metadata_json,
            ),
        )
        row = connection.execute(
            "SELECT * FROM wecom_replies WHERE id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()

    return _row_to_dict(row)


def add_record(
    *,
    kind: str,
    status: str = "open",
    sender_id: str = "",
    sender_name: str = "",
    chat_id: str = "",
    chat_type: str = "",
    message: str,
    selected_meaning: str = "",
    matched_faq_id: str = "",
    reply: str = "",
    ai_fallback: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    created_at = now_iso()

    with transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO wecom_records (
                created_at, kind, status, sender_id, sender_name, chat_id,
                chat_type, message, selected_meaning, matched_faq_id, reply,
                ai_fallback, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                kind,
                status,
                sender_id,
                sender_name,
                chat_id,
                chat_type,
                message,
                selected_meaning,
                matched_faq_id,
                reply,
                1 if ai_fallback else 0,
                metadata_json,
            ),
        )
        row = connection.execute(
            "SELECT * FROM wecom_records WHERE id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()

    record = _row_to_dict(row)
    export_records_xlsx()
    return record


def get_record(record_id: int) -> dict[str, Any] | None:
    migrate()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM wecom_records WHERE id = ?",
            (int(record_id),),
        ).fetchone()
    return _row_to_dict(row) if row else None


def find_record_by_metadata(
    key: str,
    value: str,
    *,
    kind: str | None = None,
) -> dict[str, Any] | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None

    migrate()
    clauses = []
    params: list[Any] = []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM wecom_records
            {where_sql}
            ORDER BY id DESC
            """,
            params,
        ).fetchall()

    for row in rows:
        record = _row_to_dict(row)
        metadata = record.get("metadata")
        if isinstance(metadata, dict) and str(metadata.get(key) or "").strip() == clean_value:
            return record

    return None


def update_record(
    record_id: int,
    *,
    status: str | None = None,
    message: str | None = None,
    selected_meaning: str | None = None,
    reply: str | None = None,
    ai_fallback: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_record(record_id)
    if not existing:
        raise ValueError(f"record not found: {record_id}")

    next_metadata = dict(existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {})
    if metadata:
        next_metadata.update(metadata)

    updates: dict[str, Any] = {
        "metadata_json": json.dumps(next_metadata, ensure_ascii=False, sort_keys=True),
    }
    if status is not None:
        updates["status"] = status
    if message is not None:
        updates["message"] = message
    if selected_meaning is not None:
        updates["selected_meaning"] = selected_meaning
    if reply is not None:
        updates["reply"] = reply
    if ai_fallback is not None:
        updates["ai_fallback"] = 1 if ai_fallback else 0

    set_sql = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [int(record_id)]

    with transaction() as connection:
        connection.execute(
            f"UPDATE wecom_records SET {set_sql} WHERE id = ?",
            params,
        )
        row = connection.execute(
            "SELECT * FROM wecom_records WHERE id = ?",
            (int(record_id),),
        ).fetchone()

    record = _row_to_dict(row)
    export_records_xlsx()
    return record


def list_records(limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
    migrate()
    limit = max(1, min(int(limit or 50), 500))
    clauses = []
    params: list[Any] = []

    if kind:
        clauses.append("kind = ?")
        params.append(kind)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM wecom_records
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def export_records_xlsx(path: Path | None = None) -> Path:
    migrate()
    output_path = path or get_records_xlsx_path()

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM wecom_records
            ORDER BY id ASC
            """
        ).fetchall()

    values = []
    for row in rows:
        data = _row_to_dict(row)
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        values.append([
            *[data.get(header, "") for header in BASE_RECORD_HEADERS],
            *[metadata.get(header, "") for header in WORK_ORDER_METADATA_HEADERS],
            data.get("metadata_json", ""),
        ])

    return write_xlsx(
        output_path,
        sheet_name="WeCom Records",
        headers=RECORD_HEADERS,
        rows=values,
    )


def records_report(kind: str | None = None) -> dict[str, Any]:
    records = list_records(limit=500, kind=kind)
    export_path = export_records_xlsx()

    def metadata_value(record: dict[str, Any], key: str) -> str:
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            return ""
        value = metadata.get(key)
        return str(value or "").strip()

    by_kind = Counter(str(record.get("kind") or "") for record in records)
    by_status = Counter(str(record.get("status") or "") for record in records)
    by_category = Counter(metadata_value(record, "category") for record in records)
    by_priority = Counter(metadata_value(record, "priority") for record in records)
    by_role = Counter(metadata_value(record, "assigned_role") for record in records)
    by_source = Counter(metadata_value(record, "source_channel") for record in records)

    for counter in (by_kind, by_status, by_category, by_priority, by_role, by_source):
        counter.pop("", None)

    return {
        "ok": True,
        "kind": kind or "",
        "total": len(records),
        "open": sum(1 for record in records if str(record.get("status") or "") == "open"),
        "by_kind": dict(by_kind),
        "by_status": dict(by_status),
        "by_category": dict(by_category),
        "by_priority": dict(by_priority),
        "by_assigned_role": dict(by_role),
        "by_source_channel": dict(by_source),
        "records_xlsx_path": str(export_path),
    }


def doctor() -> dict[str, Any]:
    from reins.features.wecom.notifier import notification_doctor

    migrate()
    records_path = export_records_xlsx()

    with connect() as connection:
        record_count = int(connection.execute("SELECT COUNT(*) FROM wecom_records").fetchone()[0])
        reply_count = int(connection.execute("SELECT COUNT(*) FROM wecom_replies").fetchone()[0])

    return {
        "ok": True,
        "wecom_dir": str(get_wecom_dir()),
        "db_path": str(get_db_path()),
        "faq_path": str(get_faq_path()),
        "records_xlsx_path": str(records_path),
        "record_count": record_count,
        "reply_count": reply_count,
        "notifications": notification_doctor(),
    }
