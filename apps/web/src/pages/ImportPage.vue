<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiField from '../components/UiField.vue'
import StatusTag from '../components/StatusTag.vue'
import UiIcon from '../components/UiIcon.vue'
import { copy } from '../copy'
import { emptySource, sourceProvenanceLabel, sourceStatusLabel, sourceTypes } from '../workflow'
import type { Workflow } from '../workflow'
const props = defineProps<{ state: Workflow; busy?: boolean; uploadedName?: string }>()
const emit = defineEmits<{ example: []; next: []; file: [File]; dirty: [] }>()
const file = ref<File | null>(null)
const fileError = ref('')
const dropActive = ref(false)
const filePicker = ref<HTMLInputElement | null>(null)
const textErrors = ref<Record<string, string>>({})
const textReads = new Map<string, symbol>()
onBeforeUnmount(() => textReads.clear())
const canContinue = computed(() => props.state.example ? props.state.sources.some(source => source.text.trim() && source.status !== 'failed') : !!(file.value || props.uploadedName) && props.state.sources.some(source => source.text.trim() || source.url.trim()))
function acceptFile(selected?: File) {
  if (!selected) return
  fileError.value = ''
  if (!selected.name.toLowerCase().endsWith('.apk')) { fileError.value = copy.fileInvalid; return }
  if (selected.size === 0 || selected.size > (props.state.example ? 250 : 150) * 1024 * 1024) { fileError.value = copy.fileTooLarge + '（真实扫描上限 150 MiB，文件不能为空）'; return }
  file.value = selected; emit('file', selected)
}
function drop(event: DragEvent) { dropActive.value = false; acceptFile(event.dataTransfer?.files[0]) }
function addSource() {
  if (props.state.sources.length >= 8) return
  const id = 'source-' + crypto.randomUUID()
  props.state.sources.push(emptySource(id)); props.state.sourceId = id
  if (!props.state.example) emit('dirty')
}
function removeSource(id: string) {
  if (!props.state.example) emit('dirty')
  textReads.delete(id)
  delete textErrors.value[id]
  props.state.sources = props.state.sources.filter(item => item.id !== id)
  props.state.candidates = props.state.candidates.filter(item => item.sourceId !== id)
  if (props.state.sourceId === id) props.state.sourceId = props.state.sources[0]?.id ?? ''
}
async function readText(event: Event, id: string) {
  const input = event.target as HTMLInputElement; const selected = input.files?.[0]
  const source = props.state.sources.find(item => item.id === id)
  if (!selected || !source) return
  const request = Symbol(id)
  textReads.set(id, request)
  input.value = ''
  if (selected.size > 1024 * 1024 || !/\.(txt|md)$/i.test(selected.name)) { textErrors.value[id] = '请选择 1 MB 以内的 TXT 或 Markdown 文本。'; return }
  try {
    const text = await selected.text()
    if (textReads.get(id) !== request) return
    source.text = text
    source.status = text.trim() ? 'manual' : 'empty'
    delete textErrors.value[id]
  } catch { if (textReads.get(id) === request) textErrors.value[id] = '文本未能读取，请重新选择文件或粘贴正文。' }
  finally { if (textReads.get(id) === request) textReads.delete(id) }
}
function useText(id: string) {
  textReads.delete(id)
  const source = props.state.sources.find(item => item.id === id)
  if (!source) return
  if (!source.text.trim()) { textErrors.value[id] = copy.missingText; return }
  source.status = 'manual'; delete textErrors.value[id]
}
</script>
<template>
  <div>
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ copy.importTitle }}</h1><p>{{ copy.importDescription }}</p></div>
    <div class="import-grid" :inert="busy || undefined" @input="!state.example && emit('dirty')" @change="!state.example && emit('dirty')">
      <section class="material-panel apk-panel"><div class="panel-heading"><h2>APK 文件</h2><StatusTag>本机</StatusTag></div>
        <div class="file-drop" :class="{ 'drag-active': dropActive }" @dragover.prevent="dropActive = true" @dragleave="dropActive = false" @drop.prevent="drop">
          <span class="file-glyph" aria-hidden="true"><UiIcon name="file" /><span>APK</span></span>
          <strong>{{ file?.name || uploadedName || (state.example ? 'paperboat-example.apk' : copy.apkPlaceholder) }}</strong>
          <span v-if="file" class="field-help">{{ (file.size / 1024 / 1024).toFixed(2) }} MB · 尚未上传</span>
          <span v-else-if="state.example" class="field-help">固定示例名称 · 无 APK 文件</span>
          <span v-else class="field-help">拖放到这里，或选择文件</span>
          <input ref="filePicker" class="sr-only" type="file" accept=".apk" aria-label="选择 APK 文件" @change="acceptFile(($event.target as HTMLInputElement).files?.[0])" />
          <UiButton @click="filePicker?.click()">选择 APK</UiButton>
        </div>
        <p v-if="fileError" class="error-text" role="alert">{{ fileError }}</p><p class="field-help">{{ state.example ? copy.apkHelp : "继续后会上传到本机服务，仅在受限 Docker 中解析。上限 150 MiB。本机材料保留以便恢复和重试。" }}</p>
        <div class="example-entry"><h3>先看一次对照</h3><p class="field-help">{{ copy.demoHelp }}</p><UiButton @click="emit('example')">{{ copy.tryDemo }}<UiIcon name="arrow-right" /></UiButton></div>
      </section>
      <section class="material-panel policy-panel"><div class="panel-heading"><h2>政策来源</h2><span class="field-help">{{ state.sources.length }} 份来源</span></div>
        <article v-for="(source, index) in state.sources" :key="source.id" class="source-editor">
          <div class="source-heading"><h3>{{ source.title || `政策来源 ${index + 1}` }}</h3><StatusTag :tone="source.status === 'failed' ? 'error' : source.text ? 'info' : 'neutral'">{{ state.example ? (source.text ? '示例节选' : '待准备') : `${sourceStatusLabel(source.status)} · ${sourceProvenanceLabel(source.provenance)}` }}</StatusTag><UiButton v-if="state.sources.length > 1" variant="quiet" :aria-label="`移除来源 ${index + 1}`" @click="removeSource(source.id)">移除</UiButton></div>
          <div class="field-pair"><UiField label="来源名称" :id="'title-' + source.id"><input :id="'title-' + source.id" v-model="source.title" maxlength="100" placeholder="例如：应用官网政策" /></UiField><UiField label="来源类型" :id="'type-' + source.id"><select :id="'type-' + source.id" v-model="source.type"><option v-for="(text, value) in sourceTypes" :key="value" :value="value">{{ text }}</option></select></UiField></div>
          <UiField label="政策网址" :id="'url-' + source.id"><input :id="'url-' + source.id" v-model="source.url" type="url" maxlength="2000" placeholder="https://" /></UiField>
          <details class="source-body" :open="!state.example && index === 0"><summary>正文与适用范围<span class="source-summary-meta">{{ source.text ? `${source.text.length} 字` : copy.missingText }}</span></summary>
            <UiField label="政策正文" :id="'text-' + source.id" :help="state.example ? copy.policyHelp : '普通公开 HTML 网页可自动获取正文；抓取失败可粘贴或导入文本。正文完整度仍为未知。'" :error="textErrors[source.id]" v-slot="{ describedby }"><textarea :id="'text-' + source.id" v-model="source.text" rows="5" maxlength="200000" :aria-describedby="describedby" :aria-invalid="!!textErrors[source.id]" @input="textReads.delete(source.id)" /></UiField>
            <div class="source-actions"><label class="text-upload">导入文本<input type="file" accept=".txt,.md" :aria-label="`导入来源 ${index + 1} 文本`" @change="readText($event, source.id)" /></label><UiButton variant="quiet" @click="useText(source.id)">使用这份正文</UiButton><UiButton v-if="state.example" variant="quiet" @click="source.status = source.status === 'failed' ? 'ready' : 'failed'">{{ source.status === 'failed' ? '重试示例来源' : '体验来源失败' }}</UiButton></div>
            <details class="source-body"><summary>适用范围</summary><div class="field-pair"><UiField label="适用版本" :id="'version-' + source.id"><input :id="'version-' + source.id" v-model="source.version" maxlength="100" placeholder="未知" /></UiField><UiField label="适用地区" :id="'region-' + source.id"><input :id="'region-' + source.id" v-model="source.region" maxlength="100" placeholder="未知" /></UiField></div>
            <div v-if="!state.example" class="field-pair"><UiField label="适用包名" :id="'package-' + source.id"><input :id="'package-' + source.id" v-model="source.packageName" maxlength="200" placeholder="未知" /></UiField><UiField label="适用 versionCode" :id="'vcode-' + source.id"><input :id="'vcode-' + source.id" v-model.number="source.versionCode" type="number" min="0" placeholder="未知" /></UiField></div><UiField label="应用／产品范围" :id="'product-' + source.id"><input :id="'product-' + source.id" v-model="source.product" maxlength="100" placeholder="未知" /></UiField></details>
          </details>
          <p v-if="source.status === 'failed'" class="error-text" role="alert">{{ copy.sourceFailed }} · {{ copy.retry }}</p>
          <div class="source-notes"><span>{{ copy.sourceScopeUnknown }}</span><span>{{ copy.attachmentsUnknown }}</span></div>
        </article>
        <UiButton :disabled="state.sources.length >= 8" @click="addSource">添加政策来源</UiButton>
      </section>
    </div>
    <div class="flow-footer"><p>{{ state.example ? copy.storageHelp : "继续后会在本机保存输入快照，获取缺少正文的网页，并请求已配置模型提供候选。失败来源会保留。" }}</p><UiButton variant="primary" :disabled="!canContinue || busy" :busy="busy" @click="emit('next')">{{ state.example ? copy.nextCandidates : "获取政策并检查候选" }}<UiIcon name="arrow-right" /></UiButton></div>
  </div>
</template>
