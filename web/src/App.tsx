import { useState } from 'react'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ActionsCard } from '@/components/ActionsCard'
import { ChainExplorer } from '@/components/ChainExplorer'
import { ConnectScreen } from '@/components/ConnectScreen'
import { PeersList } from '@/components/PeersList'
import { SlashAlert } from '@/components/SlashAlert'
import { StakersLeaderboard } from '@/components/StakersLeaderboard'
import { TopBar } from '@/components/TopBar'
import { useNetworkState } from '@/hooks/useNetworkState'
import { clearConnection, loadConnection, saveConnection, type Connection } from '@/lib/connection'

function Dashboard({ conn, onDisconnect }: { conn: Connection; onDisconnect: () => void }) {
  const { state, refresh } = useNetworkState(conn)
  const [dismissedSlashAt, setDismissedSlashAt] = useState<number | null>(null)

  const slashedCreators = new Set(
    state.lastSlash && dismissedSlashAt !== state.lastSlash.at ? [state.lastSlash.creator] : [],
  )

  return (
    <div className="min-h-svh bg-background">
      <TopBar
        connected={state.connected}
        myPublicKey={state.myPublicKey}
        myBalance={state.myBalance}
        epochEndsInSeconds={state.epochEndsInSeconds}
        onDisconnect={onDisconnect}
      />

      <main className="mx-auto flex max-w-6xl flex-col gap-6 p-6">
        {state.error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {state.error}
          </div>
        )}

        {state.lastSlash && dismissedSlashAt !== state.lastSlash.at && (
          <SlashAlert slash={state.lastSlash} onDismiss={() => setDismissedSlashAt(state.lastSlash!.at)} />
        )}

        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">Chain</h2>
          <ChainExplorer blocks={state.blocks} myPublicKey={state.myPublicKey} slashedCreators={slashedCreators} />
        </section>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <StakersLeaderboard stakers={state.stakers} myPublicKey={state.myPublicKey} />
          </div>
          <ActionsCard conn={conn} onActionComplete={refresh} />
        </div>

        <PeersList peers={state.peers} />
      </main>
    </div>
  )
}

export default function App() {
  const [conn, setConn] = useState<Connection | null>(() => loadConnection())

  function handleConnect(c: Connection) {
    saveConnection(c)
    setConn(c)
  }

  function handleDisconnect() {
    clearConnection()
    setConn(null)
  }

  return (
    <TooltipProvider>
      {conn ? <Dashboard conn={conn} onDisconnect={handleDisconnect} /> : <ConnectScreen onConnect={handleConnect} />}
      <Toaster />
    </TooltipProvider>
  )
}
