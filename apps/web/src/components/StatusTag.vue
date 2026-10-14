<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'neutral' | 'info' | 'wait' | 'success' | 'error' }>(), { tone: 'neutral' })
</script>
<template><span class="status-tag" :class="tone"><slot /></span></template>
