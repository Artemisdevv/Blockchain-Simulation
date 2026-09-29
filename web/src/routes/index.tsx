import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ConnectionScreen } from "@/features/blockchain/ConnectionScreen";
import { Dashboard } from "@/features/blockchain/Dashboard";
import type { Connection } from "@/lib/api-client";
import { resolveNodeByName } from "@/lib/node-registry";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Consensus Console — Blockchain Network Monitor" },
      {
        name: "description",
        content:
          "Monitor proof-of-stake consensus, validators, blocks, peers, and pending transactions.",
      },
      { property: "og:title", content: "Consensus Console — Blockchain Network Monitor" },
      {
        property: "og:description",
        content: "A live operations dashboard for proof-of-stake blockchain simulations.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // 1. Check for query parameters for zero-friction auto-connect / spectator mode
    const params = new URLSearchParams(window.location.search);
    const qNode = params.get("node");
    const qUrl = params.get("url");
    const qToken = params.get("token");
    const qWsUrl = params.get("wsUrl");

    let autoConn: Connection | null = null;

    if (qNode) {
      autoConn = resolveNodeByName(qNode);
    }
    if (!autoConn && qUrl && qToken) {
      autoConn = { url: qUrl, token: qToken, ...(qWsUrl ? { wsUrl: qWsUrl } : {}) };
    }

    if (autoConn) {
      window.localStorage.setItem("consensus-console-connection", JSON.stringify(autoConn));
      setConnection(autoConn);
      setHydrated(true);
      return;
    }

    // 2. Fallback to localStorage saved connection
    const saved = window.localStorage.getItem("consensus-console-connection");
    if (saved) {
      try {
        setConnection(JSON.parse(saved) as Connection);
      } catch {
        window.localStorage.removeItem("consensus-console-connection");
      }
    }
    setHydrated(true);
  }, []);

  if (!hydrated) return <div className="min-h-screen bg-background" />;

  if (!connection)
    return (
      <ConnectionScreen
        onConnect={(next) => {
          window.localStorage.setItem("consensus-console-connection", JSON.stringify(next));
          setConnection(next);
        }}
      />
    );

  return (
    <Dashboard
      connection={connection}
      onDisconnect={() => {
        window.localStorage.removeItem("consensus-console-connection");
        setConnection(null);
      }}
    />
  );
}
