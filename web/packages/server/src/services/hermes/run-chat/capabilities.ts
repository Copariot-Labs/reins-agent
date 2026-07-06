import type { ChatCapabilities, BrowserCapabilityMode } from './types'

export interface NormalizedChatCapabilities {
  browser: {
    mode: BrowserCapabilityMode
  }
  computer_use: {
    enabled: boolean
  }
}

export const DEFAULT_CHAT_CAPABILITIES: NormalizedChatCapabilities = {
  browser: { mode: 'backend' },
  computer_use: { enabled: false },
}

export function normalizeChatCapabilities(value: unknown): NormalizedChatCapabilities {
  const record = value && typeof value === 'object' ? value as Record<string, any> : {}
  const browser = record.browser && typeof record.browser === 'object' ? record.browser : {}
  const computerUse = record.computer_use && typeof record.computer_use === 'object' ? record.computer_use : {}
  const rawBrowserMode = String(browser.mode || '').trim()
  const browserMode: BrowserCapabilityMode = rawBrowserMode === 'off' || rawBrowserMode === 'connected'
    ? rawBrowserMode
    : 'backend'

  return {
    browser: { mode: browserMode },
    computer_use: { enabled: computerUse.enabled === true },
  }
}

export function chatCapabilitiesKey(value: unknown): string {
  const capabilities = normalizeChatCapabilities(value)
  return [
    `browser:${capabilities.browser.mode}`,
    `computer:${capabilities.computer_use.enabled ? 'on' : 'off'}`,
  ].join('|')
}

export function chatCapabilitiesInstructions(value: unknown): string[] {
  const capabilities = normalizeChatCapabilities(value)
  const lines = [
    `[Web chat browser mode: ${capabilities.browser.mode}]`,
    `[Web chat computer use: ${capabilities.computer_use.enabled ? 'enabled' : 'disabled'}]`,
  ]

  if (capabilities.browser.mode === 'connected') {
    lines.push('The user selected a visible connected browser. Use Hermes browser tooling with the configured connected browser/CDP backend when it is available; do not send `/browser connect` as chat text.')
  } else if (capabilities.browser.mode === 'backend') {
    lines.push('The user selected backend browsing. Use Hermes browser tooling in the backend when web research or browser automation is useful.')
  } else {
    lines.push('The user turned browser tooling off for this run. Avoid browser automation unless the user explicitly changes the mode.')
  }

  if (capabilities.computer_use.enabled) {
    lines.push('The user enabled Hermes computer use for this run. Use desktop control only when it is necessary, and rely on approval events for risky actions.')
  } else {
    lines.push('Hermes computer use is disabled for this run. Do not attempt desktop app control unless the user enables it.')
  }

  return lines
}

export function toBridgeCapabilities(value: unknown): ChatCapabilities {
  return normalizeChatCapabilities(value)
}
