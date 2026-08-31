import type { OfficeFormat } from '@/api/reins/office'

export interface OfficeFormatNavigationItem {
  value: OfficeFormat
  mark: 'W' | 'X' | 'P'
  tone: 'word' | 'excel' | 'ppt'
  labelZh: string
  labelEn: string
}

export const OFFICE_FORMAT_NAV_ITEMS: readonly OfficeFormatNavigationItem[] = [
  {
    value: 'docx',
    mark: 'W',
    tone: 'word',
    labelZh: 'Word 文档',
    labelEn: 'Word documents',
  },
  {
    value: 'xlsx',
    mark: 'X',
    tone: 'excel',
    labelZh: 'Excel 表格',
    labelEn: 'Excel workbooks',
  },
  {
    value: 'pptx',
    mark: 'P',
    tone: 'ppt',
    labelZh: 'PPT 演示',
    labelEn: 'PPT presentations',
  },
]

export function officeFormatFromQuery(value: unknown): OfficeFormat {
  const first = Array.isArray(value) ? value[0] : value
  const normalized = String(first || '')
  return OFFICE_FORMAT_NAV_ITEMS.some(item => item.value === normalized)
    ? normalized as OfficeFormat
    : 'docx'
}
