import fs from 'node:fs';
import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  resolve: { dedupe: ['react', 'react-dom'] },
  publicDir: '../diy-web/public',
  plugins: [react(), {
    name: 'coupon-poster-isolated-preview',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const url = new URL(request.url || '/', 'http://localhost');
        if (url.pathname.startsWith('/api/')) {
          response.statusCode = 403; response.end('Preview denies real API access'); return;
        }
        if (url.pathname === '/preview-claim.json') {
          const filename = path.resolve('../output/poster-preview/preview-claim.json');
          response.setHeader('Content-Type', 'application/json; charset=utf-8');
          response.setHeader('Cache-Control', 'no-store');
          if (!fs.existsSync(filename)) { response.statusCode = 404; response.end('{}'); return; }
          response.end(fs.readFileSync(filename)); return;
        }
        if (url.pathname === '/flow') { request.url = '/tests/poster-flow.html'; next(); return; }
        if (url.pathname === '/' || url.pathname === '/preview' || url.pathname.startsWith('/technician/')) request.url = '/tests/coupon-poster.html' + url.search;
        next();
      });
    },
  }],
  cacheDir: '../output/poster-preview/vite-cache',
  server: { host: '127.0.0.1', port: 18443, strictPort: true, hmr: false },
});
