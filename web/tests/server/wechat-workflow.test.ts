import { describe, expect, it } from 'vitest'
import {
  buildWeChatWorkflow,
  mayNeedWeChatWorkflow,
  weChatWorkflowToolArgs,
  weChatWorkflowToolResult,
} from '../../packages/server/src/services/hermes/wechat-workflow'

describe('WeChat workflow detection', () => {
  it('detects desktop WeChat message requests', () => {
    expect(mayNeedWeChatWorkflow('Send a WeChat message to Alice saying the report is ready')).toBe(true)
    expect(mayNeedWeChatWorkflow('wechat Alice report is ready')).toBe(true)
    expect(mayNeedWeChatWorkflow('微信发给张三：报告已经好了')).toBe(true)
  })

  it('does not treat generic WeChat feature discussion as a desktop task', () => {
    expect(buildWeChatWorkflow('start work with WeChat section')).toBeNull()
    expect(buildWeChatWorkflow('How should the WeChat integration be designed?')).toBeNull()
  })

  it('builds a structured tool payload with a send confirmation guard', () => {
    const workflow = buildWeChatWorkflow('Find latest info about X and send it to Alice on WeChat')
    expect(workflow).not.toBeNull()
    expect(workflow!.instructions.join('\n')).toContain('Use the deterministic Reins WeChat skill/CLI')
    const args = weChatWorkflowToolArgs(workflow!, 'Find latest info about X and send it to Alice on WeChat')
    expect(args).toMatchObject({
      workflow: 'wechat_desktop_message',
      confirmation_required_before_send: true,
    })
    expect(args.preferred_skill_commands).toEqual(expect.arrayContaining([
      expect.stringContaining('reins wechat draft'),
      expect.stringContaining('reins wechat send-current --confirm'),
    ]))
    expect(args.steps).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'gather_info' }),
      expect.objectContaining({ id: 'confirm_send' }),
    ]))

    const result = weChatWorkflowToolResult({
      workflow: workflow!,
      status: 'completed',
      finalOutput: 'Drafted message and asked for confirmation.',
    })
    expect(result).toContain('No WeChat message or file should be sent until the user confirms')
    expect(result).toContain('Drafted message and asked for confirmation.')
  })
})
