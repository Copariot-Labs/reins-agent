from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROLE_ENV = {
    "property": "REINS_WECOM_NOTIFY_WEBHOOK_PROPERTY",
    "cleaning": "REINS_WECOM_NOTIFY_WEBHOOK_CLEANING",
    "police": "REINS_WECOM_NOTIFY_WEBHOOK_POLICE",
    "hospital": "REINS_WECOM_NOTIFY_WEBHOOK_HOSPITAL",
    "community": "REINS_WECOM_NOTIFY_WEBHOOK_COMMUNITY",
    "human_review": "REINS_WECOM_NOTIFY_WEBHOOK_HUMAN_REVIEW",
}

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

PRIORITY_LABELS = {
    "high": "紧急",
    "urgent": "紧急",
    "critical": "紧急",
    "emergency": "紧急",
    "normal": "普通",
    "medium": "普通",
    "low": "低",
}


WECOM_CORP_ID_ENV = "REINS_WECOM_CORP_ID"
WECOM_APP_SECRET_ENV = "REINS_WECOM_APP_SECRET"
WECOM_APP_AGENT_ID_ENV = "REINS_WECOM_APP_AGENT_ID"

_TOKEN_CACHE: dict[tuple[str, str], tuple[str, float]] = {}


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def webhook_for_role(role: str) -> tuple[str, str]:
    env_name = ROLE_ENV.get(role, "")
    if env_name:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value, env_name

    default_env = "REINS_WECOM_NOTIFY_WEBHOOK_DEFAULT"
    default_value = os.environ.get(default_env, "").strip()
    if default_value:
        return default_value, default_env

    return "", env_name or default_env


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


def build_staff_notification(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    role_label = _string(metadata.get("assigned_role_label") or metadata.get("assigned_role") or "相关人员")
    ticket_id = _string(metadata.get("external_id") or metadata.get("ticket_id")) or _string(record.get("id"))
    priority = _priority_label(metadata.get("priority"))
    category = _string(metadata.get("category")) or "未分类"
    location = _string(metadata.get("location"))

    # Keep the resident's complete issue content. Prefer the parsed resident
    # description, then the title, then the stored message as a final fallback.
    issue = _string(metadata.get("description") or metadata.get("title") or record.get("message"))
    requirements = _string(metadata.get("handling_requirements"))
    reply_bot_name = os.environ.get(WECOM_REPLY_BOT_NAME_ENV, "社区美女").strip() or "社区美女"

    lines = [
        "【Reins工单提醒】",
        f"工单编号：{ticket_id}",
        f"负责人：{role_label}",
        f"优先级：{priority}",
        f"类型：{category}",
    ]

    if location:
        lines.append(f"地点：{location}")

    if issue:
        lines.extend(["", "居民诉求：", issue])

    if requirements:
        lines.extend(["", f"处理要求：{requirements}"])

    lines.extend(
        [
            "",
            "请被@的负责人尽快跟进处理。",
            f"完成后请在本群 @{reply_bot_name} 回复：{ticket_id} 已处理：<处理结果>",
        ]
    )
    return "\n".join(lines)


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


def get_wecom_access_token(
    corp_id: str,
    app_secret: str,
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    cache_key = (corp_id, app_secret)
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > time.monotonic():
        return {"ok": True, "status": "cached", "access_token": cached[0], "error": ""}

    query = urlencode({"corpid": corp_id, "corpsecret": app_secret})
    request = Request(
        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?{query}",
        method="GET",
    )
    response = _read_json_response(request, timeout=timeout)
    if not response.get("ok"):
        return response

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    if data.get("errcode") not in (None, 0):
        return {
            "ok": False,
            "status": "failed",
            "error": str(data.get("errmsg") or "wecom_token_error"),
        }

    access_token = _string(data.get("access_token"))
    if not access_token:
        return {
            "ok": False,
            "status": "failed",
            "error": "missing_access_token",
        }

    expires_in = int(data.get("expires_in") or 7200)
    _TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + max(60, expires_in - 60))
    return {"ok": True, "status": "received", "access_token": access_token, "error": ""}


def send_wecom_app_text(
    *,
    corp_id: str,
    app_secret: str,
    agent_id: str,
    user_ids: list[str],
    content: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    token_result = get_wecom_access_token(corp_id, app_secret, timeout=timeout)
    if not token_result.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "error": f"access_token: {token_result.get('error') or 'failed'}",
            "body": token_result.get("body", ""),
        }

    try:
        numeric_agent_id = int(agent_id)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "status": "failed",
            "error": f"invalid {WECOM_APP_AGENT_ID_ENV}",
            "body": "",
        }

    payload = json.dumps(
        {
            "touser": "|".join(user_ids),
            "msgtype": "text",
            "agentid": numeric_agent_id,
            "text": {"content": content},
            "safe": 0,
            "enable_duplicate_check": 1,
            "duplicate_check_interval": 1800,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    query = urlencode({"access_token": token_result["access_token"]})
    request = Request(
        f"https://qyapi.weixin.qq.com/cgi-bin/message/send?{query}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response = _read_json_response(request, timeout=timeout)
    if not response.get("ok"):
        return response

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    if data.get("errcode") not in (None, 0):
        return {
            "ok": False,
            "status": "failed",
            "error": str(data.get("errmsg") or "wecom_message_error"),
            "body": response.get("body", ""),
        }

    invalid = {
        key: _string(data.get(key))
        for key in ("invaliduser", "unlicenseduser", "invalidparty", "invalidtag")
        if _string(data.get(key))
    }
    if invalid:
        detail = ", ".join(f"{key}={value}" for key, value in invalid.items())
        return {
            "ok": False,
            "status": "partial_sent",
            "error": detail,
            "body": response.get("body", ""),
            "message_id": _string(data.get("msgid")),
        }

    return {
        "ok": True,
        "status": "sent",
        "error": "",
        "body": response.get("body", ""),
        "message_id": _string(data.get("msgid")),
    }


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

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {}

    if isinstance(parsed, dict) and parsed.get("errcode") not in (None, 0):
        return {
            "ok": False,
            "status": "failed",
            "error": str(parsed.get("errmsg") or "wecom_error"),
            "body": body,
        }

    return {
        "ok": True,
        "status": "sent",
        "error": "",
        "body": body,
        "message_id": "",
    }


def notify_staff(record: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    role = _string(metadata.get("assigned_role")) or "human_review"
    content = build_staff_notification(record)
    user_ids, user_env_name = users_for_role(role)

    # New preferred mode: send one concise message to the shared operations
    # group and mention the responsible member(s) using their internal UserIDs.
    group_webhook = os.environ.get(WECOM_GROUP_WEBHOOK_ENV, "").strip()
    if group_webhook:
        channel = "group_webhook_mention"

        if dry_run:
            return {
                "ok": True,
                "status": "dry_run",
                "channel": channel,
                "assigned_role": role,
                "target_env": WECOM_GROUP_WEBHOOK_ENV,
                "recipients": user_ids,
                "content": content,
                "error": "",
            }

        if not user_ids:
            return {
                "ok": False,
                "status": "pending_configuration",
                "channel": channel,
                "assigned_role": role,
                "target_env": WECOM_GROUP_WEBHOOK_ENV,
                "recipients": [],
                "content": content,
                "error": f"missing {user_env_name}",
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
            "recipients": user_ids,
            "content": content,
        }

    # Backward-compatible fallback. If the new shared-group webhook is not
    # configured, preserve the old private-message/application behavior.
    webhook_url, webhook_env_name = webhook_for_role(role)

    if user_ids:
        channel = "private_message"
        target_env = user_env_name
    elif webhook_url:
        channel = "group_webhook_fallback"
        target_env = webhook_env_name
    else:
        channel = "private_message"
        target_env = user_env_name

    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "channel": channel,
            "assigned_role": role,
            "target_env": target_env,
            "recipients": user_ids,
            "content": content,
            "error": "",
        }

    if user_ids:
        credentials = {
            WECOM_CORP_ID_ENV: os.environ.get(WECOM_CORP_ID_ENV, "").strip(),
            WECOM_APP_SECRET_ENV: os.environ.get(WECOM_APP_SECRET_ENV, "").strip(),
            WECOM_APP_AGENT_ID_ENV: os.environ.get(WECOM_APP_AGENT_ID_ENV, "").strip(),
        }
        missing = [name for name, value in credentials.items() if not value]
        if missing:
            return {
                "ok": False,
                "status": "pending_configuration",
                "channel": channel,
                "assigned_role": role,
                "target_env": target_env,
                "recipients": user_ids,
                "content": content,
                "error": f"missing {', '.join(missing)}",
            }

        result = send_wecom_app_text(
            corp_id=credentials[WECOM_CORP_ID_ENV],
            app_secret=credentials[WECOM_APP_SECRET_ENV],
            agent_id=credentials[WECOM_APP_AGENT_ID_ENV],
            user_ids=user_ids,
            content=content,
        )
        return {
            **result,
            "channel": channel,
            "assigned_role": role,
            "target_env": target_env,
            "recipients": user_ids,
            "content": content,
        }

    if not webhook_url:
        return {
            "ok": False,
            "status": "pending_configuration",
            "channel": channel,
            "assigned_role": role,
            "target_env": target_env,
            "recipients": [],
            "content": content,
            "error": f"missing {user_env_name}",
        }

    result = send_wecom_text(webhook_url, content)
    return {
        **result,
        "channel": channel,
        "assigned_role": role,
        "target_env": target_env,
        "recipients": [],
        "content": content,
    }


def notification_doctor() -> dict[str, Any]:
    credentials = {
        WECOM_CORP_ID_ENV: bool(os.environ.get(WECOM_CORP_ID_ENV, "").strip()),
        WECOM_APP_SECRET_ENV: bool(os.environ.get(WECOM_APP_SECRET_ENV, "").strip()),
        WECOM_APP_AGENT_ID_ENV: bool(os.environ.get(WECOM_APP_AGENT_ID_ENV, "").strip()),
    }
    app_credentials_ready = all(credentials.values())
    shared_group_ready = bool(os.environ.get(WECOM_GROUP_WEBHOOK_ENV, "").strip())
    roles: dict[str, Any] = {}

    for role in ROLE_USER_ENV:
        user_ids, user_env = users_for_role(role)

        if shared_group_ready:
            mode = "group_webhook_mention"
            ready = bool(user_ids)
            target_env = WECOM_GROUP_WEBHOOK_ENV
        else:
            webhook_url, webhook_env = webhook_for_role(role)
            if user_ids:
                mode = "private_message"
                ready = app_credentials_ready
                target_env = user_env
            elif webhook_url:
                mode = "group_webhook_fallback"
                ready = True
                target_env = webhook_env
            else:
                mode = "not_configured"
                ready = False
                target_env = user_env

        roles[role] = {
            "ready": ready,
            "mode": mode,
            "target_env": target_env,
            "recipient_env": user_env,
            "recipient_count": len(user_ids),
        }

    return {
        "preferred_mode": "group_webhook_mention" if shared_group_ready else "legacy",
        "group_webhook_ready": shared_group_ready,
        "group_webhook_env": WECOM_GROUP_WEBHOOK_ENV,
        "app_credentials_ready": app_credentials_ready,
        "credentials": credentials,
        "roles": roles,
    }
