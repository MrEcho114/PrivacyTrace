<script setup lang="ts">
// Evidence preview extracted from App.vue so the desktop report keeps the inline
// panel and the Tauri mobile shell can render exactly the same evidence body in a
// bottom sheet (issue #144). Display logic lives here once; the host only decides
// where the panel appears and what happens on close / policy jump.
import { computed, ref, watch } from 'vue'
import type { DemoReport, Evidence, MatchStatus, PrivacyIssue, Report, Taxonomy } from '../types'
import { frontendCopy, policyStateLine } from '../copy'

const props = withDefaults(defineProps<{
  issue: PrivacyIssue
  report: Report | DemoReport
  taxonomy: Taxonomy | null
  statusLabels: Record<MatchStatus, string>
  kindLabels: Record<string, string>
  sourceLabels: Record<string, string>
  /** Desktop keeps the panel heading; the sheet host owns the visible title. */
  heading?: boolean
}>(), { heading: true })
const emit = defineEmits<{ close: []; openPolicy: [string] }>()

const label = (id: string) => props.taxonomy?.data_types.find(item => item.id === id)?.label ?? id
const documentFor = (item: Evidence) => props.report.policy_documents.find(doc => doc.id === item.document_id)
const sentenceContext = (item: Evidence) => {
  const text = documentFor(item)?.artifact.text
  if (!text || item.start_offset == null || item.end_offset == null) return null
  const points = Array.from(text)
  const start = Math.max(0, item.start_offset)
  const end = Math.max(start, Math.min(points.length, item.end_offset))
  return {
    before: points.slice(Math.max(0, start - 100), start).join(''),
    sentence: points.slice(start, end).join(''),
    after: points.slice(end, Math.min(points.length, end + 100)).join(''),
  }
}
const selectedEvidence = computed(() => props.report.evidence.filter(item => props.issue.evidence_ids.includes(item.id)))
const issueNumber = computed(() => {
  const index = props.report.result.issues.findIndex(item => item.id === props.issue.id)
  return index < 0 ? '--' : String(index + 1).padStart(2, '0')
})
// The unified source-state line is generated from the document's own values; a
// fetched body never upgrades the review state and missing values stay unknown.
const docState = (doc?: Report['policy_documents'][number]) => policyStateLine(doc ?? {})

// Candidate clauses are navigation aids, not evaluator-confirmed evidence or matches.
const CANDIDATE_PAGE_SIZE = 20
const candidatePage = ref(0)
const candidateClaims = computed(() => {
  const report = props.report
  if (report.demo) return []
  return report.policy_claims.filter(claim => claim.data_type === props.issue.data_type)
})
const candidatePageCount = computed(() => Math.ceil(candidateClaims.value.length / CANDIDATE_PAGE_SIZE))
const relatedCandidates = computed(() => {
  const report = props.report
  if (report.demo) return []
  return candidateClaims.value
    .slice(candidatePage.value * CANDIDATE_PAGE_SIZE, (candidatePage.value + 1) * CANDIDATE_PAGE_SIZE)
    .map(claim => ({
      claim,
      document: report.policy_documents.find(doc => doc.id === claim.document_id),
      evidence: report.evidence.filter(item => item.kind === 'POLICY_SENTENCE'
        && item.document_id === claim.document_id && claim.evidence_ids.includes(item.id)),
    }))
})
// Only the selected issue / report switch resets the candidate page.
watch(() => [props.issue, props.report], () => { candidatePage.value = 0 })
</script>

<template>
  <section id="evidence-panel" class="evidence-panel" :class="{ 'm-evidence-panel': !heading }" tabindex="-1">
    <div v-if="heading" class="section-heading"><h2>{{ label(issue.data_type) }} · {{ statusLabels[issue.status] }}</h2><button @click="emit('close')">返回刚才的操作</button></div>
    <div class="evidence-context">
      <p class="evidence-context-meta">对应条目 {{ issueNumber }} · {{ label(issue.data_type) }} · {{ issue.evidence_ids.length }} 条关联证据</p>
      <p class="evidence-context-conclusion">对照结论：{{ statusLabels[issue.status] }}{{ issue.requires_review ? ' · 条目待复核' : '' }}</p>
    </div>
    <p class="explanation">{{ issue.explanation }}</p>
    <p v-if="issue.status === 'NOT_DECLARED'" class="demo-note">{{ frontendCopy.facts.notDeclared }} 下面保留完整政策及这些状态。</p>
    <div class="evidence-grid"><article v-for="item in selectedEvidence" :key="item.id" class="evidence-card">
      <div class="section-heading"><strong>{{ kindLabels[item.kind] }}</strong><span class="subtle">{{ item.id }}</span></div>
      <p class="locator">{{ item.source }} · {{ item.locator }}</p>
      <template v-if="item.api_call"><p class="hash">目标：{{ item.api_call.target_descriptor }}</p><p class="subtle">规则 {{ item.api_call.rule_id }} · {{ item.api_call.ruleset_version }}；静态上下文 {{ JSON.stringify(item.api_call.context) }}</p><p class="subtle">字节码定位保留调用方法、DEX 与指令偏移；未提供 JADX Java 源码时以字节码作为依据。</p></template>
      <p v-if="item.kind === 'POLICY_SENTENCE'" class="subtle">原文位置：[{{ item.start_offset }}, {{ item.end_offset }})，按 Unicode 码点计数。</p>
      <pre v-if="sentenceContext(item)">{{ sentenceContext(item)?.before }}<mark>{{ sentenceContext(item)?.sentence }}</mark>{{ sentenceContext(item)?.after }}</pre>
      <pre v-else-if="item.excerpt">{{ item.excerpt }}</pre>
      <p v-else class="subtle">本条引用政策快照，全文见下方。</p>
      <button v-if="item.document_id && documentFor(item)" class="policy-jump-btn" @click="emit('openPolicy', item.document_id!)">完整政策与适用边界</button>
    </article></div>
    <section v-if="relatedCandidates.length" class="candidate-clauses">
      <h3>相关候选条款（未确认匹配）</h3>
      <nav aria-label="候选条款分页" class="candidate-nav">
        <span>共 {{ candidateClaims.length }} 条 · 第 {{ candidatePage + 1 }} / {{ Math.max(1, candidatePageCount) }} 页</span>
        <button :disabled="candidatePage === 0" @click="candidatePage--">上一页</button>
        <button :disabled="candidatePage + 1 >= candidatePageCount" @click="candidatePage++">下一页</button>
      </nav>
      <p class="subtle">{{ frontendCopy.facts.candidateUnconfirmed }} 以下仅按相同数据类型展示候选原句，不改变结论或结论证据引用。SDK 自有政策不能替代宿主声明；候选提取仍需人工核验。</p>
      <div class="evidence-grid"><article v-for="candidate in relatedCandidates" :key="candidate.claim.id" class="evidence-card">
        <strong>{{ candidate.claim.id }} · {{ candidate.document ? sourceLabels[candidate.document.source_type] : '来源待补充' }}</strong>
        <p>极性 {{ candidate.claim.polarity ?? 'UNKNOWN' }} · 主体 {{ candidate.claim.subject ?? 'UNKNOWN' }} · 动作 {{ candidate.claim.action ?? 'UNKNOWN' }}</p>
        <p>条件：{{ candidate.claim.condition || '未提取条件（不代表无条件）' }}</p>
        <p v-if="candidate.claim.action === 'UNKNOWN'" class="subtle">动作尚未确认，不能视为声明了实际访问。</p>
        <p>{{ docState(candidate.document) }} · 提取 {{ candidate.document?.extraction_status ?? '未知' }}</p>
        <p class="hash">声明来源 {{ candidate.claim.document_id }} · 候选证据 {{ candidate.claim.evidence_ids.join('、') }}</p>
        <div v-for="item in candidate.evidence" :key="item.id">
          <p class="locator">{{ item.locator }}</p>
          <p class="subtle">原文位置：[{{ item.start_offset }}, {{ item.end_offset }})，按 Unicode 码点计数。</p>
          <pre v-if="sentenceContext(item)">{{ sentenceContext(item)?.before }}<mark>{{ sentenceContext(item)?.sentence }}</mark>{{ sentenceContext(item)?.after }}</pre>
          <pre v-else>{{ item.excerpt || '缺少可定位原句，需补充证据。' }}</pre>
        </div>
        <p v-if="!candidate.evidence.length" class="subtle">没有可定位的候选原句证据，需补充证据。</p>
        <button v-if="candidate.document" class="policy-jump-btn" @click="emit('openPolicy', candidate.document.id)">候选来源全文与适用边界</button>
      </article></div>
    </section>
  </section>
</template>
