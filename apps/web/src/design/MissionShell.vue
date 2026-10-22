<script setup lang="ts">
defineProps<{ gallery?: boolean }>()
const steps = ['导入材料', '检查候选', '分析进度', '对照报告']
</script>
<template>
  <div class="pt-foundation">
    <a class="pt-skip" href="#design-content">跳到主要内容</a>
    <div class="pt-equipment">
      <header class="pt-masthead">
        <div><p class="pt-brand">PRIVACYTRACE</p><p class="pt-brand-caption">静态证据与隐私声明对照 <span>/ MISSION CONTROL</span></p></div>
        <div class="pt-header-meta"><span class="pt-code">PT–04 / REPORT</span><a :href="gallery ? './design.html' : './design.html?view=components'">{{ gallery ? '查看报告示例' : '组件与设计规范' }} ↗</a></div>
      </header>
      <div class="pt-identity" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
      <div class="pt-workspace">
        <aside class="pt-index" aria-label="流程概览">
          <p class="pt-code pt-index-label">MISSION / INDEX 01—04</p>
          <ol><li v-for="(step, index) in steps" :key="step" :class="{ current: index === 3 }"><span class="pt-code">0{{ index + 1 }}</span><strong>{{ step }}</strong></li></ol>
          <div class="pt-index-notes"><p>静态分析 · 证据可追溯</p><p>示例材料 / 不代表真实扫描</p><p>未知与待复核如实保留</p></div>
        </aside>
        <main id="design-content" class="pt-main" tabindex="-1">
          <ol class="pt-step-rail" aria-label="报告所在流程"><li v-for="(step, index) in steps" :key="step" :aria-current="index === 3 ? 'step' : undefined"><span class="pt-code">0{{ index + 1 }}</span><span>{{ step }}</span></li></ol>
          <slot />
        </main>
      </div>
      <footer class="pt-footer"><span class="pt-code">PRIVACYTRACE / DESIGN FOUNDATION</span><span>设计示例 · 合成材料 · 未连接分析服务</span></footer>
    </div>
  </div>
</template>
