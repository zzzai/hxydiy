import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react(), {
    name: 'technician-test-entry',
    configureServer(server) {
      server.middlewares.use((request, _response, next) => {
        if (request.url?.split('?')[0].startsWith('/technician/')) request.url = '/tests/technician-wecom.html';
        next();
      });
    },
  }],
  cacheDir: '.test-vite-cache',
  server: { host: '127.0.0.1', port: 18335, strictPort: true, hmr: false },
});
