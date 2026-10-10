import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The API target is configurable so the browser acceptance harness can drive an
// isolated backend instance without editing this file.
const apiTarget = process.env.PRIVACYTRACE_API_ORIGIN || 'http://127.0.0.1:8000'
const devPort = Number(process.env.PRIVACYTRACE_WEB_PORT || 5173)

export default defineConfig({
  plugins: [vue()],
  server: {
    port: devPort,
    strictPort: true,
    proxy: { '/api': { target: apiTarget } },
  },
  preview: { port: devPort, proxy: { '/api': { target: apiTarget } } },
})
