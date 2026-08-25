export type WorkTool =
  | 'general'
  | 'document'
  | 'spreadsheet'
  | 'slides'
  | 'finance'
  | 'work-orders'
  | 'research'
  | 'browser';

export interface WorkToolOption {
  id: Exclude<WorkTool, 'general'>;
  label: string;
  icon: Exclude<WorkTool, 'general'>;
}

export type OfficeWorkTool = 'document' | 'spreadsheet' | 'slides';
export type RoutedWorkTool = OfficeWorkTool | 'research' | 'browser';

export interface WorkSuggestion {
  id: string;
  label: string;
  prompt: string;
  description?: string;
  officeSkillId?: string;
}

export interface SuggestionSessionState {
  hasSession: boolean;
  title?: string;
  messageCount?: number;
  messageTotal?: number;
  loadedMessageCount?: number;
  visibleMessageCount: number;
  isLoadingMessages: boolean;
}

export function getWorkToolOptions(isChinese: boolean): WorkToolOption[] {
  return [
    {
      id: 'document',
      label: isChinese ? '文档' : 'Documents',
      icon: 'document',
    },
    {
      id: 'finance',
      label: isChinese ? '财务' : 'Finance',
      icon: 'finance',
    },
    {
      id: 'work-orders',
      label: isChinese ? '工单' : 'Work orders',
      icon: 'work-orders',
    },
    {
      id: 'research',
      label: isChinese ? '深度研究' : 'Deep research',
      icon: 'research',
    },
    { id: 'browser', label: isChinese ? '浏览器' : 'Browser', icon: 'browser' },
  ];
}

export function getOfficeFormatOptions(isChinese: boolean): WorkToolOption[] {
  return [
    {
      id: 'document',
      label: isChinese ? 'Word 文档' : 'Word documents',
      icon: 'document',
    },
    {
      id: 'spreadsheet',
      label: isChinese ? 'Excel 表格' : 'Excel spreadsheets',
      icon: 'spreadsheet',
    },
    {
      id: 'slides',
      label: isChinese ? 'PPT 演示' : 'PPT presentations',
      icon: 'slides',
    },
  ];
}

const ENGLISH_SUGGESTIONS: Record<
  Exclude<WorkTool, 'general'>,
  WorkSuggestion[]
> = {
  document: [
    {
      id: 'reins-agent-report',
      label: 'Reins Agent Report',
      prompt:
        'Create a polished Reins Agent operations report document covering completed work, monitoring results, blockers, outcomes, and next steps.',
    },
    {
      id: 'work-order-summary',
      label: 'Work Order Summary',
      prompt:
        'Create a professional Reins work order summary document with the owner, priority, status, timeline, results, and next actions.',
    },
    {
      id: 'monitoring-incident-report',
      label: 'Monitoring Incident Report',
      prompt:
        'Create a Reins monitoring incident report document with the impact, timeline, root cause, resolution, and prevention actions.',
    },
    {
      id: 'automation-sop',
      label: 'Automation SOP',
      prompt:
        'Create an automation SOP document for Reins covering triggers, steps, approvals, exceptions, monitoring, and escalation.',
    },
    {
      id: 'client-proposal',
      label: 'Client Proposal',
      prompt:
        'Create a client proposal document for Reins Agent explaining the goals, capabilities, implementation plan, timeline, and expected outcomes.',
    },
  ],
  spreadsheet: [
    {
      id: 'work-order-tracker',
      label: 'Work Order Tracker',
      prompt:
        'Create a Reins work order tracking spreadsheet with owner, priority, status, due date, progress, blockers, and next action columns.',
    },
    {
      id: 'agent-performance-dashboard',
      label: 'Agent Performance Dashboard',
      prompt:
        'Create a Reins Agent performance spreadsheet tracking task volume, completion rate, duration, failures, cost, and quality.',
    },
    {
      id: 'finance-monitor',
      label: 'Finance Monitor',
      prompt:
        'Create a Reins finance monitoring spreadsheet for income, expenses, budget variance, recurring costs, and monthly totals.',
    },
    {
      id: 'task-capacity-plan',
      label: 'Task Capacity Plan',
      prompt:
        'Create a Reins task capacity planning spreadsheet with assignees, availability, workload, deadlines, dependencies, and risk.',
    },
  ],
  slides: [
    {
      id: 'reins-agent-overview',
      label: 'Reins Agent Overview',
      prompt:
        'Create a polished presentation about Reins Agent, its core capabilities, office workflows, monitoring, profiles, and business value.',
    },
    {
      id: 'client-demo-deck',
      label: 'Client Demo Deck',
      prompt:
        'Create a Reins Agent client demo presentation with the problem, live workflow, key features, outcomes, and next steps.',
    },
    {
      id: 'operations-review',
      label: 'Operations Review',
      prompt:
        'Create a Reins operations review presentation covering completed work, monitoring results, incidents, lessons, and priorities.',
    },
    {
      id: 'automation-proposal',
      label: 'Automation Proposal',
      prompt:
        'Create an automation proposal presentation for Reins with the current workflow, opportunity, solution, rollout plan, risks, and ROI.',
    },
  ],
  finance: [
    {
      id: 'record-expense',
      label: 'Record an Expense',
      prompt:
        'Record an expense of [enter amount] yuan for [enter purpose] today. Ask me before recording if any required information is unclear.',
    },
    {
      id: 'record-income',
      label: 'Record Income',
      prompt:
        'Record income of [enter amount] yuan from [enter source] today. Ask me before recording if any required information is unclear.',
    },
    {
      id: 'monthly-finance-summary',
      label: 'Monthly Summary',
      prompt:
        'Summarize this month\'s income, expenses, net balance, and largest categories using my Reins Finance records.',
    },
    {
      id: 'largest-expenses',
      label: 'Largest Expenses',
      prompt:
        'List the 10 largest expenses this month from my Reins Finance records and summarize what drove the spending.',
    },
    {
      id: 'export-finance-ledger',
      label: 'Export Finance Excel',
      prompt:
        'Export the latest Reins Finance Excel ledger to my Reins Workspace and tell me the saved file path.',
    },
  ],
  'work-orders': [
    {
      id: 'monthly-work-order-summary',
      label: 'Monthly Summary',
      prompt:
        'Summarize this month\'s work orders by status, priority, category, and responsible department using the current Reins Work Orders data.',
    },
    {
      id: 'urgent-pending-work-orders',
      label: 'Urgent Pending Orders',
      prompt:
        'List all urgent pending work orders, including their work-order IDs, locations, responsible departments, and creation times.',
    },
    {
      id: 'recent-work-orders',
      label: 'Recent Work Orders',
      prompt:
        'Show the 10 most recent work orders with their IDs, status, priority, category, and responsible department.',
    },
    {
      id: 'update-work-order',
      label: 'Update a Work Order',
      prompt:
        'Update work order [enter work-order ID] with this handling result: [enter result]. Ask me for any missing information before changing the record.',
    },
    {
      id: 'export-work-order-ledger',
      label: 'Export Work Orders Excel',
      prompt:
        'Export the latest work-order Excel ledger to my Reins Workspace and tell me the saved file path.',
    },
    {
      id: 'work-order-report-document',
      label: 'Create Work Order Report',
      prompt:
        'Create a professional Word document reporting this month\'s real Reins work-order activity, including totals, status distribution, urgent cases, department workload, completed results, risks, and next actions.',
    },
  ],
  research: [
    {
      id: 'competitor-analysis',
      label: 'Competitor Analysis',
      prompt:
        'Research and compare Reins Agent with current AI agent workspace competitors, including capabilities, positioning, strengths, and gaps.',
    },
    {
      id: 'automation-opportunities',
      label: 'Automation Opportunities',
      prompt:
        'Research the highest-value business workflow automation opportunities that Reins Agent can support and rank them by impact and effort.',
    },
    {
      id: 'agent-benchmark',
      label: 'Agent Benchmark',
      prompt:
        'Research useful benchmarks for evaluating Reins Agent task quality, speed, reliability, cost, and human oversight.',
    },
    {
      id: 'workflow-risk-review',
      label: 'Workflow Risk Review',
      prompt:
        'Research the operational, security, and governance risks of deploying Reins Agent in business workflows and recommend controls.',
    },
  ],
  browser: [
    {
      id: 'review-current-website',
      label: 'Review Current Website',
      prompt:
        'Open and review the current Reins website, then identify usability, messaging, navigation, and conversion improvements.',
    },
    {
      id: 'competitor-examples',
      label: 'Collect Competitor Examples',
      prompt:
        'Browse leading AI agent products and collect examples of effective onboarding, task creation, office document, and monitoring experiences.',
    },
    {
      id: 'test-user-workflow',
      label: 'Test User Workflow',
      prompt:
        'Use the browser to test the main Reins Agent user workflow and report broken steps, confusing behavior, and recommended fixes.',
    },
    {
      id: 'gather-product-evidence',
      label: 'Gather Product Evidence',
      prompt:
        'Browse relevant sources and gather current evidence, examples, and links for a Reins Agent product decision.',
    },
  ],
};

const CHINESE_SUGGESTIONS: Record<
  Exclude<WorkTool, 'general'>,
  WorkSuggestion[]
> = {
  document: [
    {
      id: 'reins-agent-report',
      label: 'Reins Agent 运营报告',
      prompt:
        '创建一份精美的 Reins Agent 运营报告文档，包含已完成工作、监控结果、阻塞问题、成果和下一步计划。',
    },
    {
      id: 'work-order-summary',
      label: '工单摘要',
      prompt:
        '创建一份 Reins 工单摘要文档，包含负责人、优先级、状态、时间线、结果和下一步行动。',
    },
    {
      id: 'monitoring-incident-report',
      label: '监控事件报告',
      prompt:
        '创建一份 Reins 监控事件报告文档，包含影响、时间线、根本原因、解决方案和预防措施。',
    },
    {
      id: 'automation-sop',
      label: '自动化 SOP',
      prompt:
        '创建一份 Reins 自动化 SOP 文档，包含触发条件、执行步骤、审批、异常、监控和升级流程。',
    },
    {
      id: 'client-proposal',
      label: '客户方案',
      prompt:
        '创建一份 Reins Agent 客户方案文档，说明目标、能力、实施计划、时间表和预期成果。',
    },
  ],
  spreadsheet: [
    {
      id: 'work-order-tracker',
      label: '工单跟踪表',
      prompt:
        '创建一个 Reins 工单跟踪表格，包含负责人、优先级、状态、截止日期、进度、阻塞和下一步行动。',
    },
    {
      id: 'agent-performance-dashboard',
      label: 'Agent 绩效看板',
      prompt:
        '创建一个 Reins Agent 绩效表格，跟踪任务量、完成率、耗时、失败、成本和质量。',
    },
    {
      id: 'finance-monitor',
      label: '财务监控表',
      prompt:
        '创建一个 Reins 财务监控表格，包含收入、支出、预算差异、经常性成本和月度汇总。',
    },
    {
      id: 'task-capacity-plan',
      label: '任务容量计划',
      prompt:
        '创建一个 Reins 任务容量计划表格，包含执行人、可用时间、工作量、截止日期、依赖和风险。',
    },
  ],
  slides: [
    {
      id: 'reins-agent-overview',
      label: 'Reins Agent 概览',
      prompt:
        '创建一份精美的 Reins Agent 演示文稿，介绍核心能力、Office 工作流、监控、配置文件和业务价值。',
    },
    {
      id: 'client-demo-deck',
      label: '客户演示文稿',
      prompt:
        '创建一份 Reins Agent 客户演示文稿，包含问题、实际工作流、核心功能、成果和下一步。',
    },
    {
      id: 'operations-review',
      label: '运营复盘',
      prompt:
        '创建一份 Reins 运营复盘演示文稿，包含已完成工作、监控结果、事件、经验和优先事项。',
    },
    {
      id: 'automation-proposal',
      label: '自动化提案',
      prompt:
        '创建一份 Reins 自动化提案演示文稿，包含当前流程、机会、解决方案、上线计划、风险和投资回报。',
    },
  ],
  finance: [
    {
      id: 'record-expense',
      label: '记录支出',
      prompt: '记录一笔支出：金额【请输入金额】元，用途【请输入用途】，日期为今天。如有必要信息不明确，请先向我确认。',
    },
    {
      id: 'record-income',
      label: '记录收入',
      prompt: '记录一笔收入：金额【请输入金额】元，来源【请输入来源】，日期为今天。如有必要信息不明确，请先向我确认。',
    },
    {
      id: 'monthly-finance-summary',
      label: '本月财务汇总',
      prompt: '根据 Reins 财务记录，汇总本月收入、支出、净收支和主要收支分类。',
    },
    {
      id: 'largest-expenses',
      label: '本月大额支出',
      prompt: '从 Reins 财务记录中列出本月金额最高的 10 笔支出，并总结主要支出原因。',
    },
    {
      id: 'export-finance-ledger',
      label: '导出财务 Excel',
      prompt: '将最新的 Reins 财务 Excel 台账导出到 Reins Workspace，并告诉我保存路径。',
    },
  ],
  'work-orders': [
    {
      id: 'monthly-work-order-summary',
      label: '本月工单汇总',
      prompt: '使用当前 Reins 工单数据，按状态、优先级、分类和负责部门汇总本月工单。',
    },
    {
      id: 'urgent-pending-work-orders',
      label: '紧急待处理工单',
      prompt: '列出所有紧急且待处理的工单，包含工单编号、地点、负责部门和创建时间。',
    },
    {
      id: 'recent-work-orders',
      label: '最近工单',
      prompt: '查询最近 10 条工单，显示工单编号、状态、优先级、分类和负责部门。',
    },
    {
      id: 'update-work-order',
      label: '更新工单',
      prompt: '更新工单【请输入工单编号】，处理结果为【请输入处理结果】。信息不完整时，请先向我确认再修改。',
    },
    {
      id: 'export-work-order-ledger',
      label: '导出工单 Excel',
      prompt: '将最新的工单 Excel 台账导出到 Reins Workspace，并告诉我保存路径。',
    },
    {
      id: 'work-order-report-document',
      label: '生成工单报告',
      prompt: '根据真实的 Reins 工单数据，创建一份本月工单处理情况 Word 报告，包含总量、状态分布、紧急事项、部门工作量、完成结果、风险和下一步行动。',
    },
  ],
  research: [
    {
      id: 'competitor-analysis',
      label: '竞品分析',
      prompt:
        '深度研究并对比 Reins Agent 与当前 AI Agent 工作区竞品的能力、定位、优势和差距。',
    },
    {
      id: 'automation-opportunities',
      label: '自动化机会',
      prompt:
        '研究 Reins Agent 可支持的高价值业务流程自动化机会，并按影响和实施成本排序。',
    },
    {
      id: 'agent-benchmark',
      label: 'Agent 评测',
      prompt:
        '研究评估 Reins Agent 任务质量、速度、可靠性、成本和人工监督的有效基准。',
    },
    {
      id: 'workflow-risk-review',
      label: '工作流风险评估',
      prompt:
        '研究在业务流程中部署 Reins Agent 的运营、安全和治理风险，并提出控制措施。',
    },
  ],
  browser: [
    {
      id: 'review-current-website',
      label: '审查当前网站',
      prompt:
        '打开并审查当前 Reins 网站，找出可用性、信息表达、导航和转化方面的改进点。',
    },
    {
      id: 'competitor-examples',
      label: '收集竞品案例',
      prompt:
        '浏览领先的 AI Agent 产品，收集有效的新手引导、任务创建、Office 文档和监控体验案例。',
    },
    {
      id: 'test-user-workflow',
      label: '测试用户流程',
      prompt:
        '使用浏览器测试 Reins Agent 的主要用户流程，报告断裂步骤、混乱行为和修复建议。',
    },
    {
      id: 'gather-product-evidence',
      label: '收集产品证据',
      prompt: '浏览相关来源，为 Reins Agent 产品决策收集当前证据、案例和链接。',
    },
  ],
};

export function getWorkSuggestions(
  tool: WorkTool,
  isChinese: boolean,
): WorkSuggestion[] {
  if (tool === 'general') return [];
  return (isChinese ? CHINESE_SUGGESTIONS : ENGLISH_SUGGESTIONS)[tool];
}

export function routedWorkTool(tool: WorkTool): RoutedWorkTool | undefined {
  if (tool === 'finance' || tool === 'work-orders' || tool === 'general') return undefined;
  return tool;
}

export function shouldShowNewChatSuggestions(
  state: SuggestionSessionState,
): boolean {
  if (!state.hasSession) return true;

  const knownMessageCount = Math.max(
    state.messageCount || 0,
    state.messageTotal || 0,
    state.loadedMessageCount || 0,
    state.visibleMessageCount,
  );
  if (knownMessageCount > 0) return false;

  // Avoid flashing the strip while an existing titled conversation is still
  // loading. Once loading confirms that the chat is empty, suggestions stay
  // visible even if the session already has a title.
  if (state.isLoadingMessages && state.title?.trim()) return false;
  return true;
}
