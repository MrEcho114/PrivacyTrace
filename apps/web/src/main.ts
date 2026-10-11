import { createApp } from 'vue'
import App from './WorkflowApp.vue'
import './style.css'
import './workbench.css'

const app = createApp(App)
app.config.errorHandler = (err) => {
  console.error('Captured Vue error:', err)
}
app.mount('#app')
