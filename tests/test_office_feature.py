from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

import reins.features.office.cli as office_cli
import reins.features.office.content_writer as office_content_writer
import reins.features.office.service as office_service
from reins.features.office.editor import (
    OfficeRevisionError,
    build_revision_prompt,
    build_presentation_revision_prompt,
    canonicalize_excel_revision_inspection,
    canonicalize_presentation_revision_inspection,
    canonicalize_revision_plan_paths,
    canonicalize_word_revision_inspection,
    inherit_word_revision_formatting,
    normalize_revision_plan,
)
from reins.features.office.intent import classify_office_followup
from reins.features.office.content_writer import (
    DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    OfficeContentError,
    OfficeContentResponseError,
    OfficeContentTimeoutError,
    build_office_content_prompt,
    generate_office_content,
)
from reins.features.office.chat import infer_office_format, should_handle_office_chat
from reins.features.office.officecli_client import officecli_batch_item
from reins.features.office.renderer import render_office_content
from reins.features.office.schemas import (
    OfficeDocumentRecord,
    normalize_office_format,
    normalize_presentation_options,
)
from reins.features.office.service import (
    OfficeServiceError,
    create_office_document,
    import_office_document,
    list_office_documents,
    preview_office_document,
    revise_office_document,
)
from reins.features.office.workflows import (
    OfficeWorkflowError,
    get_office_workflow,
    list_office_workflows,
)


@pytest.fixture(autouse=True)
def configure_reins_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_WORKSPACE_ROOT", str(tmp_path / "Reins Workspace"))


class FakeOfficeCliClient:
    binary = "/fake/officecli"

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.run_options: list[dict[str, object]] = []

    @property
    def command_count(self) -> int:
        return len(self.commands)

    def run(self, args, **kwargs):
        command = [str(arg) for arg in args]
        self.commands.append(command)
        self.run_options.append(dict(kwargs))
        if command and command[0] == "create":
            Path(command[1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[1]).touch()
        if command[:1] == ["view"] and "html" in command and "-o" in command:
            output = Path(command[command.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("<html><body>Office preview</body></html>", encoding="utf-8")
        stdout = ""
        if len(command) > 2 and command[0] == "view" and command[2] == "outline":
            stdout = '/body/p[1] (paragraph) "Pending"'
        elif len(command) > 2 and command[0] == "view" and command[2] == "annotated":
            stdout = '/body/p[1] (paragraph) "Pending" style=Normal'
        elif command[:1] == ["validate"]:
            stdout = "no errors found"
        elif command[:1] == ["view"] and "issues" in command:
            stdout = '{"count":0,"issues":[]}'
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


class BatchOfficeCliClient(FakeOfficeCliClient):
    def __init__(self) -> None:
        super().__init__()
        self.batches: list[list[dict[str, object]]] = []

    def run_batch(self, path, commands, **kwargs):
        batch = list(commands)
        self.batches.append(batch)
        self.commands.append(["batch", str(path)])
        self.run_options.append(dict(kwargs))
        return SimpleNamespace(stdout='{"success":true}', stderr="", returncode=0)


def test_office_format_aliases():
    assert normalize_office_format("word") == "docx"
    assert normalize_office_format("excel") == "xlsx"
    assert normalize_office_format("ppt") == "pptx"
    assert normalize_office_format("unknown") == "docx"


def test_officecli_batch_item_preserves_unicode_properties():
    item = officecli_batch_item(
        [
            "add",
            "C:/Users/test/Documents/Reins Workspace/Word/report.docx",
            "/body",
            "--type",
            "paragraph",
            "--prop",
            "text=社区第四季度工作计划",
            "--prop",
            "bold=true",
        ]
    )

    assert item == {
        "command": "add",
        "parent": "/body",
        "type": "paragraph",
        "props": {"text": "社区第四季度工作计划", "bold": "true"},
    }


def test_office_cli_uses_long_running_model_timeout_by_default():
    assert DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS == 1_200

    parser = office_cli.build_parser()
    assert parser.parse_args(["create", "--prompt", "生成工作计划"]).timeout == 1_200
    assert parser.parse_args(
        ["revise", "--id", "office_1", "--instruction", "补充详细内容"]
    ).timeout == 1_200


def _write_minimal_office_package(path: Path, member: str) -> None:
    with ZipFile(path, "w") as package:
        package.writestr(member, "<root />")


def test_import_office_document_validates_copies_and_registers_file(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path / "home"))
    source = tmp_path / "upload.docx"
    _write_minimal_office_package(source, "word/document.xml")

    imported = import_office_document(
        source_path=source,
        office_format="docx",
        display_name="阳光社区工作计划.docx",
    )

    assert imported.title == "阳光社区工作计划"
    assert imported.kind == "docx"
    assert imported.generator == "import"
    assert imported.metadata == {
        "imported": True,
        "source_file_name": "阳光社区工作计划.docx",
    }
    assert Path(imported.path).parent.name == "Word"
    assert Path(imported.path).read_bytes() == source.read_bytes()
    assert list_office_documents(limit=0)[-1].id == imported.id


def test_import_office_document_rejects_the_wrong_section(tmp_path):
    source = tmp_path / "upload.docx"
    _write_minimal_office_package(source, "word/document.xml")

    with pytest.raises(OfficeServiceError, match="only accepts .xlsx"):
        import_office_document(
            source_path=source,
            office_format="xlsx",
            display_name="社区工作计划.docx",
        )


def test_import_office_document_rejects_renamed_non_office_file(tmp_path):
    source = tmp_path / "upload.pptx"
    source.write_text("not a presentation", encoding="utf-8")

    with pytest.raises(OfficeServiceError, match="not a valid PPTX package"):
        import_office_document(
            source_path=source,
            office_format="pptx",
        )


def test_reins_semantically_routes_an_uncommon_office_followup():
    prompts = []

    decision = classify_office_followup(
        message="give the previous file a fresher voice",
        document_title="Community Plan",
        document_kind="docx",
        planner=lambda prompt, _timeout: (
            prompts.append(prompt),
            {"intent": "revise", "format": None, "confidence": 0.91},
        )[1],
    )

    assert decision == {"intent": "revise", "format": None, "confidence": 0.91}
    assert "do not depend on keywords" in prompts[0]
    assert "Never propose terminal commands" in prompts[0]


def test_fixed_office_workflows_are_grouped_and_format_checked():
    workflows = list_office_workflows()

    assert len(workflows) == 10
    assert len(list_office_workflows(office_format="docx")) == 5
    assert len(list_office_workflows(office_format="xlsx")) == 2
    assert len(list_office_workflows(office_format="pptx")) == 3
    assert get_office_workflow("community-work-plan", office_format="docx").label_zh == "社区工作计划"

    try:
        get_office_workflow("community-work-plan", office_format="pptx")
    except OfficeWorkflowError as exc:
        assert "creates docx" in str(exc)
    else:
        raise AssertionError("A workflow must not be used with another Office format.")


def test_fixed_workflow_is_injected_as_a_content_contract():
    prompt = build_office_content_prompt(
        user_prompt="Create Sunshine Community's Q3 plan",
        office_format="docx",
        skill_id="community-work-plan",
    )

    assert "Reins Office 固定文档技能" in prompt
    assert "community-work-plan" in prompt
    assert "Word 任务分解表" in prompt
    assert "不是工具、插件、软件包" in prompt
    assert "不得改为通用模板" in prompt
    assert "最终文件仍必须采用当前所选固定技能" in prompt
    assert "Never answer with a question" in prompt
    assert "Missing names, dates, locations" in prompt
    assert 'When Language is "zh", use natural Simplified Chinese' in prompt


def test_office_content_uses_the_configured_reins_model_without_a_nested_cli(monkeypatch):
    captured = {}

    def call_model(messages, *, timeout):
        captured["messages"] = messages
        captured["timeout"] = timeout
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"title":"阳光社区工作计划","office_format":"docx","body":"正文"}'
                    )
                )
            ]
        )

    monkeypatch.setattr(office_content_writer, "_call_office_content_model", call_model)

    payload = office_content_writer.call_reins_json("生成社区工作计划", timeout=37)

    assert payload["title"] == "阳光社区工作计划"
    assert captured["timeout"] == 37
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][1] == {"role": "user", "content": "生成社区工作计划"}


def test_office_content_timeout_never_exposes_the_prompt_or_command(monkeypatch):
    secret_prompt = "生成阳光社区工作计划并包含内部敏感内容"

    def timeout(_messages, *, timeout):
        command = ["python", "-m", "reins.main", "-z", secret_prompt]
        raise TimeoutError(f"Command {command!r} timed out")

    monkeypatch.setattr(office_content_writer, "_call_office_content_model", timeout)

    with pytest.raises(OfficeContentTimeoutError) as captured:
        office_content_writer.call_reins_json(secret_prompt, timeout=300)

    assert str(captured.value) == "Reins content planning timed out after 300 seconds."
    assert secret_prompt not in str(captured.value)


def test_fixed_skill_retries_once_when_reins_returns_unstructured_text(monkeypatch):
    prompts = []

    def generate(prompt, *, timeout):
        prompts.append((prompt, timeout))
        if len(prompts) == 1:
            raise OfficeContentResponseError("Reins did not return a JSON object.")
        return {
            "title": "阳光社区2026年第三季度工作计划",
            "office_format": "docx",
            "body": "一、总体目标\n扎实推进防汛和垃圾分类工作。",
            "document_kind": "report",
            "tables": [
                {
                    "headers": ["任务", "具体措施", "责任部门", "完成时限", "预期成果"],
                    "rows": [["防汛", "开展隐患排查", "社区相关岗位", "第三季度", "风险闭环"]],
                }
            ],
            "missing_fields": [],
        }

    monkeypatch.setattr(office_content_writer, "_call_reins_json", generate)

    content = generate_office_content(
        prompt="为阳光社区编写2026年第三季度工作计划，重点包括防汛和垃圾分类。",
        office_format="docx",
        skill_id="community-work-plan",
    )

    assert len(prompts) == 2
    assert "JSON response retry" in prompts[1][0]
    assert "community-work-plan" in prompts[1][0]
    assert "Do not ask the user for more information" in prompts[1][0]
    assert content["generator"] == "reins"
    assert content["tables"][0]["headers"][0] == "任务"


def test_fixed_skill_does_not_retry_runtime_or_model_failures(monkeypatch):
    calls = 0

    def fail(_prompt, *, timeout):
        nonlocal calls
        calls += 1
        raise OfficeContentError("No LLM provider configured")

    monkeypatch.setattr(office_content_writer, "_call_reins_json", fail)

    with pytest.raises(OfficeContentError, match="No LLM provider configured"):
        generate_office_content(
            prompt="生成第三季度社区工作计划",
            office_format="docx",
            skill_id="community-work-plan",
        )

    assert calls == 1


def test_fixed_skill_retries_a_json_clarification_response(monkeypatch):
    responses = [
        {
            "title": "请补充文件信息",
            "office_format": "docx",
            "body": "请提供更多文档详情，包括文件用途、主要内容和格式要求。",
        },
        {
            "title": "阳光社区第三季度工作计划",
            "office_format": "docx",
            "body": "一、总体目标\n推进防汛和垃圾分类重点工作。",
        },
    ]

    monkeypatch.setattr(
        office_content_writer,
        "_call_reins_json",
        lambda _prompt, *, timeout: responses.pop(0),
    )

    content = generate_office_content(
        prompt="制定社区第三季度工作计划",
        office_format="docx",
        skill_id="community-work-plan",
    )

    assert content["title"] == "阳光社区第三季度工作计划"
    assert not responses


@pytest.mark.parametrize(
    "workflow",
    list_office_workflows(),
    ids=lambda workflow: workflow["id"],
)
def test_every_fixed_office_skill_is_injected_during_creation(workflow):
    workflow_contract = get_office_workflow(
        workflow["id"],
        office_format=workflow["format"],
    )
    prompt = build_office_content_prompt(
        user_prompt=workflow["placeholder_zh"],
        office_format=workflow["format"],
        skill_id=workflow["id"],
    )

    assert f"技能 ID：{workflow['id']}" in prompt
    assert workflow_contract.instruction in prompt
    assert "技能规定的结构、用途和文种优先级最高" in prompt


def test_main_chat_routes_document_requests_to_office():
    assert should_handle_office_chat("create a maintenance notice document")
    assert infer_office_format("create an Excel maintenance tracker") == "xlsx"
    assert infer_office_format("制作一个会议演示文稿") == "pptx"
    assert should_handle_office_chat("整理8月社区两委联席会议纪要")
    assert infer_office_format("整理8月社区两委联席会议纪要") == "docx"
    assert should_handle_office_chat("Put together a Word briefing for the quarterly review")
    assert should_handle_office_chat("Convert this quarterly summary into a Word document")
    assert should_handle_office_chat("将这份内容导出为PPT")
    assert not should_handle_office_chat("把这些想法整理一下")
    assert not should_handle_office_chat("如何制作一个PPT？")
    assert not should_handle_office_chat("what is a maintenance report?")
    assert not should_handle_office_chat("hello")


def test_legacy_generator_name_is_presented_as_reins():
    record = OfficeDocumentRecord.from_dict(
        {
            "id": "office_legacy",
            "title": "Legacy deck",
            "kind": "pptx",
            "path": "/tmp/legacy.pptx",
            "generator": "hermes",
        }
    )

    assert record.generator == "reins"


def test_office_fallback_content_matches_requested_format():
    content = generate_office_content(
        prompt="create an Excel repair tracker",
        office_format="xlsx",
        use_reins=False,
    )

    assert content["office_format"] == "xlsx"
    assert content["generator"] == "fallback"
    assert content["sheets"]
    assert not content["slides"]


def test_packaged_office_brain_prefers_private_python_over_recursive_launcher(
    tmp_path,
    monkeypatch,
):
    service_python = tmp_path / "python.exe"
    service_python.write_bytes(b"")
    monkeypatch.setenv("REINS_SERVICE_PYTHON", str(service_python))
    monkeypatch.setenv("REINS_BIN", str(tmp_path / "reins-runtime.exe"))

    invocation = office_content_writer._resolve_reins_invocation()

    assert invocation is not None
    assert invocation.command == [str(service_python), "-m", "reins.main"]


def test_word_and_excel_prompts_make_reins_the_design_decision_maker():
    word_prompt = build_office_content_prompt(
        user_prompt="Create a formal navy annual report",
        office_format="docx",
    )
    excel_prompt = build_office_content_prompt(
        user_prompt="Create a clean financial budget workbook",
        office_format="xlsx",
    )

    assert "Reins is the document designer" in word_prompt
    assert '"title_treatment": "plain|rule|band|boxed"' in word_prompt
    assert "If the user explicitly requests a design" in word_prompt
    assert "Reins is the workbook designer" in excel_prompt
    assert '"header_style": "dark|accent|light|outline"' in excel_prompt
    assert '"column_formats"' in excel_prompt
    assert "If the user specifies colors, style, density" in excel_prompt


def test_presentation_prompt_requests_a_designed_narrative():
    options = normalize_presentation_options(
        {
            "style": "executive",
            "slide_count": 10,
            "audience": "client",
            "detail": "detailed",
        }
    )
    prompt = build_office_content_prompt(
        user_prompt="Create a launch strategy deck",
        office_format="pptx",
        presentation_options=options,
    )

    assert "Create exactly 10 slides" in prompt
    assert "Requested style: executive" in prompt
    assert '"background": "6-digit HEX without #"' in prompt
    assert '"composition": "editorial|geometric|split|spotlight"' in prompt
    assert '"variant": "auto|editorial|geometric|split|spotlight"' in prompt
    assert "Reins is the presentation art director" in prompt
    assert "Use at least four different layouts" in prompt
    assert '"layout": "cover|agenda|statement|kpi|cards|comparison|timeline|chart|quote|closing"' in prompt
    assert '"notes": "speaker script or useful talking points"' in prompt


def test_renderer_emits_modern_pptx_layouts_notes_and_quality_check(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "strategy.pptx"
    content = {
        "title": "Service Momentum",
        "design": {"style": "executive"},
        "slides": [
            {
                "layout": "cover",
                "title": "Service Momentum",
                "subtitle": "A focused operating review",
                "notes": "Open with the service objective.",
            },
            {
                "layout": "chart",
                "title": "Response speed improves as coverage expands",
                "chart": {
                    "type": "column",
                    "title": "Median response time",
                    "categories": ["Q1", "Q2", "Q3"],
                    "series": [
                        {"name": "Actual", "values": [42, 31, 22]},
                        {"name": "Target", "values": [38, 28, 20]},
                    ],
                },
                "takeaway": "Coverage closes most of the response-time gap.",
                "notes": "Explain the trend and remaining gap.",
            },
            {
                "layout": "closing",
                "title": "Protect the gains with clear ownership",
                "bullets": ["Confirm the owner", "Publish the scorecard"],
                "notes": "Close with ownership and cadence.",
            },
        ],
    }

    render_office_content(
        office_format="pptx",
        content=content,
        output_path=output,
        client=client,
    )

    slide_commands = [
        command
        for command in client.commands
        if command[:1] == ["add"] and "--type" in command
        and command[command.index("--type") + 1] == "slide"
    ]
    note_commands = [
        command
        for command in client.commands
        if command[:1] == ["add"] and "--type" in command
        and command[command.index("--type") + 1] == "notes"
    ]

    assert len(slide_commands) == 3
    assert all("layout=blank" in command for command in slide_commands)
    assert len(note_commands) == 3
    assert any(
        "chartType=column" in command
        and "series1.values=42,31,22" in command
        and "series2.values=38,28,20" in command
        for command in client.commands
    )
    assert any("autoFit=normal" in command for command in client.commands)
    assert ["view", str(output), "issues", "--json"] in client.commands


def test_renderer_uses_reins_custom_presentation_palette(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "custom-theme.pptx"

    render_office_content(
        office_format="pptx",
        content={
            "title": "Custom Theme",
            "design": {
                "style": "modern",
                "background": "F0FFF4",
                "surface": "FFFFFF",
                "primary": "123456",
                "secondary": "BEE3F8",
                "accent": "C53030",
                "warm": "D69E2E",
                "text": "1A202C",
                "muted": "4A5568",
                "heading_font": "Georgia",
                "body_font": "Arial",
            },
            "slides": [{"layout": "cover", "title": "Custom Theme"}],
        },
        output_path=output,
        client=client,
    )

    serialized = " ".join(" ".join(command) for command in client.commands)
    assert "background=123456-C53030-145" in serialized
    assert "fill=C53030" in serialized
    assert "font=Georgia" in serialized


def test_renderer_changes_slide_geometry_for_split_composition(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "split-composition.pptx"

    render_office_content(
        office_format="pptx",
        content={
            "title": "Split Composition",
            "design": {"style": "modern", "composition": "split", "motif": "blocks"},
            "slides": [
                {"layout": "cover", "title": "Split Composition"},
                {
                    "layout": "cards",
                    "variant": "split",
                    "title": "One feature leads the supporting ideas",
                    "cards": [
                        {"title": "Lead", "body": "The primary idea receives visual priority."},
                        {"title": "Support", "body": "Supporting context is stacked separately."},
                        {"title": "Action", "body": "The final point makes the next move clear."},
                    ],
                },
            ],
        },
        output_path=output,
        client=client,
    )

    serialized = " ".join(" ".join(command) for command in client.commands)
    assert "width=12.60cm" in serialized
    assert "width=13.20cm" in serialized
    assert "x=15.55cm" in serialized


def test_renderer_applies_reins_word_design(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "report.docx"

    render_office_content(
        office_format="docx",
        content={
            "title": "Annual Review",
            "body": "Executive Summary:\nA concise review of the year.\n\nPriorities:\n- Protect service quality",
            "tables": [
                {
                    "title": "Task breakdown",
                    "headers": ["Task", "Owner", "Deadline"],
                    "rows": [["Review services", "Operations", "Q3"]],
                }
            ],
            "design": {
                "style": "formal",
                "primary": "172554",
                "secondary": "E8EEF6",
                "accent": "B45309",
                "heading_font": "Georgia",
                "body_font": "Times New Roman",
                "title_treatment": "band",
                "heading_treatment": "shaded",
                "title_alignment": "left",
                "page_size": "letter",
                "margins": "generous",
                "body_size": 12,
                "line_spacing": "1.3x",
            },
        },
        output_path=output,
        client=client,
    )

    serialized = " ".join(" ".join(command) for command in client.commands)
    assert "pageWidth=21.59cm" in serialized
    assert "marginLeft=3cm" in serialized
    assert "docDefaults.font=Times New Roman" in serialized
    assert "theme.font.major.latin=Georgia" in serialized
    assert "shading.fill=172554" in serialized
    assert "shading.fill=E8EEF6" in serialized
    assert "lineSpacing=1.3x" in serialized
    assert "--type table" in serialized
    assert "rows=2" in serialized
    assert "cols=3" in serialized
    assert "/body/tbl[1]/tr[1]/tc[1]" in serialized
    assert "text=Review services" in serialized


def test_renderer_stages_chinese_workspace_filename_through_ascii_officecli_path(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "玫瑰湾社区2026年第四季度工作计划.docx"

    result = render_office_content(
        office_format="docx",
        content={
            "title": "玫瑰湾社区2026年第四季度工作计划",
            "body": "一、总体目标\n做好社区第四季度重点工作。",
            "tables": [],
        },
        output_path=output,
        client=client,
    )

    officecli_path = Path(client.commands[0][1])
    assert result == output
    assert output.is_file()
    assert officecli_path != output
    assert officecli_path.name.isascii()
    assert officecli_path.suffix == ".docx"
    assert not officecli_path.exists()
    assert all(
        len(command) < 2 or Path(command[1]) == officecli_path
        for command in client.commands
    )


def test_renderer_emits_designed_officecli_xlsx_commands(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "tracker.xlsx"

    render_office_content(
        office_format="xlsx",
        content={
            "title": "Repair Tracker",
            "body": "Operational repair status",
            "design": {
                "style": "tracker",
                "primary": "264653",
                "secondary": "E9F5F2",
                "accent": "E76F51",
                "header_style": "accent",
                "row_density": "spacious",
                "table_style": "medium3",
                "show_title": True,
                "banded_rows": True,
            },
            "sheets": [
                {
                    "name": "Repairs",
                    "headers": ["ID", "Status"],
                    "rows": [[1, "Open"], [2, "Overdue"]],
                    "column_formats": [{"column": "ID", "format": "integer"}],
                    "column_widths": [{"column": "Status", "width": 24}],
                    "conditional_highlights": [
                        {"column": "Status", "contains": "Overdue", "fill": "FDE8E7"}
                    ],
                }
            ],
        },
        output_path=output,
        client=client,
    )

    assert output.exists()
    assert client.commands[0] == ["create", str(output)]
    assert ["open", str(output)] in client.commands
    assert ["set", str(output), "/Sheet1", "--prop", "name=Repairs"] in client.commands
    serialized = " ".join(" ".join(command) for command in client.commands)
    assert "merge=A1:B1" in serialized
    assert "value=ID" in serialized and "/Repairs/A3" in serialized
    assert "fill=E76F51" in serialized
    assert "numberformat=#,##0" in serialized
    assert "width=24" in serialized
    assert "type=containsText" in serialized
    assert "ref=B4:B5" in serialized
    assert "style=medium3" in serialized
    assert "freeze=A4" in serialized
    assert ["validate", str(output)] in client.commands


def test_create_office_document_registers_separate_office_record(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    client = FakeOfficeCliClient()
    progress = []

    record = create_office_document(
        prompt="write a resident notice",
        office_format="docx",
        use_reins=False,
        client=client,
        progress=lambda stage, percent, message_zh, message_en: progress.append(
            (stage, percent, message_zh, message_en)
        ),
    )

    assert record.kind == "docx"
    assert record.path.startswith(str((tmp_path / "Reins Workspace" / "Word").resolve()))
    assert Path(record.path).exists()
    assert record.generator == "fallback"

    records = list_office_documents(limit=10)
    assert [item.id for item in records] == [record.id]
    assert [event[0] for event in progress] == [
        "accepted",
        "skill_ready",
        "content_generation",
        "content_ready",
        "officecli_prepare",
        "officecli_render",
        "validating",
        "file_ready",
        "saving",
        "completed",
    ]
    assert progress[-1][1] == 100
    assert progress[-1][2] == "文件生成完成"


def test_revision_plan_rejects_non_officecli_mutations():
    try:
        normalize_revision_plan(
            {
                "summary": "Run a shell command",
                "commands": [{"verb": "exec", "arguments": ["/", "rm", "file"]}],
            }
        )
    except OfficeRevisionError as exc:
        assert "disallowed verb" in str(exc)
    else:
        raise AssertionError("unsafe revision verb was accepted")


def test_revision_plan_rejects_find_and_replace_as_cell_properties():
    try:
        normalize_revision_plan(
            {
                "summary": "Replace a cell label",
                "commands": [
                    {
                        "verb": "set",
                        "arguments": [
                            "/筛选说明/B11",
                            "--prop",
                            "find=旧说明",
                            "--prop",
                            "replace=新说明",
                        ],
                    }
                ],
            }
        )
    except OfficeRevisionError as exc:
        assert "find as a property" in str(exc)
    else:
        raise AssertionError("unsupported Excel find/replace properties were accepted")


def test_word_revision_paths_are_canonicalized_for_packaged_officecli():
    inspection, aliases = canonicalize_word_revision_inspection(
        {
            "outline": "",
            "text": (
                '[/body/p[@paraId=0010006D]] 「标题」 ← Heading 1\n'
                '[/body/p[@paraId=0010006E]] 「正文」 ← Normal\n'
                '[/body/p[@paraId=0010006E]] 「续文」 ← Normal'
            ),
            "issues": '{"count":0,"issues":[]}',
        }
    )

    assert "@paraId=" not in inspection["text"]
    assert "/body/p[1]" in inspection["text"]
    assert inspection["text"].count("/body/p[2]") == 2
    assert aliases["/body/p[@paraId=0010006E]"] == "/body/p[2]"

    plan = canonicalize_revision_plan_paths(
        {
            "summary": "Updated the second paragraph",
            "commands": [
                ["set", "/body/p[@paraId=0010006E]", "--prop", "bold=true"]
            ],
        },
        aliases,
    )
    assert plan["commands"] == [
        ["set", "/body/p[2]", "--prop", "bold=true"]
    ]

    with pytest.raises(OfficeRevisionError, match="positional paragraph path"):
        canonicalize_revision_plan_paths(
            {
                "summary": "Invalid unknown paragraph",
                "commands": [
                    ["set", "/body/p[@paraId=00FFFFFF]", "--prop", "bold=true"]
                ],
            }
        )


def test_word_revision_normalizes_natural_language_character_spacing():
    plan = normalize_revision_plan(
        {
            "summary": "Adjusted title typography",
            "commands": [
                {
                    "verb": "set",
                    "arguments": [
                        "/body/p[1]",
                        "--prop",
                        "spacing=2 characters",
                        "--prop",
                        "letterSpacing=1.5字符",
                    ],
                }
            ],
        }
    )

    assert plan["commands"] == [
        [
            "set",
            "/body/p[1]",
            "--prop",
            "spacing=2pt",
            "--prop",
            "letterSpacing=1.5pt",
        ]
    ]


def test_word_revision_prompt_includes_existing_design_and_revision_context():
    record = OfficeDocumentRecord(
        id="office_word_design",
        title="AI in Daily Life",
        kind="docx",
        path="/tmp/ai.docx",
        file_name="ai.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        created_at="2026-09-02T00:00:00+00:00",
        updated_at="2026-09-02T00:00:00+00:00",
        revision_count=1,
        metadata={
            "last_revision": {
                "instruction": "add an AI agent section",
                "summary": "Added the AI agent section",
                "changed_paths": ["/body"],
            }
        },
    )

    prompt = build_revision_prompt(
        record=record,
        instruction="make the new section follow the document design",
        inspection={
            "outline": "/body/p[1]",
            "text": '[/body/p[1]] 「AI in Daily Life」 ← Title',
            "formatting": (
                '/body/p[1]\t[Title]\t"AI in Daily Life"\t'
                "styleId=Title\tsize=24pt"
            ),
            "issues": "{}",
        },
    )

    assert "Added the AI agent section" in prompt
    assert "OfficeCLI Word paragraph formatting" in prompt
    assert "size=24pt" in prompt
    assert "Preserve the existing document language" in prompt
    assert "style name alone may not reproduce the visible design" in prompt


def test_word_additions_inherit_missing_properties_from_existing_design():
    inspection = {
        "formatting": (
            '/body/p[1]\t[Heading1]\t"Existing heading"\tstyleId=Heading1\t'
            'styleName=Heading1\tfont=\tsize=16pt\tcolor=#1F3864\tbold=True\t'
            'italic=\talign=\tspaceBefore=14pt\tspaceAfter=7pt\tlineSpacing=\t'
            'firstLineIndent=\tlistStyle=\tnumId=\tnumLevel=\n'
            '/body/p[2]\t[Normal]\t"Existing body"\tstyleId=\tstyleName=\tfont=\t'
            'size=11pt\tcolor=#262626\tbold=\titalic=\talign=\tspaceBefore=\t'
            'spaceAfter=7pt\tlineSpacing=1.15x\tfirstLineIndent=\tlistStyle=\t'
            'numId=\tnumLevel='
        )
    }
    plan = {
        "summary": "Add a matching section",
        "commands": [
            [
                "add",
                "/body",
                "--type",
                "paragraph",
                "--prop",
                "styleId=Heading1",
                "--prop",
                "text=AI Agents",
            ],
            [
                "add",
                "/body",
                "--type",
                "paragraph",
                "--prop",
                "text=AI agents help people.",
            ],
        ],
    }

    inherited = inherit_word_revision_formatting(plan, inspection)
    heading = inherited["commands"][0]
    body = inherited["commands"][1]

    assert "style=Heading1" not in heading
    assert "size=16pt" in heading
    assert "color=#1F3864" in heading
    assert "bold=True" in heading
    assert "spaceBefore=14pt" in heading
    assert "size=11pt" in body
    assert "color=#262626" in body
    assert "spaceAfter=7pt" in body
    assert "lineSpacing=1.15x" in body


def test_word_set_inherits_only_properties_missing_from_target_paragraph():
    inspection = {
        "formatting": (
            '/body/p[1]\t[Heading1]\t"Existing heading"\tstyleId=Heading1\t'
            'styleName=Heading1\tfont=\tsize=16pt\tcolor=#1F3864\tbold=True\t'
            'italic=\talign=\tspaceBefore=14pt\tspaceAfter=7pt\tlineSpacing=\t'
            'firstLineIndent=\tlistStyle=\tnumId=\tnumLevel=\n'
            '/body/p[2]\t[Heading1]\t"New heading"\tstyleId=Heading1\t'
            'styleName=Heading1\tfont=\tsize=\tcolor=\tbold=\titalic=\talign=\t'
            'spaceBefore=\tspaceAfter=\tlineSpacing=\tfirstLineIndent=\tlistStyle=\t'
            'numId=\tnumLevel='
        )
    }
    plan = {
        "summary": "Match the new heading design",
        "commands": [
            ["set", "/body/p[2]", "--prop", "color=#C00000"],
        ],
    }

    inherited = inherit_word_revision_formatting(plan, inspection)
    command = inherited["commands"][0]

    assert "color=#C00000" in command
    assert "color=#1F3864" not in command
    assert "size=16pt" in command
    assert "bold=True" in command
    assert "spaceBefore=14pt" in command
    assert "spaceAfter=7pt" in command


def test_revision_plan_rejects_clone_with_inline_properties():
    with pytest.raises(OfficeRevisionError, match="combines --from with --prop"):
        normalize_revision_plan(
            {
                "summary": "Clone and rewrite a heading",
                "commands": [
                    {
                        "verb": "add",
                        "arguments": [
                            "/body",
                            "--from",
                            "/body/p[1]",
                            "--prop",
                            "text=New heading",
                        ],
                    }
                ],
            }
        )


def test_excel_revision_inspection_exposes_chinese_worksheet_paths():
    inspection, aliases = canonicalize_excel_revision_inspection(
        {
            "outline": 'File: ledger.xlsx\n├── "社区台账" (2 rows × 2 cols)',
            "text": (
                "=== Sheet: 社区台账 ===\n"
                "  A1: [居民姓名] ← String\n"
                "  B1: [联系电话] ← String"
            ),
            "issues": '{"count":0,"issues":[]}',
        }
    )

    assert "Editable worksheet path: /社区台账" in inspection["text"]
    assert "[/社区台账/A1]" in inspection["text"]
    assert aliases["/Sheet1"] == "/社区台账"
    assert aliases["/工作表1"] == "/社区台账"
    assert aliases["/sheet[1]"] == "/社区台账"


def test_presentation_revision_paths_are_canonicalized_for_packaged_officecli():
    inspection, aliases = canonicalize_presentation_revision_inspection(
        {
            "outline": 'File: report.pptx | 1 slides',
            "text": '[/slide[1]]\n  [Text Box] "社区工作汇报" ← (default)',
            "elements": (
                '/slide[1]/shape[@id=100000]\t[title]\t"社区工作汇报"\n'
                '/slide[1]/picture[@id=100001]\t[picture]\t(empty)\n'
                '/slide[1]/shape[@id=100002]\t[textbox]\t"防汛安排"'
            ),
            "issues": '{"count":0,"issues":[]}',
        }
    )

    assert "@id=" not in inspection["elements"]
    assert "/slide[1]/shape[1]" in inspection["elements"]
    assert "/slide[1]/shape[2]" in inspection["elements"]
    assert "/slide[1]/picture[1]" in inspection["elements"]

    plan = canonicalize_revision_plan_paths(
        {
            "summary": "更新防汛安排",
            "commands": [
                [
                    "set",
                    "/slide[1]/shape[@id=100002]",
                    "--prop",
                    "text=完善社区防汛安排",
                ]
            ],
        },
        aliases,
    )
    assert plan["commands"][0][1] == "/slide[1]/shape[2]"


def test_revise_document_keeps_one_record_and_tracks_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a task list",
        office_format="docx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    revision_client = FakeOfficeCliClient()

    revised = revise_office_document(
        document_id=created.id,
        instruction="change Pending to Complete",
        client=revision_client,
        planner=lambda _prompt, _timeout: {
            "summary": "Changed task status to Complete",
            "commands": [
                {
                    "verb": "set",
                    "arguments": ["/", "--find", "Pending", "--replace", "Complete"],
                }
            ],
        },
    )

    assert revised.id == created.id
    assert revised.revision_count == 1
    assert revised.metadata["last_revision"]["summary"] == "Changed task status to Complete"
    assert revised.metadata["last_revision"]["validation"] == "no errors found"
    assert len(list_office_documents(limit=10)) == 1


def test_imported_document_revision_uses_an_ascii_officecli_working_path(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path / "home"))
    source = tmp_path / "upload.docx"
    _write_minimal_office_package(source, "word/document.xml")
    imported = import_office_document(
        source_path=source,
        office_format="docx",
        display_name="阳光社区工作计划.docx",
    )
    revision_client = FakeOfficeCliClient()

    revised = revise_office_document(
        document_id=imported.id,
        instruction="将标题改为正式公文风格",
        client=revision_client,
        planner=lambda _prompt, _timeout: {
            "summary": "Updated the title style",
            "commands": [
                {
                    "verb": "set",
                    "arguments": ["/body/p[1]", "--prop", "bold=true"],
                }
            ],
        },
    )

    assert revised.path == imported.path
    assert Path(revised.path).exists()
    officecli_paths = [command[1] for command in revision_client.commands if len(command) > 1]
    assert officecli_paths
    assert all(Path(path).name.isascii() for path in officecli_paths)


def test_imported_word_revision_translates_stable_paragraph_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path / "home"))
    source = tmp_path / "upload.docx"
    _write_minimal_office_package(source, "word/document.xml")
    imported = import_office_document(
        source_path=source,
        office_format="docx",
        display_name="玫瑰湾社区工作计划.docx",
    )

    class StableParagraphOfficeCliClient(FakeOfficeCliClient):
        def run(self, args, **kwargs):
            result = super().run(args, **kwargs)
            command = [str(arg) for arg in args]
            if len(command) > 2 and command[0] == "view" and command[2] == "annotated":
                result.stdout = (
                    '[/body/p[@paraId=0010006D]] 「标题」 ← Heading 1\n'
                    '[/body/p[@paraId=0010006E]] 「正文」 ← Normal'
                )
            return result

    revision_client = StableParagraphOfficeCliClient()

    def planner(prompt, _timeout):
        assert "@paraId=" not in prompt
        assert "/body/p[2]" in prompt
        return {
            "summary": "Updated the body paragraph",
            "commands": [
                {
                    "verb": "set",
                    "arguments": [
                        "/body/p[@paraId=0010006E]",
                        "--prop",
                        "bold=true",
                    ],
                }
            ],
        }

    revised = revise_office_document(
        document_id=imported.id,
        instruction="加粗正文",
        client=revision_client,
        planner=planner,
    )

    assert revised.revision_count == 1
    set_commands = [
        command for command in revision_client.commands if command[:1] == ["set"]
    ]
    assert set_commands
    assert set_commands[0][2] == "/body/p[2]"
    assert all("@paraId=" not in argument for argument in set_commands[0])


def test_imported_excel_revision_uses_chinese_worksheet_path(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path / "home"))
    source = tmp_path / "upload.xlsx"
    _write_minimal_office_package(source, "xl/workbook.xml")
    imported = import_office_document(
        source_path=source,
        office_format="xlsx",
        display_name="社区居民台账.xlsx",
    )

    class ChineseWorksheetOfficeCliClient(FakeOfficeCliClient):
        def run(self, args, **kwargs):
            result = super().run(args, **kwargs)
            command = [str(arg) for arg in args]
            if len(command) > 2 and command[0] == "view" and command[2] == "annotated":
                result.stdout = (
                    "=== Sheet: 社区台账 ===\n"
                    "  A1: [居民姓名] ← String\n"
                    "  B1: [联系电话] ← String"
                )
            return result

    revision_client = ChineseWorksheetOfficeCliClient()

    def planner(prompt, _timeout):
        assert "[/社区台账/A1]" in prompt
        assert "visible content in Chinese" in prompt
        return {
            "summary": "补充居民信息",
            "commands": [
                {
                    "verb": "set",
                    "arguments": [
                        "/Sheet1/A2",
                        "--prop",
                        "value=张三",
                    ],
                }
            ],
        }

    revised = revise_office_document(
        document_id=imported.id,
        instruction="在台账中补充一条中文居民信息",
        client=revision_client,
        planner=planner,
    )

    assert revised.revision_count == 1
    set_commands = [
        command for command in revision_client.commands if command[:1] == ["set"]
    ]
    assert set_commands[0][2] == "/社区台账/A2"
    assert "value=张三" in set_commands[0]


def test_imported_presentation_revision_translates_stable_shape_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path / "home"))
    source = tmp_path / "upload.pptx"
    _write_minimal_office_package(source, "ppt/presentation.xml")
    imported = import_office_document(
        source_path=source,
        office_format="pptx",
        display_name="社区工作汇报.pptx",
    )

    class StableShapeOfficeCliClient(FakeOfficeCliClient):
        def run(self, args, **kwargs):
            result = super().run(args, **kwargs)
            command = [str(arg) for arg in args]
            if command[:1] == ["query"]:
                result.stdout = (
                    '/slide[1]/shape[@id=100000]\t[title]\t"社区工作汇报"\n'
                    '/slide[1]/shape[@id=100002]\t[textbox]\t"防汛安排"\n'
                    "total: 2 of 2 elements / 1 slides"
                )
            return result

    revision_client = StableShapeOfficeCliClient()

    def planner(prompt, _timeout):
        assert "@id=" not in prompt
        assert "/slide[1]/shape[2]" in prompt
        assert "visible content in Chinese" in prompt
        return {
            "summary": "更新防汛安排",
            "commands": [
                {
                    "verb": "set",
                    "arguments": [
                        "/slide[1]/shape[@id=100002]",
                        "--prop",
                        "text=完善社区防汛安排",
                    ],
                }
            ],
        }

    revised = revise_office_document(
        document_id=imported.id,
        instruction="将第二个文本框改为更完整的中文防汛安排",
        client=revision_client,
        planner=planner,
    )

    assert revised.revision_count == 1
    set_commands = [
        command for command in revision_client.commands if command[:1] == ["set"]
    ]
    assert set_commands[0][2] == "/slide[1]/shape[2]"
    assert "text=完善社区防汛安排" in set_commands[0]


def test_revision_timeout_stops_without_retry_and_preserves_original(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a task list",
        office_format="docx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    original = Path(created.path).read_bytes()
    planner_calls = 0

    def timed_out_planner(_prompt, _timeout):
        nonlocal planner_calls
        planner_calls += 1
        raise TimeoutError("model request timed out")

    try:
        revise_office_document(
            document_id=created.id,
            instruction="extend the plan through November",
            timeout=7,
            client=FakeOfficeCliClient(),
            planner=timed_out_planner,
        )
    except OfficeServiceError as exc:
        assert str(exc) == "Reins revision planning timed out after 7 seconds."
    else:
        raise AssertionError("revision timeout was accepted")

    assert planner_calls == 1
    assert Path(created.path).read_bytes() == original
    assert list_office_documents(limit=10)[0].revision_count == 0


def test_reins_word_revision_uses_saved_structure_and_rebuilds_same_file(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a June to September safety plan",
        office_format="docx",
        language="en",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    reins_record = OfficeDocumentRecord(
        id=created.id,
        title=created.title,
        kind=created.kind,
        path=created.path,
        file_name=created.file_name,
        mime_type=created.mime_type,
        created_at=created.created_at,
        updated_at=created.updated_at,
        revision_count=created.revision_count,
        prompt=created.prompt,
        generator="reins",
        command_count=created.command_count,
        metadata=created.metadata,
    )
    revised_content = deepcopy(created.metadata["content"])
    revised_content["title"] = "June to November Safety Plan"
    revised_content["generator"] = "reins"
    generation_calls = []
    monkeypatch.setattr(office_service, "get_office_document", lambda _document_id: reins_record)
    monkeypatch.setattr(
        office_service,
        "generate_office_content",
        lambda **kwargs: (generation_calls.append(kwargs), revised_content)[1],
    )
    revision_client = FakeOfficeCliClient()

    revised = revise_office_document(
        document_id=created.id,
        instruction="translate this into chinese. i need chinse version",
        client=revision_client,
    )

    assert revised.id == created.id
    assert revised.path == created.path
    assert revised.title == "June to November Safety Plan"
    assert revised.revision_count == 1
    assert "Current structured document content" in generation_calls[0]["prompt"]
    assert generation_calls[0]["language"] == "zh"
    assert "skill_id" not in generation_calls[0]
    assert "original creation skill is provenance" in generation_calls[0]["prompt"]
    assert revised.metadata["language"] == "zh"
    assert not any("annotated" in command for command in revision_client.commands)
    assert any(command[:1] == ["create"] for command in revision_client.commands)


def test_generated_word_simple_revision_uses_compact_officecli_plan(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a community work plan",
        office_format="docx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    reins_record = OfficeDocumentRecord(
        id=created.id,
        title=created.title,
        kind=created.kind,
        path=created.path,
        file_name=created.file_name,
        mime_type=created.mime_type,
        created_at=created.created_at,
        updated_at=created.updated_at,
        revision_count=created.revision_count,
        prompt=created.prompt,
        generator="reins",
        command_count=created.command_count,
        metadata=created.metadata,
    )
    monkeypatch.setattr(
        office_service, "get_office_document", lambda _document_id: reins_record
    )
    monkeypatch.setattr(
        office_service,
        "generate_office_content",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("full regeneration was used")
        ),
    )
    revision_client = BatchOfficeCliClient()

    revised = revise_office_document(
        document_id=created.id,
        instruction="把第一段改成更详细的中文说明",
        client=revision_client,
        planner=lambda _prompt, _timeout: {
            "summary": "补充第一段说明",
            "commands": [
                {
                    "verb": "set",
                    "arguments": [
                        "/body/p[1]",
                        "--prop",
                        "text=更详细的社区工作说明",
                    ],
                }
            ],
        },
    )

    assert revised.revision_count == 1
    assert revised.metadata["content_stale"] is True
    assert revised.metadata["revision_mode"] == "officecli_patch"
    assert len(revision_client.batches) == 1
    assert revision_client.batches[0][0]["props"] == {
        "text": "更详细的社区工作说明"
    }
    assert any("annotated" in command for command in revision_client.commands)


def test_renderer_releases_officecli_resident_after_validation(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "windows-safe.docx"

    render_office_content(
        office_format="docx",
        content={"title": "Windows Safe", "body": ["Ready"]},
        output_path=output,
        client=client,
    )

    validate_index = next(
        index for index, command in enumerate(client.commands)
        if command[:1] == ["validate"]
    )
    assert client.run_options[validate_index]["env_overrides"] == {
        "OFFICECLI_NO_AUTO_RESIDENT": "1"
    }
    assert client.commands[-1] == ["close", str(output)]


def test_renderer_batches_office_mutations_when_client_supports_it(tmp_path):
    client = BatchOfficeCliClient()
    output = tmp_path / "batched.docx"

    render_office_content(
        office_format="docx",
        content={"title": "社区工作计划", "body": ["一、总体目标", "完成重点任务。"]},
        output_path=output,
        client=client,
    )

    assert output.exists()
    assert len(client.batches) == 1
    assert len(client.batches[0]) > 2
    assert not any(command[:1] in (["add"], ["set"]) for command in client.commands)
    create_options = client.run_options[0]
    assert create_options["env_overrides"] == {"OFFICECLI_NO_AUTO_RESIDENT": "1"}
    assert any(item["command"] == "add" for item in client.batches[0])


def test_windows_atomic_revision_retries_a_transient_sharing_lock(tmp_path, monkeypatch):
    temporary = tmp_path / ".revision.docx"
    source = tmp_path / "document.docx"
    temporary.write_bytes(b"revised")
    source.write_bytes(b"original")
    attempts = 0
    delays: list[float] = []

    def replace_with_transient_lock(from_path, to_path):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            error = PermissionError(13, "file is being used by another process")
            error.winerror = 32
            raise error
        Path(from_path).replace(to_path)

    monkeypatch.setattr(office_service, "_atomic_replace", replace_with_transient_lock)
    monkeypatch.setattr(office_service, "_is_windows_sharing_error", lambda _error: True)
    monkeypatch.setattr(office_service.time, "sleep", delays.append)

    office_service._replace_revised_file(temporary, source)

    assert attempts == 3
    assert delays == list(office_service._WINDOWS_REPLACE_RETRY_DELAYS[:2])
    assert source.read_bytes() == b"revised"


def test_reins_excel_revision_uses_saved_workbook_and_rebuilds_same_file(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a resident screening workbook",
        office_format="xlsx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    reins_record = OfficeDocumentRecord(
        id=created.id,
        title=created.title,
        kind=created.kind,
        path=created.path,
        file_name=created.file_name,
        mime_type=created.mime_type,
        created_at=created.created_at,
        updated_at=created.updated_at,
        revision_count=created.revision_count,
        prompt=created.prompt,
        generator="reins",
        command_count=created.command_count,
        metadata=created.metadata,
    )
    revised_content = deepcopy(created.metadata["content"])
    revised_content["sheets"][0]["rows"].append(["November", "Complete"])
    revised_content["generator"] = "reins"
    generation_calls = []
    monkeypatch.setattr(office_service, "get_office_document", lambda _document_id: reins_record)
    monkeypatch.setattr(
        office_service,
        "generate_office_content",
        lambda **kwargs: (generation_calls.append(kwargs), revised_content)[1],
    )
    revision_client = FakeOfficeCliClient()

    revised = revise_office_document(
        document_id=created.id,
        instruction="rebuild the entire workbook and extend it through November",
        client=revision_client,
    )

    assert revised.id == created.id
    assert revised.path == created.path
    assert revised.revision_count == 1
    assert revised.metadata["content"]["sheets"][0]["rows"][-1][0] == "November"
    assert "Current structured workbook content" in generation_calls[0]["prompt"]
    assert "skill_id" not in generation_calls[0]
    assert "original creation skill is provenance" in generation_calls[0]["prompt"]
    assert not any("annotated" in command for command in revision_client.commands)
    assert any(command[:1] == ["create"] for command in revision_client.commands)


def test_excel_renderer_leaves_long_wrapped_rows_available_for_auto_fit(tmp_path):
    client = FakeOfficeCliClient()
    output = tmp_path / "long-notes.xlsx"
    render_office_content(
        office_format="xlsx",
        content={
            "title": "Screening Notes",
            "design": {"row_density": "compact"},
            "sheets": [{
                "name": "筛选说明",
                "headers": ["项目", "说明"],
                "rows": [["范围", "这是一段需要自动换行并根据内容自动调整高度的较长筛选说明文字。"]],
            }],
        },
        output_path=output,
        client=client,
    )

    assert not any(
        command[:3] == ["set", str(output), "/筛选说明/row[4]"]
        and "height=18" in command
        for command in client.commands
    )


def test_ppt_revision_updates_structured_content_without_dom_inspection(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a launch presentation",
        office_format="pptx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    revised_content = deepcopy(created.metadata["content"])
    revised_content["slides"][1]["title"] = "A sharper launch narrative"
    revised_content["revision_summary"] = "Updated the launch narrative"
    revision_client = FakeOfficeCliClient()

    revised = revise_office_document(
        document_id=created.id,
        instruction="rewrite the entire presentation to make the launch narrative sharper",
        client=revision_client,
        planner=lambda prompt, _timeout: (
            revised_content
            if "Current presentation JSON" in prompt
            else (_ for _ in ()).throw(AssertionError("structured presentation prompt was not used"))
        ),
    )

    assert revised.revision_count == 1
    assert revised.metadata["content"]["slides"][1]["title"] == "A sharper launch narrative"
    assert revised.metadata["last_revision"]["summary"] == "Updated the launch narrative"
    assert not any("annotated" in command for command in revision_client.commands)
    assert any(command[:1] == ["create"] for command in revision_client.commands)
    assert Path(revised.path).exists()


def test_ppt_redesign_prompt_requires_a_new_ai_art_direction(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a launch presentation",
        office_format="pptx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )

    prompt = build_presentation_revision_prompt(
        record=created,
        instruction="redesign it with a new color palette and typography",
    )

    assert "MUST art-direct a visibly different result" in prompt
    assert "Change at least the primary, accent, and background colors" in prompt
    assert "Do not reuse the current theme" in prompt


def test_ppt_redesign_retries_when_reins_reuses_the_theme(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a launch presentation",
        office_format="pptx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )
    unchanged = deepcopy(created.metadata["content"])
    redesigned = deepcopy(unchanged)
    redesigned["design"].update(
        {
            "composition": "editorial",
            "motif": "frames",
            "primary": "123456",
            "accent": "C53030",
            "background": "F0FFF4",
            "heading_font": "Georgia",
            "body_font": "Arial",
        }
    )
    for slide in redesigned["slides"]:
        slide["variant"] = "editorial"
    responses = iter([unchanged, redesigned])
    prompts: list[str] = []

    revised = revise_office_document(
        document_id=created.id,
        instruction="give this a completely new design and color palette",
        client=FakeOfficeCliClient(),
        planner=lambda prompt, _timeout: (prompts.append(prompt), next(responses))[1],
    )

    assert len(prompts) == 2
    assert "Correction required" in prompts[1]
    assert revised.metadata["content"]["design"]["accent"] == "C53030"
    assert revised.metadata["content"]["design"]["composition"] == "editorial"


def test_preview_document_uses_officecli_html_renderer(tmp_path, monkeypatch):
    monkeypatch.setenv("REINS_HOME", str(tmp_path))
    created = create_office_document(
        prompt="create a task list",
        office_format="docx",
        use_reins=False,
        client=FakeOfficeCliClient(),
    )

    preview = preview_office_document(created.id, client=FakeOfficeCliClient())

    assert preview.read_text(encoding="utf-8") == "<html><body>Office preview</body></html>"
