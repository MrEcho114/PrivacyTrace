<script setup lang="ts">
import { computed } from 'vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy, frontendCopy } from '../copy'
import type { Workflow } from '../workflow'
const props = defineProps<{ state: Workflow }>()
defineEmits<{ back: []; report: [] }>()
// The example starts after the job is queued, so the clickable positions are the
// five non-terminal stages after QUEUED; terminal results stay in outcome.
const demoStages = frontendCopy.stageOrder.filter(stage => stage !== 'QUEUED' && stage !== 'SUCCEEDED' && stage !== 'FAILED' && stage !== 'CANCELLED')
const stopped = computed(() => props.state.outcome === 'failed' || props.state.outcome === 'cancelled')
const finished = computed(() => props.state.outcome === 'complete')
const position = computed(() => finished.value ? demoStages.length : Math.min(props.state.stage + 1, demoStages.length))
const displayStage = computed(() => props.state.outcome === 'failed' ? frontendCopy.stages.FAILED
  : props.state.outcome === 'cancelled' ? frontendCopy.stages.CANCELLED
    : finished.value ? frontendCopy.stages.SUCCEEDED
      : frontendCopy.stages[demoStages[props.state.stage] ?? 'REPORTING'])
function advance() { if (props.state.stage < demoStages.length - 1) props.state.stage++; else props.state.outcome = 'complete' }
</script>
<template>
  <div class="page page-progress">
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ frontendCopy.pageTitles.progress }}</h1><p>{{ copy.progressDescription }}</p></div>
    <section class="material-panel progress-panel priority-panel">
      <div class="panel-heading"><h2>示例材料</h2><StatusTag tone="info">手动切换阶段</StatusTag></div><p class="field-help">{{ state.sources.length }} 份政策来源 · APK 静态线索与政策候选</p>
      <div class="progress-overview"><ol class="stage-list"><li v-for="(stage, index) in demoStages" :key="stage" :class="{ current: !finished && !stopped && index === state.stage, done: finished || index < state.stage }"><span class="stage-number" aria-hidden="true">{{ finished || index < state.stage ? '✓' : index + 1 }}</span><div><strong>{{ frontendCopy.stages[stage] }}</strong><p>{{ finished || index < state.stage ? '已完成' : !finished && !stopped && index === state.stage ? '当前阶段' : '尚未开始' }}</p></div></li></ol>
      <div class="stage-preview"><div role="status" aria-atomic="true"><p class="stage-progress">阶段 {{ position }} / {{ demoStages.length }}</p><h2>{{ displayStage }}</h2></div>
        <div class="progress-actions"><template v-if="state.outcome === 'idle'"><UiButton variant="primary" @click="advance">{{ state.stage === demoStages.length - 1 ? copy.completeStage : copy.nextStage }}</UiButton><UiButton variant="quiet" @click="state.outcome = 'cancelled'">{{ copy.cancel }}</UiButton></template><UiButton v-else-if="finished" variant="primary" @click="$emit('report')">{{ copy.viewReport }}</UiButton></div>
      </div></div>
      <div v-if="stopped" class="notice"><p role="alert">{{ displayStage }} · 输入保留</p><UiButton @click="state.outcome = 'idle'">{{ copy.retry }}</UiButton></div>
      <div v-if="state.sources.some(source => source.status === 'failed')" class="notice" role="status"><span>{{ copy.sourceFailed }}</span><p v-for="source in state.sources.filter(item => item.status === 'failed')" :key="source.id">{{ source.title || '未命名来源' }}</p></div>
      <details class="execution-details"><summary>阶段与来源详情</summary><dl><div><dt>模型请求</dt><dd>未执行</dd></div><div><dt>Docker 扫描</dt><dd>未执行</dd></div></dl><UiButton v-if="state.outcome === 'idle'" @click="state.outcome = 'failed'">{{ copy.failStage }}</UiButton></details>
    </section>
    <div class="flow-footer"><UiButton @click="$emit('back')">{{ copy.back }}</UiButton></div>
  </div>
</template>
