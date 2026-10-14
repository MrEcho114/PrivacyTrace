<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiField from '../components/UiField.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy } from '../copy'
import { dataTypes, quoteExists, sourceTypes } from '../workflow'
import type { Candidate, Workflow } from '../workflow'
const props = defineProps<{ state: Workflow; busy?: boolean; typeLabels?: Record<string, string> }>()
const emit = defineEmits<{ back: []; next: []; retrySource: [string]; retryModel: [string]; persistCandidates: [] }>()
const editorTypes = computed(() => props.state.example ? dataTypes : props.typeLabels ?? {})
const chosenId = ref('')
const chosen = computed(() => props.state.candidates.find(item => item.id === chosenId.value))
const source = computed(() => props.state.sources.find(item => item.id === props.state.sourceId))
const candidates = computed(() => props.state.candidates.filter(item => item.sourceId === props.state.sourceId))
const quoteValid = computed(() => !!chosen.value && quoteExists(chosen.value, props.state.sources))
const quoteError = computed(() => {
  if (quoteValid.value) return ''
  if (source.value?.status === 'failed') return copy.quoteUnavailable
  return chosen.value?.quote.trim() ? copy.quoteNotFound : copy.quoteRequired
})
const checkedCount = computed(() => candidates.value.filter(item => item.checked && quoteExists(item, props.state.sources)).length)
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
}
function locateQuote() { void nextTick(() => document.getElementById('candidate-quote-mark')?.focus()) }
function add() {
  if (!source.value || props.state.candidates.length >= 100) return
  const candidate: Candidate = { id: crypto.randomUUID(), sourceId: source.value.id, quote: '', dataType: props.state.example ? 'location' : 'LOCATION', polarity: 'UNKNOWN', subject: 'UNKNOWN', condition: '', checked: false, action: 'UNKNOWN' }
  props.state.candidates.push(candidate); chosenId.value = candidate.id
  void nextTick(() => document.getElementById('candidate-quote')?.focus())
}
function save() {
  if (!chosen.value) return
  if (!quoteValid.value) { notice.value = quoteError.value; return }
  chosen.value.checked = true; notice.value = copy.saved
  if (!props.state.example) emit('persistCandidates')
}
function remove() {
  props.state.candidates = props.state.candidates.filter(item => item.id !== chosenId.value)
  if (!props.state.example) emit('persistCandidates')
  chosenId.value = candidates.value[0]?.id ?? ''; notice.value = ''
  void nextTick(() => document.getElementById('add-candidate')?.focus())
}
function edit() { if (chosen.value) chosen.value.checked = false; notice.value = '' }
</script>
<template>
  <div>
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ copy.candidateTitle }}</h1><p>{{ copy.candidateHelp }}</p></div>
    <div class="source-tabs" role="group" aria-label="政策来源"><button v-for="item in state.sources" :key="item.id" :aria-pressed="item.id === state.sourceId" :class="{ selected: item.id === state.sourceId }" @click="state.sourceId = item.id">{{ item.title || '未命名来源' }}<span v-if="item.status === 'failed'"> · 获取失败</span></button></div>
    <div v-if="source" class="candidate-grid" :inert="busy || undefined">
      <section class="material-panel original-panel"><div class="panel-heading"><h2>政策原文</h2><StatusTag :tone="source.status === 'failed' ? 'error' : 'neutral'">{{ sourceTypes[source.type] }}</StatusTag></div><p class="field-help">{{ source.title }} · {{ source.version || '版本未知' }}</p><UiButton v-if="!state.example" :disabled="busy || source.status === 'failed'" variant="quiet" @click="$emit('retryModel', source.id)">重新提取候选</UiButton>
        <div v-if="source.status === 'failed'" class="notice" role="status"><p>{{ state.example ? copy.sourceFailed : "这份来源未获得正文，可重试或返回材料页手动补入。" }}</p><UiButton v-if="state.example" @click="source.status = source.text.trim() ? 'ready' : 'empty'">重试示例来源</UiButton><UiButton v-else @click="$emit('retrySource', source.id)">重新获取来源</UiButton></div>
        <div v-else class="policy-reading" tabindex="0" aria-label="政策原文阅读区"><span>{{ parts.before }}</span><mark v-if="parts.quote" id="candidate-quote-mark" tabindex="-1">{{ parts.quote }}</mark><span>{{ parts.after }}</span><p v-if="!source.text">{{ copy.missingText }}</p></div>
        <div class="source-notes"><span>正文节选</span><span>{{ copy.attachmentsUnknown }}</span><span>{{ copy.sourceScopeUnknown }}</span></div>
      </section>
      <section class="material-panel candidates-panel"><div class="panel-heading"><h2>候选声明 <span class="count">{{ candidates.length }}</span></h2><UiButton id="add-candidate" :disabled="source.status === 'failed' || state.candidates.length >= 100" @click="add">{{ copy.addCandidate }}</UiButton></div>
        <p class="candidate-summary" role="status">已检查 {{ checkedCount }} / {{ candidates.length }} 条<span>选择一条查看和修改</span></p>
        <div class="candidate-list" aria-label="候选列表"><button v-for="candidate in candidates" :key="candidate.id" class="candidate-item" :class="{ selected: chosenId === candidate.id }" :aria-pressed="chosenId === candidate.id" @click="select(candidate)"><span class="candidate-item-heading"><strong>{{ editorTypes[candidate.dataType] || candidate.dataType }}</strong><StatusTag :tone="candidate.checked && quoteExists(candidate, state.sources) ? 'success' : 'wait'">{{ candidate.checked && quoteExists(candidate, state.sources) ? '已检查' : '待检查' }}</StatusTag></span><span class="candidate-quote-preview">{{ candidate.quote || copy.quoteMissing }}</span></button><p v-if="!candidates.length" class="field-help">{{ copy.emptyCandidates }}</p></div>
        <form v-if="chosen" class="candidate-editor" @submit.prevent="save">
          <div class="candidate-editor-heading"><h3>编辑候选<span>{{ editorTypes[chosen.dataType] || chosen.dataType }}</span></h3><UiButton variant="quiet" :disabled="!quoteValid" @click="locateQuote">定位原句</UiButton></div>
          <UiField label="政策原句" id="candidate-quote" :help="quoteValid ? copy.quoteMatched : ''" :error="quoteError" v-slot="{ describedby }"><textarea id="candidate-quote" v-model="chosen.quote" maxlength="5000" rows="3" :aria-describedby="describedby" :aria-invalid="!quoteValid" @input="edit" /></UiField>
          <div class="field-pair"><UiField label="数据类型" id="candidate-type"><select id="candidate-type" v-model="chosen.dataType" @change="edit"><option v-for="(text, id) in editorTypes" :key="id" :value="id">{{ text }}</option></select></UiField><UiField label="声明方式" id="candidate-polarity"><select id="candidate-polarity" v-model="chosen.polarity" @change="edit"><option value="AFFIRMED">肯定</option><option value="NEGATED">否定</option><option value="UNKNOWN">未知</option></select></UiField></div>
          <div class="field-pair"><UiField label="声明主体" id="candidate-subject"><select id="candidate-subject" v-model="chosen.subject" @change="edit"><option value="APP">应用自身</option><option value="THIRD_PARTY">第三方</option><option value="UNKNOWN">未知</option></select></UiField>
          <UiField label="条件" id="candidate-condition"><input id="candidate-condition" v-model="chosen.condition" maxlength="1000" placeholder="未知或不适用" @input="edit" /></UiField></div>
          <div v-if="!state.example" class="field-pair"><UiField label="声明动作" id="candidate-action"><select id="candidate-action" v-model="chosen.action" @change="edit"><option value="UNKNOWN">未知</option><option value="ACCESS">访问</option></select></UiField><UiField label="声明目的" id="candidate-purpose"><input id="candidate-purpose" v-model="chosen.purpose" maxlength="1000" @input="edit" /></UiField><UiField label="接收方" id="candidate-recipient"><input id="candidate-recipient" v-model="chosen.recipient" maxlength="1000" @input="edit" /></UiField></div><div class="source-actions"><UiButton type="submit" variant="primary" :disabled="!quoteValid">{{ copy.saveCandidate }}</UiButton><UiButton variant="danger" @click="remove">{{ copy.deleteCandidate }}</UiButton></div><p v-if="notice" role="status" class="field-help">{{ notice }}</p><p class="field-help">{{ state.example ? copy.storageHelp : "保存后才标为候选已检查；进入分析时保存本机快照。全文和附件仍未复核。" }}</p>
        </form>
      </section>
    </div>
    <div class="flow-footer"><UiButton @click="$emit('back')">{{ copy.editMaterials }}</UiButton><span class="field-help">{{ state.example ? copy.reportHelp : "未采用的候选请删除；其余逐条检查。空候选不代表政策未声明。" }}</span><UiButton variant="primary" :disabled="busy" :busy="busy" @click="$emit('next')">{{ state.example ? copy.nextProgress : "保存候选并开始分析" }}</UiButton></div>
  </div>
</template>
