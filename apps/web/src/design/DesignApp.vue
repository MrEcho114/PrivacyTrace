<script setup lang="ts">
import MissionShell from './MissionShell.vue'
import ReportExample from './ReportExample.vue'
import ComponentGallery from './ComponentGallery.vue'
import { fixtureFor } from './model'
const params = new URLSearchParams(location.search)
const gallery = params.get('view') === 'components'
const report = fixtureFor(params.get('state'))
</script>
<template><MissionShell :gallery="gallery"><ComponentGallery v-if="gallery" /><ReportExample v-else :report="report" /></MissionShell></template>
