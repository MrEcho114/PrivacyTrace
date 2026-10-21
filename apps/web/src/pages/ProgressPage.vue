<script setup lang="ts">
import { computed } from 'vue'
import UiButton from '../components/UiButton.vue'
import StatusTag from '../components/StatusTag.vue'
import { copy } from '../copy'
import { stageNames } from '../workflow'
import type { Workflow } from '../workflow'
const props = defineProps<{ state: Workflow }>()
defineEmits<{ back: []; report: [] }>()
const stopped = computed(() => props.state.outcome === 'failed' || props.state.outcome === 'cancelled')
function advance() { if (props.state.stage < 4) props.state.stage++; else props.state.outcome = 'complete' }
</script>
<template>
  <div>
    <div class="page-heading"><h1 id="page-title" tabindex="-1">{{ copy.progressTitle }}</h1><p>{{ copy.demoHelp }}</p></div>
    <section class="material-panel progress-panel">
      <div class="panel-heading"><h2>纸舟地图</h2><StatusTag tone="info">手动体验阶段</StatusTag></div><p class="field-help">{{ state.sources.length }} 份政策来源 · APK 静态线索与政策候选</p>
      <div class="progress-overview"><ol class="stage-list"><li v-for="(name, index) in stageNames" :key="name" :class="{ current: index === state.stage, done: index < state.stage || state.outcome === 'complete' }"><span class="stage-number">{{ index < state.stage || state.outcome === 'complete' ? '✓' : index + 1 }}</span><div><strong>{{ name }}</strong><p>{{ index < state.stage || state.outcome === 'complete' ? '示例阶段已切换' : index === state.stage ? '当前体验阶段' : '尚未体验' }}</p></div></li></ol>
      <div class="stage-preview"><div role="status" aria-atomic="true"><StatusTag :tone="stopped ? 'error' : state.outcome === 'complete' ? 'success' : 'info'">{{ state.outcome === 'failed' ? copy.stageFailed : state.outcome === 'cancelled' ? copy.cancelled : state.outcome === 'complete' ? copy.fixedReport : '当前体验阶段' }}</StatusTag><h2>{{ stageNames[state.stage] }}</h2></div><p>{{ copy.progressDescription }}</p>
        <div class="progress-actions"><template v-if="state.outcome === 'idle'"><UiButton variant="primary" @click="advance">{{ state.stage === 4 ? copy.completeStage : copy.nextStage }}</UiButton><UiButton variant="quiet" @click="state.outcome = 'cancelled'">{{ copy.cancel }}</UiButton></template><UiButton v-else-if="state.outcome === 'complete'" variant="primary" @click="$emit('report')">{{ copy.viewReport }}</UiButton></div>
      </div></div>
      <div v-if="stopped" class="notice"><p role="alert">{{ state.outcome === 'failed' ? copy.stageFailed : copy.cancelled }} · 输入保留</p><UiButton @click="state.outcome = 'idle'">{{ copy.retry }}</UiButton></div>
      <div v-if="state.sources.some(source => source.status === 'failed')" class="notice" role="status"><span>{{ copy.sourceFailed }}</span><p v-for="source in state.sources.filter(item => item.status === 'failed')" :key="source.id">{{ source.title || '未命名来源' }}</p></div>
      <details class="execution-details"><summary>阶段与来源详情</summary><p>{{ copy.reportHelp }}</p><dl><div><dt>模型请求</dt><dd>未执行</dd></div><div><dt>Docker 扫描</dt><dd>未执行</dd></div><div><dt>材料</dt><dd>人工构造示例</dd></div></dl><UiButton v-if="state.outcome === 'idle'" @click="state.outcome = 'failed'">{{ copy.failStage }}</UiButton></details>
    </section>
    <div class="flow-footer"><UiButton @click="$emit('back')">{{ copy.back }}</UiButton><span class="field-help">{{ copy.storageHelp }}</span></div>
  </div>
</template>
