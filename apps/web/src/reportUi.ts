/**
 * Report reading helpers shared by the desktop columns, the evidence panel and
 * the example report. Row numbers are a presentation detail: they always count
 * from the report's own issue order, never from a filtered subset.
 */
export function reportRowNumber(index: number): string {
  return index < 0 ? '--' : String(index + 1).padStart(2, '0')
}
