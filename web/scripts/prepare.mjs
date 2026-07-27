import { existsSync } from 'fs'
import { dirname, resolve } from 'path'
import { spawnSync } from 'child_process'
import { fileURLToPath } from 'url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const distDir = resolve(rootDir, 'dist')

if (existsSync(distDir)) {
  process.exit(0)
}

const npmExecPath = process.env.npm_execpath
const command = npmExecPath
  ? process.execPath
  : process.platform === 'win32'
    ? 'npm.cmd'
    : 'npm'
const args = npmExecPath
  ? [npmExecPath, 'run', 'build']
  : ['run', 'build']

const result = spawnSync(command, args, {
  cwd: rootDir,
  stdio: 'inherit',
  shell: !npmExecPath && process.platform === 'win32',
})

process.exit(result.status ?? 1)
