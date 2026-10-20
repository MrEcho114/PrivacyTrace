<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ExistingReports from './App.vue'
import UiButton from './components/UiButton.vue'
import StatusTag from './components/StatusTag.vue'
import ImportPage from './pages/ImportPage.vue'
import CandidatePage from './pages/CandidatePage.vue'
import { cancelJob, loadJob, loadTaxonomy } from './api'
import { createDraft, discoverSources, displaySourceUrl, extractSource, reserveExtraction, getAttemptStatus, fetchSource, importExternal, readDraft, saveCandidates, startScan, uploadApk } from './liveApi'
import type { LiveDraft } from './liveApi'
import type { ExternalInput } from './policyAssist'
import { quoteExists, sourceProvenanceLabel, sourceStatusLabel } from './workflow'
import type { Workflow, Candidate } from './workflow'
import type { AnalysisJob, WebCandidate, WebSource } from './types'
const props = defineProps<{ state: Workflow }>()
const emit = defineEmits<{ example: [] }>()
const draft = ref<LiveDraft | null>(null)
const file = ref<File | null>(null)
const job = ref<AnalysisJob | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const labels = ref<Record<string, string>>({})
const controller = new AbortController()
const storageKey = 'privacytrace.live.draft.v1'
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
let submissionId = ''
let pendingRevision: number | null = null
const signal = controller.signal
let activeRequest: AbortController | null = null
let needsPreparation = true
const preparedSources = new Set<string>()
// A transport failure or cancellation may occur after the server committed.
 // Keep unresolved attempts until their audit is reconciled. A rejected retry
 // must never erase the earlier attempt that could have committed.
type PendingExtractionAttempt = { draftId: string; revision: number; attemptId: string }
const maxPendingAttemptsPerSource = 16
const pendingExtractionAttempts = new Map<string, PendingExtractionAttempt[]>()
async function startExtractionAttempt(value: LiveDraft, id: string, requestSignal: AbortSignal): Promise<string> {
  const attempts = pendingExtractionAttempts.get(id) ?? []
  if (attempts.length >= maxPendingAttemptsPerSource) {
    throw new Error('这份来源有多次尚未确认的提取操作。请先重新读取材料，对账后再尝试。')
  }
  const attemptId = crypto.randomUUID().replaceAll('-', '')
  // Do not issue the paid /extract POST until registration is acknowledged.
  // If reservation response is lost, no extract request was sent by this client.
  const receipt = await reserveExtraction(value.id, id, value.revision, attemptId, requestSignal)
  assertActive(requestSignal)
  if (receipt.attempt_id !== attemptId || receipt.state !== 'RESERVED') {
    throw new Error('服务器未确认本次提取登记，请重新读取材料。')
  }
  pendingExtractionAttempts.set(id, [...attempts, { draftId: value.id, revision: value.revision, attemptId }])
  return attemptId
}
function finishExtractionAttempt(value: LiveDraft, id: string, attemptId: string) {
  const audit = value.sources.find(source => source.id === id)?.model_audit
  if (audit?.attempt_id && audit.attempt_id !== attemptId) {
    throw new Error('服务返回的候选提取审计与本次请求不匹配。请重新读取材料。')
  }
  // A direct response carries a committed result; older unresolved attempts
  // cannot supersede this source's newest committed audit.
  pendingExtractionAttempts.delete(id)
}
const failedSourceIds = ref<string[]>([])
function markExtraction(id: string, failed: boolean) {
  failedSourceIds.value = failed ? [...new Set([...failedSourceIds.value, id])] : failedSourceIds.value.filter(item => item !== id)
  if (failed) preparedSources.delete(id)
  else preparedSources.add(id)
}
function extractionFailed(value: LiveDraft, id: string): boolean {
  return value.sources.find(source => source.id === id)?.model_audit?.status === 'FAILED'
}
const states: Record<string, string> = { QUEUED: '等待处理', INTAKE: '核对输入', STATIC_ANALYSIS: '隔离扫描', POLICY_PARSING: '装载政策快照', EVALUATING: '规则对照', REPORTING: '生成报告', SUCCEEDED: '报告已生成', FAILED: '分析失败', CANCELLED: '已取消' }
const terminal = computed(() => !!job.value && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.value.state))
const events = computed(() => draft.value?.jobs.find(r => r.job_id === job.value?.id)?.events ?? [])
const jobError = computed(() => { try { return JSON.parse(job.value?.error ?? '{}').code ?? '' } catch { return 'JOB_FAILED' } })
function remember(id: string) { try { localStorage.setItem(storageKey, id) } catch { notice.value = '浏览器暂存不可用。请记下材料编号，刷新后可用编号恢复。' } }
function apply(value: LiveDraft) {
  if (signal.aborted) return
  draft.value = value; remember(value.id)
  props.state.sources = value.sources.map(s => ({ id: s.id, title: s.title, type: s.source_type ?? 'OFFICIAL_WEB_POLICY', url: s.url ?? '', text: s.text ?? '',
    status: s.status ?? 'empty', version: s.version ?? '', region: s.region ?? '', product: s.product ?? '', complete: false,
    packageName: s.package_name ?? '', versionCode: s.version_code, capturedAt: s.captured_at, sha256: s.sha256, errorCode: s.error_code, provenance: s.provenance, modelAudit: s.model_audit }))
  props.state.candidates = value.candidates.map(c => ({ id: c.id, sourceId: c.source_id, quote: c.excerpt, dataType: c.data_type,
    polarity: c.polarity === 'AFFIRMATIVE' ? 'AFFIRMED' : c.polarity === 'NEGATIVE' ? 'NEGATED' : 'UNKNOWN',
    subject: c.subject === 'HOST_APP' ? 'APP' : c.subject === 'THIRD_PARTY' ? 'THIRD_PARTY' : 'UNKNOWN',
    condition: c.condition ?? '', checked: c.checked ?? false, action: c.action, purpose: c.declared_purpose ?? '', recipient: c.declared_recipient ?? '', startOffset: c.start_offset ?? undefined, ambiguityFlags: c.ambiguity_flags }))
  if (!props.state.sources.some(s => s.id === props.state.sourceId)) props.state.sourceId = props.state.sources[0]?.id ?? ''
}
function go(step: Workflow['step']) { props.state.step = step; props.state.maxStep = Math.max(props.state.maxStep, ['import', 'candidates', 'progress', 'report'].indexOf(step)); void nextTick(() => document.getElementById('page-title')?.focus()) }
async function perform(action: (requestSignal: AbortSignal) => Promise<void>) {
  if (busy.value) return
  const request = new AbortController()
  activeRequest = request
  busy.value = true; error.value = ''
  try { await action(request.signal) } catch (cause) { if (!signal.aborted && !request.signal.aborted) error.value = cause instanceof Error ? cause.message : '操作未完成，请重试。' }
  finally { if (activeRequest === request) { activeRequest = null; busy.value = false } }
}
function assertActive(requestSignal: AbortSignal) {
  if (signal.aborted || requestSignal.aborted) throw new Error('请求已取消。')
}
function cancelPreparation() {
  activeRequest?.abort()
  notice.value = '当前准备请求已取消。服务可能已保存材料；继续前可重新读取材料确认。'
}
function sourceInput(): WebSource[] {
  return props.state.sources.map((s, i) => ({ id: s.id, title: s.title.trim() || `政策来源 ${i + 1}`, source_type: s.type,
    url: s.url, text: s.text, status: s.text.trim() ? 'manual' : 'empty', version: s.version || 'UNKNOWN',
    region: s.region, product: s.product, package_name: s.packageName || '', version_code: typeof s.versionCode === 'number' ? s.versionCode : null }))
}
async function ensureDraft(requestSignal: AbortSignal): Promise<LiveDraft> {
  const selected = file.value
  const fields = ['id', 'title', 'source_type', 'url', 'text', 'version', 'region', 'product', 'package_name', 'version_code'] as const
  const inputs = sourceInput()
  const previous = draft.value
  const unchanged = previous && inputs.length === previous.sources.length && inputs.every(s => {
    const original = previous.sources.find(item => item.id === s.id)
    if (!original) return false
    const normalized = { ...original, title: original.title.trim() || s.title, version: original.version || 'UNKNOWN' }
    return fields.every(k => (s[k] ?? null) === (normalized[k] ?? null))
  })
  // Reuse the server draft so imported provenance, quotes and audit survive upload.
  if (previous && unchanged && !previous.jobs.length && !(selected && previous.uploaded)) return previous
  if (previous?.external_imports?.length) throw new Error('这份材料保留了外部收集记录。请重新读取以恢复原材料，或明确新建材料版本后修改；新版本按手动输入保存，原收集记录留在旧版本。')
  if (previous?.uploaded && !selected) throw new Error('材料已经变更或开始分析，请重新选择 APK 创建新版本。旧任务和报告仍保留。')
  const value = await createDraft({ name: selected?.name ?? previous?.name ?? '政策准备材料', sources: inputs }, requestSignal)
  assertActive(requestSignal)
  generation++; clearTimeout(timer); job.value = null; submissionId = ''; pendingRevision = null
  needsPreparation = true
  preparedSources.clear()
  pendingExtractionAttempts.clear()
  failedSourceIds.value = []
  apply(value)
  return value
}
async function importCollected(input: ExternalInput) {
  await perform(async requestSignal => {
    const incoming = 'results' in input ? input.results.filter(r => r.source).length : 1
    if (props.state.sources.length + incoming > 8) throw new Error(`当前已有 ${props.state.sources.length} 份来源，每份材料最多 8 份来源。请减少本次回填来源。`)
    let value = await ensureDraft(requestSignal)
    if (value.sources.length + incoming > 8) throw new Error(`当前已有 ${value.sources.length} 份来源，每份材料最多 8 份来源。请减少本次回填来源。`)
    value = await importExternal(value.id, input, requestSignal)
    assertActive(requestSignal)
    apply(value); pendingRevision = null; if (incoming) needsPreparation = true
    notice.value = incoming ? '收集结果已补入当前材料。来源、原句与收集状态分别保留，完整度未知、未复核。' : '已记录离线或未找到结果；尚未取得政策正文，可补充网址或正文。'
  })
}
// Exact attempt receipts, not a transient active=false observation, authorize
// releasing reservations after lost HTTP responses.
async function assertSourceIdle(id: string, requestSignal: AbortSignal) {
  const pending = pendingExtractionAttempts.get(id)
  if (!draft.value || !pending?.length) return
  const unresolved: PendingExtractionAttempt[] = []
  let committed = false
  for (const attempt of pending) {
    const receipt = await getAttemptStatus(attempt.draftId, id, attempt.attemptId, requestSignal)
    assertActive(requestSignal)
    if (receipt.attempt_id !== attempt.attemptId) throw new Error('服务器操作对账标识不一致。')
    if (receipt.state === 'COMMITTED') committed = true
    else if (receipt.state !== 'FAILED' && receipt.state !== 'EXPIRED') unresolved.push(attempt)
  }
  if (unresolved.length) {
    pendingExtractionAttempts.set(id, unresolved)
    throw new Error('该来源仍存在已登记或执行中的模型操作。请重新读取材料对账，勿重复发送。')
  }
  if (committed) throw new Error('已检测到服务器保存的提取结果。请先重新读取材料对账，避免重复付费请求。')
  pendingExtractionAttempts.delete(id)
}
async function refreshMaterials() {
  await perform(async requestSignal => {
    if (!draft.value) return
    // Per-ID terminal receipts are the sole authority for retiring attempts.
    const receipts = new Map<string, Map<string, string>>()
    for (const [id, pending] of pendingExtractionAttempts) {
      const statuses = new Map<string, string>()
      for (const attempt of pending) {
        try {
          const status = await getAttemptStatus(attempt.draftId, id, attempt.attemptId, requestSignal)
          assertActive(requestSignal)
          if (status.attempt_id === attempt.attemptId) statuses.set(attempt.attemptId, status.state)
        } catch (cause) {
          assertActive(requestSignal)
          // Unknown network results are not proof of FAILED / EXPIRED.
        }
      }
      receipts.set(id, statuses)
    }
    const value = await readDraft(draft.value.id, requestSignal)
    assertActive(requestSignal)
    for (const source of value.sources) {
      const audit = source.model_audit
      const previous = draft.value.sources.find(item => item.id === source.id)?.model_audit
      const pending = pendingExtractionAttempts.get(source.id)
      const matchedAttempt = pending?.some(attempt =>
        attempt.draftId === value.id && value.revision > attempt.revision &&
        audit?.attempt_id === attempt.attemptId
      ) ?? false
      // Preserve legacy untagged status transitions, but never trust a different
      // tagged attempt or arbitrary duration/token metadata to clear a failure.
      const statusTransition = value.revision > draft.value.revision && previous?.status !== audit?.status
      const compatibleTransition = statusTransition && (!pending || !audit?.attempt_id)
      if (audit?.status === 'FAILED') {
        markExtraction(source.id, true)
        if (matchedAttempt) pendingExtractionAttempts.delete(source.id)
      } else if ((audit?.status === 'SUCCESS' || audit?.status === 'PARTIAL') &&
        (matchedAttempt || compatibleTransition)) {
        markExtraction(source.id, false)
        if (matchedAttempt) pendingExtractionAttempts.delete(source.id)
      }
      if (!matchedAttempt && pending?.length) {
        const status = receipts.get(source.id)
        const keep = pending.filter(a => !['FAILED', 'EXPIRED'].includes(status?.get(a.attemptId) ?? ''))
        if (keep.length) pendingExtractionAttempts.set(source.id, keep)
        else pendingExtractionAttempts.delete(source.id)
      }
    }
    needsPreparation = failedSourceIds.value.length > 0 || value.sources.some(source => !preparedSources.has(source.id))
    apply(value)
    notice.value = '已重新读取服务保存的材料。'
  })
}
async function prepare() {
  await perform(async requestSignal => {
    if (!file.value && !draft.value?.uploaded) throw new Error('请选择 APK 文件。政策辅助材料可以先补入，上传后继续。')
    let value = await ensureDraft(requestSignal)
    const selected = file.value
    if (!needsPreparation && value.uploaded && !selected) { go('candidates'); return }
    if (selected && !value.uploaded) {
      value = await uploadApk(value.id, selected, requestSignal)
      assertActive(requestSignal); apply(value); file.value = null
    }
    if (!value.sources.some(s => s.text?.trim() || s.url?.trim())) {
      const discovery = await discoverSources(value.id, requestSignal)
      assertActive(requestSignal)
      value = await readDraft(value.id, requestSignal)
      assertActive(requestSignal); apply(value)
      notice.value = discovery.limitations.length ? '自动查找存在范围限制；已保留可用线索，请按需补充政策。' : ''
    }
    for (const source of [...value.sources]) {
      if (!preparedSources.has(source.id) && !source.text?.trim() && source.url) {
        value = await fetchSource(value.id, source.id, value.revision, requestSignal)
        assertActive(requestSignal); apply(value)
      }
    }
    if (!value.sources.some(s => s.text?.trim() && s.status !== 'failed')) { go('import'); throw new Error('各份来源均未获得正文。请重试网址，或粘贴／导入政策文本。') }
    let failedExtraction = false
    let recoveredExtraction = false
    for (const source of [...value.sources]) {
      if (!source.text?.trim() || source.status === 'failed' || preparedSources.has(source.id)) continue
      if (value.candidates.some(c => c.source_id === source.id) && !failedSourceIds.value.includes(source.id) && !extractionFailed(value, source.id)) {
        markExtraction(source.id, false); continue
      }
      try {
        await assertSourceIdle(source.id, requestSignal)
        const attemptId = await startExtractionAttempt(value, source.id, requestSignal)
        value = await extractSource(value.id, source.id, value.revision, requestSignal, attemptId)
        assertActive(requestSignal); finishExtractionAttempt(value, source.id, attemptId); apply(value)
        if (extractionFailed(value, source.id)) {
          failedExtraction = true; markExtraction(source.id, true)
          notice.value = `${source.title || source.id}：候选提取未完成。可在候选页面重新提取或手动补充。`
        } else {
          if (failedSourceIds.value.includes(source.id)) recoveredExtraction = true
          markExtraction(source.id, false)
        }
      } catch (cause) {
        assertActive(requestSignal)
        failedExtraction = true; markExtraction(source.id, true)
        notice.value = `${source.title || source.id}：${cause instanceof Error ? cause.message : '模型请求失败'}。可在候选页面重新提取或手动补充。`
      }
    }
    needsPreparation = failedExtraction
    if (!failedExtraction && recoveredExtraction) notice.value = '候选提取重试已完成；原句和语义仍需检查，全文及附件未复核。'
    go('candidates')
  })
}
function encodeCandidate(c: Candidate): WebCandidate {
  const text = props.state.sources.find(s => s.id === c.sourceId)?.text ?? ''
  const original = draft.value?.candidates.find(item => item.id === c.id)
  const validOriginal = original?.excerpt === c.quote && original.start_offset != null
  const index = text.indexOf(c.quote)
  return { id: c.id, source_id: c.sourceId, excerpt: c.quote, data_type: c.dataType,
    polarity: c.polarity === 'AFFIRMED' ? 'AFFIRMATIVE' : c.polarity === 'NEGATED' ? 'NEGATIVE' : 'UNKNOWN',
    subject: c.subject === 'APP' ? 'HOST_APP' : c.subject === 'THIRD_PARTY' ? 'THIRD_PARTY' : 'UNKNOWN',
    condition: c.condition || null, checked: c.checked, action: c.action ?? 'UNKNOWN', declared_purpose: c.purpose || null, declared_recipient: c.recipient || null,
    start_offset: validOriginal ? original.start_offset : index < 0 ? null : [...text.slice(0, index)].length,
    ambiguity_flags: c.ambiguityFlags ?? [] }
}
async function begin() {
  await perform(async () => {
    if (!draft.value) return
    if (pendingRevision === null) {
      apply(await saveCandidates(draft.value.id, { revision: draft.value.revision, candidates: props.state.candidates.map(encodeCandidate) }, signal))
      pendingRevision = draft.value.revision
      submissionId = crypto.randomUUID().replaceAll('-', '')
    }
    job.value = await startScan(draft.value.id, { revision: pendingRevision, request_id: submissionId }, signal)
    go('progress'); await poll()
  })
}
async function poll() {
  if (!draft.value || !job.value || signal.aborted) return
  const current = generation; const id = job.value.id
  clearTimeout(timer)
  try {
    const [nextJob, latest] = await Promise.all([loadJob(id, signal), readDraft(draft.value.id, signal)])
    if (current !== generation || signal.aborted) return
    job.value = nextJob; draft.value = latest
    if (!terminal.value) timer = setTimeout(() => { void poll() }, 1000)
    error.value = ''
  } catch { if (current === generation && !signal.aborted) { error.value = '暂时无法读取进度。任务编号已保留，服务恢复后可重新读取。'; timer = setTimeout(() => { void poll() }, 3000) } }
}
async function persistCandidates() {
  await perform(async () => {
    if (!draft.value) return
    const invalid = props.state.candidates.filter(c => !quoteExists(c, props.state.sources))
    const valid = props.state.candidates.filter(c => quoteExists(c, props.state.sources))
    const current = await saveCandidates(draft.value.id, { revision: draft.value.revision, candidates: valid.map(encodeCandidate) }, signal)
    apply(current); props.state.candidates.push(...invalid)
    notice.value = '候选已保存到本机输入版本。全文及附件复核状态保持不变。'
  })
}
async function cancel() { await perform(async () => { if (job.value) { try { job.value = await cancelJob(job.value.id, signal) } finally { await poll() } } }) }
async function retry() { await perform(async () => { if (!draft.value || !terminal.value) return; submissionId = crypto.randomUUID().replaceAll('-', ''); job.value = await startScan(draft.value.id, { revision: draft.value.revision, request_id: submissionId }, signal); go('progress'); await poll() }) }
async function retrySource(id: string) {
  await perform(async requestSignal => {
    if (!draft.value) return
    // Never mutate source evidence until all earlier extraction attempts are terminal.
    await assertSourceIdle(id, requestSignal)
    const fetched = await fetchSource(draft.value.id, id, draft.value.revision, requestSignal)
    assertActive(requestSignal); apply(fetched)
    pendingExtractionAttempts.delete(id) // Fetch replaced the prior source audit.
    const source = draft.value.sources.find(s => s.id === id)
    if (!source || source.status === 'failed' || source.error_code) return
    try {
      await assertSourceIdle(id, requestSignal)
      const attemptId = await startExtractionAttempt(draft.value, id, requestSignal)
      const value = await extractSource(draft.value.id, id, draft.value.revision, requestSignal, attemptId)
      assertActive(requestSignal); finishExtractionAttempt(value, id, attemptId); apply(value)
      const failed = extractionFailed(value, id)
      markExtraction(id, failed)
      needsPreparation = failedSourceIds.value.length > 0
      notice.value = failed ? '来源已经重新获取，但候选提取仍未完成；可手动添加或重试。' : '重新获取和候选提取已完成；候选仍需检查。'
    } catch (cause) {
      assertActive(requestSignal); markExtraction(id, true); needsPreparation = true
      notice.value = `${cause instanceof Error ? cause.message : '模型请求未完成'}；可手动添加候选或重试。`
    }
  })
}
async function retryModel(id: string) {
  await perform(async requestSignal => {
    if (!draft.value) return
    try {
      await assertSourceIdle(id, requestSignal)
      const attemptId = await startExtractionAttempt(draft.value, id, requestSignal)
      const value = await extractSource(draft.value.id, id, draft.value.revision, requestSignal, attemptId)
      assertActive(requestSignal); finishExtractionAttempt(value, id, attemptId); apply(value)
      const failed = extractionFailed(value, id)
      markExtraction(id, failed)
      needsPreparation = failedSourceIds.value.length > 0
      notice.value = failed ? '候选提取仍未完成。可再次尝试或手动补充。' : '该来源候选提取请求已完成；候选仍需检查，政策全文及附件未复核。'
    } catch (cause) {
      assertActive(requestSignal); markExtraction(id, true); needsPreparation = true
      throw cause
    }
  })
}
function newInput() { const external = !!draft.value?.external_imports?.length; generation++; clearTimeout(timer); preparedSources.clear(); pendingExtractionAttempts.clear(); failedSourceIds.value = []; needsPreparation = true; draft.value = null; job.value = null; file.value = null; submissionId = ''; pendingRevision = null; try { localStorage.removeItem(storageKey) } catch { /* Memory state still resets. */ }; props.state.sources = sourceInput().map(s => ({ id: s.id, title: s.title, url: s.url ?? '', text: s.text ?? '', type: s.source_type ?? 'OFFICIAL_WEB_POLICY', status: 'manual', version: s.version ?? '', region: s.region ?? '', product: s.product ?? '', packageName: s.package_name ?? '', versionCode: s.version_code ?? undefined, complete: false })); props.state.candidates = []; error.value = ''; notice.value = external ? '已转为新的手动输入版本。原始外部来源、候选与收集审计仍保存在旧材料版本。请重新选择 APK。' : ''; go('import') }
onMounted(async () => {
  try { labels.value = Object.fromEntries((await loadTaxonomy(signal)).data_types.map(t => [t.id, t.label])) } catch { /* Editor can still show IDs while service is unavailable. */ }
  let id = ''
  try { id = localStorage.getItem(storageKey) ?? '' } catch { /* Browser storage optional. */ }
  if (!/^[a-f0-9]{32}$/.test(id)) return
  await perform(async requestSignal => {
    const value = await readDraft(id, requestSignal)
    assertActive(requestSignal); apply(value)
    const latest = draft.value?.jobs.at(-1)
    if (latest) { const restored = await loadJob(latest.job_id, requestSignal); assertActive(requestSignal); job.value = restored; submissionId = latest.request_id; go('progress'); await poll() }
    else if (draft.value?.uploaded) {
      // Only persisted FAILED audits opt back into automatic preparation. Unknown
      // extraction history stays untouched so deleted candidates are not reborn.
      failedSourceIds.value = draft.value.sources.filter(source => source.model_audit?.status === 'FAILED').map(source => source.id)
      draft.value.sources.forEach(source => { if (!failedSourceIds.value.includes(source.id)) preparedSources.add(source.id) })
      needsPreparation = failedSourceIds.value.length > 0
      go('candidates')
    }
    notice.value = '已从本机服务恢复材料。候选检查不代表政策全文已复核。'
  })
})
onBeforeUnmount(() => { generation++; controller.abort(); activeRequest?.abort(); clearTimeout(timer) })
</script>
<template>
  <div>
    <div v-if="draft" class="source-actions"><span class="field-help">材料版本 {{ draft.revision }} · <span class="hash">{{ draft.id }}</span></span><UiButton :disabled="busy" variant="quiet" @click="newInput">新建材料版本</UiButton><UiButton v-if="state.step === 'import'" :disabled="busy" variant="quiet" @click="refreshMaterials">重新读取材料</UiButton></div>
    <p v-if="draft?.external_imports?.length && state.step === 'import'" class="field-help">当前版本保留外部收集审计。修改已保存的来源时，请先新建材料版本；新版本使用手动输入，旧记录仍保留。</p>
    <p v-if="busy" class="notice compact" role="status">正在处理当前请求，请稍候；已获得的来源仍保留。<UiButton v-if="state.step === 'import'" variant="quiet" @click="cancelPreparation">取消准备请求</UiButton></p>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p><p v-if="notice" class="notice compact" role="status">{{ notice }}</p>
    <ImportPage v-if="state.step === 'import'" :state="state" :busy="busy" :uploaded-name="draft?.uploaded ? draft.name : undefined" @file="file = $event" @dirty="state.maxStep = 0" @example="emit('example')" @next="prepare" @import="importCollected" />
    <CandidatePage v-else-if="state.step === 'candidates'" :state="state" :busy="busy || !!draft?.jobs.length" :type-labels="labels" :failed-source-ids="failedSourceIds" @back="go('import')" @next="begin" @retry-source="retrySource" @retry-model="retryModel" @persist-candidates="persistCandidates" />
    <div v-else-if="state.step === 'progress'" class="material-panel progress-panel">
      <div class="page-heading"><h1 id="page-title" tabindex="-1">分析进度</h1><p>显示服务实际记录的离散阶段。静态线索不证明实际采集。</p></div>
      <div role="status" aria-live="polite"><StatusTag>{{ states[job?.state ?? 'QUEUED'] }}</StatusTag><p>{{ draft?.name }} · {{ job?.id }}</p></div>
      <ol class="stage-list"><li v-for="(event, i) in events" :key="i"><span class="stage-number">{{ i + 1 }}</span><div><strong>{{ states[event.state] ?? event.state }}</strong><p>开始 {{ event.at }}<span v-if="events[i + 1]"> · 结束 {{ events[i + 1]?.at }}</span><span v-else-if="!terminal"> · 执行中</span></p></div></li></ol>
      <p v-if="jobError" class="error-text">{{ jobError === 'SERVICE_INTERRUPTED' ? '服务中断，旧任务已停止。重试会新建任务。' : '本次分析未完成，请检查 Docker 环境和 APK。' }} <code>{{ jobError }}</code></p>
      <div class="source-actions"><UiButton v-if="!terminal" :disabled="busy" @click="cancel">取消分析</UiButton><UiButton v-if="terminal && job?.state !== 'SUCCEEDED'" :disabled="busy" @click="retry">重新创建分析</UiButton><UiButton v-if="job?.state === 'SUCCEEDED'" variant="primary" @click="go('report')">查看报告</UiButton><UiButton variant="quiet" @click="poll">重新读取进度</UiButton></div>
    </div>
    <div v-else><div class="page-heading"><h1 id="page-title" tabindex="-1">对照报告</h1><p>本机存档 · 输入版本 {{ draft?.revision }} · 查看存档不会重新扫描。</p></div><ExistingReports :initial-job-id="job?.id" /></div>
    <section v-if="draft && state.step !== 'import'" class="material-panel"><h2>来源与核验范围</h2><article v-for="source in draft.sources" :key="source.id" class="source-editor"><strong>{{ source.title }}</strong><p>{{ sourceStatusLabel(source.status) }} · {{ sourceProvenanceLabel(source.provenance) }} · 正文完整度未知 · 未复核 · 附件未检查</p><p v-if="source.error_code" class="error-text">{{ source.error_code }} · 返回材料页粘贴正文，或重试网址。</p><p class="field-help">请求网址 {{ displaySourceUrl(source.url) || '手动输入' }} · 最终网址 {{ displaySourceUrl(source.final_url) || '未获取／手动输入' }}</p><p v-if="source.captured_at" class="field-help">获取时点 {{ source.captured_at }} · SHA-256 {{ source.sha256 }}</p><p v-if="source.model_audit?.status" class="field-help">{{ source.model_audit.status === 'FAILED' ? '模型提取未完成，可手动添加或重新提取' : source.model_audit.status === 'PARTIAL' ? '模型仅提取部分候选' : '模型候选已返回' }} · 原句逐字校验 · 拒绝 {{ source.model_audit.rejected_count ?? 0 }} 条<span v-if="source.model_audit.limited_candidates"> · 超出候选上限 {{ source.model_audit.limited_candidates }} 条</span> · 仍需检查语义</p></article></section>
  </div>
</template>
