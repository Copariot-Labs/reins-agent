from __future__ import annotations

from enum import Enum


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

    if any(word in text for word in ["word", "excel", "docx", "xlsx", "报表", "台账", "ledger", "report"]):
        return ExecutionPath.OFFICE

    if any(word in text for word in ["login", "portal", "form", "submit", "网页", "浏览器", "表单"]):
        return ExecutionPath.BROWSER

    if any(word in text for word in ["screenshot", "desktop", "window", "屏幕", "窗口"]):
        return ExecutionPath.DESKTOP

    if any(word in text for word in ["search", "summarize", "generate", "draft", "查询", "总结", "生成"]):
        return ExecutionPath.BACKEND_WITH_PRESENTATION

    return ExecutionPath.BACKEND_ONLY