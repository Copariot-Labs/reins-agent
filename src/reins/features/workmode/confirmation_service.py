from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from reins.features.workmode.case_service import CaseService
from reins.features.workmode.db import save_case, save_event
from reins.features.workmode.workers.wechat.ui import send_wechat_message_after_confirmation


def _confirmation_from_event(event: dict[str, Any], confirmation_id: str) -> dict[str, Any] | None:
    data = event.get("data")
    if not isinstance(data, dict):
        return None

    confirmation = data.get("confirmation")
    if isinstance(confirmation, dict) and str(confirmation.get("id")) == confirmation_id:
        return confirmation

    confirmations = data.get("pending_confirmations")
    if isinstance(confirmations, list):
        for item in confirmations:
            if isinstance(item, dict) and str(item.get("id")) == confirmation_id:
                return item

    summary = data.get("summary")
    if isinstance(summary, dict) and isinstance(summary.get("pending_confirmations"), list):
        for item in summary["pending_confirmations"]:
            if isinstance(item, dict) and str(item.get("id")) == confirmation_id:
                return item

    return None


class ConfirmationService:
    def __init__(self) -> None:
        self.cases = CaseService()

    def find_confirmation(self, case_id: str, confirmation_id: str) -> dict[str, Any] | None:
        timeline = self.cases.get_case_timeline(case_id)
        if not timeline.get("ok"):
            return None

        for event in reversed(timeline.get("events") or []):
            confirmation = _confirmation_from_event(event, confirmation_id)
            if confirmation is not None:
                return confirmation

        return None

    def approve(self, case_id: str, confirmation_id: str) -> dict[str, Any]:
        case = self.cases.get_case(case_id)
        if not case:
            return {"ok": False, "error": "case_not_found", "case_id": case_id}

        confirmation = self.find_confirmation(case_id, confirmation_id)
        if not confirmation:
            return {
                "ok": False,
                "error": "confirmation_not_found",
                "case_id": case_id,
                "confirmation_id": confirmation_id,
            }

        save_event(case_id, "confirmation_approved", "Operator approved pending confirmation.", {
            "confirmation_id": confirmation_id,
            "confirmation": confirmation,
        })

        if confirmation.get("channel") == "wechat" and confirmation.get("action") == "send_message":
            result = send_wechat_message_after_confirmation(
                case_id=case_id,
                confirmation=confirmation,
            )
            event_type = "wechat_send_completed" if result.get("ok") else "wechat_send_failed"
            save_event(case_id, event_type, str(result.get("error") or result.get("status") or event_type), result)

            next_status = "completed" if result.get("ok") else "pending_confirmation"
            self._update_case_status(case, next_status)
            return {
                "ok": bool(result.get("ok")),
                "case_id": case_id,
                "confirmation_id": confirmation_id,
                "status": next_status,
                "result": result,
            }

        result = {
            "ok": False,
            "status": "unsupported_confirmation",
            "error": "No executor is registered for this confirmation action.",
            "confirmation": confirmation,
        }
        save_event(case_id, "confirmation_approval_failed", result["error"], result)
        return {
            "ok": False,
            "case_id": case_id,
            "confirmation_id": confirmation_id,
            "status": case.get("status"),
            "result": result,
        }

    def reject(self, case_id: str, confirmation_id: str, reason: str = "") -> dict[str, Any]:
        case = self.cases.get_case(case_id)
        if not case:
            return {"ok": False, "error": "case_not_found", "case_id": case_id}

        confirmation = self.find_confirmation(case_id, confirmation_id)
        if not confirmation:
            return {
                "ok": False,
                "error": "confirmation_not_found",
                "case_id": case_id,
                "confirmation_id": confirmation_id,
            }

        data = {
            "confirmation_id": confirmation_id,
            "confirmation": confirmation,
            "reason": reason,
        }
        save_event(case_id, "confirmation_rejected", "Operator rejected pending confirmation.", data)
        self._update_case_status(case, "rejected")
        return {
            "ok": True,
            "case_id": case_id,
            "confirmation_id": confirmation_id,
            "status": "rejected",
        }

    def _update_case_status(self, case: dict[str, Any], status: str) -> None:
        updated = dict(case)
        updated["status"] = status
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_case(updated)
