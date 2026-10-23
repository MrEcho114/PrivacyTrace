<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiField from '../components/UiField.vue'
import UiIcon from '../components/UiIcon.vue'
import StatusTag from '../components/StatusTag.vue'
import MobileReadableName from '../components/MobileReadableName.vue'
import { copy, frontendCopy, policyStateFromSource } from '../copy'
import { dataTypes, quoteExists, sourceTypes } from '../workflow'
import type { Candidate, PolicySource, Workflow } from '../workflow'
const props = defineProps<{ state: Workflow; busy?: boolean; error?: string; typeLabels?: Record<string, string>; failedSourceIds?: string[]; mobile?: boolean; persist?: () => Promise<boolean> }>()
const emit = defineEmits<{ back: []; next: []; retrySource: [string]; retryModel: [string] }>()
const editorTypes = computed(() => props.state.example ? dataTypes : props.typeLabels ?? {})
const candidateLimit = computed(() => props.state.example ? 100 : 800)
const chosenId = ref('')
const mobileTab = ref<'original' | 'candidates'>('candidates')
const tabOrder: Array<'original' | 'candidates'> = ['original', 'candidates']
function focusTab(value: 'original' | 'candidates') {
  mobileTab.value = value
  void nextTick(() => document.getElementById('tab-' + value)?.focus())
}
// Roving tabindex with automatic activation: one tab stop, arrows move focus.
function onTabsKeydown(event: KeyboardEvent) {
  const index = tabOrder.indexOf(mobileTab.value)
  let next = -1
  if (event.key === 'ArrowRight') next = (index + 1) % tabOrder.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + tabOrder.length) % tabOrder.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabOrder.length - 1
  if (next < 0) return
  event.preventDefault()
  focusTab(tabOrder[next]!)
}
const chosen = computed(() => props.state.candidates.find(item => item.id === chosenId.value))
const source = computed(() => props.state.sources.find(item => item.id === props.state.sourceId))
const sourceVersionLabel = computed(() => {
  const version = source.value?.version?.trim()
  return version && version.toUpperCase() !== 'UNKNOWN' ? version : '版本未知'
})
const candidates = computed(() => props.state.candidates.filter(item => item.sourceId === props.state.sourceId))
// 移动端的来源切换是标签栏：短名保证可横滚且互不重复，完整标题紧挨在下方展示；
// 桌面保持原来的完整标题按钮，不改冻结布局。只有一份来源且标题很短时才直接用标题。
const sourceTabLabel = (item: PolicySource, index: number) => {
  const title = item.title || '未命名来源'
  if (!props.mobile) return title
  return props.state.sources.length > 1 || title.length > 10 ? `来源 ${index + 1}` : title
}
const extractionUnavailable = computed(() => !!source.value && (props.failedSourceIds?.includes(source.value.id) || source.value.modelAudit?.status === 'FAILED'))
const quoteValid = computed(() => !!chosen.value && quoteExists(chosen.value, props.state.sources))
const quoteError = computed(() => {
  if (quoteValid.value) return ''
  if (source.value?.status === 'failed') return copy.quoteUnavailable
  return chosen.value?.quote.trim() ? copy.quoteNotFound : copy.quoteRequired
})
const checkedCount = computed(() => candidates.value.filter(item => item.checked && quoteExists(item, props.state.sources)).length)
const parts = computed(() => {
  const text = source.value?.text ?? ''; const quote = chosen.value?.quote ?? ''
  const specified = chosen.value?.startOffset
  const codepointOffset = specified == null ? -1 : [...text].slice(0, specified).join('').length
  const offset = quoteValid.value ? codepointOffset >= 0 && text.slice(codepointOffset, codepointOffset + quote.length) === quote ? codepointOffset : text.indexOf(quote) : -1
  return offset < 0 ? { before: text, quote: '', after: '' } : { before: text.slice(0, offset), quote, after: text.slice(offset + quote.length) }
})
const notice = ref('')
const saving = ref(false)
const confirmingRemove = ref(false)
watch(chosenId, () => { confirmingRemove.value = false })
watch(() => props.state.sourceId, () => { chosenId.value = candidates.value[0]?.id ?? ''; notice.value = '' }, { immediate: true })
watch(() => props.state.candidates.length, () => { if (!chosen.value) chosenId.value = candidates.value[0]?.id ?? '' })
function select(candidate: Candidate) {
  chosenId.value = candidate.id; notice.value = ''
}
function askRemove() {
  confirmingRemove.value = true
  void nextTick(() => {
    document.getElementById('candidate-delete-confirm')?.scrollIntoView({ block: 'end', behavior: 'instant' })
    document.getElementById('confirm-delete-candidate')?.focus({ preventScroll: true })
  })
}
function cancelRemove() {
  confirmingRemove.value = false
  void nextTick(() => document.getElementById('delete-candidate')?.focus())
}
function locateQuote() { mobileTab.value = 'original'; void nextTick(() => document.getElementById('candidate-quote-mark')?.focus()) }
function add() {
  if (!source.value || props.state.candidates.length >= candidateLimit.value) return
  const candidate: Candidate = { id: crypto.randomUUID(), sourceId: source.value.id, quote: '', dataType: props.state.example ? 'location' : 'LOCATION', polarity: 'UNKNOWN', subject: 'UNKNOWN', condition: '', checked: false, action: 'UNKNOWN' }
  props.state.candidates.push(candidate); chosenId.value = candidate.id
  void nextTick(() => document.getElementById('candidate-quote')?.focus())
}
// "已检查" is part of the saved payload, but the success wording is not: the
// service may refuse this write (busy, stale revision, native bridge). Set the
// flag before persisting so an accepted snapshot carries it, then put the
// previous value back when the write did not happen. Restoring the old value
// matters for an already-checked candidate: #273 merges a changed `checked`
// back as a local edit, so a hard-coded false would turn a refused save into a
// sticky "待检查" that only a full re-read repairs. The edits stay in `state`
// either way, so the retry starts from what the reader typed.
async function save() {
  if (!chosen.value || saving.value) return
  if (!quoteValid.value) { notice.value = quoteError.value; return }
  if (props.state.example) { chosen.value.checked = true; notice.value = copy.saved; return }
  // Only the example may report success without persisting. A real flow that
  // forgets to wire `persist` must stay silent instead of claiming a save.
  if (!props.persist) return
  const target = chosen.value
  const wasChecked = target.checked
  target.checked = true
  notice.value = ''
  saving.value = true
  let persisted = false
  try { persisted = await props.persist() } catch { persisted = false } finally { saving.value = false }
  if (persisted) { notice.value = copy.saved; return }
  target.checked = wasChecked
  notice.value = copy.saveNotPersisted
}
function remove() {
  props.state.candidates = props.state.candidates.filter(item => item.id !== chosenId.value)
  if (!props.state.example && props.persist) void props.persist()
  chosenId.value = candidates.value[0]?.id ?? ''; notice.value = ''
  void nextTick(() => document.getElementById('add-candidate')?.focus())
}
function edit() { if (chosen.value) chosen.value.checked = false; notice.value = '' }
function editQuote() { if (chosen.value) chosen.value.startOffset = undefined; edit() }
</script>
<template>
  <div class="page page-candidates">
    <div v-if="!mobile" class="page-heading"><h1 id="page-title" tabindex="-1">{{ frontendCopy.pageTitles.candidates }}</h1><p>{{ copy.candidateHelp }}</p></div>
    <slot name="context" />
    <div class="source-tabs" role="group" aria-label="政策来源"><button v-for="(item, index) in state.sources" :key="item.id" :aria-pressed="item.id === state.sourceId" :aria-label="item.title || `来源 ${index + 1}`" :class="{ selected: item.id === state.sourceId }" @click="state.sourceId = item.id">{{ sourceTabLabel(item, index) }}<span v-if="item.status === 'failed'"> · 失败</span></button></div>
    <MobileReadableName v-if="mobile && source" :key="source.id" class="source-context-title" :value="source.title || '未命名来源'" />
    <p v-if="source" class="source-context" role="note" data-testid="candidate-source-context">
      <StatusTag :tone="source.status === 'failed' ? 'error' : 'neutral'">{{ sourceTypes[source.type] }}</StatusTag>
      <span>{{ sourceVersionLabel }}</span>
      <span class="source-context-meta"><span v-if="source.status === 'failed'">来源获取失败</span><span>{{ policyStateFromSource(source) }}</span><span>{{ copy.sourceScopeUnknown }}</span></span>
    </p>
    <p v-if="!state.example && extractionUnavailable" class="notice" role="status">当前来源的候选提取未完成，正文与已有候选仍保留。可在“政策原文”中选择“重新提取候选”，或手动添加；此状态不代表政策未声明。</p>
    <div v-if="source" class="mobile-panel-tabs" role="tablist" aria-label="检查候选视图" @keydown="onTabsKeydown">
      <button id="tab-original" type="button" role="tab" aria-controls="panel-original" :aria-selected="mobileTab === 'original'" :tabindex="mobileTab === 'original' ? 0 : -1" :class="{ selected: mobileTab === 'original' }" @click="mobileTab = 'original'">政策原文</button>
      <button id="tab-candidates" type="button" role="tab" aria-controls="panel-candidates" :aria-selected="mobileTab === 'candidates'" :tabindex="mobileTab === 'candidates' ? 0 : -1" :class="{ selected: mobileTab === 'candidates' }" @click="mobileTab = 'candidates'">候选声明 {{ candidates.length }}</button>
    </div>
    <div v-if="source" class="candidate-grid" :data-tab="mobileTab" :inert="busy || undefined" :aria-busy="busy || undefined">
      <section id="panel-original" class="material-panel original-panel" role="tabpanel" aria-labelledby="tab-original"><div class="panel-heading"><h2>政策原文</h2><StatusTag v-if="!mobile" :tone="source.status === 'failed' ? 'error' : 'neutral'">{{ sourceTypes[source.type] }}</StatusTag></div><UiButton v-if="!state.example" :disabled="busy || source.status === 'failed'" variant="quiet" @click="$emit('retryModel', source.id)">重新提取候选</UiButton>
        <div v-if="source.status === 'failed'" class="notice" role="status"><p>{{ state.example ? copy.sourceFailed : "这份来源未获得正文，可重试或返回材料页手动补入。" }}</p><UiButton v-if="state.example" @click="source.status = source.text.trim() ? 'ready' : 'empty'">重试示例来源</UiButton><UiButton v-else @click="$emit('retrySource', source.id)">重新获取来源</UiButton></div>
        <div v-else class="policy-reading" tabindex="0" aria-label="政策原文阅读区"><span>{{ parts.before }}</span><mark v-if="parts.quote" id="candidate-quote-mark" tabindex="-1">{{ parts.quote }}</mark><span>{{ parts.after }}</span><p v-if="!source.text">{{ copy.missingText }}</p></div>
        <div class="source-notes"><span>正文节选</span></div>
      </section>
      <section id="panel-candidates" class="material-panel candidates-panel priority-panel" role="tabpanel" aria-labelledby="tab-candidates"><div class="panel-heading"><h2 v-if="!mobile">候选声明<span class="count">{{ candidates.length }}</span></h2><p v-else class="candidate-summary" role="status">已检查 {{ checkedCount }}/{{ candidates.length }} 条</p><UiButton id="add-candidate" :variant="mobile ? 'quiet' : 'secondary'" :disabled="source.status === 'failed' || state.candidates.length >= candidateLimit" @click="add">{{ copy.addCandidate }}</UiButton></div>
        <p v-if="!mobile" class="candidate-summary" role="status">已检查 {{ checkedCount }}/{{ candidates.length }} 条<span> · 选择一条查看或修改</span></p>
        <div class="candidate-list" role="group" aria-label="候选列表"><button v-for="candidate in candidates" :key="candidate.id" class="candidate-item" :class="{ selected: chosenId === candidate.id }" :aria-pressed="chosenId === candidate.id" @click="select(candidate)"><span class="candidate-item-heading"><strong>{{ editorTypes[candidate.dataType] || candidate.dataType }}</strong><StatusTag :tone="candidate.checked && quoteExists(candidate, state.sources) ? 'success' : 'wait'">{{ candidate.checked && quoteExists(candidate, state.sources) ? '已检查' : '待检查' }}</StatusTag></span><span class="candidate-quote-preview">{{ candidate.quote || copy.quoteMissing }}</span><UiIcon v-if="mobile" name="chevron-right" class="candidate-chevron" /></button><p v-if="!candidates.length" class="field-help">{{ frontendCopy.facts.noCandidates }}</p></div>
        <p v-if="candidates.length" class="field-help">{{ frontendCopy.facts.candidateUnconfirmed }}</p>
        <form v-if="chosen" class="candidate-editor" @submit.prevent="save">
          <div class="candidate-editor-heading"><h3>编辑候选<span>{{ editorTypes[chosen.dataType] || chosen.dataType }}</span></h3><UiButton variant="quiet" :disabled="!quoteValid" @click="locateQuote">定位原句</UiButton></div>
          <p v-if="mobile && !state.example" class="field-help">保存候选会保存当前编辑，并将这条标为已检查；不会启动分析。逐条检查可选，全文和附件仍未复核。</p>
          <UiField label="政策原句" id="candidate-quote" :help="quoteValid ? copy.quoteMatched : ''" :error="quoteError" v-slot="{ describedby }"><textarea id="candidate-quote" v-model="chosen.quote" maxlength="5000" rows="3" :aria-describedby="describedby" :aria-invalid="!quoteValid" @input="editQuote" /></UiField>
          <div class="field-pair"><UiField label="数据类型" id="candidate-type"><select id="candidate-type" v-model="chosen.dataType" @change="edit"><option v-for="(text, id) in editorTypes" :key="id" :value="id">{{ text }}</option></select></UiField><UiField label="声明方式" id="candidate-polarity"><select id="candidate-polarity" v-model="chosen.polarity" @change="edit"><option value="AFFIRMED">肯定</option><option value="NEGATED">否定</option><option value="UNKNOWN">未知</option></select></UiField></div>
          <div class="field-pair"><UiField label="声明主体" id="candidate-subject"><select id="candidate-subject" v-model="chosen.subject" @change="edit"><option value="APP">应用自身</option><option value="THIRD_PARTY">第三方</option><option value="UNKNOWN">未知</option></select></UiField>
          <UiField label="条件" id="candidate-condition"><input id="candidate-condition" v-model="chosen.condition" maxlength="1000" placeholder="未知或不适用" @input="edit" /></UiField></div>
          <div v-if="!state.example" class="field-pair"><UiField label="声明动作" id="candidate-action"><select id="candidate-action" v-model="chosen.action" @change="edit"><option value="UNKNOWN">未知</option><option value="ACCESS">访问</option></select></UiField><UiField label="声明目的" id="candidate-purpose"><input id="candidate-purpose" v-model="chosen.purpose" maxlength="1000" @input="edit" /></UiField><UiField label="接收方" id="candidate-recipient"><input id="candidate-recipient" v-model="chosen.recipient" maxlength="1000" @input="edit" /></UiField></div>
          <div class="source-actions">
            <UiButton type="submit" :disabled="!quoteValid" :busy="saving">{{ copy.saveCandidate }}</UiButton>
            <UiButton v-if="!mobile" variant="danger" @click="remove">{{ copy.deleteCandidate }}</UiButton>
            <UiButton v-else-if="!confirmingRemove" id="delete-candidate" variant="quiet" class="m-delete-candidate" @click="askRemove">{{ copy.deleteCandidate }}</UiButton>
          </div>
          <div v-if="mobile && confirmingRemove" id="candidate-delete-confirm" class="m-candidate-delete-confirm">
            <p role="alert">删除当前「{{ editorTypes[chosen.dataType] || chosen.dataType }}」候选？政策原文和其他候选会保留。</p>
            <div class="source-actions"><UiButton id="confirm-delete-candidate" variant="danger" @click="remove">确认删除候选</UiButton><UiButton variant="quiet" @click="cancelRemove">取消删除</UiButton></div>
          </div>
          <p v-if="notice" :role="notice === copy.saveNotPersisted ? 'alert' : 'status'" class="field-help">{{ notice }}</p>
          <p v-if="!mobile && !state.example" class="field-help">保存后才会标为已检查；开始分析时保存本机快照。全文和附件仍未复核。</p>
        </form>
      </section>
    </div>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <div v-if="!mobile" class="flow-footer"><UiButton @click="$emit('back')">{{ copy.editMaterials }}</UiButton><span v-if="!state.example" class="field-help">未采用的候选可删除；未检查的候选会保留，启动分析不强制逐条检查，也不会自动提升核验状态。</span><UiButton variant="primary" :disabled="busy" :busy="busy" @click="$emit('next')">{{ state.example ? copy.nextProgress : "保存候选并开始分析" }}</UiButton></div>
  </div>
</template>
