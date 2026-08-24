from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from reins.features.office.editor import (
    OfficeRevisionError,
    build_presentation_revision_prompt,
    normalize_revision_plan,
)
from reins.features.office.content_writer import build_office_content_prompt, generate_office_content
from reins.features.office.chat import infer_office_format, should_handle_office_chat
from reins.features.office.renderer import render_office_content
from reins.features.office.schemas import (
    OfficeDocumentRecord,
    normalize_office_format,
    normalize_presentation_options,
)
from reins.features.office.service import (
    create_office_document,
    list_office_documents,
    preview_office_document,
    revise_office_document,
)
from reins.features.office.workflows import (
    OfficeWorkflowError,
    get_office_workflow,
    list_office_workflows,
)


class FakeOfficeCliClient:
    binary = "/fake/officecli"

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    @property
    def command_count(self) -> int:
        return len(self.commands)

    def run(self, args, **kwargs):
        del kwargs
        command = [str(arg) for arg in args]
        self.commands.append(command)
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


def test_office_format_aliases():
    assert normalize_office_format("word") == "docx"
    assert normalize_office_format("excel") == "xlsx"
    assert normalize_office_format("ppt") == "pptx"
    assert normalize_office_format("unknown") == "docx"


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
    assert 'When Language is "zh", use natural Simplified Chinese' in prompt


def test_main_chat_routes_document_requests_to_office():
    assert should_handle_office_chat("create a maintenance notice document")
    assert infer_office_format("create an Excel maintenance tracker") == "xlsx"
    assert infer_office_format("制作一个会议演示文稿") == "pptx"
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
    assert record.path.startswith(str((tmp_path / "office" / "documents").resolve()))
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
        instruction="make the launch narrative sharper",
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
