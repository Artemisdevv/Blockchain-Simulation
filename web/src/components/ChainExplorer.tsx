import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { keysEqual, shortKey } from '@/lib/keys'
import type { Block } from '@/lib/types'

function BlockCard({
  block,
  index,
  isMine,
  isSlashed,
}: {
  block: Block
  index: number
  isMine: boolean
  isSlashed: boolean
}) {
  return (
    <div className="flex shrink-0 flex-col items-center">
      <Card
        className={`w-56 shrink-0 gap-3 py-4 ${isSlashed ? 'border-destructive/60' : isMine ? 'border-primary/50' : ''}`}
      >
        <CardHeader className="px-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-muted-foreground">#{index}</span>
            {index === 0 ? (
              <Badge variant="secondary">genesis</Badge>
            ) : isSlashed ? (
              <Badge variant="destructive">slashed</Badge>
            ) : isMine ? (
              <Badge className="bg-primary/10 text-primary">you mined this</Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 px-4">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">creator</span>
            <span className="font-mono">{shortKey(block.creator)}</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">staked</span>
            <span className="font-mono tabular-nums">{block.staked_amt}</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">txs</span>
            <span className="font-mono tabular-nums">{block.transactions.length}</span>
          </div>
          <div className="mt-1 border-t pt-2 text-[11px] text-muted-foreground">
            {new Date(block.ts).toLocaleTimeString()}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export function ChainExplorer({
  blocks,
  myPublicKey,
  slashedCreators,
}: {
  blocks: Block[]
  myPublicKey: string | null
  slashedCreators: Set<string>
}) {
  return (
    <div className="flex items-stretch gap-0 overflow-x-auto pb-2">
      {blocks.length === 0 && (
        <p className="text-sm text-muted-foreground">No blocks yet - waiting for genesis.</p>
      )}
      {blocks.map((block, i) => (
        <div key={block.id} className="flex items-center">
          {i > 0 && <div className="h-px w-6 shrink-0 self-center bg-border" aria-hidden />}
          <BlockCard
            block={block}
            index={i}
            isMine={keysEqual(block.creator, myPublicKey)}
            isSlashed={slashedCreators.has(block.creator)}
          />
        </div>
      ))}
    </div>
  )
}
