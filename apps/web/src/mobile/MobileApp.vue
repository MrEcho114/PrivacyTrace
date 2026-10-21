<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiIcon from '../components/UiIcon.vue'
import UiSheet from '../components/UiSheet.vue'
import PolicyAssist from '../components/PolicyAssist.vue'
import CandidatePage from '../pages/CandidatePage.vue'
import ExistingReports from '../App.vue'
import { collectionInstructions } from '../policyAssist'
import { sourceStatusLabel, steps } from '../workflow'
import type { Step } from '../workflow'
import { mobileBridge } from './bridge'
import { createMobileFlow } from './flow'
import './mobile.css'

const flow = createMobileFlow(mobileBridge)
const { state, context, draft, job, report, taxonomy, busy, error, notice, model, modelResult } = flow
const modelName = ref(''), appHint = ref('')
const modelPrompt = computed(() => appHint.value.trim() ? collectionInstructions(appHint.value) : '')
const labels = computed(() => Object.fromEntries(taxonomy.value?.data_types.map(t => [t.id, t.label]) ?? []))
const terminal = computed(() => !!job.value && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.value.state))
const stages: Record<string, string> = { QUEUED: '等待处理', INTAKE: '核对材料', STATIC_ANALYSIS: '静态扫描', POLICY_PARSING: '装载政策', EVALUATING: '规则对照', REPORTING: '生成报告', SUCCEEDED: '报告已生成', FAILED: '分析未完成', CANCELLED: '分析已取消' }

const stepMeta = [
  { id: 'import', label: '导入', title: '应用与政策' },
  { id: 'candidates', label: '候选', title: '检查政策候选' },
  { id: 'progress', label: '进度', title: '分析进度' },
  { id: 'report', label: '报告', title: '对照报告' },
] as const
const currentIndex = computed(() => steps.indexOf(state.step))
const title = computed(() => stepMeta[currentIndex.value]?.title ?? 'PrivacyTrace')
const hasContext = computed(() => !!context.value)
const hasJob = computed(() => !!job.value || !!draft.value?.jobs.length)
const hasReport = computed(() => !!report.value)
// The rail is a view of real reachable state, not a second copy of the flow:
// candidates need an uploaded material, progress a job, the report a loaded one.
function stepAvailable(index: number) {
  if (index === 0) return true
  if (index === 1) return hasContext.value
  if (index === 2) return hasContext.value && (hasJob.value || hasReport.value)
  return hasReport.value
}
function stepDisabled(index: number) { return index !== currentIndex.value && !stepAvailable(index) }

const contextName = computed(() => {
  if (state.step === 'report' && report.value) return report.value.sample.name
  return draft.value?.name || '当前分析材料'
})
const contextVersion = computed(() => {
  if (state.step === 'report' && report.value) {
    const sample = report.value.sample
    return sample.version_name ?? ('v' + sample.version_code)
  }
  return draft.value ? `材料版本 ${draft.value.revision}` : ''
})

const visibleSources = computed(() => draft.value?.sources.filter(source => source.text || source.url) ?? [])
const hasSources = computed(() => !!draft.value?.sources.some(source => source.text || source.url))
const jobEvents = computed(() => draft.value?.jobs.find(record => record.job_id === job.value?.id)?.events ?? [])
const stageLabel = computed(() => job.value ? stages[job.value.state] ?? job.value.state : '等待开始分析')
const failed = computed(() => !!job.value && (job.value.state === 'FAILED' || job.value.state === 'CANCELLED'))

// --- Android back + per-step scroll restoration -----------------------------
// Body scroll is intentional: the Tauri WebView keeps native scroll restoration
// and the report's evidence focus behaviour, while the app bar sticks and the
// action bar is fixed. One history entry tracks every reachable step, so the
// hardware back button and the in-app back arrow follow the same chain:
// import <-> candidates <-> progress <-> report. A flow transition that skips
// steps (a restored job opens progress directly) fills the intermediate entries
// so back cannot strand the user on an unreachable page.
const scrollByStep: Partial<Record<Step, number>> = {}
let suppressPush = false
let ignoreNextPop = false
let overlayEntries = 0
let closingOverlayByBack = false
const settingsOpen = ref(false)
const settingsTrigger = ref<HTMLElement | null>(null)
const stepEntering = ref(false)
type ReportViewApi = { evidenceOpen: boolean; closeEvidence: () => void }
const reportView = useTemplateRef<ReportViewApi>('reportView')
// The fixed action bar grows with 200% text; publish its measured height so the
// last content is never trapped behind it. Not a layout listener on the page.
const actionbar = useTemplateRef<HTMLElement>('actionbar')
let actionbarObserver: ResizeObserver | undefined
watch(actionbar, element => {
  actionbarObserver?.disconnect()
  if (!element) { document.documentElement.style.removeProperty('--m-actionbar-actual'); return }
  actionbarObserver = new ResizeObserver(() => {
    document.documentElement.style.setProperty('--m-actionbar-actual', Math.round(element.getBoundingClientRect().height) + 'px')
  })
  actionbarObserver.observe(element)
  document.documentElement.style.setProperty('--m-actionbar-actual', Math.round(element.getBoundingClientRect().height) + 'px')
}, { flush: 'post' })

function backTarget(): Step | null {
  if (state.step === 'candidates') return 'import'
  if (state.step === 'progress') return 'candidates'
  if (state.step === 'report') return 'progress'
  return null
}
function navigate(target: Step) {
  if (target === state.step || !stepAvailable(steps.indexOf(target))) return
  const targetIndex = steps.indexOf(target)
  if (targetIndex < currentIndex.value) {
    // Earlier steps reuse the entries already in history; going back keeps the
    // forward direction working instead of stacking duplicate entries.
    history.go(targetIndex - currentIndex.value)
    return
  }
  state.step = target
}
function goBack() {
  if (settingsOpen.value) { closeSettings(); return }
  if (reportView.value?.evidenceOpen) { reportView.value.closeEvidence(); return }
  const target = backTarget()
  if (target) navigate(target)
}
watch(() => state.step, (next, previous) => {
  scrollByStep[previous] = Math.round(window.scrollY)
  const nextIndex = steps.indexOf(next), previousIndex = steps.indexOf(previous)
  if (suppressPush) suppressPush = false
  else if (nextIndex > previousIndex) {
    // Fill skipped steps so every reachable entry has the same chain the back
    // button walks. Entries for unreachable steps are not invented.
    for (let index = previousIndex + 1; index < nextIndex; index += 1) {
      if (stepAvailable(index)) history.pushState({ pt: steps[index] }, '')
    }
    history.pushState({ pt: next }, '')
  } else {
    // A flow reset moved backwards (for example deleting the material); collapse
    // the current entry instead of growing the stack.
    history.replaceState({ pt: next }, '')
  }
  void nextTick(() => {
    // Focus lands on the app-bar title, then the saved position is restored with
    // focus itself not scrolling the page.
    document.getElementById('page-title')?.focus({ preventScroll: true })
    window.scrollTo({ top: scrollByStep[next] ?? 0, behavior: 'auto' })
    // One short opacity/offset entrance per step. Reduced motion disables it in CSS.
    stepEntering.value = false
    void nextTick(() => { stepEntering.value = true })
  })
})
function pushOverlay() {
  overlayEntries += 1
  history.pushState({ pt: state.step, overlay: true }, '')
}
function popOverlay() {
  if (overlayEntries <= 0) return
  overlayEntries -= 1
  ignoreNextPop = true
  history.back()
}
function onPopState(event: PopStateEvent) {
  if (ignoreNextPop) { ignoreNextPop = false; return }
  if (settingsOpen.value) { closeSettings(true); return }
  if (reportView.value?.evidenceOpen) {
    closingOverlayByBack = true
    reportView.value.closeEvidence()
    closingOverlayByBack = false
    return
  }
  const target = (event.state as { pt?: string } | null)?.pt
  if (target && (steps as readonly string[]).includes(target) && target !== state.step && stepAvailable(steps.indexOf(target as Step))) {
    suppressPush = true
    state.step = target as Step
    return
  }
  // A history entry outside the app chain (older page or unreachable step):
  // resolve to the semantic previous step instead of leaving the shell stuck.
  const fallback = backTarget()
  if (fallback && stepAvailable(steps.indexOf(fallback))) {
    suppressPush = true
    state.step = fallback
  }
}
function openSettings(event?: Event) {
  settingsTrigger.value = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null
  settingsOpen.value = true
  pushOverlay()
}
function closeSettings(byBack = false) {
  if (!settingsOpen.value) return
  settingsOpen.value = false
  if (!byBack) popOverlay()
  void nextTick(() => settingsTrigger.value?.focus({ preventScroll: true }))
}
function onEvidenceOpen() { pushOverlay() }
function onEvidenceClose() {
  if (closingOverlayByBack) return
  popOverlay()
}

const progressPrimary = () => { if (job.value?.state === 'SUCCEEDED') void flow.openReport(); else void flow.poll() }
const progressSecondary = () => {
  if (!job.value) return
  if (!terminal.value) void flow.control('cancel-job')
  else if (job.value.state !== 'SUCCEEDED') void flow.control('retry-job')
}

onMounted(() => {
  document.documentElement.classList.add('mobile-shell')
  history.replaceState({ ...(typeof history.state === 'object' && history.state ? history.state : {}), pt: state.step }, '')
  window.addEventListener('popstate', onPopState)
  void flow.settings()
})
onBeforeUnmount(() => {
  window.removeEventListener('popstate', onPopState)
  actionbarObserver?.disconnect()
  document.documentElement.style.removeProperty('--m-actionbar-actual')
  document.documentElement.classList.remove('mobile-shell')
  void flow.stop()
})
</script>

<template>
  <div class="mobile-workspace" :class="{ 'm-report-step': state.step === 'report' }">
    <a class="skip-link" href="#workspace-content">跳到内容</a>
    <header class="m-appbar">
      <button v-if="state.step !== 'import'" type="button" class="m-icon-button" aria-label="返回上一步" @click="goBack">
        <UiIcon name="back" />
      </button>
      <span v-else class="m-appbar-spacer" aria-hidden="true"></span>
      <h1 id="page-title" tabindex="-1">{{ title }}</h1>
      <button type="button" class="m-icon-button" aria-label="服务与存储设置" aria-haspopup="dialog" @click="openSettings">
        <UiIcon name="settings" />
      </button>
    </header>

    <nav class="m-steps" aria-label="创建流程">
      <ol>
        <li v-for="(step, index) in stepMeta" :key="step.id">
          <button type="button" class="m-step" :class="{ current: index === currentIndex, complete: index < currentIndex }" :aria-current="index === currentIndex ? 'step' : undefined" :disabled="stepDisabled(index)" @click="navigate(step.id)">
            <span class="m-step-number" aria-hidden="true">{{ index < currentIndex ? '✓' : index + 1 }}</span>
            <span class="m-step-label">{{ step.label }}</span>
          </button>
        </li>
      </ol>
    </nav>

    <main id="workspace-content" class="m-main" :class="{ 'm-step-enter': stepEntering }" tabindex="-1" @animationend="stepEntering = false">
      <section v-if="context && state.step !== 'import'" class="m-context" aria-label="当前分析材料">
        <div class="m-context-text">
          <strong class="m-context-name">{{ contextName }}</strong>
          <span class="m-context-meta">{{ contextVersion }}</span>
        </div>
        <button type="button" class="m-text-button" @click="navigate('import')">更换</button>
        <details class="m-context-details">
          <summary>材料标识与来源</summary>
          <p class="hash">{{ context.origin }}</p>
          <p class="hash">材料 {{ context.draft }}<template v-if="draft"> · 版本 {{ draft.revision }}</template></p>
        </details>
      </section>

      <template v-if="state.step === 'import'">
        <section v-if="!context" class="m-card m-empty-card">
          <h2>选择要对照的应用</h2>
          <p>仅上传主动选择的应用及其完整安装包集合。服务端长期保留至主动删除。</p>
          <div class="m-button-row">
            <UiButton variant="primary" :disabled="busy" @click="flow.select()">选择应用并上传</UiButton>
            <UiButton :disabled="busy" @click="flow.select(true)">恢复当前实例材料</UiButton>
          </div>
        </section>
        <section v-else class="m-card">
          <div class="m-card-head"><h2>当前分析材料</h2><UiButton variant="quiet" :disabled="busy" @click="flow.remove">删除远端材料</UiButton></div>
          <p class="m-material-name">{{ draft?.name || '正在读取材料…' }}</p>
          <p v-if="draft?.apk_sha256" class="hash">APK SHA-256 {{ draft.apk_sha256 }}</p>
          <p class="m-help">材料保存在本机服务，服务端长期保留至主动删除。更换文件请重新选择应用。</p>
        </section>
        <div v-if="busy" class="m-notice m-busy-notice"><span role="status">正在处理当前请求。</span><UiButton variant="quiet" @click="flow.stop">停止本次请求</UiButton></div>
        <section v-if="context" class="m-section" aria-labelledby="m-sources-title">
          <div class="m-section-head"><h2 id="m-sources-title">政策来源</h2><span class="m-help">{{ draft?.sources.length ?? 0 }} 份来源</span></div>
          <article v-for="source in visibleSources" :key="source.id" class="m-source-row">
            <details>
              <summary class="m-row">
                <span class="m-row-main">
                  <strong>{{ source.title || '未命名来源' }}</strong>
                  <span class="m-row-sub">{{ sourceStatusLabel(source.status) }} · 完整度未知 · 未复核 · 附件未检查</span>
                </span>
                <UiIcon name="chevron-right" class="m-chevron" />
              </summary>
              <div class="m-row-body">
                <p v-if="source.url" class="hash">{{ source.url }}</p>
                <div v-if="source.text" class="policy-reading">{{ source.text }}</div>
                <p v-else class="m-help">尚未取得正文；下一步会尝试自动查找，也可以使用下方辅助入口。</p>
              </div>
            </details>
          </article>
          <p v-if="!hasSources" class="m-help">尚未补入政策。下一步会尝试自动查找；也可以使用下方辅助入口。</p>
        </section>
        <PolicyAssist v-if="context" :busy="busy" :source-count="draft?.sources.length ?? 0" :initial-result="modelResult" @import="flow.importCollected" />
        <details v-if="context" class="m-details m-model">
          <summary>使用手机上的个人模型</summary>
          <p class="m-help">Key 在系统窗口输入并保存在本机。仅把完整收集指令和应用线索发送给所选模型；服务是否具备联网能力，以实际结果为准。</p>
          <div class="m-button-row"><UiButton :disabled="busy" @click="flow.settings(true)">{{ model.configured ? '修改模型配置' : '设置模型配置' }}</UiButton><span class="m-help">{{ model.configured ? '本机已配置' : '尚未配置，可继续自动流程' }}</span></div>
          <p v-if="model.endpoint" class="hash">{{ model.endpoint }}</p>
          <label class="mobile-field" for="mobile-model-name">模型名称<input id="mobile-model-name" v-model="modelName" :disabled="busy" maxlength="200" /></label>
          <label class="mobile-field" for="mobile-app-hint">应用名称或包名<input id="mobile-app-hint" v-model="appHint" :disabled="busy" maxlength="200" :placeholder="draft?.name" /></label>
          <details v-if="modelPrompt" class="m-details"><summary>查看将发送的完整指令</summary><pre class="policy-reading">{{ modelPrompt }}</pre></details>
          <UiButton :disabled="busy || !model.configured || !modelName.trim() || !appHint.trim()" @click="flow.collect(modelName, appHint)">使用个人模型收集一次</UiButton>
        </details>
      </template>

      <CandidatePage v-else-if="state.step === 'candidates' && context" mobile :state="state" :busy="busy" :type-labels="labels" @back="navigate('import')" @next="flow.begin" @persist-candidates="flow.save" />

      <template v-else-if="state.step === 'progress'">
        <section class="m-card m-status-card" :class="{ failed }">
          <p class="m-eyebrow" role="status">{{ stageLabel }}</p>
          <h2>{{ job?.state === 'SUCCEEDED' ? '报告已生成' : failed ? '本次分析未完成' : '正在分析当前材料' }}</h2>
          <p v-if="job?.id" class="hash">{{ job.id }}</p>
          <p v-if="failed" class="m-error" role="alert">本次分析未完成，可刷新状态或重试为新的分析。静态线索不证明实际采集。</p>
          <p v-if="job?.state === 'SUCCEEDED'" class="m-help">阶段已完成。查看报告中的证据依据与政策原句。</p>
        </section>
        <section class="m-section" aria-labelledby="m-timeline-title">
          <div class="m-section-head"><h2 id="m-timeline-title">分析阶段</h2><span class="m-help">{{ job ? stages[job.state] ?? job.state : '未开始' }}</span></div>
          <ol v-if="jobEvents.length" class="m-timeline">
            <li v-for="(event, index) in jobEvents" :key="event.at + event.state" :class="{ current: index === jobEvents.length - 1 }">
              <span class="m-timeline-dot" aria-hidden="true"></span>
              <span class="m-timeline-body"><strong>{{ stages[event.state] ?? event.state }}</strong><span>{{ event.at }}</span></span>
            </li>
          </ol>
          <p v-else class="m-help">任务创建后会在这里按时间顺序显示阶段记录。</p>
        </section>
      </template>

      <div v-else-if="state.step === 'report' && report && taxonomy" class="m-report">
        <ExistingReports ref="reportView" :key="report.job.id" :snapshot="{ report, taxonomy }" mobile @evidence-open="onEvidenceOpen" @evidence-close="onEvidenceClose" />
      </div>
      <p v-else-if="state.step === 'report'" class="m-notice" role="status">报告尚未载入，请返回进度刷新状态。</p>

      <template v-if="error || notice">
        <p v-if="error" class="m-error m-message" role="alert">{{ error }}</p>
        <p v-if="notice && state.step !== 'progress'" class="m-notice m-message" role="status">{{ notice }}</p>
      </template>
    </main>

    <footer v-if="state.step !== 'report'" ref="actionbar" class="m-actionbar" role="group" aria-label="当前步骤操作">
      <template v-if="state.step === 'import'">
        <UiButton :disabled="busy || !context" @click="flow.refresh">重新读取材料</UiButton>
        <UiButton variant="primary" :disabled="busy || !context" @click="flow.prepare">自动准备政策并继续</UiButton>
      </template>
      <template v-else-if="state.step === 'candidates'">
        <UiButton :disabled="busy" @click="navigate('import')">修改材料</UiButton>
        <UiButton variant="primary" :disabled="busy" :busy="busy" @click="flow.begin">保存候选并开始分析</UiButton>
      </template>
      <template v-else-if="state.step === 'progress'">
        <UiButton v-if="(job && !terminal) || failed" :disabled="busy" @click="progressSecondary">{{ job && !terminal ? '取消分析' : '重试为新的分析' }}</UiButton>
        <UiButton variant="primary" :disabled="busy" :busy="busy" @click="progressPrimary">{{ job?.state === 'SUCCEEDED' ? '查看报告' : '刷新进度' }}</UiButton>
      </template>
    </footer>

    <UiSheet v-if="settingsOpen" class="m-settings-dialog" variant="detail" title="服务与存储设置" description="检查本机模型连接、当前分析材料的保存范围与证据边界。" @close="closeSettings()">
      <section class="m-settings-section">
        <h2>模型连接</h2>
        <p class="m-settings-status">{{ model.configured ? '本机已配置模型' : '尚未配置模型' }}</p>
        <p v-if="model.endpoint" class="hash">{{ model.endpoint }}</p>
        <p class="m-help">Key 在系统窗口输入并保存在本机。仅把完整收集指令和应用线索发送给所选模型；服务是否具备联网能力，以实际结果为准。</p>
        <UiButton :disabled="busy" @click="flow.settings(true)">{{ model.configured ? '修改模型配置' : '设置模型配置' }}</UiButton>
      </section>
      <section class="m-settings-section">
        <h2>材料与存储</h2>
        <p v-if="context">当前材料保存在本机服务，服务端长期保留至主动删除。删除后原始材料与分析结果不可恢复。</p>
        <p v-else>尚未选择分析材料。</p>
        <p v-if="context" class="hash">{{ context.origin }}</p>
        <div class="m-button-row">
          <UiButton :disabled="busy || !context" @click="flow.refresh">重新读取材料</UiButton>
          <UiButton v-if="context" variant="danger" :disabled="busy" @click="flow.remove">删除远端材料</UiButton>
        </div>
      </section>
      <section class="m-settings-section">
        <h2>证据边界</h2>
        <p class="m-help">静态线索不证明实际采集；权限是能力，invoke 是静态潜在线索。UNKNOWN、PARTIAL、UNREVIEWED 与附件未检查状态保持可见，不升级结论。</p>
        <p class="m-help">PrivacyTrace · 本机运行 · 政策对照工作台</p>
      </section>
    </UiSheet>
  </div>
</template>
