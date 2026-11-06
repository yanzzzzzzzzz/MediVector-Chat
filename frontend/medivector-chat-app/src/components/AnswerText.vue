<template>
  <span>
    <template v-for="(part, index) in parseAnswerParts(text, references)" :key="index">
      <button v-if="part.reference" class="inline-reference" type="button" @click="$emit('open-reference', part.reference)">[{{ part.reference.index }}]</button>
      <strong v-else-if="part.emphasis">{{ part.text }}</strong>
      <template v-else>{{ part.text }}</template>
    </template>
  </span>
</template>

<script setup lang="ts">
  import type { ReferenceItem } from '@/types'
  import { parseAnswerParts } from '@/utils/answerParts'

  withDefaults(defineProps<{ text: string, references?: ReferenceItem[] }>(), { references: () => [] })
  defineEmits<{ 'open-reference': [reference: ReferenceItem] }>()
</script>

<style scoped>
.inline-reference { display: inline; padding: 0 4px; border: 1px solid #b8ddd7; border-radius: 4px; background: #eef7f5; color: #0b5f59; font: inherit; cursor: pointer; }
</style>
