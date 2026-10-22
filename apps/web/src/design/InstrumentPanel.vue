<script setup lang="ts">
defineProps<{ title: string; label?: string; priority?: boolean }>()
</script>
<template>
  <section class="pt-panel">
    <div v-if="priority" class="pt-priority-stripe" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
    <header class="pt-panel-heading"><h2>{{ title }}</h2><span v-if="label" class="pt-code">{{ label }}</span></header>
    <div class="pt-panel-body"><slot /></div>
  </section>
</template>
