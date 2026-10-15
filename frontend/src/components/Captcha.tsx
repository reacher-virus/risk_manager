import { useEffect, useState } from 'react'
import { auth } from '../api'
import type { CaptchaChallenge } from '../types'
import { Button } from './ui'

/** Image CAPTCHA. Bump `nonce` from the parent (e.g. after a failed submit) to fetch a fresh one: each is single-use. */
export function Captcha({ nonce, onChange }: { nonce: number; onChange: (v: { captcha_id: string; captcha_answer: string }) => void }) {
  const [c, setC] = useState<CaptchaChallenge | null>(null)
  const [answer, setAnswer] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [local, setLocal] = useState(0)

  useEffect(() => {
    let live = true
    setAnswer(''); setErr(null); setC(null)
    auth.captcha().then((r) => { if (live) { setC(r); onChange({ captcha_id: r.captcha_id, captcha_answer: '' }) } })
      .catch((e: Error) => { if (live) setErr(e.message) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, local])

  return (
    <div className="captcha">
      <div className="captcha__row">
        {c ? <img className="captcha__img" src={c.image} alt="CAPTCHA: distorted letters and digits" width={200} height={70} /> : <div className="captcha__img captcha__img--loading">{err ?? 'Loading…'}</div>}
        <Button type="button" variant="ghost" onClick={() => setLocal((n) => n + 1)} aria-label="Get a new CAPTCHA">↻ New</Button>
      </div>
      <label className="field">
        <span className="field__label">Type the characters you see</span>
        <input value={answer} maxLength={10} autoComplete="off" autoCapitalize="characters" spellCheck={false} required
          onChange={(e) => { setAnswer(e.target.value); if (c) onChange({ captcha_id: c.captcha_id, captcha_answer: e.target.value }) }} />
      </label>
    </div>
  )
}
