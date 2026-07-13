import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseFromEnv = String(env.VITE_API_BASE_URL || "").trim();
  const apiBase = apiBaseFromEnv || "http://localhost:8082";
  const proxyConfig = {
    target: apiBase,
    changeOrigin: true,
    timeout: 300000,
    proxyTimeout: 300000,
  };

  return {
    server: {
      port: 5173,
      proxy: {
        "/api": proxyConfig,
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
