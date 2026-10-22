<script setup lang="ts">
import UiButton from './UiButton.vue'
import UiIcon from './UiIcon.vue'

defineProps<{ name: string; version: string; origin: string; draftId: string; revision?: number }>()
defineEmits<{ change: [] }>()
</script>

<template>
  <section class="m-context material-context" aria-label="当前分析材料">
    <details class="material-disclosure">
      <summary>
        <span class="material-identity"><strong>{{ name }}</strong><span>{{ version }}</span></span>
        <span class="material-affordance">详情<UiIcon name="chevron-right" /></span>
      </summary>
      <dl class="material-facts">
        <div><dt>应用或材料</dt><dd>{{ name }}</dd></div>
        <div><dt>分析服务</dt><dd>{{ origin }}</dd></div>
        <div><dt>材料标识</dt><dd>{{ draftId }}</dd></div>
        <div v-if="revision != null"><dt>材料版本</dt><dd>{{ revision }}</dd></div>
      </dl>
    </details>
    <UiButton variant="quiet" class="material-change" @click="$emit('change')">更换材料</UiButton>
  </section>
</template>

<style scoped>
.material-context { display: flex; align-items: flex-start; gap: 4px; padding: 4px 8px 4px 12px; margin-bottom: 12px; border: 1px solid var(--pt-rule); border-radius: var(--m-card-radius); background: var(--pt-paper); }
.material-disclosure { flex: 1; min-width: 0; }
.material-disclosure > summary { display: flex; align-items: center; gap: 8px; min-height: var(--m-touch); padding: 4px 0; box-sizing: border-box; cursor: pointer; list-style: none; }
.material-disclosure > summary::-webkit-details-marker { display: none; }
.material-identity { display: grid; flex: 1; min-width: 0; gap: 2px; }
.material-identity strong { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 0.9375rem; font-weight: 600; color: var(--pt-ink); }
.material-identity > span { color: var(--pt-muted); font-size: var(--m-caption); overflow-wrap: anywhere; }
.material-affordance { display: flex; align-items: center; gap: 2px; flex: none; color: var(--pt-muted); font-size: var(--m-caption); }
.material-affordance .ui-icon { width: 16px; height: 16px; }
.material-disclosure[open] .material-affordance .ui-icon { transform: rotate(90deg); }
.material-facts { margin: 8px 0; padding-top: 8px; border-top: 1px solid var(--pt-rule); font-size: var(--m-caption); }
.material-facts > div + div { margin-top: 10px; }
.material-facts dt { margin-bottom: 2px; color: var(--pt-muted); }
.material-facts dd { margin: 0; color: var(--pt-ink); overflow-wrap: anywhere; }
.material-change { flex: none; margin: 0; }
</style>
