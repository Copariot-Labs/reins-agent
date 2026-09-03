const HAN_TEXT = /[\u3400-\u9fff]/

export function visibleReinsReasoning(text: string, hasResponseContent = false): string {
  const normalized = String(text || '').trim()
  if (!normalized) return ''
  if (HAN_TEXT.test(normalized)) return normalized
  return hasResponseContent
    ? '已完成所需操作，正在检查并整理结果。'
    : '正在理解您的需求，并确定需要使用的 Reins 功能。'
}
