from reins.features.workmode.db import save_event, save_case, save_artifact


def persist_case(case):
    save_case(case)


def persist_event(case_id, event):
    save_event(
        case_id=case_id,
        event_type=event.type,
        message=event.message,
        data=event.data or {}
    )


def persist_artifact(case_id, artifact):
    save_artifact(case_id, artifact)