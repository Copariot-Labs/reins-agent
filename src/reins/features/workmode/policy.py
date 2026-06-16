from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


WorkModeName = Literal["work", "demo", "headless"]


@dataclass(frozen=True)
class ModePolicy:
    mode: WorkModeName
    visible_actions: bool
    window_policy: str
    narration: str
    show_terminal_logs: bool
    show_office_windows: bool
    key_action_preview_ms: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DANGEROUS_ACTIONS = {
    "send_message",
    "submit_form",
    "delete_file",
    "make_payment",
    "change_password",
    "install_software",
}


MODE_POLICIES: dict[WorkModeName, ModePolicy] = {
    "work": ModePolicy(
        mode="work",
        visible_actions=True,
        window_policy="key_windows",
        narration="concise",
        show_terminal_logs=False,
        show_office_windows=True,
        key_action_preview_ms=200,
    ),
    "demo": ModePolicy(
        mode="demo",
        visible_actions=True,
        window_policy="full_stage",
        narration="verbose",
        show_terminal_logs=True,
        show_office_windows=True,
        key_action_preview_ms=1500,
    ),
    "headless": ModePolicy(
        mode="headless",
        visible_actions=False,
        window_policy="none",
        narration="none",
        show_terminal_logs=False,
        show_office_windows=False,
        key_action_preview_ms=0,
    ),
}


def get_mode_policy(mode: str) -> ModePolicy:
    try:
        return MODE_POLICIES[mode]  # type: ignore[index]
    except KeyError as exc:
        known = ", ".join(sorted(MODE_POLICIES))
        raise ValueError(f"Unknown workmode mode: {mode}. Expected one of: {known}") from exc


def requires_confirmation(action: str, context: dict | None = None) -> bool:
    context = context or {}

    if action in DANGEROUS_ACTIONS:
        return True

    if context.get("contains_password"):
        return True

    if context.get("external_submit"):
        return True

    return False
