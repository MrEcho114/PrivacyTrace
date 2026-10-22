<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import InstrumentPanel from './InstrumentPanel.vue'
import ReportMetrics from './ReportMetrics.vue'
import StaticBoundary from './StaticBoundary.vue'
import type { DesignReport } from './model'
const props = defineProps<{ report: DesignReport }>()
const selectedId = ref(props.report.findings[0]?.id)
const evidencePanel = ref<HTMLElement | null>(null)
const policyDetails = ref<HTMLDetailsElement | null>(null)
const lastTrigger = ref<HTMLButtonElement | null>(null)
watch(() => props.report, value => { selectedId.value = value.findings[0]?.id; lastTrigger.value = null })
const selected = computed(() => props.report.findings.find(item => item.id === selectedId.value))
const selectedEvidence = computed(() => props.report.evidence.filter(item => selected.value?.evidenceIds.includes(item.id)))
const types = computed(() => new Set(props.report.findings.map(item => item.dataType)).size)
async function showEvidence(id?: string, trigger?: EventTarget | null, policy = false) {
  selectedId.value = id ?? selectedId.value
  lastTrigger.value = trigger instanceof HTMLButtonElement ? trigger : null
  await nextTick()
  if (policy && policyDetails.value) policyDetails.value.open = true
  evidencePanel.value?.focus({ preventScroll: true })
  evidencePanel.value?.scrollIntoView({ block: 'start', behavior: 'instant' })
}
function returnToFinding() {
  lastTrigger.value?.focus()
  lastTrigger.value?.scrollIntoView({ block: 'center', behavior: 'instant' })
}
</script>
<template>
  <div class="pt-report">
    <header class="pt-report-heading">
      <p class="pt-eyebrow pt-code">REPORT / 04 <span>·</span> DATA COMPARISON</p>
      <div class="pt-title-row"><div><h1>隐私声明对照报告</h1><p class="pt-subtitle">{{ report.name }} · 版本 {{ report.version }} · 包名按需查看</p></div><StatusTag>{{ report.source }}</StatusTag></div>
    </header>
    <ReportMetrics :types="types" :sources="report.policySources.length" :evidence="report.evidence.length" />
    <div class="pt-report-columns">
      <InstrumentPanel title="对照结论 / FINDINGS" priority :label="String(report.findings.length).padStart(2, '0') + ' ITEMS ↓'">
        <div v-if="!report.findings.length" class="pt-empty"><h3>尚无对照结果</h3><p>这里是空状态示例。请在业务流程中导入材料并完成分析，再查看报告。</p></div>
        <ol v-else class="pt-findings"><li v-for="(finding, index) in report.findings" :key="finding.id">
          <div class="pt-tags"><StatusTag>{{ finding.conclusion }}</StatusTag><StatusTag>{{ finding.review }}</StatusTag></div>
          <h3>{{ String(index + 1).padStart(2, '0') }} / {{ finding.title }}</h3>
          <p>{{ finding.description }}</p>
          <button :id="finding.id" class="pt-text-link" @click="showEvidence(finding.id, $event.currentTarget)">查看对应证据 <span aria-hidden="true">→</span><span class="pt-sr-only">：{{ finding.title }}</span></button>
        </li></ol>
        <div class="pt-report-actions">
          <details class="pt-details"><summary>展开来源与技术信息</summary><dl class="pt-technical"><div><dt>应用包名</dt><dd>{{ report.packageName }}</dd></div><div><dt>送达方式</dt><dd>{{ report.delivery }}</dd></div><div><dt>数据来源</dt><dd>{{ report.source }}</dd></div></dl></details>
          <UiButton variant="primary" :disabled="!report.findings.length" @click="showEvidence(undefined, $event.currentTarget, true)">查看证据与政策原文 <span aria-hidden="true">→</span></UiButton>
        </div>
      </InstrumentPanel>
      <div ref="evidencePanel" class="pt-evidence-target" tabindex="-1" role="region" aria-label="证据详情" :aria-describedby="selected ? 'selected-evidence-heading' : undefined">
        <InstrumentPanel title="证据详情 / EVIDENCE" :label="selected ? 'ITEM ' + String(report.findings.indexOf(selected) + 1).padStart(2, '0') : 'NO SELECTION'">
          <dl class="pt-metadata"><div><dt>应用</dt><dd>{{ report.name }}</dd></div><div><dt>来源</dt><dd>{{ report.policySources.map(item => item.title).join('、') || '尚无政策来源' }}</dd></div><div><dt>捕获方式</dt><dd>仅静态分析 / 示例</dd></div><div><dt>报告覆盖</dt><dd>{{ report.coverage }}</dd></div></dl>
          <StaticBoundary />
          <template v-if="selected"><h3 id="selected-evidence-heading" class="pt-evidence-title">{{ selected.title }}的对应证据</h3>
            <ul class="pt-evidence-list"><li v-for="evidence in selectedEvidence" :key="evidence.id"><strong>{{ evidence.kind }}</strong><p class="pt-locator">{{ evidence.locator }}</p><p>{{ evidence.excerpt }}</p></li></ul>
            <p v-if="!selectedEvidence.length">本项尚无可定位证据，需补充材料。</p>
          </template><p v-else class="pt-empty">尚无证据。未知与未检查项继续保留。</p>
          <details ref="policyDetails" class="pt-policy-details"><summary>政策原文与适用边界</summary>
            <p v-for="policy in report.policySources" :key="policy.id">{{ policy.text }}</p><p v-if="!report.policySources.length">尚无政策原文。</p>
            <dl class="pt-technical"><div><dt>复核</dt><dd>{{ report.review }}</dd></div><div><dt>提取</dt><dd>{{ report.extraction }}</dd></div><div><dt>完整性</dt><dd>{{ report.completeness }}</dd></div><div><dt>附件</dt><dd>{{ report.attachments }}</dd></div></dl>
          </details>
          <button v-if="lastTrigger" class="pt-text-link pt-return" @click="returnToFinding">返回刚才的操作 <span aria-hidden="true">↑</span></button>
          <p class="pt-code pt-evidence-foot">来源文本已保留 / 未知仍按未知展示</p>
        </InstrumentPanel>
      </div>
    </div>
  </div>
</template>
