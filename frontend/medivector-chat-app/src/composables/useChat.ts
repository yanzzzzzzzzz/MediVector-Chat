import type { AskResponse, ChatMessage, ConversationItem, ConversationMessageItem, EvidenceAssessment, ReferenceItem, RiskAssessment } from '@/types'
import { computed, nextTick, ref, type Ref } from 'vue'
import { api } from '@/composables/useApi'

type SetStatus = (text: string) => void

export function useChat (setStatus: SetStatus, chatLogEl: Ref<HTMLDivElement | null>) {
  const messages = ref<ChatMessage[]>([])
  const question = ref('')
  const ragEnabled = ref(true)
  const conversations = ref<ConversationItem[]>([])
  const deletingConvoId = ref<string | null>(null)
  const pendingDeleteId = ref<string | null>(null)
  const pendingDeleteTitle = ref('')
  const conversationId = ref<string>(localStorage.getItem('conversationId') || crypto.randomUUID())
  let nextMessageId = 1

  localStorage.setItem('conversationId', conversationId.value)

  const currentConvoTitle = computed(() => {
    const found = conversations.value.find(c => c.id === conversationId.value)
    return found?.title || '新對話'
  })

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

  async function askQuestion () {
    const trimmedQuestion = question.value.trim()
    if (!trimmedQuestion) {
      return
    }

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
      updateAskStatus(data)
      loadConversations()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      thinkingMessage.thinking = false
      thinkingMessage.text = `發生錯誤：${message}`
      setStatus(message)
    }
  }

  function updateAskStatus (data: AskResponse) {
    if (data.risk_assessment?.diverted) {
      setStatus(`急症分流：${data.risk_assessment.reason}`)
      return
    }
    if (!data.rag_enabled) {
      setStatus('RAG 關閉，未搜尋向量資料庫')
      return
    }

    const riskLabel = data.risk_assessment ? `風險=${data.risk_assessment.label}` : '風險=一般'
    const referenceLabel = data.references.length > 0 ? `使用 ${data.references.length} 筆參考` : '未使用參考索引'
    const evidenceLabel = data.evidence_assessment?.sufficient ? '證據充足' : '證據不足'
    const retrievalTerms = data.retrieval_terms || []
    const retrievalLabel = retrievalTerms.length > 0 ? `檢索詞=${retrievalTerms.length} 組` : '檢索詞=無'
    setStatus(`${riskLabel} · ${referenceLabel} · ${evidenceLabel} · ${retrievalLabel}`)
  }

  function handleQuestionKeydown (event: KeyboardEvent) {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
      return
    }
    event.preventDefault()
    askQuestion()
  }

  async function loadConversationHistory () {
    try {
      const data = await api<{ messages: ConversationMessageItem[] }>(
        `/api/conversations/${encodeURIComponent(conversationId.value)}`,
      )
      for (const msg of data.messages) {
        if (msg.role === 'user' || msg.role === 'assistant') {
          addMessage(
            msg.role,
            msg.content,
            msg.references || [],
            false,
            msg.evidence_assessment || null,
            msg.retrieval_terms || [],
            msg.risk_assessment || null,
          )
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
    if (id === conversationId.value) {
      return
    }
    conversationId.value = id
    localStorage.setItem('conversationId', id)
    messages.value = []
    await loadConversationHistory()
  }

  function requestDeleteConversation (id: string) {
    const convo = conversations.value.find(c => c.id === id)
    pendingDeleteId.value = id
    pendingDeleteTitle.value = convo?.title || '此對話'
  }

  function cancelDeleteConversation () {
    pendingDeleteId.value = null
  }

  async function confirmDeleteConversation () {
    const id = pendingDeleteId.value
    if (!id) {
      return false
    }
    deletingConvoId.value = id
    try {
      await api(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
      pendingDeleteId.value = null
      if (id === conversationId.value) {
        const newId = crypto.randomUUID()
        conversationId.value = newId
        localStorage.setItem('conversationId', newId)
        messages.value = []
        setStatus('對話已刪除，已開新對話')
      }
      await loadConversations()
      return true
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setStatus(message)
      return false
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

  return {
    conversationId,
    conversations,
    currentConvoTitle,
    deletingConvoId,
    messages,
    pendingDeleteId,
    pendingDeleteTitle,
    question,
    ragEnabled,
    askQuestion,
    cancelDeleteConversation,
    clearChat,
    confirmDeleteConversation,
    createNewConversation,
    handleQuestionKeydown,
    loadConversationHistory,
    loadConversations,
    requestDeleteConversation,
    switchConversation,
  }
}
