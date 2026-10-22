<script setup lang="ts">
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogClose } from 'reka-ui'
import UiIcon from './UiIcon.vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{ title: string; description?: string; initialFocus?: string; variant?: 'bottom' | 'detail' }>(), { variant: 'bottom' })
const emit = defineEmits<{ close: [] }>()

// Element ID preferred by the caller (for example the close button D tests);
// otherwise the sheet's own close control receives the initial focus.
function focusInitial(event: Event) {
  const preferred = props.initialFocus ? document.getElementById(props.initialFocus) : null
  const container = event.target instanceof HTMLElement ? event.target : null
  const target = preferred ?? container?.querySelector<HTMLElement>('.ui-sheet-close')
  if (!target) return
  event.preventDefault()
  target.focus()
}
</script>
<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) emit('close') }">
    <DialogPortal>
      <DialogOverlay class="ui-sheet-overlay" />
      <DialogContent v-bind="$attrs" as="dialog" open aria-modal="true" class="ui-sheet" :class="variant === 'detail' ? 'ui-sheet--detail' : 'ui-sheet--bottom'" @open-auto-focus="focusInitial">
        <div class="ui-sheet-handle" aria-hidden="true" />
        <div class="ui-sheet-head">
          <DialogTitle class="ui-sheet-title">{{ title }}</DialogTitle>
          <DialogClose class="ui-sheet-close" type="button" aria-label="关闭">
            <slot name="close"><UiIcon name="close" /></slot>
          </DialogClose>
        </div>
        <DialogDescription v-if="description" class="ui-sheet-description">{{ description }}</DialogDescription>
        <!-- Empty but present, so aria-describedby never points at a missing node. -->
        <DialogDescription v-else class="ui-sheet-description-empty" />
        <div class="ui-sheet-body"><slot /></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
<style scoped>
/* Shared component: consume the semantic aliases from docs/design/frontend-design-spec-mobile.md
   §11.3. The old token stays as the fallback so desktop and mobile keep their current values
   until the `--ui-*` layer in theme.css is authored; once it exists the alias wins. */
.ui-sheet-overlay { position: fixed; inset: 0; z-index: 100; background: var(--ui-scrim); animation: m-sheet-fade var(--ui-duration-enter) var(--ui-ease-decelerate); }
.ui-sheet {
  position: fixed; inset-inline: 0; bottom: 0; z-index: 101;
  display: flex; flex-direction: column; width: min(100%, 640px); max-height: min(88dvh, 720px);
  margin-inline: auto; padding-inline: env(safe-area-inset-left, 0px) env(safe-area-inset-right, 0px);
  background: var(--ui-surface); color: var(--ui-fg); border: 1px solid var(--ui-border-soft); border-bottom: 0;
  border-radius: var(--ui-radius-sheet) var(--ui-radius-sheet) 0 0; box-shadow: var(--ui-shadow-sheet);
  box-sizing: border-box; animation: m-sheet-rise var(--ui-duration-enter) var(--ui-ease-decelerate);
}
.ui-sheet--detail { animation-name: m-sheet-fade; }
.ui-sheet--detail .ui-sheet-close { order: -1; margin: -10px 0 0 -10px; }
.ui-sheet-handle { flex: none; width: 36px; height: 4px; margin: 10px auto 2px; border-radius: 999px; background: var(--ui-handle); }
.ui-sheet-head { flex: none; display: flex; align-items: flex-start; gap: var(--space-12); padding: 4px var(--m-gutter) 12px; }
.ui-sheet-title { flex: 1; min-width: 0; margin: 0; font-family: var(--ui-font-display); font-size: var(--m-font-title); font-weight: 600; line-height: 1.35; }
.ui-sheet-close {
  display: grid; place-items: center; flex: none; width: var(--ui-touch); height: var(--ui-touch);
  margin: -10px -10px 0 0; padding: 0; border: 0; border-radius: 999px; background: transparent;
  color: var(--ui-fg); touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.ui-sheet-close:active { background: var(--ui-state-press); }
@media (hover: hover) and (pointer: fine) { .ui-sheet-close:hover { background: var(--ui-state-hover); } }
.ui-sheet-description { flex: none; margin: 0; padding: 0 var(--m-gutter) 12px; color: var(--ui-muted); font-size: var(--m-caption); line-height: 1.5; }
.ui-sheet-description-empty { display: none; }
.ui-sheet-body {
  flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
  padding: 0 var(--m-gutter) max(var(--m-gutter), env(safe-area-inset-bottom, 0px));
}
.ui-sheet--detail {
  inset: 0; width: 100%; max-width: none; max-height: none; height: 100dvh;
  padding-top: env(safe-area-inset-top, 0px); border: 0; border-radius: 0; box-shadow: none;
}
/* Motion contract (docs/design/frontend-round2-android-pioneer.md §6): the sheet
   enters with a short, decelerating rise; reduced motion renders it immediately.
   No height/width animation, so the dialog layout is final on the first frame. */
@keyframes m-sheet-rise {
  from { opacity: .01; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes m-sheet-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .ui-sheet-overlay, .ui-sheet { animation: none; }
}
</style>
