from __future__ import annotations

import json
from typing import Any

from reins.features.wecom.store import doctor, records_report
from reins.features.wecom.work_order import create_work_order, record_staff_reply


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _work_order_result(result: dict[str, Any]) -> dict[str, Any]:
    record = result.get("record") if isinstance(result.get("record"), dict) else {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    notification = result.get("notification") if isinstance(result.get("notification"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "duplicate": bool(result.get("duplicate")),
        "record_id": record.get("id"),
        "external_id": metadata.get("external_id", ""),
        "status": record.get("status", ""),
        "category": metadata.get("category", ""),
        "priority": metadata.get("priority", ""),
        "assigned_role": metadata.get("assigned_role", ""),
        "assigned_role_label": metadata.get("assigned_role_label", ""),
        "notification": {
            "ok": bool(notification.get("ok")),
            "status": notification.get("status", ""),
            "channel": notification.get("channel", ""),
            "target_env": notification.get("target_env", ""),
            "recipient_env": notification.get("recipient_env", ""),
            "recipients": notification.get("recipients", []),
            "error": notification.get("error", ""),
        },
        "records_xlsx_path": result.get("records_xlsx_path", ""),
        "records_xlsx_ok": bool(result.get("records_xlsx_ok", True)),
        "records_xlsx_error": result.get("records_xlsx_error", ""),
    }


def register(ctx) -> None:
    register_ingest_group_ticket(ctx)
    register_staff_reply(ctx)
    register_report(ctx)
    register_doctor(ctx)
    ctx.register_hook("pre_llm_call", preprocess_inbound_work_order)


def preprocess_inbound_work_order(
    session_id: str = "",
    user_message: str = "",
    conversation_history: list | None = None,
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    sender_id: str = "",
    **kwargs,
) -> dict[str, str] | None:
    del session_id, conversation_history, is_first_turn, model, kwargs
    message = str(user_message or "").strip()
    platform_name = str(getattr(platform, "value", platform) or "").lower()
    if platform_name != "wecom":
        return None
    lines = message.splitlines()
    if (
        len(lines) > 1
        and lines[0].strip().startswith("@")
        and (
            lines[1].strip().startswith("【新建工单】")
            or lines[1].strip().startswith("待处理工单")
        )
    ):
        message = "\n".join(lines[1:]).strip()
    if not (message.startswith("【新建工单】") or message.startswith("待处理工单")):
        return None

    result = create_work_order(
        {
            "message": message,
            "sender_id": str(sender_id or ""),
            "chat_type": "group",
            "platform": "wecom",
            "notify": True,
        }
    )
    summary = _work_order_result(result)
    return {
        "context": (
            "REINS_WECOM_PREPROCESSED_WORK_ORDER\n"
            "The current structured WeCom ticket was already processed deterministically before "
            "this model call. Do not call wecom_ingest_group_ticket and do not infer a different "
            "result from conversation history. Reply with one concise receipt based only on this "
            "JSON. Claim that staff were notified only when notification.status is sent.\n"
            f"{_json_result(summary)}"
        )
    }


def register_ingest_group_ticket(ctx) -> None:
    schema = {
        "name": "wecom_ingest_group_ticket",
        "description": (
            "Parse one complete WeCom group work-order message, classify the responsible role, "
            "save or update its Excel record, and mention the responsible staff in the shared WeCom group."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The complete, unchanged WeCom work-order message.",
                },
                "sender_id": {"type": "string", "description": "Optional WeCom sender UserID."},
                "sender_name": {"type": "string", "description": "Optional sender display name."},
                "chat_id": {"type": "string", "description": "Optional source group chat ID."},
                "dry_run": {
                    "type": "boolean",
                    "description": "Analyze and save, but preview notification instead of sending it.",
                    "default": False,
                },
            },
            "required": ["message"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        result = create_work_order(
            {
                "message": str(params.get("message") or ""),
                "sender_id": str(params.get("sender_id") or ""),
                "sender_name": str(params.get("sender_name") or ""),
                "chat_id": str(params.get("chat_id") or ""),
                "chat_type": "group",
                "platform": "wecom",
                "notify": True,
                "dry_run": params.get("dry_run") is True,
            }
        )
        return _json_result(_work_order_result(result))

    ctx.register_tool(
        name="wecom_ingest_group_ticket",
        toolset="reins_wecom",
        schema=schema,
        handler=handler,
        description="Record, classify, and notify staff for one WeCom group ticket.",
    )


def register_staff_reply(ctx) -> None:
    schema = {
        "name": "wecom_record_staff_reply",
        "description": "Update an existing Reins work order from a WeCom staff handling-result message.",
        "parameters": {
            "type": "object",
            "properties": {
                "external_id": {"type": "string", "description": "Ticket ID such as t_27f4f7b483174238."},
                "message": {"type": "string", "description": "The staff member's complete handling result."},
                "responder": {"type": "string", "description": "Staff name or WeCom UserID."},
                "status": {
                    "type": "string",
                    "description": "Optional explicit status. Otherwise inferred from the reply.",
                },
            },
            "required": ["external_id", "message"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        result = record_staff_reply(
            {
                "external_id": str(params.get("external_id") or ""),
                "message": str(params.get("message") or ""),
                "responder": str(params.get("responder") or ""),
                "status": str(params.get("status") or ""),
            }
        )
        record = result.get("record") if isinstance(result.get("record"), dict) else {}
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        return _json_result(
            {
                "ok": bool(result.get("ok")),
                "record_id": record.get("id"),
                "external_id": metadata.get("external_id", ""),
                "status": record.get("status", ""),
                "last_staff_responder": metadata.get("last_staff_responder", ""),
                "records_xlsx_path": result.get("records_xlsx_path", ""),
                "records_xlsx_ok": bool(result.get("records_xlsx_ok", True)),
                "records_xlsx_error": result.get("records_xlsx_error", ""),
            }
        )

    ctx.register_tool(
        name="wecom_record_staff_reply",
        toolset="reins_wecom",
        schema=schema,
        handler=handler,
        description="Update a Reins work order from staff feedback.",
    )


def register_report(ctx) -> None:
    schema = {
        "name": "wecom_work_order_report",
        "description": "Summarize Reins WeCom work orders by status, category, priority, role, and source.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del params, kwargs
        return _json_result(records_report(kind="work_order"))

    ctx.register_tool(
        name="wecom_work_order_report",
        toolset="reins_wecom",
        schema=schema,
        handler=handler,
        description="Summarize locally recorded WeCom work orders.",
    )


def register_doctor(ctx) -> None:
    schema = {
        "name": "wecom_work_order_doctor",
        "description": "Check Reins WeCom storage and shared-group mention notification configuration.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del params, kwargs
        return _json_result(doctor())

    ctx.register_tool(
        name="wecom_work_order_doctor",
        toolset="reins_wecom",
        schema=schema,
        handler=handler,
        description="Check Reins WeCom work-order readiness.",
    )
