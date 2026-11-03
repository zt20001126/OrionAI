import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        input: {
          app: resolve(process.cwd(), "index.html"),
          vrmPreview: resolve(process.cwd(), "vrm-preview.html"),
        },
      },
    },
    server: {
      host: "0.0.0.0",
      allowedHosts: ["orionaihub.ltd", "www.orionaihub.ltd"],
      proxy: {
        "/api": {
          target: env.API_PROXY_TARGET || "http://localhost:8000",
          changeOrigin: false,
        },
      },
    },
  };
});
