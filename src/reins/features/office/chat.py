from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

from reins.features.office.service import create_office_document


@dataclass(slots=True)
class OfficeChatResult:
    handled: bool
    message: str = ""
    exit_code: int = 0
    document: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "handled": self.handled,
            "message": self.message,
            "exit_code": self.exit_code,
            "document": self.document,
        }


CREATE_PATTERN = re.compile(
    r"\b(create|make|generate|write|prepare|draft|build|compose|produce|design|assemble|compile|format|export|save|convert)\b",
    re.IGNORECASE,
)
CREATE_PHRASE_PATTERN = re.compile(
    r"\b(?:put|pull)\s+together\b|\bturn\b.{0,80}\binto\b",
    re.IGNORECASE,
)
QUESTION_PATTERN = re.compile(
    r"^(how\s+to\s+|how\s+can\s+i\s+|what\s+is\s+|why\s+|can\s+you\s+explain\s+)",
    re.IGNORECASE,
)
CHINESE_QUESTION_PATTERN = re.compile(r"^(如何|怎么|怎样|为什么|什么是|请解释|请介绍)")
DOCUMENT_PATTERN = re.compile(
    r"\b(document|docx?|word|letter|application|report|proposal|summary|resume|cv|notice|program|plan|minutes|memo|policy|agreement|contract|statement|certificate|form|invoice|receipt|agenda|briefing)\b",
    re.IGNORECASE,
)
SPREADSHEET_PATTERN = re.compile(
    r"\b(spreadsheet|excel|xlsx|workbook|sheets?|table|ledger|tracker|budget|inventory|roster)\b",
    re.IGNORECASE,
)
PRESENTATION_PATTERN = re.compile(
    r"\b(presentation|pptx?|slides?|slide deck|deck|powerpoint)\b",
    re.IGNORECASE,
)
CHINESE_CREATE_PATTERN = re.compile(r"创建|制作|生成|写一份|撰写|编写|准备|起草|整理|汇总|输出|形成|保存|转换|导出|做一个|做一份|出一份")
CHINESE_DOCUMENT_PATTERN = re.compile(r"文档|Word|报告|总结|简报|公文|通知|公告|倡议书|申请|合同|简历|计划|方案|会议记录|会议纪要|纪要", re.IGNORECASE)
CHINESE_SPREADSHEET_PATTERN = re.compile(r"台账|清单|表格|电子表格|工作簿|Excel", re.IGNORECASE)
CHINESE_PRESENTATION_PATTERN = re.compile(r"演示文稿|幻灯片|PPT", re.IGNORECASE)


def infer_office_format(message: str) -> str | None:
    text = str(message or "")
    if SPREADSHEET_PATTERN.search(text) or CHINESE_SPREADSHEET_PATTERN.search(text):
        return "xlsx"
    if PRESENTATION_PATTERN.search(text) or CHINESE_PRESENTATION_PATTERN.search(text):
        return "pptx"
    if DOCUMENT_PATTERN.search(text) or CHINESE_DOCUMENT_PATTERN.search(text):
        return "docx"
    return None


def should_handle_office_chat(message: str) -> bool:
    text = str(message or "").strip()
    if (
        not text
        or text.startswith("/")
        or QUESTION_PATTERN.search(text)
        or CHINESE_QUESTION_PATTERN.search(text)
    ):
        return False
    has_create_intent = bool(
        CREATE_PATTERN.search(text)
        or CREATE_PHRASE_PATTERN.search(text)
        or CHINESE_CREATE_PATTERN.search(text)
    )
    return has_create_intent and infer_office_format(text) is not None


def open_command_for_path(path: str, *, platform: str | None = None) -> str:
    current_platform = platform or sys.platform
    if current_platform == "win32":
        return f'start "" "{path}"'
    if current_platform == "darwin":
        return f'open "{path}"'
    return f'xdg-open "{path}"'


def preprocess_office_text(
    message: str,
    *,
    verbose: bool = True,
) -> OfficeChatResult:
    if not should_handle_office_chat(message):
        return OfficeChatResult(handled=False)

    office_format = infer_office_format(message) or "docx"
    if verbose:
        print(f"Reins Office request detected. Format: {office_format}")

    try:
        record = create_office_document(
            prompt=message,
            office_format=office_format,
            language="zh" if re.search(r"[\u3400-\u9fff]", message) else "en",
        )
    except Exception as exc:
        return OfficeChatResult(
            handled=True,
            message=f"Failed to create Office document: {exc}",
            exit_code=1,
        )

    document = record.to_dict()
    output = "\n".join(
        [
            "Office document created successfully.",
            f"Title: {record.title}",
            f"Type: {record.kind}",
        ]
    )
    return OfficeChatResult(
        handled=True,
        message=output,
        exit_code=0,
        document=document,
    )
