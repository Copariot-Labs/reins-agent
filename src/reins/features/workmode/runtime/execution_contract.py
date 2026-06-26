from dataclasses import dataclass
from typing import Literal


ExecutionKind = Literal[
    "browser_source",
    "desktop_capture",
    "ocr",
    "office_generate",
    "artifact_present",
    "wechat_prepare",
    "confirmation_gate",
    "backend_only",
    "backend_process",
    "result_present",
]


@dataclass(frozen=True)
class ExecutionContract:
    """
    HARD RULES:
    - No heuristic routing allowed
    - Every step must match a valid execution kind
    """

    VISUAL_KINDS = {
        "browser_source",
        "desktop_capture",
    }

    NON_VISUAL_KINDS = {
        "ocr",
        "office_generate",
        "artifact_present",
        "wechat_prepare",
        "confirmation_gate",
        "backend_only",
        "backend_process",
        "result_present",
    }

    @staticmethod
    def is_visual(kind: str) -> bool:
        return kind in ExecutionContract.VISUAL_KINDS

    @staticmethod
    def validate(kind: str) -> None:
        if kind not in ExecutionContract.VISUAL_KINDS and kind not in ExecutionContract.NON_VISUAL_KINDS:
            raise Exception(f"[EXEC CONTRACT ERROR] Invalid kind: {kind}")
