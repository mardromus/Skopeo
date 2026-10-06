import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend so the UI and API share an origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.SKOPEO_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
      "/docs": { target: process.env.SKOPEO_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
      "/openapi.json": { target: process.env.SKOPEO_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});
