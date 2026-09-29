import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ConnectionScreen, type Connection } from "@/features/blockchain/ConnectionScreen";
import { Dashboard } from "@/features/blockchain/Dashboard";

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
