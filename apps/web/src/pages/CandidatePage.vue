<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiField from '../components/UiField.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy } from '../copy'
import { dataTypes, quoteExists, sourceTypes } from '../workflow'
import type { Candidate, Workflow } from '../workflow'
const props = defineProps<{ state: Workflow }>()
defineEmits<{ back: []; next: [] }>()
const chosenId = ref('')
const chosen = computed(() => props.state.candidates.find(item => item.id === chosenId.value))
const source = computed(() => props.state.sources.find(item => item.id === props.state.sourceId))
const candidates = computed(() => props.state.candidates.filter(item => item.sourceId === props.state.sourceId))
const quoteValid = computed(() => !!chosen.value && quoteExists(chosen.value, props.state.sources))
const parts = computed(() => {
  const text = source.value?.text ?? ''; const quote = chosen.value?.quote ?? ''
  const offset = quoteValid.value ? text.indexOf(quote) : -1
  return offset < 0 ? { before: text, quote: '', after: '' } : { before: text.slice(0, offset), quote, after: text.slice(offset + quote.length) }
})
const notice = ref('')
watch(() => props.state.sourceId, () => { chosenId.value = candidates.value[0]?.id ?? ''; notice.value = '' }, { immediate: true })
watch(() => props.state.candidates.length, () => { if (!chosen.value) chosenId.value = candidates.value[0]?.id ?? '' })
function select(candidate: Candidate) {
  chosenId.value = candidate.id; notice.value = ''
  void nextTick(() => document.getElementById('candidate-quote-mark')?.scrollIntoView({ block: 'nearest', behavior: 'auto' }))
}
function add() {
  if (!source.value || props.state.candidates.length >= 100) return
  const candidate: Candidate = { id: crypto.randomUUID(), sourceId: source.value.id, quote: '', dataType: 'location', polarity: 'UNKNOWN', subject: 'UNKNOWN', condition: '', checked: false }
  props.state.candidates.push(candidate); chosenId.value = candidate.id
  void nextTick(() => document.getElementById('candidate-quote')?.focus())
}
function save() {
  if (!chosen.value) return
  if (!quoteValid.value) { notice.value = copy.quoteMissing; return }
  chosen.value.checked = true; notice.value = copy.saved
}
function remove() {
  props.state.candidates = props.state.candidates.filter(item => item.id !== chosenId.value)
  chosenId.value = candidates.value[0]?.id ?? ''; notice.value = ''
  void nextTick(() => document.getElementById('add-candidate')?.focus())
}
function edit() { if (chosen.value) chosen.value.checked = false; notice.value = '' }
</script>
<template>
  <div>
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ copy.candidateTitle }}</h1><p>{{ copy.candidateHelp }}</p></div>
    <div class="source-tabs" role="group" aria-label="政策来源"><button v-for="item in state.sources" :key="item.id" :aria-pressed="item.id === state.sourceId" :class="{ selected: item.id === state.sourceId }" @click="state.sourceId = item.id">{{ item.title || '未命名来源' }}<span v-if="item.status === 'failed'"> · 获取失败</span></button></div>
    <div v-if="source" class="candidate-grid">
      <section class="material-panel original-panel"><div class="panel-heading"><h2>政策原文</h2><StatusTag :tone="source.status === 'failed' ? 'error' : 'neutral'">{{ sourceTypes[source.type] }}</StatusTag></div><p class="field-help">{{ source.title }} · {{ source.version || '版本未知' }}</p>
        <div v-if="source.status === 'failed'" class="notice" role="status"><p>{{ copy.sourceFailed }}</p><UiButton @click="source.status = source.text.trim() ? 'ready' : 'empty'">重试示例来源</UiButton></div>
        <div v-else class="policy-reading" tabindex="0" aria-label="政策原文阅读区"><span>{{ parts.before }}</span><mark v-if="parts.quote" id="candidate-quote-mark">{{ parts.quote }}</mark><span>{{ parts.after }}</span><p v-if="!source.text">{{ copy.missingText }}</p></div>
        <div class="source-notes"><span>正文节选</span><span>{{ copy.attachmentsUnknown }}</span><span>{{ copy.sourceScopeUnknown }}</span></div>
      </section>
      <section class="material-panel candidates-panel"><div class="panel-heading"><h2>候选声明 <span class="count">{{ candidates.length }}</span></h2><UiButton id="add-candidate" :disabled="source.status === 'failed' || state.candidates.length >= 100" @click="add">{{ copy.addCandidate }}</UiButton></div>
        <div class="candidate-list" aria-label="候选列表"><button v-for="candidate in candidates" :key="candidate.id" class="candidate-item" :class="{ selected: chosenId === candidate.id }" :aria-pressed="chosenId === candidate.id" @click="select(candidate)"><span class="candidate-item-heading"><strong>{{ dataTypes[candidate.dataType] }}</strong><StatusTag :tone="candidate.checked && quoteExists(candidate, state.sources) ? 'success' : 'wait'">{{ candidate.checked && quoteExists(candidate, state.sources) ? '已检查' : '待检查' }}</StatusTag></span><span class="candidate-quote-preview">{{ candidate.quote || copy.quoteMissing }}</span></button><p v-if="!candidates.length" class="field-help">{{ copy.emptyCandidates }}</p></div>
        <form v-if="chosen" class="candidate-editor" @submit.prevent="save">
          <UiField label="政策原句" id="candidate-quote" :error="!quoteValid ? copy.quoteMissing : ''" v-slot="{ describedby }"><textarea id="candidate-quote" v-model="chosen.quote" maxlength="5000" rows="3" :aria-describedby="describedby" :aria-invalid="!quoteValid" @input="edit" /></UiField>
          <div class="field-pair"><UiField label="数据类型" id="candidate-type"><select id="candidate-type" v-model="chosen.dataType" @change="edit"><option v-for="(text, id) in dataTypes" :key="id" :value="id">{{ text }}</option></select></UiField><UiField label="极性" id="candidate-polarity"><select id="candidate-polarity" v-model="chosen.polarity" @change="edit"><option value="AFFIRMED">肯定</option><option value="NEGATED">否定</option><option value="UNKNOWN">未知</option></select></UiField></div>
          <UiField label="主体" id="candidate-subject"><select id="candidate-subject" v-model="chosen.subject" @change="edit"><option value="APP">应用自身</option><option value="THIRD_PARTY">第三方</option><option value="UNKNOWN">未知</option></select></UiField>
          <UiField label="条件" id="candidate-condition"><input id="candidate-condition" v-model="chosen.condition" maxlength="1000" placeholder="未知或不适用" @input="edit" /></UiField>
          <div class="source-actions"><UiButton type="submit" variant="primary" :disabled="!quoteValid">{{ copy.saveCandidate }}</UiButton><UiButton variant="danger" @click="remove">{{ copy.deleteCandidate }}</UiButton></div><p v-if="notice" role="status" class="field-help">{{ notice }}</p><p class="field-help">{{ copy.storageHelp }}</p>
        </form>
      </section>
    </div>
    <div class="flow-footer"><UiButton @click="$emit('back')">{{ copy.editMaterials }}</UiButton><span class="field-help">{{ copy.reportHelp }}</span><UiButton variant="primary" @click="$emit('next')">{{ copy.nextProgress }}</UiButton></div>
  </div>
</template>
