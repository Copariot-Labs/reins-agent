import { getActiveProfileName, getApiKey, getBaseUrlValue } from '../client'

type TauriInvoke = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>

type TauriWindow = Window & {
  __TAURI_INTERNALS__?: {
    invoke?: TauriInvoke
  }
}

function getTauriInvoke(): TauriInvoke | null {
  if (typeof window === 'undefined') return null
  const internals = (window as TauriWindow).__TAURI_INTERNALS__
  const invoke = internals?.invoke
  return typeof invoke === 'function' ? invoke.bind(internals) : null
}

function normalizedDownloadName(fileName?: string): string {
  let decoded = fileName || ''
  try {
    decoded = decodeURIComponent(decoded)
  } catch {
    // Preserve a valid literal filename when it contains a standalone `%`.
  }
  return decoded.split(/[\\/]/).pop()?.trim() || 'download'
}

/**
 * Save a fetched file in either environment. Browsers use the native download
 * mechanism; Tauri opens an OS save dialog and writes through a Rust command.
 */
export async function saveBlob(blob: Blob, fileName?: string): Promise<boolean> {
  const name = normalizedDownloadName(fileName)
  const invoke = getTauriInvoke()
  if (invoke) {
    const bytes = Array.from(new Uint8Array(await blob.arrayBuffer()))
    return invoke<boolean>('save_download', { fileName: name, bytes })
  }

  const blobUrl = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = name
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    return true
  } finally {
    URL.revokeObjectURL(blobUrl)
  }
}

/** Fetch a URL and save its response using the environment-appropriate flow. */
export async function downloadUrl(
  url: string,
  fileName?: string,
  options?: RequestInit,
): Promise<boolean> {
  const res = await fetch(url, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(body.error || `Download failed: ${res.status}`)
  }
  return saveBlob(await res.blob(), fileName)
}

/**
 * Construct a download URL with auth token as query parameter.
 * Token is passed via query param because <a> tags cannot set headers.
 */
export function getDownloadUrl(filePath: string, fileName?: string): string {
  const base = getBaseUrlValue()

  // Guard: if filePath is already a full download URL, extract the real path
  // to prevent double-wrapping (/api/hermes/download?path=/api/hermes/download?path=...)
  if (filePath.startsWith('/api/hermes/download?')) {
    try {
      const parsed = new URL(filePath, 'http://localhost')
      const realPath = parsed.searchParams.get('path')
      if (realPath) filePath = realPath
    } catch {
      // fall through with original filePath
    }
  }

  // Decode the path first in case it's already encoded (e.g., from AI responses)
  // URLSearchParams will encode it again, so we need to start with decoded text
  const decodedPath = decodeURIComponent(filePath)
  const params = new URLSearchParams({ path: decodedPath })
  if (fileName) {
    const decodedName = decodeURIComponent(fileName)
    params.set('name', decodedName)
  }
  const profileName = getActiveProfileName()
  if (profileName) params.set('profile', profileName)
  const token = getApiKey()
  if (token) params.set('token', token)
  return `${base}/api/hermes/download?${params.toString()}`
}

/**
 * Download a file. Uses fetch to detect errors, then creates a blob URL
 * for the browser download. Throws with error message on failure.
 */
export async function downloadFile(filePath: string, fileName?: string): Promise<boolean> {
  const url = getDownloadUrl(filePath, fileName)
  return downloadUrl(url, fileName || filePath.split('/').pop() || 'download')
}

/**
 * Get preview file content.
 * Throws with error message on failure.
 */
export async function fetchFileText(filePath: string, fileName?: string): Promise<string> {
  const url = getDownloadUrl(filePath, fileName)
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(body.error || `Preview failed: ${res.status}`)
  }
  return res.text()
}
