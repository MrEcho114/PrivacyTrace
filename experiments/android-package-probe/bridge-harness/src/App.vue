<script setup lang="ts">
import { ref } from 'vue';
import { cancel, inspectSelected, type ProbeResult } from '../../tauri-plugin/guest-js/index';

const busy = ref(false);
const status = ref('尚未读取');
const result = ref<ProbeResult | null>(null);
async function read() {
  if (busy.value) return;
  busy.value = true;
  result.value = null;
  status.value = '等待原生选择、确认或读取';
  try {
    // Also exercise the real cancel IPC round trip before opening a new native picker.
    await cancel();
    result.value = await inspectSelected();
    status.value = '本机读取完成';
  } catch (error) {
    status.value = typeof error === 'string' ? error : 'NATIVE_PROBE_FAILED';
  } finally { busy.value = false; }
}
async function stop() {
  try { await cancel(); } catch { status.value = 'NATIVE_PROBE_FAILED'; }
}
</script>

<template>
  <main>
    <h1>本机桥接验证</h1>
    <p>实验工具：选择应用后，在原生窗口确认读取当前 base 和全部已安装 splits。仅显示本机摘要，不上传。</p>
    <button :disabled="busy" @click="read">选择应用并读取</button>
    <button :disabled="!busy" @click="stop">取消本次读取</button>
    <p role="status">{{ status }}</p>
    <section v-if="result" aria-label="所选应用摘要">
      <h2>{{ result.packageName }}</h2>
      <p>版本 {{ result.versionCode }} · {{ result.parts.length }} 个包 · {{ result.totalBytes }} 字节</p>
      <p>本机集合 SHA-256</p><code>{{ result.localSetSha256 }}</code>
      <article v-for="part in result.parts" :key="part.splitName ?? 'base'">
        <h3>{{ part.splitName ?? 'base' }} · {{ part.bytes }} 字节</h3><code>{{ part.sha256 }}</code>
      </article>
    </section>
  </main>
</template>

<style>
body { margin: 0; color: #18201e; background: #fff; font: 1rem/1.6 sans-serif; }
main { padding: 1.25rem; max-width: 40rem; margin: auto; }
h1 { font-size: 1.5rem; } h2, h3 { font-size: 1rem; overflow-wrap: anywhere; }
button { font: inherit; padding: .6rem; margin: .25rem .4rem .25rem 0; min-height: 3rem; }
code { display: block; overflow-wrap: anywhere; user-select: text; }
</style>
