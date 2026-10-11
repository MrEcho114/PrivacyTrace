<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ExistingReports from './App.vue'
import UiButton from './components/UiButton.vue'
import StatusTag from './components/StatusTag.vue'
import UiIcon from './components/UiIcon.vue'
import ImportPage from './pages/ImportPage.vue'
import CandidatePage from './pages/CandidatePage.vue'
import ProgressPage from './pages/ProgressPage.vue'
import ExampleReport from './pages/ExampleReport.vue'
import SettingsPanel from './pages/SettingsPanel.vue'
import { copy } from './copy'
import { draftKey, freshWorkflow, restoreDraft, saveDraft, steps } from './workflow'
import type { Step } from './workflow'

const state = ref(freshWorkflow())
const view = ref<'workflow' | 'reports'>(location.hash === '#reports' ? 'reports' : 'workflow')
const settings = ref(false)
const message = ref('')
const storageError = ref(false)
let settingsTrigger: HTMLElement | null = null
const stepLabels = ['导入材料', '检查候选', '分析进度', '对照报告']
const stepNumber = computed(() => steps.indexOf(state.value.step))
function focusPage() { void nextTick(() => document.getElementById('page-title')?.focus()) }
function go(step: Step) {
  const index = steps.indexOf(step)
  if (index > state.value.maxStep) return
  view.value = 'workflow'; state.value.step = step; location.hash = step; focusPage()
}
function next(step: Step) {
  state.value.maxStep = Math.max(state.value.maxStep, steps.indexOf(step)); go(step)
}
function startExample() {
  state.value = freshWorkflow(true); message.value = ''; view.value = 'workflow'; location.hash = 'import'; focusPage()
}
function openReports() { view.value = 'reports'; location.hash = 'reports'; focusPage() }
function newMaterials() { state.value = freshWorkflow(); go('import'); message.value = '' }
function persist() {
  const raw = saveDraft(state.value)
  if (!raw) return
  try { localStorage.setItem(draftKey, raw); storageError.value = false } catch { storageError.value = true }
}
function clearDraft() {
  try { localStorage.removeItem(draftKey); storageError.value = false; state.value = freshWorkflow(); message.value = copy.clearDraft; view.value = 'workflow'; location.hash = 'import' }
  catch { storageError.value = true }
}
function openSettings(event: Event) { settingsTrigger = event.currentTarget as HTMLElement; settings.value = true }
function closeSettings() { settings.value = false; void nextTick(() => settingsTrigger?.focus()) }
function hashChanged() {
  if (location.hash === '#reports') { view.value = 'reports'; return }
  const step = location.hash.slice(1) as Step
  if (steps.includes(step) && steps.indexOf(step) <= state.value.maxStep) { view.value = 'workflow'; state.value.step = step }
}
onMounted(() => {
  try {
    const draft = restoreDraft(localStorage.getItem(draftKey))
    if (draft) { state.value = draft; message.value = copy.draftRestored }
  } catch { storageError.value = true }
  hashChanged()
  window.addEventListener('hashchange', hashChanged)
})
onBeforeUnmount(() => window.removeEventListener('hashchange', hashChanged))
watch(state, persist, { deep: true })
</script>

<template>
  <div class="workbench">
    <a class="skip-link" href="#workspace-content">跳到内容</a>
    <header class="workspace-bar">
      <a href="#import" class="workspace-brand" @click.prevent="go('import')"><span aria-hidden="true" class="brand-mark">P</span>PrivacyTrace</a>
      <span class="workspace-purpose">静态证据与政策对照</span>
      <UiButton variant="quiet" @click="openSettings">项目设置</UiButton>
    </header>
    <div class="workspace-layout">
      <aside class="workspace-sidebar">
        <nav aria-label="工作台">
          <button class="nav-item" :class="{ active: view === 'workflow' }" @click="view = 'workflow'; go(state.step)"><UiIcon name="plus" />新建对照</button>
          <button class="nav-item" :class="{ active: view === 'reports' }" @click="openReports"><UiIcon name="report" />{{ copy.realReports }}</button>
        </nav>
        <div class="sidebar-foot"><span class="status-dot" aria-hidden="true"></span>本机工作台</div>
      </aside>
      <main id="workspace-content" class="workspace-content" tabindex="-1">
        <template v-if="view === 'workflow'">
          <div class="workflow-toolbar"><nav class="step-nav" aria-label="创建流程"><button v-for="(step, index) in steps" :key="step" :disabled="index > state.maxStep" :aria-current="state.step === step ? 'step' : undefined" @click="go(step)"><span :class="{ complete: index < stepNumber }">{{ index < stepNumber ? '✓' : index + 1 }}</span>{{ stepLabels[index] }}</button></nav>
          <div class="flow-context"><StatusTag :tone="state.example ? 'info' : 'neutral'">{{ state.example ? '示例体验 · 固定材料' : '新建对照' }}</StatusTag><UiButton v-if="state.example" variant="quiet" @click="newMaterials">新材料</UiButton></div></div>
          <p v-if="message" class="notice compact" role="status">{{ message }}</p>
          <p v-if="storageError" class="notice" role="status">浏览器暂存不可用，当前输入仍可继续使用。</p>
          <ImportPage v-if="state.step === 'import'" :key="state.example ? 'example' : 'new'" :state="state" @example="startExample" @next="next('candidates')" />
          <CandidatePage v-else-if="state.step === 'candidates'" :state="state" @back="go('import')" @next="next('progress')" />
          <ProgressPage v-else-if="state.step === 'progress'" :state="state" @back="go('candidates')" @report="next('report')" />
          <ExampleReport v-else :state="state" @edit="go('candidates')" />
        </template>
        <template v-else><div class="report-page-title"><h1 id="page-title" tabindex="-1">{{ copy.realReports }}</h1><p>{{ copy.reportDescription }}</p></div><ExistingReports /></template>
      </main>
    </div>
    <SettingsPanel v-if="settings" :storage-error="storageError" @close="closeSettings" @clear="clearDraft" />
  </div>
</template>
