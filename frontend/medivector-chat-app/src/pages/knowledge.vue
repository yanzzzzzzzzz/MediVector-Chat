<template>
  <div class="workspace">
    <h1>院所文件與審核</h1>
    <RouterLink to="/">回到 Demo</RouterLink>
    <p>僅使用合成或經授權的非個人文件，請勿輸入病歷或個人健康資料。新增文件先存為待審版本。只有核准有效的來源可用於院所查詢，查詢結果仍須核對原文。</p>
    <p aria-live="polite">{{ status }}</p>

    <template v-if="catalog">
      <section>
        <h2>{{ catalog.organization_id }} · {{ catalog.principal }}（{{ catalog.role }}）</h2>
        <label>院區<select v-model="branchId" :disabled="busy"><option v-for="b in catalog.branches" :key="b.id" :value="b.id">{{ b.name }}</option></select></label>
        <label>科別<select v-model="departmentId" :disabled="busy"><option v-for="d in catalog.departments" :key="d.id" :value="d.id">{{ d.name }}</option></select></label>
        <button :disabled="busy" type="button" @click="run(load)">重新整理</button>

        <details v-if="catalog.role === 'admin'">
          <summary>登錄院區與科別</summary>

          <form @submit.prevent="run(saveCatalog)">
            <label>類別<select v-model="catalogKind"><option value="branches">院區</option><option value="departments">科別</option></select></label>
            <label>已授權代碼<input v-model.trim="catalogId" required></label>
            <label>名稱<input v-model.trim="catalogName" required></label>
            <button :disabled="busy" type="submit">儲存名稱</button>
          </form>
        </details>
      </section>

      <section>
        <h2>版本清單</h2>
        <label>審核／撤回理由<input v-model.trim="reason" placeholder="操作前請填寫理由"></label>
        <p v-if="versions.length === 0">尚無可存取版本。</p>

        <article v-for="v in versions" :key="v.id">
          <h3>{{ v.title }} · {{ v.version_label }} · {{ labels[v.status] || v.status }}</h3>
          <p>文件 {{ v.document_id }} · 版本 {{ v.id }}</p>
          <p>適用：{{ v.scopes.map(s => `${s.branch_id}／${s.department_id}`).join('、') }}</p>
          <p>有效：{{ v.effective_from }} 至 {{ v.effective_until || '未設定截止' }}</p>
          <p v-if="v.approved_by">核准：{{ v.approved_by }} · {{ v.approved_at }}</p>
          <button :disabled="busy" type="button" @click="run(() => inspect(v, false))">檢視原文</button>
          <button v-if="canEdit" :disabled="busy" type="button" @click="run(() => inspect(v, true))">建立新修訂</button>
          <button v-if="canEdit && v.status === 'draft'" :disabled="busy || !reason" type="button" @click="run(() => transition(v, 'submit'))">送審</button>

          <template v-if="canReview && v.status === 'in_review'">
            <button :disabled="busy || !reason" type="button" @click="run(() => transition(v, 'approve'))">核准發布</button>
            <button :disabled="busy || !reason" type="button" @click="run(() => transition(v, 'return'))">退回</button>
          </template>

          <button v-if="canReview && ['approved', 'superseded'].includes(v.status)" :disabled="busy || !reason" type="button" @click="run(() => transition(v, 'withdraw'))">撤回</button>
        </article>
      </section>

      <section v-if="canEdit">
        <h2>{{ form.document_id ? '建立新版本（保留舊版）' : '新增待審文件' }}</h2>
        <p>適用範圍為上方選定的院區／科別。新版發布會取代同一文件的舊核准版本。</p>
        <button v-if="form.document_id" type="button" @click="form.document_id = null">改為新增文件</button>

        <form @submit.prevent="run(createVersion)">
          <label>標題<input v-model.trim="form.title" required></label>
          <label>版本名稱<input v-model.trim="form.version_label" required></label>
          <label>來源<input v-model.trim="form.source" required></label>
          <label>來源網址<input v-model.trim="form.source_url" type="url"></label>
          <label>授權／可使用依據<input v-model.trim="form.license" required></label>
          <label>生效時間<input v-model="effectiveFrom" required type="datetime-local"></label>
          <label>失效時間（可留空）<input v-model="effectiveUntil" type="datetime-local"></label>
          <label>原文<textarea v-model="form.content" required rows="8" /></label>
          <label>修訂理由<input v-model.trim="form.change_reason" required></label>
          <button :disabled="busy || !branchId || !departmentId" type="submit">儲存待審版本並建立索引</button>
        </form>
      </section>

      <section>
        <h2>核准來源查詢</h2>

        <form @submit.prevent="run(ask)">
          <label>問題<textarea v-model.trim="question" required rows="3" /></label>
          <button :disabled="busy || !branchId || !departmentId" type="submit">查詢此院區／科別</button>
        </form>

        <template v-if="answer">
          <p>適用院區／科別：{{ answer.applied_filters?.branch_id }}／{{ answer.applied_filters?.department_id }}</p>
          <p class="original">{{ answer.answer }}</p>

          <button
            v-for="reference in answer.references"
            :key="reference.uuid"
            :disabled="busy"
            type="button"
            @click="run(() => openCitation(reference))"
          >[{{ reference.index }}] {{ reference.title }} · {{ reference.version }} · 核對原文</button>
        </template>
      </section>
    </template>

    <section v-if="original"><h2>原文核對</h2><pre>{{ original }}</pre></section>
  </div>
</template>

<script setup lang="ts">
  import type { AskResponse, ReferenceItem } from '@/types'
  import { computed, onMounted, ref, watch } from 'vue'
  import { api } from '@/composables/useApi'

  interface Entry { id: string, name: string }
  interface Catalog { organization_id: string, principal: string, role: string, branches: Entry[], departments: Entry[] }
  interface Version { id: string, document_id: string, version_label: string, status: string, title: string, source: string, source_url: string, license: string, content?: string, effective_from: string, effective_until: string | null, approved_by: string | null, approved_at: string | null, scopes: { branch_id: string, department_id: string }[] }
  const catalog = ref<Catalog | null>(null)
  const versions = ref<Version[]>([])
  const branchId = ref('')
  const departmentId = ref('')
  const status = ref('請先於頁面上方套用院所帳號 Token。')
  const busy = ref(false)
  const reason = ref('')
  const form = ref({ document_id: null as string | null, title: '', version_label: 'v1', source: '', source_url: '', license: '', content: '', change_reason: '' })
  const effectiveFrom = ref(new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16))
  const effectiveUntil = ref('')
  const catalogKind = ref('branches')
  const catalogId = ref('')
  const catalogName = ref('')
  const original = ref('')
  const question = ref('')
  const answer = ref<AskResponse | null>(null)
  const canEdit = computed(() => ['admin', 'reviewer', 'nurse'].includes(catalog.value?.role || ''))
  const canReview = computed(() => ['admin', 'reviewer'].includes(catalog.value?.role || ''))
  const labels: Record<string, string> = { draft: '草稿', in_review: '待審', approved: '已核准', superseded: '已被新版取代', archived: '已撤回' }

  async function run (task: () => Promise<void>) {
    busy.value = true
    try {
      await task()
    } catch (error) {
      status.value = error instanceof Error ? error.message : String(error)
    } finally {
      busy.value = false
    }
  }
  async function load () {
    catalog.value = await api<Catalog>('/api/knowledge/catalog')
    branchId.value ||= catalog.value.branches[0]?.id || ''
    departmentId.value ||= catalog.value.departments[0]?.id || ''
    versions.value = (await api<{ versions: Version[] }>('/api/knowledge/versions')).versions
    status.value = `已載入 ${versions.value.length} 個可存取版本。`
  }
  async function saveCatalog () {
    await api(`/api/knowledge/catalog/${catalogKind.value}`, { method: 'PUT', body: JSON.stringify({ id: catalogId.value, name: catalogName.value }) })
    await load()
  }
  async function createVersion () {
    await api('/api/knowledge/versions', { method: 'POST', body: JSON.stringify({ ...form.value, scopes: [{ branch_id: branchId.value, department_id: departmentId.value }], effective_from: new Date(effectiveFrom.value).toISOString(), effective_until: effectiveUntil.value ? new Date(effectiveUntil.value).toISOString() : null }) })
    await load()
    status.value = '已建立待審版本；尚未核准，不會用於正式查詢。'
  }
  async function transition (version: Version, action: string) {
    await api(`/api/knowledge/versions/${version.id}/transition`, { method: 'POST', body: JSON.stringify({ action, reason: reason.value }) })
    answer.value = null
    original.value = ''
    await load()
  }
  async function inspect (version: Version, revise: boolean) {
    const detail = await api<Version>(`/api/knowledge/versions/${version.id}`)
    original.value = `${detail.title} · ${detail.version_label} · ${detail.status}\n${detail.source}\n\n${detail.content}`
    if (revise) {
      form.value = { document_id: detail.document_id, title: detail.title, source: detail.source, source_url: detail.source_url, license: detail.license, content: detail.content || '', version_label: '', change_reason: '' }
    }
  }
  async function ask () {
    answer.value = null
    original.value = ''
    answer.value = await api<AskResponse>('/api/ask', { method: 'POST', body: JSON.stringify({ conversation_id: crypto.randomUUID(), question: question.value, branch_id: branchId.value, department_id: departmentId.value, rag_enabled: true }) })
    status.value = '查詢完成，請核對引用原文。'
  }
  async function openCitation (reference: ReferenceItem) {
    const metadata = reference.chunk_metadata || {}
    const params = new URLSearchParams({ branch_id: String(metadata.branch_id || ''), department_id: String(metadata.department_id || '') })
    original.value = ''
    const excerpt = await api<{ content: string, version_label: string, document_version_id: string, chunk_metadata: Record<string, unknown> }>(`/api/knowledge/chunks/${reference.uuid}?${params}`)
    if (excerpt.document_version_id !== reference.document_version_id) {
      throw new Error('引用版本不一致，請重新查詢。')
    }
    const pages = excerpt.chunk_metadata.pages
    original.value = `版本 ${excerpt.version_label}（${excerpt.document_version_id}）\n頁碼：${Array.isArray(pages) && pages.length > 0 ? pages.join('、') : '純文字'}；原文範圍：${excerpt.chunk_metadata.start}–${excerpt.chunk_metadata.end}\n\n${excerpt.content}`
  }
  watch([branchId, departmentId], () => {
    answer.value = null
    original.value = ''
  })
  onMounted(() => run(load))
</script>

<style scoped>
.workspace { max-width: 1080px; margin: auto; padding: 24px; }
section, details { border: 1px solid #bbb; border-radius: 8px; padding: 16px; margin: 20px 0; }
form { display: grid; gap: 12px; margin-top: 12px; }
label { display: grid; gap: 4px; margin: 8px 0; }
input, select, textarea, button { border: 1px solid #aaa; border-radius: 4px; padding: 8px; }
button { margin: 4px; }
button:disabled { opacity: .5; }
article { padding: 16px 0; border-bottom: 1px solid #ddd; overflow-wrap: anywhere; }
pre, .original { white-space: pre-wrap; overflow-wrap: anywhere; }
h1, h2, h3 { margin-bottom: 8px; }
</style>
