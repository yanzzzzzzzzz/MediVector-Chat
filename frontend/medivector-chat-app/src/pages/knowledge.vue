<template>
  <div class="knowledge-app">
    <aside aria-label="工作區導覽" class="sidebar">
      <RouterLink class="brand" to="/knowledge"><span class="brand-mark"><i aria-hidden="true" class="mdi mdi-plus" /></span><span>MediVector<small>醫療文件知識管理原型</small></span></RouterLink>
      <div class="organization"><span class="organization-icon"><i aria-hidden="true" class="mdi mdi-domain" /></span><div><strong>院所工作空間</strong><small :title="catalog?.organization_id">{{ catalog?.organization_id || '等待連線' }}</small></div><i aria-hidden="true" class="mdi mdi-lock-outline" /></div>
      <p class="nav-caption">工作空間</p>

      <nav class="workspace-nav">
        <button :aria-current="activeView === 'documents' ? 'page' : undefined" :class="{ active: activeView === 'documents' }" type="button" @click="changeView('documents')"><i aria-hidden="true" class="mdi mdi-folder-outline" />文件資料庫</button>

        <button
          v-if="canEdit"
          :aria-current="activeView === 'review' ? 'page' : undefined"
          :class="{ active: activeView === 'review' }"
          type="button"
          @click="changeView('review')"
        ><i aria-hidden="true" class="mdi mdi-clipboard-check-outline" />審核佇列<span v-if="reviewCount" class="nav-count">{{ reviewCount }}</span></button>

        <a class="source-link" href="/education">衛教草稿工作台</a>
        <button :aria-current="activeView === 'query' ? 'page' : undefined" :class="{ active: activeView === 'query' }" type="button" @click="changeView('query')"><i aria-hidden="true" class="mdi mdi-text-box-search-outline" />核准知識查詢</button>

        <button
          v-if="catalog?.role === 'admin'"
          :aria-current="activeView === 'settings' ? 'page' : undefined"
          class="settings-nav"
          :class="{ active: activeView === 'settings' }"
          type="button"
          @click="changeView('settings')"
        ><i aria-hidden="true" class="mdi mdi-tune-variant" />院區與科別</button>
      </nav>

      <div class="sidebar-bottom">
        <div class="trust-note"><i aria-hidden="true" class="mdi mdi-shield-check-outline" /><strong>讓知識值得信賴</strong><p>只有流程中核准且有效的文件，<br>才會用於文件查詢。</p></div>
        <RouterLink class="demo-link" to="/"><i aria-hidden="true" class="mdi mdi-arrow-top-right" />查閱對話紀錄</RouterLink>
        <button class="account" type="button" @click="openApiAccess"><span class="avatar">{{ catalog?.principal.slice(0, 1).toUpperCase() || 'M' }}</span><span><strong>{{ catalog?.principal || '尚未連線' }}</strong><small>{{ roleLabels[catalog?.role || ''] || '設定存取憑證' }}</small></span><i aria-hidden="true" class="mdi mdi-cog-outline" /></button>
      </div>
    </aside>

    <main class="main-content">
      <div class="topbar"><div>工作台<i aria-hidden="true" class="mdi mdi-chevron-right" /><span>{{ pageTitles[activeView] }}</span></div><button class="connection" type="button" @click="openApiAccess"><span :class="['connection-dot', { online: catalog }]" />{{ catalog ? '工作空間已連線' : '連線設定' }}<i aria-hidden="true" class="mdi mdi-chevron-down" /></button></div>

      <header class="page-header">
        <div><div class="eyebrow">KNOWLEDGE WORKSPACE</div><h1>{{ pageTitles[activeView] }}</h1><p>{{ pageDescriptions[activeView] }}</p></div>

        <div class="header-actions"><button class="button secondary" :disabled="busy" type="button" @click="run(refresh)"><i aria-hidden="true" :class="['mdi mdi-refresh', { spinning: busy }]" /><span>重新整理</span></button>

          <button
            v-if="canEdit && ['documents', 'review'].includes(activeView)"
            class="button primary"
            :disabled="busy"
            type="button"
            @click="startNew"
          ><i aria-hidden="true" class="mdi mdi-plus" />新增文件</button></div>
      </header>

      <div v-if="notice" :class="['notice', notice.tone]" role="status"><i aria-hidden="true" :class="['mdi', notice.tone === 'error' ? 'mdi-alert-circle-outline' : 'mdi-check-circle-outline']" /><span>{{ notice.text }}</span><button aria-label="關閉通知" type="button" @click="notice = null"><i aria-hidden="true" class="mdi mdi-close" /></button></div>

      <template v-if="catalog">
        <div v-if="!catalog.ai_available" class="setup-notice"><i aria-hidden="true" class="mdi mdi-information-outline" /><span>目前可管理、送審與核准文件。AI 索引與問答尚未啟用，待建立索引的版本不會用於知識查詢。</span></div>
        <div v-if="activeView !== 'settings'" class="scope-filter"><span><i aria-hidden="true" class="mdi mdi-map-marker-outline" />適用範圍</span><label><span class="sr-only">選擇院區</span><select v-model="branchId" :disabled="busy"><option value="">全部院區</option><option v-for="branch in catalog.branches" :key="branch.id" :value="branch.id">{{ branch.name }}</option></select></label><span class="scope-divider" /><label><span class="sr-only">選擇科別</span><select v-model="departmentId" :disabled="busy"><option value="">全部科別</option><option v-for="department in catalog.departments" :key="department.id" :value="department.id">{{ department.name }}</option></select></label><span class="scope-hint">依帳號權限顯示可用內容</span></div>

        <template v-if="activeView === 'documents' || activeView === 'review'">
          <div class="metrics">
            <div v-for="metric in metrics" :key="metric.label" class="metric"><span :class="['metric-icon', metric.tone]"><i aria-hidden="true" :class="['mdi', metric.icon]" /></span><div><span>{{ metric.label }}</span><strong>{{ metric.count }}<small>份</small></strong></div></div>
          </div>

          <section aria-label="文件與版本清單" class="document-panel">
            <div class="panel-heading"><div><h2>{{ activeView === 'review' ? '等待審核的文件' : '文件與版本' }}<span class="count-badge">{{ activeView === 'review' ? reviewCount : scopedVersions.length }}</span></h2><p>{{ activeView === 'review' ? '核對來源與適用範圍，再決定是否核准發布。' : '管理來源內容，追蹤每一次修訂與發布。' }}</p></div><label class="search-field"><i aria-hidden="true" class="mdi mdi-magnify" /><input v-model="search" aria-label="搜尋文件" placeholder="搜尋標題、來源或版本…" type="search"></label></div>

            <div aria-label="依文件狀態篩選" class="filter-tabs" role="group"><button
              v-for="tab in tabs"
              :key="tab.value"
              :aria-pressed="statusFilter === tab.value"
              :class="{ selected: statusFilter === tab.value }"
              type="button"
              @click="statusFilter = tab.value"
            >{{ tab.label }}<span v-if="tabCount(tab.value)">{{ tabCount(tab.value) }}</span></button></div>

            <div v-if="filteredVersions.length > 0" class="table-scroll"><table class="version-table"><thead><tr><th>文件名稱</th><th>狀態</th><th>適用範圍</th><th>生效日期</th><th><span class="sr-only">操作</span></th></tr></thead>

              <tbody><tr v-for="version in filteredVersions" :key="version.id"><td><div class="document-cell"><span class="file-icon"><i aria-hidden="true" class="mdi mdi-file-document-outline" /></span><div><button class="document-title" :disabled="busy" type="button" @click="run(() => inspect(version, false))">{{ version.title }}</button><div class="document-meta"><span class="version-tag">{{ version.version_label }}</span><span>{{ version.source }}</span><span v-if="version.index_status === 'pending'" class="pending-index"><i aria-hidden="true" class="mdi mdi-clock-outline" />待建索引</span></div></div></div></td><td><span :class="['status-pill', statusClass(version)]"><span />{{ statusText(version) }}</span></td><td><div class="scope-cell">{{ scopeNames(version, 'branch') }}<small>{{ scopeNames(version, 'department') }}</small></div></td><td><time :datetime="version.effective_from">{{ formatDate(version.effective_from) }}</time><small class="date-sub">{{ version.effective_until ? `至 ${formatDate(version.effective_until)}` : '無截止日期' }}</small></td>

                <td><div class="row-actions"><button class="text-button" :disabled="busy" type="button" @click="run(() => inspect(version, false))">檢視</button>

                  <v-menu v-if="canEdit" location="bottom end"><template #activator="{ props }"><button
                                                                 v-bind="props"
                                                                 :aria-label="`${version.title} 的更多操作`"
                                                                 class="icon-button"
                                                                 :disabled="busy"
                                                                 type="button"
                                                               ><i aria-hidden="true" class="mdi mdi-dots-vertical" /></button></template>

                    <div class="version-menu"><button v-if="version.index_status === 'pending' && !['superseded', 'archived'].includes(version.status)" :disabled="!catalog.ai_available" type="button" @click="run(() => buildIndex(version))"><i aria-hidden="true" class="mdi mdi-database-sync-outline" />建立檢索索引</button><button type="button" @click="run(() => inspect(version, true))"><i aria-hidden="true" class="mdi mdi-file-edit-outline" />建立新修訂</button><button v-if="version.status === 'draft'" type="button" @click="requestTransition(version, 'submit')"><i aria-hidden="true" class="mdi mdi-send-outline" />送交審核</button><template v-if="canReview && version.status === 'in_review'"><button type="button" @click="requestTransition(version, 'approve')"><i aria-hidden="true" class="mdi mdi-check-circle-outline" />核准發布</button><button type="button" @click="requestTransition(version, 'return')"><i aria-hidden="true" class="mdi mdi-undo-variant" />退回草稿</button></template><button v-if="canReview && ['approved', 'superseded'].includes(version.status)" class="danger-text" type="button" @click="requestTransition(version, 'withdraw')"><i aria-hidden="true" class="mdi mdi-archive-arrow-down-outline" />撤回文件</button></div></v-menu></div></td></tr></tbody></table></div>

            <div v-else class="empty-state"><div class="empty-illustration"><span class="paper-back" /><span class="paper-front"><i aria-hidden="true" class="mdi mdi-file-document-outline" /></span><span class="paper-check"><i aria-hidden="true" class="mdi mdi-check" /></span></div><h3>{{ search || statusFilter !== 'all' ? '沒有符合條件的文件' : '從第一份院所文件開始' }}</h3><p>{{ search || statusFilter !== 'all' ? '試著調整搜尋文字或文件狀態，找找其他版本。' : '整理來源、設定適用範圍，送審後就能成為可信的衛教依據。' }}</p><button v-if="search || statusFilter !== 'all'" class="button secondary" type="button" @click="clearFilters">清除篩選</button>

              <button
                v-else-if="canEdit && catalog.branches.length > 0 && catalog.departments.length > 0"
                class="button primary"
                :disabled="busy"
                type="button"
                @click="startNew"
              ><i aria-hidden="true" class="mdi mdi-plus" />新增第一份文件</button>

              <button v-else-if="catalog.role === 'admin'" class="button primary" type="button" @click="changeView('settings')">設定院區與科別<i aria-hidden="true" class="mdi mdi-arrow-right" /></button></div>

            <footer class="table-footer"><span>顯示 {{ filteredVersions.length }} 個版本</span><span><i aria-hidden="true" class="mdi mdi-lock-check-outline" />僅顯示你有權限存取的文件</span></footer>
          </section>

          <section class="workflow-guide"><div class="guide-title"><span><i aria-hidden="true" class="mdi mdi-shield-check-outline" /></span><div><h3>每份知識，都有一道品質把關</h3><p>來源核准後才會用於正式查詢，歷史版本則完整保留。</p></div></div><div class="workflow-steps"><span><b>1</b>建立草稿</span><i aria-hidden="true" class="mdi mdi-chevron-right" /><span><b>2</b>送交審核</span><i aria-hidden="true" class="mdi mdi-chevron-right" /><span><b>3</b>核准發布</span></div></section>
        </template>

        <div v-else-if="activeView === 'query'" class="query-layout"><section class="query-card"><div class="section-icon"><i aria-hidden="true" class="mdi mdi-text-box-search-outline" /></div><h2>從核准的知識中，找到答案</h2><p class="muted">選定院區與科別，輸入想核對的文件問題。</p>

                                                                       <form @submit.prevent="run(ask)"><label class="field-label" for="knowledge-question">你想查詢什麼？</label>

                                                                         <textarea
                                                                           id="knowledge-question"
                                                                           v-model.trim="question"
                                                                           placeholder="例如：檢查前需要準備哪些文件？"
                                                                           required
                                                                           rows="6"
                                                                         />

                                                                         <div class="query-submit"><small><i aria-hidden="true" class="mdi mdi-shield-check-outline" />只使用已核准且有效的資料</small><button class="button primary" :disabled="busy || !branchId || !departmentId" type="submit"><i aria-hidden="true" class="mdi mdi-magnify" />{{ busy ? '正在查詢…' : '查詢核准知識' }}</button></div></form>

                                                                       <template v-if="answer"><div class="answer-heading"><span class="status-pill approved"><span />查詢完成</span><small>{{ branchName(String(answer.applied_filters?.branch_id || '')) }}／{{ departmentName(String(answer.applied_filters?.department_id || '')) }}</small></div><div class="answer-content"><AnswerText :references="answer.references" :text="answer.answer" @open-reference="reference => run(() => openCitation(reference))" /></div>

                                                                         <div v-if="answer.references.length > 0" class="answer-references"><button v-if="answer.query_trace_id" class="source-link" type="button" @click="run(inspectTrace)">查看模型與查詢追溯</button><h3>核對參考原文</h3><button v-if="answer.references[0]?.document_version_id" class="source-link" type="button" @click="startReport(answer.references[0].document_version_id, answerTrace)">回報此答案</button>

                                                                           <button
                                                                             v-for="reference in answer.references"
                                                                             :key="reference.uuid"
                                                                             :disabled="busy"
                                                                             type="button"
                                                                             @click="run(() => openCitation(reference))"
                                                                           ><span>[{{ reference.index }}]</span><div>{{ reference.title }}<small>{{ reference.version }} · 查看來源片段</small></div><i aria-hidden="true" class="mdi mdi-arrow-top-right" /></button>

                                                                           <p>引用與檢索證據不代表答案已通過事實驗證，請核對原文。</p></div></template></section>

          <aside class="query-context"><span class="section-icon small"><i aria-hidden="true" class="mdi mdi-map-marker-outline" /></span><h3>本次查詢範圍</h3><dl><dt>院區</dt><dd>{{ branchName(branchId) || '請先選擇院區' }}</dd><dt>科別</dt><dd>{{ departmentName(departmentId) || '請先選擇科別' }}</dd><dt>已建索引的核准版本</dt><dd>{{ searchableCount }} 份</dd></dl><div class="context-note"><i aria-hidden="true" class="mdi mdi-information-outline" />沒有合適的核准資料時，系統會說明無法確認院所規範。</div></aside></div>

        <section v-else class="settings-panel"><div class="panel-heading"><div><h2>院區與科別設定</h2><p>為帳號已授權的代碼設定名稱，方便文件選擇適用範圍。</p></div><span class="settings-icon"><i aria-hidden="true" class="mdi mdi-domain" /></span></div><div class="settings-grid"><form @submit.prevent="run(saveCatalog)"><h3>登錄名稱</h3><label class="field-label">類別<select v-model="catalogKind"><option value="branches">院區</option><option value="departments">科別</option></select></label><label class="field-label">已授權代碼<input v-model.trim="catalogId" placeholder="輸入帳號已獲授權的代碼" required></label><label class="field-label">顯示名稱<input v-model.trim="catalogName" placeholder="例如：主院區、一般衛教" required></label><button class="button primary" :disabled="busy" type="submit">儲存設定<i aria-hidden="true" class="mdi mdi-check" /></button></form><div class="registered-scopes"><h3>已登錄範圍</h3><p>院區</p><div v-for="branch in catalog.branches" :key="branch.id"><i aria-hidden="true" class="mdi mdi-hospital-building" /><strong>{{ branch.name }}</strong><code>{{ branch.id }}</code></div><small v-if="catalog.branches.length === 0">尚未登錄院區</small><p>科別</p><div v-for="department in catalog.departments" :key="department.id"><i aria-hidden="true" class="mdi mdi-stethoscope" /><strong>{{ department.name }}</strong><code>{{ department.id }}</code></div><small v-if="catalog.departments.length === 0">尚未登錄科別</small></div></div></section>
      </template>

      <section v-else class="connect-state"><span class="section-icon"><i aria-hidden="true" :class="['mdi', busy ? 'mdi-loading spinning' : 'mdi-domain']" /></span><h2>{{ busy ? '正在載入院所工作空間' : '連線你的院所工作空間' }}</h2><p>{{ busy ? '正在確認權限與可用文件，請稍候。' : '設定存取憑證後，即可管理授權範圍內的文件與審核工作。' }}</p><button v-if="!busy" class="button primary" type="button" @click="openApiAccess">設定連線<i aria-hidden="true" class="mdi mdi-arrow-right" /></button></section>
      <footer class="workspace-footer"><span>MediVector<span class="footer-dot">·</span>醫療文件知識管理原型</span><span>僅使用經授權的非個人資料</span></footer>
    </main>

    <dialog ref="editorDialog" aria-labelledby="editor-title" class="editor-dialog">
      <form class="editor-form" @submit.prevent="run(createVersion)"><header class="dialog-heading"><div><span class="dialog-eyebrow">DOCUMENT EDITOR</span><h2 id="editor-title">{{ form.document_id ? '建立新修訂' : '新增院所文件' }}</h2><p>儲存後先成為草稿，經核准後才可用於正式查詢。</p></div>

                                                                       <button
                                                                         aria-label="關閉文件編輯器"
                                                                         class="icon-button"
                                                                         :disabled="busy"
                                                                         type="button"
                                                                         @click="editorDialog?.close()"
                                                                       ><i aria-hidden="true" class="mdi mdi-close" /></button></header>

        <div class="editor-body"><div v-if="notice?.tone === 'error'" class="notice error" role="alert"><i aria-hidden="true" class="mdi mdi-alert-circle-outline" />{{ notice.text }}</div><section class="form-section"><h3><span>01</span>基本資訊</h3><label class="field-label">文件標題<input v-model.trim="form.title" placeholder="輸入清楚、易於辨識的標題" required></label><div class="field-grid"><label class="field-label">版本名稱<input v-model.trim="form.version_label" placeholder="例如：v1.0" required></label><label class="field-label">文件來源<input v-model.trim="form.source" placeholder="例如：護理部、檢驗科" required></label></div><label class="field-label">來源網址<span class="optional">選填</span><input v-model.trim="form.source_url" placeholder="https://" type="url"></label></section><section class="form-section"><h3><span>02</span>適用範圍與效期</h3><div class="field-grid"><label class="field-label">院區<select v-model="branchId" required><option disabled value="">選擇院區</option><option v-for="branch in catalog?.branches" :key="branch.id" :value="branch.id">{{ branch.name }}</option></select></label><label class="field-label">科別<select v-model="departmentId" required><option disabled value="">選擇科別</option><option v-for="department in catalog?.departments" :key="department.id" :value="department.id">{{ department.name }}</option></select></label><label class="field-label">生效時間<input v-model="effectiveFrom" required type="datetime-local"></label><label class="field-label">失效時間<span class="optional">選填</span><input v-model="effectiveUntil" type="datetime-local"></label></div><p v-if="form.document_id" class="field-help">新版本發布後，會取代同一文件的舊核准版本；請再次確認本次適用範圍。</p></section>

          <section class="form-section"><h3><span>03</span>原文與授權</h3>

            <label class="field-label">PDF 附件<span class="optional">選填，最多 8 MiB</span>

              <input
                ref="pdfInput"
                accept="application/pdf,.pdf"
                :disabled="busy"
                type="file"
                @change="choosePdf"
              >

              <span v-if="pdfFile">{{ pdfFile.name }} · 系統將擷取原文；掃描圖片需先完成 OCR。</span></label>

            <label class="field-label">文件原文<textarea
              v-model="form.content"
              :disabled="!!pdfFile"
              placeholder="貼上經授權的原始文件內容，請勿輸入病歷或個人健康資料。"
              :required="!pdfFile"
              rows="8"
            />

              <span class="field-counter">{{ [...form.content].length.toLocaleString() }} 字</span></label>

            <label class="field-label">授權或使用依據<input v-model.trim="form.license" placeholder="說明文件的授權來源或可使用依據" required></label><label class="field-label">{{ form.document_id ? '修訂理由' : '建立說明' }}<input v-model.trim="form.change_reason" placeholder="簡述本次建立或修訂的原因" required></label></section></div>

        <footer class="dialog-footer"><span><i aria-hidden="true" class="mdi mdi-lock-outline" />先儲存為草稿</span><div><button class="button secondary" :disabled="busy" type="button" @click="editorDialog?.close()">取消</button><button class="button primary" :disabled="busy || !branchId || !departmentId" type="submit"><i aria-hidden="true" :class="['mdi', busy ? 'mdi-loading spinning' : 'mdi-content-save-outline']" />{{ busy ? '正在儲存…' : '儲存草稿' }}</button></div></footer></form>
    </dialog>

    <dialog ref="reviewDialog" aria-labelledby="review-title" class="review-dialog"><form v-if="reviewTarget" @submit.prevent="run(confirmTransition)"><header class="dialog-heading compact"><div><span class="dialog-eyebrow">DOCUMENT REVIEW</span><h2 id="review-title">{{ actionLabels[reviewTarget.action] }}</h2></div>

                                                                                                                                                         <button
                                                                                                                                                           aria-label="關閉審核操作"
                                                                                                                                                           class="icon-button"
                                                                                                                                                           :disabled="busy"
                                                                                                                                                           type="button"
                                                                                                                                                           @click="reviewDialog?.close()"
                                                                                                                                                         ><i aria-hidden="true" class="mdi mdi-close" /></button></header>

      <div class="review-body"><div class="review-document"><i aria-hidden="true" class="mdi mdi-file-document-outline" /><div><strong>{{ reviewTarget.version.title }}</strong><small>{{ reviewTarget.version.version_label }} · {{ scopeNames(reviewTarget.version, 'branch') }}</small></div></div><p>{{ actionDescriptions[reviewTarget.action] }}</p><div v-if="notice?.tone === 'error'" class="notice error" role="alert">{{ notice.text }}</div><label class="field-label">操作理由<textarea v-model.trim="reason" placeholder="請填寫理由，這段紀錄將保留於版本歷史中。" required rows="3" /></label></div><footer class="dialog-footer"><button class="button secondary" :disabled="busy" type="button" @click="reviewDialog?.close()">取消</button><button :class="['button', reviewTarget.action === 'withdraw' ? 'danger' : 'primary']" :disabled="busy || !reason" type="submit">{{ busy ? '正在處理…' : actionLabels[reviewTarget.action] }}</button></footer></form></dialog>

    <dialog ref="sourceDialog" aria-labelledby="source-title" class="source-dialog" @close="clearPdf"><template v-if="sourcePreview"><header class="dialog-heading"><div><span class="dialog-eyebrow">SOURCE DOCUMENT</span><h2 id="source-title">{{ sourcePreview.title }}</h2><p>{{ sourcePreview.version }} · {{ sourcePreview.source }}</p></div><button aria-label="關閉原文核對" class="icon-button" type="button" @click="sourceDialog?.close()"><i aria-hidden="true" class="mdi mdi-close" /></button></header>

      <div class="source-body"><div class="source-meta"><span :class="['status-pill', sourcePreview.status]"><span />{{ labels[sourcePreview.status] || sourcePreview.status }}</span><span v-if="sourcePreview.scope">{{ sourcePreview.scope }}</span><span v-if="sourcePreview.location"><i aria-hidden="true" class="mdi mdi-book-open-page-variant-outline" />{{ sourcePreview.location }}</span></div>

        <a
          v-if="sourcePreview.sourceUrl"
          class="source-link"
          :href="sourcePreview.sourceUrl"
          rel="noopener noreferrer"
          target="_blank"
        >查看來源網址<i aria-hidden="true" class="mdi mdi-open-in-new" /></a>

        <div v-if="sourcePreview.attachment" class="pdf-source"><p>原始 PDF：{{ sourcePreview.attachment.filename }}</p>

          <button
            v-if="!pdfUrl"
            class="button secondary"
            :disabled="busy"
            type="button"
            @click="run(loadPdf)"
          >載入原始 PDF</button>

          <a
            v-else
            class="source-link"
            :href="`${pdfUrl}#page=${sourcePreview.page || 1}`"
            rel="noopener"
            target="_blank"
          >開啟原始 PDF（第 {{ sourcePreview.page || 1 }} 頁）</a>

          <p v-if="sourcePreview.unparsedPages?.length">第 {{ sourcePreview.unparsedPages.join('、') }} 頁無可用文字或解析失敗，未用於檢索；請核對原件。</p></div>

        <button class="source-link" type="button" @click="startReport(sourcePreview.versionId)">回報文件過期或內容問題</button><pre>{{ sourcePreview.content }}</pre><details class="trace-details"><summary>查看版本追溯資訊</summary><dl><dt>文件 ID</dt><dd>{{ sourcePreview.documentId }}</dd><dt>版本 ID</dt><dd>{{ sourcePreview.versionId }}</dd></dl></details></div>

      <footer class="source-footer"><i aria-hidden="true" class="mdi mdi-information-outline" />引用原文可供核對，不代表生成答案已通過事實驗證。</footer></template></dialog>

    <dialog ref="traceDialog" class="source-dialog"><header class="dialog-heading"><h2>查詢追溯</h2><button type="button" @click="traceDialog?.close()">關閉</button></header><div class="source-body"><p>保留模型、設定、文件版本與雜湊；稽核記錄不另複製原始問題與答案。</p><pre>{{ tracePreview }}</pre></div></dialog>
    <dialog ref="feedbackDialog" class="review-dialog"><form @submit.prevent="run(sendReport)"><header class="dialog-heading"><h2>回報內容問題</h2><button type="button" @click="feedbackDialog?.close()">關閉</button></header><div class="review-body"><p>回報會連結來源版本與本次查詢（如有）。請勿輸入病歷或個人健康資料。</p><label class="field-label">問題類型<select v-model="reportCategory"><option value="inappropriate_answer">回答不適切</option><option value="outdated_source">文件過期</option><option value="other">其他內容問題</option></select></label><label class="field-label">問題說明<textarea v-model.trim="reportReason" maxlength="2000" required rows="4" /></label><p v-if="notice?.tone === 'error'" role="alert">{{ notice.text }}</p></div><footer class="dialog-footer"><button class="button primary" :disabled="busy || !reportReason" type="submit">送出回報</button></footer></form></dialog>
  </div>
</template>

<script setup lang="ts">
  import type { AskResponse, ReferenceItem } from '@/types'
  import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import AnswerText from '@/components/AnswerText.vue'
  import { api, apiBlob } from '@/composables/useApi'

  interface Entry { id: string, name: string }
  interface Catalog { ai_available?: boolean, organization_id: string, principal: string, role: string, branches: Entry[], departments: Entry[] }
  interface PageMapping { page: number, status?: string }
  interface Attachment { filename: string, sha256: string }
  interface Version { attachment?: Attachment | null, pages?: PageMapping[], index_status?: 'ready' | 'pending', id: string, document_id: string, version_label: string, status: string, title: string, source: string, source_url: string, license: string, content?: string, effective_from: string, effective_until: string | null, approved_by: string | null, approved_at: string | null, scopes: { branch_id: string, department_id: string }[] }
  interface SourcePreview { title: string, version: string, status: string, source: string, sourceUrl?: string, content: string, documentId: string, versionId: string, location?: string, attachment?: Attachment | null, attachmentPath?: string, page?: number, scope?: string, unparsedPages?: number[] }
  type View = 'documents' | 'review' | 'query' | 'settings'
  type Filter = 'all' | 'draft' | 'in_review' | 'approved' | 'history'
  type Action = 'submit' | 'approve' | 'return' | 'withdraw'

  const openApiAccess = inject<() => void>('openApiAccess', () => {})
  const catalog = ref<Catalog | null>(null)
  const versions = ref<Version[]>([])
  const branchId = ref('')
  const departmentId = ref('')
  const busy = ref(false)
  const loadedOnce = ref(false)
  const notice = ref<{ text: string, tone: 'success' | 'error' } | null>(null)
  const route = useRoute()
  const activeView = ref<View>(route.query.view === 'query' ? 'query' : 'documents')
  const statusFilter = ref<Filter>('all')
  const search = ref('')
  const editorDialog = ref<HTMLDialogElement | null>(null)
  const reviewDialog = ref<HTMLDialogElement | null>(null)
  const sourceDialog = ref<HTMLDialogElement | null>(null)
  const reviewTarget = ref<{ version: Version, action: Action } | null>(null)
  const sourcePreview = ref<SourcePreview | null>(null)
  const pdfFile = ref<File | null>(null)
  const pdfInput = ref<HTMLInputElement | null>(null)
  const pdfUrl = ref('')
  function clearPdf () {
    if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value)
    pdfUrl.value = ''
  }
  function choosePdf (event: Event) {
    pdfFile.value = (event.target as HTMLInputElement).files?.[0] || null
  }
  async function loadPdf () {
    clearPdf()
    const preview = sourcePreview.value
    if (!preview?.attachmentPath) return
    const blob = await apiBlob(preview.attachmentPath)
    pdfUrl.value = URL.createObjectURL(blob)
  }
  onUnmounted(clearPdf)
  const reason = ref('')
  const blankForm = () => ({ document_id: null as string | null, title: '', version_label: 'v1.0', source: '', source_url: '', license: '', content: '', change_reason: '' })
  const form = ref(blankForm())
  const localDatetime = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
  const effectiveFrom = ref(localDatetime())
  const effectiveUntil = ref('')
  const catalogKind = ref('branches')
  const catalogId = ref('')
  const catalogName = ref('')
  const question = ref('')
  const answer = ref<AskResponse | null>(null)
  const answerTrace = ref('')
  const traceDialog = ref<HTMLDialogElement | null>(null)
  const tracePreview = ref('')
  async function inspectTrace () {
    if (!answer.value?.query_trace_id) return
    const trace = await api(`/api/knowledge/query-traces/${answer.value.query_trace_id}`)
    tracePreview.value = JSON.stringify(trace, null, 2)
    traceDialog.value?.showModal()
  }
  const feedbackDialog = ref<HTMLDialogElement | null>(null)
  const reportTarget = ref<{ versionId: string, conversationId?: string } | null>(null)
  const reportReason = ref('')
  const reportCategory = ref('inappropriate_answer')
  function startReport (versionId: string, conversationId?: string) {
    reportTarget.value = { versionId, conversationId }
    reportReason.value = ''
    reportCategory.value = conversationId ? 'inappropriate_answer' : 'outdated_source'
    feedbackDialog.value?.showModal()
  }
  async function sendReport () {
    if (!reportTarget.value) return
    await api('/api/education/feedback', { method: 'POST', body: JSON.stringify({ version_id: reportTarget.value.versionId, conversation_id: reportTarget.value.conversationId || null, category: reportCategory.value, reason: reportReason.value }) })
    feedbackDialog.value?.close()
    notify('問題已回報，來源版本與查詢紀錄已連結。')
  }
  const canEdit = computed(() => ['admin', 'reviewer', 'nurse'].includes(catalog.value?.role || ''))
  const canReview = computed(() => ['admin', 'reviewer'].includes(catalog.value?.role || ''))
  const labels: Record<string, string> = { draft: '草稿', in_review: '待審核', approved: '已發布', superseded: '已取代', archived: '已撤回' }
  const roleLabels: Record<string, string> = { admin: '機構管理員', reviewer: '文件審核者', nurse: '文件編輯者', user: '知識查詢者' }
  const pageTitles: Record<View, string> = { documents: '文件資料庫', review: '審核佇列', query: '核准知識查詢', settings: '院區與科別' }
  const pageDescriptions: Record<View, string> = { documents: '管理院所的衛教知識，讓每份內容都有出處、每次修訂都可追溯。', review: '從來源、內容到適用範圍，為即將發布的文件做好把關。', query: '以院所核准的來源回答問題，並回到原文核對每一份依據。', settings: '維護工作空間的適用範圍，讓文件與查詢找到正確的院區。' }
  const actionLabels: Record<Action, string> = { submit: '送交審核', approve: '核准發布', return: '退回草稿', withdraw: '撤回文件' }
  const actionDescriptions: Record<Action, string> = { submit: '提交後將交由具權限的審核者核對。核准前，這份文件不會用於正式查詢。', approve: '請確認原文、授權與適用範圍。發布後，同一文件的舊核准版本將保留於歷史紀錄，不再用於新查詢。', return: '退回後可建立修訂並重新送審。請記錄需要調整的內容，方便編輯者接續處理。', withdraw: '撤回後，這個版本不再供正式查詢引用。歷史版本與審核紀錄仍會保留。' }
  const scopedVersions = computed(() => versions.value.filter(version => version.scopes.some(scope => (!branchId.value || scope.branch_id === branchId.value) && (!departmentId.value || scope.department_id === departmentId.value))))
  const isEffective = (version: Version) => version.status === 'approved' && Date.parse(version.effective_from) <= Date.now() && (!version.effective_until || Date.parse(version.effective_until) > Date.now())
  const publishedCount = computed(() => scopedVersions.value.filter(version => isEffective(version)).length)
  const searchableCount = computed(() => scopedVersions.value.filter(version => isEffective(version) && version.index_status === 'ready').length)
  const reviewCount = computed(() => scopedVersions.value.filter(version => version.status === 'in_review').length)
  const metrics = computed(() => [
    { label: '全部版本', count: scopedVersions.value.length, icon: 'mdi-folder-outline', tone: 'neutral' },
    { label: '已發布・有效', count: publishedCount.value, icon: 'mdi-check-decagram-outline', tone: 'green' },
    { label: '等待審核', count: reviewCount.value, icon: 'mdi-clipboard-clock-outline', tone: 'amber' },
    { label: '編輯中草稿', count: scopedVersions.value.filter(version => version.status === 'draft').length, icon: 'mdi-file-edit-outline', tone: 'blue' },
  ])
  const tabs = computed<{ value: Filter, label: string }[]>(() => activeView.value === 'review'
    ? [{ value: 'in_review', label: '待審核文件' }]
    : [{ value: 'all', label: '所有文件' }, { value: 'draft', label: '草稿' }, { value: 'in_review', label: '待審核' }, { value: 'approved', label: '已發布' }, { value: 'history', label: '歷史版本' }])
  const matchesStatus = (version: Version, filter: Filter) => filter === 'all' || (filter === 'history' ? ['superseded', 'archived'].includes(version.status) : version.status === filter)
  const tabCount = (filter: Filter) => scopedVersions.value.filter(version => matchesStatus(version, filter)).length
  const filteredVersions = computed(() => {
    const term = search.value.trim().toLocaleLowerCase()
    const filter = activeView.value === 'review' ? 'in_review' : statusFilter.value
    return scopedVersions.value.filter(version => matchesStatus(version, filter) && (!term || [version.title, version.source, version.version_label].some(value => value.toLocaleLowerCase().includes(term))))
  })
  const branchName = (id: string) => catalog.value?.branches.find(branch => branch.id === id)?.name || id
  const departmentName = (id: string) => catalog.value?.departments.find(department => department.id === id)?.name || id
  function scopeNames (version: Version, kind: 'branch' | 'department') {
    return [...new Set(version.scopes.map(scope => kind === 'branch' ? branchName(scope.branch_id) : departmentName(scope.department_id)))].join('、') || '未設定'
  }
  function statusClass (version: Version) {
    return version.status === 'approved' && !isEffective(version) ? 'expired' : version.status
  }
  function statusText (version: Version) {
    if (version.status === 'approved' && !isEffective(version)) {
      return Date.parse(version.effective_from) > Date.now() ? '尚未生效' : '已到期'
    }
    return labels[version.status] || version.status
  }
  function formatDate (value: string) {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? '未設定' : new Intl.DateTimeFormat('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
  }
  function changeView (view: View) {
    activeView.value = view
    statusFilter.value = view === 'review' ? 'in_review' : 'all'
    search.value = ''
    notice.value = null
  }
  function clearFilters () {
    search.value = ''
    statusFilter.value = activeView.value === 'review' ? 'in_review' : 'all'
  }
  function notify (text: string) {
    notice.value = { text, tone: 'success' }
  }
  async function run (task: () => Promise<void>) {
    if (busy.value) return
    busy.value = true
    try {
      await task()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      notice.value = { text: message.includes('authorization required') ? '尚未完成連線，請先設定院所提供的存取憑證。' : message, tone: 'error' }
    } finally {
      busy.value = false
    }
  }
  async function load () {
    const [workspace, documents] = await Promise.all([api<Catalog>('/api/knowledge/catalog'), api<{ versions: Version[] }>('/api/knowledge/versions')])
    catalog.value = workspace
    versions.value = documents.versions
    if (!loadedOnce.value) {
      branchId.value = workspace.branches[0]?.id || ''
      departmentId.value = workspace.departments[0]?.id || ''
      loadedOnce.value = true
    }
  }
  async function refresh () {
    await load()
    notify('文件清單已更新。')
  }
  async function saveCatalog () {
    await api(`/api/knowledge/catalog/${catalogKind.value}`, { method: 'PUT', body: JSON.stringify({ id: catalogId.value, name: catalogName.value }) })
    catalogId.value = ''
    catalogName.value = ''
    await load()
    notify('適用範圍名稱已儲存。')
  }
  function startNew () {
    pdfFile.value = null
    if (pdfInput.value) pdfInput.value.value = ''
    form.value = blankForm()
    effectiveFrom.value = localDatetime()
    effectiveUntil.value = ''
    notice.value = null
    editorDialog.value?.showModal()
  }
  async function createVersion () {
    const payload = { ...form.value, scopes: [{ branch_id: branchId.value, department_id: departmentId.value }], effective_from: new Date(effectiveFrom.value).toISOString(), effective_until: effectiveUntil.value ? new Date(effectiveUntil.value).toISOString() : null }
    let created: Version
    if (pdfFile.value) {
      const data = new FormData()
      data.set('metadata', JSON.stringify({ ...payload, content: '' }))
      data.set('file', pdfFile.value)
      created = await api<Version>('/api/knowledge/versions/pdf', { method: 'POST', body: data })
    } else {
      created = await api<Version>('/api/knowledge/versions', { method: 'POST', body: JSON.stringify(payload) })
    }
    editorDialog.value?.close()
    changeView('documents')
    await load()
    notify(created.index_status === 'ready' ? '草稿已儲存並完成索引，可從文件清單送交審核。' : '草稿已儲存，可送交審核；檢索索引待建立。')
  }
  async function buildIndex (version: Version) {
    await api(`/api/knowledge/versions/${version.id}/index`, { method: 'POST', body: JSON.stringify({ reason: '為既有來源片段建立檢索索引' }) })
    await load()
    notify(`${version.title}：檢索索引已建立。`)
  }
  function requestTransition (version: Version, action: Action) {
    reviewTarget.value = { version, action }
    reason.value = ''
    notice.value = null
    reviewDialog.value?.showModal()
  }
  async function confirmTransition () {
    const target = reviewTarget.value
    if (!target) return
    await api(`/api/knowledge/versions/${target.version.id}/transition`, { method: 'POST', body: JSON.stringify({ action: target.action, reason: reason.value }) })
    reviewDialog.value?.close()
    answer.value = null
    sourcePreview.value = null
    await load()
    notify(`${target.version.title}：${actionLabels[target.action]}已完成。`)
  }
  async function inspect (version: Version, revise: boolean) {
    clearPdf()
    pdfFile.value = null
    if (pdfInput.value) pdfInput.value.value = ''
    const detail = await api<Version>(`/api/knowledge/versions/${version.id}`)
    notice.value = null
    if (revise) {
      form.value = { document_id: detail.document_id, title: detail.title, source: detail.source, source_url: detail.source_url, license: detail.license, content: detail.content || '', version_label: '', change_reason: '' }
      effectiveFrom.value = localDatetime()
      effectiveUntil.value = ''
      editorDialog.value?.showModal()
    } else {
      sourcePreview.value = { title: detail.title, version: detail.version_label, status: detail.status, source: detail.source, sourceUrl: detail.source_url, content: detail.content || '', documentId: detail.document_id, versionId: detail.id, scope: `${scopeNames(detail, 'branch')}／${scopeNames(detail, 'department')}`, attachment: detail.attachment, attachmentPath: `/api/knowledge/versions/${detail.id}/attachment`, unparsedPages: detail.pages?.filter(page => page.status !== 'extracted').map(page => page.page) }
      sourceDialog.value?.showModal()
    }
  }
  async function ask () {
    answer.value = null
    notice.value = null
    const conversationId = crypto.randomUUID()
    answer.value = await api<AskResponse>('/api/ask', { method: 'POST', body: JSON.stringify({ conversation_id: conversationId, question: question.value, branch_id: branchId.value, department_id: departmentId.value, rag_enabled: true }) })
    answerTrace.value = conversationId
  }
  async function openCitation (reference: ReferenceItem) {
    clearPdf()
    const metadata = reference.chunk_metadata || {}
    const params = new URLSearchParams({ branch_id: String(metadata.branch_id || ''), department_id: String(metadata.department_id || '') })
    const excerpt = await api<{ content: string, version_label: string, document_id: string, document_version_id: string, source: string, source_url: string, chunk_metadata: Record<string, unknown>, attachment?: Attachment | null }>(`/api/knowledge/chunks/${reference.uuid}?${params}`)
    if (excerpt.document_version_id !== reference.document_version_id) throw new Error('引用版本不一致，請重新查詢。')
    const pages = excerpt.chunk_metadata.pages
    sourcePreview.value = { title: reference.title, version: excerpt.version_label, status: 'approved', source: excerpt.source, sourceUrl: excerpt.source_url, content: excerpt.content, documentId: excerpt.document_id, versionId: excerpt.document_version_id, scope: `${branchName(String(metadata.branch_id))}／${departmentName(String(metadata.department_id))}`, attachment: excerpt.attachment, attachmentPath: `/api/knowledge/versions/${excerpt.document_version_id}/attachment?${params}&chunk_id=${encodeURIComponent(reference.uuid)}`, page: Array.isArray(pages) ? Number(pages[0]) || 1 : 1, location: `${Array.isArray(pages) && pages.length > 0 ? `第 ${pages.join('、')} 頁` : '純文字來源'} · 字元 ${excerpt.chunk_metadata.start}–${excerpt.chunk_metadata.end}` }
    sourceDialog.value?.showModal()
  }
  watch([branchId, departmentId], () => {
    answer.value = null
  })
  onMounted(() => run(load))
</script>

<style scoped>
:where(.knowledge-app) :where(h1, h2, h3, p, dl, dd) { margin: 0; }
:where(.knowledge-app) button { appearance: none; border: 0; background: transparent; padding: 0; }
:where(.knowledge-app) input { border: 0; background: transparent; padding: 0; min-width: 0; }

.knowledge-app { --ink: #263b32; --muted: #839088; --green: #287b5c; --border: #e7ece8; display: grid; grid-template-columns: 232px minmax(0, 1fr); min-height: 100dvh; background: #f6f8f6; color: var(--ink); color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif; font-size: 14px; line-height: 1.5; }
.knowledge-app button, .knowledge-app input, .knowledge-app select, .knowledge-app textarea { font: inherit; }
.knowledge-app button { cursor: pointer; transition: background .15s, border-color .15s, box-shadow .15s; }
.knowledge-app button:disabled { opacity: .45; cursor: not-allowed; }
.knowledge-app button:focus-visible, .knowledge-app a:focus-visible { outline: 3px solid #9ec8b4; outline-offset: 3px; }
.sidebar { height: 100dvh; position: sticky; top: 0; display: flex; flex-direction: column; padding: 30px 18px 0; background: #fff; border-right: 1px solid var(--border); }
.brand { display: flex; gap: 10px; align-items: center; color: #214c3b; text-decoration: none; padding: 0 9px; font-size: 21px; font-weight: 750; letter-spacing: -.7px; }
.brand-mark { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; color: #fff; background: var(--green); font-size: 27px; box-shadow: 0 4px 9px #2c80551a; }
.brand small { display: block; color: #707872; font-size: 11px; font-weight: 450; letter-spacing: 2px; margin-top: 1px; }
.organization { display: flex; align-items: center; gap: 10px; border: 1px solid var(--border); border-radius: 10px; background: #fcfdfc; padding: 12px 10px; margin: 30px 2px; }
.organization-icon { display: grid; place-items: center; flex: 0 0 29px; height: 29px; border-radius: 7px; background: #edf2ed; color: #657b6d; font-size: 17px; }
.organization > div { min-width: 0; flex: 1; }
.organization strong { font-size: 13px; font-weight: 600; }
.organization small { display: block; max-width: 125px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #6e7570; font-size: 11px; margin-top: 3px; }
.organization > .mdi { font-size: 14px; color: #707872; }
.nav-caption { color: #717873; font-size: 12px; letter-spacing: 1px; margin: 0 13px 10px; }
.workspace-nav { display: grid; gap: 5px; }
.workspace-nav button { display: flex; gap: 11px; align-items: center; padding: 12px 14px; width: 100%; border-radius: 8px; color: #6b7770; font-size: 13px; text-align: left; font-weight: 500; }
.workspace-nav button > .mdi { font-size: 19px; opacity: .85; }
.workspace-nav button:hover { background: #f6f8f5; color: var(--green); }
.workspace-nav button.active { background: #edf4ed; color: #2c6f4b; font-weight: 650; }
.nav-count { margin-left: auto; background: #deeadb; color: #48734b; padding: 0 6px; font-size: 12px; border-radius: 4px; }
.workspace-nav .settings-nav { margin-top: 24px; }
.sidebar-bottom { margin-top: auto; padding-top: 40px; }
.trust-note { position: relative; background: linear-gradient(135deg, #f1f6ed, #f8faf6); border: 1px solid #e8eee2; border-radius: 10px; padding: 16px 14px; margin: 0 3px 23px; }
.trust-note > .mdi { display: block; color: #577e59; font-size: 23px; margin-bottom: 8px; }
.trust-note strong { font-size: 13px; color: #587354; font-weight: 600; }
.trust-note p { color: #6b7767; font-size: 12px; line-height: 1.9; margin-top: 6px; }
.demo-link { display: flex; gap: 8px; align-items: center; margin: 0 14px 18px; font-size: 12px; color: #6e7772; text-decoration: none; }
.account { display: flex; align-items: center; gap: 10px; width: calc(100% + 36px); margin-left: -18px; border-top: 1px solid var(--border); padding: 18px; text-align: left; }
.avatar { display: grid; place-items: center; border: 3px solid #fff; outline: 1px solid #e2e9df; background: #e8eee0; color: #687c53; width: 32px; height: 32px; border-radius: 50%; font-size: 13px; font-weight: 600; }
.account > span:nth-child(2) { min-width: 0; flex: 1; }
.account strong { display: block; overflow: hidden; text-overflow: ellipsis; font-size: 13px; font-weight: 600; }
.account small { display: block; color: #6e7771; font-size: 11px; margin-top: 3px; }
.account > .mdi { color: #707772; font-size: 17px; }
.main-content { min-width: 0; width: 100%; max-width: 1500px; padding: 24px 38px 0; margin: 0 auto; }
.topbar { display: flex; justify-content: space-between; align-items: center; color: #707872; font-size: 12px; padding-bottom: 29px; }
.topbar > div { display: flex; gap: 12px; align-items: center; }
.topbar > div > .mdi { color: #727873; }
.topbar > div > span { color: #687b6e; }
.connection { display: flex; gap: 7px; align-items: center; border: 1px solid #e4eae2; padding: 6px 9px; border-radius: 6px; background: #ffffffb3; color: #6a796e; font-size: 12px; }
.connection-dot { width: 5px; height: 5px; border-radius: 50%; background: #b8c1ba; }
.connection-dot.online { background: #65a779; box-shadow: 0 0 0 3px #65a7790c; }
.page-header { display: flex; justify-content: space-between; gap: 24px; align-items: center; margin-bottom: 26px; }
.eyebrow { color: #677966; font-size: 11px; font-weight: 650; letter-spacing: 1.7px; margin-bottom: 7px; }
.page-header h1 { font-size: 29px; font-weight: 700; letter-spacing: -1.1px; line-height: 1.35; }
.page-header p { font-size: 13px; color: #6e7870; margin-top: 10px; line-height: 1.8; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; padding-top: 10px; }
.button { display: inline-flex; justify-content: center; align-items: center; gap: 7px; border: 1px solid transparent; border-radius: 7px; padding: 9px 14px; font-size: 13px !important; font-weight: 550; white-space: nowrap; line-height: 1.6; }
.button .mdi { font-size: 16px; }
.primary { color: #fff; background: var(--green, #287b5c); border-color: var(--green, #287b5c); box-shadow: 0 2px 3px #245b3810; }
.primary:hover:not(:disabled) { background: #1d654a; }
.secondary { background: #fff; border-color: #e0e7df; color: #68776b; }
.secondary:hover:not(:disabled) { border-color: #b3c6b5; background: #fafcf9; }
.danger { color: #fff; background: #b55e51; }
.scope-filter { display: flex; align-items: center; gap: 17px; margin-bottom: 22px; font-size: 13px; }
.scope-filter > span:first-child { display: flex; align-items: center; gap: 6px; color: #71786f; font-size: 12px; }
.scope-filter > span:first-child > .mdi { font-size: 15px; }
.scope-filter select { padding: 7px 26px 7px 10px; border: 1px solid #e2e8de; border-radius: 6px; background: #fff; color: #5e7562; appearance: auto; min-width: 110px; font-size: 12px; cursor: pointer; }
.scope-divider { height: 16px; width: 1px; background: #e2e8df; margin: 0 -7px; }
.scope-hint { margin-left: auto; color: #6f756e; font-size: 11px; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 26px; }
.metric { display: flex; gap: 13px; align-items: center; min-width: 0; background: #fff; border: 1px solid #e7ece3; border-radius: 10px; padding: 18px; }
.metric-icon { display: grid; place-items: center; width: 38px; height: 38px; flex-shrink: 0; border: 1px solid transparent; border-radius: 10px; font-size: 20px; }
.metric-icon.neutral { color: #6c7966; background: #f5f7f1; border-color: #edf1e6; }
.metric-icon.green { color: #507d60; background: #f0f6ef; border-color: #e8f0e4; }
.metric-icon.amber { color: #89734c; background: #faf6ec; border-color: #f3eddb; }
.metric-icon.blue { color: #627888; background: #f0f5f7; border-color: #e8eff2; }
.metric > div > span { font-size: 12px; color: #6e776b; }
.metric strong { display: block; color: #4a624d; font-weight: 650; font-size: 26px; line-height: 1.2; margin-top: 6px; font-variant-numeric: tabular-nums; letter-spacing: -.8px; }
.metric strong small { margin-left: 7px; font-size: 12px; font-weight: 450; color: #70766c; }
.document-panel { min-width: 0; background: #fff; border: 1px solid #e4eade; border-radius: 11px; box-shadow: 0 3px 9px #29401602; overflow: hidden; }
.panel-heading { display: flex; justify-content: space-between; align-items: center; gap: 18px; padding: 23px 24px 20px; }
.panel-heading h2 { display: flex; align-items: center; gap: 9px; font-size: 14px; font-weight: 650; color: #465d45; }
.panel-heading p { color: #6f756a; font-size: 12px; margin-top: 6px; }
.count-badge { padding: 1px 6px; border-radius: 5px; background: #f0f4eb; color: #6c7a62; font-size: 11px; font-weight: 500; }
.search-field { display: flex; align-items: center; gap: 8px; color: #6f766c; border: 1px solid #e8ede1; background: #fdfefb; border-radius: 7px; padding: 8px 10px; min-width: 225px; font-size: 12px; }
.search-field > .mdi { font-size: 15px; }
.search-field input { outline: none; min-width: 0; width: 100%; color: #677b60; }
.search-field input::placeholder { color: #6f756b; }
.search-field:focus-within { border-color: #9eb998; box-shadow: 0 0 0 3px #5c8e4b08; }
.filter-tabs { display: flex; gap: 24px; padding: 0 24px; border-bottom: 1px solid #edf0e7; }
.filter-tabs button { display: flex; align-items: center; gap: 6px; position: relative; padding: 10px 1px 13px; color: #707768; font-size: 12px; white-space: nowrap; }
.filter-tabs button.selected { color: #417441; font-weight: 650; }
.filter-tabs button.selected::after { content: ''; position: absolute; bottom: -1px; left: 0; right: 0; height: 2px; border-radius: 2px; background: #49854a; }
.filter-tabs button > span { font-size: 10px; padding: 0 4px; background: #f2f5ed; border-radius: 3px; }
.table-scroll { overflow-x: auto; }
.version-table { width: 100%; border-collapse: collapse; text-align: left; }
.version-table th { font-size: 11px; font-weight: 500; color: #72796b; background: #fcfdf9; padding: 12px 16px; border-bottom: 1px solid #eef1e7; white-space: nowrap; }
.version-table th:first-child, .version-table td:first-child { padding-left: 24px; }
.version-table td { padding: 18px 16px; border-bottom: 1px solid #f0f3e9; font-size: 13px; vertical-align: middle; }
.version-table th:first-child { width: 40%; }
.version-table tbody tr:last-child td { border-bottom: 0; }
.version-table tbody tr:hover { background: #fcfdf9; }
.document-cell { display: flex; align-items: center; gap: 12px; }
.file-icon { display: grid; place-items: center; flex: 0 0 34px; height: 39px; background: #f2f6ed; border: 1px solid #e8eedf; color: #667b59; border-radius: 7px; font-size: 20px; }
.document-title { display: block; text-align: left; font-size: 13px; font-weight: 600; color: #49613e; line-height: 1.6; }
.document-title:hover { color: #2c7843; text-decoration: underline; text-underline-offset: 3px; }
.document-meta { display: flex; align-items: center; gap: 7px; color: #70756a; font-size: 11px; margin-top: 5px; }
.version-tag { padding: 0 5px; font-size: 10px; border: 1px solid #e8eddf; border-radius: 3px; color: #707867; white-space: nowrap; }
.status-pill { display: inline-flex; gap: 5px; align-items: center; border: 1px solid transparent; border-radius: 5px; padding: 3px 7px; font-size: 11px; font-weight: 550; white-space: nowrap; }
.status-pill > span { display: inline-block; height: 4px; width: 4px; border-radius: 50%; background: currentColor; }
.status-pill.draft { color: #6f7967; background: #f5f7ef; border-color: #ebefdf; }
.status-pill.approved { color: #538155; background: #f0f7eb; border-color: #e4efdb; }
.status-pill.in_review, .status-pill.expired { color: #857248; background: #fcf8ec; border-color: #f2ead5; }
.status-pill.superseded { color: #67777c; background: #f2f6f7; border-color: #e6edf0; }
.status-pill.archived { color: #71756b; background: #f7f8f3; border-color: #eceee5; }
.scope-cell { color: #6d7760; font-size: 12px; }
.scope-cell small, .date-sub { display: block; color: #73786b; font-size: 11px; margin-top: 4px; }
.version-table time { color: #6d7860; font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.row-actions { display: flex; gap: 6px; align-items: center; justify-content: flex-end; }
.text-button { color: #5e7d4a; font-size: 12px !important; padding: 4px; white-space: nowrap; }
.icon-button { display: grid; place-items: center; height: 29px; width: 29px; border-radius: 6px; color: #727969; font-size: 18px !important; flex: 0 0 auto; }
.icon-button:hover { background: #f1f5e9; color: #5f803c; }
.version-menu { display: grid; padding: 5px; min-width: 172px; background: #fff; color: #64794f; border: 1px solid #e4ebd8; border-radius: 9px; box-shadow: 0 7px 24px #3d54221a; font-size: 13px; }
.version-menu button { display: flex; gap: 9px; align-items: center; padding: 10px; border-radius: 5px; text-align: left; }
.version-menu button:hover { background: #f5f8ee; }
.version-menu .mdi { font-size: 16px; }
.version-menu .danger-text { color: #96695a; }
.empty-state { display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 28px 24px 32px; min-height: 295px; text-align: center; }
.empty-illustration { width: 90px; height: 91px; position: relative; margin: 0 0 10px; }
.empty-illustration::before { content: ''; position: absolute; width: 78px; height: 78px; left: 6px; top: 3px; border-radius: 50%; background: #f7f9f1; }
.paper-back { position: absolute; width: 44px; height: 56px; top: 9px; left: 14px; border: 1px solid #dfe8d1; background: #fcfdf9; border-radius: 7px; transform: rotate(-14deg); }
.paper-front { display: grid; place-items: center; position: absolute; width: 46px; height: 58px; top: 17px; left: 30px; border: 1px solid #d5e1c4; background: #fff; border-radius: 7px; color: #6c775c; font-size: 29px; box-shadow: 0 4px 12px #556a3210; transform: rotate(8deg); }
.paper-check { display: grid; place-items: center; position: absolute; right: 6px; bottom: 8px; width: 22px; height: 22px; border-radius: 50%; background: #75a95f; border: 3px solid #fff; color: #fff; font-size: 13px; }
.empty-state h3 { font-size: 15px; letter-spacing: -.4px; font-weight: 600; color: #60764c; }
.empty-state p { font-size: 12px; color: #707765; margin: 9px 0 21px; line-height: 1.9; max-width: 350px; }
.empty-state .button { padding: 8px 14px; font-size: 12px !important; }
.table-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; border-top: 1px solid #eef2e4; padding: 12px 24px; font-size: 11px; color: #717766; background: #fdfefb; }
.table-footer span:last-child { display: flex; align-items: center; gap: 5px; }
.workflow-guide { display: flex; justify-content: space-between; align-items: center; gap: 24px; padding: 23px 21px; margin-top: 21px; border: 1px solid #e5ebdc; border-radius: 10px; background: linear-gradient(110deg, #f2f6ec, #f9fbf4); }
.guide-title { display: flex; gap: 12px; align-items: center; }
.guide-title > span { display: grid; place-items: center; color: #677b55; font-size: 26px; }
.guide-title h3 { font-size: 13px; font-weight: 600; color: #677b52; }
.guide-title p { font-size: 11px; color: #717966; margin-top: 6px; }
.workflow-steps { display: flex; gap: 10px; align-items: center; font-size: 11px; flex-shrink: 0; color: #6a7858; }
.workflow-steps > span { display: flex; align-items: center; gap: 5px; white-space: nowrap; }
.workflow-steps b { display: grid; place-items: center; height: 17px; width: 17px; border: 1px solid #dce7cd; border-radius: 50%; color: #6b785a; font-size: 10px; font-weight: 500; background: #ffffff9c; }
.workflow-steps > .mdi { color: #6f7665; }
.workspace-footer { display: flex; justify-content: space-between; gap: 20px; padding: 26px 1px 20px; color: #70766a; font-size: 11px; }
.footer-dot { margin: 0 7px; color: #72776d; }
.setup-notice { display: flex; gap: 9px; align-items: flex-start; color: #7b8060; background: #faf9ee; border: 1px solid #ece9d6; padding: 12px 14px; border-radius: 8px; font-size: 12px; line-height: 1.8; margin-bottom: 20px; }
.pending-index { display: inline-flex; align-items: center; gap: 3px; color: #93805d; font-size: 10px; white-space: nowrap; }
.document-meta { flex-wrap: wrap; }
.notice { display: flex; align-items: center; gap: 9px; padding: 12px 14px; margin-bottom: 18px; border-radius: 8px; font-size: 13px; border: 1px solid; line-height: 1.7; }
.notice > button { margin-left: auto; flex-shrink: 0; }
.notice.error { color: #9c6856; border-color: #f1e1d7; background: #fdf6f0; }
.notice.success { color: #5e7c49; border-color: #e2ecd5; background: #f5f9ee; }
.query-layout { display: grid; grid-template-columns: minmax(0, 1fr) 250px; gap: 20px; }
.query-card, .query-context, .settings-panel { background: #fff; border: 1px solid var(--border); border-radius: 11px; padding: 28px; }
.section-icon { display: grid; place-items: center; height: 46px; width: 46px; background: #f0f6e9; border: 1px solid #e9efdf; color: #687d50; border-radius: 13px; font-size: 24px; margin-bottom: 19px; }
.section-icon.small { height: 35px; width: 35px; border-radius: 9px; font-size: 18px; }
.query-card h2, .connect-state h2 { font-size: 20px; font-weight: 600; letter-spacing: -.6px; color: #4e6840; }
.muted { color: #6f7964; font-size: 13px; margin-top: 8px; }
.query-card form { margin-top: 28px; }
.query-submit { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-top: 15px; }
.query-submit > small { display: flex; gap: 5px; align-items: center; font-size: 12px; color: #6b795b; }
.query-context { align-self: start; padding: 23px; }
.query-context h3 { font-size: 13px; font-weight: 600; color: #677a52; }
.query-context dl { margin-top: 21px; }
.query-context dt { color: #6e7662; font-size: 12px; margin-top: 17px; }
.query-context dd { font-size: 13px; margin-top: 5px; color: #667d4e; }
.context-note { display: flex; align-items: flex-start; gap: 6px; color: #6c785e; font-size: 12px; line-height: 1.9; border-top: 1px solid #edf1e5; margin-top: 25px; padding-top: 18px; }
.answer-heading { display: flex; gap: 10px; align-items: center; border-top: 1px solid #e9efdf; padding-top: 25px; margin-top: 28px; }
.answer-heading small { color: #6c795e; font-size: 12px; }
.answer-content { white-space: pre-wrap; overflow-wrap: anywhere; color: #587244; font-size: 14px; line-height: 2; margin: 20px 0 25px; }
.answer-references { border-top: 1px solid #edf1e6; padding-top: 20px; }
.answer-references h3 { font-size: 13px; color: #687953; font-weight: 500; margin-bottom: 12px; }
.answer-references > button { display: flex; width: 100%; gap: 10px; align-items: center; text-align: left; padding: 12px; border: 1px solid #e8efdf; border-radius: 7px; background: #fafcf6; margin-bottom: 8px; font-size: 13px; color: #647d4a; }
.answer-references > button > span { color: #6c7b5a; }
.answer-references > button > .mdi { margin-left: auto; }
.answer-references small { display: block; color: #6e7a5e; font-size: 11px; margin-top: 3px; }
.answer-references > p { color: #6f7865; font-size: 12px; margin-top: 13px; }
.settings-panel { padding: 0; overflow: hidden; }
.settings-panel .panel-heading { border-bottom: 1px solid #edf1e4; padding: 24px 28px; }
.settings-icon { font-size: 30px; color: #6c7a5e; }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; padding: 28px; }
.settings-grid form { display: grid; gap: 19px; align-content: start; }
.settings-grid h3 { font-size: 13px; font-weight: 550; color: #647d4c; margin-bottom: 4px; }
.settings-grid form .button { justify-self: start; margin-top: 6px; }
.registered-scopes { padding-left: 28px; border-left: 1px solid #edf1e5; }
.registered-scopes > p { font-size: 12px; color: #707966; margin: 20px 0 8px; }
.registered-scopes > div { display: flex; gap: 9px; align-items: center; padding: 13px 0; border-bottom: 1px solid #f1f4ea; color: #6b7c56; font-size: 15px; }
.registered-scopes strong { color: #667b4d; font-size: 13px; font-weight: 500; }
.registered-scopes code { color: #6f7863; font-size: 11px; margin-left: auto; }
.registered-scopes > small { color: #6f7863; font-size: 12px; }
.connect-state { display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px solid var(--border); border-radius: 12px; background: #fff; min-height: 400px; padding: 40px; text-align: center; }
.connect-state p { max-width: 360px; color: #6d7960; font-size: 13px; line-height: 1.9; margin: 12px 0 26px; }
.field-label { display: flex; flex-direction: column; position: relative; gap: 8px; font-size: 13px; color: #617c42; font-weight: 500; }
.knowledge-app input:not([type=search]), .knowledge-app textarea, .field-label > select { width: 100%; border: 1px solid #e0e8d7; border-radius: 7px; background: #fff; color: #4e6e30; padding: 11px 12px; outline: none; font-weight: 400; font-size: 13px; }
.knowledge-app input::placeholder, .knowledge-app textarea::placeholder { color: #6f7764; }
.knowledge-app input:focus, .knowledge-app textarea:focus, .knowledge-app select:focus { border-color: #a1bb80; box-shadow: 0 0 0 3px #79a74f0c; }
.knowledge-app textarea { line-height: 1.9; resize: vertical; }
.field-label > select { appearance: auto; }
.field-help { font-size: 13px; color: #6c7857; line-height: 1.8; margin-top: 13px; }
.optional { position: absolute; right: 0; top: 0; font-size: 12px; color: #6e7760; font-weight: 400; }
.knowledge-app dialog { color: var(--ink); background: #fff; padding: 0; border: 1px solid #e1e9d7; box-shadow: 0 24px 100px #263c1640; }
.knowledge-app dialog::backdrop { background: #233d2766; backdrop-filter: blur(2px); }
.editor-dialog { position: fixed; inset: 0 0 0 auto; margin: 0; height: 100dvh; max-height: 100dvh; width: min(620px, 100vw); max-width: 100vw; border: 0 !important; border-left: 1px solid #e1e9d7 !important; border-radius: 18px 0 0 18px; }
.editor-form { display: flex; flex-direction: column; height: 100%; }
.dialog-heading { display: flex; gap: 20px; justify-content: space-between; padding: 28px 30px 24px; border-bottom: 1px solid #ecf0e3; }
.dialog-eyebrow { color: #6b7959; font-size: 11px; letter-spacing: 1.7px; font-weight: 600; }
.dialog-heading h2 { font-size: 23px; letter-spacing: -.8px; font-weight: 650; color: #456525; margin-top: 6px; }
.dialog-heading p { color: #6d7760; font-size: 13px; margin-top: 8px; line-height: 1.8; }
.dialog-heading .icon-button { margin-top: 1px; }
.editor-body { overflow-y: auto; flex: 1; min-height: 0; padding: 0 30px 12px; }
.form-section { padding: 25px 0; border-bottom: 1px solid #edf1e4; }
.form-section:last-child { border-bottom: 0; }
.form-section h3 { display: flex; gap: 9px; align-items: center; font-size: 13px; font-weight: 550; color: #657f41; margin-bottom: 20px; }
.form-section h3 > span { color: #6a795a; font-size: 12px; background: #f3f7ed; border: 1px solid #e9efdf; border-radius: 5px; padding: 2px 6px; font-weight: 450; }
.form-section > .field-label + .field-label, .form-section > .field-grid, .form-section > .field-grid + .field-label { margin-top: 20px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.field-counter { display: block; align-self: flex-end; font-size: 12px; font-weight: 400; color: #6f795f; }
.dialog-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 20px 30px; border-top: 1px solid #e8efdc; background: #fdfefb; }
.dialog-footer > span { display: flex; gap: 5px; color: #6e7a5b; font-size: 12px; }
.dialog-footer > div { display: flex; gap: 8px; }
.review-dialog, .source-dialog { margin: auto; width: min(500px, calc(100vw - 32px)); border-radius: 14px; max-height: calc(100dvh - 48px); }
.dialog-heading.compact { padding: 24px; }
.review-body { padding: 24px; }
.review-document { display: flex; align-items: center; gap: 12px; padding: 15px; border: 1px solid #e9efdf; background: #f9fbf5; border-radius: 9px; }
.review-document > .mdi { font-size: 26px; color: #687d55; }
.review-document strong { display: block; font-size: 14px; color: #5e7d3c; font-weight: 550; }
.review-document small { display: block; color: #6c795d; margin-top: 4px; font-size: 12px; }
.review-body > p { color: #6e7b5e; font-size: 13px; line-height: 1.9; margin: 18px 0 24px; }
.review-dialog .dialog-footer { padding: 18px 24px; }
.source-dialog { width: min(740px, calc(100vw - 32px)); }
.source-body { max-height: calc(100dvh - 280px); overflow-y: auto; padding: 25px 30px 30px; }
.source-meta { display: flex; gap: 16px; align-items: center; margin-bottom: 18px; }
.source-meta > span:last-child:not(.status-pill) { color: #6c795a; font-size: 12px; }
.source-body pre { font-family: inherit; white-space: pre-wrap; overflow-wrap: anywhere; color: #536f34; font-size: 14px; line-height: 2; }
.source-link { display: inline-flex; gap: 7px; align-items: center; margin-bottom: 18px; color: #607c46; text-decoration: none; font-size: 13px; }
.trace-details { margin-top: 28px; padding-top: 18px; border-top: 1px solid #edf1e4; color: #6d775d; font-size: 12px; }
.trace-details summary { cursor: pointer; }
.trace-details dl { margin-top: 12px; }
.trace-details dt { color: #697d53; margin-top: 10px; }
.trace-details dd { overflow-wrap: anywhere; font-size: 11px; margin-top: 4px; }
.source-footer { padding: 17px 30px; background: #fafcf6; border-top: 1px solid #edf1e2; color: #707a62; font-size: 12px; }
.source-footer .mdi { margin-right: 6px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (min-width: 1600px) { .main-content { padding-left: 60px; padding-right: 60px; } }
@media (max-width: 1150px) { .main-content { padding: 24px 26px 0; } .sidebar { padding-left: 14px; padding-right: 14px; } .knowledge-app { grid-template-columns: 208px minmax(0, 1fr); } .account { width: calc(100% + 28px); margin-left: -14px; padding: 16px 14px; } .metric { padding: 15px 12px; gap: 10px; } .metric-icon { width: 32px; height: 32px; font-size: 18px; } .metric > div > span { font-size: 11px; } .workflow-guide { flex-wrap: wrap; gap: 17px; } .query-layout { grid-template-columns: minmax(0, 1fr) 210px; gap: 15px; } }
@media (max-width: 900px) { .knowledge-app { grid-template-columns: minmax(0, 1fr); } .sidebar { position: static; height: auto; display: grid; grid-template-columns: 1fr auto; padding: 18px 24px 0; gap: 15px; border-right: 0; border-bottom: 1px solid var(--border); } .brand { padding: 0; } .brand-mark { height: 32px; width: 32px; } .organization, .nav-caption, .sidebar-bottom .trust-note, .demo-link { display: none; } .workspace-nav { grid-column: 1 / -1; display: flex; gap: 4px; overflow-x: auto; padding-bottom: 12px; } .workspace-nav .settings-nav { margin-top: 0; } .workspace-nav button { width: auto; padding: 9px 13px; white-space: nowrap; font-size: 13px; } .sidebar > .workspace-nav:last-of-type { grid-row: 2; }  .sidebar-bottom { padding: 0; margin: 0; grid-row: 1; grid-column: 2; } .account { width: auto; border: 0; margin: 0; padding: 0; } .account > span:nth-child(2), .account > .mdi { display: none; }  .main-content { padding: 20px 24px 0; } .topbar { padding-bottom: 23px; } .page-header h1 { font-size: 27px; } .scope-hint { display: none; } .page-header { align-items: flex-start; } .header-actions { padding-top: 18px; } .query-layout { grid-template-columns: 1fr; } .query-context { order: -1; } .query-context dl { display: flex; gap: 10px; align-items: center; margin-top: 0; flex-wrap: wrap; } .query-context dt, .query-context dd { margin: 0; } .query-context dt:not(:first-child) { margin-left: 15px; } .query-context .section-icon, .query-context h3, .context-note { display: none; } .query-context { padding: 15px 20px; } }
@media (max-width: 600px) { .sidebar { padding: 16px 16px 0; gap: 17px; } .brand { font-size: 19px; } .workspace-nav button { padding: 8px 10px; font-size: 12px; } .workspace-nav button > .mdi { font-size: 16px; } .main-content { padding: 17px 16px 0; } .topbar { padding-bottom: 22px; } .connection { font-size: 11px; border: 0; background: transparent; padding: 0; } .page-header { gap: 15px; flex-wrap: wrap; margin-bottom: 22px; } .eyebrow { font-size: 10px; } .page-header h1 { font-size: 26px; } .page-header p { font-size: 12px; margin-top: 8px; } .header-actions { padding-top: 0; } .button { padding: 8px 12px; font-size: 12px !important; } .scope-filter { gap: 10px; flex-wrap: wrap; margin-bottom: 18px; } .scope-filter select { min-width: 99px; padding-right: 12px; } .scope-divider { margin: 0; } .metrics { grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; } .metric { padding: 14px; gap: 12px; } .metric strong { font-size: 23px; } .panel-heading { align-items: flex-start; padding: 19px 17px 17px; flex-direction: column; gap: 16px; } .search-field { width: 100%; min-width: 0; } .filter-tabs { gap: 20px; padding: 0 17px; overflow-x: auto; } .filter-tabs button { font-size: 11px; } .empty-state { padding: 30px 16px 35px; min-height: 280px; } .empty-state h3 { font-size: 14px; } .empty-state p { max-width: 240px; font-size: 12px; } .table-footer { padding: 12px 17px; font-size: 10px; } .table-footer span:last-child { gap: 3px; } .table-scroll .version-table { min-width: 700px; } .workflow-guide { padding: 19px 17px; gap: 19px; } .guide-title h3 { font-size: 12px; } .guide-title p { font-size: 11px; line-height: 1.9; } .workflow-steps { width: 100%; justify-content: space-between; } .workspace-footer { padding-top: 22px; font-size: 10px; } .workspace-footer > span:last-child { display: none; } .query-card { padding: 22px 19px; } .query-card h2 { font-size: 18px; } .query-submit { flex-wrap: wrap; gap: 14px; } .query-submit .button { width: 100%; } .settings-grid { grid-template-columns: 1fr; gap: 30px; padding: 22px; } .registered-scopes { padding: 25px 0 0; border-left: 0; border-top: 1px solid #edf1e5; } .dialog-heading { padding: 23px 22px 21px; } .dialog-heading h2 { font-size: 21px; } .editor-body { padding: 0 22px 10px; } .editor-dialog { border-radius: 0; } .dialog-footer { padding: 17px 22px; } .dialog-footer > span { display: none; } .dialog-footer > div { width: 100%; justify-content: flex-end; } .field-grid { gap: 17px 12px; } .knowledge-app input[type=datetime-local] { font-size: 12px; padding: 11px 6px; min-width: 0; } .source-body { padding: 22px; } .source-footer { padding: 16px 22px; line-height: 1.8; } }
@media (prefers-reduced-motion: reduce) { .spinning { animation: none; } .knowledge-app button { transition: none; } }
</style>
