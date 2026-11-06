import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const isolationHeaders = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
  "Cross-Origin-Resource-Policy": "same-origin",
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    headers: isolationHeaders,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8787",
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    headers: isolationHeaders,
  },
  build: {
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 4096,
  },
  optimizeDeps: {
    // The WebGPU build of onnxruntime-web must stay in the browser condition.
    include: ["@huggingface/transformers"],
  },
});
