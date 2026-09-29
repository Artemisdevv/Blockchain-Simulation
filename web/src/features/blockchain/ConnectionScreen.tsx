import { useState, useEffect, useRef } from "react";
import { ArrowRight, CircleCheck, Database, Loader2, LockKeyhole, Network, QrCode, Server, Zap, Copy, Check } from "lucide-react";
import QRCode from "qrcode";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchBalance, type Connection } from "@/lib/api-client";

export function ConnectionScreen({ onConnect }: { onConnect: (connection: Connection) => void }) {
  const [url, setUrl] = useState("http://localhost:6001");
  const [token, setToken] = useState("demo-token-alice");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showQr, setShowQr] = useState(false);
  const [copied, setCopied] = useState(false);
  const qrCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const currentShareUrl = `${window.location.origin}/?url=${encodeURIComponent(
    url,
  )}&token=${encodeURIComponent(token)}`;

  // Generate QR Code when modal is opened or URL/Token changes
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

  const handleConnect = async (targetUrl: string, targetToken: string) => {
    if (!targetUrl.trim() || !targetToken.trim()) {
      setError("Enter both the node API URL and Bearer token.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const conn: Connection = { url: targetUrl.trim(), token: targetToken.trim() };
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
              Connect to your blockchain node.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
              Inspect consensus mechanisms, validator selection probabilities, mempool transactions,
              and live slashing events in real time.
            </p>

            <div className="mt-8 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                1-Click Preset Connections
              </div>
              <div className="flex flex-wrap gap-3">
                <Button
                  type="button"
                  variant="default"
                  onClick={() => {
                    setUrl("http://localhost:6001");
                    setToken("demo-token-alice");
                    handleConnect("http://localhost:6001", "demo-token-alice");
                  }}
                  className="flex items-center gap-2 shadow-md"
                >
                  <Zap className="h-4 w-4 text-warning" />
                  Connect to Peer Alice (:6001)
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setUrl("http://localhost:6011");
                    setToken("demo-token-bob");
                    handleConnect("http://localhost:6011", "demo-token-bob");
                  }}
                  className="flex items-center gap-2"
                >
                  <Server className="h-4 w-4 text-primary" />
                  Connect to Peer Bob (:6011)
                </Button>
              </div>
            </div>

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

          <form
            className="panel p-6 sm:p-7"
            onSubmit={(event) => {
              event.preventDefault();
              handleConnect(url, token);
            }}
          >
            <div className="mb-6">
              <h2 className="text-lg font-semibold">Node Credentials</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Custom API endpoint & auth token.
              </p>
            </div>

            <div className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="node-url">Node API URL</Label>
                <Input
                  id="node-url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="http://localhost:6001"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="node-token">Bearer Token</Label>
                <Input
                  id="node-token"
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="demo-token-alice"
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  Default preset: <code className="rounded bg-muted px-1 py-0.5">demo-token-alice</code>
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
