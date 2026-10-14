import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

const app = createApp(App)
app.config.errorHandler = (err) => {
  console.error('Captured Vue error:', err)
}
app.mount('#app')
