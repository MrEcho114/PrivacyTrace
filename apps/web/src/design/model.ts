import type { PolicyStateCopyInput } from '../copy'

/**
 * Presentation-only model. The future adapter maps generated contracts into this
 * shape; components never evaluate policies or infer a source/coverage/review.
 */
export interface DesignEvidence {
  id: string
  kind: string
  locator: string
  excerpt: string
}
export interface DesignFinding {
  id: string
  dataType: string
  title: string
  review: string
  conclusion: string
  description: string
  evidenceIds: string[]
}
export interface DesignReport {
  name: string
  version: string
  packageName: string
  source: string
  delivery: string
  coverage: string
  review: PolicyStateCopyInput['review_status']
  extraction: string
  completeness: PolicyStateCopyInput['completeness']
  attachments: PolicyStateCopyInput['attachments_status']
  policySources: { id: string; title: string; text: string }[]
  findings: DesignFinding[]
  evidence: DesignEvidence[]
}

/** Deliberately synthetic: no REAL_SCAN or runtime claim is made by this fixture. */
export const reportFixture: DesignReport = {
  name: '手机端验收示例', version: '1.0.7', packageName: 'example.privacytrace.design',
  source: 'DEMO / 合成材料', delivery: '设计示例 / 未连接分析服务',
  coverage: 'PARTIAL / 部分覆盖', review: 'UNREVIEWED',
  extraction: 'PARTIAL / 提取未完成', completeness: null,
  attachments: 'NOT_CHECKED',
  policySources: [{
    id: 'policy-01', title: '示例政策 01',
    text: '为提供附近服务，应用可能读取精确位置信息。本段未说明保留期限，需结合适用版本与完整政策核验。',
  }],
  findings: [
    { id: 'finding-location', dataType: 'location', title: '位置信息',
      review: '条目待复核', conclusion: '证据不足',
      description: '政策提到精确位置读取与附近服务目的，但没有说明保留期限。',
      evidenceIds: ['evidence-invoke', 'evidence-policy'] },
    { id: 'finding-device', dataType: 'device_id', title: '设备标识',
      review: '条目待复核', conclusion: '证据不足',
      description: '当前材料缺少适用声明，需核对版本、完整政策原文和静态线索。',
      evidenceIds: ['evidence-manifest'] },
  ],
  evidence: [
    { id: 'evidence-invoke', kind: '静态调用线索',
      locator: '合成 DEX · example/LocationReader.read · 指令偏移 0x12',
      excerpt: '人工构造的静态片段：LocationManager.getLastKnownLocation。' },
    { id: 'evidence-policy', kind: '政策声明',
      locator: '示例政策 01 · 第 1 段',
      excerpt: '为提供附近服务，应用可能读取精确位置信息。' },
    { id: 'evidence-manifest', kind: '清单权限能力',
      locator: '合成 AndroidManifest.xml · uses-permission',
      excerpt: '示例权限：READ_PHONE_STATE。权限表示能力，不能据此认定实际访问了设备标识。' },
  ],
}

export function fixtureFor(state: string | null): DesignReport {
  const value = structuredClone(reportFixture)
  if (state === 'empty') {
    value.findings = []; value.evidence = []; value.policySources = []
    value.coverage = 'UNKNOWN / 尚无结果'
  }
  if (state === 'unknown') {
    value.source = 'UNKNOWN / 来源未确认'; value.delivery = 'UNKNOWN / 送达方式未知'
    value.coverage = 'UNKNOWN / 覆盖未知'; value.review = null
    value.extraction = 'UNKNOWN / 提取未知'
    value.findings.forEach(finding => { finding.review = '条目复核未知' })
  }
  if (state === 'long') {
    value.name = '用于验证窄屏、大字与长应用名称换行的合成示例应用'
    value.packageName = 'example.privacytrace.design.long_package_identifier_for_layout_validation_only'
    value.findings[0]!.description += '请核对原文上下文、适用版本、政策来源与附件；没有检查的内容仍须保留未知，不能转换成确定结论。'.repeat(3)
  }
  return value
}
