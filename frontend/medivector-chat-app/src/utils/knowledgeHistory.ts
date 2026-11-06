import type { ConversationMessageItem, QueryTraceSummary, ReferenceItem } from '@/types'

export type HistoryRequest = <T>(path: string) => Promise<T>

export async function loadHistoryDetail (request: HistoryRequest, conversationId: string) {
  const [history, audit] = await Promise.all([
    request<{ messages: ConversationMessageItem[] }>(`/api/conversations/${encodeURIComponent(conversationId)}`),
    request<{ traces: QueryTraceSummary[] }>(`/api/knowledge/query-traces?${new URLSearchParams({ conversation_id: conversationId })}`),
  ])
  return {
    messages: history.messages.filter(message => message.role === 'user' || message.role === 'assistant'),
    traces: audit.traces,
  }
}

export function linkedHistoryTrace (message: ConversationMessageItem, traces: QueryTraceSummary[]): string | null {
  const traceId = message.query_trace_id
  return traceId && traces.some(trace => trace.id === traceId) ? traceId : null
}

export function canOpenHistoryCitation (reference: ReferenceItem): boolean {
  const metadata = reference.chunk_metadata
  return Boolean(reference.uuid && reference.document_version_id
    && typeof metadata?.branch_id === 'string' && metadata.branch_id
    && typeof metadata?.department_id === 'string' && metadata.department_id)
}

export function historyScope (message: ConversationMessageItem) {
  const filters = message.applied_filters || message.references?.[0]?.chunk_metadata || {}
  return {
    branchId: typeof filters.branch_id === 'string' ? filters.branch_id : '',
    departmentId: typeof filters.department_id === 'string' ? filters.department_id : '',
  }
}
