import { ShieldAlert, X } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { shortKey } from '@/lib/keys'
import type { SlashEvent } from '@/hooks/useNetworkState'

export function SlashAlert({ slash, onDismiss }: { slash: SlashEvent; onDismiss: () => void }) {
  return (
    <Alert variant="destructive" className="relative animate-in fade-in slide-in-from-top-2">
      <ShieldAlert className="h-4 w-4" />
      <AlertTitle>Malicious node caught - double-sign detected</AlertTitle>
      <AlertDescription>
        Node <span className="font-mono">{shortKey(slash.creator)}</span> was slashed at block
        position {slash.blockPos}. Its stake for that block is forfeit and the block is marked
        invalid - the consensus fix from issue #3 catching a real attack live.
      </AlertDescription>
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-3 right-3 h-6 w-6"
        onClick={onDismiss}
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </Alert>
  )
}
