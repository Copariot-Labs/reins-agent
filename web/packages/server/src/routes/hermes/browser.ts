import Router from '@koa/router'
import type { Context } from 'koa'
import { connectVisibleBrowser, disconnectVisibleBrowser, getVisibleBrowserStatus } from '../../services/hermes/browser-connection'
import { getActiveProfileName } from '../../services/hermes/hermes-profile'

export const browserRoutes = new Router()

function requestedProfile(ctx: Context): string {
  const body = ctx.request.body as { profile?: unknown } | undefined
  const bodyProfile = typeof body?.profile === 'string' ? body.profile.trim() : ''
  const queryProfile = typeof ctx.query.profile === 'string' ? ctx.query.profile.trim() : ''
  const headerProfile = typeof ctx.headers['x-hermes-profile'] === 'string'
    ? ctx.headers['x-hermes-profile'].trim()
    : ''
  return bodyProfile || queryProfile || headerProfile || getActiveProfileName() || 'default'
}

async function status(ctx: Context) {
  ctx.body = await getVisibleBrowserStatus(requestedProfile(ctx))
}

async function connect(ctx: Context) {
  ctx.body = await connectVisibleBrowser(requestedProfile(ctx))
}

async function disconnect(ctx: Context) {
  ctx.body = await disconnectVisibleBrowser(requestedProfile(ctx))
}

for (const prefix of ['/api/reins/browser', '/api/hermes/browser']) {
  browserRoutes.get(`${prefix}/status`, status)
  browserRoutes.post(`${prefix}/connect`, connect)
  browserRoutes.post(`${prefix}/disconnect`, disconnect)
}
