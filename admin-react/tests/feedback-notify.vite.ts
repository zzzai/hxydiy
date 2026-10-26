import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins:[react(),{name:'feedback-isolated',configureServer(server){server.middlewares.use((request,response,next)=>{
    const url=new URL(request.url || '/', 'http://localhost');
    if(url.pathname.startsWith('/api/')){response.statusCode=403;response.end('Isolated fixture denies real API access');return;}
    if(url.pathname.startsWith('/technician/')) request.url='/tests/feedback-notify.html'+url.search;
    next();
  });}}],
  cacheDir:path.resolve('../output/takeover-feedback/vite-cache'),
  optimizeDeps:{entries:['tests/feedback-notify.html']},
  server:{host:'127.0.0.1',port:18429,strictPort:true,hmr:false},
});
