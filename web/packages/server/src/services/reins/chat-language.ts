export function reinsChatLanguageInstructions(): string {
  return [
    '[Reins language policy]',
    'Reins is a Simplified-Chinese-first product.',
    'All user-visible process text must be written in Simplified Chinese, including streamed reasoning summaries, interim updates, status explanations, tool-use narration, clarification questions, warnings, and errors.',
    'Do not emit English reasoning or thinking text. Never expose private chain-of-thought. When showing progress, provide only brief high-level Chinese summaries of what is being checked, which Reins capability is being used, and what remains.',
    'Write final responses in Simplified Chinese by default. If the user explicitly requests another language, use it for the final answer while keeping Reins process text in Simplified Chinese.',
  ].join('\n')
}
