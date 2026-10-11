import type { Evidence } from './types'

/**
 * SDK attribution is reference material, not a privacy finding.
 *
 * The privacy comparison renders only the evidence its issues cite, and by design
 * an SDK label is never cited by an issue (an SDK's static presence creates no
 * behaviour). SDK evidence therefore needs its own access path, or it stays in
 * `report.evidence` counted-but-unreachable.
 *
 * These helpers stay deliberately dumb: they select, count and paginate the
 * evidence records the worker already produced. No field of `excerpt` is parsed,
 * so the panel cannot drift out of sync with the worker's wording.
 */

/** Entries per page. A scan can contribute up to the worker's SDK output cap. */
export const SDK_PAGE_SIZE = 25

export function getSdkEvidence(evidence: readonly Evidence[]): Evidence[] {
  return evidence.filter((item) => item.kind === 'SDK')
}

/** Pages needed for `total` entries; always at least one so the UI can say "1 / 1". */
export function sdkPageCount(total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 1
  return Math.ceil(total / SDK_PAGE_SIZE)
}

/** Clamp a requested page into range, so a shrinking report cannot strand it. */
export function clampSdkPage(page: number, total: number): number {
  const last = sdkPageCount(total) - 1
  if (!Number.isFinite(page) || page < 0) return 0
  return Math.min(Math.floor(page), last)
}

export function sdkPageSlice(
  evidence: readonly Evidence[],
  page: number,
): Evidence[] {
  const safe = clampSdkPage(page, evidence.length)
  return evidence.slice(safe * SDK_PAGE_SIZE, (safe + 1) * SDK_PAGE_SIZE)
}
