from __future__ import annotations

import os
from tempfile import TemporaryDirectory

from reins.features.workmode.artifacts import generate_docx_artifact
from reins.features.workmode.artifacts import infer_office_artifact_format
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.hermes_planner import build_plan_from_hermes_dict
from reins.features.workmode.planner import build_fallback_plan
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.policy import get_mode_policy
from reins.features.workmode.router import ExecutionPath, choose_execution_path
from reins.features.workmode.workers.office import content_writer


def test_office_format_inference_uses_prompt_and_metadata():
    assert infer_office_artifact_format("create an Excel ledger for repairs") == "xlsx"
    assert infer_office_artifact_format("prepare PowerPoint slides for staff") == "pptx"
    assert infer_office_artifact_format("生成维修台账") == "xlsx"
    assert infer_office_artifact_format("准备会议幻灯片") == "pptx"
    assert infer_office_artifact_format("write a resident notice") == "docx"
    assert infer_office_artifact_format("write a report", {"artifact_format": "xlsx"}) == "xlsx"


def test_fallback_office_plan_keeps_requested_excel_format():
    message = "create an Excel ledger for elevator repair follow-up"
    policy = get_mode_policy("work")

    assert choose_execution_path(message) == ExecutionPath.OFFICE
    assert choose_execution_path("write a leave application for tomorrow") == ExecutionPath.OFFICE

    plan = build_fallback_plan(message, policy=policy, path=ExecutionPath.OFFICE)
    generate_step = plan.steps[0]
    present_step = plan.steps[1]

    assert generate_step.kind == "office_generate"
    assert generate_step.expected_artifacts == ["xlsx"]
    assert generate_step.metadata["artifact_format"] == "xlsx"
    assert present_step.kind == "artifact_present"
    assert present_step.metadata["artifact_kind"] == "xlsx"
    assert present_step.visible_action is True


def test_hermes_plan_repair_preserves_powerpoint_format_and_presentation():
    raw = {
        "id": "office-test",
        "intent": "prepare PowerPoint slides for resident meeting",
        "execution_path": "backend_only",
        "mode": "work",
        "summary_for_user": "Preparing slides",
        "steps": [
            {
                "id": "make-slides",
                "kind": "office_generate",
                "title": "Prepare meeting slides",
                "worker": "workmode.backend",
                "description": "Create the requested presentation.",
                "expected_artifacts": [],
                "depends_on": [],
                "metadata": {},
            }
        ],
        "risk_flags": [],
        "version": 1,
    }

    plan = build_plan_from_hermes_dict(
        raw,
        message="prepare PowerPoint slides for resident meeting",
        policy=get_mode_policy("work"),
        path=ExecutionPath.BACKEND_ONLY,
    )

    assert [step.kind for step in plan.steps] == ["office_generate", "artifact_present"]
    assert plan.steps[0].expected_artifacts == ["pptx"]
    assert plan.steps[0].metadata["artifact_format"] == "pptx"
    assert plan.steps[1].metadata["artifact_kind"] == "pptx"
    assert plan.steps[1].visible_action is True


def test_office_fallback_writes_document_not_planner_description():
    original = content_writer.call_vendor_hermes_json

    def fail_content_call(_prompt: str):
        raise RuntimeError("Hermes unavailable")

    content_writer.call_vendor_hermes_json = fail_content_call
    try:
        step = WorkStep(
            id="office-generate",
            kind="office_generate",
            title="Generate Chinese New Year resident notice",
            worker="workmode.office",
            description=(
                "Draft and produce a resident notice about the Chinese New Year festival, "
                "including holiday greetings, community reminders, and any relevant notices for residents."
            ),
            expected_artifacts=["docx"],
            metadata={"artifact_format": "docx"},
        )
        state = WorkExecutionState(
            task_id="case-office",
            message="write a resident notice, notice about the chinese new year festival",
            mode_policy=get_mode_policy("work"),
            plan_id="plan-office",
        )

        content = content_writer.generate_office_content(step, state)
    finally:
        content_writer.call_vendor_hermes_json = original

    assert content["writer"] == "fallback"
    assert content["title"] == "Resident Notice: Chinese New Year Festival"
    assert "Dear Residents" in content["body"]
    assert "Draft and produce" not in content["body"]
    assert "write a resident notice" not in content["body"]


def test_docx_renderer_does_not_duplicate_title():
    try:
        from docx import Document
    except Exception:
        return

    title = "Resident Notice: Chinese New Year Festival"
    old_home = os.environ.get("REINS_HOME")

    with TemporaryDirectory() as tmp:
        os.environ["REINS_HOME"] = tmp
        try:
            path = generate_docx_artifact(title, f"{title}\n\n[Date]\n\nDear Residents,")
            doc = Document(path)
            paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        finally:
            if old_home is None:
                os.environ.pop("REINS_HOME", None)
            else:
                os.environ["REINS_HOME"] = old_home

    assert paragraphs.count(title) == 1
