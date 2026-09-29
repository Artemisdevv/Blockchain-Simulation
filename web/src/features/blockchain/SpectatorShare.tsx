import { useState } from "react";
import { Check, Copy, Eye, Loader2 } from "lucide-react";
import QRCode from "qrcode";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { createSpectatorLink, type Connection } from "@/lib/api-client";

/**
 * "Share" button for a joined node. Only a node that holds a peer token for the
 * room can mint a read-only spectator link, so the link is created here (after
 * joining) rather than on the join screen.
 */
export function SpectatorShare({
  connection,
  onToast,
}: {
  connection: Connection;
  onToast: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [url, setUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [qr, setQr] = useState("");

  const share = async () => {
    setLoading(true);
    try {
      const link = await createSpectatorLink(connection.token);
      // Rendered up front as an image: the dialog content mounts after `open`, so a
      // canvas ref is not available yet when we would draw into it.
      setQr(await QRCode.toDataURL(link, { width: 180, margin: 2, color: { dark: "#0f172a", light: "#ffffff" } }));
      setUrl(link);
      setCopied(false);
      setOpen(true);
    } catch (err: any) {
      onToast(err.message || "Could not create a spectator link.");
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    void navigator.clipboard.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      <Button variant="outline" onClick={() => void share()} disabled={loading}>
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
        Share spectator link
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Share this room as a spectator</DialogTitle>
            <DialogDescription>
              Anyone with this link can watch the room live, read-only, for 24 hours. They cannot
              send transactions or change anything.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center gap-4">
            {qr && <img src={qr} alt="Spectator link QR code" width={180} height={180} className="rounded-lg bg-white" />}
            <div className="flex w-full items-center gap-2">
              <Input readOnly value={url} className="min-w-0 flex-1 bg-muted font-mono text-xs text-muted-foreground" onFocus={(e) => e.currentTarget.select()} />
              <Button variant="secondary" size="sm" onClick={copy} className="shrink-0">
                {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
