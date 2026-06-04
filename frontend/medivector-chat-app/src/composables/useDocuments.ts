import type { DocumentGroup, DocumentItem, DocumentSection, Embedding, MetadataSuggestions } from '@/types'
import { computed, reactive, ref, type Ref } from 'vue'
import { api } from '@/composables/useApi'

type SetStatus = (text: string) => void

function todayDate () {
  const now = new Date()
  const offsetMs = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10)
}

function chunkIndexOf (doc: DocumentItem) {
  return Number(doc.chunk_index || 1)
}

function insertChunkByIndex (sortedChunks: DocumentItem[], chunk: DocumentItem) {
  const insertAt = sortedChunks.findIndex(item => chunkIndexOf(chunk) < chunkIndexOf(item))
  if (insertAt === -1) {
    return [...sortedChunks, chunk]
  }
  return [
    ...sortedChunks.slice(0, insertAt),
    chunk,
    ...sortedChunks.slice(insertAt),
  ]
}

export function useDocuments (setStatus: SetStatus, fileInputEl: Ref<HTMLInputElement | null>) {
  const docs = ref<DocumentItem[]>([])
  const docsLoading = ref(false)
  const deletingDocumentId = ref('')
  const addingDoc = ref(false)
  const inferringMetadata = ref(false)
  const selectedFiles = ref<File[]>([])
  const editingDocumentId = ref('')
  const docGroupBy = ref<'topic' | 'source' | 'file'>('topic')
  const docSearchQuery = ref('')
  const docDateFrom = ref('')
  const docDateTo = ref('')

  const newDoc = reactive({
    source_id: '',
    title: '',
    source: '',
    published_date: todayDate(),
    audience: '',
    topic: '',
    content: '',
  })

  const docGroups = computed<DocumentGroup[]>(() => {
    const groups = new Map<string, DocumentItem[]>()
    for (const doc of docs.value) {
      const key = doc.document_id || doc.uuid
      groups.set(key, [...(groups.get(key) || []), doc])
    }

    return Array.from(groups.entries()).map(([documentId, chunks]) => {
      const sortedChunks = chunks.reduce<DocumentItem[]>(
        (sorted, chunk) => insertChunkByIndex(sorted, chunk),
        [],
      )
      const first = sortedChunks[0]
      return {
        document_id: documentId,
        source_id: first.source_id,
        title: first.title || '(未命名)',
        source: first.source || '',
        publisher: first.publisher || '',
        published_date: first.published_date || '',
        version: first.version || '',
        audience: first.audience || '',
        topic: first.topic || '',
        credibility: first.credibility || '',
        file_name: first.file_name || '',
        file_object_key: first.file_object_key || '',
        file_bucket: first.file_bucket || '',
        created_at: first.created_at || '',
        updated_at: first.updated_at || first.created_at || '',
        chunk_count: Math.max(...sortedChunks.map(chunk => Number(chunk.chunk_count || sortedChunks.length || 1))),
        chunks: sortedChunks,
        content: sortedChunks.map(chunk => chunk.content || '').filter(Boolean).join('\n\n'),
      }
    })
  })

  const groupedDocSections = computed<DocumentSection[]>(() => {
    const sections = new Map<string, DocumentGroup[]>()
    for (const group of docGroups.value) {
      const value = docGroupBy.value === 'topic'
        ? group.topic
        : (docGroupBy.value === 'source'
            ? group.source
            : group.file_name)
      const label = value || (docGroupBy.value === 'file' ? '未上傳檔案' : '未分類')
      sections.set(label, [...(sections.get(label) || []), group])
    }
    return Array.from(sections.entries()).map(([key, groups]) => ({ key, label: key, groups }))
  })

  const canInferMetadata = computed(() => Boolean(newDoc.content.trim() || selectedFiles.value.length > 0))
  const docFiltersActive = computed(() => Boolean(
    docSearchQuery.value.trim() || docDateFrom.value || docDateTo.value,
  ))

  function documentsApiPath () {
    const params = new URLSearchParams()
    const query = docSearchQuery.value.trim()
    if (query) {
      params.set('q', query)
    }
    if (docDateFrom.value) {
      params.set('date_from', docDateFrom.value)
    }
    if (docDateTo.value) {
      params.set('date_to', docDateTo.value)
    }
    const queryString = params.toString()
    return queryString ? `/api/documents?${queryString}` : '/api/documents'
  }

  function embeddingSummary (embedding?: Embedding) {
    if (!embedding?.dimension) {
      return 'Embedding：無資料'
    }
    const suffix = embedding.dimension > embedding.preview.length ? ', ...' : ''
    return `Embedding：${embedding.dimension} 維 · [${embedding.preview.join(', ')}${suffix}]`
  }

  function previewText (text: string, maxLength = 320) {
    const normalized = String(text || '').replace(/\s+/g, ' ').trim()
    if (!normalized) {
      return '沒有內容摘要'
    }
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
  }

  async function loadDocs () {
    setStatus('載入資料中')
    docsLoading.value = true
    try {
      const data = await api<{ documents: DocumentItem[] }>(documentsApiPath())
      docs.value = data.documents
      const prefix = docFiltersActive.value ? '篩選結果' : '共有'
      setStatus(`${prefix} ${docGroups.value.length} 份文件、${data.documents.length} 個 chunks`)
    } finally {
      docsLoading.value = false
    }
  }

  async function applyDocFilters () {
    await loadDocs()
  }

  async function clearDocFilters () {
    docSearchQuery.value = ''
    docDateFrom.value = ''
    docDateTo.value = ''
    await loadDocs()
  }

  async function deleteDoc (documentId: string) {
    if (deletingDocumentId.value) {
      return
    }
    if (!confirm('確定要刪除整份文件與所有 chunks？')) {
      return
    }
    deletingDocumentId.value = documentId
    try {
      setStatus('刪除中')
      await api(`/api/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
      await loadDocs()
      setStatus('已刪除整份文件')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
      alert(message)
    } finally {
      deletingDocumentId.value = ''
    }
  }

  function startNewDocument () {
    editingDocumentId.value = ''
    resetDocForm()
  }

  function startEditingDocument (group: DocumentGroup) {
    editingDocumentId.value = group.document_id
    newDoc.source_id = String(group.source_id || '')
    newDoc.title = group.title === '(未命名)' ? '' : group.title
    newDoc.source = group.source
    newDoc.published_date = group.published_date || todayDate()
    newDoc.audience = group.audience
    newDoc.topic = group.topic
    newDoc.content = group.content
    selectedFiles.value = []
    if (fileInputEl.value) {
      fileInputEl.value.value = ''
    }
  }

  function onFileChange (event: Event) {
    const input = event.target as HTMLInputElement
    selectedFiles.value = input.files ? Array.from(input.files) : []
  }

  function resetDocForm () {
    editingDocumentId.value = ''
    newDoc.source_id = ''
    newDoc.title = ''
    newDoc.source = ''
    newDoc.published_date = todayDate()
    newDoc.audience = ''
    newDoc.topic = ''
    newDoc.content = ''
    selectedFiles.value = []
    if (fileInputEl.value) {
      fileInputEl.value.value = ''
    }
  }

  function buildDocumentPayload () {
    const payload = new FormData()
    payload.append('source_id', newDoc.source_id || '')
    payload.append('title', newDoc.title.trim())
    payload.append('source', newDoc.source.trim())
    payload.append('publisher', '')
    payload.append('published_date', newDoc.published_date.trim())
    payload.append('version', '')
    payload.append('audience', newDoc.audience.trim())
    payload.append('topic', newDoc.topic.trim())
    payload.append('credibility', '')
    payload.append('content', newDoc.content.trim())
    for (const file of selectedFiles.value) {
      payload.append('file', file)
    }
    return payload
  }

  function applyMetadataSuggestions (metadata: MetadataSuggestions) {
    if (metadata.title) {
      newDoc.title = metadata.title
    }
    if (metadata.published_date) {
      newDoc.published_date = metadata.published_date
    }
    if (metadata.audience) {
      newDoc.audience = metadata.audience
    }
    if (metadata.topic) {
      newDoc.topic = metadata.topic
    }
  }

  async function inferMetadata () {
    if (inferringMetadata.value || !canInferMetadata.value) {
      return
    }
    inferringMetadata.value = true
    try {
      setStatus('從內容抽取資料欄位')
      const data = await api<{ metadata: MetadataSuggestions }>('/api/documents/metadata-suggestions', {
        method: 'POST',
        body: buildDocumentPayload(),
      })
      applyMetadataSuggestions(data.metadata)
      setStatus('已自動填入可判斷欄位')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
      alert(message)
    } finally {
      inferringMetadata.value = false
    }
  }

  async function saveDocument () {
    if (addingDoc.value) {
      return false
    }
    if (!newDoc.content && selectedFiles.value.length === 0) {
      alert('請輸入內容，或上傳 TXT / PDF 衛教檔案。')
      return false
    }

    const payload = buildDocumentPayload()

    addingDoc.value = true
    try {
      const isEditing = Boolean(editingDocumentId.value)
      setStatus(isEditing ? '更新資料並重新 embedding' : '新增資料並產生 embedding')
      const path = isEditing ? `/api/documents/${encodeURIComponent(editingDocumentId.value)}` : '/api/documents'
      const data = await api<{ documents?: DocumentItem[] }>(path, { method: isEditing ? 'PUT' : 'POST', body: payload })
      resetDocForm()
      if (data.documents && !docFiltersActive.value) {
        docs.value = data.documents
        setStatus(`共有 ${docGroups.value.length} 份文件、${data.documents.length} 個 chunks`)
      } else {
        await loadDocs()
      }
      setStatus(isEditing ? '已更新並重新 embedding' : '已新增資料')
      return true
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
      alert(message)
      return false
    } finally {
      addingDoc.value = false
    }
  }

  return {
    addingDoc,
    canInferMetadata,
    deletingDocumentId,
    docDateFrom,
    docDateTo,
    docFiltersActive,
    docGroupBy,
    docGroups,
    docSearchQuery,
    docs,
    docsLoading,
    editingDocumentId,
    groupedDocSections,
    inferringMetadata,
    newDoc,
    selectedFiles,
    applyDocFilters,
    clearDocFilters,
    deleteDoc,
    embeddingSummary,
    inferMetadata,
    loadDocs,
    onFileChange,
    previewText,
    resetDocForm,
    saveDocument,
    startEditingDocument,
    startNewDocument,
  }
}
