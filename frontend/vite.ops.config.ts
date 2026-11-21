import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Отдельный бандл модуля «Операции»: dist-ops/ops.js (ES-модуль с mount/unmount).
// Не входит в основную сборку; сервер отдаёт его только admin через /api/ops/ui/bundle.js.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: 'dist-ops',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'ops/main.tsx',
      formats: ['es'],
      fileName: () => 'ops.js',
    },
  },
})
