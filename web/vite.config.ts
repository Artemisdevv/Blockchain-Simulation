// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  vite: {
    server: {
      host: "0.0.0.0",
      port: 8080,
      // Cloudflare Quick Tunnels use a fresh trycloudflare.com hostname.
      allowedHosts: true,
      proxy: {
        "/api/alice": {
          target: process.env.ALICE_API_PROXY_TARGET || "http://localhost:6001",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/alice/, ""),
        },
        "/api/bob": {
          target: process.env.BOB_API_PROXY_TARGET || "http://localhost:6011",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/bob/, ""),
        },
        "/api/peer-setup": {
          target: process.env.PEER_MANAGER_API_PROXY_TARGET || "http://localhost:7001",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/peer-setup/, ""),
        },
        "/api/runtime": {
          target: process.env.PEER_MANAGER_API_PROXY_TARGET || "http://localhost:7001",
          changeOrigin: true,
        },
        "/ws/alice": {
          target: process.env.ALICE_WS_PROXY_TARGET || "http://localhost:6002",
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/ws\/alice/, ""),
        },
        "/ws/bob": {
          target: process.env.BOB_WS_PROXY_TARGET || "http://localhost:6012",
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/ws\/bob/, ""),
        },
        "/ws/runtime": {
          target: process.env.PEER_MANAGER_WS_PROXY_TARGET || "http://localhost:7002",
          changeOrigin: true,
          ws: true,
        },
      },
    },
  },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});
