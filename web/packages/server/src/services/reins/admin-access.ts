import { randomBytes, scryptSync, timingSafeEqual } from 'crypto';

const ADMIN_HASH_ENV = 'REINS_ADMIN_PASSWORD_HASH';

const SESSION_TTL_MS = 12 * 60 * 60 * 1000;

const SCRYPT_KEY_LENGTH = 64;

/*
 * Admin sessions live only in memory.
 *
 * Closing the Reins desktop backend automatically
 * removes every administrator session.
 */
const sessions = new Map<string, number>();

export interface AdminAccessStatus {
  configured: boolean;
  unlocked: boolean;
}

interface ParsedPasswordHash {
  salt: Buffer;
  hash: Buffer;
}

function configuredPasswordHash(): string {
  return process.env[ADMIN_HASH_ENV]?.trim() || '';
}

/*
 * Expected format:
 *
 * scrypt$BASE64URL_SALT$BASE64URL_HASH
 */
function parsePasswordHash(encoded: string): ParsedPasswordHash | null {
  const parts = encoded.split('$');

  if (parts.length !== 3 || parts[0] !== 'scrypt') {
    return null;
  }

  try {
    const salt = Buffer.from(parts[1], 'base64url');

    const hash = Buffer.from(parts[2], 'base64url');

    if (salt.length < 16 || hash.length !== SCRYPT_KEY_LENGTH) {
      return null;
    }

    return {
      salt,
      hash,
    };
  } catch {
    return null;
  }
}

function safeEqual(left: Buffer, right: Buffer): boolean {
  if (left.length !== right.length) {
    return false;
  }

  try {
    return timingSafeEqual(left, right);
  } catch {
    return false;
  }
}

function verifyPassword(password: string): boolean {
  if (!password) {
    return false;
  }

  const parsed = parsePasswordHash(configuredPasswordHash());

  if (!parsed) {
    return false;
  }

  try {
    const candidate = scryptSync(password, parsed.salt, SCRYPT_KEY_LENGTH);

    return safeEqual(candidate, parsed.hash);
  } catch {
    return false;
  }
}

function pruneExpiredSessions(): void {
  const now = Date.now();

  for (const [token, expiresAt] of sessions) {
    if (expiresAt <= now) {
      sessions.delete(token);
    }
  }
}

export function isAdminAccessConfigured(): boolean {
  return Boolean(parsePasswordHash(configuredPasswordHash()));
}

/*
 * This endpoint is intended for the local
 * desktop application.
 *
 * Development mode is also allowed so we
 * can test the Tauri app on macOS.
 */
export function isAdminAccessAvailable(): boolean {
  return (
    process.env.REINS_DESKTOP === '1' || process.env.NODE_ENV !== 'production'
  );
}

export function createAdminSession(password: string): string | null {
  if (!isAdminAccessConfigured()) {
    return null;
  }

  if (!verifyPassword(password)) {
    return null;
  }

  pruneExpiredSessions();

  const token = randomBytes(32).toString('base64url');

  sessions.set(token, Date.now() + SESSION_TTL_MS);

  return token;
}

export function validateAdminSession(token: string): boolean {
  if (!token) {
    return false;
  }

  pruneExpiredSessions();

  const expiresAt = sessions.get(token);

  if (!expiresAt) {
    return false;
  }

  if (expiresAt <= Date.now()) {
    sessions.delete(token);

    return false;
  }

  return true;
}

export function revokeAdminSession(token: string): void {
  if (!token) {
    return;
  }

  sessions.delete(token);
}

export function readAdminToken(getHeader: (name: string) => string): string {
  return String(getHeader('x-reins-admin-token') || '').trim();
}

export function getAdminAccessStatus(token = ''): AdminAccessStatus {
  return {
    configured: isAdminAccessConfigured(),

    unlocked: validateAdminSession(token),
  };
}
