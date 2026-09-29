import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Block, Transaction } from "./mock-data";
import { CopyValue, formatTime } from "./utils";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-border py-3 sm:grid-cols-[150px_1fr]">
      <dt className="text-xs font-medium uppercase text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all text-sm">{children}</dd>
    </div>
  );
}

export function TransactionDialog({
  transaction,
  onClose,
}: {
  transaction: Transaction | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={Boolean(transaction)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Transaction details</DialogTitle>
          <DialogDescription>Complete transaction payload from the node.</DialogDescription>
        </DialogHeader>
        {transaction && (
          <dl>
            <Row label="ID">
              <CopyValue value={transaction.id} />
            </Row>
            <Row label="Amount">{transaction.payload} coins</Row>
            <Row label="Sender">
              <CopyValue value={transaction.sender} />
            </Row>
            <Row label="Receiver">
              <CopyValue value={transaction.receiver} />
            </Row>
            <Row label="Timestamp">
              {transaction.ts} · {formatTime(transaction.ts)}
            </Row>
            {transaction.sign !== undefined && (
              <Row label="Signature">
                <CopyValue value={transaction.sign} />
              </Row>
            )}
          </dl>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function BlockDialog({ block, onClose }: { block: Block | null; onClose: () => void }) {
  return (
    <Dialog open={Boolean(block)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[88vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Block details</DialogTitle>
          <DialogDescription>
            Full block representation returned by the chain endpoint.
          </DialogDescription>
        </DialogHeader>
        {block && (
          <dl>
            <Row label="ID">
              <CopyValue value={block.id} />
            </Row>
            <Row label="Previous hash">
              {block.prevHash ? <CopyValue value={block.prevHash} /> : "Genesis block"}
            </Row>
            <Row label="Timestamp">
              {block.ts} · {formatTime(block.ts)}
            </Row>
            <Row label="Creator">
              <CopyValue value={block.creator} />
            </Row>
            <Row label="Staked amount">{block.staked_amt} coins</Row>
            <Row label="Files">
              <code className="font-mono text-xs">{JSON.stringify(block.files)}</code>
            </Row>
            <Row label="Transactions">{block.transactions.length}</Row>
            <Row label="Stakers">
              {block.stakers.length
                ? block.stakers.map((s) => (
                    <div key={s.id} className="mb-2">
                      <CopyValue value={s.id} compact /> · {s.amt} coins ·{" "}
                      <CopyValue value={s.staker} compact />
                    </div>
                  ))
                : "None"}
            </Row>
            <Row label="VRF proof">
              {block.vrf_proof_b64 ? (
                <CopyValue value={block.vrf_proof_b64} />
              ) : (
                "Not applicable (genesis block isn't chosen via VRF)"
              )}
            </Row>
            <Row label="Seed">
              {block.seed ? <CopyValue value={block.seed} /> : "Not applicable (genesis block)"}
            </Row>
            <Row label="Signature">
              <CopyValue value={block.sign} />
            </Row>
          </dl>
        )}
      </DialogContent>
    </Dialog>
  );
}
