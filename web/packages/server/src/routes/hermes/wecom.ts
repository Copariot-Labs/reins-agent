import Router from '@koa/router';
import {
  processWeComWorkOrder,
  processWeComWorkOrderReply,
} from '../../services/hermes/wecom';

export const wecomRoutes = new Router();

function getBearerToken(ctx: any): string {
  const auth = String(ctx.headers.authorization || '').trim();

  if (!auth.toLowerCase().startsWith('bearer ')) {
    return '';
  }

  return auth.slice(7).trim();
}

function getApiKey(ctx: any): string {
  return String(
    ctx.headers['x-api-key'] || ctx.headers['x-reins-api-key'] || '',
  ).trim();
}

function requireReinsWeComApiKey(ctx: any): boolean {
  const expected = process.env.REINS_WECOM_INGEST_API_KEY?.trim();

  /**
   * Fail closed in production.
   * In local development, you can either set REINS_WECOM_INGEST_API_KEY
   * or explicitly allow unsecured local testing.
   */
  if (!expected) {
    if (process.env.NODE_ENV !== 'production') {
      return true;
    }

    ctx.status = 500;
    ctx.body = {
      error: 'REINS_WECOM_INGEST_API_KEY is not configured',
    };
    return false;
  }

  const bearerToken = getBearerToken(ctx);
  const headerApiKey = getApiKey(ctx);

  if (bearerToken === expected || headerApiKey === expected) {
    return true;
  }

  ctx.status = 401;
  ctx.body = {
    error: 'Unauthorized',
  };
  return false;
}

function statusFromErrorMessage(message: string): number {
  if (/unauthorized/i.test(message)) return 401;
  if (/required|invalid|malformed|missing/i.test(message)) return 400;
  if (/timeout/i.test(message)) return 504;
  return 500;
}

async function workOrder(ctx: any) {
  if (!requireReinsWeComApiKey(ctx)) return;

  try {
    const body = ctx.request.body as Record<string, unknown> | undefined;
    ctx.body = await processWeComWorkOrder(body || {});
  } catch (err: any) {
    const message = err?.message || 'WeCom work order processing failed';
    ctx.status = statusFromErrorMessage(message);
    ctx.body = { error: message };
  }
}

async function workOrderReply(ctx: any) {
  if (!requireReinsWeComApiKey(ctx)) return;

  try {
    const body = ctx.request.body as Record<string, unknown> | undefined;
    ctx.body = await processWeComWorkOrderReply(body || {});
  } catch (err: any) {
    const message = err?.message || 'WeCom work order reply processing failed';
    ctx.status = statusFromErrorMessage(message);
    ctx.body = { error: message };
  }
}

/**
 * New project-plan routes:
 *
 * Reins does not handle WeChat Customer Service callbacks.
 * Reins does not handle resident-facing chatbot messages here.
 *
 * VPS wechat_kf sends the documented WeCom ticket notification text.
 * Hermes WeCom gateway / reader posts either that raw message text or the
 * parsed payload into these endpoints.
 */
for (const prefix of ['/api/reins/wecom']) {
  wecomRoutes.post(`${prefix}/work-orders`, workOrder);
  wecomRoutes.post(`${prefix}/work-order`, workOrder);

  wecomRoutes.post(`${prefix}/work-orders/replies`, workOrderReply);
  wecomRoutes.post(`${prefix}/work-order/reply`, workOrderReply);
}
