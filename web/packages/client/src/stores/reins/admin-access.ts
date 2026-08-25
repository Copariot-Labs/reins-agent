import { defineStore } from 'pinia';

import { ref } from 'vue';

import {
  AdminAccessApiError,
  clearAdminToken,
  fetchAdminAccessStatus,
  getAdminToken,
  lockAdminAccess,
  setupAdminAccess,
  unlockAdminAccess,
} from '@/api/reins/admin-access';

export const useAdminAccessStore = defineStore('reins-admin-access', () => {
  const configured = ref(false);

  const unlocked = ref(false);

  const setupAllowed = ref(false);

  const initialized = ref(false);

  const checking = ref(false);

  const unlocking = ref(false);

  const modalOpen = ref(false);

  const error = ref('');

  const errorCode = ref('');

  const retryAfterSeconds = ref(0);

  /*
   * Route the administrator wanted
   * to open before being challenged.
   */
  const pendingRoute = ref<string | null>(null);

  let statusRequest: Promise<boolean> | null = null;

  function refreshStatus(): Promise<boolean> {
    if (statusRequest) {
      return statusRequest;
    }

    checking.value = true;

    statusRequest = (async () => {
      try {
        const status = await fetchAdminAccessStatus();

        configured.value = status.configured;

        unlocked.value = status.unlocked;

        setupAllowed.value = Boolean(status.setupAllowed);

        /*
         * A token can become invalid if the
         * backend was restarted.
         */
        if (!status.unlocked && getAdminToken()) {
          clearAdminToken();
        }

        return status.unlocked;
      } catch (err: any) {
        unlocked.value = false;

        setupAllowed.value = false;

        error.value = err?.message || '';

        clearAdminToken();

        return false;
      } finally {
        initialized.value = true;

        checking.value = false;

        statusRequest = null;
      }
    })();

    return statusRequest;
  }

  async function ensureUnlocked(): Promise<boolean> {
    /*
     * Always trust the backend when
     * restoring a saved session token.
     */
    if (unlocked.value) {
      return true;
    }

    /*
     * The route guard runs before App.vue mounts. Always load status here so
     * the first unlock dialog does not incorrectly look unconfigured.
     */
    return refreshStatus();
  }

  function requestUnlock(targetRoute?: string): void {
    if (targetRoute) {
      pendingRoute.value = targetRoute;
    }

    error.value = '';

    errorCode.value = '';

    retryAfterSeconds.value = 0;
    modalOpen.value = true;
  }

  function cancelUnlock(): void {
    modalOpen.value = false;

    pendingRoute.value = null;

    error.value = '';

    errorCode.value = '';

    retryAfterSeconds.value = 0;
  }

  async function unlock(password: string): Promise<boolean> {
    const clean = password;

    if (!clean) {
      error.value = 'Administrator password is required';

      errorCode.value = 'password_required';

      return false;
    }

    unlocking.value = true;

    error.value = '';

    errorCode.value = '';

    retryAfterSeconds.value = 0;

    try {
      const result = await unlockAdminAccess(clean);

      if (!result.ok || !result.token) {
        error.value = 'Invalid administrator password';

        return false;
      }

      configured.value = true;

      unlocked.value = true;

      setupAllowed.value = false;

      modalOpen.value = false;

      return true;
    } catch (err: any) {
      error.value = err?.message || 'Unable to unlock administrator access';

      errorCode.value =
        err instanceof AdminAccessApiError
          ? err.code
          : '';

      retryAfterSeconds.value =
        err instanceof AdminAccessApiError
          ? err.retryAfterSeconds
          : 0;

      unlocked.value = false;

      return false;
    } finally {
      unlocking.value = false;
    }
  }

  async function setup(password: string): Promise<boolean> {
    unlocking.value = true;
    error.value = '';
    errorCode.value = '';
    retryAfterSeconds.value = 0;

    try {
      const result = await setupAdminAccess(password);

      if (!result.ok || !result.token) {
        error.value = 'Unable to configure administrator access';
        errorCode.value = 'setup_failed';
        return false;
      }

      configured.value = true;
      unlocked.value = true;
      setupAllowed.value = false;
      modalOpen.value = false;
      return true;
    } catch (err: any) {
      error.value = err?.message || 'Unable to configure administrator access';
      errorCode.value =
        err instanceof AdminAccessApiError
          ? err.code
          : '';
      unlocked.value = false;
      return false;
    } finally {
      unlocking.value = false;
    }
  }

  async function lock(): Promise<void> {
    try {
      await lockAdminAccess();
    } catch {
      clearAdminToken();
    }

    unlocked.value = false;

    pendingRoute.value = null;

    modalOpen.value = false;

    error.value = '';

    errorCode.value = '';

    retryAfterSeconds.value = 0;
  }

  function takePendingRoute(): string | null {
    const route = pendingRoute.value;

    pendingRoute.value = null;

    return route;
  }

  return {
    configured,
    unlocked,
    setupAllowed,
    initialized,
    checking,
    unlocking,
    modalOpen,
    error,
    errorCode,
    retryAfterSeconds,
    pendingRoute,

    refreshStatus,
    ensureUnlocked,
    requestUnlock,
    cancelUnlock,
    unlock,
    setup,
    lock,
    takePendingRoute,
  };
});
