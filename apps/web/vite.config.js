import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBase = env.VITE_API_BASE_URL || "http://localhost:8082";

  return {
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiBase,
          changeOrigin: true,
          timeout: 300000,
          proxyTimeout: 300000,
        },
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
