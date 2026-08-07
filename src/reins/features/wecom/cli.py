from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from typing import Any, Sequence

from dotenv import load_dotenv

from reins.api.home import get_reins_home
from reins.features.wecom.docx_importer import import_docx_faq
from reins.features.wecom.engine import add_faq_entry, export_records, load_faq_entries, process_message
from reins.features.wecom.plugin_installer import install_hermes_plugin, print_install_instructions
from reins.features.wecom.store import doctor, list_records, records_report
from reins.features.wecom.ticket_api import (
    TicketAPIConfig,
    clear_cursor,
    inspect_tickets,
    load_cursor,
    poll_forever,
    poll_once,
    save_cursor,
    ticket_api_doctor,
)
from reins.features.wecom.ticket_service import (
    install_service,
    service_status,
    start_service,
    stop_service,
    uninstall_service,
)
from reins.features.wecom.work_order import create_work_order, notify_work_order, record_staff_reply


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reins wecom",
        description="Reins WeCom work-order intake, Excel ledger, staff notification, and reply update tools.",
    )
    subparsers = parser.add_subparsers(dest="command")

    process_parser = subparsers.add_parser(
        "process",
        help="Legacy: process a single inbound WeCom message through the old FAQ/complaint path.",
    )
    process_parser.add_argument("--message", required=True, help="Inbound message text.")
    process_parser.add_argument("--sender-id", default="", help="WeCom sender user ID.")
    process_parser.add_argument("--sender-name", default="", help="Human-readable sender name.")
    process_parser.add_argument("--chat-id", default="", help="WeCom chat/group ID.")
    process_parser.add_argument("--chat-type", default="", help="DM or group chat type.")
    process_parser.add_argument("--platform", default="wecom", help="Source platform label.")
    process_parser.add_argument("--record-kind", default="", help="Force saving this message as complaint, feedback, lead, etc.")
    process_parser.add_argument("--metadata-json", default="", help="Extra metadata as JSON.")
    process_parser.add_argument("--match-threshold", type=float, default=0.72, help="FAQ match threshold.")
    process_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    faq_parser = subparsers.add_parser("faq", help="Legacy: manage approved fixed answers.")
    faq_subparsers = faq_parser.add_subparsers(dest="faq_command")

    faq_add_parser = faq_subparsers.add_parser("add", help="Add or replace an approved fixed answer.")
    faq_add_parser.add_argument("--id", default="", help="Stable FAQ ID. Generated when omitted.")
    faq_add_parser.add_argument("--meaning", required=True, help="Approved meaning label.")
    faq_add_parser.add_argument("--answer", required=True, help="Approved answer text.")
    faq_add_parser.add_argument("--question", action="append", default=[], help="Example user question.")
    faq_add_parser.add_argument("--keyword", action="append", default=[], help="Keyword that should match.")
    faq_add_parser.add_argument("--pattern", action="append", default=[], help="Regex pattern that should match.")
    faq_add_parser.add_argument("--disabled", action="store_true", help="Create the entry disabled.")
    faq_add_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    faq_list_parser = faq_subparsers.add_parser("list", help="List approved fixed answers.")
    faq_list_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    faq_import_parser = faq_subparsers.add_parser("import-docx", help="Import approved fixed answers from a Word table.")
    faq_import_parser.add_argument("--file", required=True, help="Path to the .docx FAQ table.")
    faq_import_parser.add_argument("--community", default="", help="Community name. Inferred from filename when omitted.")
    faq_import_parser.add_argument(
        "--include-template-examples",
        action="store_true",
        help="Also import rows before a numbering restart. By default template examples are skipped when detected.",
    )
    faq_import_parser.add_argument("--dry-run", action="store_true", help="Preview import without writing faq.json.")
    faq_import_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    records_parser = subparsers.add_parser("records", help="Inspect captured WeCom records.")
    records_subparsers = records_parser.add_subparsers(dest="records_command")

    records_list_parser = records_subparsers.add_parser("list", help="List captured records.")
    records_list_parser.add_argument("--limit", type=int, default=50, help="Maximum records to show.")
    records_list_parser.add_argument("--kind", default="", help="Filter by record kind.")
    records_list_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    records_export_parser = records_subparsers.add_parser("export", help="Export the staff-facing work-order Excel file.")
    records_export_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    records_report_parser = records_subparsers.add_parser("report", help="Summarize captured records.")
    records_report_parser.add_argument("--kind", default="", help="Filter by record kind.")
    records_report_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    work_order_parser = subparsers.add_parser("work-order", help="Capture a WeCom work order into records and Excel.")
    work_order_subparsers = work_order_parser.add_subparsers(dest="work_order_command")

    work_order_add_parser = work_order_subparsers.add_parser("add", help="Add a structured work order record.")
    work_order_add_parser.add_argument("--payload-json", default="", help="Full work order payload as a JSON object.")
    work_order_add_parser.add_argument("--metadata-json", default="", help="Extra metadata as a JSON object.")
    work_order_add_parser.add_argument("--external-id", default="", help="External ticket/work-order ID.")
    work_order_add_parser.add_argument("--ticket-created-at", default="", help="Original ticket creation timestamp.")
    work_order_add_parser.add_argument("--title", default="", help="Short work order title.")
    work_order_add_parser.add_argument("--description", default="", help="Detailed resident request or problem description.")
    work_order_add_parser.add_argument("--message", default="", help="Raw formatted work order message.")
    work_order_add_parser.add_argument("--resident-ref", default="", help="Redacted resident/customer reference.")
    work_order_add_parser.add_argument("--resident-name", default="", help="Resident/customer name.")
    work_order_add_parser.add_argument("--resident-contact", default="", help="Resident contact phone or handle.")
    work_order_add_parser.add_argument("--location", default="", help="Community, building, room, or address.")
    work_order_add_parser.add_argument("--category", default="", help="Work order category.")
    work_order_add_parser.add_argument("--priority", default="", help="Priority or urgency.")
    work_order_add_parser.add_argument("--assigned-role", default="", help="Responsible role such as property, cleaning, police, hospital, or community.")
    work_order_add_parser.add_argument("--source-channel", default="", help="Original source channel, such as wechat_customer_service.")
    work_order_add_parser.add_argument("--assignee", default="", help="Owner or handler.")
    work_order_add_parser.add_argument("--due-at", default="", help="Expected due time.")
    work_order_add_parser.add_argument("--status", default="", help="Initial status.")
    work_order_add_parser.add_argument("--kind", default="work_order", help="Record kind.")
    work_order_add_parser.add_argument("--sender-id", default="", help="WeCom sender/external user ID.")
    work_order_add_parser.add_argument("--sender-name", default="", help="Human-readable sender name.")
    work_order_add_parser.add_argument("--chat-id", default="", help="WeCom chat/conversation ID.")
    work_order_add_parser.add_argument("--chat-type", default="work_order", help="Conversation type.")
    work_order_add_parser.add_argument("--platform", default="wecom", help="Source platform label.")
    work_order_add_parser.add_argument("--notify", action="store_true", help="Notify the responsible WeCom target after recording.")
    work_order_add_parser.add_argument("--force-notify", action="store_true", help="Notify again even when this is an exact duplicate ticket.")
    work_order_add_parser.add_argument(
        "--force-reroute",
        action="store_true",
        help="Recompute a persisted routing decision, including the Hermes fallback when needed.",
    )
    work_order_add_parser.add_argument("--dry-run", action="store_true", help="Build the notification without sending it.")
    work_order_add_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    work_order_notify_parser = work_order_subparsers.add_parser("notify", help="Notify staff for an existing work order.")
    work_order_notify_parser.add_argument("--record-id", default="", help="Local record ID.")
    work_order_notify_parser.add_argument("--external-id", default="", help="External ticket/work-order ID.")
    work_order_notify_parser.add_argument("--dry-run", action="store_true", help="Build the notification without sending it.")
    work_order_notify_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    work_order_reply_parser = work_order_subparsers.add_parser("reply", help="Record staff feedback and update a work order.")
    work_order_reply_parser.add_argument("--payload-json", default="", help="Full reply payload as a JSON object.")
    work_order_reply_parser.add_argument("--record-id", default="", help="Local record ID.")
    work_order_reply_parser.add_argument("--external-id", default="", help="External ticket/work-order ID.")
    work_order_reply_parser.add_argument("--message", required=False, default="", help="Staff reply or handling result.")
    work_order_reply_parser.add_argument("--responder", default="", help="Staff member or team that replied.")
    work_order_reply_parser.add_argument("--status", default="", help="New ticket status. Inferred when omitted.")
    work_order_reply_parser.add_argument("--replied-at", default="", help="Reply timestamp.")
    work_order_reply_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    ticket_api_parser = subparsers.add_parser(
        "ticket-api",
        help="Poll the internal ticket API and notify responsible staff in the shared WeCom group.",
    )
    ticket_api_subparsers = ticket_api_parser.add_subparsers(dest="ticket_api_command")

    ticket_poll_parser = ticket_api_subparsers.add_parser("poll", help="Fetch and process available tickets.")
    ticket_poll_parser.add_argument("--url", default=None, help="Override REINS_TICKET_API_URL.")
    ticket_poll_parser.add_argument("--since", default=None, help="Override the saved ISO-8601 cursor for this run.")
    ticket_poll_parser.add_argument(
        "--status",
        action="append",
        default=None,
        help="Status to fetch; repeat or use comma-separated values.",
    )
    ticket_poll_parser.add_argument("--limit", type=int, default=None, help="Tickets per API request (1-100).")
    ticket_poll_parser.add_argument("--interval", type=float, default=None, help="Watch interval in seconds (minimum 5).")
    ticket_poll_parser.add_argument("--timeout", type=float, default=None, help="HTTP timeout in seconds.")
    ticket_poll_parser.add_argument("--cursor-path", default=None, help="Override the local cursor JSON path.")
    ticket_poll_parser.add_argument("--watch", action="store_true", help="Continue polling until interrupted.")
    ticket_poll_parser.add_argument("--dry-run", action="store_true", help="Classify and preview without sending or advancing the cursor.")
    ticket_poll_parser.add_argument("--reset-cursor", action="store_true", help="Remove the saved cursor before polling.")
    ticket_poll_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")
    ticket_poll_parser.add_argument("--json-lines", action="store_true", help="Print one compact JSON object per watch cycle.")

    ticket_doctor_parser = ticket_api_subparsers.add_parser("doctor", help="Check ticket API and WeCom notification configuration.")
    ticket_doctor_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    ticket_inspect_parser = ticket_api_subparsers.add_parser(
        "inspect",
        help="Read sanitized ticket metadata without recording or notifying.",
    )
    ticket_inspect_parser.add_argument("--url", default=None, help="Override REINS_TICKET_API_URL.")
    ticket_inspect_parser.add_argument("--since", default="", help="Optional ISO-8601 lower bound; empty means no cursor.")
    ticket_inspect_parser.add_argument(
        "--status",
        action="append",
        default=[],
        help="Optional status filter; omit it to use the API default.",
    )
    ticket_inspect_parser.add_argument("--limit", type=int, default=5, help="Tickets per API request (1-100).")
    ticket_inspect_parser.add_argument("--timeout", type=float, default=None, help="HTTP timeout in seconds.")
    ticket_inspect_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    ticket_cursor_parser = ticket_api_subparsers.add_parser("cursor", help="Show, set, or reset the polling cursor.")
    ticket_cursor_actions = ticket_cursor_parser.add_mutually_exclusive_group()
    ticket_cursor_actions.add_argument("--set", dest="cursor_since", default="", help="Set an ISO-8601 since value.")
    ticket_cursor_actions.add_argument("--now", action="store_true", help="Start watching from the current UTC time.")
    ticket_cursor_actions.add_argument("--reset", action="store_true", help="Remove the saved cursor.")
    ticket_cursor_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    ticket_service_parser = ticket_api_subparsers.add_parser(
        "service",
        help="Manage the background ticket poller on macOS, Windows, or Linux.",
    )
    ticket_service_subparsers = ticket_service_parser.add_subparsers(dest="ticket_service_command")
    ticket_service_install = ticket_service_subparsers.add_parser(
        "install",
        help="Install and start the launchd, Task Scheduler, or systemd poller.",
    )
    ticket_service_install.add_argument("--interval", type=float, default=None, help="Poll interval in seconds (minimum 5).")
    ticket_service_install.add_argument(
        "--replay-existing",
        action="store_true",
        help="Process existing matching tickets instead of starting from the current time.",
    )
    for service_command in ("start", "stop", "status", "uninstall"):
        ticket_service_subparsers.add_parser(service_command)

    doctor_parser = subparsers.add_parser("doctor", help="Check WeCom processor storage.")
    doctor_parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON.")

    subparsers.add_parser("install-plugin", help="Install the Reins WeCom tools for Hermes profiles.")

    return parser


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _print(value: Any, *, json_output: bool) -> None:
    if json_output:
        print(_json(value))
        return

    if isinstance(value, dict):
        if value.get("reply"):
            print(value["reply"])
        elif value.get("ai_fallback"):
            print("No fixed answer matched. Hand off to Hermes AI.")
            if value.get("record_saved"):
                print(f"Record saved: {value.get('records_xlsx_path')}")
        elif value.get("ok"):
            for key, item in value.items():
                print(f"{key}: {item}")
        else:
            print(_json(value))
    else:
        print(_json(value))


def _print_json_line(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def _load_wecom_env() -> None:
    env_path = get_reins_home() / ".env"
    try:
        load_dotenv(env_path, override=False, encoding="utf-8-sig")
    except UnicodeDecodeError:
        load_dotenv(env_path, override=False, encoding="latin-1")


def _ticket_api_config(args: argparse.Namespace) -> TicketAPIConfig:
    return TicketAPIConfig.from_env(
        url=getattr(args, "url", None),
        statuses=getattr(args, "status", None),
        limit=getattr(args, "limit", None),
        poll_interval=getattr(args, "interval", None),
        timeout=getattr(args, "timeout", None),
        cursor_path=getattr(args, "cursor_path", None),
    )


def _metadata(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("--metadata-json must be a JSON object.")
    return value


def _work_order_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _metadata(args.payload_json) if args.payload_json else {}
    metadata = _metadata(args.metadata_json) if args.metadata_json else {}
    if metadata:
        payload["metadata"] = {**payload.get("metadata", {}), **metadata} if isinstance(payload.get("metadata"), dict) else metadata

    for key in [
        "external_id",
        "ticket_created_at",
        "title",
        "description",
        "message",
        "resident_ref",
        "resident_name",
        "resident_contact",
        "location",
        "category",
        "priority",
        "assigned_role",
        "source_channel",
        "assignee",
        "due_at",
        "status",
        "kind",
        "sender_id",
        "sender_name",
        "chat_id",
        "chat_type",
        "platform",
        "notify",
        "force_notify",
        "force_reroute",
        "dry_run",
    ]:
        value = getattr(args, key, "")
        if value:
            payload[key] = value

    return payload


def _work_order_reply_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _metadata(args.payload_json) if args.payload_json else {}
    for key in [
        "record_id",
        "external_id",
        "message",
        "responder",
        "status",
        "replied_at",
    ]:
        value = getattr(args, key, "")
        if value:
            payload[key] = value
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    _load_wecom_env()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "process":
        try:
            result = process_message(
                args.message,
                sender_id=args.sender_id,
                sender_name=args.sender_name,
                chat_id=args.chat_id,
                chat_type=args.chat_type,
                platform=args.platform,
                metadata=_metadata(args.metadata_json),
                record_kind=args.record_kind or None,
                match_threshold=args.match_threshold,
            )
        except Exception as exc:
            result = {"handled": False, "route": "error", "reply": "", "ai_fallback": False, "error": str(exc)}
            _print(result, json_output=args.json_output)
            return 1
        _print(result, json_output=args.json_output)
        return 0

    if args.command == "faq":
        if args.faq_command == "add":
            try:
                entry = add_faq_entry(
                    entry_id=args.id or None,
                    meaning=args.meaning,
                    approved_answer=args.answer,
                    questions=args.question,
                    keywords=args.keyword,
                    patterns=args.pattern,
                    enabled=not args.disabled,
                )
            except Exception as exc:
                _print({"ok": False, "error": str(exc)}, json_output=args.json_output)
                return 1
            _print({"ok": True, "entry": entry}, json_output=args.json_output)
            return 0

        if args.faq_command == "list":
            _print({"entries": load_faq_entries()}, json_output=args.json_output)
            return 0

        if args.faq_command == "import-docx":
            try:
                result = import_docx_faq(
                    args.file,
                    community=args.community or None,
                    dry_run=args.dry_run,
                    skip_template_examples=not args.include_template_examples,
                )
            except Exception as exc:
                _print({"ok": False, "error": str(exc)}, json_output=args.json_output)
                return 1
            _print(result, json_output=args.json_output)
            return 0

        faq_parser = next(action for action in parser._actions if action.dest == "command").choices["faq"]
        faq_parser.print_help()
        return 0

    if args.command == "records":
        if args.records_command == "list":
            records = list_records(limit=args.limit, kind=args.kind or None)
            _print({"records": records}, json_output=args.json_output)
            return 0

        if args.records_command == "export":
            result = export_records()
            _print(result, json_output=args.json_output)
            return 0 if result.get("ok") else 1

        if args.records_command == "report":
            _print(records_report(kind=args.kind or None), json_output=args.json_output)
            return 0

        records_parser = next(action for action in parser._actions if action.dest == "command").choices["records"]
        records_parser.print_help()
        return 0

    if args.command == "work-order":
        if args.work_order_command == "add":
            try:
                result = create_work_order(_work_order_payload(args))
            except Exception as exc:
                _print({"ok": False, "error": str(exc)}, json_output=args.json_output)
                return 1
            _print(result, json_output=args.json_output)
            return 0

        if args.work_order_command == "notify":
            try:
                result = notify_work_order(
                    {
                        "record_id": args.record_id,
                        "external_id": args.external_id,
                        "dry_run": args.dry_run,
                    }
                )
            except Exception as exc:
                _print({"ok": False, "error": str(exc)}, json_output=args.json_output)
                return 1
            _print(result, json_output=args.json_output)
            return 0

        if args.work_order_command == "reply":
            try:
                result = record_staff_reply(_work_order_reply_payload(args))
            except Exception as exc:
                _print({"ok": False, "error": str(exc)}, json_output=args.json_output)
                return 1
            _print(result, json_output=args.json_output)
            return 0

        work_order_parser = next(action for action in parser._actions if action.dest == "command").choices["work-order"]
        work_order_parser.print_help()
        return 0

    if args.command == "ticket-api":
        if args.ticket_api_command == "poll":
            config = _ticket_api_config(args)
            if args.reset_cursor:
                clear_cursor(config.cursor_path)
            if args.watch:
                emit = _print_json_line if args.json_lines else lambda value: _print(
                    value,
                    json_output=args.json_output,
                )
                try:
                    poll_forever(
                        config,
                        since=args.since,
                        dry_run=args.dry_run,
                        emit=emit,
                    )
                except KeyboardInterrupt:
                    return 0
                return 0
            try:
                result = poll_once(config, since=args.since, dry_run=args.dry_run)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            if args.json_lines:
                _print_json_line(result)
            else:
                _print(result, json_output=args.json_output)
            return 0 if result.get("ok") else 1

        if args.ticket_api_command == "doctor":
            result = ticket_api_doctor(_ticket_api_config(args))
            _print(result, json_output=args.json_output)
            return 0 if result.get("ok") else 1

        if args.ticket_api_command == "inspect":
            config = _ticket_api_config(args)
            try:
                result = inspect_tickets(config, since=args.since)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            _print(result, json_output=args.json_output)
            return 0 if result.get("ok") else 1

        if args.ticket_api_command == "cursor":
            config = _ticket_api_config(args)
            if args.reset:
                removed = clear_cursor(config.cursor_path)
                result = {
                    "ok": True,
                    "action": "reset",
                    "removed": removed,
                    "cursor_path": str(config.cursor_path),
                    "cursor": {},
                }
            elif args.now or args.cursor_since:
                since = args.cursor_since or datetime.now(timezone.utc).replace(
                    tzinfo=None,
                    microsecond=0,
                ).isoformat()
                save_cursor(config.cursor_path, since)
                result = {
                    "ok": True,
                    "action": "set",
                    "cursor_path": str(config.cursor_path),
                    "cursor": load_cursor(config.cursor_path),
                }
            else:
                result = {
                    "ok": True,
                    "action": "show",
                    "cursor_path": str(config.cursor_path),
                    "cursor": load_cursor(config.cursor_path),
                }
            _print(result, json_output=args.json_output)
            return 0

        if args.ticket_api_command == "service":
            service_command = args.ticket_service_command
            if service_command == "install":
                config = TicketAPIConfig.from_env(poll_interval=args.interval)
                try:
                    config.validate()
                except Exception as exc:
                    _print({"ok": False, "error": str(exc)}, json_output=True)
                    return 1
                if not args.replay_existing and not load_cursor(config.cursor_path).get("since"):
                    since = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
                    save_cursor(config.cursor_path, since)
                result = install_service(interval=config.poll_interval)
            elif service_command == "start":
                result = start_service()
            elif service_command == "stop":
                result = stop_service()
            elif service_command == "status":
                result = service_status()
            elif service_command == "uninstall":
                result = uninstall_service()
            else:
                command_parser = next(
                    action for action in parser._actions if action.dest == "command"
                ).choices["ticket-api"]
                service_parser = next(
                    action for action in command_parser._actions if action.dest == "ticket_api_command"
                ).choices["service"]
                service_parser.print_help()
                return 0
            _print(result, json_output=True)
            return 0 if result.get("ok") else 1

        command_parser = next(
            action for action in parser._actions if action.dest == "command"
        ).choices["ticket-api"]
        command_parser.print_help()
        return 0

    if args.command == "doctor":
        _print(doctor(), json_output=args.json_output)
        return 0

    if args.command == "install-plugin":
        plugin_dirs = install_hermes_plugin()
        print_install_instructions(plugin_dirs)
        return 0

    parser.print_help()
    return 1
