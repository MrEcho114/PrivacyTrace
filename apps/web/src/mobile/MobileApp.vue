<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import UiButton from '../components/UiButton.vue'
import PolicyAssist from '../components/PolicyAssist.vue'
import CandidatePage from '../pages/CandidatePage.vue'
import ExistingReports from '../App.vue'
import { collectionInstructions } from '../policyAssist'
import { sourceStatusLabel } from '../workflow'
import { mobileBridge } from './bridge'
import { createMobileFlow } from './flow'

const flow = createMobileFlow(mobileBridge)
const { state, context, draft, job, report, taxonomy, busy, error, notice, model, modelResult } = flow
const modelName = ref(''), appHint = ref('')
const modelPrompt = computed(() => appHint.value.trim() ? collectionInstructions(appHint.value) : '')
const labels = computed(() => Object.fromEntries(taxonomy.value?.data_types.map(t => [t.id, t.label]) ?? []))
const terminal = computed(() => !!job.value && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.value.state))
const stages: Record<string, string> = { QUEUED: '等待处理', INTAKE: '核对材料', STATIC_ANALYSIS: '静态扫描', POLICY_PARSING: '装载政策', EVALUATING: '规则对照', REPORTING: '生成报告', SUCCEEDED: '报告已生成', FAILED: '分析未完成', CANCELLED: '分析已取消' }
onMounted(() => flow.settings())
onBeforeUnmount(() => { void flow.stop() })
</script>
<template>
  <div class="mobile-workspace">
    <a class="skip-link" href="#workspace-content">跳到内容</a>
    <header class="workspace-bar"><span class="workspace-brand"><span aria-hidden="true" class="brand-mark">P</span>PrivacyTrace</span><span class="workspace-purpose">静态证据与政策对照</span></header>
    <main id="workspace-content" class="mobile-content" tabindex="-1">
      <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ state.step === 'progress' ? '分析进度' : state.step === 'report' ? '对照报告' : '应用与政策' }}</h1><p>选择应用后，在系统窗口确认目标服务和上传范围。静态线索不证明实际采集。</p></div>
      <section class="material-panel">
        <div class="panel-heading"><h2>{{ context ? '当前分析材料' : '选择要对照的应用' }}</h2><span v-if="draft" class="field-help">材料版本 {{ draft.revision }}</span></div>
        <p v-if="context" class="hash">{{ context.origin }}<br />{{ draft?.name || context.draft }}</p>
        <p v-else class="field-help">仅上传主动选择的应用及其完整安装包集合。服务端长期保留至主动删除。</p>
        <div class="source-actions"><UiButton variant="primary" :disabled="busy" @click="flow.select()">选择应用并上传</UiButton><UiButton :disabled="busy" @click="flow.select(true)">恢复当前实例材料</UiButton><UiButton v-if="context" :disabled="busy" variant="quiet" @click="flow.remove">删除远端材料</UiButton></div>
      </section>
      <div v-if="busy" class="notice busy-notice"><span role="status">正在处理当前请求。</span><UiButton variant="quiet" @click="flow.stop">停止本次请求</UiButton></div>
      <p v-if="error" class="error-text" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <section v-if="context && state.step === 'import'" class="material-panel">
        <div class="panel-heading"><h2>政策来源</h2><UiButton :disabled="busy" variant="quiet" @click="flow.refresh">重新读取材料</UiButton></div>
        <article v-for="source in draft?.sources.filter(s => s.text || s.url)" :key="source.id" class="source-editor"><strong>{{ source.title }}</strong><p class="field-help">{{ sourceStatusLabel(source.status) }} · 完整度未知 · 未复核 · 附件未检查</p><p v-if="source.url" class="hash">{{ source.url }}</p><details v-if="source.text"><summary>查看来源正文</summary><p class="policy-reading">{{ source.text }}</p></details></article>
        <p v-if="!draft?.sources.some(s => s.text || s.url)" class="field-help">尚未补入政策。下一步会尝试自动查找；也可以使用下方辅助入口。</p>
        <PolicyAssist :busy="busy" :source-count="draft?.sources.length ?? 0" :initial-result="modelResult" @import="flow.importCollected" />
        <details class="source-body"><summary>使用手机上的个人模型</summary><p class="field-help">Key 在系统窗口输入并保存在本机。仅把完整收集指令和应用线索发送给所选模型；服务是否具备联网能力，以实际结果为准。</p>
          <div class="source-actions"><UiButton :disabled="busy" @click="flow.settings(true)">{{ model.configured ? '修改模型配置' : '设置模型配置' }}</UiButton><span class="field-help">{{ model.configured ? '本机已配置' : '尚未配置，可继续自动流程' }}</span></div>
          <p v-if="model.endpoint" class="hash">{{ model.endpoint }}</p>
          <label class="mobile-field" for="mobile-model-name">模型名称<input id="mobile-model-name" v-model="modelName" :disabled="busy" maxlength="200" /></label>
          <label class="mobile-field" for="mobile-app-hint">应用名称或包名<input id="mobile-app-hint" v-model="appHint" :disabled="busy" maxlength="200" :placeholder="draft?.name" /></label>
          <details v-if="modelPrompt"><summary>查看将发送的完整指令</summary><pre class="policy-reading">{{ modelPrompt }}</pre></details>
          <UiButton :disabled="busy || !model.configured || !modelName.trim() || !appHint.trim()" @click="flow.collect(modelName, appHint)">使用个人模型收集一次</UiButton>
        </details>
        <div class="flow-footer"><UiButton variant="primary" :disabled="busy" @click="flow.prepare">自动准备政策并继续</UiButton><span class="field-help">不强制配置个人模型或逐条检查候选。</span></div>
      </section>
      <CandidatePage v-if="context && state.step === 'candidates'" :state="state" :busy="busy" :type-labels="labels" @back="state.step = 'import'" @next="flow.begin" @persist-candidates="flow.save" />
      <section v-if="context && state.step === 'progress'" class="material-panel" :aria-busy="busy || undefined">
        <div role="status"><h2>{{ job ? stages[job.state] : '任务状态暂不可用' }}</h2></div><p class="hash">{{ job?.id }}</p><p v-if="job?.error" class="error-text" role="alert">本次分析未完成，可刷新状态或重试为新分析。</p>
        <ol class="stage-list"><li v-for="event in draft?.jobs.find(r => r.job_id === job?.id)?.events" :key="event.at + event.state"><strong>{{ stages[event.state] ?? event.state }}</strong><span>{{ event.at }}</span></li></ol>
        <div class="source-actions"><UiButton :disabled="busy" @click="flow.poll">刷新进度</UiButton><UiButton v-if="job && !terminal" :disabled="busy" @click="flow.control('cancel-job')">取消分析</UiButton><UiButton v-if="terminal && job?.state !== 'SUCCEEDED'" :disabled="busy" @click="flow.control('retry-job')">重试为新的分析</UiButton><UiButton v-if="job?.state === 'SUCCEEDED'" variant="primary" :disabled="busy" @click="flow.openReport">查看报告</UiButton></div>
      </section>
      <div v-if="state.step === 'report' && report && taxonomy" class="mobile-report"><ExistingReports :key="report.job.id" :snapshot="{ report, taxonomy }" /></div>
    </main>
  </div>
</template>
<style scoped>
.mobile-content { width: min(100%, 72rem); margin: auto; padding: 1.5rem; box-sizing: border-box; }
.busy-notice { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem; }
.mobile-field { display: grid; gap: .4rem; margin: 1rem 0; }
.policy-reading { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 24rem; overflow: auto; }
.hash { overflow-wrap: anywhere; }
.mobile-report :deep(.topbar), .mobile-report :deep(.intro) { display: none; }
.mobile-report :deep(main) { padding: 0; }
@media (max-width: 560px) { .mobile-content { padding: 1rem; } }
</style>
