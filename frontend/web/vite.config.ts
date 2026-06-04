import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'fs';
import { resolve } from 'path';

// 从 pyproject.toml 读取版本号
function getVersion(): string {
  try {
    const pyprojectPath = resolve(__dirname, '../../pyproject.toml');
    const content = readFileSync(pyprojectPath, 'utf-8');
    const match = content.match(/version\s*=\s*"([^"]+)"/);
    return match ? match[1] : '0.0.0';
  } catch {
    return '0.0.0';
  }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(getVersion()),
  },
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'ws://127.0.0.1:3000',
        ws: true,
      },
    },
  },
});
