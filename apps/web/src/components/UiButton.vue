<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'primary' | 'secondary' | 'quiet' | 'danger'; busy?: boolean; disabled?: boolean; type?: 'button' | 'submit' }>(), { variant: 'secondary', type: 'button' })
</script>
<template><button :type="type" class="ui-button" :class="variant" :disabled="disabled || busy" :aria-busy="busy || undefined"><slot /><span v-if="busy" aria-hidden="true"> …</span></button></template>
