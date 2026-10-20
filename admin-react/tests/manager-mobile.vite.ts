
import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react(), {
    name: 'manager-isolated-fixture',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const url = new URL(request.url || '/', 'http://localhost');
        if (url.pathname.startsWith('/api/')) {
          response.statusCode = 403; response.setHeader('Content-Type', 'application/json');
          response.end(JSON.stringify({ detail: 'Synthetic preview denies all real API access' })); return;
        }
        if (url.pathname === '/admin/' || url.pathname === '/fixture-left') {
          response.setHeader('Content-Type', 'text/html; charset=utf-8');
          response.end('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><h1>合成离页检查</h1><p id="result"></p><script>document.getElementById("result").textContent="店长会话："+Boolean(localStorage.getItem("hxy_admin_token"))+"；保留技师会话："+Boolean(localStorage.getItem("hxy_technician_token"));</script></html>'); return;
        }
        if (url.pathname.startsWith('/technician/')) request.url = '/tests/manager-mobile.html' + url.search;
        next();
      });
    },
  }],
  cacheDir: path.resolve(process.cwd(), '../output/mobile-manager/vite-cache'),
  optimizeDeps: { entries: ['tests/manager-mobile.html'] },
  server: { host: '127.0.0.1', port: 18420, strictPort: true, hmr: false },
});
