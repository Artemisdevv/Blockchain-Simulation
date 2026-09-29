import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { shortKey } from '@/lib/keys'
import type { Peer } from '@/lib/types'

export function PeersList({ peers }: { peers: Peer[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Network</CardTitle>
        <CardDescription>{peers.length} peer{peers.length === 1 ? '' : 's'} known</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {peers.length === 0 && <p className="text-sm text-muted-foreground">No peers discovered yet.</p>}
        {peers.map((peer) => (
          <div
            key={peer.public_key}
            className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
          >
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-live" />
              <span className="font-medium">{peer.name}</span>
            </div>
            <span className="font-mono text-xs text-muted-foreground">
              {peer.host}:{peer.port} · {shortKey(peer.public_key)}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
