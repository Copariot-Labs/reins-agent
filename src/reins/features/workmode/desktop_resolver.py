from __future__ import annotations

import re


APP_TRIGGERS = {
    "activate",
    "bring up",
    "focus",
    "launch",
    "open",
    "start",
    "use",
    "打开",
}

APP_CONTEXT_WORDS = {
    "app",
    "application",
    "desktop",
    "program",
    "window",
    "应用",
    "窗口",
}

KNOWN_DESKTOP_APPS = {
    "activity monitor": "Activity Monitor",
    "calculator": "Calculator",
    "calendar": "Calendar",
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "excel": "Microsoft Excel",
    "finder": "Finder",
    "github desktop": "GitHub Desktop",
    "google chrome": "Google Chrome",
    "mail": "Mail",
    "messages": "Messages",
    "microsoft edge": "Microsoft Edge",
    "microsoft excel": "Microsoft Excel",
    "microsoft word": "Microsoft Word",
    "notes": "Notes",
    "preview": "Preview",
    "safari": "Safari",
    "slack": "Slack",
    "system settings": "System Settings",
    "terminal": "Terminal",
    "textedit": "TextEdit",
    "wechat": "WeChat",
    "weixin": "WeChat",
    "word": "Microsoft Word",
    "zoom": "zoom.us",
    "微信": "WeChat",
}

CAPTURE_ONLY_WORDS = {
    "capture desktop",
    "desktop screenshot",
    "screenshot",
    "screen capture",
    "window proof",
    "屏幕截图",
    "截图",
}


def is_desktop_app_intent(message: str) -> bool:
    text = message.lower()
    if any(phrase in text for phrase in CAPTURE_ONLY_WORDS):
        return True
    return infer_desktop_app_name(message) is not None


def infer_desktop_app_name(message: str) -> str | None:
    text = message.lower()

    if not any(trigger in text for trigger in APP_TRIGGERS):
        return None

    for alias, app_name in sorted(KNOWN_DESKTOP_APPS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return app_name

    explicit_patterns = [
        r"\b(?:open|launch|start|activate|focus|use)\s+(?:the\s+)?(?:app|application|program)\s+([A-Za-z0-9 ._-]{2,50})",
        r"\b(?:open|launch|start|activate|focus|use)\s+([A-Za-z0-9 ._-]{2,50})\s+(?:app|application|program|window)\b",
    ]

    for pattern in explicit_patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return _clean_app_name(match.group(1))

    return None


def _clean_app_name(raw: str) -> str | None:
    value = re.split(r"\b(?:and|then|to|for|with|so)\b", raw, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\s+", " ", value).strip(" ._-")
    if not value:
        return None

    lowered = value.lower()
    return KNOWN_DESKTOP_APPS.get(lowered, value)
