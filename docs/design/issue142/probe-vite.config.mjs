import vue from '@vitejs/plugin-vue'
import path from 'node:path'
export default { plugins: [vue()], publicDir: path.resolve('apps/web/public'), resolve: { dedupe: ['vue'] } }
