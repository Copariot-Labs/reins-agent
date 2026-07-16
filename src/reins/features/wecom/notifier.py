from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROLE_ENV = {
    "property": "REINS_WECOM_NOTIFY_WEBHOOK_PROPERTY",
    "cleaning": "REINS_WECOM_NOTIFY_WEBHOOK_CLEANING",
    "police": "REINS_WECOM_NOTIFY_WEBHOOK_POLICE",
    "hospital": "REINS_WECOM_NOTIFY_WEBHOOK_HOSPITAL",
    "community": "REINS_WECOM_NOTIFY_WEBHOOK_COMMUNITY",
    "human_review": "REINS_WECOM_NOTIFY_WEBHOOK_HUMAN_REVIEW",
}


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
    return os.environ.get(default_env, "").strip(), default_env


def build_staff_notification(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    role_label = _string(metadata.get("assigned_role_label") or metadata.get("assigned_role") or "相关人员")
    lines = [
        f"【Reins工单通知】请{role_label}跟进",
        f"工单编号：{_string(metadata.get('external_id') or metadata.get('ticket_id')) or record.get('id')}",
        f"状态：{_string(record.get('status')) or 'new'}",
        f"优先级：{_string(metadata.get('priority')) or 'normal'}",
        f"分类：{_string(metadata.get('category')) or '未分类'}",
    ]

    for label, key in [
        ("来源", "source_channel"),
        ("创建时间", "ticket_created_at"),
        ("居民", "resident_ref"),
        ("位置", "location"),
        ("标题", "title"),
        ("内容", "description"),
    ]:
        value = _string(metadata.get(key))
        if value:
            lines.append(f"{label}：{value}")

    errors = metadata.get("validation_errors")
    if isinstance(errors, list) and errors:
        lines.append(f"需要人工确认：{', '.join(str(item) for item in errors)}")

    lines.append("处理后请在企业微信回复处理结果，Reins会更新本地工单记录。")
    return "\n".join(lines)


def send_wecom_text(webhook_url: str, content: str, *, timeout: float = 10.0) -> dict[str, Any]:
    payload = json.dumps(
        {
            "msgtype": "text",
            "text": {"content": content},
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
    }


def notify_staff(record: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    role = _string(metadata.get("assigned_role")) or "human_review"
    content = build_staff_notification(record)
    webhook_url, env_name = webhook_for_role(role)

    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "assigned_role": role,
            "target_env": env_name,
            "content": content,
            "error": "",
        }

    if not webhook_url:
        return {
            "ok": False,
            "status": "pending_configuration",
            "assigned_role": role,
            "target_env": env_name,
            "content": content,
            "error": f"missing {env_name}",
        }

    result = send_wecom_text(webhook_url, content)
    return {
        **result,
        "assigned_role": role,
        "target_env": env_name,
        "content": content,
    }
