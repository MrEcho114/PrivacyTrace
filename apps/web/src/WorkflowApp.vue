<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ExistingReports from './App.vue'
import LiveWorkflow from './LiveWorkflow.vue'
import UiButton from './components/UiButton.vue'
import StatusTag from './components/StatusTag.vue'
import UiIcon from './components/UiIcon.vue'
import ImportPage from './pages/ImportPage.vue'
import CandidatePage from './pages/CandidatePage.vue'
import ProgressPage from './pages/ProgressPage.vue'
import ExampleReport from './pages/ExampleReport.vue'
import SettingsPanel from './pages/SettingsPanel.vue'
import { copy, frontendCopy } from './copy'
import { draftKey, freshWorkflow, restoreDraft, saveDraft, steps } from './workflow'
import type { Step } from './workflow'

const state = ref(freshWorkflow())
const view = ref<'workflow' | 'reports'>(location.hash === '#reports' ? 'reports' : 'workflow')
const settings = ref(false)
const message = ref('')
const storageError = ref(false)
let settingsTrigger: HTMLElement | null = null
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
// Real mode keeps the restored server/local draft; only the example owns a
// destructive reset, because its materials are synthetic.
function newComparison() { view.value = 'workflow'; go('import') }
function newMaterials() { try { localStorage.removeItem('privacytrace.live.draft.v1') } catch { storageError.value = true }; state.value = freshWorkflow(); go('import'); message.value = '' }
function persist() {
  const raw = saveDraft(state.value)
  try {
    if (raw) localStorage.setItem(draftKey, raw)
    else localStorage.removeItem(draftKey)
    storageError.value = false
  } catch { storageError.value = true }
}
function clearDraft() {
  try {
    localStorage.removeItem(draftKey)
    storageError.value = false
    if (state.value.example) {
      state.value = freshWorkflow()
      view.value = 'workflow'
      location.hash = 'import'
    }
    message.value = copy.draftCleared
  }
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
      <span class="workspace-purpose">{{ frontendCopy.brandSubtitle }}</span>
      <StatusTag class="shell-demo" :tone="state.example ? 'info' : 'neutral'">{{ state.example ? frontendCopy.demoBadge : '真实入口 · 本机材料' }}</StatusTag>
      <UiButton variant="quiet" @click="openSettings">项目设置</UiButton>
    </header>
    <div class="workspace-layout">
      <aside class="workspace-sidebar">
        <nav class="flow-nav" aria-label="四步流程">
          <ol>
            <li v-for="(step, index) in steps" :key="step">
              <button :disabled="index > state.maxStep" :aria-disabled="index > state.maxStep || undefined" :aria-current="view === 'workflow' && state.step === step ? 'step' : undefined" :aria-label="index > state.maxStep ? `${frontendCopy.steps[index]}，完成前一步后解锁` : frontendCopy.steps[index]" :title="index > state.maxStep ? '完成前一步后解锁' : undefined" @click="go(step)"><span class="flow-step-number" aria-hidden="true">{{ index < stepNumber ? '✓' : index + 1 }}</span><span class="flow-step-name">{{ frontendCopy.steps[index] }}</span></button>
            </li>
          </ol>
        </nav>
        <nav class="sidebar-actions" aria-label="工作台">
          <UiButton v-if="!state.example" variant="quiet" @click="newComparison"><UiIcon name="plus" />新建对照</UiButton>
          <UiButton v-else variant="quiet" @click="newMaterials">新材料</UiButton>
          <button class="nav-item" :class="{ active: view === 'reports' }" :aria-current="view === 'reports' ? 'page' : undefined" @click="openReports"><UiIcon name="report" />{{ copy.realReports }}</button>
        </nav>
        <div class="sidebar-foot"><span class="status-dot" aria-hidden="true"></span>本机工作台</div>
      </aside>
      <main id="workspace-content" class="workspace-content" tabindex="-1" :data-view="view" :data-step="view === 'workflow' ? state.step : 'reports'">
        <template v-if="view === 'workflow'">
          <p v-if="message" class="notice compact" role="status">{{ message }}</p>
          <p v-if="storageError" class="notice" role="status">浏览器暂存不可用，当前输入仍可继续使用。</p>
          <LiveWorkflow v-if="!state.example" :state="state" @example="startExample" />
          <ImportPage v-else-if="state.step === 'import'" :key="state.example ? 'example' : 'new'" :state="state" @example="startExample" @next="next('candidates')" />
          <CandidatePage v-else-if="state.step === 'candidates'" :state="state" @back="go('import')" @next="next('progress')" />
          <ProgressPage v-else-if="state.step === 'progress'" :state="state" @back="go('candidates')" @report="next('report')" />
          <ExampleReport v-else :state="state" @edit="go('candidates')" />
        </template>
        <template v-else><div class="page-heading"><h1 id="page-title" tabindex="-1">{{ frontendCopy.pageTitles.reports }}</h1><p>{{ frontendCopy.facts.archiveNoRescan }}</p></div><ExistingReports embedded /></template>
      </main>
    </div>
    <SettingsPanel v-if="settings" :storage-error="storageError" :example="state.example" @close="closeSettings" @clear="clearDraft" />
  </div>
</template>

<style src="./hierarchy.css"></style>
