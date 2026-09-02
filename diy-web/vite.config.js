import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    // diy.hexiaoyue.com is served from the domain root, not a /diy/ subpath.
    base: process.env.VITE_BASE_PATH || '/',
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 4180,
        proxy: {
            '/api': 'http://127.0.0.1:8010',
        },
    },
    preview: {
        host: '0.0.0.0',
        port: 4180,
        proxy: {
            '/api': 'http://127.0.0.1:8010',
        },
    },
});
