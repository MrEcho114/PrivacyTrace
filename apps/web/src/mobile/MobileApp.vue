<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiIcon from '../components/UiIcon.vue'
import BrandMark from '../components/BrandMark.vue'
import UiSheet from '../components/UiSheet.vue'
import HashValue from '../components/HashValue.vue'
import PolicyAssist from '../components/PolicyAssist.vue'
import CandidatePage from '../pages/CandidatePage.vue'
import ExistingReports from '../App.vue'
import MobileMaterialContext from '../components/MobileMaterialContext.vue'
import { frontendCopy, policyStateLine } from '../copy'
import type { JobStage, PolicyStateCopyInput } from '../copy'
import { collectionInstructions } from '../policyAssist'
import { sourceStatusLabel, steps } from '../workflow'
import type { Step } from '../workflow'
import type { WebSource } from '../types'
import { mobileBridge } from './bridge'
import { createMobileFlow } from './flow'
import './mobile.css'

const flow = createMobileFlow(mobileBridge)
const { state, context, draft, job, report, taxonomy, busy, error, notice, lastUpdated, model, modelResult, resultToken, hasPolicyText } = flow
const modelName = ref(''), appHint = ref('')
const modelPrompt = computed(() => appHint.value.trim() ? collectionInstructions(appHint.value) : '')
const labels = computed(() => Object.fromEntries(taxonomy.value?.data_types.map(t => [t.id, t.label]) ?? []))

// Claude 的 4×48 步骤轨放不下 #167 的长文案；可见标签用短名，完整名称保留在 aria-label。
const stepLabels = frontendCopy.steps
const shortStepLabels = ['APK', '核对', '扫描', '报告']
const pageTitles: Record<Step, string> = {
  import: frontendCopy.pageTitles.import,
  candidates: frontendCopy.pageTitles.candidates,
  progress: frontendCopy.pageTitles.progress,
  report: frontendCopy.pageTitles.report,
}
const currentIndex = computed(() => steps.indexOf(state.step))
const title = computed(() => pageTitles[state.step] ?? 'PrivacyTrace')
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
// One stage vocabulary: the canonical frontendCopy map plus its order. Unknown
// codes from a newer bridge stay readable instead of being renamed locally.
function stageName(value: string): string {
  return frontendCopy.stageOrder.includes(value as JobStage) ? frontendCopy.stages[value as JobStage] : value
}
const stageLabel = computed(() => job.value ? stageName(job.value.state) : '等待开始分析')
const failed = computed(() => !!job.value && (job.value.state === 'FAILED' || job.value.state === 'CANCELLED'))
// A mobile draft exposes text availability (`status`) only; review, completeness
// and attachment checks are not part of the draft contract. Fetching a body never
// upgrades review, and the shell has no review/attachment action, so the truthful
// source line is unreviewed / completeness unknown / attachments not checked.
function sourceStateLine(source: WebSource): string {
  const fields = source as WebSource & Partial<PolicyStateCopyInput>
  const has = (key: keyof PolicyStateCopyInput) => Object.hasOwn(source, key)
  return policyStateLine({
    // Draft sources have no review/completeness/attachment fields. Until the
    // bridge exposes them, their absence is the documented mobile fact: the
    // shell cannot review a policy or check attachments, and a body fetch never
    // upgrades either. A present null still reads as unknown.
    review_status: has('review_status') ? fields.review_status ?? null : 'UNREVIEWED',
    completeness: has('completeness') ? fields.completeness ?? null : null,
    attachments_status: has('attachments_status') ? fields.attachments_status ?? null : 'NOT_CHECKED',
  })
}
const reportVersion = computed(() => {
  if (!report.value) return ''
  const sample = report.value.sample
  return sample.version_name ?? ('v' + sample.version_code)
})

// 时间戳统一转成本地可读格式；原始值仍留在 datetime 属性 / 说明里，供核对时区。
// 解析失败时不编造时间，原样显示服务返回的字符串。
function formatLocal(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false, dateStyle: 'medium', timeStyle: 'medium' })
}
// 失败原因只展示服务真的返回过的内容；没有就明说尚未取得，不补百分比、ETA 或猜测。
const failureReason = computed(() => {
  if (!failed.value) return ''
  const raw = job.value?.error?.trim()
  if (!raw) return '服务尚未返回失败原因。'
  try {
    const parsed = JSON.parse(raw) as { message?: string; detail?: string }
    const message = String(parsed?.message ?? parsed?.detail ?? '').trim()
    if (message) return message
  } catch { /* 不是 JSON 就按原样展示 */ }
  return raw
})
const statusHeading = computed(() => {
  if (job.value?.state === 'SUCCEEDED') return frontendCopy.stages.SUCCEEDED
  return failed.value ? '本次分析未完成' : '正在分析当前材料'
})
const lastUpdatedLabel = computed(() => lastUpdated.value ? `最近更新 ${formatLocal(lastUpdated.value)}` : '')
// 移动壳只保留一个主操作：报告是阅读态、空材料态由空状态卡片自己提供 CTA，
// 这两种情况不再挂一条挤占视口的固定底栏。
const showActionBar = computed(() => state.step !== 'report' && !(state.step === 'import' && !context.value))
// 删除材料是破坏性操作：先在同一位置确认作用对象，再调用真实删除。
const pendingRemove = ref(false)
const pendingSettingsRemove = ref(false)
watch(context, () => { pendingRemove.value = false; pendingSettingsRemove.value = false })
function askRemove() { pendingRemove.value = true }
function cancelRemove() { pendingRemove.value = false }
function confirmRemove() { pendingRemove.value = false; void flow.remove() }
function askSettingsRemove() { pendingSettingsRemove.value = true }
function cancelSettingsRemove() { pendingSettingsRemove.value = false }
function confirmSettingsRemove() { pendingSettingsRemove.value = false; void flow.remove() }
function refreshJob() { void flow.poll() }

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
const settingsOpen = ref(false)
const settingsTrigger = ref<HTMLElement | null>(null)
const stepEntering = ref(false)
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
  pendingSettingsRemove.value = false
  settingsOpen.value = true
  pushOverlay()
}
function closeSettings(byBack = false) {
  if (!settingsOpen.value) return
  pendingSettingsRemove.value = false
  settingsOpen.value = false
  if (!byBack) popOverlay()
  void nextTick(() => settingsTrigger.value?.focus({ preventScroll: true }))
}

onMounted(() => {
  document.documentElement.classList.add('mobile-shell')
  // 移动 token 作用域（main.ts 只在 Tauri 里挂；浏览器 harness 走这里兜底）。
  document.body.classList.add('is-mobile-app')
  history.replaceState({ ...(typeof history.state === 'object' && history.state ? history.state : {}), pt: state.step }, '')
  window.addEventListener('popstate', onPopState)
  void flow.settings()
})
onBeforeUnmount(() => {
  window.removeEventListener('popstate', onPopState)
  actionbarObserver?.disconnect()
  document.documentElement.style.removeProperty('--m-actionbar-actual')
  document.documentElement.classList.remove('mobile-shell')
  document.body.classList.remove('is-mobile-app')
  void flow.stop()
})
</script>

<template>
  <div class="mobile-workspace" :class="{ 'm-report-step': state.step === 'report', 'm-no-actionbar': !showActionBar }">
    <a class="skip-link" href="#workspace-content">跳到内容</a>
    <header class="m-appbar">
      <button v-if="state.step !== 'import'" type="button" class="m-icon-button" aria-label="返回上一步" @click="goBack">
        <UiIcon name="back" />
      </button>
      <span v-else class="m-appbar-spacer m-appbar-brand" aria-hidden="true"><BrandMark /></span>
      <div class="m-appbar-titles">
        <h1 id="page-title" tabindex="-1">{{ title }}</h1>
        <p class="m-appbar-subtitle">{{ frontendCopy.brandSubtitle }}</p>
      </div>
      <button type="button" class="m-icon-button" aria-label="服务与存储设置" aria-haspopup="dialog" @click="openSettings">
        <UiIcon name="settings" />
      </button>
    </header>

    <nav class="m-steps" aria-label="创建流程">
      <ol>
        <li v-for="(label, index) in stepLabels" :key="steps[index]">
          <button type="button" class="m-step" :class="{ current: index === currentIndex, complete: index < currentIndex }" :aria-current="index === currentIndex ? 'step' : undefined" :aria-label="label" :disabled="stepDisabled(index)" @click="navigate(steps[index])">
            <span class="m-step-number" aria-hidden="true">{{ index < currentIndex ? '✓' : index + 1 }}</span>
            <span class="m-step-label">{{ shortStepLabels[index] ?? label }}</span>
          </button>
        </li>
      </ol>
    </nav>

    <main id="workspace-content" class="m-main" :class="{ 'm-step-enter': stepEntering }" tabindex="-1" @animationend="stepEntering = false">
      <MobileMaterialContext v-if="context && state.step !== 'import' && state.step !== 'report'"
        :name="contextName" :version="contextVersion" :origin="context.origin" :draft-id="context.draft" :revision="draft?.revision" @change="navigate('import')" />

      <template v-if="state.step === 'import'">
        <section v-if="!context" class="m-card m-empty-card">
          <h2>选择要对照的应用</h2>
          <p>只会上传你选择的应用和安装包。选择后由分析服务解析，材料保留到你主动删除。</p>
          <div class="m-button-row">
            <UiButton variant="primary" :disabled="busy" @click="flow.select()">选择应用</UiButton>
            <UiButton :disabled="busy" @click="flow.select(true)">恢复当前材料</UiButton>
          </div>
          <p class="m-help">上传的是安装包本身；这里不会读取手机上的其他文件。</p>
        </section>
        <section v-else class="m-card">
          <div class="m-card-head"><h2>当前分析材料</h2></div>
          <p class="m-material-name" :role="draft ? undefined : 'status'">{{ draft?.name || '正在读取材料…' }}</p>
          <HashValue v-if="draft?.apk_sha256" label="APK SHA-256" :value="draft.apk_sha256" />
          <p class="m-help">材料保存在分析服务，直到你主动删除。更换文件请重新选择应用。</p>
          <p class="m-help">分析服务：{{ context.origin }}</p>
          <div class="m-material-actions">
            <template v-if="pendingRemove">
              <p class="m-material-warning" role="alert">将从分析服务删除「{{ draft?.name || '当前材料' }}」及其分析结果，无法恢复。</p>
              <UiButton variant="danger" :disabled="busy" @click="confirmRemove">确认删除</UiButton>
              <UiButton variant="quiet" :disabled="busy" @click="cancelRemove">取消</UiButton>
            </template>
            <template v-else>
              <UiButton :disabled="busy" @click="flow.refresh">重新读取材料</UiButton>
              <UiButton variant="danger" :disabled="busy" @click="askRemove">删除已上传材料</UiButton>
            </template>
          </div>
        </section>
        <div v-if="busy" class="m-notice m-busy-notice"><span role="status">正在处理，请稍候。</span><UiButton variant="quiet" @click="flow.stop">停止本次请求</UiButton></div>
        <section v-if="context" class="m-section" aria-labelledby="m-sources-title">
          <div class="m-section-head"><h2 id="m-sources-title">政策来源</h2><span class="m-help">{{ draft?.sources.length ?? 0 }} 份</span></div>
          <article v-for="source in visibleSources" :key="source.id" class="m-source-row">
            <details>
              <summary class="m-row">
                <span class="m-row-main">
                  <strong>{{ source.title || '未命名来源' }}</strong>
                  <span class="m-row-sub">{{ sourceStatusLabel(source.status) }} · {{ sourceStateLine(source) }}</span>
                </span>
                <UiIcon name="chevron-right" class="m-chevron" />
              </summary>
              <div class="m-row-body">
                <p v-if="source.url" class="hash">{{ source.url }}</p>
                <div v-if="source.text" class="policy-reading">{{ source.text }}</div>
                <p v-else class="m-help">还没有正文。下一步会尝试查找，也可以从下方补充。</p>
              </div>
            </details>
          </article>
          <p v-if="!hasSources" class="m-help">还没有政策来源。下一步会尝试查找，也可以从下方补充。</p>
        </section>
        <PolicyAssist v-if="context" :busy="busy" :source-count="draft?.sources.length ?? 0" :initial-result="modelResult" :result-token="resultToken" @import="flow.importCollected" />
        <details v-if="context" class="m-details m-model">
          <summary>使用手机上的个人模型</summary>
          <p class="m-help">密钥只在系统窗口输入，保存在本机。</p>
          <div class="m-button-row"><UiButton :disabled="busy" @click="flow.settings(true)">{{ model.configured ? '修改模型' : '配置模型' }}</UiButton><span class="m-help">{{ model.configured ? '本机已配置' : '尚未配置，也能继续' }}</span></div>
          <p v-if="model.endpoint" class="hash">{{ model.endpoint }}</p>
          <label class="mobile-field" for="mobile-model-name">模型名称<input id="mobile-model-name" v-model="modelName" :disabled="busy" maxlength="200" /></label>
          <label class="mobile-field" for="mobile-app-hint">应用名称或包名<input id="mobile-app-hint" v-model="appHint" :disabled="busy" maxlength="200" :placeholder="draft?.name" /></label>
          <details v-if="modelPrompt" class="m-details"><summary>查看将发送的完整指令</summary><pre class="policy-reading">{{ modelPrompt }}</pre></details>
          <UiButton :disabled="busy || !model.configured || !modelName.trim() || !appHint.trim()" @click="flow.collect(modelName, appHint)">使用个人模型收集一次</UiButton>
        </details>
      </template>

      <template v-else-if="state.step === 'candidates' && context">
        <p v-if="!hasPolicyText" class="m-notice m-message" role="status">当前没有可对照的政策正文，保存候选并开始分析会被服务拒绝。请返回材料页重新获取网址，或粘贴／导入政策文本。</p>
        <!-- 移动端由下方共享消息区渲染 flow.error；页内再传一次会重复 role="alert"。 -->
        <CandidatePage mobile :state="state" :busy="busy" :type-labels="labels" :persist="flow.save" @back="navigate('import')" @next="flow.begin" @retry-source="flow.retrySource" @retry-model="flow.retryModel" />
      </template>

      <template v-else-if="state.step === 'progress'">
        <section class="m-card m-status-card" :class="{ failed }">
          <p class="m-eyebrow" role="status">{{ stageLabel }}</p>
          <h2>{{ statusHeading }}</h2>
          <p v-if="failed" class="m-error" role="alert">{{ failureReason }}</p>
          <p v-else-if="job?.state === 'SUCCEEDED'" class="m-help">阶段已完成。报告里有证据位置与政策原句。</p>
          <p v-else class="m-help">阶段会自动更新，不需要反复点刷新。取消只停止本次分析，材料会保留。</p>
          <p v-if="lastUpdatedLabel" class="m-help">{{ lastUpdatedLabel }}</p>
          <details v-if="job" class="m-details m-job-meta">
            <summary>任务详情</summary>
            <div class="m-row-body">
              <dl class="m-meta-list">
                <div><dt>任务 ID</dt><dd class="hash">{{ job.id }}</dd></div>
                <div v-if="job.created_at"><dt>创建时间</dt><dd><time :datetime="job.created_at" :title="job.created_at">{{ formatLocal(job.created_at) }}</time></dd></div>
                <div v-if="lastUpdated"><dt>最近读取</dt><dd><time :datetime="lastUpdated" :title="lastUpdated">{{ formatLocal(lastUpdated) }}</time></dd></div>
              </dl>
            </div>
          </details>
        </section>
        <section class="m-section" aria-labelledby="m-timeline-title">
          <div class="m-section-head"><h2 id="m-timeline-title">分析阶段</h2><span class="m-help">{{ job ? stageName(job.state) : '未开始' }}</span></div>
          <ol v-if="jobEvents.length" class="m-timeline">
            <li v-for="(event, index) in jobEvents" :key="event.at + event.state" :class="{ current: index === jobEvents.length - 1 }">
              <span class="m-timeline-dot" aria-hidden="true"></span>
              <span class="m-timeline-body"><strong>{{ stageName(event.state) }}</strong><time :datetime="event.at" :title="event.at">{{ formatLocal(event.at) }}</time></span>
            </li>
          </ol>
          <p v-else class="m-help">任务创建后会在这里按时间顺序显示阶段记录。</p>
        </section>
      </template>

      <div v-else-if="state.step === 'report' && report && taxonomy" class="m-report">
        <ExistingReports :key="report.job.id" :snapshot="{ report, taxonomy }" mobile />
        <details class="m-details m-report-meta">
          <summary>报告来源与版本</summary>
          <div class="m-row-body">
            <dl class="m-meta-list">
              <div><dt>包名</dt><dd class="hash">{{ report.sample.package_name }}</dd></div>
              <div><dt>版本</dt><dd>{{ reportVersion }}</dd></div>
              <div v-if="report.job.created_at"><dt>原生成时间</dt><dd><time :datetime="report.job.created_at" :title="report.job.created_at">{{ formatLocal(report.job.created_at) }}</time></dd></div>
              <div v-if="context"><dt>分析服务</dt><dd class="hash">{{ context.origin }}</dd></div>
              <div v-if="context"><dt>材料标识</dt><dd class="hash">{{ context.draft }}</dd></div>
              <div v-if="context && draft?.revision != null"><dt>材料版本</dt><dd>{{ draft.revision }}</dd></div>
            </dl>
            <UiButton v-if="context" variant="quiet" @click="navigate('import')">更换材料</UiButton>
          </div>
        </details>
      </div>
      <p v-else-if="state.step === 'report'" class="m-notice" role="status">报告还没载入。回到进度页刷新状态。</p>

      <template v-if="error || notice">
        <p v-if="error" class="m-error m-message" role="alert">{{ error }}</p>
        <p v-if="notice && state.step !== 'progress'" class="m-notice m-message" role="status">{{ notice }}</p>
      </template>
    </main>

    <footer v-if="showActionBar" ref="actionbar" class="m-actionbar" role="group" aria-label="当前步骤操作">
      <template v-if="state.step === 'import'">
        <UiButton variant="primary" :disabled="busy || !context" :busy="busy" @click="flow.prepare">准备政策</UiButton>
      </template>
      <template v-else-if="state.step === 'candidates'">
        <UiButton variant="primary" :disabled="busy || !hasPolicyText" :busy="busy" @click="flow.begin">保存并分析</UiButton>
      </template>
      <template v-else-if="state.step === 'progress'">
        <template v-if="job && job.state === 'SUCCEEDED'">
          <UiButton variant="primary" :disabled="busy" :busy="busy" @click="flow.openReport">查看报告</UiButton>
        </template>
        <template v-else-if="failed">
          <UiButton :disabled="busy" :busy="busy" @click="refreshJob">刷新状态</UiButton>
          <UiButton variant="primary" :disabled="busy" @click="flow.control('retry-job')">重新分析</UiButton>
        </template>
        <template v-else>
          <UiButton :disabled="busy" :busy="busy" @click="refreshJob">刷新状态</UiButton>
          <UiButton v-if="job" variant="quiet" class="m-cancel-action" :disabled="busy" @click="flow.control('cancel-job')">取消分析</UiButton>
        </template>
      </template>
    </footer>

    <UiSheet v-if="settingsOpen" class="m-settings-dialog" variant="detail" title="服务与存储设置" description="查看模型连接，以及当前材料保存在哪里。" @close="closeSettings()">
      <section class="m-settings-section">
        <h2>模型连接</h2>
        <p class="m-settings-status">{{ model.configured ? '本机已配置模型' : '尚未配置模型' }}</p>
        <p v-if="model.endpoint" class="hash">{{ model.endpoint }}</p>
        <p class="m-help">密钥只在系统窗口输入，保存在本机。{{ frontendCopy.facts.mobileModelInput }}</p>
        <UiButton :disabled="busy" @click="flow.settings(true)">{{ model.configured ? '修改模型' : '配置模型' }}</UiButton>
      </section>
      <section class="m-settings-section">
        <h2>材料与存储</h2>
        <p v-if="context">当前材料保存在下面的分析服务，直到你主动删除。删除后原始材料与分析结果不可恢复。</p>
        <p v-else>尚未选择分析材料。</p>
        <p v-if="context" class="hash">{{ context.origin }}</p>
        <div class="m-button-row">
          <UiButton :disabled="busy || !context" @click="flow.refresh">重新读取材料</UiButton>
          <UiButton v-if="context && !pendingSettingsRemove" variant="danger" :disabled="busy" @click="askSettingsRemove">删除已上传材料</UiButton>
        </div>
        <div v-if="context && pendingSettingsRemove" class="m-button-row">
          <p class="m-material-warning" role="alert">将从分析服务删除当前材料及其分析结果，无法恢复。</p>
          <UiButton variant="danger" :disabled="busy" @click="confirmSettingsRemove">确认删除</UiButton>
          <UiButton variant="quiet" :disabled="busy" @click="cancelSettingsRemove">取消</UiButton>
        </div>
      </section>
    </UiSheet>
  </div>
</template>

<style scoped>
/* Import step has no back button; the 48×48 spacer keeps the appbar grid
   symmetric, and 9px of padding centres the 30px shared mark inside it. */
.m-appbar-brand { display: grid; place-items: center; padding: 9px; }
</style>
