<script setup lang="ts">
import { frontendCopy } from '../copy'

// The mobile report's first screen. Report-level metadata is folded at the end
// of the report (MobileApp) per #165, so this block only carries identity,
// scope/boundary and the counts a reader needs before the finding list.
defineProps<{
  name: string
  version: string
  packageName: string
  sourceBadge: string
  sourceDescription: string
  deliveryBadge: string
  deliveryDescription: string
  generatedAt?: string
  generatedAtLabel?: string
  dataTypeCount: number
  policyCount: number
  evidenceCount: number
  material?: { origin: string; draft: string; revision?: number }
}>()
defineEmits<{ changeMaterial: [] }>()
</script>

<template>
  <section class="mobile-report-summary" aria-label="报告摘要">
    <header class="reading-identity">
      <span class="reading-mark" aria-hidden="true">PT</span>
      <div><h2>{{ name }}</h2><p class="reading-version">版本 {{ version }}</p></div>
    </header>
    <div class="reading-origin" aria-label="来源与查看方式">
      <span>{{ sourceBadge }}</span><span>{{ deliveryBadge }}</span>
    </div>
    <p class="reading-scope">{{ frontendCopy.reportScope }}</p>
    <p class="reading-boundary">{{ frontendCopy.facts.staticRuntime }}</p>
    <dl class="reading-counts">
      <div><dt>{{ frontendCopy.table.dataType }}</dt><dd>{{ dataTypeCount }}</dd></div>
      <div><dt>政策来源</dt><dd>{{ policyCount }}</dd></div>
      <div><dt>可查看证据</dt><dd>{{ evidenceCount }}</dd></div>
    </dl>
  </section>
</template>

<style scoped>
.mobile-report-summary { padding: 16px 16px 14px; margin-bottom: 12px; border: 1px solid var(--pt-rule); border-radius: var(--m-card-radius); background: var(--pt-paper); }
.reading-identity { display: flex; align-items: center; gap: 12px; }
.reading-mark { display: grid; place-items: center; width: 44px; height: 44px; flex: none; border-radius: 10px; background: var(--pt-structure); color: var(--pt-paper); font-family: var(--pt-font-code); font-size: 0.9375rem; font-weight: 600; }
.reading-identity > div { min-width: 0; }
.reading-identity h2 { margin: 0; font-family: var(--pt-font-display); font-size: var(--pt-type-finding-mobile); font-weight: 600; line-height: 1.35; overflow-wrap: anywhere; color: var(--pt-ink); }
.reading-version { margin: 2px 0 0; color: var(--pt-muted); font-size: var(--m-caption); }
.reading-origin { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.reading-origin > span { padding: 3px 8px; border: 1px solid var(--pt-rule); border-radius: 6px; color: var(--pt-ink); font-size: var(--m-caption); line-height: 1.5; overflow-wrap: anywhere; }
.reading-scope { margin: 12px 0 0; color: var(--pt-ink); font-size: var(--pt-type-reading); line-height: 1.6; }
.reading-boundary { margin: 4px 0 12px; color: var(--pt-muted); font-size: var(--m-caption); line-height: 1.6; }
.reading-counts { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0; padding: 12px 0 0; border-top: 1px solid var(--pt-rule); }
.reading-counts > div { display: flex; align-items: baseline; gap: 6px; }
.reading-counts dt { font-size: var(--m-caption); color: var(--pt-muted); }
.reading-counts dd { margin: 0; color: var(--pt-ink); font-size: var(--pt-type-finding-mobile); font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
</style>
