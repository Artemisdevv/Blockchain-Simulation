import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { keysEqual, shortKey } from '@/lib/keys'

export function StakersLeaderboard({
  stakers,
  myPublicKey,
}: {
  stakers: Record<string, number>
  myPublicKey: string | null
}) {
  const entries = Object.entries(stakers).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, amt]) => sum + amt, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Validators this epoch</CardTitle>
        <CardDescription>
          Bar width is win probability - literally amount staked / total staked, the actual PoS
          lottery odds.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {entries.length === 0 && (
          <p className="text-sm text-muted-foreground">No one has staked yet this epoch.</p>
        )}
        {entries.map(([pubkey, amt]) => {
          const pct = total > 0 ? (amt / total) * 100 : 0
          const mine = keysEqual(pubkey, myPublicKey)
          return (
            <div key={pubkey} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-sm">
                <span className="font-mono">
                  {shortKey(pubkey)}
                  {mine && <span className="ml-1.5 text-primary">(you)</span>}
                </span>
                <span className="font-mono tabular-nums text-muted-foreground">
                  {amt} · {pct.toFixed(0)}%
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${mine ? 'bg-primary' : 'bg-accent-foreground/40'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
