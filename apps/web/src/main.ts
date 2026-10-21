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
const app = createApp(offline ? ExistingReports : isTauri() ? MobileApp : WorkflowApp)
app.config.errorHandler = (err) => {
  console.error('Captured Vue error:', err)
}
app.mount('#app')
