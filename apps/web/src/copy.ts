// Initial copy: Gemini 3.8 Flash Medium. Edited on 2026-10-13 for clarity;
// scope and evidence limits checked against the implementation.
// 2026-10-22: #167 adopted into #165; 21 unreferenced keys were removed after
// confirming no component read them. New names live in frontendCopy.
export const copy = {
  "importDescription": "准备 APK 和各份政策，也可以先用示例熟悉对照流程。",
  "apkHelp": "文件还不会上传；这里只显示名称和大小，刷新后需重新选择。",
  "apkPlaceholder": "选择本地 APK 文件",
  "policyHelp": "粘贴正文或导入 TXT、Markdown 文件。网址暂不会自动抓取；刷新后需重新输入正文。",
  "demoHelp": "用一组固定材料走完四步。阶段由你切换，修改候选不会改变示例报告。",
  "tryDemo": "体验示例",
  "realReports": "已有报告",
  "nextCandidates": "检查候选",
  "candidateHelp": "对照原文，检查每条候选的内容和适用条件。检查这些条款不代表政策全文已复核。",
  "nextProgress": "进入流程演示",
  "addCandidate": "添加候选",
  "saveCandidate": "保存候选",
  "deleteCandidate": "删除候选",
  "quoteMissing": "尚无可引用的原句",
  "quoteRequired": "请粘贴这份政策中的原句。",
  "quoteNotFound": "未在当前来源中找到这句话，请核对原文。",
  "quoteUnavailable": "来源获取失败，请先重试，再核对原句。",
  "quoteMatched": "已在当前来源中找到原句。",
  "progressDescription": "手动切换阶段，了解分析顺序。这里不会执行 APK 扫描。",
  "nextStage": "进入下一阶段",
  "failStage": "标记当前阶段失败",
  "cancel": "取消",
  "retry": "重试",
  "viewReport": "查看报告",
  "reportHelp": "这是固定示例报告，修改材料或候选不会改变这里的结果。",
  "settingsTitle": "服务与存储设置",
  "settingsDescription": "设置本项目的模型连接、检查服务，或清除浏览器中的示例草稿。",
  "storageHelp": "自动保存示例选项和阅读进度。自填文本只在本次打开期间保留，刷新后会丢失。",
  "clearDraft": "清除示例草稿",
  "draftCleared": "已清除示例草稿。",
  "connectionHelp": "检查本机服务是否有响应。Docker 扫描和模型请求的结果分别显示在实际任务中。",
  "notConnected": "未连接分析服务",
  "saved": "已保存",
  "sourceFailed": "示例来源获取失败",
  "missingText": "还没有正文，请粘贴或导入文本。",
  "fileInvalid": "文件格式不支持，请选择 APK 文件",
  "fileTooLarge": "文件超出大小限制",
  "draftRestored": "已恢复示例进度与选项",
  "sourceScopeUnknown": "适用范围不明",
  "refreshConnection": "测试连接",
  "close": "关闭",
  "back": "返回",
  "completeStage": "完成当前阶段",
  "editMaterials": "修改材料"
} as const

// Adopted #167 vocabulary. Every runtime page, the report shell and the
// independent design foundation read names from here; no component keeps its
// own step, stage or page-title list.
const steps = ['APK 与政策材料', '核对政策声明', '扫描与对照进度', '对照报告'] as const
const reportTitleParts = ['APP', '隐私收集越权报告'] as const
const reportTitle = reportTitleParts.join(' ')

export type JobStage =
  | 'QUEUED' | 'INTAKE' | 'STATIC_ANALYSIS' | 'POLICY_PARSING'
  | 'EVALUATING' | 'REPORTING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'

/** The nine job states. {#167} fixed these names; the map is the only definition. */
const stageNames: Record<JobStage, string> = {
  QUEUED: '等待处理',
  INTAKE: '核对材料',
  STATIC_ANALYSIS: '隔离扫描 APK',
  POLICY_PARSING: '装载政策原文',
  EVALUATING: '规则对照',
  REPORTING: '生成报告',
  SUCCEEDED: '报告已生成',
  FAILED: '分析失败',
  CANCELLED: '已取消',
}

export const frontendCopy = {
  steps,
  brandSubtitle: '隐私权限使用与隐私声明对照',
  reportTitle,
  reportTitleParts,
  comparisonTitle: '数据类型与政策声明对照',
  reportScope: '对照 APK 中的权限、调用位置与政策原文。',
  comparisonScope: '六种结论只回答政策是否提到相应数据类型，不作合规判断。',
  demoBadge: '示例体验 · 固定材料',
  // Step labels and page h1s share one literal: pageTitles derives from steps.
  pageTitles: {
    import: steps[0],
    candidates: steps[1],
    progress: steps[2],
    report: reportTitle,
    reports: '本机存档报告',
  },
  stages: stageNames,
  stageOrder: Object.keys(stageNames) as JobStage[],
  table: { dataType: '数据类型', evidence: '证据' },
  // One fact, one place: each sentence renders at the location named in
  // docs/design/concept-foundation/copy-contract-167.md.
  facts: {
    permission: '权限只代表应用申请过，不代表已经访问。',
    staticRuntime: '静态线索不证明运行时采集。',
    coverage: '规则集覆盖有限，没有命中规则不代表没有隐私行为。',
    sdkAttribution: 'SDK 归属只按公开包前缀匹配，不代表实际收集或外传。',
    notDeclared: '“未找到声明”需要适用版本、完整正文、提取成功、全文复核、附件齐全五项同时成立；缺一项只能算证据不足。',
    candidateUnconfirmed: '候选尚未确认对应关系，确认后才进入对照。',
    noCandidates: '没有候选只说明这份来源还没整理，不代表政策没有声明。',
    archiveNoRescan: '查看本机存档不会重新扫描。',
    modelTextOnly: '模型只接收政策文本，APK 不发送给模型。',
    assistUnreviewed: '网页补入的来源仍是未复核。',
  },
} as const

export interface PolicyStateCopyInput {
  review_status?: 'UNREVIEWED' | 'REVIEWED' | null
  completeness?: 'COMPLETE' | 'PARTIAL' | null
  attachments_status?: 'NOT_CHECKED' | 'COMPLETE' | 'MISSING' | null
}

/** Missing facts remain unknown; never infer review from text availability. */
export function policyStateLine(state: PolicyStateCopyInput): string {
  const review = state.review_status === 'REVIEWED' ? '来源已复核'
    : state.review_status === 'UNREVIEWED' ? '来源未复核' : '来源复核状态未知'
  const completeness = state.completeness === 'COMPLETE' ? '正文完整'
    : state.completeness === 'PARTIAL' ? '正文不完整' : '正文完整度未知'
  const attachments = state.attachments_status === 'COMPLETE' ? '附件齐全'
    : state.attachments_status === 'MISSING' ? '附件缺失'
      : state.attachments_status === 'NOT_CHECKED' ? '附件未检查' : '附件状态未知'
  return [review, completeness, attachments].join(' · ')
}
