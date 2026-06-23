from reins.features.workmode.case_service import CaseService


class CaseReplayEngine:

    def __init__(self):
        self.service = CaseService()

    def replay(self, case_id: str):
        data = self.service.replay_case(case_id)

        for event in data["timeline"]:
            yield {
                "type": "replay.event",
                "event": event,
            }

        yield {
            "type": "replay.finished",
            "case_id": case_id,
            "artifact_count": len(data["artifacts"]),
        }