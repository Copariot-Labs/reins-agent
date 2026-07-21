import { describe, expect, it } from 'vitest'

import { parseWeComTicketText } from '../../packages/server/src/services/hermes/wecom'

const productionTicket = `待处理工单：待处理工单
· 工单号：t_89751e8754e44289
· 优先级：normal
· 来源：微信客服·工单补充
· 类别：community_sanitation

· 状态：待工作人员跟进
· 生成时间：2026-07-17 15:17:28 CST

客户描述
客户原话：我要报保洁：A栋楼道垃圾没人清理，需要保洁处理。位置：A栋3楼。

已核实信息
· 工单类别：公共区域清扫
· 微信客户：redacted-wechat-customer-reference
· 地点：A栋3楼
· 问题/现象：楼道垃圾无人清理

客服研判
居民报告A栋3楼楼道垃圾无人清理，需要保洁处理。

处理要求
请尽快联系或到场处理；处理后在企业微信同步结果。`

const emergencyTicket = `【新建工单】
工单编号：t_27f4f7b483174238
处理状态：待处理
优先级：紧急
问题类别：危急事件
消息来源：微信客服
生成时间：2026-07-17 17:00:06（北京时间）
【客户诉求】
客户原话：心脏不舒服，药吃完了，快帮忙
【已确认信息】
- 地点：6栋3单元502
- 问题/现象：心脏不舒服，药吃完了，需要帮助
- 涉及人员：1
- 当前危险：是
【客服判断】
居民心脏不舒服，药吃完了，需要紧急帮助。位置：6栋3单元502。
【处理要求】
请尽快联系或到场处理；完成后在本群同步结果。
【系统信息】
客户标识：redacted-wechat-customer-reference
【工单结束】`

const screenshotTicket = `【新建工单】
工单编号：t_3ab6a6d8f17648ad
处理状态：待处理
优先级：紧急
问题类别：危急事件
消息来源：微信居民消息
生成时间：2026-07-20 08:05:34（北京时间）
【居民诉求】
居民原话：居民反映6栋2单元602有人多次将电动车推进楼道充电，昨晚仍在充电，疑似飞线充电且通道有遮挡。
【已确认信息】
- 地点：6栋2单元602
- 问题/现象：有人多次将电动车推进楼道充电，疑似存在飞线充电，通道有一定遮挡。
- 联系方式：136886886886
【网格员研判】
居民反映6栋2单元602有人多次将电动车推进楼道充电，疑似存在飞线充电，通道有一定遮挡。
【处理要求】
请尽快联系或到场处理；完成后在本群同步结果。
【系统信息】
居民标识：wmvlKYcAAAcuk-t3-61mAc2tStCYuNKA
【工单结束】`

describe('WeCom production ticket parser', () => {
  it('ignores Reins staff notifications to prevent group loops', () => {
    expect(parseWeComTicketText(
      '【Reins工单通知】请物业跟进\n工单编号：t_loop_test\n标题：卫生间漏水',
    )).toEqual({})
  })

  it('parses the Chinese sectioned message before web validation', () => {
    expect(parseWeComTicketText(productionTicket)).toEqual({
      external_id: 't_89751e8754e44289',
      priority: 'normal',
      source_channel: '微信客服·工单补充',
      original_category: 'community_sanitation',
      category: '公共区域清扫',
      upstream_status: '待工作人员跟进',
      ticket_created_at: '2026-07-17 15:17:28 CST',
      description: '我要报保洁：A栋楼道垃圾没人清理，需要保洁处理。位置：A栋3楼。',
      resident_ref: 'redacted-wechat-customer-reference',
      location: 'A栋3楼',
      title: '楼道垃圾无人清理',
      customer_assessment: '居民报告A栋3楼楼道垃圾无人清理，需要保洁处理。',
      handling_requirements: '请尽快联系或到场处理；处理后在企业微信同步结果。',
    })
  })

  it('parses the bracketed emergency ticket format', () => {
    expect(parseWeComTicketText(emergencyTicket)).toEqual({
      external_id: 't_27f4f7b483174238',
      upstream_status: '待处理',
      priority: '紧急',
      category: '危急事件',
      source_channel: '微信客服',
      ticket_created_at: '2026-07-17 17:00:06（北京时间）',
      description: '心脏不舒服，药吃完了，快帮忙',
      location: '6栋3单元502',
      title: '心脏不舒服，药吃完了，需要帮助',
      people_involved: '1',
      current_danger: '是',
      customer_assessment: '居民心脏不舒服，药吃完了，需要紧急帮助。位置：6栋3单元502。',
      handling_requirements: '请尽快联系或到场处理；完成后在本群同步结果。',
      resident_ref: 'redacted-wechat-customer-reference',
    })
  })

  it('parses the resident and grid-worker labels used by the live group ticket', () => {
    expect(parseWeComTicketText(screenshotTicket)).toMatchObject({
      external_id: 't_3ab6a6d8f17648ad',
      description: expect.stringContaining('飞线充电'),
      customer_assessment: expect.stringContaining('电动车推进楼道充电'),
      resident_ref: 'wmvlKYcAAAcuk-t3-61mAc2tStCYuNKA',
      location: '6栋2单元602',
    })
  })
})
