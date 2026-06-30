import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "frontend",
  plugins: [react()],
  build: {
    outDir: "../web/static/dist",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, "frontend/src/index.jsx"),
        package: resolve(__dirname, "frontend/src/package.jsx"),
      },
    },
  },
});
