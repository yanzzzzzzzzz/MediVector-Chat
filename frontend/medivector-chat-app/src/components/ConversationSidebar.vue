<template>
  <aside class="convo-sidebar">
    <div class="convo-sidebar-head">
      <span class="convo-sidebar-title">我的對話</span>

      <button class="primary convo-new-btn" type="button" @click="$emit('create-new')">
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
          @click="$emit('switch-conversation', convo.id)"
        >
          <span class="convo-item-title">{{ convo.title }}</span>
          <span class="convo-item-time">{{ formatConvoTime(convo.created_at) }}</span>
        </button>

        <button
          class="convo-delete-btn"
          :disabled="deletingConvoId === convo.id"
          title="刪除對話"
          type="button"
          @click.stop="$emit('delete-conversation', convo.id)"
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
      <button class="sidebar-docs-btn" type="button" @click="$emit('open-docs')">
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
</template>

<script setup lang="ts">
  import type { ConversationItem } from '@/types'

  defineProps<{
    conversations: ConversationItem[]
    conversationId: string
    deletingConvoId: string | null
  }>()

  defineEmits<{
    'create-new': []
    'switch-conversation': [id: string]
    'delete-conversation': [id: string]
    'open-docs': []
  }>()

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
</script>

<style scoped>
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
  button:disabled { opacity: 0.55; cursor: not-allowed; }

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

  @media (max-width: 720px) {
    .convo-sidebar {
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      gap: 0;
      min-height: auto;
      border-radius: 8px;
    }

    .convo-sidebar-head {
      width: 100%;
      border-bottom: 1px solid #d9dee5;
      border-right: none;
    }

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
  }
</style>
