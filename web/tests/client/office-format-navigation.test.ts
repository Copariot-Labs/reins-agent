import { describe, expect, it } from 'vitest'
import {
  OFFICE_FORMAT_NAV_ITEMS,
  officeFormatFromQuery,
} from '../../packages/client/src/shared/office-formats'

describe('Office format navigation', () => {
  it('defines Word, Excel, and PPT as the direct Office categories', () => {
    expect(OFFICE_FORMAT_NAV_ITEMS.map(item => ({
      value: item.value,
      mark: item.mark,
      label: item.labelZh,
    }))).toEqual([
      { value: 'docx', mark: 'W', label: 'Word 文档' },
      { value: 'xlsx', mark: 'X', label: 'Excel 表格' },
      { value: 'pptx', mark: 'P', label: 'PPT 演示' },
    ])
  })

  it('uses the route type as shared sidebar and page state', () => {
    expect(officeFormatFromQuery('docx')).toBe('docx')
    expect(officeFormatFromQuery(['xlsx'])).toBe('xlsx')
    expect(officeFormatFromQuery('pptx')).toBe('pptx')
    expect(officeFormatFromQuery('unknown')).toBe('docx')
  })
})
