<script setup lang="ts">
import { ref, watch } from 'vue'
import UiButton from './UiButton.vue'
import UiField from './UiField.vue'
import { collectionInstructions, confirmExternal, previewExternal } from '../policyAssist'
import type { ExternalInput, ImportPreview } from '../policyAssist'
import { sourceTypes } from '../workflow'
const props = defineProps<{ busy?: boolean; sourceCount: number; initialResult?: string }>()
const emit = defineEmits<{ import: [ExternalInput] }>()
const app = ref('')
const prompt = ref('')
const raw = ref('')
const preview = ref<ImportPreview | null>(null)
const error = ref('')
const message = ref('')
watch(() => props.initialResult, value => { if (value) raw.value = value })
watch(raw, () => { preview.value = null; error.value = ''; message.value = '' })
watch(app, () => { prompt.value = ''; message.value = '' })
async function copyInstructions() {
  error.value = ''; message.value = ''
  try {
    prompt.value = collectionInstructions(app.value)
    try { await navigator.clipboard.writeText(prompt.value); message.value = '收集指令已复制。请在你选择的网页聊天工具中使用。' }
    catch { message.value = '未能自动复制，请在下方选择并复制完整指令。' }
  } catch (cause) { error.value = (cause as Error).message }
}
function inspect() {
  error.value = ''; preview.value = null
  try { preview.value = previewExternal(raw.value) } catch (cause) { error.value = (cause as Error).message }
}
function submit() {
  error.value = ''
  try { if (preview.value) emit('import', confirmExternal(preview.value)) }
  catch (cause) { error.value = (cause as Error).message }
}
</script>
<template>
  <details class="policy-assist source-body">
    <summary>找不到政策？使用网页辅助收集</summary>
    <p class="field-help">复制指令到你选择的聊天工具，再回填结果。只提供当前应用的名称或包名；联网能力与来源是否取得，以实际收集结果为准。</p>
    <p class="field-help">当前有 {{ sourceCount }} 份政策来源，最多可再补入 {{ Math.max(0, 8 - sourceCount) }} 份；没有取得来源的失败记录不占来源数量。</p>
    <fieldset :disabled="busy" class="assist-fields">
      <UiField label="要查找政策的应用" id="collector-app"><input id="collector-app" v-model="app" maxlength="200" placeholder="应用名称或包名" /></UiField>
      <UiButton @click="copyInstructions">复制收集指令</UiButton>
      <UiField v-if="prompt" label="完整收集指令" id="collector-instructions"><textarea id="collector-instructions" :value="prompt" readonly rows="5" @focus="($event.target as HTMLTextAreaElement).select()" /></UiField>
      <UiField label="回填政策收集结果" id="collector-result" help="粘贴完整 JSON。也支持既有单来源导出；普通网址或正文可直接填入上方政策来源。"><textarea id="collector-result" v-model="raw" rows="6" maxlength="2000000" spellcheck="false" /></UiField>
      <UiButton :disabled="!raw.trim()" @click="inspect">检查回填内容</UiButton>
      <div v-if="preview" class="assist-preview">
        <p>确认来源类型后补入当前材料。完整度未知、未复核与附件未检查状态继续保留。</p>
        <p v-if="!preview.sources.length" class="field-help">本次没有取得政策来源，只记录收集失败或离线结果。</p>
        <UiField v-for="row in preview.sources" :key="row.index" :label="`${row.title}：来源类型`" :id="'collector-type-' + row.index"><select :id="'collector-type-' + row.index" v-model="row.type"><option value="" disabled>请选择已确认的来源类型</option><option v-for="(label, type) in sourceTypes" :key="type" :value="type">{{ label }}</option></select></UiField>
        <UiButton variant="primary" @click="submit">确认并补入材料</UiButton>
      </div>
    </fieldset>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="message" class="field-help" role="status">{{ message }}</p>
  </details>
</template>
<style scoped>
.assist-fields { border: 0; padding: 0; margin: 1rem 0 0; display: grid; gap: 1rem; min-width: 0; }
.assist-fields :deep(button) { justify-self: start; }
.assist-preview { display: grid; gap: 1rem; min-width: 0; }
.assist-preview p { margin: 0; overflow-wrap: anywhere; }
</style>
