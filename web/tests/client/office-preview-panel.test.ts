// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchOfficePreviewHtmlMock = vi.hoisted(() => vi.fn())

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ locale: { value: 'en' } }),
}))

vi.mock('naive-ui', () => ({
  NButton: { template: '<button><slot /></button>' },
  NSpin: { template: '<span class="test-spin" />' },
  NTag: { template: '<span><slot /></span>' },
}))

vi.mock('@/api/reins/office', () => ({
  fetchOfficePreviewHtml: fetchOfficePreviewHtmlMock,
}))

vi.mock('@/api/reins/download', () => ({
  downloadFile: vi.fn(),
}))

import OfficePreviewPanel from '@/components/reins/OfficePreviewPanel.vue'
import type { OfficeDocument } from '@/api/reins/office'

const document: OfficeDocument = {
  id: 'office-1',
  title: 'Visible Office Preview',
  kind: 'docx',
  path: '/tmp/visible.docx',
  file_name: 'visible.docx',
  mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  created_at: '2026-08-12T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
  revision_count: 0,
  prompt: 'create document',
  generator: 'reins',
  officecli_bin: null,
  command_count: 1,
  metadata: {},
}

describe('OfficePreviewPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the toolbar and fetched Office HTML in a visible iframe', async () => {
    const html = '<!doctype html><html><body><h1>Rendered document</h1></body></html>'
    fetchOfficePreviewHtmlMock.mockResolvedValue(html)

    const wrapper = mount(OfficePreviewPanel, { props: { document } })
    await flushPromises()

    expect(wrapper.find('.document-toolbar').exists()).toBe(true)
    expect(wrapper.find('.preview-shell').exists()).toBe(true)
    const frame = wrapper.find('iframe')
    expect(frame.exists()).toBe(true)
    expect(frame.attributes('srcdoc')).toBe(html)
    expect(wrapper.find('template .document-toolbar').exists()).toBe(false)
  })

  it('shows a visible error and retry action when rendering fails', async () => {
    fetchOfficePreviewHtmlMock.mockRejectedValue(new Error('Preview worker failed'))

    const wrapper = mount(OfficePreviewPanel, { props: { document } })
    await flushPromises()

    expect(wrapper.find('.preview-error').text()).toContain('Preview worker failed')
    expect(wrapper.find('.preview-error button').text()).toBe('Refresh')
  })
})
