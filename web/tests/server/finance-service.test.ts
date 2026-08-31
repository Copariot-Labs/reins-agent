import { describe, expect, it } from 'vitest'
import {
  createFinanceTransaction,
  FINANCE_DESCRIPTION_MAX_LENGTH,
} from '../../packages/server/src/services/hermes/finance'

describe('Finance transaction validation', () => {
  it('rejects descriptions longer than the UI limit', () => {
    expect(() => createFinanceTransaction({
      type: 'expense',
      amount: 20,
      currency: 'CNY',
      category: '餐饮',
      description: '字'.repeat(FINANCE_DESCRIPTION_MAX_LENGTH + 1),
      occurred_at: '2026-08-31',
    })).toThrow(`Description must be ${FINANCE_DESCRIPTION_MAX_LENGTH} characters or fewer.`)
  })
})
