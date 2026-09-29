import { useState } from "react";
import { ArrowRight, CircleCheck, Database, LockKeyhole, Network } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface Connection {
  url: string;
  token: string;
}

export function ConnectionScreen({ onConnect }: { onConnect: (connection: Connection) => void }) {
  const [url, setUrl] = useState("http://localhost:6000");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  return (
    <main className="min-h-screen bg-background px-5 py-10 sm:px-8 lg:px-12">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl flex-col justify-between">
        <header className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground">
            <Network className="h-5 w-5" />
          </div>
          <div>
            <div className="font-semibold text-foreground">Consensus Console</div>
            <div className="text-xs text-muted-foreground">Proof-of-stake network monitor</div>
          </div>
        </header>
        <section className="grid items-center gap-14 py-16 lg:grid-cols-[1fr_440px]">
          <div className="max-w-2xl">
            <span className="eyebrow">
              <CircleCheck className="h-3.5 w-3.5" /> Local simulation ready
            </span>
            <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-tight text-foreground sm:text-5xl">
              Connect to your blockchain node.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
              Point the console at a running peer to inspect consensus, validators, transactions,
              and network health in one place.
            </p>
            <div className="mt-10 grid max-w-xl gap-4 sm:grid-cols-3">
              {[
                [Database, "Chain data", "Inspect every block"],
                [Network, "Peer health", "Track the mesh"],
                [LockKeyhole, "Validator safety", "Surface slashing"],
              ].map(([Icon, title, text]) => {
                const I = Icon as typeof Database;
                return (
                  <div key={String(title)} className="border-l-2 border-border pl-3">
                    <I className="mb-2 h-4 w-4 text-primary" />
                    <div className="text-sm font-medium">{String(title)}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{String(text)}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <form
            className="panel p-6 sm:p-7"
            onSubmit={(event) => {
              event.preventDefault();
              if (!url.trim() || !token.trim()) {
                setError("Enter the node URL and access token.");
                return;
              }
              onConnect({ url: url.trim(), token: token.trim() });
            }}
          >
            <div className="mb-6">
              <h2 className="text-lg font-semibold">Node connection</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Credentials stay in this browser.
              </p>
            </div>
            <div className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="node-url">Node API URL</Label>
                <Input
                  id="node-url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="http://localhost:6000"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="node-token">Bearer token</Label>
                <Input
                  id="node-token"
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste token from peer console"
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  Printed in the peer's terminal when it starts up, e.g.{" "}
                  <code className="rounded bg-muted px-1 py-0.5">
                    Auth token (also in .webapi_token_6000): ...
                  </code>
                  . Running via Docker?{" "}
                  <code className="rounded bg-muted px-1 py-0.5">
                    docker compose logs peer-alice
                  </code>{" "}
                  shows it. See the repo's README for full setup.
                </p>
              </div>
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}
              <Button className="w-full" size="lg">
                Open console <ArrowRight />
              </Button>
            </div>
            <div className="mt-5 flex items-start gap-2 border-t border-border pt-4 text-xs leading-5 text-muted-foreground">
              <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Mock mode is active. No requests will leave this interface.
            </div>
          </form>
        </section>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border py-5 text-xs text-muted-foreground">
          <span>Consensus Console v0.9</span>
          <span>REST simulation · 2.5s refresh cadence</span>
        </footer>
      </div>
    </main>
  );
}
