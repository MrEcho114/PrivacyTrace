<script setup lang="ts">
import UiButton from './UiButton.vue'
defineProps<{ revision: number; draftId: string; busy?: boolean; showRefresh?: boolean }>()
defineEmits<{ new: []; refresh: [] }>()
</script>
<template>
  <div class="material-context">
    <span>材料版本 {{ revision }} · <span class="hash">{{ draftId }}</span></span>
    <!-- Extra identity (application name, version, origin) stays with the caller:
         the mobile shell reuses this component instead of copying it (#144). -->
    <slot />
    <UiButton :disabled="busy" @click="$emit('new')">新建材料版本</UiButton>
    <UiButton v-if="showRefresh" :disabled="busy" variant="quiet" @click="$emit('refresh')">重新读取材料</UiButton>
  </div>
</template>
