import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 55173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:58000',
        changeOrigin: true,
      },
      '/healthz': {
        target: 'http://127.0.0.1:58000',
        changeOrigin: true,
      },
      '/readyz': {
        target: 'http://127.0.0.1:58000',
        changeOrigin: true,
      },
    },
  },
});
