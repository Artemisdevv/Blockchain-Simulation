import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { Connection } from '@/lib/connection'

export function ConnectScreen({ onConnect }: { onConnect: (conn: Connection) => void }) {
  const [apiUrl, setApiUrl] = useState('http://localhost:6000')
  const [token, setToken] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!apiUrl || !token) return
    onConnect({ apiUrl: apiUrl.replace(/\/$/, ''), token: token.trim() })
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Connect to a node</CardTitle>
          <CardDescription>
            Point this dashboard at a running peer's web API. Not a login - each node prints its
            own token to the console on startup.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="apiUrl">Node API URL</Label>
              <Input
                id="apiUrl"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                placeholder="http://localhost:6000"
                className="font-mono text-sm"
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="token">Auth token</Label>
              <Input
                id="token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="printed at peer startup"
                className="font-mono text-sm"
                type="password"
              />
            </div>
            <Button type="submit" className="mt-2">
              Connect
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
