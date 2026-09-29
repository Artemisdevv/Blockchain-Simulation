import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

// Every SECP256k1 SPKI public key starts with the same 32 base64 chars of DER
// header, so the distinguishing part is what follows.
const DER_HEADER_LEN = 32;

export const normKey = (value: string) => value.replace(/\s+/g, "");

export const shortKey = (value: string, left = 10, right = 7) => {
  if (!value) return "";
  const clean = value
    .replace(/-----BEGIN [^-]+-----/g, "")
    .replace(/-----END [^-]+-----/g, "")
    .replace(/\s+/g, "");
  if (clean.length === 0) return value.slice(0, left);
  const body = clean.length > DER_HEADER_LEN + left + right ? clean.slice(DER_HEADER_LEN) : clean;
  return `${body.slice(0, left)}…${body.slice(-right)}`;
};
export const formatTime = (value: number) =>
  new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
    new Date(value > 1e12 ? value : value * 1000),
  );

export function CopyValue({ value, compact = false }: { value: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <span
      className={`${
        compact ? "inline-flex" : "flex w-full"
      } min-w-0 items-center gap-1 font-mono text-xs`}
    >
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
