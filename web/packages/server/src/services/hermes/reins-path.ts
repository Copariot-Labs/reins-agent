import { homedir } from 'os'
import * as path from 'path'

function pathForPlatform(platform: NodeJS.Platform): typeof path.win32 | typeof path.posix {
  return platform === 'win32' ? path.win32 : path.posix
}

function expandEnvVars(value: string, env: NodeJS.ProcessEnv): string {
  return value
    .replace(/%([^%]+)%/g, (match, name) => env[name] ?? match)
    .replace(/\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)/g, (match, bracedName, bareName) => {
      const name = bracedName || bareName
      return env[name] ?? match
    })
}

export function defaultReinsHome(
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
): string {
  const platformPath = pathForPlatform(platform)

  if (platform === 'win32') {
    const localAppData = env.LOCALAPPDATA?.trim() || env.APPDATA?.trim()
    if (localAppData) return platformPath.join(localAppData, 'reins')
  }

  return platformPath.join(homedir(), '.reins')
}

export function resolveRootHomeFromHermes(
  value: string,
  platform: NodeJS.Platform = process.platform,
): string {
  const platformPath = pathForPlatform(platform)
  const home = platformPath.resolve(value)
  const parent = platformPath.dirname(home)
  if (platformPath.basename(parent) === 'profiles') return platformPath.dirname(parent)
  return home
}

export function resolveReinsHome(
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
): string {
  const platformPath = pathForPlatform(platform)
  const reinsHome = env.REINS_HOME?.trim()
  if (reinsHome) return platformPath.resolve(expandEnvVars(reinsHome, env))

  const hermesHome = env.HERMES_HOME?.trim()
  if (hermesHome) return resolveRootHomeFromHermes(expandEnvVars(hermesHome, env), platform)

  return defaultReinsHome(env, platform)
}
