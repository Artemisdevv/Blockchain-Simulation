// PEM public keys are long and multi-line - nobody wants to read one.
// A short fingerprint (last 8 hex-ish chars of the key body) is enough to
// tell nodes apart at a glance while staying visually out of the way.
export function shortKey(pem: string): string {
  const body = pem
    .replace('-----BEGIN PUBLIC KEY-----', '')
    .replace('-----END PUBLIC KEY-----', '')
    .replace(/\s+/g, '')
  return body.slice(-8)
}

export function keysEqual(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false
  return a.trim() === b.trim()
}
