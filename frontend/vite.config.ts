/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'

// Fills the absolute social-share URLs in index.html from VITE_SITE_URL (e.g. https://risk.example.com). Empty = relative URLs.
const siteUrl = (): Plugin => ({
  name: 'site-url',
  transformIndexHtml: (html) => html.replaceAll('__SITE_URL__', (process.env.VITE_SITE_URL ?? '').replace(/\/$/, '')),
})

export default defineConfig({
  plugins: [react(), siteUrl()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], css: false },
})
