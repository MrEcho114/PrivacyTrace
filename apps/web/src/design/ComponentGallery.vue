<script setup lang="ts">
import { ref } from 'vue'
import UiButton from '../components/UiButton.vue'
import UiField from '../components/UiField.vue'
import StatusTag from '../components/StatusTag.vue'
import InstrumentPanel from './InstrumentPanel.vue'
import ReportMetrics from './ReportMetrics.vue'
import StaticBoundary from './StaticBoundary.vue'
import { frontendCopy, policyStateLine } from '../copy'
const note = ref('')
const showError = ref(false)
const pending = ref(false)
function togglePending() { pending.value = !pending.value }
const colors = [{ name: '工作面', value: '#FFFFFF' }, { name: '仅顶栏', value: '#ECE5D6' }, { name: '正文', value: '#252A2E' }, { name: '结构线', value: '#4C5A68' }, { name: '关键动作', value: '#D63A2C' }]
</script>
<template>
  <header class="pt-report-heading"><p class="pt-eyebrow pt-code">DESIGN / FOUNDATION</p><h1>基础组件与使用规范</h1><p class="pt-subtitle">同一套控件、同一套视觉规则，供完整前端接入。</p></header>
  <div class="pt-gallery">
    <InstrumentPanel title="01 / 颜色与字体" label="TOKENS">
      <ul class="pt-swatches"><li v-for="color in colors" :key="color.value"><span :style="{ backgroundColor: color.value }" aria-hidden="true"></span><strong>{{ color.name }}</strong><code>{{ color.value }}</code></li></ul>
      <h3>复用 Pioneer 的字体设计</h3><p>保留 Noto Serif SC 展示标题、Noto Sans SC 正文与操作、Consolas / Courier New 技术标识。报告主标题桌面48px/手机36px，重点条目28px/24px，阅读正文16px；重要信息与辅助标签拉开明显层级。</p><p class="pt-type-specimen">{{ frontendCopy.reportTitle }}</p><p class="pt-code">REPORT / 04 · DATA COMPARISON</p><p>白色工作面；米白仅用于顶栏。四色条属于身份识别，不表示风险或分析结果。</p>
    </InstrumentPanel>
    <InstrumentPanel title="02 / 操作控件" label="UiButton / UiField">
      <div class="pt-component-row"><UiButton variant="primary" @click="showError = true">校验示例字段</UiButton><UiButton @click="togglePending">{{ pending ? '结束等待演示' : '演示等待状态' }}</UiButton><UiButton :busy="pending" :disabled="!pending">{{ pending ? '正在处理示例' : '等待状态示例' }}</UiButton><UiButton disabled>不可用操作</UiButton></div>
      <UiField id="design-note" label="材料备注" help="仅用于本页组件演示，不会发送或保存。" :error="showError && !note.trim() ? '请填写备注后再校验。' : undefined" v-slot="{ describedby }"><input id="design-note" v-model="note" :aria-describedby="describedby" :aria-invalid="showError && !note.trim() || undefined" /></UiField>
      <p v-if="showError && note.trim()" role="status">备注已填写（仅本地演示）。</p>
      <p>一个任务区域保留一个主操作。等待和禁用不依赖颜色；键盘焦点用深色外框。</p>
    </InstrumentPanel>
    <InstrumentPanel title="03 / 状态与证据边界" label="StatusTag">
      <div class="pt-tags"><StatusTag>UNKNOWN / 未知</StatusTag><StatusTag tone="wait">PARTIAL / 部分覆盖</StatusTag><StatusTag>UNREVIEWED / 待复核</StatusTag><StatusTag tone="error">失败 / 可重试</StatusTag><StatusTag tone="success">已保存 / 本地示例</StatusTag></div>
      <p class="pt-policy-state">{{ policyStateLine({ review_status: 'UNREVIEWED', completeness: null, attachments_status: 'NOT_CHECKED' }) }}</p>
      <StaticBoundary /><p>标签保留明确文字。来源、送达、复核、提取与覆盖分别映射，不把 REAL_SCAN 理解成实时运行。</p>
    </InstrumentPanel>
    <InstrumentPanel title="04 / 重点信息面板" label="InstrumentPanel / priority" priority>
      <p>每页选择一个最重要的信息区，以窄四色条标记。报告中优先标记“对照结论”，不标记每条结果或所有面板；红色仍用于主要操作，颜色不代表风险等级。</p>
      <ReportMetrics :types="2" :sources="1" :evidence="3" /><p>数量由当前材料计算；这里的 02 / 01 / 03 是合成示例，不是风险评分。</p>
    </InstrumentPanel>
    <InstrumentPanel title="05 / 响应式报告与状态" label="EXAMPLES">
      <ul class="pt-example-links"><li><a href="./design.html">双端报告示例 →</a></li><li><a href="./design.html?state=empty">空结果示例 →</a></li><li><a href="./design.html?state=unknown">未知来源与覆盖 →</a></li><li><a href="./design.html?state=long">长应用名与长文本 →</a></li></ul><p>桌面结论与证据并列；手机先读结论，再定位下方证据。返回操作恢复触发按钮焦点。示例不调用业务 API。</p>
    </InstrumentPanel>
  </div>
</template>
