import Router from '@koa/router';

import {
  ADMIN_PASSWORD_MAX_LENGTH,
  ADMIN_PASSWORD_MIN_LENGTH,
  adminPasswordValidationError,
  configureDevelopmentAdminPassword,
  createAdminSession,
  getAdminAccessStatus,
  isAdminAccessAvailable,
  isAdminAccessConfigured,
  isAdminSetupAllowed,
  readAdminToken,
  revokeAdminSession,
} from '../../services/reins/admin-access';

export const adminAccessRoutes = new Router();

interface FailedAttemptState {
  failures: number;
  blockedUntil: number;
}

const failedAttempts = new Map<string, FailedAttemptState>();

const MAX_FAILURES = 5;

const BLOCK_TIME_MS = 30 * 1000;

function clientKey(ctx: any): string {
  return String(ctx.ip || ctx.request?.ip || 'local').trim() || 'local';
}

function ensureAvailable(ctx: any): boolean {
  if (isAdminAccessAvailable()) {
    return true;
  }

  /*
   * Do not expose this local desktop
   * feature on a regular production
   * web deployment.
   */
  ctx.status = 404;

  ctx.body = {
    error: 'Not found',
  };

  return false;
}

function getAttemptState(key: string): FailedAttemptState {
  const existing = failedAttempts.get(key);

  if (existing) {
    return existing;
  }

  const created = {
    failures: 0,
    blockedUntil: 0,
  };

  failedAttempts.set(key, created);

  return created;
}

function isBlocked(key: string): number {
  const state = getAttemptState(key);

  const now = Date.now();

  if (state.blockedUntil <= now) {
    if (state.blockedUntil !== 0) {
      state.failures = 0;
      state.blockedUntil = 0;
    }

    return 0;
  }

  return state.blockedUntil - now;
}

function recordFailure(key: string): void {
  const state = getAttemptState(key);

  state.failures += 1;

  if (state.failures >= MAX_FAILURES) {
    state.blockedUntil = Date.now() + BLOCK_TIME_MS;

    state.failures = 0;
  }
}

function clearFailures(key: string): void {
  failedAttempts.delete(key);
}

/*
 * Check whether administrator access
 * is configured and whether this current
 * admin session is unlocked.
 */
adminAccessRoutes.get('/api/reins/admin-access/status', async (ctx) => {
  if (!ensureAvailable(ctx)) {
    return;
  }

  const token = readAdminToken((name) => ctx.get(name));

  ctx.body = getAdminAccessStatus(token);
});

/*
 * Unlock administrator access.
 *
 * Password is used only for this request.
 * It is never written to disk or returned.
 */
adminAccessRoutes.post('/api/reins/admin-access/unlock', async (ctx) => {
  if (!ensureAvailable(ctx)) {
    return;
  }

  if (!isAdminAccessConfigured()) {
    ctx.status = 503;

    ctx.body = {
      error: 'Administrator access is not configured',
      code: 'not_configured',
    };

    return;
  }

  const key = clientKey(ctx);

  const remaining = isBlocked(key);

  if (remaining > 0) {
    ctx.status = 429;

    ctx.body = {
      error: 'Too many failed attempts. Try again shortly.',
      code: 'rate_limited',
      retry_after_seconds: Math.max(1, Math.ceil(remaining / 1000)),
    };

    return;
  }

  const body = ctx.request.body as
    | {
        password?: unknown;
      }
    | undefined;

  const password = typeof body?.password === 'string' ? body.password : '';

  if (!password) {
    ctx.status = 400;

    ctx.body = {
      error: 'Administrator password is required',
      code: 'password_required',
    };

    return;
  }

  const token = createAdminSession(password);

  if (!token) {
    recordFailure(key);

    ctx.status = 401;

    ctx.body = {
      error: 'Invalid administrator password',
      code: 'invalid_password',
    };

    return;
  }

  clearFailures(key);

  ctx.body = {
    ok: true,
    token,
  };
});

/*
 * The packaged Windows build is always preconfigured. This route exists only
 * for a local Tauri development build where no release password is bundled.
 */
adminAccessRoutes.post('/api/reins/admin-access/setup', async (ctx) => {
  if (!ensureAvailable(ctx)) {
    return;
  }

  if (!isAdminSetupAllowed()) {
    ctx.status = 403;
    ctx.body = {
      error: 'Administrator password setup is not available',
      code: 'setup_unavailable',
    };
    return;
  }

  const body = ctx.request.body as
    | {
        password?: unknown;
      }
    | undefined;
  const password = typeof body?.password === 'string' ? body.password : '';
  const validationError = adminPasswordValidationError(password);

  if (validationError) {
    ctx.status = 400;
    ctx.body = {
      error:
        validationError === 'too_short'
          ? `Administrator password must contain at least ${ADMIN_PASSWORD_MIN_LENGTH} characters`
          : `Administrator password must contain at most ${ADMIN_PASSWORD_MAX_LENGTH} characters`,
      code: `password_${validationError}`,
    };
    return;
  }

  const token = configureDevelopmentAdminPassword(password);

  if (!token) {
    ctx.status = 409;
    ctx.body = {
      error: 'Administrator password was already configured',
      code: 'already_configured',
    };
    return;
  }

  ctx.body = {
    ok: true,
    token,
  };
});

/*
 * Explicitly lock administrator access.
 */
adminAccessRoutes.post('/api/reins/admin-access/lock', async (ctx) => {
  if (!ensureAvailable(ctx)) {
    return;
  }

  const token = readAdminToken((name) => ctx.get(name));

  revokeAdminSession(token);

  ctx.body = {
    ok: true,
  };
});
