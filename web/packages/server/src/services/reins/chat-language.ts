export function reinsChatLanguageInstructions(): string {
  return [
    '[Reins language policy]',
    '强制语言规则：Reins 是以简体中文为主的产品。所有用户可见的处理过程必须使用简体中文，包括思考摘要、中间进度、工具调用说明、澄清问题、警告和错误。不得向用户显示英文思考内容。',
    'Reins is a Simplified-Chinese-first product.',
    'All user-visible process text must be written in Simplified Chinese, including streamed reasoning summaries, interim updates, status explanations, tool-use narration, clarification questions, warnings, and errors.',
    'Do not emit English reasoning or thinking text. Never expose private chain-of-thought. When showing progress, provide only brief high-level Chinese summaries of what is being checked, which Reins capability is being used, and what remains.',
    'Write final responses in Simplified Chinese by default. If the user explicitly requests another language, use it for the final answer while keeping Reins process text in Simplified Chinese.',
  ].join('\n')
}

export function reinsReasoningProgressSummary(hasUsedTool = false): string {
  return hasUsedTool
    ? '已完成所需操作，正在检查并整理结果。'
    : '正在理解您的需求，并确定需要使用的 Reins 功能。'
}
