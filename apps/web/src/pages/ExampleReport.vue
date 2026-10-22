<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy, frontendCopy, policyStateLine } from '../copy'
import { exampleRows, exampleSources } from '../workflow'
import type { Workflow } from '../workflow'
const props = defineProps<{ state: Workflow }>()
defineEmits<{ edit: [] }>()
type ExampleRow = (typeof exampleRows)[number]
type ExampleSource = (typeof exampleSources)[number]
// Fixed example report: the rows and sources are synthetic, never inferred.
const selected = computed(() => exampleRows.find(item => item.id === props.state.evidenceId))
const rows = computed(() => exampleRows.filter(item => props.state.filter === 'all' || item.source === props.state.filter))
const visibleIds = computed<Set<string>>(() => new Set(rows.value.map(item => item.id)))
// Entry shows the first visible item until the reader picks another one.
const activeFinding = computed<ExampleRow | undefined>(() => selected.value ?? rows.value[0])
const activeSource = computed<ExampleSource | undefined>(() => exampleSources.find(item => item.id === activeFinding.value?.source))
const rowNumber = (row: ExampleRow) => String(exampleRows.findIndex(item => item.id === row.id) + 1).padStart(2, '0')
const evidenceCount = (row: ExampleRow) => row.quote ? 2 : 1
const sourceLabel = (id: string) => id === 'host' ? '应用官网' : 'SDK 服务'
const sourceStateLine = (source: Workflow['sources'][number]) => policyStateLine({ review_status: 'UNREVIEWED', completeness: source.complete ? 'COMPLETE' : null, attachments_status: 'NOT_CHECKED' })
const sourceSummary = computed(() => props.state.sources.map(source => ({ id: source.id, title: source.title || '未命名来源', version: source.version || '版本未知', failed: source.status === 'failed', stateLine: sourceStateLine(source) })))
const materialState = computed(() => props.state.sources[0] ? sourceStateLine(props.state.sources[0]) : policyStateLine({ review_status: 'UNREVIEWED', attachments_status: 'NOT_CHECKED' }))
const activePermission = computed(() => !!activeFinding.value && activeFinding.value.code.trimStart().startsWith('<uses-permission'))
const fullText = ref(false)
watch(() => props.state.filter, () => {
  if (props.state.evidenceId && !visibleIds.value.has(props.state.evidenceId)) {
    props.state.evidenceId = ''
    fullText.value = false
  }
})
const originButton = ref<HTMLElement | null>(null)
const evidenceRegion = ref<HTMLElement | null>(null)
const inlineEvidence = ref(false)
let narrowQuery: MediaQueryList | null = null
function syncNarrow(event: MediaQueryList | MediaQueryListEvent) { inlineEvidence.value = event.matches }
onMounted(() => {
  narrowQuery = window.matchMedia('(max-width: 896px)')
  syncNarrow(narrowQuery)
  narrowQuery.addEventListener('change', syncNarrow)
})
onBeforeUnmount(() => { narrowQuery?.removeEventListener('change', syncNarrow) })
function open(id: string | undefined, event?: Event, policy = false) {
  if (!id) return
  if (event?.currentTarget) originButton.value = event.currentTarget as HTMLElement
  props.state.evidenceId = id; fullText.value = policy
  void nextTick(() => {
    document.getElementById('example-evidence-title')?.focus()
    // Same evidence region at every width; only the stacked layout needs the page
    // to scroll to it, the desktop columns already show it beside the entry.
    if (inlineEvidence.value) evidenceRegion.value?.scrollIntoView({ block: 'start' })
  })
}
function returnToTrigger() {
  const target = originButton.value
  if (target?.isConnected) target.focus()
  else document.getElementById('page-title')?.focus()
}
</script>
<template>
  <div class="page page-report">
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ frontendCopy.reportTitle }}</h1><p>{{ frontendCopy.reportScope }}</p></div>
    <p class="report-boundary">{{ frontendCopy.facts.staticRuntime }}</p>
    <div class="report-summary">
      <div class="report-identity"><div class="sample-monogram" aria-hidden="true">纸</div><div><h2>纸舟地图</h2><p>com.paperboat.example · 示例 1.0</p></div></div>
      <div class="report-source-state"><p class="field-help">{{ state.sources.length }} 份政策来源</p><p>{{ materialState }}</p></div>
    </div>
    <div class="report-columns" :data-layout="inlineEvidence ? 'stacked' : 'columns'">
      <section class="report-conclusions priority-panel" aria-labelledby="report-conclusions-title">
        <div class="panel-heading"><h2 id="report-conclusions-title">{{ frontendCopy.comparisonTitle }}</h2><label class="report-filter">来源<select v-model="state.filter" aria-label="报告来源筛选"><option value="all">全部来源</option><option value="host">应用官网</option><option value="sdk">SDK 服务</option></select></label></div>
        <table class="comparison-table"><thead><tr><th scope="col">{{ frontendCopy.table.dataType }}</th><th scope="col">{{ frontendCopy.table.evidence }}</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id" :class="{ 'is-selected': activeFinding?.id === row.id }"><td class="finding-type" data-label="数据类型"><span class="finding-number" aria-hidden="true">{{ rowNumber(row) }}</span><h3>{{ row.type }}</h3><p class="finding-meta">{{ sourceLabel(row.source) }} · {{ evidenceCount(row) }} 条关联证据</p><StatusTag :tone="row.tone">结论：{{ row.status }}</StatusTag></td><td class="finding-evidence" data-label="证据"><button class="text-link" :aria-pressed="activeFinding?.id === row.id" aria-controls="example-evidence" :aria-label="activeFinding?.id === row.id ? `当前证据：「${row.type}」` : `查看「${row.type}」证据`" @click="open(row.id, $event)">{{ activeFinding?.id === row.id ? '当前证据' : '查看证据' }}</button></td></tr></tbody></table>
        <p v-if="!rows.length" class="field-help">当前没有匹配条目。 <UiButton @click="state.filter = 'all'">清除筛选</UiButton></p>
        <p class="comparison-scope">{{ frontendCopy.comparisonScope }}</p>
        <div class="report-action"><p class="action-context">{{ activeFinding ? '当前对象：' + rowNumber(activeFinding) + ' / ' + activeFinding.type : '尚无条目可阅读' }}</p><UiButton variant="primary" :disabled="!activeFinding" aria-controls="example-evidence" @click="open(activeFinding?.id, $event, true)"><span class="action-label">{{ activeFinding ? `查看「${activeFinding.type}」证据与政策原文` : '查看证据与政策原文' }}</span></UiButton></div>
      </section>
      <section id="example-evidence" ref="evidenceRegion" class="report-evidence example-evidence" tabindex="-1" role="region" aria-label="证据详情">
        <div class="panel-heading"><h2 id="example-evidence-title" tabindex="-1">{{ activeFinding ? activeFinding.type + '的对应证据' : '证据详情' }}</h2></div>
        <div class="report-evidence-body">
        <template v-if="activeFinding"><div class="selected-context"><p class="field-help">对应条目 {{ rowNumber(activeFinding) }} · {{ evidenceCount(activeFinding) }} 条关联证据</p><p>结论：{{ activeFinding.status }}</p><p>{{ activeFinding.explanation }}</p></div>
          <div class="evidence-grid"><article class="evidence-card"><h3>代码位置</h3><p class="locator">{{ activeFinding.locator }}</p><pre>{{ activeFinding.code }}</pre><StatusTag>人工构造的静态片段</StatusTag><p v-if="activePermission" class="field-help">{{ frontendCopy.facts.permission }}</p></article><article class="evidence-card"><h3>政策原句</h3><p class="field-help">{{ activeSource?.title }} · {{ activeSource?.version }}</p><blockquote v-if="activeFinding.quote">{{ activeFinding.quote }}</blockquote><p v-else>{{ copy.quoteMissing }}</p><UiButton variant="quiet" :aria-expanded="fullText" @click="fullText = !fullText">{{ fullText ? '收起正文' : '查看示例全文' }}</UiButton><div v-if="fullText" class="policy-reading"><template v-if="activeFinding.quote && activeSource?.text.includes(activeFinding.quote)"><span>{{ activeSource.text.split(activeFinding.quote)[0] }}</span><mark>{{ activeFinding.quote }}</mark><span>{{ activeSource.text.split(activeFinding.quote).slice(1).join(activeFinding.quote) }}</span></template><span v-else>{{ activeSource?.text }}</span></div></article></div>
          <p v-if="originButton" class="field-help"><button class="text-link" @click="returnToTrigger">返回刚才的操作</button></p>
        </template>
        <p v-else class="field-help">尚无条目可阅读。未知与未检查项继续保留。</p>
        <details class="report-info"><summary>报告来源与技术信息</summary><dl><div v-for="source in sourceSummary" :key="source.id"><dt>{{ source.title }}</dt><dd>{{ source.version }} · {{ source.stateLine }}<span v-if="source.failed"> · {{ copy.sourceFailed }}</span></dd></div><div><dt>材料</dt><dd>人工构造示例</dd></div><div><dt>应用包名</dt><dd>com.paperboat.example</dd></div></dl></details>
        </div>
      </section>
    </div>
    <div class="flow-footer"><UiButton @click="$emit('edit')">返回候选</UiButton><span class="field-help">{{ copy.reportHelp }}</span></div>
  </div>
</template>
