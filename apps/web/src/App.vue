<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { loadReport, loadTaxonomy } from './api'
import type { DemoReport, MatchStatus, PrivacyIssue, Taxonomy } from './types'

const report = ref<DemoReport | null>(null)
const taxonomy = ref<Taxonomy | null>(null)
const selected = ref<PrivacyIssue | null>(null)
const loading = ref(false)
const error = ref('')
let controller: AbortController | null = null
let requestId = 0
const statusLabels: Record<MatchStatus, string> = {
  EXACT_MATCH: '具体类型已声明', CATEGORY_MATCH: '声明粒度不足',
  NOT_DECLARED: '未找到对应声明', POLICY_SOURCE_CONFLICT: '不同来源声明有差异',
  AMBIGUOUS_DISCLOSURE: '相关声明不够清楚', INSUFFICIENT_EVIDENCE: '证据不足',
}
const sourceLabels: Record<string, string> = {
  IN_APP_POLICY: 'App 内政策', STORE_POLICY: '应用商店',
  OFFICIAL_WEB_POLICY: '官网政策', SDK_POLICY: 'SDK 自有政策',
}
const kindLabels = {
  MANIFEST: '权限配置', API: 'API 代码', SDK: 'SDK 特征',
  POLICY_DOCUMENT: '政策快照引用', POLICY_SENTENCE: '政策原句',
}
const label = (id: string) => taxonomy.value?.data_types.find(item => item.id === id)?.label ?? id
const selectedEvidence = computed(() => report.value?.evidence.filter(
  item => selected.value?.evidence_ids.includes(item.id),
) ?? [])
const dataTypeCount = computed(() => new Set(report.value?.result.issues.map(i => i.data_type)).size)
const documentLabels = (ids: string[]) => ids.map(id => {
  const doc = report.value?.policy_documents.find(item => item.id === id)
  return doc ? sourceLabels[doc.source_type] ?? doc.source_type : '来源待补充'
}).join(' / ') || '缺少宿主政策'

async function reload() {
  controller?.abort()
  const current = ++requestId
  controller = new AbortController()
  loading.value = true
  error.value = ''
  selected.value = null
  try {
    const [nextReport, nextTaxonomy] = await Promise.all([
      loadReport(controller.signal), loadTaxonomy(controller.signal),
    ])
    if (current !== requestId) return
    report.value = nextReport
    taxonomy.value = nextTaxonomy
  } catch (cause) {
    if (current !== requestId) return
    error.value = cause instanceof Error && cause.name === 'AbortError'
      ? '请求已取消，可以重新加载。'
      : cause instanceof Error ? cause.message : '报告加载失败，请重试。'
  } finally {
    if (current === requestId) loading.value = false
  }
}
onMounted(reload)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <a class="brand" href="#"><span class="brand-icon">P</span>PrivacyTrace</a>
      <span class="subtle">让每个结论都有依据</span>
    </header>
    <main>
      <section class="intro">
        <div>
          <p class="eyebrow">APP 隐私体检 · 开发预览</p>
          <h1>看懂隐私，从证据开始。</h1>
          <p class="lead">查看程序中的潜在隐私访问，与不同来源的政策逐一对照。</p>
        </div>
        <button class="primary" :disabled="loading" @click="reload">重新加载示例报告</button>
      </section>
      <aside class="demo-note">
        <strong>演示数据</strong>
        本页使用人工构造的代码片段与政策文本验证报告流程，尚未接入真实 APK 分析。
        静态证据表示程序中存在相关能力，实际运行时是否访问仍需验证。
      </aside>
      <section v-if="loading" class="state" role="status">
        正在加载示例报告… <button @click="controller?.abort()">取消</button>
      </section>
      <section v-else-if="error" class="state error" role="alert">
        {{ error }} <button @click="reload">重试</button>
      </section>
      <template v-else-if="report">
        <section class="sample-card">
          <div class="app-icon">PT</div>
          <div>
            <h2>{{ report.sample.name }}</h2>
            <p class="subtle">{{ report.sample.package_name }} · {{ report.sample.version }}</p>
          </div>
          <span class="badge">静态潜在行为</span>
        </section>
        <div class="metrics">
          <div><strong>{{ dataTypeCount }}</strong><span>涉及的数据类型</span></div>
          <div><strong>{{ report.policy_documents.length }}</strong><span>独立政策来源</span></div>
          <div><strong>{{ report.evidence.length }}</strong><span>可查看的证据</span></div>
        </div>
        <section class="report-section">
          <div class="section-heading"><h2>隐私声明对照</h2><span class="subtle">选择一条结论，查看原始依据</span></div>
          <div class="table-scroll">
            <table>
              <thead><tr><th>隐私数据</th><th>政策来源</th><th>当前结论</th><th>依据</th></tr></thead>
              <tbody>
                <tr v-for="issue in report.result.issues" :key="issue.id">
                  <td class="type-cell">{{ label(issue.data_type) }}</td>
                  <td>{{ documentLabels(issue.policy_document_ids) }}</td>
                  <td><span class="tag" :class="issue.status === 'EXACT_MATCH' && !issue.requires_review ? 'clear' : 'review'">{{ statusLabels[issue.status] }}{{ issue.requires_review ? ' · 待复核' : '' }}</span></td>
                  <td><button class="evidence-button" :aria-expanded="selected?.id === issue.id" aria-controls="evidence-panel" @click="selected = issue">查看 {{ issue.evidence_ids.length }} 条证据 →</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section v-if="selected" id="evidence-panel" class="evidence-panel" aria-live="polite">
          <div class="section-heading">
            <h2>{{ label(selected.data_type) }} · {{ statusLabels[selected.status] }}</h2>
            <button @click="selected = null">收起</button>
          </div>
          <p class="explanation">{{ selected.explanation }}</p>
          <div class="evidence-grid">
            <article v-for="item in selectedEvidence" :key="item.id" class="evidence-card">
              <div class="section-heading"><strong>{{ kindLabels[item.kind] }}</strong><span class="subtle">{{ item.id }}</span></div>
              <p class="locator">{{ item.source }} · {{ item.locator }}</p>
              <p v-if="item.kind === 'POLICY_SENTENCE'" class="subtle">
                原文位置：[{{ item.start_offset }}, {{ item.end_offset }})，按 Unicode 码点计数。
              </p>
              <p v-if="item.kind === 'POLICY_DOCUMENT' && item.excerpt" class="subtle">以下为快照预览，完整政策请在下方展开。</p>
              <pre v-if="item.excerpt">{{ item.excerpt }}</pre>
              <p v-else class="subtle">此证据引用完整政策快照，不含预览原句。请在下方展开政策全文。</p>
            </article>
          </div>
        </section>
        <details class="provenance">
          <summary>查看报告版本与政策快照</summary>
          <p>任务：{{ report.job.id }} · 规则版本：{{ report.job.ruleset_version }}</p>
          <article v-for="doc in report.policy_documents" :key="doc.id">
            <strong>{{ doc.title }}</strong>
            <p>{{ sourceLabels[doc.source_type] }} · {{ doc.version }} · {{ doc.captured_at }}</p>
            <p class="hash">SHA-256 {{ doc.artifact.sha256 }}</p>
            <p class="subtle">
              快照：{{ doc.completeness }} · 提取：{{ doc.extraction_status }} · 复核：{{ doc.review_status }}
            </p>
            <details>
              <summary>查看政策全文</summary>
              <pre>{{ doc.artifact.text }}</pre>
            </details>
          </article>
        </details>
      </template>
      <footer>PrivacyTrace · 每条结论保留证据来源，推断与声明单独记录。</footer>
    </main>
  </div>
</template>
