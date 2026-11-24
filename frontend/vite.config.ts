// truelift SPA build (G15). The build lands in src/truelift/web/, which the FastAPI app serves
// (src/truelift/api/spa.py); it is not committed.
//
// Dev: run the API with TRUELIFT_DEV=1 TRUELIFT_DEV_ORIGINS=http://localhost:5173 on port 8000
// (AGENTS.md), then `npm run dev` and open the printed `dev:` link. The proxy rewrites Host to the
// API's (D12 host allowlist) and keeps the dev Origin, which dev mode allows.
import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const apiPort = process.env.TRUELIFT_API_PORT ?? '8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: fileURLToPath(new URL('../src/truelift/web', import.meta.url)),
    emptyOutDir: true,
    // A chunk-size warning is a failure (frontend-quality.md); routes are lazy-loaded.
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      onwarn(warning, warn) {
        if (warning.code === 'CHUNK_SIZE') throw new Error(warning.message);
        warn(warning);
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
    },
  },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          environment: 'jsdom',
          include: ['src/**/*.test.{ts,tsx}'],
          setupFiles: ['./tests/setup-dom.ts'],
          restoreMocks: true,
        },
      },
      {
        extends: true,
        test: {
          name: 'stub-api',
          environment: 'node',
          include: ['tests/**/*.contract.test.ts'],
          globalSetup: ['./tests/stub-server.global.ts'],
          testTimeout: 20_000,
          hookTimeout: 120_000,
        },
      },
    ],
  },
});
