from __future__ import annotations

import json
from typing import Any

from reins.features.wechat.service import (
    doctor,
    draft_file,
    draft_message,
    open_wechat,
    search_contact,
    send_current_draft,
    send_file,
    send_message,
)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def register(ctx) -> None:
    register_doctor(ctx)
    register_open(ctx)
    register_search_contact(ctx)
    register_draft_message(ctx)
    register_send_current_draft(ctx)
    register_send_message(ctx)
    register_draft_file(ctx)
    register_send_file(ctx)


def register_doctor(ctx) -> None:
    schema = {
        "name": "wechat_doctor",
        "description": "Check whether deterministic Reins WeChat automation dependencies are available on this computer.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del params, kwargs
        return _json_result(doctor())

    ctx.register_tool(
        name="wechat_doctor",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Check deterministic Reins WeChat automation dependencies.",
    )


def register_open(ctx) -> None:
    schema = {
        "name": "wechat_open",
        "description": "Open or focus the desktop WeChat/Weixin app using deterministic OS automation.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del params, kwargs
        return _json_result(open_wechat())

    ctx.register_tool(
        name="wechat_open",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Open or focus desktop WeChat.",
    )


def register_search_contact(ctx) -> None:
    schema = {
        "name": "wechat_search_contact",
        "description": "Search and select a desktop WeChat contact or conversation. Verify the selected chat before sending.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Contact or conversation name to search."},
            },
            "required": ["name"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(search_contact(str(params.get("name") or "")))

    ctx.register_tool(
        name="wechat_search_contact",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Search and select a WeChat contact.",
    )


def register_draft_message(ctx) -> None:
    schema = {
        "name": "wechat_draft_message",
        "description": "Search a WeChat contact and paste a message draft. This tool never sends.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Contact or conversation name."},
                "message": {"type": "string", "description": "Message text to draft."},
            },
            "required": ["to", "message"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(draft_message(str(params.get("to") or ""), str(params.get("message") or "")))

    ctx.register_tool(
        name="wechat_draft_message",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Draft a WeChat message without sending.",
    )


def register_send_current_draft(ctx) -> None:
    schema = {
        "name": "wechat_send_current_draft",
        "description": (
            "Send the currently focused WeChat draft. Only call this after the user has confirmed "
            "the exact recipient and final content in the current run."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirm": {
                    "type": "boolean",
                    "description": "Must be true after explicit user confirmation.",
                },
                "send_key": {
                    "type": "string",
                    "description": "Send shortcut. Usually enter; macOS also supports cmd-enter; Linux supports ctrl-enter.",
                    "default": "enter",
                },
            },
            "required": ["confirm"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(send_current_draft(
            confirm=params.get("confirm") is True,
            send_key=str(params.get("send_key") or "enter"),
        ))

    ctx.register_tool(
        name="wechat_send_current_draft",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Send the current WeChat draft after confirmation.",
    )


def register_send_message(ctx) -> None:
    schema = {
        "name": "wechat_send_message",
        "description": (
            "Draft and optionally send a WeChat message. Without confirm=true this only drafts. "
            "Use confirm=true only after explicit user confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Contact or conversation name."},
                "message": {"type": "string", "description": "Message text."},
                "confirm": {"type": "boolean", "description": "Must be true to send; false drafts only.", "default": False},
                "send_key": {"type": "string", "description": "Send shortcut.", "default": "enter"},
            },
            "required": ["to", "message"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(send_message(
            str(params.get("to") or ""),
            str(params.get("message") or ""),
            confirm=params.get("confirm") is True,
            send_key=str(params.get("send_key") or "enter"),
        ))

    ctx.register_tool(
        name="wechat_send_message",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Draft and optionally send a WeChat message.",
    )


def register_draft_file(ctx) -> None:
    schema = {
        "name": "wechat_draft_file",
        "description": "Search a WeChat contact and paste a file attachment draft. This tool never sends.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Contact or conversation name."},
                "file": {"type": "string", "description": "Local file path to attach."},
                "message": {"type": "string", "description": "Optional message text.", "default": ""},
            },
            "required": ["to", "file"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(draft_file(
            str(params.get("to") or ""),
            str(params.get("file") or ""),
            str(params.get("message") or ""),
        ))

    ctx.register_tool(
        name="wechat_draft_file",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Draft a WeChat file attachment without sending.",
    )


def register_send_file(ctx) -> None:
    schema = {
        "name": "wechat_send_file",
        "description": (
            "Draft and optionally send a WeChat file. Without confirm=true this only drafts. "
            "Use confirm=true only after explicit user confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Contact or conversation name."},
                "file": {"type": "string", "description": "Local file path to attach."},
                "message": {"type": "string", "description": "Optional message text.", "default": ""},
                "confirm": {"type": "boolean", "description": "Must be true to send; false drafts only.", "default": False},
                "send_key": {"type": "string", "description": "Send shortcut.", "default": "enter"},
            },
            "required": ["to", "file"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(send_file(
            str(params.get("to") or ""),
            str(params.get("file") or ""),
            str(params.get("message") or ""),
            confirm=params.get("confirm") is True,
            send_key=str(params.get("send_key") or "enter"),
        ))

    ctx.register_tool(
        name="wechat_send_file",
        toolset="reins_wechat",
        schema=schema,
        handler=handler,
        description="Draft and optionally send a WeChat file.",
    )
