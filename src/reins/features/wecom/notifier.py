from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


ROLE_USER_ENV = {
    "property": "REINS_WECOM_NOTIFY_USERS_PROPERTY",
    "cleaning": "REINS_WECOM_NOTIFY_USERS_CLEANING",
    "police": "REINS_WECOM_NOTIFY_USERS_POLICE",
    "hospital": "REINS_WECOM_NOTIFY_USERS_HOSPITAL",
    "community": "REINS_WECOM_NOTIFY_USERS_COMMUNITY",
    "human_review": "REINS_WECOM_NOTIFY_USERS_HUMAN_REVIEW",
}

# Preferred production mode: one shared WeCom group bot webhook.
# The role-specific UserID variables below are reused as real group mentions.
WECOM_GROUP_WEBHOOK_ENV = "REINS_WECOM_NOTIFY_GROUP_WEBHOOK"
WECOM_REPLY_BOT_NAME_ENV = "REINS_WECOM_REPLY_BOT_NAME"
WECOM_GROUP_WEBHOOK_HOST = "qyapi.weixin.qq.com"
WECOM_GROUP_WEBHOOK_PATH = "/cgi-bin/webhook/send"
WECOM_TEXT_MAX_BYTES = 2048

PRIORITY_LABELS = {
    "high": "紧急",
    "urgent": "紧急",
    "critical": "紧急",
    "emergency": "紧急",
    "normal": "普通",
    "medium": "普通",
    "low": "低",
}


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def users_for_role(role: str) -> tuple[list[str], str]:
    env_name = ROLE_USER_ENV.get(role, "")
    if env_name:
        users = _split_user_ids(os.environ.get(env_name, ""))
        if users:
            return users, env_name

    default_env = "REINS_WECOM_NOTIFY_USERS_DEFAULT"
    default_users = _split_user_ids(os.environ.get(default_env, ""))
    if default_users:
        return default_users, default_env

    return [], env_name or default_env


def _split_user_ids(value: Any) -> list[str]:
    users: list[str] = []
    for user_id in re.split(r"[|,;，；\s]+", _string(value)):
        clean = user_id.strip()
        if clean and clean not in users:
            users.append(clean)
    return users


def _priority_label(value: Any) -> str:
    priority = _string(value)
    if not priority:
        return "普通"
    return PRIORITY_LABELS.get(priority.lower(), priority)


def _valid_group_webhook_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False

    keys = parse_qs(parsed.query, keep_blank_values=True).get("key", [])
    return bool(
        parsed.scheme == "https"
        and parsed.hostname == WECOM_GROUP_WEBHOOK_HOST
        and parsed.path == WECOM_GROUP_WEBHOOK_PATH
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
        and len(keys) == 1
        and keys[0].strip()
    )


def _truncate_utf8(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value

    marker = "…"
    marker_bytes = marker.encode("utf-8")
    if max_bytes <= len(marker_bytes):
        return encoded[:max_bytes].decode("utf-8", errors="ignore")
    return encoded[: max_bytes - len(marker_bytes)].decode("utf-8", errors="ignore") + marker


def _bounded_field(value: Any, max_bytes: int = 192) -> str:
    return _truncate_utf8(_string(value), max_bytes)


def _fit_notification_content(header: str, details: str, footer: str) -> str:
    parts = [part for part in (header, details, footer) if part]
    content = "\n\n".join(parts)
    if len(content.encode("utf-8")) <= WECOM_TEXT_MAX_BYTES:
        return content

    marker = "（工单内容过长，已截断）"
    fixed = "\n\n".join((header, marker, footer))
    available = WECOM_TEXT_MAX_BYTES - len(fixed.encode("utf-8")) - 2
    shortened_details = _truncate_utf8(details, max(0, available))
    if shortened_details:
        return "\n\n".join((header, shortened_details, marker, footer))
    return _truncate_utf8(fixed, WECOM_TEXT_MAX_BYTES)


def build_staff_notification(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    role_label = _bounded_field(
        metadata.get("assigned_role_label") or metadata.get("assigned_role") or "相关人员",
        96,
    )
    ticket_id = _bounded_field(
        metadata.get("external_id") or metadata.get("ticket_id") or record.get("id"),
        128,
    )
    priority = _bounded_field(_priority_label(metadata.get("priority")), 48)
    category = _bounded_field(metadata.get("category") or "未分类", 192)
    location = _bounded_field(metadata.get("location"), 192)

    # Keep the resident's complete issue content. Prefer the parsed resident
    # description, then the title, then the stored message as a final fallback.
    issue = _string(metadata.get("description") or metadata.get("title") or record.get("message"))
    assessment = _string(metadata.get("customer_assessment"))
    requirements = _string(metadata.get("handling_requirements"))
    reply_bot_name = _bounded_field(
        os.environ.get(WECOM_REPLY_BOT_NAME_ENV, "社区美女").strip() or "社区美女",
        96,
    )

    lines = [
        "【Reins工单提醒】",
        f"工单编号：{ticket_id}",
        f"负责人：{role_label}",
        f"优先级：{priority}",
        f"类型：{category}",
    ]

    if location:
        lines.append(f"地点：{location}")

    details = []
    if issue:
        details.extend(["居民诉求：", issue])
    if assessment and assessment != issue:
        if details:
            details.append("")
        details.extend(["客服研判：", assessment])
    if requirements:
        if details:
            details.append("")
        details.extend(["处理要求：", requirements])

    footer = "\n".join(
        [
            "请被@的负责人尽快跟进处理。",
            f"完成后请在本群 @{reply_bot_name} 回复：{ticket_id} 已处理：<处理结果>",
        ]
    )
    return _fit_notification_content("\n".join(lines), "\n".join(details), footer)


def _read_json_response(request: Request, *, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": f"http_{exc.code}",
            "body": exc.read().decode("utf-8", errors="replace"),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc.reason),
            "body": "",
        }
    except TimeoutError:
        return {
            "ok": False,
            "status": "failed",
            "error": "timeout",
            "body": "",
        }

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": "failed",
            "error": "invalid_wecom_response",
            "body": body,
        }

    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "status": "failed",
            "error": "invalid_wecom_response",
            "body": body,
        }

    return {"ok": True, "status": "received", "error": "", "body": body, "data": parsed}


def send_wecom_text(
    webhook_url: str,
    content: str,
    *,
    mentioned_user_ids: list[str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    text_payload: dict[str, Any] = {"content": content}
    if mentioned_user_ids:
        # WeCom group-bot text messages support real member mentions through
        # mentioned_list. Values must be internal WeCom UserIDs.
        text_payload["mentioned_list"] = mentioned_user_ids

    payload = json.dumps(
        {
            "msgtype": "text",
            "text": text_payload,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response = _read_json_response(request, timeout=timeout)
    if not response.get("ok"):
        return response

    parsed = response.get("data") if isinstance(response.get("data"), dict) else {}
    if parsed.get("errcode") != 0:
        error_code = parsed.get("errcode", "missing")
        error_message = _string(parsed.get("errmsg")) or "wecom_webhook_error"
        return {
            "ok": False,
            "status": "failed",
            "error": f"wecom_{error_code}: {error_message}",
            "body": response.get("body", ""),
        }

    return {
        "ok": True,
        "status": "sent",
        "error": "",
        "body": response.get("body", ""),
        "message_id": "",
    }


def notify_staff(record: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Notify the responsible staff member in the single shared WeCom group.

    This function intentionally fails closed. It never falls back to private
    application messages or a different group when the shared group webhook is
    missing, preventing accidental delivery to the wrong destination.
    """
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    role = _string(metadata.get("assigned_role")) or "human_review"
    content = build_staff_notification(record)
    user_ids, user_env_name = users_for_role(role)
    group_webhook = os.environ.get(WECOM_GROUP_WEBHOOK_ENV, "").strip()
    channel = "group_webhook_mention"

    if not group_webhook:
        return {
            "ok": False,
            "status": "pending_configuration",
            "channel": channel,
            "assigned_role": role,
            "target_env": WECOM_GROUP_WEBHOOK_ENV,
            "recipient_env": user_env_name,
            "recipients": user_ids,
            "content": content,
            "error": f"missing {WECOM_GROUP_WEBHOOK_ENV}",
        }

    if not _valid_group_webhook_url(group_webhook):
        return {
            "ok": False,
            "status": "pending_configuration",
            "channel": channel,
            "assigned_role": role,
            "target_env": WECOM_GROUP_WEBHOOK_ENV,
            "recipient_env": user_env_name,
            "recipients": user_ids,
            "content": content,
            "error": f"invalid {WECOM_GROUP_WEBHOOK_ENV}",
        }

    if not user_ids:
        return {
            "ok": False,
            "status": "pending_configuration",
            "channel": channel,
            "assigned_role": role,
            "target_env": WECOM_GROUP_WEBHOOK_ENV,
            "recipient_env": user_env_name,
            "recipients": [],
            "content": content,
            "error": f"missing {user_env_name}",
        }

    if any(user_id.casefold() == "@all" for user_id in user_ids):
        return {
            "ok": False,
            "status": "pending_configuration",
            "channel": channel,
            "assigned_role": role,
            "target_env": WECOM_GROUP_WEBHOOK_ENV,
            "recipient_env": user_env_name,
            "recipients": user_ids,
            "content": content,
            "error": f"invalid {user_env_name}: @all is not allowed",
        }

    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "channel": channel,
            "assigned_role": role,
            "target_env": WECOM_GROUP_WEBHOOK_ENV,
            "recipient_env": user_env_name,
            "recipients": user_ids,
            "content": content,
            "error": "",
        }

    result = send_wecom_text(
        group_webhook,
        content,
        mentioned_user_ids=user_ids,
    )
    return {
        **result,
        "channel": channel,
        "assigned_role": role,
        "target_env": WECOM_GROUP_WEBHOOK_ENV,
        "recipient_env": user_env_name,
        "recipients": user_ids,
        "content": content,
    }


def notification_doctor() -> dict[str, Any]:
    group_webhook = os.environ.get(WECOM_GROUP_WEBHOOK_ENV, "").strip()
    group_webhook_valid = _valid_group_webhook_url(group_webhook)
    roles: dict[str, Any] = {}
    resolved_recipients: dict[str, tuple[str, ...]] = {}

    for role in ROLE_USER_ENV:
        user_ids, user_env = users_for_role(role)
        resolved_recipients[role] = tuple(sorted(set(user_ids)))
        safe_recipients = bool(user_ids) and all(
            user_id.casefold() != "@all" for user_id in user_ids
        )
        roles[role] = {
            "ready": bool(group_webhook_valid and safe_recipients),
            "mode": "group_webhook_mention",
            "target_env": WECOM_GROUP_WEBHOOK_ENV,
            "recipient_env": user_env,
            "recipient_count": len(user_ids),
            "recipients_valid": safe_recipients,
        }

    shared_mappings: list[dict[str, Any]] = []
    signatures = {
        signature
        for signature in resolved_recipients.values()
        if signature
    }
    for signature in sorted(signatures):
        shared_roles = [
            role
            for role, recipient_signature in resolved_recipients.items()
            if recipient_signature == signature
        ]
        if len(shared_roles) < 2:
            continue
        shared_mappings.append(
            {
                "type": "shared_recipient_mapping",
                "roles": shared_roles,
                "recipient_count": len(signature),
            }
        )
        for role in shared_roles:
            roles[role]["shared_with_roles"] = [
                other_role for other_role in shared_roles if other_role != role
            ]

    return {
        "preferred_mode": "group_webhook_mention",
        "group_webhook_configured": bool(group_webhook),
        "group_webhook_ready": group_webhook_valid,
        "group_webhook_valid": group_webhook_valid,
        "group_webhook_env": WECOM_GROUP_WEBHOOK_ENV,
        "legacy_private_fallback_enabled": False,
        "recipient_mapping_warnings": shared_mappings,
        "roles": roles,
    }
