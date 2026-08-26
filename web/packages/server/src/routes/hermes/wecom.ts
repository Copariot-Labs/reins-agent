import Router from '@koa/router';

import {
  processWeComWorkOrder,
  processWeComWorkOrderReply,
} from '../../services/hermes/wecom';

import {
  getWeComSetupStatus,
  saveWeComSetup,
  startWeComBackgroundService,
  stopWeComBackgroundService,
} from '../../services/reins/wecom-setup';

export const wecomRoutes = new Router();

function statusFromErrorMessage(message: string): number {
  if (/unauthorized/i.test(message)) {
    return 401;
  }

  if (/required|invalid|malformed|missing/i.test(message)) {
    return 400;
  }

  if (/timeout/i.test(message)) {
    return 504;
  }

  return 500;
}

/*
 * Settings + actual background service status.
 */
wecomRoutes.get('/api/reins/wecom/setup', async (ctx) => {
  ctx.body = await getWeComSetupStatus();
});

/*
 * Save configuration and install/restart the ticket poller.
 */
wecomRoutes.post('/api/reins/wecom/setup', async (ctx) => {
  try {
    ctx.body = await saveWeComSetup(
      (ctx.request.body || {}) as Record<string, any>,
    );
  } catch (err: any) {
    const message = err?.message || 'WeCom setup failed';

    ctx.status = statusFromErrorMessage(message);

    ctx.body = {
      error: message,
    };
  }
});

/*
 * Start an already configured ticket poller.
 *
 * If it has never been installed, the service layer
 * installs it automatically.
 */
wecomRoutes.post('/api/reins/wecom/service/start', async (ctx) => {
  try {
    ctx.body = await startWeComBackgroundService();
  } catch (err: any) {
    const message =
      err?.message || 'Could not start the background ticket service';

    ctx.status = statusFromErrorMessage(message);

    ctx.body = {
      error: message,
    };
  }
});

/*
 * Stop ticket polling without deleting settings.
 */
wecomRoutes.post('/api/reins/wecom/service/stop', async (ctx) => {
  try {
    ctx.body = await stopWeComBackgroundService();
  } catch (err: any) {
    const message =
      err?.message || 'Could not stop the background ticket service';

    ctx.status = statusFromErrorMessage(message);

    ctx.body = {
      error: message,
    };
  }
});

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

  /*
   * Fail closed in production.
   *
   * Local development can run without the
   * ingest key.
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

async function workOrder(ctx: any) {
  if (!requireReinsWeComApiKey(ctx)) {
    return;
  }

  try {
    const body = ctx.request.body as Record<string, unknown> | undefined;

    ctx.body = await processWeComWorkOrder(body || {});
  } catch (err: any) {
    const message = err?.message || 'WeCom work order processing failed';

    ctx.status = statusFromErrorMessage(message);

    ctx.body = {
      error: message,
    };
  }
}

async function workOrderReply(ctx: any) {
  if (!requireReinsWeComApiKey(ctx)) {
    return;
  }

  try {
    const body = ctx.request.body as Record<string, unknown> | undefined;

    ctx.body = await processWeComWorkOrderReply(body || {});
  } catch (err: any) {
    const message = err?.message || 'WeCom work order reply processing failed';

    ctx.status = statusFromErrorMessage(message);

    ctx.body = {
      error: message,
    };
  }
}

/*
 * Reins does not handle resident-facing WeChat
 * Customer Service callbacks here.
 *
 * These endpoints receive Reins work-order payloads
 * and staff replies.
 */
for (const prefix of ['/api/reins/wecom']) {
  wecomRoutes.post(`${prefix}/work-orders`, workOrder);

  wecomRoutes.post(`${prefix}/work-order`, workOrder);

  wecomRoutes.post(`${prefix}/work-orders/replies`, workOrderReply);

  wecomRoutes.post(`${prefix}/work-order/reply`, workOrderReply);
}
