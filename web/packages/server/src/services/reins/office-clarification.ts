function normalizedOfficeRequest(message: string): string {
  return String(message || '')
    .replace(/\[(?:Attached file|Attached image):[^\]]+\]/gi, '')
    .trim()
}

export function officeCreationNeedsClarification(message: string): boolean {
  const text = normalizedOfficeRequest(message)
  if (!text) return true
  return /^(?:(?:请|麻烦)?(?:帮我)?(?:创建|制作|生成|写|做|准备|整理)(?:一份|一个)?(?:新的?)?)?(?:office\s*)?(?:文档|文件|word|docx|表格|excel|xlsx|ppt|pptx|演示文稿)(?:吧|一下)?[。！!\s]*$/i.test(text)
    || /^(?:(?:please|can you)\s+)?(?:create|make|generate|prepare|write)(?:\s+(?:a|an|the|new))?\s+(?:office\s+)?(?:file|document|docx?|spreadsheet|excel|xlsx|presentation|pptx?|deck)(?:\s+please)?[.!?\s]*$/i.test(text)
}

export function officeRevisionNeedsClarification(message: string): boolean {
  const text = normalizedOfficeRequest(message)
  if (!text) return true
  return /^(?:请|麻烦)?(?:帮我)?(?:修改|编辑|更新|调整|优化|改进)(?:一下)?(?:这个|那个|该)?(?:文档|文件|表格|工作簿|PPT|演示文稿)?[吧。！!\s]*$/i.test(text)
    || /^(?:(?:please|can you)\s+)?(?:help me\s+)?(?:edit|modify|revise|update|change|improve|fix)(?:\s+(?:this|that|the|my))?(?:\s+(?:file|document|docx|spreadsheet|workbook|presentation|deck|pptx))?(?:\s+please)?[.!?\s]*$/i.test(text)
    || /^(?:make|improve)\s+(?:it|this|that)\s+(?:better|nicer|good)[.!?\s]*$/i.test(text)
}
