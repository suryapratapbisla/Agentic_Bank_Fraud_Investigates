import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/tg': {
        target: 'http://127.0.0.1:14240',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/tg/, ''),
      },
    },
  },
});
