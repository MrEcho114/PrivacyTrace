<script setup lang="ts">
defineProps<{ name: 'plus' | 'report' | 'file' | 'arrow-right' }>()
const paths = {
  plus: 'M12 5v14M5 12h14',
  report: 'M8 7h8M8 11h8M8 15h5M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z',
  file: 'M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6M8 14h8M8 17h5',
  'arrow-right': 'M5 12h14m-6-6 6 6-6 6',
}
</script>
<template><svg class="ui-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path :d="paths[name]" /></svg></template>
