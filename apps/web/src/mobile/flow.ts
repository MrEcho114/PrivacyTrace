import { reactive, ref } from 'vue'
import { freshWorkflow } from '../workflow'
import type { Candidate } from '../workflow'
import type { AnalysisJob, Report, Taxonomy, WebCandidate } from '../types'
import type { LiveDraft } from '../liveApi'
import type { ExternalInput } from '../policyAssist'
import type { MobileBridge, Upload, ModelStatus } from './bridge'

// A native poll sends five HTTP reads. Keep the first progress read responsive,
// then leave room for two clients sharing the default 60/minute IP budget.
const FIRST_POLL_MS = 10_000, POLL_INTERVAL_MS = 20_000

export function createMobileFlow(bridge: MobileBridge) {
  const state = reactive(freshWorkflow())
  const context = ref<Upload | null>(null), draft = ref<LiveDraft | null>(null)
  const job = ref<AnalysisJob | null>(null), report = ref<Report | null>(null), taxonomy = ref<Taxonomy | null>(null)
  const busy = ref(false), error = ref(''), notice = ref('')
  const model = ref<ModelStatus>({ configured: false, endpoint: null }), modelResult = ref('')
  let generation = 0, pendingStart: { revision: number; request_id: string } | null = null
  let busyPolls = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  const terminal = () => !!job.value && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.value.state)
  function schedule(current: number, first = false) {
    if (current !== generation) return
    clearTimeout(timer)
    if (!job.value || terminal()) return
    const throttled = error.value === 'SERVER_BUSY'
    if (error.value && !throttled) return
    busyPolls = throttled ? Math.min(busyPolls + 1, 3) : 0
    // Native currently exposes a busy code, not response headers. Default to
    // the server's current 60s window; never replay a failed write operation.
    const delay = throttled ? 60_000 * 2 ** (busyPolls - 1) : first ? FIRST_POLL_MS : POLL_INTERVAL_MS
    const jitter = first && !throttled ? 0 : Math.floor(Math.random() * (throttled ? 10_000 : 4_000))
    timer = setTimeout(poll, delay + jitter)
  }
  function apply(value: LiveDraft) {
    draft.value = value
    state.sources = value.sources.map(s => ({ id: s.id, title: s.title, type: s.source_type ?? 'OFFICIAL_WEB_POLICY',
      url: s.url ?? '', text: s.text ?? '', status: s.status ?? 'empty', version: s.version ?? '', region: s.region ?? '',
      product: s.product ?? '', complete: false, provenance: s.provenance, modelAudit: s.model_audit }))
    state.candidates = value.candidates.map(c => ({ id: c.id, sourceId: c.source_id, quote: c.excerpt, dataType: c.data_type,
      polarity: c.polarity === 'AFFIRMATIVE' ? 'AFFIRMED' : c.polarity === 'NEGATIVE' ? 'NEGATED' : 'UNKNOWN',
      subject: c.subject === 'HOST_APP' ? 'APP' : c.subject === 'THIRD_PARTY' ? 'THIRD_PARTY' : 'UNKNOWN',
      condition: c.condition ?? '', checked: c.checked ?? false, action: c.action, purpose: c.declared_purpose ?? '',
      recipient: c.declared_recipient ?? '', startOffset: c.start_offset ?? undefined, ambiguityFlags: c.ambiguity_flags }))
    if (!state.sources.some(s => s.id === state.sourceId)) state.sourceId = state.sources[0]?.id ?? ''
  }
  async function run(action: (request: <T>(name: string, body?: object) => Promise<T>, check: () => void) => Promise<void>) {
    if (busy.value) return
    clearTimeout(timer)
    busy.value = true; error.value = ''
    const current = generation
    const active = () => { if (generation !== current) throw new Error('CANCELLED') }
    const request = async <T>(name: string, body?: object): Promise<T> => {
      const response = await bridge.request<T>(name, body)
      active()
      if (!context.value || response.origin !== context.value.origin || response.draft !== context.value.draft) throw new Error('INSTANCE_MISMATCH')
      return response.data
    }
    try { await action(request, active) }
    catch (cause) { if (current === generation) error.value = typeof cause === 'string' ? cause : cause instanceof Error ? cause.message : '操作未完成，请刷新确认。' }
    finally { if (current === generation) busy.value = false }
  }
  async function stop() {
    generation++; clearTimeout(timer); busy.value = false
    notice.value = '已停止当前请求。服务可能已保存结果，请刷新确认；停止读取不等于取消分析或删除材料。'
    await bridge.cancel().catch(() => {})
  }
  async function select(restore = false) {
    const current = generation
    await run(async (request, check) => {
      const selected = await (restore ? bridge.restore() : bridge.upload())
      check()
      // Native lifecycle cancellation rejects the selected result as well.
      context.value = selected; draft.value = null; job.value = null; report.value = null; pendingStart = null
      state.step = 'import'; notice.value = ''
      if (selected.state !== 'SERVER_CONFIRMED') throw new Error('服务器尚未确认完整上传，请刷新确认。')
      const restored = await request<LiveDraft>('read')
      apply(restored)
      taxonomy.value = await request<Taxonomy>('taxonomy')
      if (restored.jobs.length) {
        state.step = 'progress'
        try { job.value = await request<AnalysisJob>('job') }
        catch { check(); notice.value = '材料已恢复，历史任务暂未读到。请刷新进度重试；未创建新的分析。' }
      }
    })
    schedule(current, true)
  }
  async function refresh() { await run(async request => { apply(await request<LiveDraft>('read')); notice.value = '已读取服务保存的材料。' }) }
  async function importCollected(input: ExternalInput) {
    await run(async request => { apply(await request<LiveDraft>('import', input)); notice.value = '来源和未检查候选已补入；政策全文及附件仍未复核。' })
  }
  async function prepare() {
    await run(async (request, check) => {
      let value = await request<LiveDraft>('read'); apply(value)
      if (!value.sources.some(s => s.text?.trim() || s.url?.trim())) {
        await request('discover'); value = await request<LiveDraft>('read'); apply(value)
      }
      for (const source of [...value.sources]) {
        if (!source.text?.trim() && source.url) {
          try { value = await request<LiveDraft>('fetch', { source: source.id, revision: value.revision }); apply(value) }
          catch {
            check(); notice.value = '部分政策抓取未完成。可返回补充材料，也可继续分析；未取得的正文和缺证据状态仍保留。'
            // A lost response may already have advanced the server revision.
            try { value = await request<LiveDraft>('read'); apply(value) } catch { check() }
          }
        }
      }
      for (const source of [...value.sources]) {
        if (!source.text?.trim() || source.status === 'failed' || value.candidates.some(c => c.source_id === source.id)) continue
        try { value = await request<LiveDraft>('extract', { source: source.id, revision: value.revision }); apply(value) }
        catch { check(); notice.value = '自动候选未完成。可选用辅助入口或手动补充，也可直接分析；缺证据状态仍保留。' }
      }
      state.step = 'candidates'
    })
  }
  function encode(c: Candidate): WebCandidate {
    const text = state.sources.find(s => s.id === c.sourceId)?.text ?? ''
    const position = text.indexOf(c.quote)
    return { id: c.id, source_id: c.sourceId, excerpt: c.quote, data_type: c.dataType, checked: c.checked,
      polarity: c.polarity === 'AFFIRMED' ? 'AFFIRMATIVE' : c.polarity === 'NEGATED' ? 'NEGATIVE' : 'UNKNOWN',
      subject: c.subject === 'APP' ? 'HOST_APP' : c.subject === 'THIRD_PARTY' ? 'THIRD_PARTY' : 'UNKNOWN',
      condition: c.condition || null, action: c.action ?? 'UNKNOWN', declared_purpose: c.purpose || null,
      declared_recipient: c.recipient || null, start_offset: c.startOffset ?? (position < 0 ? null : [...text.slice(0, position)].length), ambiguity_flags: c.ambiguityFlags ?? [] }
  }
  async function save() { await run(async request => { if (draft.value) apply(await request<LiveDraft>('candidates', { revision: draft.value.revision, candidates: state.candidates.map(encode) })) }) }
  async function begin() {
    const current = generation
    await run(async (request, check) => {
      if (!draft.value) return
      const recover = async (latest: LiveDraft) => {
        if (!latest.jobs.length) { draft.value = latest; return false }
        apply(latest)
        state.step = 'progress'
        job.value = await request<AnalysisJob>('job')
        pendingStart = null
        return true
      }
      // Reconcile server state before every submission, including after remount.
      if (await recover(await request<LiveDraft>('read'))) return
      if (!pendingStart) {
        apply(await request<LiveDraft>('candidates', { revision: draft.value.revision, candidates: state.candidates.map(encode) }))
        pendingStart = { revision: draft.value.revision, request_id: crypto.randomUUID().replaceAll('-', '') }
      }
      try { job.value = await request<AnalysisJob>('start', pendingStart) }
      catch (cause) {
        check()
        if (!await recover(await request<LiveDraft>('read'))) throw cause
      }
      state.step = 'progress'
    })
    schedule(current, true)
  }
  async function poll() {
    const current = generation
    await run(async request => { job.value = await request<AnalysisJob>('job'); apply(await request<LiveDraft>('read')) })
    schedule(current)
  }
  async function control(action: 'cancel-job' | 'retry-job') {
    const current = generation
    await run(async request => { job.value = await request<AnalysisJob>(action); state.step = 'progress' })
    schedule(current, true)
  }
  async function openReport() { await run(async request => { report.value = await request<Report>('report'); state.step = 'report' }) }
  async function remove() {
    await run(async (_, check) => {
      const result = await bridge.remove()
      check()
      if (result.state === 'DELETED') { context.value = null; draft.value = null; job.value = null; report.value = null; state.step = 'import'; notice.value = result.cleanupPending ? '访问已撤销，服务器物理清理仍待完成。' : '服务器已确认删除。' }
    })
  }
  async function settings(configure = false) {
    await run(async (_, check) => { const value = await (configure ? bridge.configureModel() : bridge.modelStatus()); check(); model.value = value })
  }
  async function collect(modelName: string, app: string) {
    await run(async (_, check) => { const text = await bridge.collect(modelName, app); check(); modelResult.value = text; notice.value = '模型结果已放入回填框，请检查并确认来源类型；模型返回不等于已取得政策。' })
  }
  return { state, context, draft, job, report, taxonomy, busy, error, notice, model, modelResult, settings, collect, select, refresh, importCollected, prepare, save, begin, poll, control, openReport, remove, stop }
}
