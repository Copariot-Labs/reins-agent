import { getBaseUrlValue } from '@/api/client';

const ADMIN_TOKEN_KEY = 'reins_admin_access_token';

export interface AdminAccessStatus {
  configured: boolean;
  unlocked: boolean;
  setupAllowed: boolean;
}

export interface AdminUnlockResponse {
  ok: boolean;
  token: string;
}

export class AdminAccessApiError extends Error {
  readonly code: string;

  readonly retryAfterSeconds: number;

  constructor(
    message: string,
    code = '',
    retryAfterSeconds = 0,
  ) {
    super(message);
    this.name = 'AdminAccessApiError';
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function baseUrl(): string {
  return getBaseUrlValue();
}

export function getAdminToken(): string {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setAdminToken(token: string): void {
  try {
    if (token) {
      sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    }
  } catch {
    // Keep working even when sessionStorage is unavailable.
  }
}

export function clearAdminToken(): void {
  setAdminToken('');
}

function adminHeaders(includeJson = false): Record<string, string> {
  const headers: Record<string, string> = {};

  if (includeJson) {
    headers['Content-Type'] = 'application/json';
  }

  const token = getAdminToken();

  if (token) {
    headers['X-Reins-Admin-Token'] = token;
  }

  return headers;
}

async function readResponse<T>(response: Response): Promise<T> {
  const text = await response.text().catch(() => '');

  let data: any = {};

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = {};
    }
  }

  if (!response.ok) {
    const message =
      typeof data?.error === 'string'
        ? data.error
        : text || response.statusText || 'Administrator access request failed';

    throw new AdminAccessApiError(
      message,
      typeof data?.code === 'string' ? data.code : '',
      Number(data?.retry_after_seconds) || 0,
    );
  }

  return data as T;
}

export async function fetchAdminAccessStatus(): Promise<AdminAccessStatus> {
  const response = await fetch(`${baseUrl()}/api/reins/admin-access/status`, {
    method: 'GET',
    headers: adminHeaders(),
  });

  return readResponse<AdminAccessStatus>(response);
}

export async function unlockAdminAccess(
  password: string,
): Promise<AdminUnlockResponse> {
  const response = await fetch(`${baseUrl()}/api/reins/admin-access/unlock`, {
    method: 'POST',

    headers: adminHeaders(true),

    body: JSON.stringify({
      password,
    }),
  });

  const result = await readResponse<AdminUnlockResponse>(response);

  if (result.ok && result.token) {
    setAdminToken(result.token);
  }

  return result;
}

export async function setupAdminAccess(
  password: string,
): Promise<AdminUnlockResponse> {
  const response = await fetch(`${baseUrl()}/api/reins/admin-access/setup`, {
    method: 'POST',
    headers: adminHeaders(true),
    body: JSON.stringify({
      password,
    }),
  });

  const result = await readResponse<AdminUnlockResponse>(response);

  if (result.ok && result.token) {
    setAdminToken(result.token);
  }

  return result;
}

export async function lockAdminAccess(): Promise<void> {
  try {
    await fetch(`${baseUrl()}/api/reins/admin-access/lock`, {
      method: 'POST',
      headers: adminHeaders(),
    });
  } finally {
    clearAdminToken();
  }
}
