<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy } from '../copy'
defineProps<{ storageError: boolean }>()
const emit = defineEmits<{ close: []; clear: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const connection = ref<'unknown' | 'checking' | 'connected' | 'failed'>('unknown')
let controller: AbortController | null = null
function keepFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialog.value) return
  const controls = Array.from(dialog.value.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
  const first = controls[0]; const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
async function check() {
  controller?.abort(); const current = new AbortController(); controller = current; connection.value = 'checking'
  const timeout = setTimeout(() => current.abort(), 5000)
  try { const response = await fetch('/api/v1/health', { signal: current.signal }); const body = response.ok ? await response.json() : null
    if (controller === current) connection.value = body?.status === 'ok' ? 'connected' : 'failed'
  } catch { if (controller === current) connection.value = 'failed' }
  finally { clearTimeout(timeout) }
}
onMounted(() => { dialog.value?.showModal(); void nextTick(() => document.getElementById('settings-close')?.focus()) })
onBeforeUnmount(() => { controller?.abort(); dialog.value?.close() })
</script>
<template>
  <dialog ref="dialog" class="settings-dialog" aria-labelledby="settings-title" @keydown="keepFocus" @cancel.prevent="emit('close')"><div class="panel-heading"><h2 id="settings-title">{{ copy.settingsTitle }}</h2><UiButton id="settings-close" variant="quiet" @click="emit('close')">{{ copy.close }}</UiButton></div><p class="field-help">{{ copy.settingsDescription }}</p>
    <section class="settings-section"><h3>分析服务</h3><StatusTag :tone="connection === 'connected' ? 'success' : connection === 'failed' ? 'error' : 'neutral'">{{ connection === 'connected' ? '报告接口已连接' : connection === 'failed' ? copy.notConnected : connection === 'checking' ? '正在检查' : '尚未测试' }}</StatusTag><p>{{ copy.connectionHelp }}</p><UiButton :busy="connection === 'checking'" @click="check">{{ copy.refreshConnection }}</UiButton></section>
    <section class="settings-section"><h3>模型连接</h3><StatusTag tone="wait">待接入</StatusTag><p>{{ copy.modelHelp }}</p><p class="field-help">此页面不接收密钥。</p></section>
    <section class="settings-section"><h3>浏览器草稿</h3><p>{{ copy.storageHelp }}</p><p v-if="storageError" class="error-text">暂存不可用</p><UiButton @click="emit('clear')">{{ copy.clearDraft }}</UiButton></section>
  </dialog>
</template>
