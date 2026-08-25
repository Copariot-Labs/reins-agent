export function officeRevisionNeedsClarification(message: string): boolean {
  const text = String(message || '')
    .replace(/\[(?:Attached file|Attached image):[^\]]+\]/gi, '')
    .trim()
  if (!text) return true
  return /^(?:请|麻烦)?(?:帮我)?(?:修改|编辑|更新|调整|优化|改进)(?:一下)?(?:这个|那个|该)?(?:文档|文件|表格|工作簿|PPT|演示文稿)?[吧。！!\s]*$/i.test(text)
    || /^(?:(?:please|can you)\s+)?(?:help me\s+)?(?:edit|modify|revise|update|change|improve|fix)(?:\s+(?:this|that|the|my))?(?:\s+(?:file|document|docx|spreadsheet|workbook|presentation|deck|pptx))?(?:\s+please)?[.!?\s]*$/i.test(text)
    || /^(?:make|improve)\s+(?:it|this|that)\s+(?:better|nicer|good)[.!?\s]*$/i.test(text)
}
