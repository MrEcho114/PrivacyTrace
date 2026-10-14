<script setup lang="ts">
defineProps<{ label: string; id: string; help?: string; error?: string }>()
</script>
<template><div class="ui-field"><label :for="id">{{ label }}</label><slot :describedby="error || help ? id + '-help' : undefined" /><p v-if="error || help" :id="id + '-help'" class="field-help" :class="{ 'error-text': error }">{{ error || help }}</p></div></template>
