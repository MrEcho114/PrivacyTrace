<script setup lang="ts">
// Bind the public path at runtime: a literal src in the template is treated as a
// build asset by Vite, inlined as a data URI in dev, and blocked by the app CSP
// (`default-src 'self'`, no `img-src data:`). The runtime relative URL keeps the
// single same-origin asset request in dev and in the production build.
const symbolUrl = '/brand/privacy-trace-symbol.svg'
</script>

<template><img class="brand-mark-image" :src="symbolUrl" alt="" aria-hidden="true" decoding="async" draggable="false"></template>

<style scoped>
/* Decorative brand symbol: the surrounding link/bar carries the accessible name.
   The box is owned by the parent (.brand-mark / .brand-icon / .m-appbar-brand),
   so the same asset keeps one size rule per placement. */
.brand-mark-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
</style>
