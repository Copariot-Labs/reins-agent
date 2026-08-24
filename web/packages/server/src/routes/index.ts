import type { Context, Next } from 'koa';

// Shared route modules
import { healthRoutes } from './health';
import { webhookRoutes } from './webhook';
import { uploadRoutes } from './upload';
import { updateRoutes } from './update';
import { authPublicRoutes, authProtectedRoutes } from './auth';

// Reins local administrator access
import { adminAccessRoutes } from './reins/admin-access';

// Hermes route modules
import { sessionRoutes } from './hermes/sessions';
import { profileRoutes } from './hermes/profiles';
import { skillRoutes } from './hermes/skills';
import { pluginRoutes } from './hermes/plugins';
import { memoryRoutes } from './hermes/memory';
import { modelRoutes } from './hermes/models';
import { providerRoutes } from './hermes/providers';
import { configRoutes } from './hermes/config';
import { logRoutes } from './hermes/logs';
import { codexAuthRoutes } from './hermes/codex-auth';
import { nousAuthRoutes } from './hermes/nous-auth';
import { copilotAuthRoutes } from './hermes/copilot-auth';
import { xaiAuthRoutes } from './hermes/xai-auth';
import { weixinRoutes } from './hermes/weixin';
import { fileRoutes } from './hermes/files';
import { downloadRoutes } from './hermes/download';
import { jobRoutes } from './hermes/jobs';
import { cronHistoryRoutes } from './hermes/cron-history';
import { kanbanRoutes } from './hermes/kanban';
import { ttsRoutes } from './hermes/tts';
import { mediaRoutes } from './hermes/media';
import { proxyRoutes, proxyMiddleware } from './hermes/proxy';
import { groupChatRoutes, setGroupChatServer } from './hermes/group-chat';
import { performanceMonitorRoutes } from './hermes/performance-monitor';
import { financeRoutes } from './hermes/finance';
import { browserRoutes } from './hermes/browser';
import { computerUseRoutes } from './hermes/computer-use';
import { wecomRoutes } from './hermes/wecom';
import { workOrderRoutes } from './hermes/work-orders';
import { officeRoutes } from './reins/office';

/**
 * Register all routes on the Koa app.
 *
 * Route order is important:
 *
 * 1. Public application routes
 * 2. Local Reins administrator-access routes
 * 3. Existing public authentication routes
 * 4. Existing authentication middleware
 * 5. Existing protected application routes
 * 6. Proxy routes / proxy catch-all
 *
 * Administrator access is intentionally registered BEFORE
 * the existing user authentication middleware.
 *
 * This allows the Reins desktop application to unlock
 * administrator-only areas without requiring a normal
 * user login.
 */
export function registerRoutes(
  app: any,
  authMiddleware: Array<(ctx: Context, next: Next) => Promise<void>>,
) {
  // ---------------------------------------------------------
  // Public routes
  // ---------------------------------------------------------

  app.use(healthRoutes.routes());

  app.use(webhookRoutes.routes());

  // ---------------------------------------------------------
  // Reins local administrator access
  // ---------------------------------------------------------
  //
  // IMPORTANT:
  //
  // These routes MUST remain above authMiddleware.
  //
  // Otherwise:
  //
  // GET /api/reins/admin-access/status
  //
  // would be intercepted by the normal user JWT middleware
  // and return:
  //
  // { "error": "Unauthorized" }
  //
  // Normal Reins desktop users do not need an account/login.
  // Administrator access is a separate local password system.
  // ---------------------------------------------------------

  app.use(adminAccessRoutes.routes());

  // ---------------------------------------------------------
  // Existing public authentication routes
  // ---------------------------------------------------------
  //
  // Keep these for now.
  //
  // In the next stage we will change the desktop frontend so
  // normal Reins users do not see or require the login flow.
  // ---------------------------------------------------------

  app.use(authPublicRoutes.routes());

  // ---------------------------------------------------------
  // Existing authentication middleware
  // ---------------------------------------------------------
  //
  // Everything registered below here currently requires
  // the existing application authentication.
  //
  // We will adjust the desktop behavior separately.
  // ---------------------------------------------------------

  authMiddleware.forEach((middleware) => {
    app.use(middleware);
  });

  // ---------------------------------------------------------
  // Existing protected routes
  // ---------------------------------------------------------

  app.use(authProtectedRoutes.routes());

  app.use(ttsRoutes.routes());

  app.use(uploadRoutes.routes());

  // Must be before proxy because proxy catch-all
  // can match everything.
  app.use(updateRoutes.routes());

  app.use(sessionRoutes.routes());

  app.use(profileRoutes.routes());

  app.use(skillRoutes.routes());

  app.use(pluginRoutes.routes());

  app.use(memoryRoutes.routes());

  app.use(modelRoutes.routes());

  app.use(providerRoutes.routes());

  app.use(configRoutes.routes());

  app.use(logRoutes.routes());

  app.use(codexAuthRoutes.routes());

  app.use(nousAuthRoutes.routes());

  app.use(copilotAuthRoutes.routes());

  app.use(xaiAuthRoutes.routes());

  app.use(weixinRoutes.routes());

  // Must be before proxy.
  app.use(groupChatRoutes.routes());

  // Must be before proxy.
  app.use(fileRoutes.routes());

  // Must be before proxy.
  app.use(downloadRoutes.routes());

  // Must be before proxy.
  app.use(jobRoutes.routes());

  // Must be before proxy.
  app.use(cronHistoryRoutes.routes());

  // Must be before proxy.
  app.use(kanbanRoutes.routes());

  // Must be before proxy.
  app.use(mediaRoutes.routes());

  // Must be before proxy.
  app.use(performanceMonitorRoutes.routes());

  // Must be before proxy.
  app.use(financeRoutes.routes());

  // Must be before proxy.
  app.use(browserRoutes.routes());

  // Must be before proxy.
  app.use(computerUseRoutes.routes());

  // Must be before proxy.
  app.use(wecomRoutes.routes());

  // Must be before proxy.
  app.use(workOrderRoutes.routes());

  // Must be before proxy.
  app.use(officeRoutes.routes());

  // ---------------------------------------------------------
  // Proxy routes
  // ---------------------------------------------------------

  app.use(proxyRoutes.routes());

  // Proxy catch-all middleware must always be last.
  return proxyMiddleware;
}
