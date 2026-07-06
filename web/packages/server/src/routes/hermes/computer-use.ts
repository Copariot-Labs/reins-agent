import Router from '@koa/router'
import type { Context } from 'koa'
import { getComputerUseDoctor, getComputerUseStatus } from '../../services/hermes/computer-use'
import { getActiveProfileName } from '../../services/hermes/hermes-profile'

export const computerUseRoutes = new Router()

function requestedProfile(ctx: Context): string {
  const queryProfile = typeof ctx.query.profile === 'string' ? ctx.query.profile.trim() : ''
  const headerProfile = typeof ctx.headers['x-hermes-profile'] === 'string'
    ? ctx.headers['x-hermes-profile'].trim()
    : ''
  return queryProfile || headerProfile || getActiveProfileName() || 'default'
}

async function status(ctx: Context) {
  ctx.body = await getComputerUseStatus(requestedProfile(ctx))
}

async function doctor(ctx: Context) {
  ctx.body = await getComputerUseDoctor(requestedProfile(ctx))
}

for (const prefix of ['/api/reins/computer-use', '/api/hermes/computer-use']) {
  computerUseRoutes.get(`${prefix}/status`, status)
  computerUseRoutes.get(`${prefix}/doctor`, doctor)
}
