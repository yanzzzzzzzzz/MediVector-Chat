<template>
  <section aria-label="查詢紀錄" class="history-workspace">
    <div v-if="error" class="history-error" role="alert">{{ error }}<button :disabled="busy" type="button" @click="refresh">重新載入</button></div>

    <aside class="history-list">
      <header><h2>最近的查詢</h2><span>{{ conversations.length }} 筆</span></header>
      <label class="history-search"><i aria-hidden="true" class="mdi mdi-magnify" /><input v-model.trim="search" aria-label="搜尋查詢紀錄" placeholder="搜尋查詢標題" type="search"></label>
      <p class="history-hint">僅顯示目前帳號最近 50 筆對話。</p>

      <div class="history-items">
        <button
          v-for="conversation in filteredConversations"
          :key="conversation.id"
          :aria-pressed="selectedId === conversation.id"
          :class="{ selected: selectedId === conversation.id }"
          :disabled="busy"
          type="button"
          @click="selectConversation(conversation.id)"
        >
          <strong>{{ conversation.title }}</strong><time :datetime="conversation.created_at">{{ formatTime(conversation.created_at) }}</time>
        </button>

        <p v-if="!busy && filteredConversations.length === 0" class="history-empty">{{ search ? '沒有符合的查詢紀錄。' : '還沒有查詢紀錄，先試著查詢一個問題。' }}</p>
      </div>
    </aside>

    <div class="history-content">
      <p v-if="busy" aria-live="polite" class="history-empty" role="status">正在載入查詢紀錄…</p>

      <template v-else-if="selectedId">
        <header class="history-detail-heading"><h2>{{ selectedConversation?.title || '查詢內容' }}</h2><p>{{ formatTime(selectedConversation?.created_at) }}</p></header>
        <p v-if="messages.length === 0" class="history-empty">此對話目前沒有可讀取的訊息。</p>

        <article v-for="(message, index) in messages" :key="`${selectedId}:${index}`" :class="['history-message', message.role]">
          <header><strong>{{ message.role === 'user' ? '問題' : '文件回覆' }}</strong><time v-if="message.created_at" :datetime="message.created_at">{{ formatTime(message.created_at) }}</time></header>
          <div v-if="message.role === 'assistant'" class="history-answer"><AnswerText :references="message.references || []" :text="message.content" @open-reference="openReference" /></div>
          <p v-else class="history-answer">{{ message.content }}</p>

          <template v-if="message.role === 'assistant'">
            <p v-if="scopeText(message)" class="history-scope">原查詢範圍：{{ scopeText(message) }}</p>
            <p v-if="message.source_support_assessment" :class="['support-estimate', message.source_support_assessment.status]">{{ supportLabels[message.source_support_assessment.status] }}<small>AI 估計，仍需核對原文。</small></p>

            <div class="history-message-actions">
              <button v-if="linkedHistoryTrace(message, traces)" type="button" @click="openMessageTrace(message)">查看這則回覆的追溯</button>
              <button v-if="message.references?.[0]?.document_version_id" type="button" @click="$emit('report-answer', { versionId: message.references[0].document_version_id, conversationId: selectedId })">回報此答案</button>
            </div>

            <div v-if="message.references?.length" class="history-references"><h3>核對參考原文</h3>

              <button
                v-for="reference in message.references"
                :key="reference.uuid"
                :disabled="!canOpenHistoryCitation(reference)"
                type="button"
                @click="openReference(reference)"
              ><span>[{{ reference.index }}]</span><span>{{ reference.title }}<small>{{ reference.version || '未記錄版本' }}</small></span><i aria-hidden="true" class="mdi mdi-arrow-top-right" /></button></div>
          </template>
        </article>

        <details v-if="traces.length > 0 && needsTraceList" class="history-traces"><summary>此對話的追溯紀錄（{{ traces.length }} 筆）</summary><p>舊訊息可能沒有逐則連結，可依執行時間開啟紀錄核對。</p><button v-for="trace in traces" :key="trace.id" type="button" @click="$emit('open-trace', trace.id)">{{ formatTime(trace.created_at) }} · 查看追溯</button></details>
        <p class="history-hint">來源會在開啟時重新確認權限與有效性；紀錄不代表答案已通過人工審查。</p>
      </template>

      <div v-else class="history-empty history-start"><i aria-hidden="true" class="mdi mdi-history" /><h2>找回先前的問題與依據</h2><p>從左側選取紀錄，查看原回覆、來源版本與查詢追溯。</p><button type="button" @click="$emit('new-query')">開始新查詢</button></div>
    </div>
  </section>
</template>

<script setup lang="ts">
  import type { ConversationItem, ConversationMessageItem, QueryTraceSummary, ReferenceItem } from '@/types'
  import { computed, onMounted, ref } from 'vue'
  import AnswerText from '@/components/AnswerText.vue'
  import { api } from '@/composables/useApi'
  import { canOpenHistoryCitation, historyScope, linkedHistoryTrace, loadHistoryDetail } from '@/utils/knowledgeHistory'

  const props = defineProps<{ branches: { id: string, name: string }[], departments: { id: string, name: string }[] }>()
  const emit = defineEmits<{ 'open-reference': [reference: ReferenceItem], 'open-trace': [traceId: string], 'new-query': [], 'report-answer': [target: { versionId: string, conversationId: string }] }>()
  const conversations = ref<ConversationItem[]>([])
  const messages = ref<ConversationMessageItem[]>([])
  const traces = ref<QueryTraceSummary[]>([])
  const selectedId = ref('')
  const search = ref('')
  const busy = ref(false)
  const error = ref('')
  const needsTraceList = computed(() => messages.value.some(message => message.role === 'assistant' && !linkedHistoryTrace(message, traces.value)))
  const selectedConversation = computed(() => conversations.value.find(item => item.id === selectedId.value))
  const filteredConversations = computed(() => conversations.value.filter(item => item.title.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
  const supportLabels = { sufficient: '來源資訊足夠', partial: '部分資訊不足', insufficient: '來源資訊不足', uncertain: '來源仍需確認' }

  function formatTime (value?: string | null) {
    if (!value || Number.isNaN(Date.parse(value))) return '時間未記錄'
    return new Intl.DateTimeFormat('zh-TW', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
  }
  function scopeText (message: ConversationMessageItem) {
    const scope = historyScope(message)
    if (!scope.branchId || !scope.departmentId) return ''
    return `${props.branches.find(item => item.id === scope.branchId)?.name || scope.branchId}／${props.departments.find(item => item.id === scope.departmentId)?.name || scope.departmentId}`
  }
  function openReference (reference: ReferenceItem) {
    if (canOpenHistoryCitation(reference)) emit('open-reference', reference)
  }
  function openMessageTrace (message: ConversationMessageItem) {
    const traceId = linkedHistoryTrace(message, traces.value)
    if (traceId) emit('open-trace', traceId)
  }
  async function fetchDetail (id: string) {
    const detail = await loadHistoryDetail(api, id)
    messages.value = detail.messages
    traces.value = detail.traces
  }
  async function selectConversation (id: string) {
    if (busy.value) return
    busy.value = true
    error.value = ''
    selectedId.value = id
    messages.value = []
    traces.value = []
    try {
      await fetchDetail(id)
    } catch (error_) {
      error.value = error_ instanceof Error ? error_.message : String(error_)
    } finally {
      busy.value = false
    }
  }
  async function refresh () {
    if (busy.value) return false
    busy.value = true
    error.value = ''
    messages.value = []
    traces.value = []
    try {
      const result = await api<{ conversations: ConversationItem[] }>('/api/conversations')
      conversations.value = result.conversations
      messages.value = []
      traces.value = []
      if (selectedId.value && conversations.value.some(item => item.id === selectedId.value)) await fetchDetail(selectedId.value)
      else selectedId.value = ''
      return true
    } catch (error_) {
      conversations.value = []
      selectedId.value = ''
      error.value = error_ instanceof Error ? error_.message : String(error_)
      return false
    } finally {
      busy.value = false
    }
  }
  onMounted(refresh)
  defineExpose({ refresh })
</script>

<style scoped>
.history-workspace { display: grid; grid-template-columns: minmax(230px, 300px) minmax(0, 1fr); gap: 20px; align-items: start; }
.history-list, .history-content { min-width: 0; border: 1px solid #e7ece8; border-radius: 16px; background: #fff; }
.history-list { overflow: hidden; }
.history-list > header { display: flex; align-items: center; justify-content: space-between; padding: 20px 18px 12px; }
.history-workspace h2 { margin: 0; font-size: 17px; color: #294839; }
.history-list > header span, .history-hint { color: #839088; font-size: 12px; }
.history-hint { margin: 12px 18px; line-height: 1.7; }
.history-search { display: flex; align-items: center; gap: 8px; margin: 0 16px; padding: 9px 12px; border: 1px solid #e1e9e3; border-radius: 8px; color: #829087; }
.history-search input { min-width: 0; width: 100%; font: inherit; border: 0; outline: none; }
.history-items { display: grid; max-height: 68vh; overflow: auto; padding: 6px 10px 12px; }
.history-items button { display: grid; gap: 7px; padding: 13px 12px; border: 0; border-radius: 9px; background: transparent; text-align: left; color: #384a40; cursor: pointer; }
.history-items button:hover, .history-items button.selected { background: #edf5ef; }
.history-items strong { font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.history-items time, .history-message time { color: #89958d; font-size: 11px; }
.history-content { min-height: 400px; padding: 24px; }
.history-detail-heading { padding-bottom: 16px; border-bottom: 1px solid #edf0ed; overflow-wrap: anywhere; }
.history-detail-heading p { margin: 8px 0 0; font-size: 12px; color: #89958d; }
.history-message { margin-top: 18px; padding: 18px; border: 1px solid #e5ece6; border-radius: 12px; }
.history-message.user { background: #f4f8f4; }
.history-message > header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; font-size: 12px; color: #4e6a58; }
.history-answer { margin: 12px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.9; }
.history-scope { color: #75867a; font-size: 12px; margin-top: 14px; }
.support-estimate { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; color: #8a7044; font-size: 12px; }
.support-estimate.sufficient { color: #287b5c; }
.support-estimate small { font-size: inherit; color: #89958d; }
.history-message-actions { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 14px; }
.history-message-actions button, .history-traces button { padding: 4px 0; border: 0; color: #287b5c; background: transparent; cursor: pointer; font: inherit; font-size: 12px; text-align: left; }
.history-references { margin-top: 18px; padding-top: 16px; border-top: 1px solid #edf0ed; }
.history-references h3 { font-size: 12px; color: #6b8072; }
.history-references button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 12px 0; border: 0; background: transparent; color: #4f6d59; cursor: pointer; font: inherit; text-align: left; font-size: 12px; }
.history-references button > span:nth-child(2) { flex: 1; overflow-wrap: anywhere; }
.history-references small { display: block; margin-top: 4px; color: #89958d; }
.history-traces { margin-top: 20px; padding: 14px 0; border-top: 1px solid #edf0ed; color: #6d8173; font-size: 12px; }
.history-traces summary { cursor: pointer; }
.history-traces button { display: block; }
.history-error { grid-column: 1 / -1; padding: 15px; border-radius: 10px; background: #fff3eb; color: #875d3e; font-size: 13px; }
.history-error button { margin-left: 15px; border: 0; background: transparent; color: inherit; text-decoration: underline; cursor: pointer; }
.history-empty { padding: 25px 15px; color: #89958d; font-size: 13px; line-height: 1.8; }
.history-start { text-align: center; padding-top: 65px; }
.history-start > i { display: block; margin-bottom: 15px; color: #6b9b7b; font-size: 36px; }
.history-start button { margin-top: 10px; padding: 9px 16px; border: 0; border-radius: 8px; background: #287b5c; color: #fff; cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
@media (max-width: 900px) { .history-workspace { grid-template-columns: 1fr; } .history-items { max-height: 260px; } .history-content { padding: 18px; } }
</style>
