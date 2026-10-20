<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue';
import { cancel, inspectSelected, modelStatus, configureModel, clearModel, checkServer, uploadSelected, refreshUpload, deleteUpload, forgetUpload, type UploadStatus, type ProbeResult, type ModelConfigStatus, type ServerHealth } from '../../tauri-plugin/guest-js/index';

const busy = ref(false);
const status = ref('尚未读取');
const result = ref<ProbeResult | null>(null);
const model = ref<ModelConfigStatus>({ configured: false, endpoint: null });
const modelMessage = ref('正在读取配置状态');
const healthBusy = ref(false);
const health = ref<ServerHealth | null>(null);
const healthMessage = ref('尚未检查服务');
const uploadResult = ref<UploadStatus | null>(null);
const uploadMessage = ref('尚未上传');
async function transfer(action: () => Promise<UploadStatus>) {
  if (busy.value) return;
  busy.value = true;
  uploadResult.value = null;
  uploadMessage.value = '等待原生确认、准备材料或服务响应；可停止当前操作';
  try {
    uploadResult.value = await action();
    const current = uploadResult.value;
    uploadMessage.value = current.state === 'SERVER_CONFIRMED'
      ? '服务器已确认完整包集合（尚未开始分析）'
      : current.state === 'LOCAL_ACCESS_FORGOTTEN'
        ? '本机访问材料已清除；远端材料是否删除仍未知，旧草稿无法找回'
      : current.state === 'DELETED'
        ? (current.cleanupPending ? '服务器已撤销访问，物理清理仍待完成' : '服务器已确认删除')
        : '服务器尚未确认上传；没有自动重传';
  } catch (error) {
    const code = typeof error === 'string' ? error : 'NATIVE_PROBE_FAILED';
    uploadMessage.value = `${code}；上传结果未确认，可刷新对应实例。停止传输不会自动删除远端材料。`;
  } finally { busy.value = false; }
}
async function checkHealth() {
  if (busy.value) return;
  busy.value = true;
  healthBusy.value = true;
  health.value = null;
  healthMessage.value = '等待原生输入或服务响应';
  await nextTick();
  window.scrollTo(0, document.documentElement.scrollHeight);
  try {
    health.value = await checkServer();
    healthMessage.value = '收到健康响应（仅连通性）';
  } catch (error) {
    healthMessage.value = typeof error === 'string' ? error : 'NATIVE_PROBE_FAILED';
  } finally {
    busy.value = false;
    healthBusy.value = false;
    await nextTick();
    window.scrollTo(0, document.documentElement.scrollHeight);
  }
}
async function settings(action: () => Promise<ModelConfigStatus>) {
  if (busy.value) return;
  busy.value = true;
  try {
    model.value = await action();
    modelMessage.value = model.value.configured ? '模型已配置（仅本机）' : '未配置模型';
  } catch (error) {
    modelMessage.value = typeof error === 'string' ? error : 'NATIVE_PROBE_FAILED';
    if (modelMessage.value !== 'CANCELLED' && modelMessage.value !== 'INVALID_MODEL_CONFIG') {
      model.value = { configured: false, endpoint: null };
    }
  } finally { busy.value = false; }
}
onMounted(() => settings(modelStatus));
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
    <p>本机读取：选择应用后，在原生窗口确认读取当前 base 和全部已安装 splits，仅显示摘要。上传请使用下方独立入口。</p>
    <button :disabled="busy" @click="read">选择应用并读取</button>
    <button :disabled="!busy" @click="stop">取消当前操作</button>
    <p role="status">{{ status }}</p>
    <section v-if="result" aria-label="所选应用摘要">
      <h2>{{ result.packageName }}</h2>
      <p>版本 {{ result.versionCode }} · {{ result.parts.length }} 个包 · {{ result.totalBytes }} 字节</p>
      <p>本机集合 SHA-256</p><code>{{ result.localSetSha256 }}</code>
      <article v-for="part in result.parts" :key="part.splitName ?? 'base'">
        <h3>{{ part.splitName ?? 'base' }} · {{ part.bytes }} 字节</h3><code>{{ part.sha256 }}</code>
      </article>
    </section>
    <section aria-label="本机模型配置">
      <h2>本机模型配置</h2>
      <p>Key 在原生窗口输入并加密保存，不返回网页。本实验不调用模型。</p>
      <button :disabled="busy" @click="settings(configureModel)">设置模型配置</button>
      <button :disabled="busy" @click="settings(clearModel)">删除模型配置</button>
      <p role="status">{{ modelMessage }}</p>
      <p v-if="model.endpoint" class="model-endpoint">{{ model.endpoint }}</p>
    </section>
    <section aria-label="分析服务健康检查">
      <h2>分析服务健康检查</h2>
      <p>仅访问原生窗口中输入的 HTTPS 服务健康接口，不上传材料或发送模型 Key。健康响应不代表兼容或允许上传。</p>
      <button :disabled="busy" @click="checkHealth">检查分析服务</button>
      <button :disabled="!healthBusy" @click="stop">取消服务检查</button>
      <p role="status">{{ healthMessage }}</p>
      <p v-if="health" class="server-origin">{{ health.origin }} · 版本 {{ health.version }} · {{ health.mode }} · {{ health.scope }}</p>
    </section>
    <section aria-label="应用安全上传">
      <h2>应用安全上传</h2>
      <p>在原生窗口选择实例和应用，确认全部已安装包与长期保留规则后上传。仅上传所选应用；分析和政策交互尚未接入此验证壳。</p>
      <button :disabled="busy" @click="transfer(uploadSelected)">选择应用并确认上传</button>
      <button :disabled="busy" @click="transfer(refreshUpload)">刷新上传确认</button>
      <button :disabled="busy" @click="transfer(deleteUpload)">删除远端材料</button>
      <button :disabled="busy" @click="transfer(forgetUpload)">清除本机访问材料</button>
      <button :disabled="!busy" @click="stop">停止当前操作</button>
      <p role="status">{{ uploadMessage }}</p>
      <p v-if="uploadResult" class="server-origin">{{ uploadResult.origin }} · {{ uploadResult.state }}</p>
    </section>
  </main>
</template>

<style>
body { margin: 0; color: #18201e; background: #fff; font: 1rem/1.6 sans-serif; }
main { padding: calc(1.25rem + env(safe-area-inset-top)) 1.25rem calc(2rem + env(safe-area-inset-bottom)); max-width: 40rem; margin: auto; }
h1 { font-size: 1.5rem; } h2, h3 { font-size: 1rem; overflow-wrap: anywhere; }
button { font: inherit; padding: .6rem; margin: .25rem .4rem .25rem 0; min-height: 3rem; }
code { display: block; overflow-wrap: anywhere; user-select: text; }
.model-endpoint, .server-origin { overflow-wrap: anywhere; }
[role='status'] { overflow-wrap: anywhere; }
</style>
