import type { Connection } from "@/lib/api-client";

/**
 * Known node identities for this deployment, keyed by lowercase name -
 * mirrors start_peer.py's "Enter Name" prompt: users identify themselves by
 * name, not by pasting a URL + bearer token. Each entry's URL/token still
 * come from the deployment's env config (Aswin's docker-compose), they're
 * just never typed or shown in the UI.
 */
export const NODE_REGISTRY: Record<string, Connection> = {
  alice: {
    url: import.meta.env["VITE_ALICE_API_URL"] || "/api/alice",
    token: import.meta.env["VITE_ALICE_TOKEN"] || "demo-token-alice",
    wsUrl: import.meta.env["VITE_ALICE_WS_URL"] || undefined,
  },
  bob: {
    url: import.meta.env["VITE_BOB_API_URL"] || "/api/bob",
    token: import.meta.env["VITE_BOB_TOKEN"] || "demo-token-bob",
    wsUrl: import.meta.env["VITE_BOB_WS_URL"] || undefined,
  },
};

export function resolveNodeByName(name: string): Connection | null {
  return NODE_REGISTRY[name.trim().toLowerCase()] ?? null;
}
