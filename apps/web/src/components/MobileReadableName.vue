<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, useTemplateRef, watch } from 'vue'

const props = defineProps<{ value: string }>()
const id = useId()
const text = useTemplateRef<HTMLElement>('text')
const expanded = ref(false)
const overflowing = ref(false)
let observer: ResizeObserver | undefined
function measure() {
  if (!expanded.value && text.value) overflowing.value = text.value.scrollHeight > text.value.clientHeight + 1
}
watch(text, element => {
  observer?.disconnect()
  if (!element) return
  observer = new ResizeObserver(measure)
  observer.observe(element)
  measure()
}, { flush: 'post' })
watch(() => props.value, () => {
  expanded.value = false
  void nextTick(measure)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="m-readable-name">
    <p :id="id" ref="text" class="m-readable-name-text" :class="{ expanded }">{{ value }}</p>
    <button v-if="overflowing" type="button" :aria-expanded="expanded" :aria-controls="id" @click="expanded = !expanded">{{ expanded ? '收起名称' : '展开完整名称' }}</button>
  </div>
</template>

<style scoped>
.m-readable-name { min-width: 0; }
.m-readable-name .m-readable-name-text { margin: 0; font: inherit; color: inherit; line-height: 1.5; overflow-wrap: anywhere; }
.m-readable-name-text:not(.expanded) { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.m-readable-name button { min-width: var(--mt-touch); min-height: var(--mt-touch); padding: 4px 0; border: 0; border-radius: var(--mt-radius-control); background: transparent; color: var(--mt-fg-2); font-family: var(--mt-font-sans); font-size: var(--mt-text-caption); line-height: 1.5; text-align: left; }
</style>
