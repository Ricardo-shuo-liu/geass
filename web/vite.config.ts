import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist' },
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
  server: {
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8765', ws: true },
      '/api': 'http://127.0.0.1:8765',
    },
  },
});
