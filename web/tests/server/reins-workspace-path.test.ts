import { existsSync, mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  REINS_WORKSPACE_FOLDERS,
  ensureReinsWorkspaceSync,
  resolveReinsWorkspaceRoot,
} from '../../packages/server/src/services/reins/workspace-path'

describe('Reins native workspace paths', () => {
  let temporaryRoot = ''

  afterEach(() => {
    if (temporaryRoot) rmSync(temporaryRoot, { recursive: true, force: true })
    temporaryRoot = ''
  })

  it('uses the current user Documents folder on Windows', () => {
    expect(resolveReinsWorkspaceRoot({}, 'win32', 'C:\\Users\\mei')).toBe(
      'C:\\Users\\mei\\Documents\\Reins Workspace',
    )
  })

  it('expands a configured workspace path', () => {
    expect(resolveReinsWorkspaceRoot(
      { REINS_WORKSPACE_ROOT: '$HOME/工作区', HOME: '/Users/mei' },
      'darwin',
      '/Users/mei',
    )).toBe('/Users/mei/工作区')
  })

  it('expands Windows environment variables in an override', () => {
    expect(resolveReinsWorkspaceRoot(
      { REINS_WORKSPACE_ROOT: '%USERPROFILE%\\Reins', USERPROFILE: 'D:\\Users\\mei' },
      'win32',
      'C:\\Users\\mei',
    )).toBe('D:\\Users\\mei\\Reins')
  })

  it('creates every visible workspace folder', () => {
    temporaryRoot = mkdtempSync(join(tmpdir(), 'reins-workspace-'))
    const workspace = join(temporaryRoot, 'Reins Workspace')
    ensureReinsWorkspaceSync(workspace)

    for (const folder of REINS_WORKSPACE_FOLDERS) {
      expect(existsSync(join(workspace, folder))).toBe(true)
    }
  })
})
