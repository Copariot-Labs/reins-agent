from __future__ import annotations

from collections import Counter
import json
import os
import re
import shutil
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import fcntl
except ImportError:  # pragma: no cover - unavailable on Windows.
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - unavailable on macOS/Linux.
    msvcrt = None

from reins.api.home import get_reins_home
from reins.features.wecom.xlsx import write_xlsx


STAFF_WORK_ORDER_COLUMNS = [
    ("ticket_id", "工单编号", 24.0),
    ("created_at", "创建时间", 19.0),
    ("status", "状态", 14.0),
    ("priority", "优先级", 10.0),
    ("category", "分类", 18.0),
    ("assigned_role", "负责部门", 16.0),
    ("assignee", "负责人", 16.0),
    ("location", "地点", 26.0),
    ("issue", "居民诉求", 60.0),
    ("handling_requirements", "处理要求", 36.0),
    ("due_at", "截止时间", 19.0),
    ("notification_status", "通知状态", 14.0),
    ("result", "处理结果", 48.0),
    ("responder", "处理人", 16.0),
    ("updated_at", "最后更新时间", 19.0),
]

STATUS_LABELS = {
    "new": "待处理",
    "open": "待处理",
    "waiting_human_review": "待人工审核",
    "pending_notification": "待通知",
    "notified": "已通知",
    "processing": "处理中",
    "resolved": "已完成",
    "closed": "已关闭",
    "failed": "失败",
}

PRIORITY_LABELS = {
    "critical": "紧急",
    "emergency": "紧急",
    "urgent": "紧急",
    "high": "紧急",
    "medium": "普通",
    "normal": "普通",
    "low": "低",
}

NOTIFICATION_STATUS_LABELS = {
    "sent": "已发送",
    "dry_run": "预览",
    "pending_configuration": "待配置",
    "skipped_duplicate": "已发送（重复跳过）",
    "failed": "发送失败",
    "disabled": "未启用",
}


try:
    _CHINA_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # Keep current China operations usable on minimal Windows installs.
    _CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
_EXPORT_THREAD_LOCK = threading.RLock()
_RESIDENT_IDENTIFIER_LINE = re.compile(
    r"^\s*(?:[-·]\s*)?(?:居民标识|客户标识|微信客户)\s*[：:].*$",
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _label(value: Any, labels: dict[str, str]) -> str:
    clean = _clean(value)
    if not clean:
        return ""
    return labels.get(clean.lower(), clean)


def _format_datetime(value: Any) -> str:
    clean = _clean(value)
    if not clean:
        return ""

    normalized = clean[:-1] + "+00:00" if clean.endswith("Z") else clean
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return clean

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_CHINA_TZ)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _first_non_empty(*values: Any) -> str:
    for value in values:
        clean = _clean(value)
        if clean:
            return clean
    return ""


def _work_order_issue(record: dict[str, Any], metadata: dict[str, Any]) -> str:
    description = _clean(metadata.get("description"))
    title = _clean(metadata.get("title"))
    if description:
        if title and title not in description:
            return f"{title}\n{description}"
        return description
    if title:
        return title
    raw_message = _clean(record.get("message"))
    return "\n".join(
        line for line in raw_message.splitlines() if not _RESIDENT_IDENTIFIER_LINE.match(line)
    ).strip()


def _staff_work_order_values(record: dict[str, Any]) -> list[object]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    notification_recipients = metadata.get("notification_recipients")
    assignee_from_notification = (
        "、".join(str(value).strip() for value in notification_recipients if str(value).strip())
        if isinstance(notification_recipients, list)
        else ""
    )

    created_at = _first_non_empty(
        metadata.get("ticket_created_at"),
        metadata.get("api_created_at"),
        record.get("created_at"),
    )
    updated_at = _first_non_empty(
        metadata.get("last_staff_reply_at"),
        metadata.get("api_updated_at"),
        metadata.get("notified_at"),
        metadata.get("analyzed_at"),
        created_at,
    )

    values = {
        "ticket_id": _first_non_empty(
            metadata.get("external_id"),
            metadata.get("ticket_id"),
            metadata.get("api_ticket_id"),
            record.get("id"),
        ),
        "created_at": _format_datetime(created_at),
        "status": _label(record.get("status"), STATUS_LABELS),
        "priority": _label(metadata.get("priority"), PRIORITY_LABELS),
        "category": _clean(metadata.get("category")),
        "assigned_role": _first_non_empty(
            metadata.get("assigned_role_labels"),
            metadata.get("assigned_role_label"),
            metadata.get("assigned_role"),
        ),
        "assignee": _first_non_empty(
            metadata.get("assignee"),
            assignee_from_notification,
        ),
        "location": _clean(metadata.get("location")),
        "issue": _work_order_issue(record, metadata),
        "handling_requirements": _clean(metadata.get("handling_requirements")),
        "due_at": _format_datetime(metadata.get("due_at")),
        "notification_status": _label(
            metadata.get("notification_status"),
            NOTIFICATION_STATUS_LABELS,
        ),
        "result": _first_non_empty(
            metadata.get("last_staff_reply"),
            record.get("reply"),
        ),
        "responder": _first_non_empty(
            metadata.get("last_staff_responder"),
            metadata.get("assignee"),
        ),
        "updated_at": _format_datetime(updated_at),
    }
    return [values[key] for key, _header, _width in STAFF_WORK_ORDER_COLUMNS]


@contextmanager
def _excel_export_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with _EXPORT_THREAD_LOCK:
        with lock_path.open("a+b") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)



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


def get_visible_records_xlsx_path() -> Path | None:
    """Return the optional staff-visible workbook path.

    The internal workbook remains under REINS_HOME. Administrators can set
    REINS_WECOM_EXPORT_DIR to keep an automatically refreshed copy in a normal
    folder such as Documents or a shared synced directory.
    """
    configured = os.environ.get("REINS_WECOM_EXPORT_DIR", "").strip()
    if not configured:
        return None
    return Path(os.path.expandvars(configured)).expanduser() / "社区工单台账.xlsx"


def _mirror_records_xlsx(source: Path) -> Path | None:
    target = get_visible_records_xlsx_path()
    if target is None:
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = NORMAL")
    try:
        connection.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise
    return connection


def migrate() -> None:
    ensure_wecom_dir()
    with closing(connect()) as connection:
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

            CREATE INDEX IF NOT EXISTS idx_wecom_records_kind_created_at
                ON wecom_records(kind, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_wecom_records_status_created_at
                ON wecom_records(status, created_at DESC);
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

    return _row_to_dict(row)


def get_record(record_id: int) -> dict[str, Any] | None:
    migrate()
    with closing(connect()) as connection:
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
    with closing(connect()) as connection:
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

    return _row_to_dict(row)


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

    with closing(connect()) as connection:
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


def list_all_records(kind: str | None = None) -> list[dict[str, Any]]:
    """Return the complete local record set for trusted summaries and reports."""
    migrate()
    clauses = []
    params: list[Any] = []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(connect()) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM wecom_records
            {where_sql}
            ORDER BY id DESC
            """,
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def export_records_xlsx(path: Path | None = None) -> Path:
    """Export the staff-facing work-order workbook.

    SQLite remains the complete audit store. The Excel file intentionally
    contains only operational columns staff need and excludes technical IDs,
    raw metadata, routing diagnostics, API fields, and resident identifiers.
    """
    migrate()
    output_path = path or get_records_xlsx_path()

    with _excel_export_lock(output_path):
        with closing(connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM wecom_records
                WHERE kind = 'work_order'
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        values = [_staff_work_order_values(_row_to_dict(row)) for row in rows]
        headers = [header for _key, header, _width in STAFF_WORK_ORDER_COLUMNS]
        widths = [width for _key, _header, width in STAFF_WORK_ORDER_COLUMNS]

        exported_path = write_xlsx(
            output_path,
            sheet_name="工单台账",
            headers=headers,
            rows=values,
            column_widths=widths,
        )
        if path is None:
            _mirror_records_xlsx(exported_path)
        return exported_path


def export_records_xlsx_safely(path: Path | None = None) -> tuple[Path, str]:
    """Refresh the workbook without blocking ticket storage or notification.

    Excel on Windows locks an open workbook and prevents atomic replacement.
    SQLite remains authoritative, so callers can continue their operational
    workflow and refresh the workbook after staff close it.
    """
    output_path = path or get_records_xlsx_path()
    try:
        return export_records_xlsx(path), ""
    except PermissionError as exc:
        return output_path, (
            "Excel workbook refresh is pending because the file is open or locked. "
            f"Close the workbook and run `reins wecom records export`: {exc}"
        )



def records_report(kind: str | None = None) -> dict[str, Any]:
    records = list_records(limit=500, kind=kind)
    export_path, export_error = export_records_xlsx_safely()

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
        "records_xlsx_ok": not export_error,
        "records_xlsx_error": export_error,
        "visible_records_xlsx_path": str(get_visible_records_xlsx_path() or ""),
        "records_xlsx_scope": "work_order_staff_view",
        "records_xlsx_columns": [header for _key, header, _width in STAFF_WORK_ORDER_COLUMNS],
    }


def doctor() -> dict[str, Any]:
    from reins.features.wecom.notifier import notification_doctor
    from reins.features.wecom.routing import routing_doctor

    migrate()
    records_path, export_error = export_records_xlsx_safely()

    with closing(connect()) as connection:
        record_count = int(connection.execute("SELECT COUNT(*) FROM wecom_records").fetchone()[0])
        reply_count = int(connection.execute("SELECT COUNT(*) FROM wecom_replies").fetchone()[0])

    return {
        "ok": True,
        "wecom_dir": str(get_wecom_dir()),
        "db_path": str(get_db_path()),
        "faq_path": str(get_faq_path()),
        "records_xlsx_path": str(records_path),
        "records_xlsx_ok": not export_error,
        "records_xlsx_error": export_error,
        "visible_records_xlsx_path": str(get_visible_records_xlsx_path() or ""),
        "records_xlsx_scope": "work_order_staff_view",
        "records_xlsx_columns": [header for _key, header, _width in STAFF_WORK_ORDER_COLUMNS],
        "record_count": record_count,
        "reply_count": reply_count,
        "routing": routing_doctor(),
        "notifications": notification_doctor(),
    }
