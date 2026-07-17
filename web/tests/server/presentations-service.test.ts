import { afterEach, describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'

import {
  createPresentationSession,
  getPresentationSession,
  listPresentationSessions,
  getPresentationsHome,
  normalizePresentationChatCreateRequest,
  normalizePresentationSessionTurnRequest,
  normalizePresentationSubmitRequest,
  validatePresentationJobId,
  validatePresentationSessionId,
} from '../../packages/server/src/services/hermes/presentations'

const originalReinsHome = process.env.REINS_HOME
const temporaryRoots: string[] = []

afterEach(async () => {
  if (originalReinsHome === undefined) delete process.env.REINS_HOME
  else process.env.REINS_HOME = originalReinsHome
  await Promise.all(temporaryRoots.splice(0).map(path => rm(path, { recursive: true, force: true })))
})

describe('presentation service input', () => {
  it('normalizes a brief-first PowerPoint request', () => {
    const request = normalizePresentationSubmitRequest({
      prompt: 'Create a board update about product growth and operational risk.',
      style: 'corporate',
      slide_count: 9,
      output_format: 'pptx',
    })

    expect(request).toMatchObject({
      action: 'new',
      style: 'corporate',
      slide_count: 9,
      output_format: 'pptx',
      engine: 'auto',
      run_qa: true,
    })
    expect(request.metadata).toEqual({ origin: 'reins-web' })
  })

  it('forces HTML requests through Frontend Slides', () => {
    const request = normalizePresentationSubmitRequest({
      prompt: 'Create an interactive product strategy presentation for the web.',
      output_format: 'html',
      engine: 'auto',
    })

    expect(request.engine).toBe('frontend_slides')
  })

  it('always starts a presentation chat with an editable PPTX revision', () => {
    const request = normalizePresentationChatCreateRequest({
      prompt: 'Create a product launch presentation for enterprise customers.',
      output_format: 'html',
      engine: 'frontend_slides',
    })

    expect(request).toMatchObject({
      action: 'new',
      output_format: 'pptx',
      engine: 'auto',
    })
  })

  it('rejects unsafe and incompatible inputs', () => {
    expect(() => validatePresentationJobId('../../etc/passwd')).toThrow(/invalid/i)
    expect(() => normalizePresentationSubmitRequest({
      prompt: 'Create a short presentation for customers.',
      output_format: 'pptx',
      engine: 'frontend_slides',
    })).toThrow(/only supports HTML/i)
    expect(() => normalizePresentationSubmitRequest({
      prompt: 'Too few slides.',
      slide_count: 2,
    })).toThrow(/3 to 30/i)
  })

  it('resolves presentation storage under REINS_HOME', () => {
    process.env.REINS_HOME = '/tmp/reins-presentations-test'
    expect(getPresentationsHome()).toBe('/tmp/reins-presentations-test/presentations')
  })

  it('normalizes preservation-aware session operations', () => {
    expect(normalizePresentationSessionTurnRequest({
      action: 'modify',
      instruction: 'Replace the old product name with the new product name.',
      style: 'corporate',
    })).toMatchObject({
      action: 'modify',
      output_format: 'pptx',
      style: 'corporate',
    })
    expect(normalizePresentationSessionTurnRequest({
      action: 'convert',
      instruction: 'Create a PDF for distribution.',
      output_format: 'pdf',
    })).toMatchObject({
      action: 'convert',
      output_format: 'pdf',
    })
    expect(() => normalizePresentationSessionTurnRequest({
      action: 'restyle',
      instruction: 'Use a dark theme.',
      output_format: 'html',
    })).toThrow(/PPTX revisions/i)
  })

  it('creates and lists server-owned presentation sessions', async () => {
    const root = await mkdtemp(join(tmpdir(), 'reins-presentation-session-'))
    temporaryRoots.push(root)
    process.env.REINS_HOME = root

    const session = await createPresentationSession('Board Review.pptx', Buffer.from('PK-test'))
    const sessions = await listPresentationSessions()

    expect(validatePresentationSessionId(session.session_id)).toBe(session.session_id)
    expect(session).toMatchObject({
      name: 'Board Review',
      source_file_name: 'Board Review.pptx',
      source_type: 'pptx',
      deck_ready: true,
      active_revision: 0,
      turns: [],
    })
    expect(sessions).toHaveLength(1)
    expect(sessions[0]?.session_id).toBe(session.session_id)
    expect(() => validatePresentationSessionId('../../source.pptx')).toThrow(/invalid/i)
  })

  it('accepts a PDF as source material before the first chat turn', async () => {
    const root = await mkdtemp(join(tmpdir(), 'reins-presentation-pdf-'))
    temporaryRoots.push(root)
    process.env.REINS_HOME = root

    const session = await createPresentationSession('Market Research.pdf', Buffer.from('%PDF-test'))

    expect(session).toMatchObject({
      name: 'Market Research',
      source_file_name: 'Market Research.pdf',
      source_type: 'pdf',
      deck_ready: false,
      active_revision: 0,
      turns: [],
    })
  })

  it('promotes a completed PPTX turn to the active revision', async () => {
    const root = await mkdtemp(join(tmpdir(), 'reins-presentation-revision-'))
    temporaryRoots.push(root)
    process.env.REINS_HOME = root
    const session = await createPresentationSession('Roadmap.pptx', Buffer.from('PK-source'))
    const jobId = 'ppt_session_revision'
    const jobRoot = join(root, 'presentations', jobId)
    const outputPath = join(jobRoot, 'output', 'roadmap-modified.pptx')
    await mkdir(join(jobRoot, 'output'), { recursive: true })
    await writeFile(outputPath, Buffer.from('PK-output'))
    await writeFile(join(jobRoot, 'status.json'), JSON.stringify({
      job_id: jobId,
      status: 'completed',
      progress: 100,
      phase: 'Presentation revision is ready',
      action: 'modify',
      engine: 'native_pptx',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      output_path: outputPath,
      warnings: [],
      artifacts: [],
      metadata: {},
    }))

    const statePath = join(root, 'presentations', 'sessions', session.session_id, 'session.json')
    const stored = JSON.parse(await readFile(statePath, 'utf8'))
    stored.turns.push({
      turn: 1,
      action: 'modify',
      instruction: 'Update the roadmap title.',
      style: 'modern',
      output_format: 'pptx',
      job_id: jobId,
      parent_revision: 0,
      advances_deck: true,
      created_at: new Date().toISOString(),
    })
    await writeFile(statePath, JSON.stringify(stored))

    const refreshed = await getPresentationSession(session.session_id)
    expect(refreshed.active_revision).toBe(1)
    expect(refreshed.turns[0]?.job.has_output).toBe(true)
  })
})
