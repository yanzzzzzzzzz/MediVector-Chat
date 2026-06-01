<template>
  <div class="page">
    <header class="app-header">
      <h1>Vector DB 中文問答</h1>
      <div class="status">{{ status }}</div>
    </header>

    <main class="layout">
      <aside class="convo-sidebar">
        <div class="convo-sidebar-head">
          <span class="convo-sidebar-title">我的對話</span>

          <button class="primary convo-new-btn" type="button" @click="createNewConversation">
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
            新對話
          </button>
        </div>

        <div class="convo-list">
          <div v-if="conversations.length === 0" class="convo-empty">尚無對話記錄</div>

          <div
            v-for="convo in conversations"
            :key="convo.id"
            :class="['convo-row', { active: convo.id === conversationId }]"
          >
            <button
              :class="['convo-item', { active: convo.id === conversationId }]"
              type="button"
              @click="switchConversation(convo.id)"
            >
              <span class="convo-item-title">{{ convo.title }}</span>
              <span class="convo-item-time">{{ formatConvoTime(convo.created_at) }}</span>
            </button>

            <button
              class="convo-delete-btn"
              :disabled="deletingConvoId === convo.id"
              :title="'刪除對話'"
              type="button"
              @click.stop="deleteConversation(convo.id)"
            >
              <svg
                fill="none"
                height="13"
                stroke="currentColor"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                viewBox="0 0 24 24"
                width="13"
                xmlns="http://www.w3.org/2000/svg"
              ><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
            </button>
          </div>
        </div>

        <div class="sidebar-footer">
          <button class="sidebar-docs-btn" type="button" @click="openDocsDialog">
            <svg
              fill="none"
              height="15"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              viewBox="0 0 24 24"
              width="15"
              xmlns="http://www.w3.org/2000/svg"
            ><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
            衛教資料庫
          </button>
        </div>
      </aside>

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
          <div
            v-for="message in messages"
            :key="message.id"
            :class="['msg', message.role, { thinking: message.thinking }]"
          >
            <template v-if="message.thinking">
              <span aria-hidden="true" class="spinner inline" />
              <span>思考中</span>
            </template>

            <template v-else-if="message.role === 'assistant' && message.references.length > 0">
              <template v-for="(part, index) in answerParts(message)" :key="index">
                <button v-if="part.ref" class="citation" type="button" @click="openReferenceDialog(part.ref)">
                  [{{ part.ref.index }}]
                </button>

                <template v-else>{{ part.text }}</template>
              </template>
            </template>

            <template v-else>{{ message.text }}</template>

            <div v-if="message.role === 'assistant' && message.evidenceAssessment" class="evidence-wrap">
              <span
                :class="['evidence-badge', message.evidenceAssessment.sufficient ? 'evidence-sufficient' : 'evidence-insufficient']"
              >
                證據{{ message.evidenceAssessment.sufficient ? '充足' : '不足' }}
              </span>

              <div class="evidence-detail">{{ message.evidenceAssessment.reason }}</div>
            </div>

            <div v-if="message.role === 'assistant' && message.retrievalTerms && message.retrievalTerms.length > 0" class="retrieval-wrap">
              <div class="retrieval-title">本次檢索詞</div>

              <div class="retrieval-tags">
                <span v-for="term in message.retrievalTerms" :key="term" class="retrieval-tag">{{ term }}</span>
              </div>
            </div>

            <div v-if="message.role === 'assistant' && message.riskAssessment" class="risk-wrap">
              <span :class="['risk-badge', `risk-${message.riskAssessment.level}`]">
                風險分級：{{ message.riskAssessment.label }}
              </span>

              <div class="risk-detail">{{ message.riskAssessment.reason }}</div>
            </div>

            <div v-if="message.references.length > 0" class="refs">
              <div v-for="sourceRef in message.references" :key="sourceRef.index">
                [{{ sourceRef.index }}] {{ sourceRef.source }} · {{ sourceRef.title }} · distance={{ sourceRef.distance_text }}
              </div>

              <div v-if="message.evidenceAssessment" class="refs-evidence">
                證據狀態：{{ message.evidenceAssessment.sufficient ? '充足' : '不足' }} · {{ message.evidenceAssessment.reason }}
              </div>

              <div v-if="message.retrievalTerms && message.retrievalTerms.length > 0" class="refs-retrieval">
                檢索詞：{{ message.retrievalTerms.join(' · ') }}
              </div>
            </div>
          </div>
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

        <div v-else-if="docs.length === 0" class="doc">
          <div class="doc-title">目前沒有衛教資料</div>
          <div class="doc-meta">按「新增資料」建立第一筆向量資料。</div>
        </div>

        <template v-else>
          <article v-for="doc in docs" :key="doc.uuid" class="doc">
            <div class="doc-head">
              <div>
                <div class="doc-title">{{ doc.title || '(未命名)' }}</div>
                <div class="doc-meta">source_id={{ doc.source_id }} · {{ doc.source || '' }}</div>

                <div v-if="Number(doc.chunk_count || 1) > 1" class="doc-meta">
                  chunk={{ doc.chunk_index || 1 }} / {{ doc.chunk_count || 1 }}
                </div>

                <div v-if="doc.file_name" class="doc-meta">
                  file={{ doc.file_name }} · {{ doc.file_bucket || '' }}/{{ doc.file_object_key || '' }}
                </div>

                <div class="doc-meta">created={{ doc.created_at || '未知' }}</div>
                <div class="doc-meta">uuid={{ doc.uuid }}</div>
              </div>

              <button
                class="danger"
                :class="{ loading: deletingUuid === doc.uuid }"
                :disabled="Boolean(deletingUuid)"
                type="button"
                @click="deleteDoc(doc.uuid)"
              >
                <span aria-hidden="true" class="spinner" />
                <span>{{ deletingUuid === doc.uuid ? '刪除中' : '刪除' }}</span>
              </button>
            </div>

            <div class="doc-content">{{ doc.content || '' }}</div>

            <details class="embedding">
              <summary>{{ embeddingSummary(doc.embedding) }}</summary>
              <pre v-if="doc.embedding?.dimension">{{ JSON.stringify(doc.embedding.values, null, 2) }}</pre>
            </details>
          </article>
        </template>
      </div>
    </dialog>

    <dialog ref="docDialogEl">
      <div class="dialog-head">
        <h2>新增資料</h2>
        <button type="button" @click="closeDocDialog">關閉</button>
      </div>

      <form class="dialog-form" @submit.prevent="addDocument">
        <div class="two">
          <label>來源 ID
            <input v-model="newDoc.source_id" placeholder="自動產生" type="number">
          </label>

          <label>標題
            <input v-model.trim="newDoc.title" placeholder="例如：睡眠衛教重點" required>
          </label>
        </div>

        <label>來源
          <input v-model.trim="newDoc.source" placeholder="例如：內部測試資料 / sleep-guide" required>
        </label>

        <label>內容
          <textarea v-model.trim="newDoc.content" placeholder="輸入要放進 vector DB 的中文資料，或改以上傳檔案" />
        </label>

        <label>衛教檔案
          <input ref="fileInputEl" accept=".txt,.pdf,text/plain,application/pdf" type="file" @change="onFileChange">
          <span class="hint">可上傳 TXT 或 PDF；若同時填寫內容與上傳檔案，系統會合併後 embedding。</span>
        </label>

        <div class="dialog-actions">
          <button type="button" @click="closeDocDialog">取消</button>

          <button class="primary" :class="{ loading: addingDoc }" :disabled="addingDoc" type="submit">
            <span aria-hidden="true" class="spinner" />
            <span>{{ addingDoc ? 'Embedding 中' : '新增並 embedding' }}</span>
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

    <dialog ref="referenceDialogEl">
      <div class="dialog-head">
        <h2>{{ activeReference ? `[${activeReference.index}] ${activeReference.title || '參考資料'}` : '參考資料' }}</h2>
        <button type="button" @click="closeReferenceDialog">關閉</button>
      </div>

      <div v-if="activeReference" class="reference-body">
        <div class="reference-meta">
          來源：{{ activeReference.source || '未知' }} · source_id={{ activeReference.source_id ?? '未知' }} · distance={{ activeReference.distance_text || '未知' }}
        </div>

        <pre class="reference-content">{{ activeReference.content || '' }}</pre>
      </div>
    </dialog>
  </div>
</template>

<script setup lang="ts">
  import { computed, nextTick, onMounted, reactive, ref } from 'vue'

  interface Embedding {
    dimension: number
    preview: number[]
    values: number[]
  }

  interface DocumentItem {
    uuid: string
    source_id: number | string
    title: string
    source: string
    content: string
    file_name?: string | null
    file_object_key?: string | null
    file_bucket?: string | null
    file_content_type?: string | null
    file_size?: number | null
    chunk_index?: number | null
    chunk_count?: number | null
    created_at: string
    embedding?: Embedding
  }

  interface ReferenceItem {
    index: number
    uuid: string
    source_id: number
    title: string
    source: string
    content: string
    distance: number | null
    distance_text: string
  }

  interface RiskAssessment {
    level: 'green' | 'yellow' | 'red'
    label: string
    reason: string
    diverted: boolean
    action: string
  }

  interface EvidenceAssessment {
    sufficient: boolean
    reason: string
    reference_count: number
    best_distance: number | null
  }

  interface AskResponse {
    answer: string
    rag_enabled: boolean
    references: ReferenceItem[]
    evidence_assessment?: EvidenceAssessment
    retrieval_terms?: string[]
    risk_assessment?: RiskAssessment
  }

  interface ChatMessage {
    id: number
    role: 'user' | 'assistant'
    text: string
    references: ReferenceItem[]
    evidenceAssessment?: EvidenceAssessment | null
    retrievalTerms?: string[]
    riskAssessment?: RiskAssessment | null
    thinking?: boolean
  }

  interface AnswerPart {
    text?: string
    ref?: ReferenceItem
  }

  interface ConversationItem {
    id: string
    title: string
    created_at: string
  }

  const status = ref('準備中')
  const docs = ref<DocumentItem[]>([])
  const docsLoading = ref(false)
  const deletingUuid = ref('')
  const messages = ref<ChatMessage[]>([])
  const question = ref('')
  const ragEnabled = ref(true)
  const addingDoc = ref(false)
  const selectedFile = ref<File | null>(null)
  const activeReference = ref<ReferenceItem | null>(null)
  const conversations = ref<ConversationItem[]>([])
  const deletingConvoId = ref<string | null>(null)
  const chatLogEl = ref<HTMLDivElement | null>(null)
  const docDialogEl = ref<HTMLDialogElement | null>(null)
  const docsDialogEl = ref<HTMLDialogElement | null>(null)
  const referenceDialogEl = ref<HTMLDialogElement | null>(null)
  const deleteConvoDialogEl = ref<HTMLDialogElement | null>(null)
  const pendingDeleteId = ref<string | null>(null)
  const pendingDeleteTitle = ref('')
  const fileInputEl = ref<HTMLInputElement | null>(null)
  const conversationId = ref<string>(localStorage.getItem('conversationId') || crypto.randomUUID())
  let nextMessageId = 1

  const newDoc = reactive({
    source_id: '',
    title: '',
    source: '',
    content: '',
  })

  localStorage.setItem('conversationId', conversationId.value)

  function setStatus (text: string) {
    status.value = text
  }

  async function api<T> (path: string, options: RequestInit = {}): Promise<T> {
    const requestOptions: RequestInit = { ...options }
    if (!(options.body instanceof FormData)) {
      requestOptions.headers = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> | undefined),
      }
    }
    const response = await fetch(path, requestOptions)
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`)
    return body as T
  }

  function embeddingSummary (embedding?: Embedding) {
    if (!embedding?.dimension) return 'Embedding：無資料'
    const suffix = embedding.dimension > embedding.preview.length ? ', ...' : ''
    return `Embedding：${embedding.dimension} 維 · [${embedding.preview.join(', ')}${suffix}]`
  }

  async function loadDocs () {
    setStatus('載入資料中')
    docsLoading.value = true
    try {
      const data = await api<{ documents: DocumentItem[] }>('/api/documents')
      docs.value = data.documents
      setStatus(`共有 ${data.documents.length} 筆資料`)
    } finally {
      docsLoading.value = false
    }
  }

  async function deleteDoc (uuid: string) {
    if (deletingUuid.value) return
    if (!confirm('確定要刪除這筆 vector DB 資料？')) return
    deletingUuid.value = uuid
    try {
      setStatus('刪除中')
      await api(`/api/documents/${encodeURIComponent(uuid)}`, { method: 'DELETE' })
      await loadDocs()
      setStatus('已刪除')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
      alert(message)
    } finally {
      deletingUuid.value = ''
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

  function answerParts (message: ChatMessage): AnswerPart[] {
    const referencesByIndex = new Map(message.references.map(ref => [String(ref.index), ref]))
    const parts: AnswerPart[] = []
    const pattern = /\[(\d+)\]/g
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = pattern.exec(message.text)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ text: message.text.slice(lastIndex, match.index) })
      }
      const refItem = referencesByIndex.get(match[1])
      parts.push(refItem ? { ref: refItem } : { text: match[0] })
      lastIndex = pattern.lastIndex
    }

    if (lastIndex < message.text.length) {
      parts.push({ text: message.text.slice(lastIndex) })
    }
    return parts
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

  function openDocsDialog () {
    loadDocs()
    docsDialogEl.value?.showModal()
  }

  function closeDocsDialog () {
    docsDialogEl.value?.close()
  }

  function openDocDialog () {
    docDialogEl.value?.showModal()
  }

  function closeDocDialog () {
    if (addingDoc.value) return
    docDialogEl.value?.close()
  }

  function onFileChange (event: Event) {
    const input = event.target as HTMLInputElement
    selectedFile.value = input.files?.[0] || null
  }

  function resetDocForm () {
    newDoc.source_id = ''
    newDoc.title = ''
    newDoc.source = ''
    newDoc.content = ''
    selectedFile.value = null
    if (fileInputEl.value) fileInputEl.value.value = ''
  }

  async function addDocument () {
    if (addingDoc.value) return
    if (!newDoc.content && !selectedFile.value) {
      alert('請輸入內容，或上傳 TXT / PDF 衛教檔案。')
      return
    }

    const payload = new FormData()
    payload.append('source_id', newDoc.source_id || '')
    payload.append('title', newDoc.title.trim())
    payload.append('source', newDoc.source.trim())
    payload.append('content', newDoc.content.trim())
    if (selectedFile.value) payload.append('file', selectedFile.value)

    addingDoc.value = true
    try {
      setStatus('新增資料並產生 embedding')
      const data = await api<{ documents?: DocumentItem[] }>('/api/documents', { method: 'POST', body: payload })
      resetDocForm()
      if (data.documents) {
        docs.value = data.documents
        setStatus(`共有 ${data.documents.length} 筆資料`)
      } else {
        await loadDocs()
      }
      docDialogEl.value?.close()
      setStatus('已新增資料')
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
    nextTick(() => referenceDialogEl.value?.showModal())
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

  function formatConvoTime (isoString: string): string {
    const d = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffDays = Math.floor(diffMs / 86_400_000)
    if (diffDays === 0) return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
    if (diffDays === 1) return '昨天'
    if (diffDays < 7) return `${diffDays} 天前`
    return d.toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' })
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

  .convo-sidebar {
    display: flex;
    flex-direction: column;
    background: #ffffff;
    border: 1px solid #d9dee5;
    border-radius: 8px;
    box-shadow: 0 10px 28px rgba(16, 24, 40, 0.08);
    min-height: 0;
    overflow: hidden;
  }

  .convo-sidebar-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 12px 12px;
    border-bottom: 1px solid #d9dee5;
    flex-shrink: 0;
  }

  .convo-sidebar-title {
    font-size: 13px;
    font-weight: 700;
    color: #17202a;
  }

  .convo-new-btn {
    height: 30px;
    padding: 0 10px;
    font-size: 12px;
    gap: 4px;
  }

  .convo-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .sidebar-footer {
    flex-shrink: 0;
    padding: 8px 10px;
    border-top: 1px solid #d9dee5;
  }

  .sidebar-docs-btn {
    width: 100%;
    height: 36px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px;
    font-size: 13px;
    font-weight: 500;
    color: #454e59;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.12s ease, border-color 0.12s ease;
  }

  .sidebar-docs-btn:hover {
    background: #f0f4f8;
    border-color: #d9dee5;
  }

  .convo-empty {
    padding: 20px 10px;
    text-align: center;
    color: #687381;
    font-size: 13px;
  }

  .convo-item {
    flex: 1;
    min-width: 0;
    height: auto;
    min-height: 52px;
    padding: 8px 10px;
    border: 1px solid transparent;
    border-right: none;
    border-radius: 6px 0 0 6px;
    background: transparent;
    text-align: left;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 3px;
    cursor: pointer;
    transition: background 0.12s ease, border-color 0.12s ease;
  }

  .convo-row {
    display: flex;
    align-items: stretch;
    border: 1px solid transparent;
    border-radius: 6px;
    transition: border-color 0.12s ease;
  }

  .convo-row:hover {
    border-color: #d9dee5;
  }

  .convo-row.active {
    border-color: #b8ddd7;
  }

  .convo-row:hover .convo-item,
  .convo-row:hover .convo-delete-btn {
    background: #f6f7f8;
  }

  .convo-row.active .convo-item,
  .convo-row.active .convo-delete-btn {
    background: #eef7f5;
  }

  .convo-delete-btn {
    flex: 0 0 auto;
    width: 32px;
    padding: 0;
    border: none;
    border-left: 1px solid rgba(0,0,0,0.06);
    border-radius: 0 6px 6px 0;
    margin: 0;
    background: transparent;
    color: #a0aab4;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.12s ease, color 0.12s ease, background 0.12s ease;
  }

  .convo-row:hover .convo-delete-btn {
    opacity: 1;
  }

  .convo-delete-btn:hover {
    color: #b42318 !important;
    background: #fff1ef !important;
  }

  .convo-delete-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .convo-item-title {
    font-size: 13px;
    font-weight: 500;
    color: #17202a;
    line-height: 1.4;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    word-break: break-all;
  }

  .convo-item.active .convo-item-title {
    color: #0b5f59;
  }

  .convo-item-time {
    font-size: 11px;
    color: #a0aab4;
    line-height: 1;
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
    width: min(860px, calc(100vw - 32px));
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

  .embedding {
    margin-top: 10px;
    border-top: 1px solid #d9dee5;
    padding-top: 8px;
    color: #687381;
    font-size: 12px;
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

  label {
    display: grid;
    gap: 5px;
    color: #687381;
    font-size: 12px;
    font-weight: 700;
  }

  input, textarea {
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

  .msg {
    max-width: 88%;
    border: 1px solid #d9dee5;
    border-radius: 8px;
    padding: 10px 12px;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font-size: 14px;
    background: #ffffff;
  }

  .msg.user {
    justify-self: end;
    background: #eef7f5;
    border-color: #b8ddd7;
  }

  .msg.assistant { justify-self: start; }

  .msg.thinking {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #687381;
  }

  .refs {
    margin-top: 10px;
    display: grid;
    gap: 8px;
    color: #687381;
    font-size: 12px;
  }

  .refs-evidence {
    padding-top: 2px;
    color: #51606d;
    font-size: 12px;
    line-height: 1.5;
  }

  .refs-retrieval {
    color: #51606d;
    font-size: 12px;
    line-height: 1.5;
  }

  .evidence-wrap {
    margin-top: 10px;
    display: grid;
    gap: 6px;
  }

  .evidence-badge {
    width: fit-content;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid transparent;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.4;
  }

  .evidence-sufficient {
    background: #eef7f5;
    color: #0b5f59;
    border-color: #b8ddd7;
  }

  .evidence-insufficient {
    background: #fff8e8;
    color: #8a5a00;
    border-color: #f7d186;
  }

  .evidence-detail {
    color: #687381;
    font-size: 12px;
    line-height: 1.5;
  }

  .retrieval-wrap {
    margin-top: 10px;
    display: grid;
    gap: 6px;
  }

  .retrieval-title {
    color: #51606d;
    font-size: 12px;
    font-weight: 700;
  }

  .retrieval-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .retrieval-tag {
    padding: 2px 8px;
    border: 1px solid #d9dee5;
    border-radius: 999px;
    background: #fbfcfd;
    color: #51606d;
    font-size: 12px;
    line-height: 1.4;
  }

  .risk-wrap {
    margin-top: 10px;
    display: grid;
    gap: 6px;
  }

  .risk-badge {
    width: fit-content;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid transparent;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.4;
  }

  .risk-green {
    background: #eef7f5;
    color: #0b5f59;
    border-color: #b8ddd7;
  }

  .risk-yellow {
    background: #fff8e8;
    color: #8a5a00;
    border-color: #f7d186;
  }

  .risk-red {
    background: #fff1ef;
    color: #b42318;
    border-color: #f5b3ad;
  }

  .risk-detail {
    color: #687381;
    font-size: 12px;
    line-height: 1.5;
  }

  .citation {
    height: auto;
    min-width: 28px;
    padding: 1px 6px;
    margin: 0 2px;
    border-color: #b8ddd7;
    background: #eef7f5;
    color: #0b5f59;
    font-size: 12px;
    vertical-align: baseline;
    display: inline-flex;
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

  .reference-body {
    padding: 14px 16px;
    display: grid;
    gap: 10px;
    background: #ffffff;
  }

  .reference-meta {
    color: #687381;
    font-size: 12px;
    line-height: 1.6;
    overflow-wrap: anywhere;
  }

  .reference-content {
    max-height: 48vh;
    overflow: auto;
    margin: 0;
    padding: 12px;
    border-radius: 6px;
    border: 1px solid #d9dee5;
    background: #fbfcfd;
    color: #26323f;
    font: inherit;
    font-size: 14px;
    line-height: 1.7;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
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

    .convo-sidebar {
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      gap: 0;
      min-height: auto;
      border-radius: 8px;
    }

    .convo-sidebar-head { width: 100%; border-bottom: 1px solid #d9dee5; border-right: none; }

    .convo-list {
      display: flex;
      flex-direction: row;
      flex-wrap: nowrap;
      overflow-x: auto;
      padding: 8px;
      gap: 6px;
    }

    .convo-item {
      height: auto;
      min-width: 120px;
      max-width: 180px;
      flex: 0 0 auto;
      padding: 6px 10px;
      text-align: left;
    }

    .convo-item-time { display: none; }

    .panel { min-height: 560px; }
    .two { grid-template-columns: 1fr; }
    .ask-form { grid-template-columns: 1fr; }
    .ask-form button { grid-column: 1; width: 100%; }
    .status { text-align: left; min-width: 0; }
    .app-header { align-items: flex-start; height: auto; padding: 14px 16px; flex-direction: column; }
  }
</style>
