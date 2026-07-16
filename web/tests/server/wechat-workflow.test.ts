import { describe, expect, it } from 'vitest'
import {
  buildWeComWorkflow,
  mayNeedWeComWorkflow,
  weComWorkflowToolArgs,
  weComWorkflowToolResult,
} from '../../packages/server/src/services/hermes/wecom-workflow'

describe('WeCom workflow detection', () => {
  it('detects WeCom ticket/work-order requests', () => {
    expect(mayNeedWeComWorkflow('Handle a WeCom customer-service ticket')).toBe(true)
    expect(mayNeedWeComWorkflow('Record this Enterprise WeChat work order')).toBe(true)
    expect(mayNeedWeComWorkflow('企业微信收到工单后写入Excel并通知物业')).toBe(true)
  })

  it('does not treat generic WeCom feature discussion as a gateway task', () => {
    expect(buildWeComWorkflow('start work with WeCom section')).toBeNull()
    expect(buildWeComWorkflow('How should the WeCom integration be designed?')).toBeNull()
  })

  it('builds a structured tool payload with ticket intake guards', () => {
    const workflow = buildWeComWorkflow('When WeCom receives a ticket notification, save it and notify staff')
    expect(workflow).not.toBeNull()
    expect(workflow!.instructions.join('\n')).toContain('WeChat Customer Service / 微信客服 is handled by the VPS-side wechat_kf system')
    expect(workflow!.instructions.join('\n')).toContain('parse that text into JSON')
    const args = weComWorkflowToolArgs(workflow!, 'When WeCom receives a ticket notification, save it and notify staff')
    expect(args).toMatchObject({
      workflow: 'reins_wecom_work_order_intake',
      desktop_computer_use: false,
      resident_chat_handler: false,
      wechat_customer_service_callback: false,
    })
    expect(args.preferred_processor_commands).toEqual(expect.arrayContaining([
      expect.stringContaining('reins wecom work-order add --payload-json'),
      expect.stringContaining('reins wecom work-order add --message'),
      expect.stringContaining('reins wecom records export'),
    ]))
    expect(args.steps).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'receive_ticket_text' }),
      expect.objectContaining({ id: 'parse_ticket_text' }),
      expect.objectContaining({ id: 'record_idempotently' }),
    ]))

    const result = weComWorkflowToolResult({
      workflow: workflow!,
      status: 'completed',
      finalOutput: 'Ticket parsed, recorded, and staff notification prepared.',
    })
    expect(result).toContain('WeChat Customer Service callbacks, resident chat, FAQ, and LLM customer-service replies belong to the VPS wechat_kf system')
    expect(result).toContain('Ticket parsed, recorded, and staff notification prepared.')
  })
})
