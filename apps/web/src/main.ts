import { createApp } from 'vue'
import WorkflowApp from './WorkflowApp.vue'
import ExistingReports from './App.vue'
import MobileApp from './mobile/MobileApp.vue'
import { installVisualViewportInset } from './mobile/viewport'
import { isTauri } from '@tauri-apps/api/core'
import './theme.css'
import './style.css'
import './workbench.css'

// Exported replay packages open directly into their read-only report browser.
const offline = document.querySelector('meta[name="privacytrace-presentation"]')?.getAttribute('content') === 'offline'
const disposeViewportInset = installVisualViewportInset()
if (import.meta.hot) import.meta.hot.dispose(() => disposeViewportInset())
const tauri = isTauri()
// Mobile shell token scope (docs/design/frontend-design-spec-mobile.md §11): 共享组件与
// round2 旧变量只在 body.is-mobile-app 下重映射到 --mt-*，桌面根保持 Pioneer。浏览器
// harness 不经过这里，MobileApp 自己再挂一次兜底。
if (tauri) document.body.classList.add('is-mobile-app')
const app = createApp(offline ? ExistingReports : tauri ? MobileApp : WorkflowApp)
app.config.errorHandler = (err) => {
  console.error('Captured Vue error:', err)
}
app.mount('#app')
