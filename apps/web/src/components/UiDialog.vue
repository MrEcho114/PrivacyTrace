<script setup lang="ts">
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'

defineOptions({ inheritAttrs: false })
defineProps<{ title: string; description: string; initialFocus?: string }>()
const emit = defineEmits<{ close: [] }>()
function focusInitial(event: Event, id?: string) {
  const target = id ? document.getElementById(id) : null
  if (target) { event.preventDefault(); target.focus() }
}
</script>
<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) emit('close') }">
    <DialogPortal>
      <DialogOverlay class="ui-dialog-overlay" />
      <DialogContent v-bind="$attrs" as="dialog" open aria-modal="true" class="ui-dialog"
        @open-auto-focus="focusInitial($event, initialFocus)" @interact-outside.prevent>
        <div class="panel-heading"><DialogTitle>{{ title }}</DialogTitle><slot name="close" /></div>
        <DialogDescription class="field-help">{{ description }}</DialogDescription>
        <slot />
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
