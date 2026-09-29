import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

export const shortKey = (value: string, left = 10, right = 7) =>
  `${value.replaceAll("\n", "").slice(0, left)}…${value.replaceAll("\n", "").slice(-right)}`;
export const formatTime = (value: number) =>
  new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
    new Date(value > 1e12 ? value : value * 1000),
  );

export function CopyValue({ value, compact = false }: { value: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="inline-flex min-w-0 items-center gap-1 font-mono text-xs">
      <span className="truncate">{compact ? shortKey(value) : value}</span>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 shrink-0"
        aria-label="Copy value"
        title="Copy value"
        onClick={() => {
          void navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        }}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </span>
  );
}
