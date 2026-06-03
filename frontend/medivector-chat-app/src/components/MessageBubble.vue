<template>
  <div :class="['msg', message.role, { thinking: message.thinking }]">
    <template v-if="message.thinking">
      <span aria-hidden="true" class="spinner inline" />
      <span>思考中</span>
    </template>

    <template v-else-if="message.role === 'assistant' && message.references.length > 0">
      <template v-for="(part, index) in answerParts(message)" :key="index">
        <button v-if="part.ref" class="citation" type="button" @click="$emit('open-reference', part.ref)">
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
</template>

<script setup lang="ts">
  import type { AnswerPart, ChatMessage, ReferenceItem } from '@/types'

  defineProps<{
    message: ChatMessage
  }>()

  defineEmits<{
    'open-reference': [reference: ReferenceItem]
  }>()

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
</script>

<style scoped>
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

  @keyframes spin {
    to { transform: rotate(360deg); }
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
    border: 1px solid #b8ddd7;
    border-radius: 6px;
    background: #eef7f5;
    color: #0b5f59;
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    vertical-align: baseline;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
</style>
