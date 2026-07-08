import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseFromEnv = String(env.VITE_API_BASE_URL || "").trim();
  const apiBase = apiBaseFromEnv || "http://localhost:8082";
  const directAgent =
    env.VITE_DIRECT_AGENT === undefined
      ? !apiBaseFromEnv
      : String(env.VITE_DIRECT_AGENT || "").toLowerCase() === "true";
  const agentBase = env.VITE_AGENT_BASE_URL || "http://localhost:8001";
  const proxyTarget = directAgent ? agentBase : apiBase;
  const proxyConfig = {
    target: proxyTarget,
    changeOrigin: true,
    timeout: 300000,
    proxyTimeout: 300000,
  };

  if (directAgent) {
    proxyConfig.rewrite = (path) => path.replace(/^\/api\/travel\/query/, "/agent/query");
  }

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
