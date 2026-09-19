import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import process from "node:process";

const backend = process.env.CLARITYOPS_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: backend,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: backend,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
