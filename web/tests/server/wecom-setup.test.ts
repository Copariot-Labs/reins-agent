import { mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getWeComSetupStatus,
  saveWeComSetup,
} from '../../packages/server/src/services/reins/wecom-setup'

const originalReinsHome = process.env.REINS_HOME
const originalNotificationEnabled = process.env.REINS_WECOM_NOTIFY_ENABLED
const originalTicketApiToken = process.env.REINS_TICKET_API_TOKEN
const temporaryHomes: string[] = []

afterEach(async () => {
  if (originalReinsHome === undefined) delete process.env.REINS_HOME
  else process.env.REINS_HOME = originalReinsHome
  if (originalNotificationEnabled === undefined) delete process.env.REINS_WECOM_NOTIFY_ENABLED
  else process.env.REINS_WECOM_NOTIFY_ENABLED = originalNotificationEnabled
  if (originalTicketApiToken === undefined) delete process.env.REINS_TICKET_API_TOKEN
  else process.env.REINS_TICKET_API_TOKEN = originalTicketApiToken
  await Promise.all(temporaryHomes.splice(0).map(path => rm(path, { recursive: true, force: true })))
})

describe('WeCom settings setup', () => {
  it('reports configuration without returning secrets to the browser', async () => {
    const home = await mkdtemp(join(tmpdir(), 'reins-wecom-setup-'))
    temporaryHomes.push(home)
    process.env.REINS_HOME = home
    await writeFile(join(home, '.env'), [
      'REINS_TICKET_API_URL=https://tickets.example.test/internal/tickets',
      'REINS_TICKET_API_TOKEN=private-ticket-token',
      'REINS_WECOM_NOTIFY_GROUP_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=private-key',
      'REINS_WECOM_NOTIFY_USERS_DEFAULT=community-manager',
      'REINS_WECOM_REPLY_BOT_NAME=Reins Assistant',
      'REINS_TICKET_API_LIMIT=35',
      'REINS_TICKET_API_TIMEOUT=22',
      'REINS_WECOM_ROUTING_TIMEOUT=18',
      'REINS_WECOM_EXPORT_DIR=C:\\Users\\Tester\\Documents\\Reins',
      '',
    ].join('\n'), 'utf8')

    const status = await getWeComSetupStatus()
    const serialized = JSON.stringify(status)

    expect(status.configured).toBe(true)
    expect(status.ticket_api_token_configured).toBe(true)
    expect(status.group_webhook_configured).toBe(true)
    expect(status.values).toMatchObject({
      ticket_api_url: 'https://tickets.example.test/internal/tickets',
      users_default: 'community-manager',
      reply_bot_name: 'Reins Assistant',
      ticket_limit: '35',
      ticket_timeout: '22',
      routing_timeout: '18',
      export_dir: 'C:\\Users\\Tester\\Documents\\Reins',
    })
    expect(serialized).not.toContain('private-ticket-token')
    expect(serialized).not.toContain('private-key')
  })

  it('keeps webhook optional unless notification sending is explicitly enabled', async () => {
    const home = await mkdtemp(join(tmpdir(), 'reins-wecom-fetch-only-'))
    temporaryHomes.push(home)
    process.env.REINS_HOME = home
    process.env.REINS_WECOM_NOTIFY_ENABLED = 'true'
    await writeFile(join(home, '.env'), [
      'REINS_TICKET_API_URL=https://tickets.example.test/internal/tickets',
      'REINS_TICKET_API_TOKEN=private-ticket-token',
      'REINS_WECOM_NOTIFY_ENABLED=true',
      '',
    ].join('\n'), 'utf8')

    const bootstrap = vi.fn(async () => ({
      wecom: {
        configured: true,
        background: { ok: true, running: true },
      },
    }))
    const status = await saveWeComSetup({
      ticket_api_url: 'https://tickets.example.test/internal/tickets',
      ticket_api_token: '',
    }, bootstrap)

    expect(bootstrap).toHaveBeenCalledOnce()
    expect(status.configured).toBe(true)
    expect(status.values).toMatchObject({ notifications_enabled: false })
    expect(process.env.REINS_WECOM_NOTIFY_ENABLED).toBe('false')
    const saved = await readFile(join(home, '.env'), 'utf8')
    expect(saved).toContain('REINS_WECOM_NOTIFY_ENABLED=false')
    expect(saved).not.toContain('REINS_WECOM_NOTIFY_GROUP_WEBHOOK')
  })
})
