import { defineStore } from 'pinia';

import { ref } from 'vue';

import {
  clearAdminToken,
  fetchAdminAccessStatus,
  getAdminToken,
  lockAdminAccess,
  unlockAdminAccess,
} from '@/api/reins/admin-access';

export const useAdminAccessStore = defineStore('reins-admin-access', () => {
  const configured = ref(false);

  const unlocked = ref(false);

  const checking = ref(false);

  const unlocking = ref(false);

  const modalOpen = ref(false);

  const error = ref('');

  /*
   * Route the administrator wanted
   * to open before being challenged.
   */
  const pendingRoute = ref<string | null>(null);

  async function refreshStatus(): Promise<boolean> {
    if (checking.value) {
      return unlocked.value;
    }

    checking.value = true;

    try {
      const status = await fetchAdminAccessStatus();

      configured.value = status.configured;

      unlocked.value = status.unlocked;

      /*
       * A token can become invalid if the
       * backend was restarted.
       */
      if (!status.unlocked && getAdminToken()) {
        clearAdminToken();
      }

      return status.unlocked;
    } catch {
      unlocked.value = false;

      clearAdminToken();

      return false;
    } finally {
      checking.value = false;
    }
  }

  async function ensureUnlocked(): Promise<boolean> {
    /*
     * Always trust the backend when
     * restoring a saved session token.
     */
    if (unlocked.value) {
      return true;
    }

    if (!getAdminToken()) {
      return false;
    }

    return refreshStatus();
  }

  function requestUnlock(targetRoute?: string): void {
    if (targetRoute) {
      pendingRoute.value = targetRoute;
    }

    error.value = '';
    modalOpen.value = true;
  }

  function cancelUnlock(): void {
    modalOpen.value = false;

    pendingRoute.value = null;

    error.value = '';
  }

  async function unlock(password: string): Promise<boolean> {
    const clean = password;

    if (!clean) {
      error.value = 'Administrator password is required';

      return false;
    }

    unlocking.value = true;

    error.value = '';

    try {
      const result = await unlockAdminAccess(clean);

      if (!result.ok || !result.token) {
        error.value = 'Invalid administrator password';

        return false;
      }

      configured.value = true;

      unlocked.value = true;

      modalOpen.value = false;

      return true;
    } catch (err: any) {
      error.value = err?.message || 'Unable to unlock administrator access';

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
  }

  function takePendingRoute(): string | null {
    const route = pendingRoute.value;

    pendingRoute.value = null;

    return route;
  }

  return {
    configured,
    unlocked,
    checking,
    unlocking,
    modalOpen,
    error,
    pendingRoute,

    refreshStatus,
    ensureUnlocked,
    requestUnlock,
    cancelUnlock,
    unlock,
    lock,
    takePendingRoute,
  };
});
