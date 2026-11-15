import { fileURLToPath } from "node:url";
import { defineConfig, searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";

const cellOrigin = process.env.RW_PLANNING_API_ORIGIN || 'http://127.0.0.1:8000';
const cellProxy = Object.fromEntries(
  ['/api/v1/rank', '/api/v1/cell-at', '/api/v1/cell-context'].map(path => [path, cellOrigin]),
);

export default defineConfig({
  base: process.env.VITE_RELEASE_BASE || "/",
  resolve: {
    alias: process.env.RW_HAZARD_REPLAY_FILE
      ? [{ find: /^\.\/replay\.json$/, replacement: process.env.RW_HAZARD_REPLAY_FILE }]
      : [],
  },
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  preview: { proxy: cellProxy },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    proxy: {
      ...cellProxy,
      "/api/v1/hazard-replay": "http://127.0.0.1:" + (process.env.HAZARD_RUNTIME_PORT || "8000"),
    },
    fs: {
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        fileURLToPath(new URL("../../pipeline/evidence/arcadia-planitia/arcadia-mola-context.png", import.meta.url)),
      ],
    },
    warmup: {
      clientFiles: ["./src/main.tsx"],
    },
  },
  plugins: [react()],
});
