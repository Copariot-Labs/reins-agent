import { describe, expect, it } from 'vitest'
import {
  financeChatMessage,
  mayNeedFinanceChat,
  pendingFinanceClarificationText,
  reinsFinanceAgentInstructions,
  resolveFinanceChatText,
} from '../../packages/server/src/services/reins/finance-chat'

describe('Reins finance chat routing', () => {
  it('instructs the Reins brain to clarify before writing finance data', () => {
    const instructions = reinsFinanceAgentInstructions()

    expect(instructions).toContain('normal reasoning and tool progress')
    expect(instructions).toContain('ask one concise Chinese clarification question')
    expect(instructions).toContain('finance_record_transaction')
    expect(instructions).toContain('finance_export_excel')
    expect(instructions).toContain('use only the native finance_* tools')
    expect(instructions).toContain('Never use terminal commands')
    expect(instructions).toContain('temporarily unavailable')
  })

  it('recognizes Chinese transaction, summary, and Excel requests', () => {
    expect(mayNeedFinanceChat('记录一笔午餐支出30元')).toBe(true)
    expect(mayNeedFinanceChat('查看本月财务汇总')).toBe(true)
    expect(mayNeedFinanceChat('导出本月财务Excel')).toBe(true)
    expect(mayNeedFinanceChat('制作一个财务预算表格模板')).toBe(false)
    expect(mayNeedFinanceChat('财务是什么')).toBe(false)
    expect(mayNeedFinanceChat('帮我买一台电脑')).toBe(false)
    expect(mayNeedFinanceChat('本月花了多少钱')).toBe(true)
  })

  it('continues a pending transaction when the user replies with only an amount', () => {
    const messages = [{
      role: 'tool',
      tool_name: 'reins_finance',
      content: JSON.stringify({
        needs_clarification: true,
        pending_text: '帮我记录一笔午餐支出',
      }),
    }]

    expect(pendingFinanceClarificationText(messages)).toBe('帮我记录一笔午餐支出')
    expect(resolveFinanceChatText('28元', messages)).toBe('帮我记录一笔午餐支出 28元')
    expect(resolveFinanceChatText('取消', messages)).toBeNull()
  })

  it('keeps the original amount when the user clarifies the transaction type', () => {
    const messages = [{
      role: 'tool',
      tool_name: 'reins_finance',
      content: JSON.stringify({
        needs_clarification: true,
        pending_text: '帮我记账30元',
      }),
    }]

    expect(resolveFinanceChatText('支出', messages)).toBe('帮我记账30元 支出')
  })

  it('returns a clickable workspace workbook link', () => {
    const output = financeChatMessage({
      handled: true,
      ok: true,
      action: 'export_excel',
      raw_text: '导出本月财务Excel',
      message_zh: '财务 Excel 工作簿已生成。',
      file: {
        path: '/Users/mei/Documents/Reins Workspace/Generated/Finance/财务收支.xlsx',
        file_name: '财务收支.xlsx',
        kind: 'xlsx',
      },
    }, true)

    expect(output).toContain('打开财务 Excel 工作簿')
    expect(output).toContain('Reins Workspace/Generated/Finance/财务收支.xlsx')
  })
})
