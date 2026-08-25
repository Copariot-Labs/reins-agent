import { randomBytes, scryptSync, timingSafeEqual } from 'crypto';
import {
  chmodSync,
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from 'fs';
import { dirname, join, resolve } from 'path';

import { resolveReinsHome } from '../hermes/reins-path';

const ADMIN_HASH_ENV = 'REINS_ADMIN_PASSWORD_HASH';

const ADMIN_HASH_FILE_ENV = 'REINS_ADMIN_PASSWORD_HASH_FILE';

const ADMIN_HASH_FILE_NAME = 'admin-password.hash';

const SESSION_TTL_MS = 12 * 60 * 60 * 1000;

const SCRYPT_KEY_LENGTH = 64;

export const ADMIN_PASSWORD_MIN_LENGTH = 12;

export const ADMIN_PASSWORD_MAX_LENGTH = 256;

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
  setupAllowed: boolean;
}

interface ParsedPasswordHash {
  salt: Buffer;
  hash: Buffer;
}

function readPasswordHashFile(path: string): string {
  try {
    return readFileSync(path, 'utf8').trim();
  } catch {
    return '';
  }
}

function localPasswordHashPath(): string {
  return join(resolveReinsHome(), ADMIN_HASH_FILE_NAME);
}

function configuredPasswordHash(): string {
  const fromEnvironment = process.env[ADMIN_HASH_ENV]?.trim();

  if (fromEnvironment) {
    return fromEnvironment;
  }

  const explicitFile = process.env[ADMIN_HASH_FILE_ENV]?.trim();

  if (explicitFile) {
    return readPasswordHashFile(resolve(explicitFile));
  }

  return readPasswordHashFile(localPasswordHashPath());
}

/*
 * Expected format:
 *
 * scrypt$BASE64URL_SALT$BASE64URL_HASH
 */
function parsePasswordHash(encoded: string): ParsedPasswordHash | null {
  const parts = encoded.split('$');

  if (
    parts.length !== 3 ||
    parts[0] !== 'scrypt' ||
    !/^[A-Za-z0-9_-]+$/.test(parts[1]) ||
    !/^[A-Za-z0-9_-]+$/.test(parts[2])
  ) {
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

export function createAdminPasswordHash(
  password: string,
  salt = randomBytes(16),
): string {
  const hash = scryptSync(password, salt, SCRYPT_KEY_LENGTH);

  return [
    'scrypt',
    salt.toString('base64url'),
    hash.toString('base64url'),
  ].join('$');
}

export function adminPasswordValidationError(
  password: string,
): 'too_short' | 'too_long' | null {
  const length = Array.from(password).length;

  if (length < ADMIN_PASSWORD_MIN_LENGTH) {
    return 'too_short';
  }

  if (length > ADMIN_PASSWORD_MAX_LENGTH) {
    return 'too_long';
  }

  return null;
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
 * A missing packaged password is a release configuration error. Only the
 * desktop development build may initialize one locally for testing.
 */
export function isAdminSetupAllowed(): boolean {
  return (
    process.env.REINS_DESKTOP === '1' &&
    process.env.NODE_ENV !== 'production' &&
    !isAdminAccessConfigured()
  );
}

export function configureDevelopmentAdminPassword(
  password: string,
): string | null {
  if (adminPasswordValidationError(password) || !isAdminSetupAllowed()) {
    return null;
  }

  const target = localPasswordHashPath();
  const temporary = `${target}.tmp-${process.pid}-${randomBytes(4).toString('hex')}`;
  let completed = false;

  mkdirSync(dirname(target), {
    recursive: true,
  });

  try {
    writeFileSync(temporary, `${createAdminPasswordHash(password)}\n`, {
      encoding: 'utf8',
      mode: 0o600,
    });

    try {
      chmodSync(temporary, 0o600);
    } catch {
      // Windows access is constrained by the current-user app data directory.
    }

    renameSync(temporary, target);
    completed = true;
  } finally {
    if (!completed) {
      try {
        unlinkSync(temporary);
      } catch {
        // Nothing remains to clean up.
      }
    }
  }

  return createAdminSession(password);
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

    setupAllowed: isAdminSetupAllowed(),
  };
}
