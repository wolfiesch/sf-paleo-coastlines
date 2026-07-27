import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // `public/` holds nothing but the multi-gigabyte generated data tree. When
  // VITE_DATA_BASE_URL points the app at a bucket or CDN, copying 117k local
  // tiles (or their LFS pointer stubs) into dist is pure waste, so skip it.
  publicDir: loadEnv(mode, process.cwd(), 'VITE_').VITE_DATA_BASE_URL ? false : 'public',
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
}))
