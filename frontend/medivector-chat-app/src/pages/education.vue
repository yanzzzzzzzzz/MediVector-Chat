<template>
  <main class="education-workspace">
    <header><div><a href="/knowledge">← 院所文件資料庫</a><h1>衛教草稿工作台</h1><p>選擇核准來源，製作待審稿，經專業人員核准後發布。</p></div><button :disabled="busy" @click="run(load)">重新整理</button></header>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>

    <template v-if="catalog">
      <section v-if="canEdit" class="card">
        <h2>從核准來源建立草稿</h2>

        <form @submit.prevent="run(generate)">
          <div class="fields"><label>院區<select v-model="branch"><option v-for="entry in catalog.branches" :key="entry.id" :value="entry.id">{{ entry.name }}</option></select></label><label>科別<select v-model="department"><option v-for="entry in catalog.departments" :key="entry.id" :value="entry.id">{{ entry.name }}</option></select></label><label>衛教主題<input v-model.trim="topic" maxlength="500" placeholder="例如：檢查前衛教" required></label></div>
          <fieldset><legend>選擇核准且有效的來源（最多 10 份）</legend><p v-if="approvedSources.length === 0">此範圍尚無核准來源，請先至文件資料庫建立並完成審核。</p><label v-for="source in approvedSources" :key="source.id" class="source-choice"><input v-model="selectedSources" type="checkbox" :value="source.id"><span>{{ source.title }} <small>{{ source.version_label }}</small></span></label></fieldset>
          <p class="muted">僅使用選定原文。AI 輸出會保留來源編號，仍須逐段人工核對；請勿輸入個人健康資料。</p><button class="primary" :disabled="busy || !catalog.ai_available || selectedSources.length === 0 || selectedSources.length > 10">{{ busy ? '處理中…' : '產生待審草稿' }}</button>
        </form>
      </section>

      <section class="card"><h2>{{ canEdit ? '文稿與發布狀態' : '已發布衛教' }}</h2><p v-if="drafts.length === 0">尚無可閱讀的文稿。</p>

        <div class="draft-list"><button
          v-for="draft in drafts"
          :key="draft.id"
          class="draft-row"
          :disabled="busy"
          @click="run(() => inspect(draft.id))"
        ><strong>{{ draft.topic }}</strong><span>{{ statusLabels[draft.status] }} · r{{ draft.revision_number }}</span></button></div></section>

      <section v-if="canReview" class="card"><h2>問題回報</h2><p v-if="reports.length === 0">目前沒有回報。</p><article v-for="report in reports" :key="report.id"><strong>{{ report.category }}</strong><p>{{ report.reason }}</p><small>來源版本：{{ report.version_id }} · 查詢紀錄：{{ report.conversation_id || '文件回報' }} · {{ report.actor }} · {{ report.created_at }}</small></article></section>
    </template>

    <dialog ref="editor" @close="active = null"><template v-if="active"><header><div><h2>{{ active.topic }}</h2><p>{{ statusLabels[active.status] }} · r{{ active.revision_number }} · {{ scopeName(active) }}</p></div><button @click="editor?.close()">關閉</button></header><p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="active.status !== 'published'" class="notice">此文稿目前未供正式使用，不可作為正式衛教交付。</p>
      <label>文稿內容<textarea v-model="content" :readonly="!canEdit || active.status !== 'draft'" rows="12" /></label>
      <section><h3>核對來源</h3><details v-for="source in active.sources" :key="source.version_id"><summary>[來源{{ source.index }}] {{ source.title }} · {{ source.version_label }}</summary><p>文件 {{ source.document_id }} · 版本 {{ source.version_id }}</p><pre>{{ source.content || '請至核准文件資料庫查看原文。' }}</pre></details></section>

      <template v-if="canEdit"><label>修改／審核理由<input v-model.trim="reason" maxlength="2000" placeholder="記錄修改或審核依據，勿填個人健康資料"></label><div class="actions"><button v-if="active.status === 'draft'" :disabled="busy || !reason || content === active.content" @click="run(save)">儲存新修訂</button><button v-if="active.status === 'draft'" class="primary" :disabled="busy || !reason || content !== active.content" @click="run(() => transition('submit'))">送交審核</button><template v-if="canReview && active.status === 'in_review'"><button :disabled="busy || !reason" @click="run(() => transition('return'))">退回修改</button><button class="primary" :disabled="busy || !reason" @click="run(() => transition('approve'))">核准並發布</button></template><button v-if="canReview && active.status === 'published'" :disabled="busy || !reason" @click="run(() => transition('withdraw'))">撤回發布</button></div><p class="muted">核准前請逐段核對引用、適用範圍與文字。只檢查引用編號存在，無法證明內容正確。</p>
        <details><summary>人工修改與事件紀錄</summary><article v-for="revision in active.revisions" :key="revision.id"><h4>r{{ revision.revision_number }} · {{ revision.actor }} · {{ revision.created_at }}</h4><p>{{ revision.reason }}</p><pre>{{ revision.diff || 'AI 初始待審稿' }}</pre></article><article v-for="event in active.events" :key="event.sequence"><p>{{ event.action }} · {{ event.actor }} · {{ event.created_at }}<br>{{ event.reason }}</p></article></details>
      </template>
    </template></dialog>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { api } from '@/composables/useApi'

  interface Entry { id: string, name: string }
  interface Catalog { role: string, ai_available: boolean, branches: Entry[], departments: Entry[] }
  interface Source { id: string, title: string, version_label: string, status: string, effective_from: string, effective_until: string | null, scopes: { branch_id: string, department_id: string }[] }
  interface Evidence { index: number, document_id: string, version_id: string, title: string, version_label: string, content?: string }
  interface Revision { id: string, revision_number: number, actor: string, reason: string, diff: string, created_at: string }
  interface AuditEvent { sequence: number, action: string, actor: string, reason: string, created_at: string }
  interface Draft { id: string, topic: string, status: string, revision_number: number, branch_id: string, department_id: string, content: string, sources: Evidence[], revisions?: Revision[], events?: AuditEvent[] }
  interface Report { id: string, version_id: string, conversation_id: string | null, actor: string, category: string, reason: string, created_at: string }
  const catalog = ref<Catalog | null>(null)
  const sources = ref<Source[]>([])
  const drafts = ref<Draft[]>([])
  const reports = ref<Report[]>([])
  const branch = ref('')
  const department = ref('')
  const topic = ref('檢查前衛教')
  const selectedSources = ref<string[]>([])
  const active = ref<Draft | null>(null)
  const editor = ref<HTMLDialogElement | null>(null)
  const content = ref('')
  const reason = ref('')
  const busy = ref(false)
  const notice = ref('')
  const canEdit = computed(() => ['nurse', 'reviewer', 'admin'].includes(catalog.value?.role || ''))
  const canReview = computed(() => ['reviewer', 'admin'].includes(catalog.value?.role || ''))
  const statusLabels: Record<string, string> = { draft: '編輯中草稿', in_review: '待專業審核', published: '已發布', archived: '已撤回' }
  const approvedSources = computed(() => sources.value.filter(source => source.status === 'approved' && Date.parse(source.effective_from) <= Date.now() && (!source.effective_until || Date.parse(source.effective_until) > Date.now()) && source.scopes.some(scope => scope.branch_id === branch.value && scope.department_id === department.value)))
  function scopeName (draft: Draft) {
    return `${catalog.value?.branches.find(entry => entry.id === draft.branch_id)?.name}／${catalog.value?.departments.find(entry => entry.id === draft.department_id)?.name}`
  }
  async function run (work: () => Promise<unknown>) {
    busy.value = true
    notice.value = ''
    try {
      await work()
    } catch (error) {
      notice.value = error instanceof Error ? error.message : '操作失敗'
    } finally {
      busy.value = false
    }
  }
  async function load () {
    catalog.value = await api<Catalog>('/api/knowledge/catalog')
    branch.value ||= catalog.value.branches[0]?.id || ''
    department.value ||= catalog.value.departments[0]?.id || ''
    sources.value = (await api<{ versions: Source[] }>('/api/knowledge/versions')).versions
    drafts.value = (await api<{ drafts: Draft[] }>('/api/education/drafts')).drafts
    if (canReview.value) reports.value = (await api<{ feedback: Report[] }>('/api/education/feedback')).feedback
  }
  async function inspect (id: string) {
    active.value = await api<Draft>(`/api/education/drafts/${id}`)
    content.value = active.value.content
    reason.value = ''
    if (!editor.value?.open) editor.value?.showModal()
  }
  async function generate () {
    const draft = await api<Draft>('/api/education/drafts', { method: 'POST', body: JSON.stringify({ branch_id: branch.value, department_id: department.value, topic: topic.value, version_ids: selectedSources.value }) })
    await load()
    await inspect(draft.id)
    notice.value = '待審稿已建立，請逐段核對來源並編輯。'
  }
  async function save () {
    if (!active.value) return
    const id = active.value.id
    await api(`/api/education/drafts/${id}/revisions`, { method: 'POST', body: JSON.stringify({ expected_revision: active.value.revision_number, content: content.value, reason: reason.value }) })
    await load()
    await inspect(id)
    notice.value = '新修訂與差異已保留。'
  }
  async function transition (action: string) {
    if (!active.value) return
    const id = active.value.id
    await api(`/api/education/drafts/${id}/transition`, { method: 'POST', body: JSON.stringify({ expected_revision: active.value.revision_number, action, reason: reason.value }) })
    await load()
    await inspect(id)
    notice.value = '狀態已更新，審核事件已記錄。'
  }
  watch([branch, department], () => {
    selectedSources.value = []
  })
  onMounted(() => run(load))
</script>

<style scoped>
.education-workspace { background: #f5f8f5; min-height: 100dvh; max-width: 1120px; margin: auto; padding: 36px 24px 80px; color: #29483d; }
header, .draft-row, .actions { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
h1 { margin: 12px 0; font-size: 30px; } h2 { margin: 0 0 20px; font-size: 21px; } h3 { margin: 20px 0 12px; }
p { line-height: 1.8; } a { color: #26745c; } button { cursor: pointer; border: 1px solid #d3dfd8; border-radius: 7px; background: white; color: #29483d; padding: 10px 16px; }
button:disabled { opacity: .5; cursor: default; } .primary { color: white; background: #26745c; border-color: #26745c; }
.card { padding: 26px; background: white; border: 1px solid #e0e6e1; border-radius: 12px; margin-top: 24px; }
.fields { display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 18px; } label { display: grid; gap: 8px; font-size: 14px; margin-bottom: 16px; }
input:not([type=checkbox]), select, textarea { width: 100%; border: 1px solid #cfdad3; border-radius: 6px; padding: 10px; background: #fff; color: #29483d; font: inherit; box-sizing: border-box; }
textarea { line-height: 1.9; } input[type=checkbox] { width: 18px; height: 18px; } fieldset { padding: 18px; border: 1px solid #e0e6e1; border-radius: 8px; } .source-choice { display: flex; align-items: center; margin: 12px 0; } small, .muted { color: #738078; font-size: 12px; }
.notice { padding: 12px 16px; background: #f5f4e7; border-radius: 8px; } .draft-row { width: 100%; text-align: left; margin: 10px 0; padding: 16px; } .draft-row span { font-size: 13px; }
dialog { background: white; width: min(900px, 95vw); max-height: 92dvh; border: 0; border-radius: 14px; padding: 28px; color: #29483d; overflow: auto; } dialog::backdrop { background: #223a3377; backdrop-filter: blur(3px); } dialog header { margin-bottom: 22px; } dialog header h2 { margin-bottom: 8px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; font-size: 13px; line-height: 1.8; background: #f6f8f5; padding: 14px; } details { margin: 16px 0; } summary { cursor: pointer; } .actions { justify-content: flex-start; flex-wrap: wrap; } article { border-top: 1px solid #e3e8e2; padding: 16px 0; }
@media (max-width: 650px) { .fields { grid-template-columns: 1fr; gap: 0; } header { flex-wrap: wrap; } .education-workspace { padding: 20px 14px; } .draft-row { align-items: flex-start; flex-direction: column; gap: 8px; } dialog { padding: 20px; } }
</style>
