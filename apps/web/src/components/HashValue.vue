<script setup lang="ts">
// 哈希/标识的移动阅读件：默认缩略，展开后可看完整值并复制。
// 用 <details> 承载展开，summary 本身就是 48px 触控目标，不额外塞一排小按钮。
import { computed, ref } from 'vue'

const props = defineProps<{ value: string; label?: string }>()
const expanded = ref(false)
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
const shortened = computed(() => props.value.length <= 18
  ? props.value
  : `${props.value.slice(0, 10)}…${props.value.slice(-6)}`)
function onToggle(event: Event) {
  expanded.value = (event.target as HTMLDetailsElement).open
}
async function copy() {
  try {
    await navigator.clipboard.writeText(props.value)
    copied.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { copied.value = false }, 1600)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <details class="m-hash" @toggle="onToggle">
    <summary>
      <span v-if="label" class="m-hash-label">{{ label }}</span>
      <span class="m-hash-text">{{ expanded ? '完整值' : shortened }}</span>
    </summary>
    <p class="m-hash-full">{{ value }}</p>
    <button type="button" class="m-hash-copy" @click="copy">{{ copied ? '已复制' : '复制完整值' }}</button>
  </details>
</template>

<style scoped>
.m-hash { margin: 4px 0; }
.m-hash > summary { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; min-height: 48px; cursor: pointer; list-style: none; }
.m-hash > summary::-webkit-details-marker { display: none; }
.m-hash-label { color: var(--mt-muted, #5e5d59); font-size: 0.875rem; }
.m-hash-text { font-family: var(--mt-font-mono, ui-monospace); font-size: 0.875rem; color: var(--mt-fg-2, #3d3d3a); overflow-wrap: anywhere; }
.m-hash-full { margin: 0 0 8px; font-family: var(--mt-font-mono, ui-monospace); font-size: 0.875rem; line-height: 1.5; color: var(--mt-fg, #141413); overflow-wrap: anywhere; }
.m-hash-copy { min-height: 48px; padding: 0 12px; border: 0; border-radius: 12px; background: transparent; color: var(--mt-accent-text, #a8431f); font-size: 1rem; font-weight: 500; }
</style>
