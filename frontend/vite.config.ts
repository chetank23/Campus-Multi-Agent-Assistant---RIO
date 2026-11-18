import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      // Proxy API calls to backend during development.
      // This puts the frontend and API on the same origin (localhost:5173),
      // so the httpOnly refresh_token cookie works without CORS issues.
      proxy: {
        '/api': {
          target: env.VITE_API_BASE_URL || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
      },
    },
    build: {
      chunkSizeWarningLimit: 600,
      rollupOptions: {
        output: {
          manualChunks(id) {
            const normalized = id.replace(/\\/g, '/');
            if (normalized.includes('/node_modules/')) {
              if (normalized.includes('/jspdf') || normalized.includes('/jspdf-autotable')) {
                return 'vendor-jspdf';
              }
              if (normalized.includes('/lucide-react/')) {
                return 'vendor-icons';
              }
              if (normalized.includes('/@tanstack/')) {
                return 'vendor-query';
              }
              if (
                normalized.includes('/react/') ||
                normalized.includes('/react-dom/') ||
                normalized.includes('/react-router/') ||
                normalized.includes('/react-router-dom/')
              ) {
                return 'vendor-react';
              }
              if (normalized.includes('/axios/')) {
                return 'vendor-axios';
              }
            }
          },
        },
      },
    },
  };
});
