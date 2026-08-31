import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import zh from '../../packages/client/src/i18n/locales/zh'

describe('Finance description input', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'packages/client/src/views/hermes/FinanceView.vue'),
    'utf8',
  )

  it('shows and enforces the 500-character boundary', () => {
    expect(source).toContain('const DESCRIPTION_MAX_LENGTH = 500')
    expect(source).toContain(':maxlength="DESCRIPTION_MAX_LENGTH"')
    expect(source).toContain('show-count')
    expect(source).toContain("t('finance.form.descriptionTooLong'")
  })

  it('uses localized placeholders for every configurable form input', () => {
    for (const key of [
      'typePlaceholder',
      'amountPlaceholder',
      'currencyPlaceholder',
      'categoryPlaceholder',
      'paymentMethodPlaceholder',
      'descriptionPlaceholder',
      'counterpartyPlaceholder',
    ]) {
      expect(source).toContain(`t('finance.form.${key}')`)
      expect(zh.finance.form[key as keyof typeof zh.finance.form]).toBeTruthy()
    }
  })

  it('identifies required and optional fields before submission', () => {
    for (const field of ['type', 'amount', 'currency', 'date', 'category', 'description']) {
      expect(source).toContain(`<NFormItem required :label="t('finance.form.${field}')">`)
    }
    expect(source.match(/finance\.form\.optionalLabel/g)).toHaveLength(2)
    expect(source).toContain("t('finance.form.requiredHint')")
    expect(zh.finance.form.requiredHint).toContain('必填')
    expect(zh.finance.form.optionalLabel).toContain('可选')
  })
})
