import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  getWorkOrderSummaryMock,
  listWorkOrdersMock,
  parseWorkOrderQueryMock,
} = vi.hoisted(() => ({
  getWorkOrderSummaryMock: vi.fn(),
  listWorkOrdersMock: vi.fn(),
  parseWorkOrderQueryMock: vi.fn((query: Record<string, unknown>) => query),
}))

vi.mock('../../packages/server/src/services/hermes/work-orders', () => ({
  getWorkOrderSummary: getWorkOrderSummaryMock,
  listWorkOrders: listWorkOrdersMock,
  parseWorkOrderQuery: parseWorkOrderQueryMock,
}))

import {
  buildWorkOrderOfficePrompt,
  isNativeWorkOrderExportRequest,
  mayNeedWorkOrderChat,
  reinsWorkOrderAgentInstructions,
} from '../../packages/server/src/services/reins/work-order-chat'

describe('Reins Work Orders chat integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkOrderSummaryMock.mockReturnValue({
      database_exists: true,
      total: 1,
      pending: 1,
      processing: 0,
      urgent: 1,
      notification_failed: 0,
      completed: 0,
      last_updated: '2026-08-24 10:00:00',
    })
    listWorkOrdersMock.mockReturnValue({
      total: 1,
      records: [{
        id: 7,
        external_id: 't_community_007',
        created_at: '2026-08-24 09:00:00',
        updated_at: '2026-08-24 10:00:00',
        status: 'open',
        priority: 'high',
        category: '公共设施维修',
        assigned_role: 'property',
        assigned_role_label: '物业维修',
        assignees: ['物业值班员'],
        location: '3栋门口',
        title: '路灯故障',
        issue: '路灯不亮，联系电话 13800138000',
        customer_assessment: '',
        handling_requirements: '今日检查',
        resident_contact: '13800138000',
        notification_status: 'sent',
        notification_channel: 'wecom',
        notification_error: '',
        result: '',
        responder: '',
        source_channel: 'wecom',
        upstream_status: '',
        assignment_reason: '公共设施维修',
      }],
    })
  })

  it('recognizes Chinese work-order operations but ignores feature design discussion', () => {
    expect(mayNeedWorkOrderChat('请汇总本月所有待处理工单')).toBe(true)
    expect(mayNeedWorkOrderChat('查看工单 t_community_007 的详情')).toBe(true)
    expect(mayNeedWorkOrderChat('帮我设计工单页面')).toBe(false)
    expect(mayNeedWorkOrderChat('总结今天的工作')).toBe(false)
  })

  it('reserves native Excel exports for the Work Orders tool', () => {
    expect(isNativeWorkOrderExportRequest('导出全部工单Excel台账')).toBe(true)
    expect(isNativeWorkOrderExportRequest('Export pending work orders to Excel')).toBe(true)
    expect(isNativeWorkOrderExportRequest('创建一份工单汇总 Word 报告')).toBe(false)
  })

  it('requires native tools and asks for missing update information', () => {
    const instructions = reinsWorkOrderAgentInstructions()
    expect(instructions).toContain('wecom_work_order_report')
    expect(instructions).toContain('wecom_record_staff_reply')
    expect(instructions).toContain('先用简短中文向用户询问缺失信息')
    expect(instructions).toContain('不得使用终端')
    expect(instructions).not.toContain('Hermes')
  })

  it('adds real privacy-safe work-order data to Office report generation', () => {
    const prompt = buildWorkOrderOfficePrompt('创建一份工单汇总 Word 报告')

    expect(parseWorkOrderQueryMock).toHaveBeenCalledWith({ limit: 100 })
    expect(prompt).toContain('[Reins 工单报告真实数据]')
    expect(prompt).toContain('t_community_007')
    expect(prompt).toContain('[已隐藏联系方式]')
    expect(prompt).not.toContain('13800138000')
    expect(prompt).not.toContain('resident_contact')
    expect(prompt).toContain('不得虚构数量')
  })
})
