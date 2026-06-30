from __future__ import annotations

from enum import Enum

from reins.features.workmode.desktop_resolver import is_desktop_app_intent
from reins.features.workmode.url_resolver import is_browser_intent


class ExecutionPath(str, Enum):
    BACKEND_ONLY = "backend_only"
    BACKEND_WITH_PRESENTATION = "backend_with_presentation"
    BROWSER = "browser"
    OFFICE = "office"
    WECHAT = "wechat"
    DESKTOP = "desktop"


def choose_execution_path(message: str) -> ExecutionPath:
    text = message.lower()

    if any(word in text for word in ["wechat", "微信", "发消息", "发送消息"]):
        return ExecutionPath.WECHAT

    office_terms = [
        "word",
        "excel",
        "powerpoint",
        "presentation",
        "slides",
        "document",
        "letter",
        "memo",
        "notice",
        "spreadsheet",
        "sheet",
        "workbook",
        "table",
        "docx",
        "xlsx",
        "pptx",
        "ppt",
        "报表",
        "台账",
        "表格",
        "演示",
        "幻灯片",
        "ledger",
        "report",
    ]

    writing_actions = ("write", "create", "generate", "prepare", "make", "draft", "compose")

    if any(word in text for word in office_terms):
        return ExecutionPath.OFFICE

    if "application" in text and any(action in text for action in writing_actions):
        return ExecutionPath.OFFICE

    if any(word in text for word in ["login", "portal", "form", "submit", "网页", "浏览器", "表单"]):
        return ExecutionPath.BROWSER

    if is_browser_intent(message):
        return ExecutionPath.BROWSER

    if is_desktop_app_intent(message):
        return ExecutionPath.DESKTOP

    if any(word in text for word in ["screenshot", "desktop", "window", "屏幕", "窗口"]):
        return ExecutionPath.DESKTOP

    if any(word in text for word in ["summarize", "generate", "draft", "总结", "生成"]):
        return ExecutionPath.BACKEND_WITH_PRESENTATION

    return ExecutionPath.BACKEND_ONLY
