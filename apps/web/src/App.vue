<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { cancelJob, deleteJob, isNotFoundFor, jobPath, jobReportPath, loadJob, loadJobReport, loadJobs, loadReport, loadTaxonomy, retryJob, submitReview } from './api'
import { clampSdkPage, getSdkEvidence, sdkPageCount, sdkPageSlice } from './sdkEvidence'
import type { AnalysisJob, DemoReport, Evidence, MatchStatus, PrivacyIssue, Report, ReportSource, Taxonomy, WebSource } from './types'
import { parseSource, serializeSource, sourceProvenanceLabel, sourceStatusLabel } from './types'
const props = defineProps<{ initialJobId?: string; snapshot?: { report: Report; taxonomy: Taxonomy } }>()

const report = ref<DemoReport | Report | null>(null)
const taxonomy = ref<Taxonomy | null>(null)
const jobs = ref<AnalysisJob[]>([])
const activeJob = ref<AnalysisJob | null>(null)
// Deleting is irreversible locally, so removed ids are remembered: a late poll or
// a stale 404 response must never put the deleted job back on screen.
const removedJobIds = ref<string[]>([])
const confirmDelete = ref(false)
const jobMessage = ref('')
// Blocking loads replace the visible source; in-place refreshes keep the report,
// selection and reading position while polling or when the user asks to refresh.
const loading = ref(false)
const refreshing = ref(false)
let refreshToken = 0
const jobAnnouncement = ref('')
const jobStateEl = ref<HTMLElement | null>(null)
const jobMessageEl = ref<HTMLElement | null>(null)
const errorEl = ref<HTMLElement | null>(null)
const cancelJobEl = ref<HTMLButtonElement | null>(null)
const retryJobEl = ref<HTMLButtonElement | null>(null)
const deleteTriggerEl = ref<HTMLButtonElement | null>(null)
const confirmDeleteEl = ref<HTMLButtonElement | null>(null)
const evidenceTrigger = ref<HTMLElement | null>(null)
const reviewSubmitEl = ref<HTMLButtonElement | null>(null)
let lastAnnouncedJob = ''
const source = ref<ReportSource>({ kind: 'demo' })
const selectedSourceKey = computed({
  get: () => serializeSource(source.value),
  set: (val: string) => {
    source.value = parseSource(val)
  },
})
const selected = ref<PrivacyIssue | null>(null)
function selectIssue(issue: PrivacyIssue, event: Event) {
  evidenceTrigger.value = event.currentTarget as HTMLElement
  selected.value = issue
  void nextTick(() => {
    const panel = document.getElementById('evidence-panel')
    panel?.scrollIntoView({ block: 'start', behavior: 'smooth' })
    panel?.focus({ preventScroll: true })
  })
}
function closeEvidence() {
  const trigger = evidenceTrigger.value
  selected.value = null
  void nextTick(() => {
    const target = trigger?.isConnected ? trigger : document.getElementById('page-title')
    target?.focus()
  })
}
const error = ref('')
const refreshEl = ref<HTMLButtonElement | null>(null)
watch(error, (value, oldValue) => {
  if (typeof document === 'undefined') return
  if (value) {
    void nextTick(() => {
      if (document.activeElement === document.body) errorEl.value?.focus({ preventScroll: true })
    })
  } else if (oldValue) {
    void nextTick(() => {
      if (document.activeElement !== document.body) return
      const refresh = refreshEl.value
      const target = refresh?.isConnected && !refresh.disabled ? refresh : document.getElementById('page-title')
      target?.focus({ preventScroll: true })
    })
  }
})
const reviewMessage = ref('')
const actor = ref('')
const reason = ref('')
const note = ref('')
let controller: AbortController | null = null
let requestId = 0
let timer: ReturnType<typeof setTimeout> | undefined
const terminal = (job: AnalysisJob) => ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state)
const statusLabels: Record<MatchStatus, string> = {
  EXACT_MATCH: '具体类型已声明', CATEGORY_MATCH: '声明粒度不足',
  NOT_DECLARED: '未找到对应声明', POLICY_SOURCE_CONFLICT: '不同来源声明有差异',
  AMBIGUOUS_DISCLOSURE: '相关声明不够清楚', INSUFFICIENT_EVIDENCE: '证据不足',
}
const jobLabels: Record<AnalysisJob['state'], string> = {
  QUEUED: '等待处理', INTAKE: '核对输入', STATIC_ANALYSIS: '扫描 APK', POLICY_PARSING: '提取政策',
  EVALUATING: '规则对照', REPORTING: '生成报告', SUCCEEDED: '报告已生成', FAILED: '分析失败', CANCELLED: '已取消',
}
const sourceLabels: Record<string, string> = {
  IN_APP_POLICY: 'App 内政策', STORE_POLICY: '应用商店', OFFICIAL_WEB_POLICY: '官网政策', SDK_POLICY: 'SDK 自有政策',
  CONTROLLED_POLICY: '自建受控配对政策',
}
const kindLabels = { MANIFEST: '权限配置', API: 'API 字节码', SDK: 'SDK 特征', POLICY_DOCUMENT: '政策快照引用', POLICY_SENTENCE: '政策原句' }
const label = (id: string) => taxonomy.value?.data_types.find(item => item.id === id)?.label ?? id
const selectedEvidence = computed(() => report.value?.evidence.filter(item => selected.value?.evidence_ids.includes(item.id)) ?? [])
const dataTypeCount = computed(() => new Set(report.value?.result.issues.map(i => i.data_type)).size)
const realReport = computed(() => report.value && !report.value.demo ? report.value : null)
const webSources = computed(() => {
  try {
    const value = JSON.parse(realReport.value?.tools.web_policy_sources ?? '[]')
    return Array.isArray(value) ? value.filter(item => item && typeof item.title === 'string' && typeof item.status === 'string') as { title: string; status: NonNullable<WebSource['status']>; error_code?: string; captured_at?: string; sha256?: string; url?: string; final_url?: string; provenance?: string | null }[] : []
  } catch { return [] }
})
// SDK attribution is reference material with its own access path: no issue cites
// it, so without this panel those evidence records would be counted but unopenable.
const sdkEvidence = computed(() => getSdkEvidence(realReport.value?.evidence ?? []))
const sdkPage = ref(0)
const sdkPageTotal = computed(() => sdkPageCount(sdkEvidence.value.length))
const pagedSdkEvidence = computed(() => sdkPageSlice(sdkEvidence.value, sdkPage.value))
// Only a report switch resets the page; an in-place refresh and changing the
// selected issue must not move it.
watch(() => report.value?.job?.id, () => {
  sdkPage.value = 0
})
const controlledReport = computed(() => (realReport.value?.job ?? activeJob.value)?.input_mode === 'CONTROLLED_APK')
const replayPage = typeof document !== 'undefined'
  && document.querySelector('meta[name="privacytrace-presentation"]')?.getAttribute('content') === 'offline'
const offlineReplay = computed(() => replayPage || realReport.value?.tools.presentation_mode === 'OFFLINE_REPLAY')
// Candidate clauses are navigation aids, not evaluator-confirmed evidence or matches.
// Candidate clauses pagination
const CANDIDATE_PAGE_SIZE = 20
const candidatePage = ref(0)
const candidateClaims = computed(() => {
  if (!realReport.value || !selected.value) return []
  return realReport.value.policy_claims.filter(claim => claim.data_type === selected.value?.data_type)
})
const candidatePageCount = computed(() => Math.ceil(candidateClaims.value.length / CANDIDATE_PAGE_SIZE))
watch([() => selected.value?.id, () => report.value?.job?.id], () => {
  candidatePage.value = 0
  openedPolicyId.value = null
  provenanceOpen.value = false
})
const relatedCandidates = computed(() => {
  if (!realReport.value) return []
  const current = realReport.value
  return candidateClaims.value
    .slice(candidatePage.value * CANDIDATE_PAGE_SIZE, (candidatePage.value + 1) * CANDIDATE_PAGE_SIZE)
    .map(claim => ({
      claim,
      document: current.policy_documents.find(doc => doc.id === claim.document_id),
      evidence: current.evidence.filter(item => item.kind === 'POLICY_SENTENCE'
        && item.document_id === claim.document_id && claim.evidence_ids.includes(item.id)),
    }))
})
// Full artifacts live only in the provenance section, and are inserted on demand.
const openedPolicyId = ref<string | null>(null)
const provenanceOpen = ref(false)
const openPolicy = (id: string) => {
  provenanceOpen.value = true
  openedPolicyId.value = id
  void nextTick(() => {
    if (typeof document === 'undefined') return
    const target = document.getElementById('policy-' + id)
    target?.scrollIntoView()
    target?.focus({ preventScroll: true })
  })
}
const provenanceToggle = (event: Event) => {
  provenanceOpen.value = (event.target as HTMLDetailsElement).open
  if (!provenanceOpen.value) openedPolicyId.value = null
}
const policyToggle = (event: Event, id: string) => {
  const details = event.target as HTMLDetailsElement
  if (details.open) openedPolicyId.value = id
  else if (openedPolicyId.value === id) openedPolicyId.value = null
}

const documentFor = (item: Evidence) => report.value?.policy_documents.find(doc => doc.id === item.document_id)
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
const documentLabels = (ids: string[]) => {
  if (ids.length) return ids.map(id => {
    const doc = report.value?.policy_documents.find(item => item.id === id)
    return doc ? sourceLabels[doc.source_type] ?? doc.source_type : '来源待补充'
  }).join(' / ')
  if (report.value?.policy_documents.some(doc => doc.source_type !== 'SDK_POLICY')) {
    return '有政策快照 · 对应条款未确认'
  }
  return report.value?.policy_documents.length ? '仅有 SDK 政策 · 缺少宿主政策' : '缺少宿主政策'
}

// Multi-source classification & original timestamp formatting
const formatTimestamp = (ts?: string) => {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return isNaN(d.getTime()) ? ts : d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

// Source classification reads the explicit backend `source_origin` field.
// Naming conventions (sample_id prefixes) never decide provenance.
//
// `source_origin` is the immutable origin of the data. How the report reached
// us *now* is a separate field, `delivery_mode`, because the same persisted job
// is LIVE_GENERATED in the run that produced it and PERSISTED_REPLAY afterwards.
const SOURCE_LABELS: Record<string, { badge: string; label: string; desc: string }> = {
  SYNTHETIC: {
    badge: '人工示例 · SYNTHETIC',
    label: 'SYNTHETIC · 人工构造示例',
    desc: '人工构造的代码片段与政策文本，不属于真实 APK。',
  },
  CONTROLLED: {
    badge: '受控评测 · CONTROLLED',
    label: 'CONTROLLED · 受控测试输入',
    desc: '来自受控测试环境的标准测试用例，用于验证边界与特定异常行为。',
  },
  REAL_SCAN: {
    badge: '真实 APK · REAL_SCAN',
    label: 'REAL_SCAN · 真实 APK 静态扫描',
    desc: '数据来自真实 APK 静态扫描，已保留完整证据链与原生成时点。',
  },
  // Records written before source_origin existed. Their provenance was never
  // recorded, so it is reported as unknown instead of being guessed: "unknown"
  // must never be read as "real scan".
  UNKNOWN: {
    badge: '来源未知 · UNKNOWN',
    label: 'UNKNOWN · 来源未记录',
    desc: '该记录写于来源字段引入之前，磁盘上没有留存来源信息，因此无法判断它是真实扫描、受控用例还是人工示例。',
  },
}

const DELIVERY_LABELS: Record<string, { badge: string; desc: string }> = {
  LIVE_GENERATED: {
    badge: '本次生成 · LIVE',
    desc: '本次运行刚刚产出的结果。',
  },
  PERSISTED_REPLAY: {
    badge: '持久化回放 · REPLAY',
    desc: '从持久化存储加载的既有报告，不是本次运行新产出的结果。',
  },
}

const sourceOptionPrefix = (origin?: string) => {
  if (origin === 'CONTROLLED') return '[受控评测] '
  if (origin === 'SYNTHETIC') return '[人工示例] '
  if (origin === 'REAL_SCAN') return '[真实 APK] '
  if (origin === 'UNKNOWN') return '[来源未知] '
  return '[来源未标注] '
}

const sourceInfo = computed(() => {
  if (!report.value && !activeJob.value) return null
  const origin = report.value?.demo ? 'SYNTHETIC' : (report.value?.job ?? activeJob.value)?.source_origin
  if (origin === 'CONTROLLED' && controlledReport.value) return {
    type: origin, badge: '受控评测 · CONTROLLED', label: 'CONTROLLED_APK · 自建受控场景',
    desc: '源码构建的测试 APK；政策事实仅适用于此受控场景，不代表真实应用政策已核验。候选由代理辅助整理。',
  }
  if (!origin) {
    return { type: 'UNKNOWN', badge: '来源未标注', label: '来源未标注', desc: '报告缺少来源标注，无法判断该报告的真实性级别。' }
  }
  const known = SOURCE_LABELS[origin]
  if (!known) {
    return { type: origin, badge: `未识别来源 · ${origin}`, label: `未识别来源 · ${origin}`, desc: '后端返回了未知的来源类型，请检查契约版本是否匹配。' }
  }
  return { type: origin, ...known }
})

// Delivery badge is independent of origin: a REAL_SCAN report is "本机生成"
// only in the run that produced it, and "持久化回放" on any later load.
const deliveryInfo = computed(() => {
  if (!report.value) return null
  const mode = report.value.delivery_mode
  if (!mode) {
    return { type: 'UNKNOWN', badge: '投递方式未标注', desc: '报告缺少投递方式标注，无法判断是否为本次生成。' }
  }
  const known = DELIVERY_LABELS[mode]
  if (!known) {
    return { type: mode, badge: `未识别投递 · ${mode}`, desc: '后端返回了未知的投递方式，请检查契约版本是否匹配。' }
  }
  return { type: mode, ...known }
})

// Structured error parsing for activeJob
interface ParsedJobError {
  code: string
  message: string
  primary_error?: string
  raw: string
}
const parsedJobError = computed<ParsedJobError | null>(() => {
  if (!activeJob.value?.error) return null
  try {
    const obj = JSON.parse(activeJob.value.error)
    if (typeof obj === 'object' && obj !== null) {
      return {
        code: String(obj.code || obj.error_code || 'ERROR'),
        message: String(obj.message || obj.detail || activeJob.value.error),
        primary_error: obj.primary_error ? String(obj.primary_error) : undefined,
        raw: activeJob.value.error,
      }
    }
  } catch {}
  return {
    code: 'ERROR',
    message: activeJob.value.error,
    raw: activeJob.value.error,
  }
})

function focusedOn(element: HTMLElement | null | undefined): boolean {
  return typeof document !== 'undefined' && !!element && document.activeElement === element
}
function beginRequest() {
  controller?.abort()
  clearTimeout(timer)
  controller = new AbortController()
  return { current: ++requestId, signal: controller.signal }
}
function failure(cause: unknown) {
  return cause instanceof Error && cause.name === 'AbortError' ? '请求已取消，可以重试。' : cause instanceof Error ? cause.message : '请求失败，请重试。'
}
function focusIfLost(element: Element | null | undefined, fallback: HTMLElement | null | undefined) {
  if (typeof document === 'undefined' || !element) return
  void nextTick(() => {
    if (element.isConnected || document.activeElement !== document.body) return
    const target = fallback?.isConnected ? fallback : document.getElementById('page-title')
    target?.focus({ preventScroll: true })
  })
}
function applyJob(job: AnalysisJob) {
  const active = typeof document !== 'undefined' ? document.activeElement : null
  const key = `${job.id}:${job.state}`
  const changed = !!lastAnnouncedJob && lastAnnouncedJob !== key && lastAnnouncedJob.startsWith(job.id + ':')
  activeJob.value = job
  if (changed) jobAnnouncement.value = `任务状态更新：${jobLabels[job.state]}（${job.state}）`
  lastAnnouncedJob = key
  focusIfLost(active, jobStateEl.value)
}
function applyReport(next: DemoReport | Report, preserveSelection: boolean) {
  const previousIssueId = preserveSelection ? selected.value?.id : null
  const panelHadFocus = typeof document !== 'undefined' && !!document.getElementById('evidence-panel')?.contains(document.activeElement)
  const active = typeof document !== 'undefined' ? document.activeElement : null
  report.value = next
  selected.value = previousIssueId ? next.result.issues.find(item => item.id === previousIssueId) ?? null : null
  if (!selected.value && panelHadFocus) {
    void nextTick(() => {
      const target = evidenceTrigger.value?.isConnected ? evidenceTrigger.value : document.getElementById('page-title')
      target?.focus({ preventScroll: true })
    })
  } else if (active && panelHadFocus) {
    void nextTick(() => {
      if (active.isConnected || document.activeElement !== document.body) return
      document.getElementById('evidence-panel')?.focus({ preventScroll: true })
    })
  }
}
function schedulePoll(delay = 1500) {
  clearTimeout(timer)
  timer = setTimeout(() => { void loadData(false, 'refresh') }, delay)
}
// "replace" is for a source switch or first paint: the old source's report must
// not stay visible under a new source label. "refresh" updates the current
// source in place so polling never unmounts the job card, closes evidence, or
// announces the temporary loading state on every tick.
async function loadData(initial = false, mode: 'replace' | 'refresh' = 'replace') {
  if (props.snapshot) return
  const replace = mode === 'replace'
  let token = 0
  if (source.value.kind === 'job' && removedJobIds.value.includes(source.value.id)) source.value = { kind: 'demo' }
  if (replace) {
    refreshToken += 1
    refreshing.value = false
    loading.value = true
    error.value = ''
    reviewMessage.value = ''
    report.value = null
    selected.value = null
    activeJob.value = null
    confirmDelete.value = false
    jobAnnouncement.value = ''
    lastAnnouncedJob = ''
  } else {
    token = ++refreshToken
    refreshing.value = true
  }
  const { current, signal } = beginRequest()
  try {
    const [nextJobs, nextTaxonomy] = await Promise.all([loadJobs(signal), loadTaxonomy(signal)])
    if (current !== requestId) return
    jobs.value = nextJobs.jobs.filter(job => !removedJobIds.value.includes(job.id))
    taxonomy.value = nextTaxonomy
    if (initial && props.initialJobId) source.value = { kind: 'job', id: props.initialJobId }
    else if (initial && jobs.value.length) source.value = { kind: 'job', id: jobs.value[0]!.id }
    if (source.value.kind === 'demo') {
      const nextReport = await loadReport(signal)
      if (current === requestId) applyReport(nextReport, !replace)
    }
    else {
      const job = await loadJob(source.value.id, signal)
      if (current !== requestId) return
      applyJob(job)
      if (job.state === 'SUCCEEDED') {
        const nextReport = await loadJobReport(job.id, signal)
        if (current === requestId) applyReport(nextReport, !replace)
      }
      else if (!terminal(job)) schedulePoll()
      else { report.value = null; selected.value = null }
    }
    error.value = ''
  } catch (cause) {
    if (current !== requestId) return
    const wantedId = source.value.kind === 'job' ? source.value.id : ''
    if (wantedId && isNotFoundFor(cause, jobPath(wantedId))) {
      // Only a 404 for the job entity itself proves the record is gone. A
      // missing report (or a taxonomy/list failure) must not hide a live job.
      removedJobIds.value = [...removedJobIds.value, wantedId]
      jobs.value = jobs.value.filter(job => job.id !== wantedId)
      source.value = { kind: 'demo' }
      activeJob.value = null
      report.value = null
      selected.value = null
      lastAnnouncedJob = ''
      error.value = '任务已删除，界面已移除该任务。'
      // Load the fallback example under the same request, without clearing the
      // explanation of why the selected job disappeared.
      try {
        const fallback = await loadReport(signal)
        if (current !== requestId) return
        report.value = fallback; selected.value = null
        error.value = '任务已删除，界面已移除该任务。'
      } catch { /* keep the removal message; the user can retry */ }
    } else if (wantedId && isNotFoundFor(cause, jobReportPath(wantedId))) {
      error.value = '任务仍存在，但报告不可用（可能尚未生成或已被移除），可稍后重试。'
    } else {
      error.value = failure(cause)
      if (!replace && activeJob.value && !terminal(activeJob.value)) schedulePoll(3000)
    }
  } finally {
    if (current === requestId) loading.value = false
    if (!replace && token === refreshToken) refreshing.value = false
  }
}
function refreshData() { if (refreshing.value) return; void loadData(false, 'refresh') }
function retryLoad() {
  const trigger = typeof document !== 'undefined' ? document.activeElement as HTMLElement | null : null
  const request = report.value || activeJob.value ? loadData(false, 'refresh') : loadData(false, 'replace')
  void request.finally(() => {
    if (typeof document === 'undefined') return
    if (!trigger || trigger.isConnected || document.activeElement !== document.body) return
    const refresh = refreshEl.value
    const target = refresh?.isConnected && !refresh.disabled ? refresh : document.getElementById('page-title')
    target?.focus({ preventScroll: true })
  })
}
function switchSource() { void loadData(false, 'replace') }
// Kept as the explicit "replace the source" entry used by the unit tests and
// by callers that must not preserve the previous report.
function reload(initial = false) { return loadData(initial, 'replace') }

async function cancel() {
  if (!activeJob.value || terminal(activeJob.value)) return
  const restoreFocus = focusedOn(cancelJobEl.value)
  const id = activeJob.value.id
  const { current, signal } = beginRequest()
  loading.value = true
  try {
    const job = await cancelJob(id, signal)
    if (current !== requestId) return
    applyJob(job); report.value = null
    if (restoreFocus) void nextTick(() => jobStateEl.value?.focus({ preventScroll: true }))
  } catch (cause) {
    if (current === requestId) {
      const msg = cause instanceof Error ? cause.message : String(cause)
      if (msg.includes('409')) {
        // The job moved on while we tried to cancel. Resolve the latest state
        // instead of leaving a SUCCEEDED job without its report.
        error.value = '任务已处于终态或无法取消（状态已更新）。'
        try {
          const latest = await loadJob(id, signal)
          if (current !== requestId) return
          applyJob(latest)
          if (latest.state === 'SUCCEEDED') {
            report.value = await loadJobReport(latest.id, signal)
            if (current === requestId) error.value = ''
          } else if (!terminal(latest)) {
            // Still running after a rejected cancel: resume polling.
            error.value = ''
            schedulePoll()
          } else {
            report.value = null
          }
        } catch {}
      } else {
        error.value = failure(cause)
      }
    }
  } finally {
    if (current === requestId) {
      loading.value = false
      if (restoreFocus) void nextTick(() => {
        if (cancelJobEl.value) cancelJobEl.value.focus({ preventScroll: true })
        else jobStateEl.value?.focus({ preventScroll: true })
      })
    }
  }
}
// A retry is a NEW analysis (issue story 12): the returned job has its own id and
// the original record stays readable from the report source list.
async function retryTerminal() {
  const job = activeJob.value
  if (!job) return
  const restoreFocus = focusedOn(retryJobEl.value)
  const { current, signal } = beginRequest()
  loading.value = true
  error.value = ''
  jobMessage.value = ''
  confirmDelete.value = false
  try {
    const fresh = await retryJob(job.id, signal)
    if (current !== requestId) return
    jobMessage.value = `已创建新的分析任务 ${fresh.id}，这是新的分析，不是原任务的重新打开；原任务 ${job.id} 的记录仍保留，可在报告来源中查看。`
    source.value = { kind: 'job', id: fresh.id }
    applyJob(fresh)
    report.value = null
    selected.value = null
    void loadData(false, 'refresh')
    if (restoreFocus) void nextTick(() => jobStateEl.value?.focus({ preventScroll: true }))
  } catch (cause) {
    if (current === requestId) error.value = failure(cause)
  } finally {
    if (current === requestId) {
      loading.value = false
      if (restoreFocus) void nextTick(() => {
        if (retryJobEl.value) retryJobEl.value.focus({ preventScroll: true })
        else jobStateEl.value?.focus({ preventScroll: true })
      })
    }
  }
}
function forgetJob(id: string) {
  clearTimeout(timer)
  removedJobIds.value = [...removedJobIds.value, id]
  confirmDelete.value = false
  jobs.value = jobs.value.filter(item => item.id !== id)
  activeJob.value = null
  report.value = null
  selected.value = null
  lastAnnouncedJob = ''
  jobAnnouncement.value = ''
  if (source.value.kind === 'job' && source.value.id === id) {
    const next = jobs.value[0]
    source.value = next ? { kind: 'job', id: next.id } : { kind: 'demo' }
  }
}
async function removeJob() {
  const job = activeJob.value
  if (!job) return
  const id = job.id
  const { current, signal } = beginRequest()
  loading.value = true
  error.value = ''
  jobMessage.value = ''
  try {
    const result = await deleteJob(id, signal)
    if (current !== requestId) return
    forgetJob(id)
    jobMessage.value = `任务 ${result.job_id} 已从本机记录中删除，原始材料与分析结果不可恢复。`
    void nextTick(() => jobMessageEl.value?.focus({ preventScroll: true }))
    void loadData(false, 'replace')
  } catch (cause) {
    if (current !== requestId) return
    const message = cause instanceof Error ? cause.message : ''
    if (message === '任务已删除。') {
      // Already deleted (double click or another tab): finish the local removal.
      forgetJob(id)
      jobMessage.value = '任务已删除。'
      void nextTick(() => jobMessageEl.value?.focus({ preventScroll: true }))
      void loadData(false, 'replace')
      return
    }
    error.value = failure(cause)
  } finally {
    if (current === requestId) {
      loading.value = false
      if (confirmDelete.value) void nextTick(() => confirmDeleteEl.value?.focus({ preventScroll: true }))
    }
  }
}
function askDelete() {
  confirmDelete.value = true
  void nextTick(() => confirmDeleteEl.value?.focus({ preventScroll: true }))
}
function cancelDelete() {
  if (!confirmDelete.value) return
  confirmDelete.value = false
  void nextTick(() => deleteTriggerEl.value?.focus({ preventScroll: true }))
}
async function review() {
  if (!realReport.value) return
  const restoreFocus = focusedOn(reviewSubmitEl.value)
  const id = realReport.value.job.id
  const { current, signal } = beginRequest()
  loading.value = true
  error.value = ''
  reviewMessage.value = ''
  try {
    const next = await submitReview(id, {
      actor: actor.value.trim(),
      reason: reason.value.trim(),
      note: note.value.trim(),
    }, signal)
    if (current !== requestId) return
    applyReport(next, true)
    reviewMessage.value = '备注已保存，规则已重新计算。'
  } catch (cause) { if (current === requestId) error.value = failure(cause) }
  finally {
    if (current === requestId) {
      loading.value = false
      if (restoreFocus) void nextTick(() => reviewSubmitEl.value?.focus({ preventScroll: true }))
    }
  }
}
onMounted(() => {
  if (props.snapshot) {
    report.value = props.snapshot.report; taxonomy.value = props.snapshot.taxonomy
    source.value = { kind: 'job', id: props.snapshot.report.job.id }
  } else void loadData(true, 'replace')
})
onBeforeUnmount(() => { ++requestId; controller?.abort(); clearTimeout(timer) })
</script>

<template>
  <div class="shell">
    <header class="topbar"><a class="brand" href="#"><span class="brand-icon">P</span>PrivacyTrace</a><span class="subtle">让每个结论都有依据</span></header>
    <main>
      <section class="intro">
        <div><p class="eyebrow">APP 隐私体检 · 本地报告</p><h1>看懂隐私，从证据开始。</h1><p class="lead">查看程序中的潜在隐私访问，与不同来源的政策逐一对照。</p></div>
        <button v-if="!snapshot" ref="refreshEl" class="primary" :disabled="loading" :aria-busy="refreshing || undefined" @click="refreshData">刷新任务与报告</button>
      </section>
      <section v-if="!snapshot" class="source-picker">
        <label for="report-source">报告来源</label>
        <select id="report-source" v-model="selectedSourceKey" @change="switchSource">
          <option v-if="!offlineReplay" value="demo:synthetic">SYNTHETIC · 人工构造示例</option>
          <option v-for="job in jobs" :key="job.id" :value="`job:${job.id}`">
            {{ sourceOptionPrefix(job.source_origin) }}{{ job.package_name || job.sample_id }} · {{ job.id }} · {{ jobLabels[job.state] }}
          </option>
        </select>
        <p class="subtle">真实任务由 APK 扫描 CLI 创建；示例仅用于演示，不是实际应用的检测结果。</p>
      </section>
      <details class="demo-note"><summary>分析范围与来源 · <strong>{{ sourceInfo?.label ?? (source.kind === 'demo' ? 'SYNTHETIC 示例' : '真实 APK 静态报告') }}</strong></summary>
        {{ sourceInfo?.desc ?? (source.kind === 'demo' ? '人工构造的代码片段与政策文本，不属于真实 APK。' : 'APK 只做静态扫描，没有安装或运行。报告不保证覆盖反射、动态加载、原生代码或运行时行为。') }}
        六种状态只对照 DATA_TYPE_DISCLOSURE；“具体类型已声明”不代表目的、接收方、传输或时间范围全部一致，更不是合法性判断。
      </details>
      <section v-if="webSources.length" class="coverage-card"><h2>输入来源状态</h2><p>失败来源保留；正文完整度未知、全文未复核、附件未检查。</p><ul><li v-for="(item, index) in webSources" :key="index"><strong>{{ item.title }}</strong> · {{ sourceStatusLabel(item.status) }} · {{ sourceProvenanceLabel(item.provenance) }}<span v-if="item.error_code"> · {{ item.error_code }}</span><p class="subtle">请求网址 {{ item.url || '手动输入' }} · 最终网址 {{ item.final_url || '未获取／手动输入' }}</p></li></ul></section><section v-if="realReport" class="report-provenance" aria-label="报告生成来源">
        <strong>{{ offlineReplay ? 'OFFLINE REPLAY · 离线回放' : '存档报告查看 · PERSISTED REPLAY' }}</strong>
        <p v-if="realReport.tools.analysis_generated_at">分析生成时点：{{ realReport.tools.analysis_generated_at }}。查看存档不代表重新扫描。</p>
        <p v-else>记录创建时点：{{ realReport.job.created_at }}。未留存分析生成时点；来源以报告来源标识为准。</p>
        <p v-if="offlineReplay">回放包生成时点：{{ realReport.tools.offline_package_built_at }}。回放只读，不执行 APK 分析。</p>
        <p v-if="offlineReplay"><a href="/comparison.html" target="_blank" rel="noopener">查看六场景三方案比较与失败记录</a></p>
      </section>
      <p id="job-announcement" class="sr-only" role="status">{{ jobAnnouncement }}</p>
      <section v-if="activeJob" ref="jobStateEl" class="job-state" tabindex="-1" :aria-busy="(refreshing || loading) || undefined">
        <strong>{{ jobLabels[activeJob.state] }}</strong> · {{ activeJob.id }} · {{ activeJob.state }}
        <button v-if="!terminal(activeJob)" ref="cancelJobEl" :disabled="loading" @click="cancel">取消任务</button>
        <div v-if="parsedJobError" class="job-error-card" role="alert">
          <span class="error-code">错误码：{{ parsedJobError.code }}</span>
          <p class="error-msg">{{ parsedJobError.message }}</p>
          <p v-if="parsedJobError.primary_error" class="error-detail subtle">根因：{{ parsedJobError.primary_error }}</p>
        </div>
        <p v-if="activeJob.state === 'FAILED' || activeJob.state === 'CANCELLED'">本任务没有可展示的成功报告。可以重试为一次新的分析，或删除这条本机记录。</p>
        <!-- Destructive actions stay terminal-only: deleting a running job would leave a tombstone
             while the worker may still be writing. Running jobs keep the cancel button above. -->
        <div v-if="terminal(activeJob)" class="job-terminal-actions" @keydown.esc="cancelDelete">
          <button v-if="activeJob.state === 'FAILED' || activeJob.state === 'CANCELLED'" ref="retryJobEl" data-testid="retry-job" :disabled="loading" @click="retryTerminal">重试为新的分析</button>
          <button v-if="!confirmDelete" ref="deleteTriggerEl" data-testid="delete-job" :disabled="loading" @click="askDelete">删除任务</button>
          <span v-else class="job-delete-confirm" role="group" aria-label="删除任务确认" aria-describedby="job-delete-warning">
            <button ref="confirmDeleteEl" data-testid="delete-confirm" :disabled="loading" @click="removeJob">确认删除</button>
            <button :disabled="loading" @click="cancelDelete">取消删除</button>
          </span>
        </div>
        <p v-if="confirmDelete && terminal(activeJob)" id="job-delete-warning" class="job-delete-warning">删除会一并移除本机保存的这条任务记录与报告，事后不可恢复，也不会保留原任务的分析结果。</p>
      </section>
      <p v-if="jobMessage" id="job-message" ref="jobMessageEl" class="notice" role="status" tabindex="-1">{{ jobMessage }}</p>
      <section v-if="loading && !report && !activeJob" class="state"><span role="status">正在加载…</span> <button @click="controller?.abort()">停止本次请求</button></section>
      <section v-if="error" ref="errorEl" class="state error" tabindex="-1"><span role="alert">{{ error }}</span> <button @click="retryLoad">重试</button></section>
      <template v-if="report">
        <section class="sample-card">
          <div class="app-icon">PT</div>
          <div>
            <h2>{{ report.sample.name }}</h2>
            <p class="subtle">{{ report.sample.package_name }} · {{ report.demo ? report.sample.version : (report.sample.version_name ?? ('v' + report.sample.version_code)) }}</p>
            <p v-if="report.job?.created_at" class="subtle origin-timestamp">原生成时间：{{ formatTimestamp(report.job.created_at) }} ({{ report.job.created_at }})</p>
          </div>
          <div class="badge-stack">
            <span class="badge" :class="sourceInfo?.type?.toLowerCase()" :title="sourceInfo?.desc ?? ''">{{ sourceInfo?.badge }}</span>
            <span class="badge" :class="deliveryInfo?.type?.toLowerCase()" :title="deliveryInfo?.desc ?? ''">{{ deliveryInfo?.badge }}</span>
          </div>
        </section>
        <section v-if="realReport" class="coverage-card">
          <h2>DEX 处理范围：{{ realReport.coverage.status === 'COMPLETE' ? '已扫描所支持的 DEX 范围' : 'PARTIAL · DEX 处理有未完成部分' }}</h2>
          <p>已扫描 {{ (realReport.coverage.scanned_dex ?? []).join('、') || '无' }}；失败 {{ (realReport.coverage.failed_dex ?? []).join('、') || '无' }}。</p>
          <ul><li v-for="limitation in (realReport.coverage.limitations ?? [])" :key="limitation">{{ limitation }}</li></ul>
          <p><strong>行为识别：有限的规则静态分析（非穷尽）。</strong></p>
          <p class="subtle">不保证覆盖反射、动态加载、Native、加壳、第三方与混合运行时、复杂数据流或规则集未覆盖的行为。没有命中规则不代表没有隐私行为。</p>
          <ul><li v-for="limitation in (realReport.coverage.behavior_limitations ?? [])" :key="limitation">{{ limitation }}</li></ul>
          <p class="hash">输入 APK SHA-256：{{ realReport.sample.apk_sha256 }}</p>
          <p class="subtle">扫描完成只描述本轮处理范围，不等于发现了应用所有隐私行为。</p>
        </section>
        <div class="metrics"><div><strong>{{ dataTypeCount }}</strong><span>涉及的数据类型</span></div><div><strong>{{ report.policy_documents.length }}</strong><span>独立政策来源</span></div><div><strong>{{ report.evidence.length }}</strong><span>可查看的证据</span></div></div>
        <section class="report-section">
          <div class="section-heading"><h2>隐私声明对照</h2><span class="subtle">点开结论后，直接查看代码定位与原句</span></div>
          <!-- Narrow screens stack each row as a card; the explicit table roles keep the grid
               semantics that display:flex/block would otherwise drop. -->
          <div class="table-scroll"><table class="report-table" role="table"><thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">隐私数据</th><th scope="col" role="columnheader">政策来源</th><th scope="col" role="columnheader">当前结论</th><th scope="col" role="columnheader">依据</th></tr></thead><tbody role="rowgroup">
            <tr v-for="issue in report.result.issues" :key="issue.id" role="row"><td class="type-cell" role="cell" data-label="隐私数据">{{ label(issue.data_type) }}</td><td role="cell" data-label="政策来源">{{ documentLabels(issue.policy_document_ids) }}</td><td role="cell" data-label="当前结论"><span class="tag" :class="issue.status === 'EXACT_MATCH' && !issue.requires_review ? 'clear' : 'review'">{{ statusLabels[issue.status] }}{{ issue.requires_review ? ' · 待复核' : '' }}</span></td><td role="cell" data-label="依据"><button class="evidence-button" :aria-expanded="selected?.id === issue.id" aria-controls="evidence-panel" @click="selectIssue(issue, $event)">查看 {{ issue.evidence_ids.length }} 条证据 →</button></td></tr>
          </tbody></table></div><p v-if="!report.result.issues.length" class="subtle">未产生对照项不等于没有隐私访问，请查看权限与扫描覆盖。</p>
        </section>
        <section v-if="selected" id="evidence-panel" class="evidence-panel" tabindex="-1" aria-labelledby="evidence-title">
          <div class="section-heading"><h2 id="evidence-title">{{ label(selected.data_type) }} · {{ statusLabels[selected.status] }}</h2><button @click="closeEvidence">收起</button></div>
          <p class="explanation">{{ selected.explanation }}</p>
          <p v-if="selected.status === 'NOT_DECLARED'" class="demo-note">“未找到声明”依赖适用版本、完整正文、提取成功、全文复核和附件齐全。下面保留完整政策及这些状态；缺少其中任一项时不能据此断言违规。</p>
          <div class="evidence-grid"><article v-for="item in selectedEvidence" :key="item.id" class="evidence-card">
            <div class="section-heading"><strong>{{ kindLabels[item.kind] }}</strong><span class="subtle">{{ item.id }}</span></div>
            <p class="locator">{{ item.source }} · {{ item.locator }}</p>
            <template v-if="item.api_call"><p class="hash">目标：{{ item.api_call.target_descriptor }}</p><p class="subtle">规则 {{ item.api_call.rule_id }} · {{ item.api_call.ruleset_version }}；静态上下文 {{ JSON.stringify(item.api_call.context) }}</p><p class="subtle">字节码定位保留调用方法、DEX 与指令偏移；未提供 JADX Java 源码时以字节码作为依据。</p></template>
            <p v-if="item.kind === 'POLICY_SENTENCE'" class="subtle">原文位置：[{{ item.start_offset }}, {{ item.end_offset }})，按 Unicode 码点计数。</p>
            <pre v-if="sentenceContext(item)">{{ sentenceContext(item)?.before }}<mark>{{ sentenceContext(item)?.sentence }}</mark>{{ sentenceContext(item)?.after }}</pre>
            <pre v-else-if="item.excerpt">{{ item.excerpt }}</pre>
            <p v-else class="subtle">本条引用政策快照，全文见下方。</p>
            <button v-if="item.document_id && documentFor(item)" class="policy-jump-btn" @click="openPolicy(item.document_id)">完整政策与适用边界</button>
          </article></div>
          <section v-if="relatedCandidates.length" class="candidate-clauses">
            <h3>相关候选条款（未确认匹配）</h3>
            <nav aria-label="候选条款分页" class="candidate-nav">
              <span>共 {{ candidateClaims.length }} 条 · 第 {{ candidatePage + 1 }} / {{ Math.max(1, candidatePageCount) }} 页</span>
              <button :disabled="candidatePage === 0" @click="candidatePage--">上一页</button>
              <button :disabled="candidatePage + 1 >= candidatePageCount" @click="candidatePage++">下一页</button>
            </nav>
            <p class="subtle">以下仅按相同数据类型展示候选原句，不属于规则已确认的匹配依据，不改变结论或结论证据引用。SDK 自有政策不能替代宿主声明；候选提取仍需人工核验。</p>
            <p v-if="report.behaviors.find(item => item.id === selected?.behavior_id)?.action === 'CAPABILITY'" class="demo-note">本项只是清单权限能力，不代表实际访问；候选条款不能据此认定已发生访问或已经对应。</p>
            <div class="evidence-grid"><article v-for="candidate in relatedCandidates" :key="candidate.claim.id" class="evidence-card">
              <strong>{{ candidate.claim.id }} · {{ candidate.document ? sourceLabels[candidate.document.source_type] : '来源待补充' }}</strong>
              <p>极性 {{ candidate.claim.polarity ?? 'UNKNOWN' }} · 主体 {{ candidate.claim.subject ?? 'UNKNOWN' }} · 动作 {{ candidate.claim.action ?? 'UNKNOWN' }}</p>
              <p>条件：{{ candidate.claim.condition || '未提取条件（不代表无条件）' }}</p>
              <p v-if="candidate.claim.action === 'UNKNOWN'" class="subtle">动作尚未确认，不能视为声明了实际访问。</p>
              <p>复核 {{ candidate.document?.review_status ?? 'UNREVIEWED' }} · 提取 {{ candidate.document?.extraction_status ?? 'NOT_STARTED' }} · 快照 {{ candidate.document?.completeness ?? '未知' }}</p>
              <p class="hash">声明来源 {{ candidate.claim.document_id }} · 候选证据 {{ candidate.claim.evidence_ids.join('、') }}</p>
              <div v-for="item in candidate.evidence" :key="item.id">
                <p class="locator">{{ item.locator }}</p>
                <p class="subtle">原文位置：[{{ item.start_offset }}, {{ item.end_offset }})，按 Unicode 码点计数。</p>
                <pre v-if="sentenceContext(item)">{{ sentenceContext(item)?.before }}<mark>{{ sentenceContext(item)?.sentence }}</mark>{{ sentenceContext(item)?.after }}</pre>
                <pre v-else>{{ item.excerpt || '缺少可定位原句，需补充证据。' }}</pre>
              </div>
              <p v-if="!candidate.evidence.length" class="subtle">没有可定位的候选原句证据，需补充证据。</p>
              <button v-if="candidate.document" class="policy-jump-btn" @click="openPolicy(candidate.document.id)">候选来源全文与适用边界</button>
            </article></div>
          </section>
        </section>
        <section v-if="realReport" id="sdk-panel" class="report-section">
          <div class="section-heading"><h2>第三方 SDK 归属</h2><span class="subtle">仅按公开包前缀提供静态归属参考，不代表实际收集或外传</span></div>
          <p class="subtle">归属命中只表示类路径落在某个已公开的 SDK 包范围内；SDK 的静态存在不等于实际收集或外发，也不能替代宿主 App 自身的声明，归属结论不参与政策一致性判定。</p>
          <template v-if="sdkEvidence.length">
            <nav v-if="sdkPageTotal > 1" aria-label="SDK 归属分页">
              <span>共 {{ sdkEvidence.length }} 条 · 第 {{ sdkPage + 1 }} / {{ sdkPageTotal }} 页</span>
              <button :disabled="sdkPage === 0" @click="sdkPage = clampSdkPage(sdkPage - 1, sdkEvidence.length)">上一页</button>
              <button :disabled="sdkPage + 1 >= sdkPageTotal" @click="sdkPage = clampSdkPage(sdkPage + 1, sdkEvidence.length)">下一页</button>
            </nav>
            <div class="evidence-grid"><article v-for="item in pagedSdkEvidence" :key="item.id" class="evidence-card">
              <div class="section-heading"><strong>{{ kindLabels[item.kind] }}</strong><span class="subtle">{{ item.id }}</span></div>
              <p class="locator">{{ item.source }} · {{ item.locator }}</p>
              <pre v-if="item.excerpt">{{ item.excerpt }}</pre>
            </article></div>
          </template>
          <p v-else class="subtle">本次未命中当前有限的签名规则集。没有命中不代表 APK 不含第三方 SDK。</p>
          <ul v-if="realReport.coverage.sdk_attribution_limitations?.length"><li v-for="limitation in realReport.coverage.sdk_attribution_limitations" :key="limitation">{{ limitation }}</li></ul>
        </section>
        <details class="provenance" :open="provenanceOpen" @toggle="provenanceToggle($event)"><summary>报告版本、权限与全部政策快照</summary>
          <p>任务 {{ report.job.id }} · 输入 {{ report.job.input_mode }} · 规则版本 {{ report.job.ruleset_version }} · 原生成时间：{{ formatTimestamp(report.job.created_at) || report.job.created_at }}</p>
          <template v-if="realReport">
            <p v-for="(version, tool) in Object.fromEntries(Object.entries(realReport.tools).filter(([key]) => key !== 'web_policy_sources'))" :key="tool">{{ tool }}：{{ version }}</p>
            <p class="hash">DEX {{ (realReport.sample.dex_entries ?? []).join('、') || '无' }}</p>
            <details><summary>Android 权限（权限不等于已访问）</summary><ul><li v-for="permission in (realReport.sample.permissions ?? [])" :key="permission">{{ permission }}</li></ul></details>
          </template>
          <article v-for="doc in report.policy_documents" :key="doc.id" :id="'policy-' + doc.id" class="policy-document" tabindex="-1">
            <strong>{{ doc.title }}</strong>
            <p>{{ sourceLabels[doc.source_type] }} · {{ doc.version }} · {{ doc.captured_at }}</p>
            <p class="hash">SHA-256 {{ doc.artifact.sha256 }}</p>
            <p>快照 {{ doc.completeness }} · 提取 {{ doc.extraction_status }} · 复核 {{ doc.review_status }} · 附件 {{ doc.attachments_status }}</p>
            <p class="hash">适用范围 {{ JSON.stringify(doc.applicability) }}</p>
            <details :open="openedPolicyId === doc.id" @toggle="policyToggle($event, doc.id)">
              <summary>查看政策全文</summary>
              <pre v-if="openedPolicyId === doc.id">{{ doc.artifact.text }}</pre>
            </details>
          </article>
        </details>
        <section v-if="realReport && !offlineReplay && !snapshot" class="review-panel">
          <h2>人工复核备注</h2><p class="subtle">这里只保存备注并由纯规则重算，不自动把政策标为已复核，不修改候选声明。填写的身份未认证。</p>
          <form @submit.prevent="review">
            <label>复核人<input v-model="actor" required maxlength="100" /></label>
            <label>原因<input v-model="reason" required maxlength="1000" /></label>
            <label>备注（可选）<textarea v-model="note" maxlength="10000" rows="4"></textarea></label>
            <button ref="reviewSubmitEl" class="primary" :disabled="loading || !actor.trim() || !reason.trim()">保存备注并重新计算</button>
          </form>
          <p v-if="reviewMessage" role="status">{{ reviewMessage }}</p>
          <details v-for="(event, index) in realReport.reviews" :key="`${event.timestamp}-${index}`" class="audit-event">
            <summary>{{ event.timestamp }} · {{ event.actor }} · {{ event.reason }}</summary>
            <p v-if="event.note">{{ event.note }}</p>
            <p v-else class="subtle">（无备注内容）</p>
            <p class="subtle">{{ event.authority }} · 人工身份未认证</p>
            <p>旧结论：{{ event.old_result.issues.map(item => `${label(item.data_type)}: ${statusLabels[item.status]}`).join('；') || '无' }}</p>
            <p>新结论：{{ event.new_result.issues.map(item => `${label(item.data_type)}: ${statusLabels[item.status]}`).join('；') || '无' }}</p>
            <details v-if="event.old_claim || event.new_claim"><summary>声明修改记录</summary><pre>{{ JSON.stringify({ old: event.old_claim, new: event.new_claim }, null, 2) }}</pre></details>
          </details>
        </section>
      </template>
      <footer>
        <p>PrivacyTrace · 每条结论保留证据来源，推断与声明单独记录。</p>
        <p class="subtle ai-disclosure">报告的隐私核验结果由 Consistency Engine 输出；部分工程代码使用 AI 辅助，范围和核实状态见仓库披露记录。</p>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.candidate-nav { display: flex; align-items: center; gap: 12px; margin: 12px 0; font-size: 0.8125rem; }
.job-terminal-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; }
.job-terminal-actions button { margin-left: 0; }
.job-delete-confirm { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.job-state:focus, .evidence-panel:focus, .policy-document:focus, .notice[tabindex="-1"]:focus, .state.error:focus { outline: 2px solid var(--navy); outline-offset: 3px; }
.job-delete-warning { color: var(--error); margin: 8px 0 0; }
.candidate-nav button { padding: 4px 10px; font-size: 12px; }
.job-error-card { background: #fff1ed; border: 1px solid #f4c7bb; border-radius: 8px; padding: 14px; margin-top: 12px; }
.job-error-card .error-code { font-weight: bold; color: #a33215; display: inline-block; margin-bottom: 6px; font-size: 13px; }
.job-error-card .error-msg { margin: 4px 0; color: #72200b; font-size: 14px; }
.job-error-card .error-detail { margin-top: 6px; font-size: 12px; }
.policy-jump-btn { margin-top: 10px; font-size: 12px; padding: 6px 10px; display: inline-block; }
.origin-timestamp { font-size: 12px; color: #52665a; margin-top: 4px; }
.ai-disclosure { margin-top: 4px; font-size: 12px; color: var(--muted); }
</style>
