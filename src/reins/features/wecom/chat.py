from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from reins.compat.paths import ensure_reins_workspace
from reins.features.wecom.store import (
    export_records_xlsx_safely,
    find_record_by_metadata,
    get_record,
    list_all_records,
)


try:
    _CHINA_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # Windows may not ship the IANA timezone database.
    _CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PRIVATE_LINE_RE = re.compile(
    r"^\s*(?:[-·]\s*)?(?:居民标识|客户标识|微信客户|联系方式|联系电话|手机|电话)\s*[：:].*$"
)
_PENDING_STATUSES = {"new", "open", "pending_notification", "waiting_human_review"}
_COMPLETED_STATUSES = {"resolved", "closed"}
_URGENT_PRIORITIES = {"high", "urgent", "critical", "emergency", "紧急", "优先"}
_FAILED_NOTIFICATION_STATUSES = {"failed", "pending_configuration"}
_STATUS_ALIASES = {
    "处理中": "processing",
    "已关闭": "closed",
    "待人工审核": "waiting_human_review",
    "待通知": "pending_notification",
}
_PRIORITY_ALIASES = {
    "紧急": "high",
    "优先": "high",
    "普通": "normal",
    "低": "low",
}


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("metadata")
    return value if isinstance(value, dict) else {}


def _first(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _staff_safe_text(value: Any) -> str:
    lines = [
        line
        for line in _clean(value).splitlines()
        if not _PRIVATE_LINE_RE.match(line)
    ]
    return _PHONE_RE.sub("[已隐藏联系方式]", "\n".join(lines)).strip()


def _parse_record_datetime(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    normalized = (
        text.replace("（北京时间）", "")
        .replace("(北京时间)", "")
        .replace(" CST", "")
        .strip()
    )
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, pattern)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_CHINA_TZ)
    return parsed


def _record_datetime(record: dict[str, Any]) -> datetime | None:
    metadata = _metadata(record)
    return _parse_record_datetime(
        _first(
            metadata.get("ticket_created_at"),
            metadata.get("api_created_at"),
            record.get("created_at"),
        )
    )


def _parse_date(value: str | None, field: str) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format") from exc


def _status_values(value: Any) -> set[str]:
    status = _clean(value)
    if status == "待处理":
        return _PENDING_STATUSES
    if status in {"已完成", "已解决"}:
        return _COMPLETED_STATUSES
    normalized = _STATUS_ALIASES.get(status, status).lower()
    return {normalized} if normalized else set()


def _safe_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(record)
    title = _staff_safe_text(metadata.get("title"))
    description = _staff_safe_text(metadata.get("description"))
    issue = description or title or _staff_safe_text(record.get("message"))
    if title and description and title not in description:
        issue = f"{title}\n{description}"
    recipients = metadata.get("notification_recipients")
    assignees = (
        [_clean(item) for item in recipients if _clean(item)]
        if isinstance(recipients, list)
        else []
    )
    explicit_assignee = _clean(metadata.get("assignee"))
    if explicit_assignee and explicit_assignee not in assignees:
        assignees.insert(0, explicit_assignee)

    return {
        "id": int(record.get("id") or 0),
        "external_id": _first(
            metadata.get("external_id"),
            metadata.get("ticket_id"),
            metadata.get("api_ticket_id"),
            record.get("id"),
        ),
        "created_at": _first(
            metadata.get("ticket_created_at"),
            metadata.get("api_created_at"),
            record.get("created_at"),
        ),
        "updated_at": _first(
            metadata.get("last_staff_reply_at"),
            metadata.get("api_updated_at"),
            metadata.get("notified_at"),
            metadata.get("analyzed_at"),
            record.get("created_at"),
        ),
        "status": _clean(record.get("status")),
        "priority": _clean(metadata.get("priority")),
        "category": _clean(metadata.get("category")),
        "assigned_role": _clean(metadata.get("assigned_role")),
        "assigned_role_label": _first(
            metadata.get("assigned_role_label"),
            metadata.get("assigned_role"),
        ),
        "assignees": assignees,
        "location": _staff_safe_text(metadata.get("location")),
        "title": title,
        "issue": issue,
        "handling_requirements": _staff_safe_text(metadata.get("handling_requirements")),
        "notification_status": _clean(metadata.get("notification_status")),
        "result": _staff_safe_text(_first(metadata.get("last_staff_reply"), record.get("reply"))),
        "responder": _first(metadata.get("last_staff_responder"), metadata.get("assignee")),
        "source_channel": _clean(metadata.get("source_channel")),
        "assignment_reason": _staff_safe_text(metadata.get("assignment_reason")),
    }


def _filtered_records(
    *,
    search: str = "",
    status: str = "",
    priority: str = "",
    role: str = "",
    category: str = "",
    notification_status: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start and end and start > end:
        raise ValueError("start_date must not be after end_date")

    wanted_statuses = _status_values(status)
    wanted_priority = _PRIORITY_ALIASES.get(_clean(priority), _clean(priority)).lower()
    wanted_role = _clean(role).lower()
    wanted_category = _clean(category).lower()
    wanted_notification = _clean(notification_status).lower()
    wanted_search = _clean(search).lower()
    result: list[dict[str, Any]] = []

    for raw_record in list_all_records(kind="work_order"):
        record = _safe_record(raw_record)
        if wanted_statuses and record["status"].lower() not in wanted_statuses:
            continue
        if wanted_priority and record["priority"].lower() != wanted_priority:
            continue
        if wanted_role and wanted_role not in {
            record["assigned_role"].lower(),
            record["assigned_role_label"].lower(),
        }:
            continue
        if wanted_category and record["category"].lower() != wanted_category:
            continue
        if wanted_notification and record["notification_status"].lower() != wanted_notification:
            continue
        created = _record_datetime(raw_record)
        if start and (created is None or created.date() < start):
            continue
        if end and (created is None or created.date() > end):
            continue
        if wanted_search:
            searchable = " ".join(
                [
                    record["external_id"],
                    record["location"],
                    record["title"],
                    record["issue"],
                    record["category"],
                    record["assigned_role_label"],
                    " ".join(record["assignees"]),
                    record["result"],
                ]
            ).lower()
            if wanted_search not in searchable:
                continue
        result.append(record)
    return result


def list_work_orders(**filters: Any) -> dict[str, Any]:
    limit = max(1, min(int(filters.pop("limit", 20) or 20), 100))
    records = _filtered_records(**filters)
    return {
        "ok": True,
        "total": len(records),
        "limit": limit,
        "truncated": len(records) > limit,
        "records": records[:limit],
    }


def get_work_order(identifier: str | int) -> dict[str, Any]:
    value = _clean(identifier)
    if not value:
        return {
            "ok": False,
            "needs_clarification": True,
            "question_zh": "请提供工单编号，例如 t_123456。",
        }
    record: dict[str, Any] | None = None
    if value.isdigit():
        record = get_record(int(value))
        if record and record.get("kind") != "work_order":
            record = None
    if record is None:
        for key in ("external_id", "ticket_id", "api_ticket_id"):
            record = find_record_by_metadata(key, value, kind="work_order")
            if record:
                break
    if record is None:
        return {"ok": False, "not_found": True, "message_zh": f"未找到工单 {value}。"}
    return {"ok": True, "record": _safe_record(record)}


def summarize_work_orders(**filters: Any) -> dict[str, Any]:
    records = _filtered_records(**filters)

    def count(field: str) -> dict[str, int]:
        values = Counter(_clean(record.get(field)) for record in records)
        values.pop("", None)
        return dict(values)

    return {
        "ok": True,
        "total": len(records),
        "pending": sum(1 for item in records if item["status"].lower() in _PENDING_STATUSES),
        "processing": sum(1 for item in records if item["status"].lower() == "processing"),
        "urgent": sum(1 for item in records if item["priority"].lower() in _URGENT_PRIORITIES),
        "notification_failed": sum(
            1 for item in records if item["notification_status"].lower() in _FAILED_NOTIFICATION_STATUSES
        ),
        "completed": sum(1 for item in records if item["status"].lower() in _COMPLETED_STATUSES),
        "by_status": count("status"),
        "by_priority": count("priority"),
        "by_category": count("category"),
        "by_assigned_role": count("assigned_role_label"),
        "by_source_channel": count("source_channel"),
        "latest_records": records[:10],
    }


def export_work_orders_excel() -> dict[str, Any]:
    output_dir = ensure_reins_workspace() / "Generated" / "Work Orders"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "社区工单台账.xlsx"
    exported, error = export_records_xlsx_safely(output_path)
    if error:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        exported, error = export_records_xlsx_safely(
            output_dir / f"社区工单台账-{timestamp}.xlsx"
        )
    return {
        "ok": not error and Path(exported).is_file(),
        "path": str(exported),
        "file_name": Path(exported).name,
        "workspace_relative_path": str(Path("Generated") / "Work Orders" / Path(exported).name),
        "error": error,
    }
