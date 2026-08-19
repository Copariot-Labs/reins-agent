import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('WeCom user-facing settings', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'packages/client/src/components/reins/WeComSettings.vue'),
    'utf8',
  )

  it('keeps operational defaults out of the normal-user form', () => {
    for (const field of [
      'poll_interval',
      'routing_mode',
      'statuses',
      'ticket_limit',
      'ticket_timeout',
      'routing_confidence',
      'routing_timeout',
      'export_dir',
    ]) {
      expect(source).not.toContain(`v-model:value="form.${field}"`)
    }
  })

  it('keeps administrator-provided connection and recipient fields editable', () => {
    for (const field of [
      'ticket_api_url',
      'ticket_api_token',
      'group_webhook',
      'reply_bot_name',
      'users_default',
      'users_property',
      'users_cleaning',
      'users_police',
      'users_hospital',
      'users_community',
      'users_human_review',
    ]) {
      expect(source).toContain(`form.${field}`)
    }
  })
})
