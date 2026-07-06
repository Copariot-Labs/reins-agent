import { spawn, execFileSync, type ChildProcess } from 'child_process'
import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { platform } from 'os'
import { createServer, createConnection } from 'net'
import { getProfileDir } from './hermes-profile'
import { safeFileStore } from '../safe-file-store'
import { logger } from '../logger'
import type { NormalizedChatCapabilities } from './run-chat/capabilities'

const DEFAULT_CDP_PORT = 9222
const CDP_PORT_SCAN_LIMIT = 20
const CDP_CONNECT_TIMEOUT_MS = 10_000
const CONFIG_MANAGED_KEY = 'reins_web_managed_cdp_url'
const CONFIG_PREVIOUS_KEY = 'reins_web_previous_cdp_url'

export interface BrowserConnectionStatus {
  connected: boolean
  cdpUrl?: string
  endpoint?: string
  browser?: string
  profile: string
  managed: boolean
  pid?: number
  error?: string
}

const launchedByProfile = new Map<string, { child?: ChildProcess; cdpUrl: string; pid?: number; executable?: string }>()

function profileConfigPath(profile: string): string {
  return join(getProfileDir(profile), 'config.yaml')
}

function profileDebugDir(profile: string): string {
  return join(getProfileDir(profile), 'chrome-debug')
}

function cdpHttpUrl(value: string): string {
  const raw = value.trim()
  if (!raw) return ''
  if (raw.startsWith('ws://')) {
    const url = new URL(raw)
    return `http://${url.host}`
  }
  if (raw.startsWith('wss://')) {
    const url = new URL(raw)
    return `https://${url.host}`
  }
  return raw.replace(/\/+$/, '')
}

async function fetchJsonWithTimeout(url: string, timeoutMs = 1500): Promise<any> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timeout)
  }
}

async function probeCdp(cdpUrl: string): Promise<{ ok: boolean; data?: any; error?: string }> {
  const base = cdpHttpUrl(cdpUrl)
  if (!base) return { ok: false, error: 'CDP URL is empty' }
  try {
    const data = await fetchJsonWithTimeout(`${base}/json/version`)
    return { ok: true, data }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) }
  }
}

async function readBrowserConfig(profile: string): Promise<Record<string, any>> {
  const config = await safeFileStore.readYaml(profileConfigPath(profile))
  const browser = config.browser && typeof config.browser === 'object' ? config.browser : {}
  return browser
}

async function writeManagedCdpUrl(profile: string, cdpUrl: string): Promise<void> {
  await safeFileStore.updateYaml(profileConfigPath(profile), (config) => {
    const currentBrowser = config.browser && typeof config.browser === 'object' && !Array.isArray(config.browser)
      ? config.browser
      : {}
    if (
      currentBrowser.cdp_url === cdpUrl &&
      currentBrowser[CONFIG_MANAGED_KEY] === true
    ) {
      return { data: config, result: undefined, write: false }
    }
    const nextBrowser = { ...currentBrowser }
    if (nextBrowser[CONFIG_MANAGED_KEY] !== true && typeof nextBrowser.cdp_url === 'string' && nextBrowser.cdp_url.trim()) {
      nextBrowser[CONFIG_PREVIOUS_KEY] = nextBrowser.cdp_url
    }
    nextBrowser.cdp_url = cdpUrl
    nextBrowser[CONFIG_MANAGED_KEY] = true
    return { data: { ...config, browser: nextBrowser }, result: undefined }
  })
}

async function restoreManagedCdpUrl(profile: string): Promise<void> {
  await safeFileStore.updateYaml(profileConfigPath(profile), (config) => {
    const currentBrowser = config.browser && typeof config.browser === 'object' && !Array.isArray(config.browser)
      ? config.browser
      : {}
    if (currentBrowser[CONFIG_MANAGED_KEY] !== true) {
      return { data: config, result: undefined, write: false }
    }

    const nextBrowser = { ...currentBrowser }
    const previous = typeof nextBrowser[CONFIG_PREVIOUS_KEY] === 'string'
      ? nextBrowser[CONFIG_PREVIOUS_KEY]
      : ''
    delete nextBrowser[CONFIG_MANAGED_KEY]
    delete nextBrowser[CONFIG_PREVIOUS_KEY]
    if (previous.trim()) nextBrowser.cdp_url = previous
    else delete nextBrowser.cdp_url
    return { data: { ...config, browser: nextBrowser }, result: undefined }
  })
}

function canConnectTcp(port: number, host = '127.0.0.1'): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = createConnection({ port, host })
    const timeout = setTimeout(() => {
      socket.destroy()
      resolve(false)
    }, 400)
    socket.once('connect', () => {
      clearTimeout(timeout)
      socket.end()
      resolve(true)
    })
    socket.once('error', () => {
      clearTimeout(timeout)
      resolve(false)
    })
  })
}

async function isPortFree(port: number): Promise<boolean> {
  if (await canConnectTcp(port)) return false
  return new Promise((resolve) => {
    const server = createServer()
    server.once('error', () => resolve(false))
    server.listen(port, '127.0.0.1', () => {
      server.close(() => resolve(true))
    })
  })
}

async function findCdpPort(): Promise<number> {
  for (let offset = 0; offset < CDP_PORT_SCAN_LIMIT; offset += 1) {
    const port = DEFAULT_CDP_PORT + offset
    const existing = await probeCdp(`http://127.0.0.1:${port}`)
    if (existing.ok) return port
    if (await isPortFree(port)) return port
  }
  throw new Error(`No available CDP port found near ${DEFAULT_CDP_PORT}`)
}

function commandPath(command: string): string | null {
  try {
    const result = execFileSync(process.platform === 'win32' ? 'where.exe' : 'which', [command], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    return result.split(/\r?\n/).map(line => line.trim()).find(Boolean) || null
  } catch {
    return null
  }
}

function browserCandidates(): string[] {
  const explicit = process.env.REINS_BROWSER_EXECUTABLE?.trim()
    || process.env.HERMES_BROWSER_EXECUTABLE?.trim()
    || process.env.BROWSER_EXECUTABLE?.trim()
  if (explicit) return [explicit]

  if (platform() === 'darwin') {
    return [
      '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    ]
  }

  if (platform() === 'win32') {
    const local = process.env.LOCALAPPDATA || ''
    const programFiles = [process.env.PROGRAMFILES, process.env['PROGRAMFILES(X86)']].filter(Boolean) as string[]
    return [
      local ? join(local, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe') : '',
      ...programFiles.map(base => join(base, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe')),
      ...programFiles.map(base => join(base, 'Google', 'Chrome', 'Application', 'chrome.exe')),
      ...programFiles.map(base => join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe')),
    ].filter(Boolean)
  }

  const commands = [
    'brave-browser',
    'brave',
    'google-chrome',
    'google-chrome-stable',
    'chromium',
    'chromium-browser',
    'microsoft-edge',
    'microsoft-edge-stable',
  ]
  return [
    ...commands.map(command => commandPath(command)).filter(Boolean) as string[],
    '/opt/brave-bin/brave',
    '/snap/bin/brave',
    '/usr/bin/brave-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ]
}

function resolveBrowserExecutable(): string {
  for (const candidate of browserCandidates()) {
    if (candidate && existsSync(candidate)) return candidate
  }
  throw new Error('Could not find Chrome, Brave, Chromium, or Microsoft Edge. Set REINS_BROWSER_EXECUTABLE to the browser binary path.')
}

async function waitForCdp(cdpUrl: string, timeoutMs = CDP_CONNECT_TIMEOUT_MS): Promise<any> {
  const deadline = Date.now() + timeoutMs
  let lastError = ''
  while (Date.now() < deadline) {
    const probe = await probeCdp(cdpUrl)
    if (probe.ok) return probe.data
    lastError = probe.error || ''
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error(`Visible browser did not expose CDP at ${cdpUrl}${lastError ? `: ${lastError}` : ''}`)
}

async function launchVisibleBrowser(profile: string): Promise<BrowserConnectionStatus> {
  const port = await findCdpPort()
  const executable = resolveBrowserExecutable()
  const userDataDir = profileDebugDir(profile)
  mkdirSync(userDataDir, { recursive: true })

  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank',
  ]
  const child = spawn(executable, args, {
    detached: true,
    stdio: 'ignore',
  })
  child.unref()

  const cdpUrl = `http://127.0.0.1:${port}`
  const version = await waitForCdp(cdpUrl)
  launchedByProfile.set(profile, { child, cdpUrl, pid: child.pid, executable })
  await writeManagedCdpUrl(profile, cdpUrl)
  logger.info('[browser-connection] launched visible browser profile=%s cdp=%s pid=%s', profile, cdpUrl, child.pid)

  return {
    connected: true,
    cdpUrl,
    endpoint: version?.webSocketDebuggerUrl,
    browser: version?.Browser || executable,
    profile,
    managed: true,
    pid: child.pid,
  }
}

export async function getVisibleBrowserStatus(profile = 'default'): Promise<BrowserConnectionStatus> {
  const browser = await readBrowserConfig(profile)
  const cdpUrl = typeof browser.cdp_url === 'string' ? browser.cdp_url.trim() : ''
  const managed = browser[CONFIG_MANAGED_KEY] === true
  const launched = launchedByProfile.get(profile)

  if (!cdpUrl) {
    return {
      connected: false,
      profile,
      managed,
      ...(launched ? { cdpUrl: launched.cdpUrl, pid: launched.pid } : {}),
    }
  }

  const probe = await probeCdp(cdpUrl)
  return {
    connected: probe.ok,
    cdpUrl,
    endpoint: probe.data?.webSocketDebuggerUrl,
    browser: probe.data?.Browser,
    profile,
    managed,
    pid: launched?.pid,
    error: probe.ok ? undefined : probe.error,
  }
}

export async function connectVisibleBrowser(profile = 'default'): Promise<BrowserConnectionStatus> {
  const status = await getVisibleBrowserStatus(profile)
  if (status.connected && status.cdpUrl) {
    if (!status.managed) await writeManagedCdpUrl(profile, status.cdpUrl)
    return { ...status, managed: true }
  }

  const existingLocal = await probeCdp(`http://127.0.0.1:${DEFAULT_CDP_PORT}`)
  if (existingLocal.ok) {
    const cdpUrl = `http://127.0.0.1:${DEFAULT_CDP_PORT}`
    await writeManagedCdpUrl(profile, cdpUrl)
    return {
      connected: true,
      cdpUrl,
      endpoint: existingLocal.data?.webSocketDebuggerUrl,
      browser: existingLocal.data?.Browser,
      profile,
      managed: true,
    }
  }

  return launchVisibleBrowser(profile)
}

export async function disconnectVisibleBrowser(profile = 'default'): Promise<BrowserConnectionStatus> {
  await restoreManagedCdpUrl(profile)
  return getVisibleBrowserStatus(profile)
}

export async function prepareBrowserForRun(profile: string, capabilities: NormalizedChatCapabilities): Promise<BrowserConnectionStatus | null> {
  if (capabilities.browser.mode === 'connected') {
    return connectVisibleBrowser(profile)
  }
  await restoreManagedCdpUrl(profile)
  return null
}
