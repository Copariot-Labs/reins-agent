// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import {
  linkOfficeDocumentsToAssistantMessages,
  officeDocumentFromEvent,
  officeDocumentFromMessages,
  type Message,
} from '../../packages/client/src/stores/hermes/chat'
import type { OfficeDocument } from '../../packages/client/src/api/reins/office'

function officeDocument(id: string): OfficeDocument {
  return {
    id,
    title: `Document ${id}`,
    kind: 'docx',
    path: `/tmp/${id}.docx`,
    file_name: `${id}.docx`,
    mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    created_at: '2026-08-12T00:00:00Z',
    updated_at: '2026-08-12T00:00:00Z',
    revision_count: 0,
    prompt: 'create it',
    generator: 'reins',
    officecli_bin: null,
    command_count: 1,
    metadata: {},
  }
}

function toolMessage(
  id: string,
  toolName: string,
  toolResult: Record<string, unknown>,
): Message {
  return {
    id,
    role: 'tool',
    content: '',
    timestamp: Date.now(),
    toolName,
    toolResult: JSON.stringify(toolResult),
    toolStatus: 'done',
  }
}

describe('chat Office preview linkage', () => {
  it('ignores unrelated non-Office tool results and global documents', () => {
    const messages = [
      toolMessage('1', 'other_document_tool', {
        document: { id: 'global-last-created' },
      }),
    ]

    expect(officeDocumentFromMessages(messages)).toBeNull()
  })

  it('returns only the newest Office document linked to this chat', () => {
    const first = officeDocument('office-1')
    const latest = officeDocument('office-2')
    const messages = [
      toolMessage('1', 'create_office_document', { office_document: first }),
      toolMessage('2', 'other_tool', { office_document: officeDocument('unrelated') }),
      toolMessage('3', 'create_office_document', { office_document: latest }),
    ]

    expect(officeDocumentFromMessages(messages)).toEqual(latest)
  })

  it('reads Office metadata directly from live completion events', () => {
    const document = officeDocument('live-office')

    expect(officeDocumentFromEvent({ office_document: document })).toEqual(document)
    expect(officeDocumentFromEvent({ result: { office_document: document } })).toEqual(document)
  })

  it('links persisted Office tool results to their assistant result card', () => {
    const document = officeDocument('persisted-office')
    const assistant: Message = {
      id: 'assistant-1',
      role: 'assistant',
      content: 'Office document created successfully.',
      timestamp: Date.now(),
    }
    const messages = [
      toolMessage('tool-1', 'create_office_document', { office_document: document }),
      assistant,
    ]

    linkOfficeDocumentsToAssistantMessages(messages)

    expect(assistant.officeDocument).toEqual(document)
    expect(officeDocumentFromMessages(messages)).toEqual(document)
  })
})
