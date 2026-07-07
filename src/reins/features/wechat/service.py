from __future__ import annotations

from typing import Any

from reins.features.wechat.driver import WeChatResult, current_driver


def _error_result(action: str, exc: Exception) -> dict[str, Any]:
    return WeChatResult(
        ok=False,
        action=action,
        platform="unknown",
        message=str(exc),
        error=str(exc),
    ).to_dict()


def doctor(*, dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).doctor().to_dict()
    except Exception as exc:
        return _error_result("doctor", exc)


def open_wechat(*, dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).open().to_dict()
    except Exception as exc:
        return _error_result("open", exc)


def search_contact(name: str, *, dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).search_contact(name).to_dict()
    except Exception as exc:
        return _error_result("search_contact", exc)


def draft_message(contact: str, message: str, *, dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).draft_message(contact, message).to_dict()
    except Exception as exc:
        return _error_result("draft_message", exc)


def send_current_draft(*, confirm: bool, send_key: str = "enter", dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).send_current_draft(confirm=confirm, send_key=send_key).to_dict()
    except Exception as exc:
        return _error_result("send_current_draft", exc)


def send_message(contact: str, message: str, *, confirm: bool, send_key: str = "enter", dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).send_message(contact, message, confirm=confirm, send_key=send_key).to_dict()
    except Exception as exc:
        return _error_result("send_message", exc)


def draft_file(contact: str, file_path: str, message: str = "", *, dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).draft_file(contact, file_path, message).to_dict()
    except Exception as exc:
        return _error_result("draft_file", exc)


def send_file(contact: str, file_path: str, message: str = "", *, confirm: bool, send_key: str = "enter", dry_run: bool = False) -> dict[str, Any]:
    try:
        return current_driver(dry_run=dry_run).send_file(contact, file_path, message, confirm=confirm, send_key=send_key).to_dict()
    except Exception as exc:
        return _error_result("send_file", exc)


def exit_code_for_result(result: dict[str, Any]) -> int:
    if result.get("ok") is True:
        return 0
    if result.get("error") in {"missing_confirm"}:
        return 0
    return 1
