<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ExistingReports from './App.vue'
import UiButton from './components/UiButton.vue'
import StatusTag from './components/StatusTag.vue'
import ImportPage from './pages/ImportPage.vue'
import CandidatePage from './pages/CandidatePage.vue'
import { cancelJob, loadJob, loadTaxonomy } from './api'
import { createDraft, extractSource, fetchSource, readDraft, saveCandidates, startScan, uploadApk } from './liveApi'
import type { LiveDraft } from './liveApi'
import { quoteExists } from './workflow'
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
    packageName: s.package_name ?? '', versionCode: s.version_code, capturedAt: s.captured_at, sha256: s.sha256, errorCode: s.error_code, modelAudit: s.model_audit }))
  props.state.candidates = value.candidates.map(c => ({ id: c.id, sourceId: c.source_id, quote: c.excerpt, dataType: c.data_type,
    polarity: c.polarity === 'AFFIRMATIVE' ? 'AFFIRMED' : c.polarity === 'NEGATIVE' ? 'NEGATED' : 'UNKNOWN',
    subject: c.subject === 'HOST_APP' ? 'APP' : c.subject === 'THIRD_PARTY' ? 'THIRD_PARTY' : 'UNKNOWN',
    condition: c.condition ?? '', checked: c.checked ?? false, action: c.action, purpose: c.declared_purpose ?? '', recipient: c.declared_recipient ?? '', startOffset: c.start_offset ?? undefined, ambiguityFlags: c.ambiguity_flags }))
  if (!props.state.sources.some(s => s.id === props.state.sourceId)) props.state.sourceId = props.state.sources[0]?.id ?? ''
}
function go(step: Workflow['step']) { props.state.step = step; props.state.maxStep = Math.max(props.state.maxStep, ['import', 'candidates', 'progress', 'report'].indexOf(step)); void nextTick(() => document.getElementById('page-title')?.focus()) }
async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action() } catch (cause) { if (!signal.aborted) error.value = cause instanceof Error ? cause.message : '操作未完成，请重试。' }
  finally { busy.value = false }
}
function sourceInput(): WebSource[] {
  return props.state.sources.map((s, i) => ({ id: s.id, title: s.title.trim() || `政策来源 ${i + 1}`, source_type: s.type,
    url: s.url, text: s.text, status: s.text.trim() ? 'manual' : 'empty', version: s.version || 'UNKNOWN',
    region: s.region, product: s.product, package_name: s.packageName || '', version_code: typeof s.versionCode === 'number' ? s.versionCode : null }))
}
async function prepare() {
  await perform(async () => {
    const selected = file.value
    if (!selected && draft.value?.uploaded) {
      const fields = ['id', 'title', 'source_type', 'url', 'text', 'version', 'region', 'product', 'package_name', 'version_code'] as const
      const inputs = sourceInput()
      if (inputs.length === draft.value.sources.length && inputs.every(s => {
        const original = draft.value!.sources.find(item => item.id === s.id)
        return original && fields.every(k => (s[k] ?? null) === (original[k] ?? null))
      })) { go('candidates'); return }
    }
    if (!selected) throw new Error('请重新选择 APK 文件。原任务和报告保持在本机存档中。')
    // Each material edit produces another input record; earlier reports retain their snapshots.
    const previous = draft.value
    let value = await createDraft({ name: selected?.name ?? previous?.name ?? '本机 APK', sources: sourceInput() }, signal)
    generation++; clearTimeout(timer); job.value = null; submissionId = ''; pendingRevision = null
    apply(value)
    if (selected) { value = await uploadApk(value.id, selected, signal); apply(value) }
    for (const source of [...value.sources]) {
      if (!source.text?.trim() && source.url) { value = await fetchSource(value.id, source.id, value.revision, signal); apply(value) }
    }
    if (!value.sources.some(s => s.text?.trim() && s.status !== 'failed')) { go('import'); throw new Error('各份来源均未获得正文。请重试网址，或粘贴／导入政策文本。') }
    go('candidates')
    for (const source of [...value.sources]) {
      if (!source.text?.trim() || source.status === 'failed') continue
      try { value = await extractSource(value.id, source.id, value.revision, signal); apply(value) }
      catch (cause) { notice.value = cause instanceof Error ? cause.message : '模型请求失败，可手动添加候选。' }
    }
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
    if (props.state.candidates.some(c => !c.checked)) throw new Error('请检查剩余候选，或删除不采用的候选。没有候选的来源仍会保留证据不足提示。')
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
async function retrySource(id: string) { await perform(async () => { if (!draft.value) return; apply(await fetchSource(draft.value.id, id, draft.value.revision, signal)); if (props.state.sources.find(s => s.id === id)?.status !== 'failed') { try { apply(await extractSource(draft.value.id, id, draft.value.revision, signal)) } catch (cause) { notice.value = String(cause instanceof Error ? cause.message : '模型请求未完成') } } }) }
async function retryModel(id: string) { await perform(async () => { if (!draft.value) return; apply(await extractSource(draft.value.id, id, draft.value.revision, signal)) }) }
function newInput() { generation++; clearTimeout(timer); draft.value = null; job.value = null; file.value = null; submissionId = ''; pendingRevision = null; try { localStorage.removeItem(storageKey) } catch { /* Memory state still resets. */ }; props.state.sources = sourceInput().map(s => ({ id: s.id, title: s.title, url: s.url ?? '', text: s.text ?? '', type: s.source_type ?? 'OFFICIAL_WEB_POLICY', status: 'manual', version: s.version ?? '', region: s.region ?? '', product: s.product ?? '', complete: false })); props.state.candidates = []; go('import') }
onMounted(async () => {
  try { labels.value = Object.fromEntries((await loadTaxonomy(signal)).data_types.map(t => [t.id, t.label])) } catch { /* Editor can still show IDs while service is unavailable. */ }
  let id = ''
  try { id = localStorage.getItem(storageKey) ?? '' } catch { /* Browser storage optional. */ }
  if (!/^[a-f0-9]{32}$/.test(id)) return
  await perform(async () => {
    apply(await readDraft(id, signal))
    const latest = draft.value?.jobs.at(-1)
    if (latest) { job.value = await loadJob(latest.job_id, signal); submissionId = latest.request_id; go('progress'); await poll() }
    else if (draft.value?.uploaded) go('candidates')
    notice.value = '已从本机服务恢复材料。候选检查不代表政策全文已复核。'
  })
})
onBeforeUnmount(() => { generation++; controller.abort(); clearTimeout(timer) })
</script>
<template>
  <div>
    <div v-if="draft" class="source-actions"><span class="field-help">材料版本 {{ draft.revision }} · <span class="hash">{{ draft.id }}</span></span><UiButton :disabled="busy" variant="quiet" @click="newInput">新建材料版本</UiButton></div>
    <p v-if="busy" class="notice compact" role="status">正在处理当前请求，请稍候；已获得的来源仍保留。</p>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p><p v-if="notice" class="notice compact" role="status">{{ notice }}</p>
    <ImportPage v-if="state.step === 'import'" :state="state" :busy="busy" :uploaded-name="draft?.uploaded ? draft.name : undefined" @file="file = $event" @dirty="state.maxStep = 0" @example="emit('example')" @next="prepare" />
    <CandidatePage v-else-if="state.step === 'candidates'" :state="state" :busy="busy || !!draft?.jobs.length" :type-labels="labels" @back="go('import')" @next="begin" @retry-source="retrySource" @retry-model="retryModel" @persist-candidates="persistCandidates" />
    <div v-else-if="state.step === 'progress'" class="material-panel progress-panel">
      <div class="page-heading"><h1 id="page-title" tabindex="-1">分析进度</h1><p>显示服务实际记录的离散阶段。静态线索不证明实际采集。</p></div>
      <div role="status" aria-live="polite"><StatusTag>{{ states[job?.state ?? 'QUEUED'] }}</StatusTag><p>{{ draft?.name }} · {{ job?.id }}</p></div>
      <ol class="stage-list"><li v-for="(event, i) in events" :key="i"><span class="stage-number">{{ i + 1 }}</span><div><strong>{{ states[event.state] ?? event.state }}</strong><p>开始 {{ event.at }}<span v-if="events[i + 1]"> · 结束 {{ events[i + 1]?.at }}</span><span v-else-if="!terminal"> · 执行中</span></p></div></li></ol>
      <p v-if="jobError" class="error-text">{{ jobError === 'SERVICE_INTERRUPTED' ? '服务中断，旧任务已停止。重试会新建任务。' : '本次分析未完成，请检查 Docker 环境和 APK。' }} <code>{{ jobError }}</code></p>
      <div class="source-actions"><UiButton v-if="!terminal" :disabled="busy" @click="cancel">取消分析</UiButton><UiButton v-if="terminal && job?.state !== 'SUCCEEDED'" :disabled="busy" @click="retry">重新创建分析</UiButton><UiButton v-if="job?.state === 'SUCCEEDED'" variant="primary" @click="go('report')">查看报告</UiButton><UiButton variant="quiet" @click="poll">重新读取进度</UiButton></div>
    </div>
    <div v-else><div class="page-heading"><h1 id="page-title" tabindex="-1">对照报告</h1><p>本机存档 · 输入版本 {{ draft?.revision }} · 查看存档不会重新扫描。</p></div><ExistingReports :initial-job-id="job?.id" /></div>
    <section v-if="draft && state.step !== 'import'" class="material-panel"><h2>来源与核验范围</h2><article v-for="source in draft.sources" :key="source.id" class="source-editor"><strong>{{ source.title }}</strong><p>{{ source.status === 'failed' ? '来源获取失败' : source.status === 'empty' ? '尚无正文' : source.status === 'manual' ? '手动补入正文' : '已获取网页正文' }} · 正文完整度未知 · 未复核 · 附件未检查</p><p v-if="source.error_code" class="error-text">{{ source.error_code }} · 返回材料页粘贴正文，或重试网址。</p><p class="field-help">请求网址 {{ source.url || '手动输入' }} · 最终网址 {{ source.final_url || '未获取／手动输入' }}</p><p v-if="source.captured_at" class="field-help">获取时点 {{ source.captured_at }} · SHA-256 {{ source.sha256 }}</p><p v-if="source.model_audit?.status" class="field-help">{{ source.model_audit.status === 'FAILED' ? '模型提取未完成，可手动添加或重新提取' : source.model_audit.status === 'PARTIAL' ? '模型仅提取部分候选' : '模型候选已返回' }} · 原句逐字校验 · 拒绝 {{ source.model_audit.rejected_count ?? 0 }} 条 · 仍需检查语义</p></article></section>
  </div>
</template>
