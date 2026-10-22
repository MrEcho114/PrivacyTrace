<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import UiDialog from '../components/UiDialog.vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import UiField from '../components/UiField.vue'
import { liveRequest } from '../liveApi'
import type { ModelStatus } from '../liveApi'
import { copy } from '../copy'
defineProps<{ storageError: boolean; example: boolean }>()
const emit = defineEmits<{ close: []; clear: [] }>()
const connection = ref<'unknown' | 'checking' | 'connected' | 'failed'>('unknown')
let controller: AbortController | null = null
const model = ref({ enabled: false, api_base: '', model: '', api_key: '' })
const keyConfigured = ref(false)
const clearKey = ref(false)
const saving = ref(false)
const modelMessage = ref('')
const modelError = ref('')
const modelController = new AbortController()
async function loadModel() {
  try { const status = await liveRequest<ModelStatus>('settings', modelController.signal); Object.assign(model.value, { enabled: status.enabled, api_base: status.api_base, model: status.model }); keyConfigured.value = status.key_configured }
  catch { modelError.value = '无法读取模型设置，请启动本机分析服务。' }
}
async function saveModel() {
  if (saving.value) return
  saving.value = true; modelMessage.value = ''; modelError.value = ''
  try { const value = await liveRequest<ModelStatus>('settings', modelController.signal, { ...model.value, api_key: clearKey.value ? '' : model.value.api_key || undefined }); keyConfigured.value = value.key_configured; modelMessage.value = '已保存本项目设置。候选提取时才会请求模型。' }
  catch (cause) { modelError.value = cause instanceof Error ? cause.message : '设置未保存。' }
  finally { model.value.api_key = ''; clearKey.value = false; saving.value = false }
}
async function check() {
  controller?.abort(); const current = new AbortController(); controller = current; connection.value = 'checking'
  const timeout = setTimeout(() => current.abort(), 5000)
  try { const response = await fetch('/api/v1/health', { signal: current.signal }); const body = response.ok ? await response.json() : null
    if (controller === current) connection.value = body?.status === 'ok' ? 'connected' : 'failed'
  } catch { if (controller === current) connection.value = 'failed' }
  finally { clearTimeout(timeout) }
}
onMounted(() => { void loadModel() })
onBeforeUnmount(() => { controller?.abort(); modelController.abort(); model.value.api_key = '' })
</script>
<template>
  <UiDialog class="settings-dialog" :title="copy.settingsTitle" :description="copy.settingsDescription" initial-focus="settings-close" @close="emit('close')">
    <template #close><UiButton id="settings-close" variant="quiet" @click="emit('close')">{{ copy.close }}</UiButton></template>
    <section class="settings-section"><h3>分析服务</h3><div role="status" aria-live="polite"><StatusTag :tone="connection === 'connected' ? 'success' : connection === 'failed' ? 'error' : 'neutral'">{{ connection === 'connected' ? '分析服务有响应' : connection === 'failed' ? copy.notConnected : connection === 'checking' ? '正在检查…' : '尚未测试' }}</StatusTag></div><p>{{ copy.connectionHelp }}</p><UiButton :busy="connection === 'checking'" @click="check">{{ copy.refreshConnection }}</UiButton></section>
    <section class="settings-section"><h3>模型连接</h3><StatusTag :tone="model.enabled ? 'info' : 'neutral'">{{ model.enabled ? keyConfigured ? '已配置凭证' : '未配置凭证' : '未启用' }}</StatusTag><p>模型只接收政策文本，提供需检查的候选。APK 不会发送给模型。</p><form :aria-busy="saving || undefined" @submit.prevent="saveModel"><label><input v-model="model.enabled" type="checkbox" /> 启用政策模型</label><UiField label="模型服务地址" id="model-base"><input id="model-base" v-model="model.api_base" type="url" maxlength="2000" placeholder="https://" /></UiField><UiField label="模型名" id="model-name"><input id="model-name" v-model="model.model" maxlength="100" /></UiField><UiField label="替换模型凭证" id="model-key" help="地址不变时留空保留原凭证；更换地址需重新填写。保存后清空输入，服务不回显原密钥。"><input id="model-key" v-model="model.api_key" type="password" autocomplete="new-password" maxlength="4096" /></UiField><label><input v-model="clearKey" type="checkbox" /> 清除已保存凭证</label><div class="source-actions"><UiButton type="submit" :busy="saving">保存模型设置</UiButton></div><p v-if="modelError" class="error-text" role="alert">{{ modelError }}</p><p v-if="modelMessage" role="status">{{ modelMessage }}</p></form></section>
    <section class="settings-section"><h3>浏览器草稿</h3><p>{{ copy.storageHelp }}</p><p v-if="example" class="field-help">清除后会重置当前示例，自填文本也会丢失。</p><p v-if="storageError" class="error-text">暂存不可用</p><UiButton @click="emit('clear')">{{ copy.clearDraft }}</UiButton></section>
  </UiDialog>
</template>
