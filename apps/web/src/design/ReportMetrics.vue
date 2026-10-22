<script setup lang="ts">
defineProps<{ types: number; sources: number; evidence: number }>()
const format = (count: number) => String(count).padStart(2, '0')
</script>
<template>
  <dl class="pt-metrics">
    <div><dt class="pt-code">DATA TYPES</dt><dd class="pt-metric-value">{{ format(types) }}</dd><dd class="pt-metric-label">已识别数据类型</dd></div>
    <div><dt class="pt-code">POLICY SOURCES</dt><dd class="pt-metric-value">{{ format(sources) }}</dd><dd class="pt-metric-label">已定位政策来源</dd></div>
    <div><dt class="pt-code">EVIDENCE</dt><dd class="pt-metric-value">{{ format(evidence) }}</dd><dd class="pt-metric-label">可阅读静态证据</dd></div>
  </dl>
</template>
