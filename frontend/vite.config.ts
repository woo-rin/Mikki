import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 백엔드에 CORS 미들웨어가 없다. 프록시를 쓰면 백엔드를 한 줄도 건드리지 않는다.
    proxy: { '/api': { target: 'http://localhost:7999' } },
  },
  // main.py 가 static/ 이 있으면 / 에 마운트한다. 빌드하면 서버 하나로 게임이 뜬다.
  build: { outDir: '../backend/static', emptyOutDir: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    css: false,
  },
})
