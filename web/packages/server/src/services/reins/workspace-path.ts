import { mkdir } from 'fs/promises'
import { mkdirSync } from 'fs'
import { homedir } from 'os'
import { posix, win32, type PlatformPath } from 'path'

export const REINS_WORKSPACE_FOLDERS = [
  'Inbox',
  'Word',
  'Excel',
  'PowerPoint',
  'Generated',
  'Projects',
] as const

export type ReinsWorkspaceFolder = (typeof REINS_WORKSPACE_FOLDERS)[number]

function pathApi(platform: NodeJS.Platform): PlatformPath {
  return platform === 'win32' ? win32 : posix
}

function expandEnvironmentVariables(
  value: string,
  env: Record<string, string | undefined>,
): string {
  return value
    .replace(/%([^%]+)%/g, (match, name: string) => env[name] || match)
    .replace(/\$\{([^}]+)\}/g, (match, name: string) => env[name] || match)
    .replace(/\$([A-Za-z_][A-Za-z0-9_]*)/g, (match, name: string) => env[name] || match)
}

export function resolveReinsWorkspaceRoot(
  env: Record<string, string | undefined> = process.env,
  platform: NodeJS.Platform = process.platform,
  userHome = homedir(),
): string {
  const paths = pathApi(platform)
  const configured = env.REINS_WORKSPACE_ROOT?.trim()
  if (!configured) return paths.join(userHome, 'Documents', 'Reins Workspace')

  let expanded = expandEnvironmentVariables(configured, env)
  if (expanded === '~') expanded = userHome
  else if (expanded.startsWith('~/') || expanded.startsWith('~\\')) {
    expanded = paths.join(userHome, expanded.slice(2))
  }
  return paths.resolve(expanded)
}

export function reinsWorkspaceDir(
  folder: ReinsWorkspaceFolder,
  workspaceRoot = resolveReinsWorkspaceRoot(),
): string {
  return pathApi(process.platform).join(workspaceRoot, folder)
}

export function ensureReinsWorkspaceSync(
  workspaceRoot = resolveReinsWorkspaceRoot(),
): string {
  mkdirSync(workspaceRoot, { recursive: true })
  for (const folder of REINS_WORKSPACE_FOLDERS) {
    mkdirSync(reinsWorkspaceDir(folder, workspaceRoot), { recursive: true })
  }
  return workspaceRoot
}

export async function ensureReinsWorkspace(
  workspaceRoot = resolveReinsWorkspaceRoot(),
): Promise<string> {
  const options = { recursive: true } as const
  await mkdir(workspaceRoot, options)
  await Promise.all(
    REINS_WORKSPACE_FOLDERS.map((folder) => mkdir(reinsWorkspaceDir(folder, workspaceRoot), options)),
  )
  return workspaceRoot
}

export function reinsWorkspaceInstructions(
  workspaceRoot = resolveReinsWorkspaceRoot(),
): string {
  return [
    `[Reins workspace: ${workspaceRoot}]`,
    `[Current working directory: ${workspaceRoot}]`,
    'Use this native Reins workspace as the default root for file operations.',
    'The user may add or change files there outside Reins, so inspect and re-read the filesystem before reporting that a file is missing or using previously read content.',
    'Save user-facing output in the appropriate Word, Excel, PowerPoint, Generated, or Projects folder. Treat Inbox as user-provided input.',
  ].join('\n')
}
