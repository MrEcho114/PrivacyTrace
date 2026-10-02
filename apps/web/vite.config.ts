import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000' } },
  },
  preview: { proxy: { '/api': { target: 'http://127.0.0.1:8000' } } },
})
