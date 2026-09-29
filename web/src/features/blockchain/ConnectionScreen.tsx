import { useState, useEffect, useRef } from "react";
import { ArrowRight, CircleCheck, Database, Loader2, LockKeyhole, Network, QrCode, Settings2, Copy, Check } from "lucide-react";
import QRCode from "qrcode";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchBalance, type Connection } from "@/lib/api-client";
import { NODE_REGISTRY, resolveNodeByName } from "@/lib/node-registry";

const KNOWN_NAMES = Object.keys(NODE_REGISTRY);

export function ConnectionScreen({ onConnect }: { onConnect: (connection: Connection) => void }) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showQr, setShowQr] = useState(false);
  const [copied, setCopied] = useState(false);
  const qrCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Advanced/custom connection, for spectators or non-standard deployments
  // that aren't in NODE_REGISTRY. Hidden by default - the primary flow only
  // asks for a name, mirroring start_peer.py's "Enter Name" prompt.
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advUrl, setAdvUrl] = useState("");
  const [advToken, setAdvToken] = useState("");
  const [advWsUrl, setAdvWsUrl] = useState("");

  const trimmedName = name.trim().toLowerCase();
  const shareUrl = new URL(window.location.origin);
  if (KNOWN_NAMES.includes(trimmedName)) {
    shareUrl.searchParams.set("node", trimmedName);
  } else if (advUrl.trim() && advToken.trim()) {
    shareUrl.searchParams.set("url", advUrl.trim());
    shareUrl.searchParams.set("token", advToken.trim());
    if (advWsUrl.trim()) shareUrl.searchParams.set("wsUrl", advWsUrl.trim());
  }
  const currentShareUrl = shareUrl.toString();

  useEffect(() => {
    if (showQr && qrCanvasRef.current) {
      QRCode.toCanvas(qrCanvasRef.current, currentShareUrl, {
        width: 180,
        margin: 2,
        color: {
          dark: "#0f172a",
          light: "#ffffff",
        },
      }).catch((err) => console.error("Error generating QR:", err));
    }
  }, [showQr, currentShareUrl]);

  const connectWith = async (conn: Connection) => {
    setLoading(true);
    setError("");
    try {
      await fetchBalance(conn);
      onConnect(conn);
    } catch (err: any) {
      setError(
        err.message ||
          "Failed to connect to node. Make sure Docker container is running (docker compose up -d).",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleJoin = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Enter your node's name (e.g. alice or bob).");
      return;
    }
    const known = resolveNodeByName(name);
    if (!known) {
      setError(
        `Unknown node name '${name.trim()}'. Ask your teammate what name they used, or use Advanced connection below.`,
      );
      return;
    }
    connectWith(known);
  };

  const handleAdvancedConnect = (event: React.FormEvent) => {
    event.preventDefault();
    if (!advUrl.trim() || !advToken.trim()) {
      setError("Enter both the node API URL and Bearer token.");
      return;
    }
    connectWith({
      url: advUrl.trim(),
      token: advToken.trim(),
      ...(advWsUrl.trim() ? { wsUrl: advWsUrl.trim() } : {}),
    });
  };

  const copyShareUrl = () => {
    navigator.clipboard.writeText(currentShareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="min-h-screen bg-background px-5 py-10 sm:px-8 lg:px-12">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl flex-col justify-between">
        <header className="flex items-center justify-between border-b border-border pb-5">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground">
              <Network className="h-5 w-5" />
            </div>
            <div>
              <div className="font-semibold text-foreground">Consensus Console</div>
              <div className="text-xs text-muted-foreground">Blockchain Network Monitor</div>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowQr(!showQr)}
            className="flex items-center gap-2"
          >
            <QrCode className="h-4 w-4 text-primary" />
            Spectator QR Code
          </Button>
        </header>

        {showQr && (
          <div className="my-6 flex flex-col items-center gap-4 rounded-xl border border-primary/30 bg-card p-6 shadow-xl sm:flex-row">
            <div className="rounded-lg bg-white p-2 shadow-inner">
              <canvas ref={qrCanvasRef} />
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <div className="text-sm font-semibold text-foreground">Spectator QR & Direct Link</div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Scan this QR code or copy the link below to open the dashboard live on your mobile device or secondary browser. Automatically connects in Spectator mode!
              </p>
              <div className="flex items-center gap-2 pt-2">
                <Input
                  readOnly
                  value={currentShareUrl}
                  className="font-mono text-xs bg-muted text-muted-foreground"
                />
                <Button variant="secondary" size="sm" onClick={copyShareUrl} className="shrink-0">
                  {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
          </div>
        )}

        <section className="grid items-center gap-14 py-12 lg:grid-cols-[1fr_440px]">
          <div className="max-w-2xl">
            <span className="eyebrow">
              <CircleCheck className="h-3.5 w-3.5" /> Docker Network Ready
            </span>
            <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-tight text-foreground sm:text-5xl">
              Join your blockchain node.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
              Inspect consensus mechanisms, validator selection probabilities, mempool transactions,
              and live slashing events in real time.
            </p>

            <div className="mt-10 grid max-w-xl gap-4 sm:grid-cols-3">
              {[
                [Database, "Chain data", "Inspect every block"],
                [Network, "Peer health", "Track P2P mesh"],
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

          <form className="panel p-6 sm:p-7" onSubmit={handleJoin}>
            <div className="mb-6">
              <h2 className="text-lg font-semibold">Join as your peer</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Enter the name you used when starting your node.
              </p>
            </div>

            <div className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="peer-name">Name</Label>
                <Input
                  id="peer-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="alice"
                  autoFocus
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  Known nodes: {KNOWN_NAMES.join(", ")}
                </p>
              </div>

              {error && (
                <p role="alert" className="text-sm font-medium text-destructive">
                  {error}
                </p>
              )}

              <Button className="w-full" size="lg" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Verifying Connection...
                  </>
                ) : (
                  <>
                    Open Console <ArrowRight />
                  </>
                )}
              </Button>
            </div>

            <div className="mt-5 border-t border-border pt-4">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground"
              >
                <Settings2 className="h-3.5 w-3.5" />
                Advanced: connect by URL (spectators / custom deployments)
              </button>

              {showAdvanced && (
                <form className="mt-4 space-y-4" onSubmit={handleAdvancedConnect}>
                  <div className="space-y-2">
                    <Label htmlFor="node-url">Node API URL</Label>
                    <Input
                      id="node-url"
                      value={advUrl}
                      onChange={(e) => setAdvUrl(e.target.value)}
                      placeholder="http://localhost:6001"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="node-ws-url">Events WebSocket URL (optional)</Label>
                    <Input
                      id="node-ws-url"
                      value={advWsUrl}
                      onChange={(e) => setAdvWsUrl(e.target.value)}
                      placeholder="wss://example.com/events"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="node-token">Bearer Token</Label>
                    <Input
                      id="node-token"
                      type="password"
                      value={advToken}
                      onChange={(e) => setAdvToken(e.target.value)}
                    />
                  </div>
                  <Button className="w-full" variant="outline" size="sm" disabled={loading}>
                    Connect with URL
                  </Button>
                </form>
              )}
            </div>

            <div className="mt-5 flex items-start gap-2 border-t border-border pt-4 text-xs leading-5 text-muted-foreground">
              <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
              Direct Node Connection via REST & Event WebSocket.
            </div>
          </form>
        </section>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border py-5 text-xs text-muted-foreground">
          <span>Consensus Console v1.0</span>
          <span>Blockchain Network Monitor & Consensus Simulator</span>
        </footer>
      </div>
    </main>
  );
}
