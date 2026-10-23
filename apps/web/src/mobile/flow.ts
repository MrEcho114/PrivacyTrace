import { computed, reactive, ref } from 'vue'
import { freshWorkflow } from '../workflow'
import type { Candidate } from '../workflow'
import type { AnalysisJob, Report, Taxonomy, WebCandidate, WebSource } from '../types'
import type { LiveDraft } from '../liveApi'
import type { ExternalInput } from '../policyAssist'
import type { MobileBridge, Upload, ModelStatus } from './bridge'

// A native poll sends five HTTP reads. Keep the first progress read responsive,
// then leave room for two clients sharing the default 60/minute IP budget.
const FIRST_POLL_MS = 10_000, POLL_INTERVAL_MS = 25_000
type Request = <T>(name: string, body?: object) => Promise<T>
// WebIntake.captures() only captures a source that still has text and is not
// failed/empty/url_only. Mirror that precondition on the phone so the shell never
// offers a start the service must reject as an input/version conflict (#249).
const usableSource = (source: WebSource) =>
  !!source.text?.trim() && !['failed', 'empty', 'url_only'].includes(source.status ?? 'empty')

export function createMobileFlow(bridge: MobileBridge) {
  const state = reactive(freshWorkflow())
  const context = ref<Upload | null>(null), draft = ref<LiveDraft | null>(null)
  const job = ref<AnalysisJob | null>(null), report = ref<Report | null>(null), taxonomy = ref<Taxonomy | null>(null)
  const busy = ref(false), error = ref(''), notice = ref('')
  // 自动轮询仍在后台运行时，进度页要能说清“最近一次读到状态是什么时候”，
  // 而不是让用户误以为必须手点刷新。只记录真实成功的读取时间。
  const lastUpdated = ref('')
  const model = ref<ModelStatus>({ configured: false, endpoint: null }), modelResult = ref(''), resultToken = ref(0)
  // Starting without a body is always rejected by captures(), so the shell gates
  // the action on the same condition and explains the missing material (#249).
  const hasPolicyText = computed(() => !!draft.value?.sources.some(usableSource))
  let generation = 0, pendingStart: { revision: number; request_id: string } | null = null
  let busyPolls = 0
  let quickPolls = 0
  let nativeBusyRetries = 0
  let restoring = false
  let timer: ReturnType<typeof setTimeout> | undefined
  // Background polling is not abortable through the native bridge, so every
  // foreground action invalidates in-flight poll results with an epoch. A late
  // poll must never overwrite a newer cancellation, retry, instance or removal.
  let pollEpoch = 0
  const terminal = () => !!job.value && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.value.state)
  function stopPoll() {
    pollEpoch += 1
    clearTimeout(timer)
  }
  function schedule(current: number, first = false, quick = false) {
    if (current !== generation) return
    clearTimeout(timer)
    if ((!job.value && !restoring) || terminal()) return
    const throttled = error.value === 'SERVER_BUSY'
    if (error.value && !throttled) return
    busyPolls = throttled ? Math.min(busyPolls + 1, 3) : 0
    if (quick) quickPolls = 2
    // Native currently exposes a busy code, not response headers. Default to
    // the server's current 60s window; never replay a failed write operation.
    let delay = throttled ? 60_000 * 2 ** (busyPolls - 1) : first ? FIRST_POLL_MS : POLL_INTERVAL_MS
    if (!throttled && quickPolls > 0) { quickPolls -= 1; delay = 1_500 }
    const jitter = first && !throttled ? 0 : Math.floor(Math.random() * (throttled ? 10_000 : 4_000))
    timer = setTimeout(() => poll(true), delay + jitter)
  }
  // Candidate fields the editor can change. Comparing them with the last full
  // server snapshot tells a local edit apart from a newer server value (#273).
  const editableCandidateFields = ['sourceId', 'quote', 'dataType', 'polarity', 'subject', 'condition', 'checked', 'action', 'purpose', 'recipient', 'startOffset', 'ambiguityFlags'] as const
  let serverCandidates: WebCandidate[] = []
  function toCandidate(c: WebCandidate): Candidate {
    return { id: c.id, sourceId: c.source_id, quote: c.excerpt, dataType: c.data_type,
      polarity: c.polarity === 'AFFIRMATIVE' ? 'AFFIRMED' : c.polarity === 'NEGATIVE' ? 'NEGATED' : 'UNKNOWN',
      subject: c.subject === 'HOST_APP' ? 'APP' : c.subject === 'THIRD_PARTY' ? 'THIRD_PARTY' : 'UNKNOWN',
      condition: c.condition ?? '', checked: c.checked ?? false, action: c.action, purpose: c.declared_purpose ?? '',
      recipient: c.declared_recipient ?? '', startOffset: c.start_offset ?? undefined, ambiguityFlags: c.ambiguity_flags }
  }
  function snapshotCandidate(c: WebCandidate): WebCandidate {
    return { ...c, ambiguity_flags: c.ambiguity_flags ? [...c.ambiguity_flags] : c.ambiguity_flags }
  }
  function sameField(a: unknown, b: unknown) {
    return Array.isArray(a) && Array.isArray(b) ? a.length === b.length && a.every((value, index) => value === b[index]) : a === b
  }
  function mergeCandidateEdit(local: Candidate, incoming: Candidate, base: Candidate | undefined): Candidate {
    if (!base) return local
    const merged = { ...incoming }
    const current = local as unknown as Record<string, unknown>
    const previous = base as unknown as Record<string, unknown>
    const target = merged as unknown as Record<string, unknown>
    for (const field of editableCandidateFields) if (!sameField(current[field], previous[field])) target[field] = current[field]
    return merged
  }
  // An automatic poll must not discard what the candidate page keeps only in
  // memory. Locally changed fields and locally added candidates survive; a
  // locally deleted candidate is not resurrected; pristine fields and new server
  // candidates still follow the server. Explicit actions keep applying the full
  // server draft (including the save response), so save/refresh/delete/start stay
  // single-step and polling never issues a candidate write.
  function mergeCandidateEdits(incoming: WebCandidate[]): Candidate[] {
    const base = new Map(serverCandidates.map(c => [c.id, toCandidate(c)]))
    const next = new Map(incoming.map(c => [c.id, toCandidate(c)]))
    const local = new Set(state.candidates.map(c => c.id))
    const merged: Candidate[] = []
    for (const current of state.candidates) {
      const server = next.get(current.id)
      if (server) merged.push(mergeCandidateEdit(current, server, base.get(current.id)))
      else if (!base.has(current.id)) merged.push(current)
    }
    for (const raw of incoming) if (!local.has(raw.id) && !base.has(raw.id)) merged.push(toCandidate(raw))
    return merged
  }
  function apply(value: LiveDraft, preserveCandidateEdits = false) {
    draft.value = value
    state.sources = value.sources.map(s => ({ id: s.id, title: s.title, type: s.source_type ?? 'OFFICIAL_WEB_POLICY',
      url: s.url ?? '', text: s.text ?? '', status: s.status ?? 'empty', version: s.version ?? '', region: s.region ?? '',
      product: s.product ?? '', complete: false, provenance: s.provenance, modelAudit: s.model_audit }))
    state.candidates = preserveCandidateEdits ? mergeCandidateEdits(value.candidates) : value.candidates.map(toCandidate)
    serverCandidates = value.candidates.map(snapshotCandidate)
    if (!state.sources.some(s => s.id === state.sourceId)) state.sourceId = state.sources[0]?.id ?? ''
  }
  async function bridgeRequest<T>(name: string, body?: object): Promise<T> {
    const response = await bridge.request<T>(name, body)
    if (!context.value || response.origin !== context.value.origin || response.draft !== context.value.draft) throw new Error('INSTANCE_MISMATCH')
    return response.data
  }
  // Returns whether the action actually completed. A caller that shows a
  // success message (candidate save) must not receive `true` for a request it
  // never made: a busy gate or a superseded generation is not a saved write.
  async function run(action: (request: Request, check: () => void) => Promise<void>): Promise<boolean> {
    if (busy.value) return false
    stopPoll()
    busy.value = true; error.value = ''
    const current = generation
    const active = () => { if (generation !== current) throw new Error('CANCELLED') }
    const request = async <T>(name: string, body?: object): Promise<T> => {
      const response = await bridge.request<T>(name, body)
      active()
      if (!context.value || response.origin !== context.value.origin || response.draft !== context.value.draft) throw new Error('INSTANCE_MISMATCH')
      return response.data
    }
    let completed = false
    try { await action(request, active); completed = true }
    catch (cause) { if (current === generation) error.value = typeof cause === 'string' ? cause : cause instanceof Error ? cause.message : '操作未完成，请刷新确认。' }
    finally {
      if (current === generation) {
        busy.value = false
        if (typeof document !== 'undefined' && document.activeElement === document.body) document.getElementById('page-title')?.focus({ preventScroll: true })
        // stopPoll() ran when this action started, so a read or settings change
        // must hand the still-running job back to the poll. Terminal, deleted and
        // superseded states are rejected inside schedule() (#239).
        schedule(current, true)
      }
    }
    return completed
  }
  async function stop() {
    generation++; stopPoll(); busy.value = false
    notice.value = '已停止当前请求。服务可能已保存结果，请刷新确认；停止读取不等于取消分析或删除材料。'
    await bridge.cancel().catch(() => {})
  }
  async function readSelection(request: Request, check: () => void) {
    const restored = await request<LiveDraft>('read')
    apply(restored)
    taxonomy.value = await request<Taxonomy>('taxonomy')
    if (restored.jobs.length) {
      state.step = 'progress'
      try { job.value = await request<AnalysisJob>('job'); lastUpdated.value = new Date().toISOString() }
      catch (cause) {
        check()
        if (cause === 'SERVER_BUSY' || (cause instanceof Error && cause.message === 'SERVER_BUSY')) throw cause
        notice.value = '材料已恢复，历史任务暂未读到。请刷新进度重试；未创建新的分析。'
      }
    }
    check(); restoring = false
  }
  async function select(restore = false) {
    const current = generation
    await run(async (request, check) => {
      const selected = await (restore ? bridge.restore() : bridge.upload())
      check()
      // Native lifecycle cancellation rejects the selected result as well.
      context.value = selected; draft.value = null; job.value = null; report.value = null; pendingStart = null
      // A model answer belongs to the material instance that was collected for.
      // Dropping it here keeps a deleted or replaced material from refilling the
      // shared assistant box with the previous result (#243).
      modelResult.value = ''
      state.step = 'import'; notice.value = ''; restoring = false
      if (selected.state !== 'SERVER_CONFIRMED') throw new Error('服务器尚未确认完整上传，请刷新确认。')
      restoring = true
      await readSelection(request, check)
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
      // A failed fetch that still answers 200 lands here too: the source is kept
      // with status=failed and no text, and captures() would reject the start as a
      // version/input conflict the user cannot fix by refreshing (#249).
      if (!value.sources.some(usableSource)) {
        state.step = 'import'
        throw new Error('各份来源均未获得正文。请重试网址，或粘贴／导入政策文本。')
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
  // A save that never reached the service (no draft, busy gate, bridge error)
  // resolves false so the candidate page keeps its edit and withholds "已保存".
  async function save(): Promise<boolean> {
    if (!draft.value) return false
    return await run(async request => { if (draft.value) apply(await request<LiveDraft>('candidates', { revision: draft.value.revision, candidates: state.candidates.map(encode) })) })
  }
  async function begin() {
    const current = generation
    nativeBusyRetries = 0
    // The step rail can reach candidates without preparing, so the start action
    // repeats the precondition instead of letting the server reject a save that a
    // refresh can never repair (#249). An existing job still resumes below.
    if (draft.value && !hasPolicyText.value && !draft.value.jobs.length) {
      error.value = '各份来源均未获得正文，无法开始分析。请返回材料页重试网址，或粘贴／导入政策文本。'
      return
    }
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
      try {
        job.value = await request<AnalysisJob>('start', pendingStart)
        lastUpdated.value = new Date().toISOString()
      }
      catch (cause) {
        check()
        if (!await recover(await request<LiveDraft>('read'))) throw cause
      }
      state.step = 'progress'
    })
    schedule(current, true, true)
  }
  async function poll(background = false) {
    const current = generation
    if (background) {
      if (busy.value) return
      if (restoring) {
        await run(async (request, check) => { await readSelection(request, check) })
        schedule(current)
        return
      }
      const epoch = ++pollEpoch
      try {
        // The native workflow bridge admits one operation at a time; issue the
        // job and draft reads one after another so the second call can never be
        // rejected as BUSY_OR_INACTIVE (regression introduced by #145).
        const nextJob = await bridgeRequest<AnalysisJob>('job')
        const latest = await bridgeRequest<LiveDraft>('read')
        if (current !== generation || epoch !== pollEpoch || busy.value) return
        job.value = nextJob
        lastUpdated.value = new Date().toISOString()
        // The candidate page is editable while an automatic poll runs, so progress
        // and the server revision update here but local candidate edits survive.
        apply(latest, true)
        error.value = ''
        nativeBusyRetries = 0
        schedule(current)
      } catch (cause) {
        if (current !== generation || epoch !== pollEpoch || busy.value) return
        if (cause instanceof Error && ['CANCELLED', 'INSTANCE_MISMATCH'].includes(cause.message)) return
        const message = typeof cause === 'string' ? cause : cause instanceof Error ? cause.message : '暂时无法刷新进度。'
        // A foreground action can hold the native gate while this automatic read
        // runs; retry quickly a bounded number of times instead of stopping the
        // progress loop until the user refreshes by hand.
        if (message === 'BUSY_OR_INACTIVE' && nativeBusyRetries < 3) {
          nativeBusyRetries += 1
          error.value = ''
          clearTimeout(timer)
          timer = setTimeout(() => poll(true), 1_500)
          return
        }
        error.value = message
        schedule(current)
      }
      return
    }
    await run(async (request, check) => {
      if (restoring) await readSelection(request, check)
      else {
        job.value = await request<AnalysisJob>('job')
        lastUpdated.value = new Date().toISOString()
        apply(await request<LiveDraft>('read'))
      }
    })
    schedule(current)
  }
  async function control(action: 'cancel-job' | 'retry-job') {
    const current = generation
    await run(async request => {
      job.value = await request<AnalysisJob>(action)
      lastUpdated.value = new Date().toISOString()
      state.step = 'progress'
    })
    schedule(current, true, true)
  }
  async function openReport() { await run(async request => { report.value = await request<Report>('report'); state.step = 'report' }) }
  async function remove() {
    await run(async (_, check) => {
      const result = await bridge.remove()
      check()
      if (result.state === 'DELETED') { restoring = false; context.value = null; draft.value = null; job.value = null; report.value = null; state.step = 'import'; notice.value = result.cleanupPending ? '访问已撤销，服务器物理清理仍待完成。' : '服务器已确认删除。' }
    })
  }
  async function settings(configure = false) {
    await run(async (_, check) => { const value = await (configure ? bridge.configureModel() : bridge.modelStatus()); check(); model.value = value })
  }
  async function collect(modelName: string, app: string) {
    await run(async (_, check) => {
      const text = await bridge.collect(modelName, app)
      check()
      modelResult.value = text
      // The assistant box is remounted on every return to the material step. A
      // repeated identical answer must still count as a new delivery, so the
      // counter travels with the text instead of relying on ref inequality (#243).
      resultToken.value += 1
      notice.value = '模型结果已放入回填框，请检查并确认来源类型；模型返回不等于已取得政策。'
    })
  }
  // The candidate page offers one retry per source. Each click is a single native
  // call under the normal busy/generation/epoch guards, so a late answer cannot
  // overwrite a newer material and no model call is replayed automatically (#248).
  async function retrySource(id: string) {
    await run(async request => {
      const source = draft.value?.sources.find(item => item.id === id)
      if (!draft.value || !source) throw new Error('这份来源已不在当前材料中，请重新读取材料。')
      if (!source.url?.trim()) throw new Error('这份来源没有可重新获取的网址，请返回材料页粘贴或导入政策文本。')
      const value = await request<LiveDraft>('fetch', { source: id, revision: draft.value.revision })
      apply(value)
      const updated = value.sources.find(item => item.id === id)
      notice.value = updated && usableSource(updated)
        ? `${updated.title || '这份来源'}：已重新获取正文；未检查候选仍需确认，政策全文及附件未复核。`
        : `${updated?.title || '这份来源'}：重新获取后仍未取得正文；可重试，或返回材料页手动补入。`
    })
  }
  async function retryModel(id: string) {
    await run(async request => {
      const source = draft.value?.sources.find(item => item.id === id)
      if (!draft.value || !source) throw new Error('这份来源已不在当前材料中，请重新读取材料。')
      // Same precondition as WebIntake._extract: text present and the source not
      // marked failed. A model call on a body-less source can only fail.
      if (!source.text?.trim() || source.status === 'failed') throw new Error('这份来源尚未取得正文，无法提取候选；请先重新获取来源或手动补入正文。')
      const value = await request<LiveDraft>('extract', { source: id, revision: draft.value.revision })
      apply(value)
      const failed = value.sources.find(item => item.id === id)?.model_audit?.status === 'FAILED'
      notice.value = failed
        ? `${source.title || '这份来源'}：候选提取仍未完成；可再次重试或手动补充，缺证据状态保留。`
        : `${source.title || '这份来源'}：候选提取已完成；候选仍需检查，政策全文及附件未复核。`
    })
  }
  return { state, context, draft, job, report, taxonomy, busy, error, notice, lastUpdated, model, modelResult, resultToken, hasPolicyText, settings, collect, select, refresh, importCollected, prepare, save, begin, poll, control, openReport, remove, retrySource, retryModel, stop }
}
