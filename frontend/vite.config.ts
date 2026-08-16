import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to Django. Keeping both on one origin means the
// session cookie is same-site in development exactly as it is in production —
// so there is no CORS configuration to maintain, and no cross-origin cookie
// behaviour that only shows up after deployment.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
