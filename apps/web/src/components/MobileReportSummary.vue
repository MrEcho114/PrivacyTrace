<script setup lang="ts">
import { computed } from 'vue'
import { frontendCopy } from '../copy'

// The mobile report's first screen. Report-level metadata is folded at the end
// of the report (MobileApp) per #165, so this block only carries identity,
// scope/boundary, the result limits a reader must see before the findings, and
// the counts. Internal source/delivery codes stay behind “来源标识” instead of
// competing with the Chinese labels (#295 §5/§6).
const props = defineProps<{
  name: string
  version: string
  sourceBadge: string
  deliveryBadge: string
  coverageStatus?: 'COMPLETE' | 'PARTIAL' | null
  reviewCount?: number
  dataTypeCount: number
  policyCount: number
  evidenceCount: number
  policyStates: string[]
}>()
const human = (badge: string) => badge.split(' · ')[0]?.trim() || badge
const coverageLine = computed(() => props.coverageStatus === 'PARTIAL'
  ? '扫描范围不完整 · PARTIAL：部分 DEX 未完成'
  : props.coverageStatus === 'COMPLETE' ? '扫描范围完整：已扫描所支持的 DEX' : '')
</script>

<template>
  <section class="mobile-report-summary" aria-label="报告摘要">
    <header class="reading-identity">
      <span class="reading-mark" aria-hidden="true">PT</span>
      <div><h2>{{ name }}</h2><p class="reading-version">版本 {{ version }}</p></div>
    </header>
    <div class="reading-origin" aria-label="来源与查看方式">
      <span>{{ human(sourceBadge) }}</span><span>{{ human(deliveryBadge) }}</span>
    </div>
    <p class="reading-scope">{{ frontendCopy.reportScope }}</p>
    <p class="reading-boundary">{{ frontendCopy.facts.staticRuntime }}</p>
    <ul v-if="coverageLine || reviewCount" class="reading-status" aria-label="结果状态">
      <li v-if="coverageLine" :class="coverageStatus === 'PARTIAL' ? 'warn' : 'ok'">{{ coverageLine }}</li>
      <li v-if="reviewCount" class="warn">待复核条目 {{ reviewCount }} 条；复核状态未改变</li>
    </ul>
    <p v-for="state in policyStates" :key="state" class="reading-policy-state">{{ state }}</p>
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
.reading-status { display: grid; gap: 6px; margin: 0 0 12px; padding: 10px 12px; list-style: none; border-radius: 10px; background: var(--mt-warn-bg, #fbf3d9); }
.reading-status li { color: var(--mt-warn, #8a5a00); font-size: var(--m-caption); line-height: 1.5; }
.reading-status li.ok { color: var(--mt-success, #0f7a3c); }
.reading-status li.warn { color: var(--mt-warn, #8a5a00); }
.reading-policy-state { margin: 0 0 12px; color: var(--mt-muted); font-size: var(--mt-text-caption); line-height: 1.5; }
.reading-counts { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0; padding: 12px 0 0; border-top: 1px solid var(--pt-rule); }
.reading-counts > div { display: flex; align-items: baseline; gap: 6px; }
.reading-counts dt { font-size: var(--m-caption); color: var(--pt-muted); }
.reading-counts dd { margin: 0; color: var(--pt-ink); font-size: var(--pt-type-finding-mobile); font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
</style>
