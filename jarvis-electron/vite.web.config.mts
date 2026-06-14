import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * Standalone renderer-only dev server (no Electron) — used for visual
 * inspection/preview of the UI in a plain browser. `.mts` so the ESM-only
 * Tailwind plugin loads cleanly. The app guards `window.jarvis`, so it
 * renders fine without the preload bridge.
 */
const root = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  root: resolve(root, 'src/renderer'),
  resolve: { alias: { '@': resolve(root, 'src/renderer/src') } },
  plugins: [react(), tailwindcss()],
  server: {
    port: process.env.PORT ? Number(process.env.PORT) : 5180,
    strictPort: true
  }
})
