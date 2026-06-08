import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // The deck.gl/luma.gl GPU stack is inherently large; warn only past a
    // realistic ceiling so the build stays clean once chunks are split out.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing vendor libs into their own chunks.
        // Same total bytes, but they cache independently of app code across
        // deploys, and no single chunk dominates the initial parse.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('maplibre-gl')) return 'maplibre'
          if (/deck\.gl|luma\.gl|math\.gl|loaders\.gl|probe\.gl|gl-matrix/.test(id)) return 'deckgl'
          if (/[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return 'react-vendor'
          return undefined
        },
      },
    },
  },
})
