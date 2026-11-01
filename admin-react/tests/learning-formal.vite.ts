import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
 plugins:[react(),{name:'isolated-learning',configureServer(server){server.middlewares.use((req,res,next)=>{const url=new URL(req.url||'/','http://localhost');if(url.pathname.startsWith('/technician/'))req.url='/tests/learning-formal.html'+url.search;next();});}}],
 define:{'import.meta.env.VITE_STAFF_LEARNING_ENABLED':'"true"'},
 cacheDir:'../output/learning-formal-vite-cache',
 optimizeDeps:{entries:['tests/learning-formal.html']},
 build:{target:'es2022',outDir:'../output/learning-formal-preview-build',rollupOptions:{input:path.resolve(process.cwd(),'tests/learning-formal.html')}},
 server:{host:'127.0.0.1',port:4242,strictPort:true,hmr:false,proxy:{'/api/v1':'http://127.0.0.1:18229','/__learning_preview__':'http://127.0.0.1:18228'}},esbuild:{target:'es2022'}
});
