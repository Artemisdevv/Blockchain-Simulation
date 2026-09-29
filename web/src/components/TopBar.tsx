import { Button } from '@/components/ui/button'
import { shortKey } from '@/lib/keys'

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.max(0, seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function TopBar({
  connected,
  myPublicKey,
  myBalance,
  epochEndsInSeconds,
  onDisconnect,
}: {
  connected: boolean
  myPublicKey: string | null
  myBalance: number | null
  epochEndsInSeconds: number
  onDisconnect: () => void
}) {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background/95 px-6 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {connected && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-live opacity-75" />
            )}
            <span
              className={`relative inline-flex h-2 w-2 rounded-full ${connected ? 'bg-live' : 'bg-muted-foreground/40'}`}
            />
          </span>
          <span className="text-sm font-medium">{connected ? 'Live' : 'Disconnected'}</span>
        </div>
        {myPublicKey && (
          <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">
            you: {shortKey(myPublicKey)}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {connected && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Next block in</span>
            <span className="font-mono tabular-nums text-foreground">
              {formatCountdown(epochEndsInSeconds)}
            </span>
          </div>
        )}
        {myBalance !== null && (
          <div className="text-sm">
            <span className="text-muted-foreground">Balance </span>
            <span className="font-mono font-medium tabular-nums">{myBalance}</span>
          </div>
        )}
        <Button variant="ghost" size="sm" onClick={onDisconnect}>
          Disconnect
        </Button>
      </div>
    </header>
  )
}
