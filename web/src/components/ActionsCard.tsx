import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, ApiError } from '@/lib/api'
import type { Connection } from '@/lib/connection'

export function ActionsCard({ conn, onActionComplete }: { conn: Connection; onActionComplete: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Actions</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="send">
          <TabsList className="w-full">
            <TabsTrigger value="send" className="flex-1">
              Send
            </TabsTrigger>
            <TabsTrigger value="stake" className="flex-1">
              Stake
            </TabsTrigger>
          </TabsList>
          <TabsContent value="send">
            <SendForm conn={conn} onDone={onActionComplete} />
          </TabsContent>
          <TabsContent value="stake">
            <StakeForm conn={conn} onDone={onActionComplete} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

function SendForm({ conn, onDone }: { conn: Connection; onDone: () => void }) {
  const [receiver, setReceiver] = useState('')
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.sendTransaction(conn, receiver, Number(amount))
      toast.success('Transaction broadcast')
      setReceiver('')
      setAmount('')
      onDone()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Failed to send')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 pt-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="receiver">Receiver (name or public key)</Label>
        <Input id="receiver" value={receiver} onChange={(e) => setReceiver(e.target.value)} required />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="amount">Amount</Label>
        <Input
          id="amount"
          type="number"
          min="0"
          step="any"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="font-mono"
          required
        />
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? 'Sending...' : 'Send'}
      </Button>
    </form>
  )
}

function StakeForm({ conn, onDone }: { conn: Connection; onDone: () => void }) {
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const result = await api.stake(conn, Number(amount))
      if (result.ok) {
        toast.success(
          result.creating_block_in_seconds
            ? `Staked - block due in ${result.creating_block_in_seconds}s if you win`
            : 'Staked',
        )
        setAmount('')
        onDone()
      } else {
        toast.error(result.error ?? 'Stake rejected')
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Failed to stake')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 pt-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="stake-amount">Amount to stake</Label>
        <Input
          id="stake-amount"
          type="number"
          min="1"
          step="1"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="font-mono"
          required
        />
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? 'Staking...' : 'Stake'}
      </Button>
    </form>
  )
}
