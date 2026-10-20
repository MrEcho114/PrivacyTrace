<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy } from '../copy'
import { exampleRows, exampleSources } from '../workflow'
import type { Workflow } from '../workflow'
const props = defineProps<{ state: Workflow }>()
defineEmits<{ edit: [] }>()
const selected = computed(() => exampleRows.find(item => item.id === props.state.evidenceId))
const rows = computed(() => exampleRows.filter(item => props.state.filter === 'all' || item.source === props.state.filter))
const visibleIds = computed<Set<string>>(() => new Set(rows.value.map(item => item.id)))
const selectedSource = computed(() => exampleSources.find(item => item.id === selected.value?.source))
const fullText = ref(false)
watch(() => props.state.filter, () => {
  if (props.state.evidenceId && !visibleIds.value.has(props.state.evidenceId)) {
    props.state.evidenceId = ''
    fullText.value = false
  }
})
const originButton = ref<HTMLElement | null>(null)
const inlineEvidence = ref(false)
let narrowQuery: MediaQueryList | null = null
function syncNarrow(event: MediaQueryList | MediaQueryListEvent) { inlineEvidence.value = event.matches }
onMounted(() => {
  narrowQuery = window.matchMedia('(max-width: 560px)')
  syncNarrow(narrowQuery)
  narrowQuery.addEventListener('change', syncNarrow)
})
onBeforeUnmount(() => { narrowQuery?.removeEventListener('change', syncNarrow) })
function open(id: string, event: Event) {
  if (inlineEvidence.value && props.state.evidenceId === id) { close(); return }
  originButton.value = event.currentTarget as HTMLElement; props.state.evidenceId = id; fullText.value = false
  void nextTick(() => document.getElementById('example-evidence-title')?.focus())
}
function close() {
  props.state.evidenceId = ''
  void nextTick(() => {
    const target = originButton.value?.isConnected ? originButton.value : document.getElementById('page-title')
    target?.focus()
  })
}
</script>
<template>
  <div>
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ copy.reportTitle }}</h1><p>{{ copy.reportDescription }}</p></div>
    <div class="report-summary"><div class="report-identity"><div class="sample-monogram" aria-hidden="true">纸</div><div><h2>纸舟地图</h2><p>com.paperboat.example · 示例 1.0</p></div></div><StatusTag tone="info">{{ copy.fixedReport }}</StatusTag></div>
    <p class="field-help">{{ copy.reportHelp }}</p>
    <div class="report-source-summary"><div v-for="source in state.sources" :key="source.id"><h3>{{ source.title || '未命名来源' }}</h3><StatusTag v-if="source.status === 'failed'" tone="error">{{ copy.sourceFailed }}</StatusTag><p>{{ source.status === 'failed' ? '此来源保留失败状态' : '本次体验材料' }} · {{ source.version || '版本未知' }}</p><div class="source-notes"><span>未完成全文复核</span><span>{{ copy.attachmentsUnknown }}</span></div></div></div>
    <section class="material-panel"><div class="panel-heading"><h2>静态线索与声明</h2><label class="report-filter">来源<select v-model="state.filter" aria-label="报告来源筛选"><option value="all">全部来源</option><option value="host">应用官网</option><option value="sdk">SDK 服务</option></select></label></div><p class="field-help">固定报告的政策依据保留原始示例版本；上方为本次体验材料的状态。</p>
      <div class="table-scroll" tabindex="0" aria-label="证据对照表"><table class="comparison-table"><thead><tr><th>数据类型</th><th>静态线索</th><th>政策来源</th><th>对照结果</th><th>依据</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td data-label="数据类型"><strong>{{ row.type }}</strong></td><td data-label="静态线索">{{ row.signal }}</td><td data-label="政策来源">{{ row.source === 'host' ? '应用官网' : 'SDK 服务' }}</td><td data-label="对照结果"><StatusTag :tone="row.tone">{{ row.status }}</StatusTag></td><td data-label="依据"><UiButton variant="quiet" :aria-expanded="state.evidenceId === row.id" aria-controls="example-evidence" :aria-label="`${copy.viewEvidence}：${row.type}`" @click="open(row.id, $event)"><span class="mobile-toggle">{{ state.evidenceId === row.id ? '收起详情' : copy.viewEvidence }}</span><span class="desktop-toggle">{{ copy.viewEvidence }}</span></UiButton></td><td v-if="inlineEvidence && selected && selected.id === row.id" class="row-evidence" colspan="5"><div id="example-evidence" class="example-evidence"><div class="panel-heading"><h2 id="example-evidence-title" tabindex="-1">{{ selected.type }}的依据</h2><UiButton variant="quiet" @click="close">{{ copy.close }}</UiButton></div><p class="evidence-explanation">{{ selected.explanation }}</p><div class="evidence-grid"><article class="evidence-card"><h3>代码位置</h3><p class="locator">{{ selected.locator }}</p><pre>{{ selected.code }}</pre><StatusTag>人工构造的静态片段</StatusTag></article><article class="evidence-card"><h3>政策原句</h3><p class="field-help">{{ selectedSource?.title }} · {{ selectedSource?.version }}</p><blockquote v-if="selected.quote">{{ selected.quote }}</blockquote><p v-else>{{ copy.quoteMissing }}</p><UiButton variant="quiet" @click="fullText = !fullText">{{ fullText ? '收起正文' : '查看示例全文' }}</UiButton><div v-if="fullText" class="policy-reading"><template v-if="selected.quote && selectedSource?.text.includes(selected.quote)"><span>{{ selectedSource.text.split(selected.quote)[0] }}</span><mark>{{ selected.quote }}</mark><span>{{ selectedSource.text.split(selected.quote).slice(1).join(selected.quote) }}</span></template><span v-else>{{ selectedSource?.text }}</span></div></article></div></div></td></tr></tbody></table></div>
      <p v-if="!rows.length" class="field-help">当前没有匹配条目。<UiButton @click="state.filter = 'all'">清除筛选</UiButton></p>
    </section>
    <section v-if="selected && !inlineEvidence" id="example-evidence" class="material-panel example-evidence"><div class="panel-heading"><h2 id="example-evidence-title" tabindex="-1">{{ selected.type }}的依据</h2><UiButton variant="quiet" @click="close">{{ copy.close }}</UiButton></div><p class="evidence-explanation">{{ selected.explanation }}</p>
      <div class="evidence-grid"><article class="evidence-card"><h3>代码位置</h3><p class="locator">{{ selected.locator }}</p><pre>{{ selected.code }}</pre><StatusTag>人工构造的静态片段</StatusTag></article><article class="evidence-card"><h3>政策原句</h3><p class="field-help">{{ selectedSource?.title }} · {{ selectedSource?.version }}</p><blockquote v-if="selected.quote">{{ selected.quote }}</blockquote><p v-else>{{ copy.quoteMissing }}</p><UiButton variant="quiet" @click="fullText = !fullText">{{ fullText ? '收起正文' : '查看示例全文' }}</UiButton><div v-if="fullText" class="policy-reading"><template v-if="selected.quote && selectedSource?.text.includes(selected.quote)"><span>{{ selectedSource.text.split(selected.quote)[0] }}</span><mark>{{ selected.quote }}</mark><span>{{ selectedSource.text.split(selected.quote).slice(1).join(selected.quote) }}</span></template><span v-else>{{ selectedSource?.text }}</span></div></article></div>
    </section>
    <div class="flow-footer"><UiButton @click="$emit('edit')">返回候选</UiButton><span class="field-help">{{ copy.reportHelp }}</span></div>
  </div>
</template>
