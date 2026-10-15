export interface Rule { label: string; ok: boolean }

/** Client-side hints only (instant feedback). The server enforces the real policy, including a common-password check. */
export function checkPassword(pw: string, email = ''): Rule[] {
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length
  const local = email.split('@')[0].toLowerCase()
  return [
    { label: 'At least 12 characters', ok: pw.length >= 12 },
    { label: '3 of: lowercase, UPPERCASE, digits, symbols (or 20+ characters)', ok: classes >= 3 || pw.length >= 20 },
    { label: "Doesn't contain your email name", ok: !(local.length >= 4 && pw.toLowerCase().includes(local)) },
    { label: 'No 4+ repeated characters in a row', ok: !/(.)\1{3,}/.test(pw) },
  ]
}

