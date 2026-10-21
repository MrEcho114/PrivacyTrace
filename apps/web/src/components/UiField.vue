<script setup lang="ts">
defineProps<{ label: string; id: string; help?: string; error?: string }>()
</script>
<template><div class="ui-field"><label :for="id">{{ label }}</label><slot :describedby="error || help ? id + '-help' : undefined" /><p v-if="error || help" :id="id + '-help'" class="field-help" :class="{ 'error-text': error }">{{ error || help }}</p></div></template>
<style>
/* Keep placeholder hints on the same readable muted token instead of the
   browser default; the default can fall below 4.5:1 on the warm surface. */
.ui-field input::placeholder,
.ui-field textarea::placeholder { color: var(--muted); opacity: 1; }
</style>
