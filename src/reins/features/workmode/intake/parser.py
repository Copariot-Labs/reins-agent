from reins.features.workmode.intake.schema import ResidentIssue


class ResidentIntakeParser:
    def parse(self, text: str) -> ResidentIssue:
        text_lower = text.lower()

        # -------- ISSUE TYPE --------
        if any(k in text_lower for k in ["leak", "water", "pipe", "electric", "fire"]):
            issue_type = "repair"
        elif any(k in text_lower for k in ["complaint", "noisy", "rude"]):
            issue_type = "complaint"
        elif any(k in text_lower for k in ["danger", "accident", "unsafe"]):
            issue_type = "safety"
        elif any(k in text_lower for k in ["request", "need", "install"]):
            issue_type = "service_request"
        else:
            issue_type = "other"

        # -------- PRIORITY --------
        if any(k in text_lower for k in ["urgent", "emergency", "fire", "leak"]):
            priority = "urgent"
        elif any(k in text_lower for k in ["soon", "asap"]):
            priority = "high"
        elif any(k in text_lower for k in ["later"]):
            priority = "low"
        else:
            priority = "medium"

        # -------- LOCATION --------
        location = None
        for word in text.split():
            if "building" in word.lower() or "room" in word.lower():
                location = word

        return ResidentIssue(
            raw_text=text,
            issue_type=issue_type,
            priority=priority,
            location=location,
            description=text,
            required_action=self._generate_action(issue_type),
        )

    def _generate_action(self, issue_type: str) -> str:
        if issue_type == "repair":
            return "Dispatch maintenance team and inspect issue"
        if issue_type == "complaint":
            return "Log complaint and notify admin"
        if issue_type == "safety":
            return "Immediate safety response required"
        if issue_type == "service_request":
            return "Schedule service fulfillment"
        return "Review manually"