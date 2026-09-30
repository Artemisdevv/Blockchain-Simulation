import { useEffect, useState } from "react";
import Antigravity from "@/components/Antigravity";
import TechText from "@/components/TechText";
import { ArrowRight, CircleCheck, Database, Loader2, LockKeyhole, Network, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchBalance, startRoomPeer, type Connection } from "@/lib/api-client";

export function ConnectionScreen({ onConnect }: { onConnect: (connection: Connection) => void }) {
  const [name, setName] = useState("");
  const [roomId, setRoomId] = useState("");
  const [malicious, setMalicious] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Advanced/custom connection, for spectators or non-standard deployments
  // that aren't in NODE_REGISTRY. Hidden by default - the primary flow only
  // asks for a name, mirroring start_peer.py's "Enter Name" prompt.
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advUrl, setAdvUrl] = useState("");
  const [advToken, setAdvToken] = useState("");
  const [advWsUrl, setAdvWsUrl] = useState("");
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mobileQuery = window.matchMedia("(max-width: 639px)");
    const updateScreenSize = () => setIsMobile(mobileQuery.matches);
    updateScreenSize();
    mobileQuery.addEventListener("change", updateScreenSize);
    return () => mobileQuery.removeEventListener("change", updateScreenSize);
  }, []);

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

  const handleJoin = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Enter your node's name (e.g. alice or bob).");
      return;
    }
    if (!roomId.trim()) {
      setError("Enter a room ID to join.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const peer = await startRoomPeer({
        name: name.trim(),
        room_id: roomId.trim(),
        role: malicious ? "malicious" : "honest",
      });
      const connection: Connection = {
        url: `/api/runtime/${peer.peer_id}`,
        token: peer.token,
        wsUrl: `/ws/runtime/${peer.peer_id}/events`,
      };
      await fetchBalance(connection);
      onConnect(connection);
    } catch (err: any) {
      setError(err.message || "Failed to start the peer. Check that the Compose peer manager is running.");
    } finally {
      setLoading(false);
    }
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

  return (
    <main className="relative isolate min-h-screen overflow-hidden bg-background px-4 py-6 sm:px-8 sm:py-10 lg:px-12">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0"
      >
        <Antigravity
          count={isMobile ? 220 : 1000}
          magnetRadius={8}
          ringRadius={10}
          waveSpeed={0.1}
          waveAmplitude={1}
          particleSize={isMobile ? 0.75 : 1.2}
          lerpSpeed={0.01}
          color="#c3c3c3"
          autoAnimate={false}
          particleVariance={0.4}
          rotationSpeed={0}
          depthFactor={isMobile ? 3 : 10}
          pulseSpeed={3}
          particleShape="sphere"
          fieldStrength={19}
        />
      </div>
      <div className="pointer-events-none relative z-10 mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl flex-col justify-between [&_button]:pointer-events-auto [&_input]:pointer-events-auto [&_label]:pointer-events-auto [&_form]:pointer-events-auto [&_a]:pointer-events-auto sm:min-h-[calc(100vh-5rem)]">
        <header className="flex items-center justify-between border-b border-border pb-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center">
              <img src="/favicon.ico" alt="" className="h-8 w-8 object-contain" />
            </div>
            <div>
              <div className="font-semibold text-foreground">Consensus Console</div>
              <div className="text-xs text-muted-foreground">Blockchain Network Monitor</div>
            </div>
          </div>

        </header>


        <section className="grid items-center gap-8 py-8 sm:gap-14 sm:py-12 lg:grid-cols-[1fr_440px]">
          <div className="max-w-2xl">
            <span className="eyebrow">
              <CircleCheck className="h-3.5 w-3.5" /> Docker Network Ready
            </span>
            <h1 className="mt-4 h-40 w-full max-w-2xl leading-none sm:mt-6 sm:h-[360px]">
              <TechText
                text={`Join Your\nBlockchain Node`}
                fontWeight={700}
                fontSize={isMobile ? 64 : 250}
                align="left"
                reveal="letter"
                dashLength={4}
                dashGap={2}
                specks={15}
                fontFamily=""
                color="#000000"
                accentColor="#000000"
                letterSpacing={-0.05}
                reach={200}
                softness={0.7}
                strokeWidth={1.5}
                speed={1}
                lineStyle="dashed"
                selection
                labels
                sweep
                className="pointer-events-auto"
              />
            </h1>
            <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground sm:mt-5 sm:text-base sm:leading-7">
              Inspect consensus mechanisms, validator selection probabilities, mempool transactions,
              and live slashing events in real time.
            </p>

            <div className="mt-6 hidden max-w-xl gap-4 sm:mt-10 sm:grid sm:grid-cols-3">
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

          <form className="panel p-5 sm:p-7" onSubmit={handleJoin}>
            <div className="mb-5 sm:mb-6">
              <h2 className="text-lg font-semibold">Join as your peer</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Start a PoS peer and join a room on the Compose network.
              </p>
            </div>

            <div className="space-y-4 sm:space-y-5">
              <div className="space-y-2">
                <Label htmlFor="peer-name">Node Name</Label>
                <Input
                  id="peer-name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="your-name"
                  autoFocus
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="room-id">Room ID</Label>
                <Input
                  id="room-id"
                  required
                  value={roomId}
                  onChange={(e) => {
                    setRoomId(e.target.value);
                  }}
                  placeholder="my-room"
                />
              </div>

              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4"
                  checked={malicious}
                  onChange={(e) => setMalicious(e.target.checked)}
                />
                <span>
                  <span className="font-medium">Join as a malicious node</span>
                  <span className="block text-xs text-muted-foreground">
                    Stakes automatically and double-signs conflicting blocks whenever it is elected, so
                    honest nodes can detect and slash it. For the Attack Lab demo.
                  </span>
                </span>
              </label>

              {error && (
                <p role="alert" className="text-sm font-medium text-destructive">
                  {error}
                </p>
              )}
              <Button className="w-full" size="lg" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Starting Peer...
                  </>
                ) : (
                  <>
                    Start PoS Peer <ArrowRight />
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

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-4 text-[11px] text-muted-foreground sm:gap-3 sm:py-5 sm:text-xs">
          <span>Consensus Console v1.0</span>
          <span>Blockchain Network Monitor & Consensus Simulator</span>
        </footer>
      </div>
    </main>
  );
}
