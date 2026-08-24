from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reins.features.office.schemas import normalize_office_format


class OfficeWorkflowError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OfficeWorkflow:
    id: str
    office_format: str
    label_zh: str
    label_en: str
    description_zh: str
    description_en: str
    placeholder_zh: str
    placeholder_en: str
    instruction: str
    defaults: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "format": self.office_format,
            "label_zh": self.label_zh,
            "label_en": self.label_en,
            "description_zh": self.description_zh,
            "description_en": self.description_en,
            "placeholder_zh": self.placeholder_zh,
            "placeholder_en": self.placeholder_en,
            "defaults": dict(self.defaults),
        }


OFFICE_WORKFLOWS = (
    OfficeWorkflow(
        id="community-work-plan",
        office_format="docx",
        label_zh="社区工作计划",
        label_en="Community work plan",
        description_zh="生成年度、季度或月度工作计划，并附任务分解。",
        description_en="Create an annual, quarterly, or monthly plan with an actionable task breakdown.",
        placeholder_zh="例如：为阳光社区编写2026年第三季度工作计划，重点包括防汛和垃圾分类。",
        placeholder_en="Example: Create Sunshine Community's Q3 2026 plan, focused on flood control and waste sorting.",
        instruction="""
生成一份内容完整、可直接使用的正式社区工作计划。
必须包含以下结构：
1. 明确具体的标题；已知社区名称和计划周期时，必须写入标题。
2. 指导思想与总体目标。
3. 重点工作任务，并根据实际需求划分为党建引领、基层治理、民生服务、安全稳定、文明创建等板块。
4. 每项任务必须说明具体措施、责任人或责任部门、完成时限。
5. 保障措施与工作要求。
必须生成清晰的 Word 任务分解表，至少包括任务、具体措施、责任人或责任部门、完成时限、预期成果。语言正式、简洁、务实、可执行，并根据用户提供的社区名称、时间范围和重点领域灵活调整。不得编造私人姓名或精确统计数据。
""".strip(),
    ),
    OfficeWorkflow(
        id="community-work-summary",
        office_format="docx",
        label_zh="社区工作总结",
        label_en="Community work summary",
        description_zh="整理阶段成果、问题不足与下一步工作安排。",
        description_en="Summarize results, shortcomings, and the next phase of work.",
        placeholder_zh="例如：总结幸福社区2026年上半年工作，突出民生服务和安全治理。",
        placeholder_en="Example: Summarize Happiness Community's first half of 2026, emphasizing services and safety.",
        instruction="""
生成一份适合向上级汇报的正式社区工作总结。
必须包含以下结构：
1. 明确具体的标题。
2. 总体情况概述，包括主要指标和工作亮点；数据只能来自用户提供的内容，没有数据时使用明确的定性表述。
3. 主要工作成效，并根据实际需求划分为党建、治理、服务、安全、文明创建等板块。
4. 存在的主要问题与不足，表达客观、坦诚、有建设性。
5. 下一步工作打算，明确具体重点和行动措施。
成绩与问题应保持平衡，语言精炼、注重事实依据。不得编造数字；关键事实缺失时，只能使用克制、专业的占位内容，并将待补充信息写入 missing_fields。
""".strip(),
    ),
    OfficeWorkflow(
        id="community-action-plan",
        office_format="docx",
        label_zh="专项行动方案",
        label_en="Special action plan",
        description_zh="生成安全、创城、防汛等专项行动实施方案。",
        description_en="Build an implementation plan for safety, emergency, or community campaigns.",
        placeholder_zh="例如：制定社区汛期安全隐患排查专项行动方案，时间为6月至9月。",
        placeholder_en="Example: Plan a June-September flood-season safety inspection campaign.",
        instruction="""
生成一份正式、可操作性强的专项行动实施方案。
必须包含以下结构：
1. 指导思想与可衡量的工作目标。
2. 组织领导、工作专班和职责分工；不得编造私人姓名。
3. 重点任务与具体措施，按阶段以及责任岗位或责任部门进行划分。
4. 时间安排、进度节点和完成时限。
5. 保障措施、协调机制、报送要求和工作要求。
6. 适合时生成任务清单表，包括任务、措施、责任主体、时限和预期成果。
责任和时间必须明确，并根据用户给出的行动主题、风险、地点和周期进行定制。输出必须可以直接使用，不得只生成通用模板。
""".strip(),
    ),
    OfficeWorkflow(
        id="community-meeting-minutes",
        office_format="docx",
        label_zh="会议记录",
        label_en="Meeting minutes",
        description_zh="生成可归档的会议记录或会议纪要。",
        description_en="Produce archive-ready meeting records or minutes.",
        placeholder_zh="例如：整理8月社区两委联席会议纪要，议题包括防汛值班和停车治理。",
        placeholder_en="Example: Record the August committee meeting on flood duty and parking governance.",
        instruction="""
生成一份客观、完整、可直接归档的社区会议记录或会议纪要。
必须包含以下结构：
1. 会议名称、时间、地点、主持人、记录人、出席人员和列席人员。
2. 会议议题。
3. 按议题记录会议内容与讨论情况，区分主要意见和最终结论。
4. 形成的决议或决定事项，明确责任人或责任部门以及完成时限。
5. 散会时间。
记录必须保持事实中立，重点突出决议事项。不得编造人员姓名、日期或会议决定。仅在必要事实缺失时使用专业占位内容，并将待补充信息写入 missing_fields。
""".strip(),
    ),
    OfficeWorkflow(
        id="community-notice",
        office_format="docx",
        label_zh="公告与通知",
        label_en="Notice and announcement",
        description_zh="生成适合张贴或群发的通知、公告与倡议书。",
        description_en="Create notices, announcements, and resident initiative letters.",
        placeholder_zh="例如：发布8月28日小区停水通知，说明时间、影响范围和注意事项。",
        placeholder_en="Example: Announce an August 28 water outage with timing, affected area, and precautions.",
        instruction="""
生成一份可直接张贴或在居民群发布的正式通知、公告或倡议书。
必须包含以下结构：
1. 简洁、醒目的标题。
2. 与受众匹配的称呼，例如“广大居民朋友们：”。
3. 正文，包括事由、具体安排或要求、重要注意事项。
4. 发布单位和日期。
根据文种调整语气：通知应正式直接，公告应权威清晰，倡议书应亲切且具有号召力。时间、地点、适用对象、联系方式和安全事项等关键信息应便于快速浏览。不得编造用户未提供的业务细节。
""".strip(),
    ),
    OfficeWorkflow(
        id="community-excel-filter",
        office_format="xlsx",
        label_zh="数据筛选清洗",
        label_en="Filter and clean data",
        description_zh="按条件筛选居民或工作台账，并生成筛选说明。",
        description_en="Filter and clean resident or operational records with an audit-friendly summary.",
        placeholder_zh="例如：筛选独居老人台账，仅保留姓名、楼栋、联系电话和走访状态。可粘贴数据。",
        placeholder_en="Example: Filter elderly residents living alone; keep only name, building, phone, and visit status. Paste data here.",
        instruction="""
生成一份用于社区数据筛选和清洗的专业 Excel 工作簿。只输出可由 OfficeCLI 渲染的结构化工作簿内容，不得要求或使用 Python、pandas、插件或其他外部软件包。
工作簿必须满足以下要求：
1. 准确理解全部筛选条件，只保留用户提供数据中符合条件的记录。
2. 生成整洁的筛选结果页，仅保留工作必需字段，不得编造记录。
3. 增加筛选说明页，写明筛选条件、结果数量、数据来源说明，以及用户提供的处理日期。
4. 设置合适的列宽、数据格式、清晰的表头层级和便于浏览的重点高亮。
5. 尽量减少敏感个人信息，不保留与当前工作无关的字段。
如果用户没有提供源数据，应创建正确的数据结构，并明确列出需要补充的数据字段，不得虚构居民信息或筛选结果。
""".strip(),
        defaults={"sheet_layout": "table"},
    ),
    OfficeWorkflow(
        id="community-excel-summary",
        office_format="xlsx",
        label_zh="数据汇总分析",
        label_en="Summarize and analyze data",
        description_zh="分类汇总社区数据，生成指标、占比和完成率。",
        description_en="Aggregate community data into indicators, shares, and completion rates.",
        placeholder_zh="例如：按楼栋汇总人口、老年人和重点人群数量，并计算各楼栋占比。可粘贴数据。",
        placeholder_en="Example: Summarize population, elderly residents, and key groups by building and calculate shares. Paste data here.",
        instruction="""
生成一份专业、便于后续更新的 Excel 汇总分析工作簿。只输出可由 OfficeCLI 渲染的结构化工作簿内容，不得要求或使用 Python、pandas、插件或其他外部软件包。
工作簿必须满足以下要求：
1. 按用户指定的维度对源数据进行分类汇总。
2. 在数据结构允许时使用有效的 Excel 公式，例如 SUMIF、COUNTIF 或同类公式，确保结果可更新。
3. 仅根据用户提供的数据计算占比、完成率、合计和小计等关键指标。
4. 增加汇总说明页，并注明源数据工作表或数据来源说明。
5. 使用统一的表头样式、正确的数字与百分比格式、合适的列宽，并对有实际意义的异常情况设置条件高亮。
源数据与计算汇总应在逻辑上分开。不得编造数据或合计结果。源数据缺失时，应创建可用的数据录入结构，并说明必须补充的字段。
""".strip(),
        defaults={"sheet_layout": "dashboard"},
    ),
    OfficeWorkflow(
        id="community-ppt-report",
        office_format="pptx",
        label_zh="社区工作汇报",
        label_en="Community work report",
        description_zh="生成适合投影的季度、年度或专项工作汇报。",
        description_en="Create a projection-ready quarterly, annual, or special work report.",
        placeholder_zh="例如：制作阳光社区第三季度工作汇报，突出党建、治理、服务和安全成果。",
        placeholder_en="Example: Present Sunshine Community's Q3 results across party building, governance, services, and safety.",
        instruction="""
生成一份 8 至 12 页、适合正式投影汇报的社区工作汇报 PPT。
必须形成以下叙事结构：
1. 封面；已知时写明社区名称、汇报主题和时间范围。
2. 目录或汇报逻辑导览。
3. 总体情况和用户提供的核心数据。
4. 根据实际工作设置多个成果板块，通常包括党建、治理、民生服务和安全稳定。
5. 存在的问题与不足。
6. 具体的下一步工作计划。
7. 有力度的结束页。
除非用户指定其他方向，采用成熟的政务汇报视觉体系，并通常以政务蓝为主色。必须使用多种版式，建立清晰的数据层级，文字精炼、适合投影。只有用户提供有效数字时才能生成图表。成品中不得出现模板或生成过程说明。
""".strip(),
        defaults={"slide_count": 10, "style": "auto", "audience": "executive", "detail": "balanced"},
    ),
    OfficeWorkflow(
        id="community-ppt-party",
        office_format="pptx",
        label_zh="社区党建汇报",
        label_en="Community party-building report",
        description_zh="生成党建工作、主题党日与特色品牌汇报。",
        description_en="Present party-building work, themed activities, and signature programs.",
        placeholder_zh="例如：制作2026年度社区党建工作汇报，包含组织建设、主题党日和党建品牌。",
        placeholder_en="Example: Present 2026 party-building work, organization development, themed days, and signature programs.",
        instruction="""
生成一份庄重、政治性明确、突出实际成效的社区党建工作汇报 PPT。
必须形成以下叙事结构：
1. 正式封面。
2. 党建工作总体情况。
3. 组织建设与党员队伍情况。
4. 主题教育或主题党日活动开展情况。
5. 党建引领基层治理的具体案例。
6. 特色品牌与创新做法。
7. 下一步党建工作计划和结束页。
除非用户明确指定其他视觉方向，采用精致、庄重的红色主色调和克制的金色点缀。保持足够对比度、正式字体、多样化版式和精炼文案。只能使用用户提供的事实和成果，不得编造政治引语、数据或人员姓名。
""".strip(),
        defaults={"slide_count": 8, "style": "executive", "audience": "executive", "detail": "balanced"},
    ),
    OfficeWorkflow(
        id="community-ppt-activity",
        office_format="pptx",
        label_zh="社区活动展示",
        label_en="Community activity showcase",
        description_zh="展示文化节、志愿服务与居民活动成果。",
        description_en="Showcase festivals, volunteer service, and resident activities.",
        placeholder_zh="例如：展示社区邻里节活动，包含活动流程、精彩瞬间、参与反馈和成果。",
        placeholder_en="Example: Showcase a neighborhood festival with its flow, moments, feedback, and outcomes.",
        instruction="""
生成一份温暖、活泼、富有社区人情味的活动展示 PPT。
必须形成以下叙事结构：
1. 封面；已知时写明活动主题、时间和地点。
2. 活动背景与目的。
3. 活动流程与主要亮点。
4. 精彩瞬间；没有实际图片时，只能使用得体的图片位置说明。
5. 用户提供的参与数据和居民反馈。
6. 活动成效、社区价值和后续安排。
7. 致谢或结束页。
选择明快、亲切且包含多个色彩家族的配色，并建立清晰的视觉节奏。使用多样化版式和精炼文案，突出以居民为中心的社区温度。不得编造参与人数、居民引语或反馈内容。
""".strip(),
        defaults={"slide_count": 8, "style": "modern", "audience": "general", "detail": "balanced"},
    ),
)


_WORKFLOWS_BY_ID = {workflow.id: workflow for workflow in OFFICE_WORKFLOWS}


def get_office_workflow(
    workflow_id: str,
    *,
    office_format: str | None = None,
) -> OfficeWorkflow:
    clean_id = str(workflow_id or "").strip()
    workflow = _WORKFLOWS_BY_ID.get(clean_id)
    if workflow is None:
        raise OfficeWorkflowError(f"Unknown Reins Office workflow: {clean_id or '(empty)'}")
    if office_format and workflow.office_format != normalize_office_format(office_format):
        raise OfficeWorkflowError(
            f"Workflow {workflow.id} creates {workflow.office_format}, not "
            f"{normalize_office_format(office_format)}."
        )
    return workflow


def list_office_workflows(*, office_format: str | None = None) -> list[dict[str, Any]]:
    normalized = normalize_office_format(office_format) if office_format else None
    return [
        workflow.to_public_dict()
        for workflow in OFFICE_WORKFLOWS
        if normalized is None or workflow.office_format == normalized
    ]
