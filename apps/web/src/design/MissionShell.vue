<script setup lang="ts">
import { frontendCopy } from '../copy'
defineProps<{ gallery?: boolean }>()
const steps = frontendCopy.steps
</script>
<template>
  <div class="pt-foundation">
    <a class="pt-skip" href="#design-content">跳到主要内容</a>
    <div class="pt-equipment">
      <header class="pt-masthead">
        <div><p class="pt-brand">PRIVACYTRACE</p><p class="pt-brand-caption">{{ frontendCopy.brandSubtitle }}</p></div>
        <div class="pt-header-meta"><span class="pt-global-demo">{{ frontendCopy.demoBadge }}</span><a :href="gallery ? './design.html' : './design.html?view=components'">{{ gallery ? '查看报告示例' : '组件与设计规范' }} ↗</a></div>
      </header>
      <div class="pt-identity" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
      <div class="pt-workspace" :class="{ 'pt-workspace-gallery': gallery }">
        <nav v-if="!gallery" class="pt-workflow" aria-label="分析流程">
          <p class="pt-code pt-index-label">MISSION / 01—04</p>
          <ol><li v-for="(step, index) in steps" :key="step" :aria-current="index === 3 ? 'step' : undefined"><span class="pt-code">0{{ index + 1 }}</span><strong>{{ step }}</strong></li></ol>
          <p class="pt-workflow-help">流程位置概览</p>
        </nav>
        <main id="design-content" class="pt-main" tabindex="-1">
          <slot />
        </main>
      </div>
      <footer class="pt-footer"><span class="pt-code">PRIVACYTRACE / DESIGN FOUNDATION</span><span>报告与组件规范</span></footer>
    </div>
  </div>
</template>
