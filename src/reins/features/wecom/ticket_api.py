from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from reins.api.home import get_reins_home
from reins.features.wecom.notifier import notification_doctor
from reins.features.wecom.routing import routing_doctor
from reins.features.wecom.work_order import create_work_order


DEFAULT_API_URL = "https://kf.lnluo.com/internal/tickets"
SUPPORTED_STATUSES = {
    "pending_dispatch",
    "dispatched",
    "processing",
    "reopened",
    "notification_failed",
}
DEFAULT_NOTIFY_STATUSES = (
    "pending_dispatch",
    "dispatched",
    "reopened",
    "notification_failed",
)


class TicketAPIError(RuntimeError):
    pass


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _positive_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _positive_float(value: Any, *, default: float, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def parse_statuses(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_NOTIFY_STATUSES
    raw_values = [value] if isinstance(value, str) else list(value)
    statuses: list[str] = []
    for raw in raw_values:
        for status in str(raw or "").replace("|", ",").split(","):
            clean = status.strip()
            if not clean:
                continue
            if clean not in SUPPORTED_STATUSES:
                choices = ", ".join(sorted(SUPPORTED_STATUSES))
                raise ValueError(f"unsupported ticket status {clean!r}; choose from: {choices}")
            if clean not in statuses:
                statuses.append(clean)
    return tuple(statuses)


@dataclass(frozen=True)
class TicketAPIConfig:
    url: str
    token: str
    statuses: tuple[str, ...]
    limit: int
    poll_interval: float
    timeout: float
    cursor_path: Path

    @classmethod
    def from_env(
        cls,
        *,
        url: str | None = None,
        token: str | None = None,
        statuses: Sequence[str] | str | None = None,
        limit: int | None = None,
        poll_interval: float | None = None,
        timeout: float | None = None,
        cursor_path: str | Path | None = None,
    ) -> "TicketAPIConfig":
        env_statuses = os.environ.get("REINS_TICKET_API_STATUSES")
        selected_statuses = statuses if statuses is not None else env_statuses
        selected_cursor = cursor_path or os.environ.get("REINS_TICKET_API_CURSOR_PATH")
        return cls(
            url=(url or os.environ.get("REINS_TICKET_API_URL") or DEFAULT_API_URL).strip(),
            token=(token if token is not None else os.environ.get("REINS_TICKET_API_TOKEN", "")).strip(),
            statuses=parse_statuses(selected_statuses),
            limit=_positive_int(
                limit if limit is not None else os.environ.get("REINS_TICKET_API_LIMIT"),
                default=20,
                minimum=1,
                maximum=100,
            ),
            poll_interval=_positive_float(
                poll_interval if poll_interval is not None else os.environ.get("REINS_TICKET_API_POLL_INTERVAL"),
                default=30.0,
                minimum=5.0,
            ),
            timeout=_positive_float(
                timeout if timeout is not None else os.environ.get("REINS_TICKET_API_TIMEOUT"),
                default=15.0,
                minimum=1.0,
            ),
            cursor_path=Path(os.path.expandvars(str(selected_cursor))).expanduser()
            if selected_cursor
            else get_reins_home() / "wecom" / "ticket-api-cursor.json",
        )

    def validate(self, *, require_token: bool = True) -> None:
        parsed = urlsplit(self.url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not local_http:
            raise TicketAPIError("REINS_TICKET_API_URL must use HTTPS (HTTP is allowed only for localhost tests).")
        if not parsed.netloc:
            raise TicketAPIError("REINS_TICKET_API_URL is invalid.")
        if require_token and not self.token:
            raise TicketAPIError("missing REINS_TICKET_API_TOKEN")


def load_cursor(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise TicketAPIError(f"could not read ticket API cursor {path}: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


def save_cursor(path: Path, since: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "since": since,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def clear_cursor(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _format_since_for_api(value: str) -> str:
    clean = value.strip()
    if not clean:
        return ""
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return clean.replace("T", " ", 1)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(sep=" ", timespec="seconds")


def _request_url(base_url: str, *, status: str, since: str, limit: int) -> str:
    parsed = urlsplit(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if status:
        query["status"] = status
    if since:
        query["since"] = _format_since_for_api(since)
    query["limit"] = str(limit)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _error_detail(body: str) -> str:
    clean = " ".join(body.strip().split())
    if not clean:
        return ""
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError:
        return clean[:300]
    if isinstance(payload, dict):
        return _string(payload.get("message") or payload.get("error") or payload.get("detail"))[:300]
    return ""


def _extract_ticket_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise TicketAPIError("ticket API response must be a JSON object or array")

    for key in ("tickets", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return _extract_ticket_list(data)

    if "content_markdown" in payload and ("id" in payload or "case_id" in payload):
        return [payload]
    if not payload:
        return []
    raise TicketAPIError("ticket API response does not contain a tickets/items/data array")


def _fetch_one(
    config: TicketAPIConfig,
    *,
    status: str,
    since: str,
    opener: Callable[..., Any],
) -> list[dict[str, Any]]:
    request = Request(
        _request_url(config.url, status=status, since=since, limit=config.limit),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {config.token}",
            "User-Agent": "Reins-Ticket-Poller/0.1",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=config.timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail = _error_detail(body)
        suffix = f": {detail}" if detail else ""
        raise TicketAPIError(f"ticket API returned HTTP {exc.code}{suffix}") from exc
    except URLError as exc:
        raise TicketAPIError(f"could not connect to ticket API: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TicketAPIError("ticket API returned invalid JSON") from exc
    return _extract_ticket_list(payload)


def _ticket_key(ticket: dict[str, Any]) -> str:
    key = _string(ticket.get("id") or ticket.get("case_id"))
    if key:
        return key
    content = _string(ticket.get("content_markdown"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fetch_tickets(
    config: TicketAPIConfig,
    *,
    since: str = "",
    opener: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    config.validate()
    open_request = opener or urlopen
    statuses: Iterable[str] = config.statuses or ("",)
    tickets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for status in statuses:
        for ticket in _fetch_one(config, status=status, since=since, opener=open_request):
            key = _ticket_key(ticket)
            if key in seen:
                continue
            seen.add(key)
            tickets.append(ticket)
    return tickets


def inspect_tickets(
    config: TicketAPIConfig,
    *,
    since: str = "",
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    tickets = fetch_tickets(config, since=since, opener=opener)
    return {
        "ok": True,
        "statuses": list(config.statuses),
        "since": since,
        "fetched": len(tickets),
        "tickets": [
            {
                key: _string(ticket.get(key))
                for key in (
                    "id",
                    "case_id",
                    "status",
                    "priority",
                    "category",
                    "created_at",
                    "dispatched_at",
                    "updated_at",
                )
                if _string(ticket.get(key))
            }
            for ticket in tickets
        ],
    }


def _parse_timestamp(value: str) -> datetime | None:
    clean = value.strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ticket_timestamp(ticket: dict[str, Any]) -> str:
    candidates = [
        _string(ticket.get(key))
        for key in ("updated_at", "created_at", "generated_at", "ticket_created_at")
    ]
    parsed = [(timestamp, _parse_timestamp(timestamp)) for timestamp in candidates if timestamp]
    valid = [(timestamp, value) for timestamp, value in parsed if value is not None]
    if valid:
        return max(valid, key=lambda item: item[1])[0]
    return candidates[0] if candidates else ""


def _latest_timestamp(tickets: Sequence[dict[str, Any]]) -> str:
    values = [(value, _parse_timestamp(value)) for value in (_ticket_timestamp(item) for item in tickets) if value]
    valid = [(value, parsed) for value, parsed in values if parsed is not None]
    if valid:
        return max(valid, key=lambda item: item[1])[0]
    return max((value for value, _parsed in values), default="")


def ticket_to_work_order_payload(ticket: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    content = _string(ticket.get("content_markdown"))
    if not content:
        raise ValueError("ticket is missing content_markdown")

    api_ticket_id = _string(ticket.get("id"))
    api_case_id = _string(ticket.get("case_id"))
    external_id = api_ticket_id or api_case_id
    api_status = _string(ticket.get("status"))
    created_at = _string(ticket.get("created_at") or ticket.get("generated_at"))
    updated_at = _string(ticket.get("updated_at"))
    priority = _string(ticket.get("priority") or ticket.get("priority_label"))
    category = _string(ticket.get("category"))
    notification_event_key = "|".join(
        value for value in (external_id, api_status, updated_at or created_at) if value
    )

    metadata = {
        key: value
        for key, value in {
            "external_id": external_id,
            "ticket_created_at": created_at,
            "priority": priority,
            "upstream_status": api_status,
            "api_category": category,
            "api_ticket_id": api_ticket_id,
            "api_case_id": api_case_id,
            "api_status": api_status,
            "api_created_at": created_at,
            "api_updated_at": updated_at,
            "api_received_at": datetime.now(timezone.utc).isoformat(),
            "notification_event_key": notification_event_key,
        }.items()
        if value
    }
    return {
        "message": content,
        "metadata": metadata,
        "chat_type": "ticket_api",
        "platform": "ticket_api",
        "notify": True,
        "force_notify": api_status in {"reopened", "notification_failed"},
        "dry_run": dry_run,
    }


def _ticket_summary(ticket: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    record = result.get("record") if isinstance(result.get("record"), dict) else {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    notification = result.get("notification") if isinstance(result.get("notification"), dict) else {}
    return {
        "id": _string(ticket.get("id")),
        "case_id": _string(ticket.get("case_id")),
        "api_status": _string(ticket.get("status")),
        "api_created_at": _string(ticket.get("created_at")),
        "api_dispatched_at": _string(ticket.get("dispatched_at")),
        "external_id": _string(metadata.get("external_id")),
        "duplicate": bool(result.get("duplicate")),
        "category": _string(metadata.get("category")),
        "assigned_role": _string(metadata.get("assigned_role")),
        "assigned_roles": (
            metadata.get("assigned_roles")
            if isinstance(metadata.get("assigned_roles"), list)
            else []
        ),
        "assignment_reason": _string(metadata.get("assignment_reason")),
        "routing_source": _string(metadata.get("routing_source")),
        "routing_confidence": metadata.get("routing_confidence"),
        "routing_error": _string(metadata.get("routing_error")),
        "notification_channel": _string(notification.get("channel")),
        "notification_recipient_env": _string(notification.get("recipient_env")),
        "notification_recipient_envs": (
            notification.get("recipient_envs")
            if isinstance(notification.get("recipient_envs"), list)
            else []
        ),
        "notification_recipient_count": len(
            notification.get("recipients")
            if isinstance(notification.get("recipients"), list)
            else []
        ),
        "notification_status": _string(notification.get("status")),
        "notification_error": _string(notification.get("error")),
    }


def poll_once(
    config: TicketAPIConfig,
    *,
    since: str | None = None,
    dry_run: bool = False,
    opener: Callable[..., Any] | None = None,
    processor: Callable[[dict[str, Any]], dict[str, Any]] = create_work_order,
) -> dict[str, Any]:
    cursor = load_cursor(config.cursor_path)
    effective_since = since if since is not None else _string(cursor.get("since"))
    tickets = fetch_tickets(config, since=effective_since, opener=opener)
    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    notification_failures = 0

    for ticket in tickets:
        try:
            result = processor(ticket_to_work_order_payload(ticket, dry_run=dry_run))
            summary = _ticket_summary(ticket, result)
            summaries.append(summary)
            status = summary["notification_status"]
            if status not in {"sent", "skipped_duplicate", "dry_run", "disabled"}:
                notification_failures += 1
        except Exception as exc:
            errors.append(
                {
                    "id": _string(ticket.get("id")),
                    "case_id": _string(ticket.get("case_id")),
                    "error": str(exc),
                }
            )

    next_since = _latest_timestamp(tickets)
    can_advance = bool(next_since) and not dry_run and not errors and notification_failures == 0
    if can_advance:
        save_cursor(config.cursor_path, next_since)

    return {
        "ok": not errors and notification_failures == 0,
        "statuses": list(config.statuses),
        "fetched": len(tickets),
        "processed": len(summaries),
        "duplicates": sum(1 for item in summaries if item["duplicate"]),
        "notifications_sent": sum(1 for item in summaries if item["notification_status"] == "sent"),
        "notifications_skipped": sum(
            1
            for item in summaries
            if item["notification_status"] in {"skipped_duplicate", "disabled"}
        ),
        "notification_failures": notification_failures,
        "since": effective_since,
        "next_since": next_since,
        "cursor_advanced": can_advance,
        "cursor_path": str(config.cursor_path),
        "dry_run": dry_run,
        "tickets": summaries,
        "errors": errors,
    }


def poll_forever(
    config: TicketAPIConfig,
    *,
    since: str | None = None,
    dry_run: bool = False,
    emit: Callable[[dict[str, Any]], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    first_since = since
    while True:
        try:
            result = poll_once(config, since=first_since, dry_run=dry_run)
        except Exception as exc:
            result = {
                "ok": False,
                "statuses": list(config.statuses),
                "fetched": 0,
                "processed": 0,
                "notification_failures": 0,
                "error": str(exc),
            }
        first_since = None
        if emit:
            emit(result)
        sleep(config.poll_interval)


def ticket_api_doctor(config: TicketAPIConfig) -> dict[str, Any]:
    validation_error = ""
    try:
        config.validate(require_token=False)
    except TicketAPIError as exc:
        validation_error = str(exc)
    cursor_error = ""
    try:
        cursor = load_cursor(config.cursor_path)
    except TicketAPIError as exc:
        cursor = {}
        cursor_error = str(exc)
    routing = routing_doctor()
    return {
        "ok": not validation_error and bool(config.token) and bool(routing.get("mode_valid")),
        "api_url": config.url,
        "api_token_configured": bool(config.token),
        "statuses": list(config.statuses),
        "limit": config.limit,
        "poll_interval": config.poll_interval,
        "timeout": config.timeout,
        "cursor_path": str(config.cursor_path),
        "cursor": cursor,
        "validation_error": validation_error,
        "cursor_error": cursor_error,
        "routing": routing,
        "notification": notification_doctor(),
    }
