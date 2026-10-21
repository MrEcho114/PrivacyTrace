import { build } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'
import { gzipSync } from 'node:zlib'
const root = process.cwd()
const dir = path.resolve('tmp/issue142-probe')
const common = `<label>政策来源<select aria-label="政策来源"><option>官网政策</option><option>应用内政策</option></select></label><details><summary>展开证据</summary><p>UNKNOWN；静态潜在线索；附件未检查。</p></details>`
const fixtures = {
  reka: `<script setup>
import { ref } from 'vue'
import { DialogRoot, DialogTrigger, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription, DialogClose } from 'reka-ui'
const open = ref(false)
</script>
<template><DialogRoot v-model:open="open"><DialogTrigger class="ui-button">打开设置</DialogTrigger><DialogPortal><DialogOverlay class="probe-overlay"/><DialogContent class="probe-dialog"><DialogTitle>设置</DialogTitle><DialogDescription>连接设置保留本机输入。</DialogDescription><DialogClose class="ui-button">关闭</DialogClose>${common}<input aria-label="模型名"/><button>保存</button></DialogContent></DialogPortal></DialogRoot></template>`,
  naive: `<script setup>
import { ref } from 'vue'
import { NConfigProvider, NModal } from 'naive-ui'
const open = ref(false)
const themeOverrides = { common: { primaryColor: 'var(--navy)', primaryColorHover: 'var(--navy-hover)', bodyColor: 'var(--canvas)', cardColor: 'var(--surface)', modalColor: 'var(--surface)', textColorBase: 'var(--ink)', textColor1: 'var(--ink)', textColor2: 'var(--muted)', borderColor: 'var(--border)', borderRadius: 'var(--radius)', fontFamily: 'var(--font-body)' }, Dialog: { color: 'var(--surface)', textColor: 'var(--ink)', titleTextColor: 'var(--ink)', borderRadius: 'var(--radius-panel)', padding: '28px' } }
</script>
<template><NConfigProvider :theme-overrides="themeOverrides"><button class="ui-button" @click="open = true">打开设置</button><NModal v-model:show="open" preset="dialog" title="设置" :show-icon="false" :mask-closable="false" style="width:600px;max-width:calc(100% - 32px)"><p>连接设置保留本机输入。</p><button class="ui-button" @click="open = false">关闭</button>${common}<input aria-label="模型名"/><button>保存</button></NModal></NConfigProvider></template>`
}
fs.writeFileSync(path.join(dir, 'probe.css'), `.probe-overlay{position:fixed;inset:0;background:rgba(44,53,71,.3)}.probe-dialog{position:fixed;inset:0;margin:auto;width:600px;max-width:calc(100% - 32px);height:fit-content;max-height:calc(100dvh - 32px);overflow:auto;padding:28px;border:1px solid var(--border);border-radius:12px;background:var(--surface);color:var(--ink)}label{display:block}input{display:block}h2{font-family:'Noto Serif SC',serif}`)
const result = {}
for (const [name, source] of Object.entries(fixtures)) {
 const target = path.join(dir, name); fs.mkdirSync(target, { recursive: true })
 fs.writeFileSync(path.join(target, 'App.vue'), source)
 fs.writeFileSync(path.join(target, 'index.html'), '<div id="app"></div><script type="module" src="./main.js"></script>')
 fs.writeFileSync(path.join(target, 'main.js'), `import {createApp} from 'vue';import App from './App.vue';import '${path.join(root,'apps/web/src/theme.css').replaceAll('\\','/')}';import '${path.join(root,'apps/web/src/style.css').replaceAll('\\','/')}';import '${path.join(root,'apps/web/src/workbench.css').replaceAll('\\','/')}';import '../probe.css';createApp(App).mount('#app')`)
 await build({configFile:false,root:target,publicDir:path.join(root,'apps/web/public'),plugins:[vue()],resolve:{dedupe:['vue']},build:{outDir:path.join(target,'dist')},logLevel:'error'})
 const files = fs.readdirSync(path.join(target,'dist/assets')).map(file=>{const bytes=fs.readFileSync(path.join(target,'dist/assets',file));return {file,bytes:bytes.length,gzip:gzipSync(bytes).length}})
 result[name]={vueSourceLines:source.split('\n').length,vueSourceBytes:Buffer.byteLength(source),assets:files}
}
fs.writeFileSync(path.join(dir,'build-results.json'),JSON.stringify(result,null,2)+'\n')
console.log(JSON.stringify(result,null,2))
