<template>
  <dialog ref="dialogEl">
    <div class="dialog-head">
      <h2>{{ reference ? `[${reference.index}] ${reference.title || '參考資料'}` : '參考資料' }}</h2>
      <button type="button" @click="$emit('close')">關閉</button>
    </div>

    <div v-if="reference" class="reference-body">
      <div class="reference-meta">
        來源：{{ reference.source || '未知' }} · source_id={{ reference.source_id ?? '未知' }} · distance={{ reference.distance_text || '未知' }}
        <br>
        日期：{{ reference.published_date || '未填' }} · 適用對象：{{ reference.audience || '未填' }} · 主題：{{ reference.topic || '未分類' }}
      </div>

      <pre class="reference-content">{{ reference.content || '' }}</pre>
    </div>
  </dialog>
</template>

<script setup lang="ts">
  import type { ReferenceItem } from '@/types'
  import { ref } from 'vue'

  defineProps<{
    reference: ReferenceItem | null
  }>()

  defineEmits<{
    close: []
  }>()

  const dialogEl = ref<HTMLDialogElement | null>(null)

  function show () {
    dialogEl.value?.showModal()
  }

  function close () {
    dialogEl.value?.close()
  }

  defineExpose({ show, close })
</script>

<style scoped>
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
</style>
