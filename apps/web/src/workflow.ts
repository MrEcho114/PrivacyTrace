// Shared editor state and explicit synthetic interaction data. API calls live in liveApi.ts.
export type Step = 'import' | 'candidates' | 'progress' | 'report'
export type SourceType = 'OFFICIAL_WEB_POLICY' | 'SDK_POLICY' | 'STORE_POLICY' | 'IN_APP_POLICY'
export type Candidate = {
  id: string; sourceId: string; quote: string; dataType: string
  polarity: 'AFFIRMED' | 'NEGATED' | 'UNKNOWN'; subject: 'APP' | 'THIRD_PARTY' | 'UNKNOWN'
  condition: string; checked: boolean
  action?: 'ACCESS' | 'UNKNOWN'; purpose?: string; recipient?: string
  startOffset?: number; ambiguityFlags?: ('CATCH_ALL' | 'UNCLEAR_ACTION')[]
}
export type PolicySource = {
  id: string; title: string; url: string; type: SourceType; text: string
  status: 'ready' | 'failed' | 'manual' | 'empty'; version: string; region: string
  product: string; complete: boolean
  packageName?: string; versionCode?: number | null
  capturedAt?: string | null; sha256?: string | null; errorCode?: string | null
  modelAudit?: Record<string, unknown>
}
export type Workflow = {
  example: boolean; step: Step; maxStep: number; sourceId: string
  sources: PolicySource[]; candidates: Candidate[]; stage: number
  outcome: 'idle' | 'failed' | 'cancelled' | 'complete'; filter: string; evidenceId: string
}
export const steps: Step[] = ['import', 'candidates', 'progress', 'report']
export const sourceTypes: Record<SourceType, string> = {
  OFFICIAL_WEB_POLICY: '官网政策', SDK_POLICY: 'SDK 自有政策', STORE_POLICY: '应用商店政策', IN_APP_POLICY: '应用内政策',
}
export const dataTypes: Record<string, string> = { location: '位置信息', device_id: '设备标识', camera: '相机', contacts: '联系人' }
export const stageNames = ['核对输入', '静态线索', '政策候选', '规则对照', '报告']
export const exampleSources: PolicySource[] = [
  { id: 'host', title: '纸舟地图隐私政策', url: 'https://example.com/paperboat/privacy', type: 'OFFICIAL_WEB_POLICY',
    text: '纸舟地图隐私政策\n\n一、附近地点\n当您主动打开“附近地点”时，我们会读取您的位置信息，用于展示周边地点。关闭该功能后，不再读取位置信息。\n\n二、设备与账号\n我们不会读取您的通讯录。用于统计的设备标识由第三方统计服务处理。\n\n三、第三方服务\n第三方服务的处理方式，请查阅对应服务的隐私政策及附件列表。',
    status: 'ready', version: '示例 1.0', region: 'UNKNOWN', product: '纸舟地图', complete: false },
  { id: 'sdk', title: '云点统计服务说明', url: 'https://example.com/cloudpoint/privacy', type: 'SDK_POLICY',
    text: '云点统计服务说明\n\n我们会处理设备标识，用于统计应用使用情况。\n服务是否启用由接入应用决定。\n\n本说明只描述云点统计服务，不代表接入应用的全部政策。',
    status: 'ready', version: '示例 1.0', region: 'UNKNOWN', product: '云点统计服务', complete: false },
]
export const exampleCandidates: Candidate[] = [
  { id: 'location', sourceId: 'host', quote: '当您主动打开“附近地点”时，我们会读取您的位置信息，用于展示周边地点。', dataType: 'location', polarity: 'AFFIRMED', subject: 'APP', condition: '主动打开“附近地点”', checked: false },
  { id: 'contacts', sourceId: 'host', quote: '我们不会读取您的通讯录。', dataType: 'contacts', polarity: 'NEGATED', subject: 'APP', condition: '', checked: false },
  { id: 'device', sourceId: 'host', quote: '用于统计的设备标识由第三方统计服务处理。', dataType: 'device_id', polarity: 'AFFIRMED', subject: 'THIRD_PARTY', condition: '', checked: false },
  { id: 'sdk-device', sourceId: 'sdk', quote: '我们会处理设备标识，用于统计应用使用情况。', dataType: 'device_id', polarity: 'AFFIRMED', subject: 'THIRD_PARTY', condition: '由接入应用决定', checked: false },
]
export function freshWorkflow(example = false): Workflow {
  return { example, step: 'import', maxStep: 0, sourceId: example ? 'host' : 'source-1',
    sources: example ? structuredClone(exampleSources) : [emptySource('source-1')],
    candidates: example ? structuredClone(exampleCandidates) : [], stage: 0, outcome: 'idle', filter: 'all', evidenceId: '' }
}
export function emptySource(id: string): PolicySource {
  return { id, title: '', url: '', type: 'OFFICIAL_WEB_POLICY', text: '', status: 'empty', version: '', region: '', product: '', complete: false }
}
export function quoteExists(candidate: Candidate, sources: PolicySource[]): boolean {
  const source = sources.find(item => item.id === candidate.sourceId)
  return !!source && source.status !== 'failed' && candidate.quote.trim().length > 0 && source.text.includes(candidate.quote)
}

// Only predefined example IDs and enum edits are persisted. Arbitrary user text,
// local files, URLs, conditions and policy bodies stay in memory.
export const draftKey = 'privacytrace.example.v1'
export function saveDraft(state: Workflow): string | null {
  if (!state.example) return null
  return JSON.stringify({ version: 1, step: state.step, maxStep: state.maxStep, sourceId: state.sourceId,
    stage: state.stage, outcome: state.outcome, filter: state.filter, evidenceId: state.evidenceId,
    sources: state.sources.filter(item => exampleSources.some(original => original.id === item.id)).map(item => ({ id: item.id, status: item.status })),
    candidates: state.candidates.filter(item => exampleCandidates.some(original => original.id === item.id)).map(item => {
      const original = exampleCandidates.find(candidate => candidate.id === item.id)!
      const source = state.sources.find(candidate => candidate.id === item.sourceId)
      const originalSource = exampleSources.find(candidate => candidate.id === item.sourceId)
      return { id: item.id, dataType: Object.hasOwn(dataTypes, item.dataType) ? item.dataType : 'location', polarity: item.polarity, subject: item.subject,
        checked: item.checked && item.quote === original.quote && item.condition === original.condition && source?.text === originalSource?.text }
    }) })
}
export function restoreDraft(raw: string | null): Workflow | null {
  if (!raw || raw.length > 10000) return null
  try {
    const saved = JSON.parse(raw)
    if (saved.version !== 1 || !Array.isArray(saved.candidates) || !Array.isArray(saved.sources)) return null
    const state = freshWorkflow(true)
    state.maxStep = Number.isInteger(saved.maxStep) ? Math.max(0, Math.min(3, saved.maxStep)) : 0
    state.step = steps.includes(saved.step) && steps.indexOf(saved.step) <= state.maxStep ? saved.step : 'import'
    state.sources = state.sources.filter(source => saved.sources.some((item: { id?: string }) => item.id === source.id))
    if (!state.sources.length) return null
    state.sourceId = state.sources.some(item => item.id === saved.sourceId) ? saved.sourceId : state.sources[0]!.id
    state.stage = Number.isInteger(saved.stage) ? Math.max(0, Math.min(4, saved.stage)) : 0
    state.outcome = ['idle', 'failed', 'cancelled', 'complete'].includes(saved.outcome) ? saved.outcome : 'idle'
    if (state.outcome === 'complete') state.stage = 4
    if (state.step === 'report' && state.outcome !== 'complete') state.step = 'progress'
    state.filter = ['all', 'host', 'sdk'].includes(saved.filter) ? saved.filter : 'all'
    state.evidenceId = ['location', 'device', 'camera'].includes(saved.evidenceId) ? saved.evidenceId : ''
    state.sources.forEach(source => {
      if (saved.sources.some((item: { id?: string; status?: string }) => item.id === source.id && item.status === 'failed')) source.status = 'failed'
    })
    state.candidates = state.candidates.filter(candidate => state.sources.some(source => source.id === candidate.sourceId) && saved.candidates.some((item: { id?: string }) => item.id === candidate.id))
    state.candidates.forEach(candidate => {
      const item = saved.candidates.find((entry: { id?: string }) => entry.id === candidate.id)
      if (Object.hasOwn(dataTypes, item.dataType)) candidate.dataType = item.dataType
      if (['AFFIRMED', 'NEGATED', 'UNKNOWN'].includes(item.polarity)) candidate.polarity = item.polarity
      if (['APP', 'THIRD_PARTY', 'UNKNOWN'].includes(item.subject)) candidate.subject = item.subject
      candidate.checked = item.checked === true
    })
    return state
  } catch { return null }
}

export const exampleRows = [
  { id: 'location', type: '位置信息', source: 'host', signal: '位置权限与潜在调用', status: '具体类型已声明', tone: 'success',
    explanation: '示例原句提到位置信息，并限定为主动打开附近地点。此处只对照数据类型，条件仍需结合上下文核对。',
    locator: 'com.paperboat.nearby.NearbyScreen → openNearby · offset 0x18',
    code: '// 人工构造的静态片段\ninvoke-virtual {v0}, Landroid/location/LocationManager;\n  ->getLastKnownLocation(Ljava/lang/String;)\n    Landroid/location/Location;',
    quote: exampleCandidates[0]!.quote },
  { id: 'device', type: '设备标识', source: 'sdk', signal: '设备标识潜在调用', status: '证据不足', tone: 'wait',
    explanation: 'SDK 说明提到设备标识，但不能替接入应用补充声明。宿主来源的范围与附件仍待核对。',
    locator: 'com.paperboat.analytics.Client → initialize · offset 0x24',
    code: '// 人工构造的静态片段\ninvoke-static {v0}, Landroid/provider/Settings$Secure;\n  ->getString(Landroid/content/ContentResolver;\n    Ljava/lang/String;)Ljava/lang/String;', quote: exampleCandidates[3]!.quote },
  { id: 'camera', type: '相机', source: 'host', signal: '相机权限', status: '证据不足', tone: 'wait',
    explanation: '示例声明了相机权限。政策节选没有对应候选，但正文与附件不完整，不能据此认定未声明。',
    locator: 'AndroidManifest.xml · uses-permission', code: '<uses-permission android:name="android.permission.CAMERA" />', quote: '' },
] as const
