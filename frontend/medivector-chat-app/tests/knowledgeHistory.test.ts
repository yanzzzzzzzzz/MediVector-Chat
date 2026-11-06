import type { ConversationMessageItem, QueryTraceSummary, ReferenceItem } from '../src/types.ts'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canOpenHistoryCitation, historyScope, linkedHistoryTrace, loadHistoryDetail } from '../src/utils/knowledgeHistory.ts'

const traces = [{ id: 'later-trace' }, { id: 'original-trace' }] as QueryTraceSummary[]

test('links only an explicit trace from the owned conversation, never a latest or matching-answer guess', () => {
  const oldMessage = { role: 'assistant', content: 'same answer' }
  assert.equal(linkedHistoryTrace(oldMessage, traces), null)
  assert.equal(linkedHistoryTrace({ ...oldMessage, query_trace_id: 'foreign-trace' }, traces), null)
  assert.equal(linkedHistoryTrace({ ...oldMessage, query_trace_id: 'original-trace' }, traces), 'original-trace')
})

test('history uses saved scope and disables citations without a version or authorized-scope metadata', () => {
  const reference = { uuid: 'chunk', document_version_id: 'v1', chunk_metadata: { branch_id: 'old-branch', department_id: 'old-department' } } as ReferenceItem
  assert.equal(canOpenHistoryCitation(reference), true)
  assert.equal(canOpenHistoryCitation({ ...reference, document_version_id: undefined }), false)
  assert.equal(canOpenHistoryCitation({ ...reference, chunk_metadata: {} }), false)
  const message: ConversationMessageItem = { role: 'assistant', content: '', references: [reference] }
  assert.deepEqual(historyScope(message), { branchId: 'old-branch', departmentId: 'old-department' })
  assert.deepEqual(historyScope({ ...message, applied_filters: { branch_id: 'saved', department_id: 'scope' } }), { branchId: 'saved', departmentId: 'scope' })
  assert.deepEqual(historyScope({ role: 'assistant', content: 'no evidence' }), { branchId: '', departmentId: '' })
})

test('loads history and audit together without showing internal message roles', async () => {
  const paths: string[] = []
  const request = async <T>(path: string): Promise<T> => {
    paths.push(path)
    return (path.startsWith('/api/conversations/')
      ? { messages: [{ role: 'system', content: 'internal' }, { role: 'user', content: 'synthetic' }, { role: 'assistant', content: 'reply' }] }
      : { traces }) as T
  }
  const result = await loadHistoryDetail(request, 'synthetic/id')
  assert.deepEqual(result.messages.map(message => message.role), ['user', 'assistant'])
  assert.equal(result.traces, traces)
  assert.ok(paths.includes('/api/conversations/synthetic%2Fid'))
  assert.ok(paths.includes('/api/knowledge/query-traces?conversation_id=synthetic%2Fid'))
})

test('a denied history or trace read rejects the detail load', async () => {
  await assert.rejects(loadHistoryDetail(async () => {
    throw new Error('not authorized')
  }, 'id'), /not authorized/)
})
