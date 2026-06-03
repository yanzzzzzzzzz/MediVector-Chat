<template>
  <div class="page">
    <header class="app-header">
      <h1>Vector DB 中文問答</h1>
      <div class="status">{{ status }}</div>
    </header>

    <main class="layout">
      <ConversationSidebar
        :conversation-id="conversationId"
        :conversations="conversations"
        :deleting-convo-id="deletingConvoId"
        @create-new="createNewConversation"
        @delete-conversation="deleteConversation"
        @open-docs="openDocsDialog"
        @switch-conversation="switchConversation"
      />

      <section class="panel">
        <div class="toolbar">
          <div class="toolbar-left">
            <h2 class="chat-title">{{ currentConvoTitle }}</h2>
          </div>

          <div class="actions">
            <button type="button" @click="clearChat">清除對話</button>
          </div>
        </div>

        <div ref="chatLogEl" class="chat-log">
          <MessageBubble
            v-for="message in messages"
            :key="message.id"
            :message="message"
            @open-reference="openReferenceDialog"
          />
        </div>

        <form class="ask-form" @submit.prevent="askQuestion">
          <label class="rag-control">
            <span>使用 RAG 搜尋向量資料庫</span>
            <input v-model="ragEnabled" type="checkbox">
          </label>

          <label>問題
            <textarea
              v-model.trim="question"
              placeholder="問一個問題，系統會先搜尋 vector DB 當參考"
              required
              @keydown="handleQuestionKeydown"
            />
          </label>

          <button class="primary" type="submit">送出</button>
        </form>
      </section>
    </main>

    <dialog ref="docsDialogEl" class="docs-dialog">
      <div class="dialog-head">
        <h2>衛教資料庫</h2>

        <div style="display:flex; align-items:center; gap:8px;">
          <button type="button" @click="loadDocs">
            <svg
              fill="none"
              height="14"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              viewBox="0 0 24 24"
              width="14"
              xmlns="http://www.w3.org/2000/svg"
            ><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
            重新整理
          </button>

          <button class="primary" type="button" @click="openDocDialog">
            <svg
              fill="none"
              height="14"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2.5"
              viewBox="0 0 24 24"
              width="14"
              xmlns="http://www.w3.org/2000/svg"
            ><line x1="12" x2="12" y1="5" y2="19" /><line x1="5" x2="19" y1="12" y2="12" /></svg>
            新增資料
          </button>

          <button type="button" @click="closeDocsDialog">關閉</button>
        </div>
      </div>

      <div class="docs-dialog-body">
        <div v-if="docsLoading" aria-live="polite" class="list-loading" role="status">
          <span aria-hidden="true" class="spinner inline" />
          <span>載入資料中</span>
        </div>

        <div v-else-if="docGroups.length === 0" class="doc">
          <div class="doc-title">目前沒有衛教資料</div>
          <div class="doc-meta">按「新增資料」建立第一筆向量資料。</div>
        </div>

        <template v-else>
          <div class="doc-tools">
            <label>分組方式
              <select v-model="docGroupBy">
                <option value="topic">主題分類</option>
                <option value="source">來源</option>
                <option value="file">檔案</option>
              </select>
            </label>

            <div class="doc-count">{{ docGroups.length }} 份文件 · {{ docs.length }} 個 chunks</div>
          </div>

          <section v-for="section in groupedDocSections" :key="section.key" class="doc-section">
            <h3>{{ section.label }}</h3>

            <article v-for="group in section.groups" :key="group.document_id" class="doc">
              <div class="doc-head">
                <div>
                  <div class="doc-title">{{ group.title || '(未命名)' }}</div>
                  <div class="doc-meta">source_id={{ group.source_id }} · {{ group.source || '未填來源' }}</div>

                  <div class="doc-meta">
                    日期={{ group.published_date || '未填' }} · 適用對象={{ group.audience || '未填' }} · 主題={{ group.topic || '未分類' }}
                  </div>

                  <div class="doc-meta">
                    {{ group.file_name || '手動內容' }} · chunks={{ group.chunks.length }} · updated={{ group.updated_at || '未知' }}
                  </div>
                </div>

                <div class="doc-actions">
                  <button type="button" @click="editDoc(group)">編輯</button>

                  <button
                    class="danger"
                    :class="{ loading: deletingDocumentId === group.document_id }"
                    :disabled="Boolean(deletingDocumentId)"
                    type="button"
                    @click="deleteDoc(group.document_id)"
                  >
                    <span aria-hidden="true" class="spinner" />
                    <span>{{ deletingDocumentId === group.document_id ? '刪除中' : '刪除整份' }}</span>
                  </button>
                </div>
              </div>

              <p class="doc-preview">{{ previewText(group.content) }}</p>

              <details class="doc-details">
                <summary>展開全文</summary>
                <div class="doc-content">{{ group.content }}</div>
              </details>

              <details class="doc-details">
                <summary>查看 {{ group.chunks.length }} 個 chunks</summary>

                <article v-for="chunk in group.chunks" :key="chunk.uuid" class="chunk-card">
                  <div class="doc-meta">chunk={{ chunk.chunk_index || 1 }} / {{ chunk.chunk_count || 1 }} · uuid={{ chunk.uuid }}</div>
                  <p class="doc-preview">{{ previewText(chunk.content || '', 220) }}</p>

                  <details class="doc-details nested">
                    <summary>展開 chunk 內容</summary>
                    <div class="doc-content">{{ chunk.content || '' }}</div>
                  </details>

                  <details class="embedding nested">
                    <summary>{{ embeddingSummary(chunk.embedding) }}</summary>
                    <pre v-if="chunk.embedding?.dimension">{{ JSON.stringify(chunk.embedding.values, null, 2) }}</pre>
                  </details>
                </article>
              </details>

              <details class="doc-details">
                <summary>技術資訊</summary>
                <div class="doc-meta">document_id={{ group.document_id }}</div>

                <div v-if="group.file_name" class="doc-meta">
                  file={{ group.file_name }} · {{ group.file_bucket || '' }}/{{ group.file_object_key || '' }}
                </div>
              </details>
            </article>
          </section>
        </template>
      </div>
    </dialog>

    <dialog ref="docDialogEl">
      <div class="dialog-head">
        <h2>{{ editingDocumentId ? '編輯資料' : '新增資料' }}</h2>
        <button type="button" @click="closeDocDialog">關閉</button>
      </div>

      <form class="dialog-form" @submit.prevent="addDocument">
        <div class="two">
          <label>來源 ID
            <input v-model="newDoc.source_id" placeholder="自動產生" type="number">
          </label>

          <label>標題
            <input v-model.trim="newDoc.title" placeholder="例如：睡眠衛教重點" :required="selectedFiles.length === 0">
          </label>
        </div>

        <label>來源
          <input v-model.trim="newDoc.source" placeholder="例如：內部測試資料 / sleep-guide" required>
        </label>

        <div class="two">
          <label>日期
            <input v-model.trim="newDoc.published_date" placeholder="例如：2026-06-03">
          </label>

          <label>適用對象
            <input v-model.trim="newDoc.audience" placeholder="例如：成人 / 孕婦 / 照護者">
          </label>
        </div>

        <label>主題分類
          <input v-model.trim="newDoc.topic" placeholder="例如：睡眠 / 皮膚 / 慢性病">
        </label>

        <label>內容
          <textarea v-model.trim="newDoc.content" placeholder="輸入要放進 vector DB 的中文資料，或改以上傳檔案" />
        </label>

        <label>衛教檔案
          <input
            ref="fileInputEl"
            accept=".txt,.pdf,text/plain,application/pdf"
            multiple
            type="file"
            @change="onFileChange"
          >

          <span class="hint">
            可批次上傳 TXT 或 PDF；新增時多檔會各自成為一份文件。編輯既有文件時若選檔，會替換為該檔文字並重新 embedding。
          </span>
        </label>

        <div class="metadata-actions">
          <button
            :class="{ loading: inferringMetadata }"
            :disabled="!canInferMetadata || inferringMetadata || addingDoc"
            type="button"
            @click="inferMetadata"
          >
            <span aria-hidden="true" class="spinner" />
            <span>{{ inferringMetadata ? '讀取內容中' : '從內容自動填入' }}</span>
          </button>

          <span class="hint">會補齊內容中能判斷的欄位；抽不到的會保持空白。</span>
        </div>

        <div class="dialog-actions">
          <button type="button" @click="closeDocDialog">取消</button>

          <button class="primary" :class="{ loading: addingDoc }" :disabled="addingDoc" type="submit">
            <span aria-hidden="true" class="spinner" />
            <span>{{ addingDoc ? 'Embedding 中' : editingDocumentId ? '更新並 embedding' : '新增並 embedding' }}</span>
          </button>
        </div>
      </form>
    </dialog>

    <dialog ref="deleteConvoDialogEl" class="confirm-dialog">
      <div class="dialog-head">
        <h2>刪除對話</h2>
        <button type="button" @click="cancelDeleteConversation">關閉</button>
      </div>

      <div class="confirm-body">
        <p>確定要刪除「{{ pendingDeleteTitle }}」？此操作無法復原。</p>

        <div class="dialog-actions">
          <button type="button" @click="cancelDeleteConversation">取消</button>

          <button
            class="danger"
            :class="{ loading: deletingConvoId !== null }"
            :disabled="deletingConvoId !== null"
            type="button"
            @click="confirmDeleteConversation"
          >
            <span aria-hidden="true" class="spinner" />
            <span>{{ deletingConvoId !== null ? '刪除中' : '確認刪除' }}</span>
          </button>
        </div>
      </div>
    </dialog>

    <ReferenceDialog ref="referenceDialogEl" :reference="activeReference" @close="closeReferenceDialog" />
  </div>
</template>

<script setup lang="ts">
  import type { AskResponse, ChatMessage, ConversationItem, DocumentGroup, DocumentItem, DocumentSection, Embedding, EvidenceAssessment, MetadataSuggestions, ReferenceItem, RiskAssessment } from '@/types'
  import { computed, nextTick, onMounted, reactive, ref } from 'vue'
  import ConversationSidebar from '@/components/ConversationSidebar.vue'
  import MessageBubble from '@/components/MessageBubble.vue'
  import ReferenceDialog from '@/components/ReferenceDialog.vue'
  import { api } from '@/composables/useApi'

  const status = ref('準備中')
  const docs = ref<DocumentItem[]>([])
  const docsLoading = ref(false)
  const deletingDocumentId = ref('')
  const messages = ref<ChatMessage[]>([])
  const question = ref('')
  const ragEnabled = ref(true)
  const addingDoc = ref(false)
  const inferringMetadata = ref(false)
  const selectedFiles = ref<File[]>([])
  const editingDocumentId = ref('')
  const docGroupBy = ref<'topic' | 'source' | 'file'>('topic')
  const activeReference = ref<ReferenceItem | null>(null)
  const conversations = ref<ConversationItem[]>([])
  const deletingConvoId = ref<string | null>(null)
  const chatLogEl = ref<HTMLDivElement | null>(null)
  const docDialogEl = ref<HTMLDialogElement | null>(null)
  const docsDialogEl = ref<HTMLDialogElement | null>(null)
  const referenceDialogEl = ref<InstanceType<typeof ReferenceDialog> | null>(null)
  const deleteConvoDialogEl = ref<HTMLDialogElement | null>(null)
  const pendingDeleteId = ref<string | null>(null)
  const pendingDeleteTitle = ref('')
  const fileInputEl = ref<HTMLInputElement | null>(null)
  const conversationId = ref<string>(localStorage.getItem('conversationId') || crypto.randomUUID())
  let nextMessageId = 1

  function todayDate () {
    const now = new Date()
    const offsetMs = now.getTimezoneOffset() * 60_000
    return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10)
  }

  const newDoc = reactive({
    source_id: '',
    title: '',
    source: '',
    published_date: todayDate(),
    audience: '',
    topic: '',
    content: '',
  })

  localStorage.setItem('conversationId', conversationId.value)

  function setStatus (text: string) {
    status.value = text
  }

  function embeddingSummary (embedding?: Embedding) {
    if (!embedding?.dimension) return 'Embedding：無資料'
    const suffix = embedding.dimension > embedding.preview.length ? ', ...' : ''
    return `Embedding：${embedding.dimension} 維 · [${embedding.preview.join(', ')}${suffix}]`
  }

  function previewText (text: string, maxLength = 320) {
    const normalized = String(text || '').replace(/\s+/g, ' ').trim()
    if (!normalized) return '沒有內容摘要'
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
  }

  async function loadDocs () {
    setStatus('載入資料中')
    docsLoading.value = true
    try {
      const data = await api<{ documents: DocumentItem[] }>('/api/documents')
      docs.value = data.documents
      setStatus(`共有 ${docGroups.value.length} 份文件、${data.documents.length} 個 chunks`)
    } finally {
      docsLoading.value = false
    }
  }

  function chunkIndexOf (doc: DocumentItem) {
    return Number(doc.chunk_index || 1)
  }

  function insertChunkByIndex (sortedChunks: DocumentItem[], chunk: DocumentItem) {
    const insertAt = sortedChunks.findIndex(item => chunkIndexOf(chunk) < chunkIndexOf(item))
    if (insertAt === -1) return [...sortedChunks, chunk]
    return [
      ...sortedChunks.slice(0, insertAt),
      chunk,
      ...sortedChunks.slice(insertAt),
    ]
  }

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

  async function deleteDoc (documentId: string) {
    if (deletingDocumentId.value) return
    if (!confirm('確定要刪除整份文件與所有 chunks？')) return
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

  function addMessage (
    role: 'user' | 'assistant',
    text: string,
    references: ReferenceItem[] = [],
    thinking = false,
    evidenceAssessment: EvidenceAssessment | null = null,
    retrievalTerms: string[] = [],
    riskAssessment: RiskAssessment | null = null,
  ) {
    const message: ChatMessage = {
      id: nextMessageId++,
      role,
      text,
      references,
      evidenceAssessment,
      retrievalTerms,
      thinking,
      riskAssessment,
    }
    messages.value.push(message)
    scrollChat()
    return message
  }

  function scrollChat () {
    nextTick(() => {
      if (chatLogEl.value) {
        chatLogEl.value.scrollTop = chatLogEl.value.scrollHeight
      }
    })
  }

  const currentConvoTitle = computed(() => {
    const found = conversations.value.find(c => c.id === conversationId.value)
    return found?.title || '新對話'
  })

  const canInferMetadata = computed(() => Boolean(newDoc.content.trim() || selectedFiles.value.length > 0))

  function openDocsDialog () {
    loadDocs()
    docsDialogEl.value?.showModal()
  }

  function closeDocsDialog () {
    docsDialogEl.value?.close()
  }

  function openDocDialog () {
    editingDocumentId.value = ''
    resetDocForm()
    docDialogEl.value?.showModal()
  }

  function editDoc (group: DocumentGroup) {
    editingDocumentId.value = group.document_id
    newDoc.source_id = String(group.source_id || '')
    newDoc.title = group.title === '(未命名)' ? '' : group.title
    newDoc.source = group.source
    newDoc.published_date = group.published_date || todayDate()
    newDoc.audience = group.audience
    newDoc.topic = group.topic
    newDoc.content = group.content
    selectedFiles.value = []
    if (fileInputEl.value) fileInputEl.value.value = ''
    docDialogEl.value?.showModal()
  }

  function closeDocDialog () {
    if (addingDoc.value) return
    docDialogEl.value?.close()
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
    if (fileInputEl.value) fileInputEl.value.value = ''
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
    for (const file of selectedFiles.value) payload.append('file', file)
    return payload
  }

  function applyMetadataSuggestions (metadata: MetadataSuggestions) {
    if (metadata.title) newDoc.title = metadata.title
    if (metadata.published_date) newDoc.published_date = metadata.published_date
    if (metadata.audience) newDoc.audience = metadata.audience
    if (metadata.topic) newDoc.topic = metadata.topic
  }

  async function inferMetadata () {
    if (inferringMetadata.value || !canInferMetadata.value) return
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

  async function addDocument () {
    if (addingDoc.value) return
    if (!newDoc.content && selectedFiles.value.length === 0) {
      alert('請輸入內容，或上傳 TXT / PDF 衛教檔案。')
      return
    }

    const payload = buildDocumentPayload()

    addingDoc.value = true
    try {
      const isEditing = Boolean(editingDocumentId.value)
      setStatus(isEditing ? '更新資料並重新 embedding' : '新增資料並產生 embedding')
      const path = isEditing ? `/api/documents/${encodeURIComponent(editingDocumentId.value)}` : '/api/documents'
      const data = await api<{ documents?: DocumentItem[] }>(path, { method: isEditing ? 'PUT' : 'POST', body: payload })
      resetDocForm()
      if (data.documents) {
        docs.value = data.documents
        setStatus(`共有 ${docGroups.value.length} 份文件、${data.documents.length} 個 chunks`)
      } else {
        await loadDocs()
      }
      docDialogEl.value?.close()
      setStatus(isEditing ? '已更新並重新 embedding' : '已新增資料')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
      alert(message)
    } finally {
      addingDoc.value = false
    }
  }

  function openReferenceDialog (refItem: ReferenceItem) {
    activeReference.value = refItem
    nextTick(() => referenceDialogEl.value?.show())
  }

  function closeReferenceDialog () {
    referenceDialogEl.value?.close()
  }

  async function askQuestion () {
    const trimmedQuestion = question.value.trim()
    if (!trimmedQuestion) return

    const useRag = ragEnabled.value
    addMessage('user', `${trimmedQuestion}\n\n模式：${useRag ? 'RAG 開啟' : 'RAG 關閉'}`)
    const thinkingMessage = addMessage('assistant', '', [], true)
    question.value = ''
    setStatus(useRag ? '搜尋參考並詢問 GPT' : '直接詢問 GPT')

    try {
      const data = await api<AskResponse>('/api/ask', {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: conversationId.value,
          question: trimmedQuestion,
          rag_enabled: useRag,
        }),
      })
      messages.value = messages.value.filter(message => message.id !== thinkingMessage.id)
      addMessage(
        'assistant',
        data.answer,
        data.references || [],
        false,
        data.evidence_assessment || null,
        data.retrieval_terms || [],
        data.risk_assessment || null,
      )
      if (data.risk_assessment?.diverted) {
        setStatus(`急症分流：${data.risk_assessment.reason}`)
      } else if (data.rag_enabled) {
        const riskLabel = data.risk_assessment ? `風險=${data.risk_assessment.label}` : '風險=一般'
        const referenceLabel = data.references.length > 0 ? `使用 ${data.references.length} 筆參考` : '未使用參考索引'
        const evidenceLabel = data.evidence_assessment?.sufficient ? '證據充足' : '證據不足'
        const retrievalTerms = data.retrieval_terms || []
        const retrievalLabel = retrievalTerms.length > 0 ? `檢索詞=${retrievalTerms.length} 組` : '檢索詞=無'
        setStatus(`${riskLabel} · ${referenceLabel} · ${evidenceLabel} · ${retrievalLabel}`)
      } else {
        setStatus('RAG 關閉，未搜尋向量資料庫')
      }
      loadConversations()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      thinkingMessage.thinking = false
      thinkingMessage.text = `發生錯誤：${message}`
      setStatus(message)
    }
  }

  function handleQuestionKeydown (event: KeyboardEvent) {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
    event.preventDefault()
    askQuestion()
  }

  async function loadConversationHistory () {
    try {
      const data = await api<{ messages: { role: string, content: string }[] }>(
        `/api/conversations/${encodeURIComponent(conversationId.value)}`,
      )
      for (const msg of data.messages) {
        if (msg.role === 'user' || msg.role === 'assistant') {
          addMessage(msg.role as 'user' | 'assistant', msg.content)
        }
      }
      if (data.messages.length > 0) {
        setStatus(`已還原 ${data.messages.length} 則對話記錄`)
      }
    } catch {
      // 歷史載入失敗不中斷，靜默忽略
    }
  }

  async function loadConversations () {
    try {
      const data = await api<{ conversations: ConversationItem[] }>('/api/conversations')
      conversations.value = data.conversations
    } catch {
      // 對話列表載入失敗，靜默忽略
    }
  }

  async function createNewConversation () {
    const newId = crypto.randomUUID()
    conversationId.value = newId
    localStorage.setItem('conversationId', newId)
    messages.value = []
    setStatus('新對話已建立')
  }

  async function switchConversation (id: string) {
    if (id === conversationId.value) return
    conversationId.value = id
    localStorage.setItem('conversationId', id)
    messages.value = []
    await loadConversationHistory()
  }

  async function deleteConversation (id: string) {
    const convo = conversations.value.find(c => c.id === id)
    pendingDeleteId.value = id
    pendingDeleteTitle.value = convo?.title || '此對話'
    deleteConvoDialogEl.value?.showModal()
  }

  function cancelDeleteConversation () {
    deleteConvoDialogEl.value?.close()
    pendingDeleteId.value = null
  }

  async function confirmDeleteConversation () {
    const id = pendingDeleteId.value
    if (!id) return
    deletingConvoId.value = id
    try {
      await api(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
      deleteConvoDialogEl.value?.close()
      pendingDeleteId.value = null
      if (id === conversationId.value) {
        const newId = crypto.randomUUID()
        conversationId.value = newId
        localStorage.setItem('conversationId', newId)
        messages.value = []
        setStatus('對話已刪除，已開新對話')
      }
      await loadConversations()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
    } finally {
      deletingConvoId.value = null
    }
  }

  async function clearChat () {
    await api(`/api/conversations/${encodeURIComponent(conversationId.value)}`, { method: 'DELETE' })
    const newId = crypto.randomUUID()
    conversationId.value = newId
    localStorage.setItem('conversationId', newId)
    messages.value = []
    setStatus('已清除對話記憶')
    loadConversations()
  }

  onMounted(() => {
    loadDocs().catch(error => {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
    })
    loadConversations()
    loadConversationHistory()
  })
</script>

<style scoped>
  .page {
    min-height: 100vh;
    background: #f6f7f8;
    color: #17202a;
  }

  .app-header {
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 0 24px;
    border-bottom: 1px solid #d9dee5;
    background: #ffffff;
  }

  h1 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
  }

  .layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 18px;
    padding: 18px;
    height: calc(100vh - 60px);
    min-height: 680px;
  }

  .panel {
    min-height: 0;
    background: #ffffff;
    border: 1px solid #d9dee5;
    border-radius: 8px;
    box-shadow: 0 10px 28px rgba(16, 24, 40, 0.08);
    display: flex;
    flex-direction: column;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 14px 16px;
    border-bottom: 1px solid #d9dee5;
  }

  .toolbar h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  button {
    height: 36px;
    border: 1px solid #d9dee5;
    border-radius: 6px;
    background: #ffffff;
    color: #17202a;
    padding: 0 12px;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  button.primary {
    border-color: #0f766e;
    background: #0f766e;
    color: #ffffff;
  }

  button.primary:hover { background: #0b5f59; }
  button.danger { color: #b42318; border-color: #f1b7b2; }
  button:disabled { opacity: 0.55; cursor: not-allowed; }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.45);
    border-top-color: #ffffff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    display: none;
    flex: 0 0 auto;
  }

  .spinner.inline {
    display: inline-block;
    border-color: rgba(15, 118, 110, 0.22);
    border-top-color: #0f766e;
  }

  button.loading .spinner { display: inline-block; }

  button.danger .spinner {
    border-color: rgba(180, 35, 24, 0.25);
    border-top-color: #b42318;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .status {
    color: #687381;
    font-size: 13px;
    min-width: 180px;
    text-align: right;
  }

  .content {
    min-height: 0;
    overflow: auto;
    padding: 14px 16px;
  }

  .doc-list {
    display: grid;
    gap: 10px;
  }

  .docs-dialog {
    width: min(1040px, calc(100vw - 32px));
    max-height: min(88vh, 860px);
    flex-direction: column;
  }

  .docs-dialog[open] {
    display: flex;
  }

  .docs-dialog-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 16px;
    background: #f6f7f8;
    display: grid;
    gap: 10px;
    align-content: start;
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .chat-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: #17202a;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    max-width: 400px;
  }

  .list-loading {
    min-height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: #687381;
    font-size: 14px;
    border: 1px dashed #d9dee5;
    border-radius: 8px;
    background: #fbfcfd;
  }

  .doc-tools {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 12px;
    padding: 12px;
    border: 1px solid #d9dee5;
    border-radius: 8px;
    background: #ffffff;
  }

  .doc-tools label {
    width: min(260px, 100%);
  }

  .doc-count {
    color: #51606d;
    font-size: 13px;
    font-weight: 700;
  }

  .doc-section {
    display: grid;
    gap: 10px;
  }

  .doc-section h3 {
    margin: 6px 0 0;
    color: #51606d;
    font-size: 13px;
    font-weight: 700;
  }

  .doc {
    border: 1px solid #d9dee5;
    border-radius: 8px;
    padding: 12px;
    background: #ffffff;
  }

  .doc-head {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: flex-start;
    margin-bottom: 8px;
  }

  .doc-actions {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .doc-title {
    font-weight: 700;
    font-size: 14px;
    line-height: 1.4;
    overflow-wrap: anywhere;
  }

  .doc-meta {
    color: #687381;
    font-size: 12px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .doc-content {
    margin-top: 8px;
    color: #2f3a46;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .doc-preview {
    margin: 8px 0 0;
    color: #2f3a46;
    font-size: 13px;
    line-height: 1.55;
    overflow-wrap: anywhere;
  }

  .doc-details {
    margin-top: 8px;
    border-top: 1px solid #eef1f4;
    padding-top: 8px;
    color: #51606d;
    font-size: 12px;
  }

  .doc-details summary {
    width: fit-content;
    cursor: pointer;
    color: #0b5f59;
    font-weight: 700;
  }

  .doc-details.nested {
    border-top: 0;
    padding-top: 4px;
  }

  .chunk-card {
    margin-top: 10px;
    padding: 10px;
    border: 1px solid #d9dee5;
    border-radius: 6px;
    background: #fbfcfd;
  }

  .embedding {
    margin-top: 10px;
    border-top: 1px solid #d9dee5;
    padding-top: 8px;
    color: #687381;
    font-size: 12px;
  }

  .embedding.nested {
    border-top: 0;
    margin-top: 8px;
    padding-top: 0;
  }

  .embedding summary {
    cursor: pointer;
    overflow-wrap: anywhere;
  }

  .embedding pre {
    max-height: 180px;
    overflow: auto;
    margin: 8px 0 0;
    padding: 10px;
    border-radius: 6px;
    background: #f4f6f8;
    color: #26323f;
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  form {
    display: grid;
    gap: 10px;
    padding: 14px 16px;
    border-top: 1px solid #d9dee5;
    background: #fbfcfd;
  }

  dialog {
    width: min(620px, calc(100vw - 32px));
    border: 1px solid #d9dee5;
    border-radius: 8px;
    padding: 0;
    background: #ffffff;
    color: #17202a;
    box-shadow: 0 24px 70px rgba(16, 24, 40, 0.24);
    overflow: hidden;
  }

  dialog:not([open]) {
    display: none;
  }

  dialog::backdrop {
    background: rgba(23, 32, 42, 0.42);
  }

  .dialog-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px;
    border-bottom: 1px solid #d9dee5;
    background: #ffffff;
    color: #17202a;
  }

  .dialog-head h2 {
    margin: 0;
    font-size: 16px;
  }

  .dialog-form {
    border-top: 0;
    background: #ffffff;
  }

  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding-top: 4px;
  }

  .metadata-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding-top: 2px;
  }

  .metadata-actions .spinner {
    border-color: rgba(15, 118, 110, 0.22);
    border-top-color: #0f766e;
  }

  label {
    display: grid;
    gap: 5px;
    color: #687381;
    font-size: 12px;
    font-weight: 700;
  }

  input, textarea, select {
    width: 100%;
    border: 1px solid #d9dee5;
    border-radius: 6px;
    background: #ffffff;
    color: #17202a;
    padding: 9px 10px;
    font: inherit;
    font-size: 14px;
    resize: vertical;
    letter-spacing: 0;
  }

  input[type="file"] {
    padding: 7px 10px;
    background: #fbfcfd;
  }

  .hint {
    color: #687381;
    font-size: 12px;
    line-height: 1.5;
    font-weight: 400;
  }

  textarea { min-height: 96px; }
  .two { display: grid; grid-template-columns: 120px 1fr; gap: 10px; }

  .chat-log {
    min-height: 0;
    flex: 1;
    overflow: auto;
    padding: 16px;
    display: grid;
    align-content: start;
    gap: 12px;
  }

  .confirm-dialog {
    width: min(380px, calc(100vw - 32px));
  }

  .confirm-body {
    padding: 16px 16px 14px;
    display: grid;
    gap: 14px;
    background: #ffffff;
  }

  .confirm-body p {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: #17202a;
  }

  .ask-form {
    grid-template-columns: 1fr auto;
    align-items: end;
  }

  .ask-form label { grid-column: 1; }
  .ask-form button { grid-column: 2; height: 42px; min-width: 88px; }
  .ask-form textarea { min-height: 42px; max-height: 150px; }

  .rag-control {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 12px;
    padding: 9px 10px;
    border: 1px solid #d9dee5;
    border-radius: 6px;
    background: #ffffff;
  }

  .rag-control span {
    color: #17202a;
    font-size: 13px;
    font-weight: 700;
  }

  .rag-control input {
    appearance: none;
    width: 50px;
    height: 28px;
    padding: 0;
    margin: 0 0 0 4px;
    flex: 0 0 auto;
    border: 2px solid #4093e8;
    border-radius: 999px;
    background: #ffffff;
    cursor: pointer;
    position: relative;
    transition: background 0.18s ease, border-color 0.18s ease;
  }

  .rag-control input::before {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #4093e8;
    transition: transform 0.18s ease, background 0.18s ease;
  }

  .rag-control input:checked {
    background: #4093e8;
    border-color: #4093e8;
  }

  .rag-control input:checked::before {
    background: #ffffff;
    transform: translateX(22px);
  }

  .rag-control input:focus-visible {
    outline: 3px solid rgba(64, 147, 232, 0.25);
    outline-offset: 2px;
  }

  @media (max-width: 720px) {
    .layout {
      height: auto;
      min-height: auto;
      grid-template-columns: 1fr;
    }

    .panel { min-height: 560px; }
    .two { grid-template-columns: 1fr; }
    .ask-form { grid-template-columns: 1fr; }
    .ask-form button { grid-column: 1; width: 100%; }
    .status { text-align: left; min-width: 0; }
    .app-header { align-items: flex-start; height: auto; padding: 14px 16px; flex-direction: column; }
  }
</style>
