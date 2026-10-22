<script setup lang="ts">
import UiIcon from './UiIcon.vue'
import UiButton from './UiButton.vue'

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
    <p class="reading-boundary">静态线索与政策声明对照，不证明实际采集。</p>
    <dl class="reading-counts">
      <div><dt>数据类型</dt><dd>{{ dataTypeCount }}</dd></div>
      <div><dt>政策来源</dt><dd>{{ policyCount }}</dd></div>
      <div><dt>可查看证据</dt><dd>{{ evidenceCount }}</dd></div>
    </dl>
    <details class="reading-details">
      <summary>报告来源与版本<UiIcon name="chevron-right" /></summary>
      <div class="reading-detail-body">
        <p>{{ sourceDescription }}</p>
        <p>{{ deliveryDescription }}</p>
        <p>六种状态只对照 DATA_TYPE_DISCLOSURE；“具体类型已声明”不代表目的、接收方、传输或时间范围全部一致，更不是合法性判断。</p>
        <dl>
          <div><dt>包名</dt><dd class="reading-code">{{ packageName }}</dd></div>
          <div v-if="generatedAt"><dt>原生成时间</dt><dd><time :datetime="generatedAt">{{ generatedAtLabel || generatedAt }}</time><span v-if="generatedAtLabel" class="reading-raw-time">{{ generatedAt }}</span></dd></div>
          <template v-if="material">
            <div><dt>分析服务</dt><dd>{{ material.origin }}</dd></div>
            <div><dt>材料标识</dt><dd class="reading-code">{{ material.draft }}</dd></div>
            <div v-if="material.revision != null"><dt>材料版本</dt><dd>{{ material.revision }}</dd></div>
          </template>
        </dl>
        <UiButton v-if="material" variant="quiet" class="reading-change" @click="$emit('changeMaterial')">更换材料</UiButton>
      </div>
    </details>
  </section>
</template>

<style scoped>
.mobile-report-summary { padding: 16px 16px 0; margin-bottom: 12px; border: 1px solid var(--border); border-radius: var(--m-card-radius); background: var(--surface); }
.reading-identity { display: flex; align-items: center; gap: 12px; }
.reading-mark { display: grid; place-items: center; width: 40px; height: 40px; flex: none; border-radius: 10px; background: var(--navy); color: var(--surface); font-size: 0.9375rem; font-weight: 600; }
.reading-identity > div { min-width: 0; }
.reading-identity h2 { margin: 0; font-family: var(--font-display); font-size: var(--m-font-title); font-weight: 500; line-height: 1.4; overflow-wrap: anywhere; }
.reading-version { margin: 2px 0 0; color: var(--muted); font-size: var(--m-caption); }
.reading-origin { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.reading-origin > span { padding: 3px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: var(--m-caption); line-height: 1.5; overflow-wrap: anywhere; }
.reading-boundary { margin: 8px 0 12px; font-size: var(--m-caption); line-height: 1.6; color: var(--muted); }
.reading-counts { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0; padding: 12px 0; border-top: 1px solid var(--border); }
.reading-counts > div { display: flex; align-items: baseline; gap: 6px; }
.reading-counts dt { font-size: var(--m-caption); color: var(--muted); }
.reading-counts dd { margin: 0; font-size: 1rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.reading-details { border-top: 1px solid var(--border); }
.reading-details > summary { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: var(--m-touch); cursor: pointer; list-style: none; font-size: var(--m-body); }
.reading-details > summary::-webkit-details-marker { display: none; }
.reading-details > summary .ui-icon { width: 16px; height: 16px; flex: none; }
.reading-details[open] > summary .ui-icon { transform: rotate(90deg); }
.reading-detail-body { padding-bottom: 16px; font-size: var(--m-body); line-height: 1.7; }
.reading-detail-body p { margin: 0 0 10px; }
.reading-detail-body dl { margin: 16px 0 0; }
.reading-detail-body dl > div + div { margin-top: 12px; }
.reading-detail-body dt { color: var(--muted); font-size: var(--m-caption); }
.reading-detail-body dd { margin: 2px 0 0; overflow-wrap: anywhere; }
.reading-code { font-family: var(--font-code); font-size: var(--m-caption); }
.reading-raw-time { display: block; color: var(--muted); font-size: var(--m-caption); }
.reading-change { margin-top: 12px; }
</style>
