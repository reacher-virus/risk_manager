import { describe, expect, it } from 'vitest'

// Every shipped source file (not the tests) is scanned. These patterns are how XSS and token theft usually enter a React app.
const files = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../__tests__/**', '!../**/*.d.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('static safety scan of the frontend source', () => {
  it('found the source files', () => {
    expect(Object.keys(files).length).toBeGreaterThan(20)
  })

  const banned: [string, RegExp][] = [
    ['dangerouslySetInnerHTML', /dangerouslySetInnerHTML/],
    ['innerHTML / outerHTML assignment', /\.(inner|outer)HTML\s*=/],
    ['insertAdjacentHTML', /insertAdjacentHTML/],
    ['document.write', /document\.write/],
    ['eval()', /\beval\s*\(/],
    ['new Function()', /new\s+Function\s*\(/],
    ['string timers', /set(Timeout|Interval)\(\s*['"`]/],
    ['sessionStorage', /sessionStorage/],
    ['javascript: URLs', /javascript:/i],
    ['unsafe target=_blank without rel', /target=["']_blank["'](?![^>]*noopener)/],
    ['dead "#" links', /href=["']#["']/],
    ['unbalanced braces in a quoted JSX attribute (renders literally)', /="[^"\n]*\{[A-Za-z_.]+\}[^"\n]*"/],
  ]
  for (const [name, re] of banned) {
    it(`never uses ${name}`, () => {
      const hits = Object.entries(files).filter(([, src]) => re.test(src)).map(([f]) => f)
      expect(hits).toEqual([])
    })
  }

  it('only writes the theme preference to localStorage (no tokens, keys or user data)', () => {
    const resolve = (src: string, arg: string): string => {
      if (/^['"]/.test(arg)) return arg.replace(/['"]/g, '')
      const def = src.match(new RegExp(`const\\s+${arg}\\s*=\\s*['"]([^'"]+)['"]`))     // a named constant defined in the same file
      return def ? def[1] : `UNRESOLVED(${arg})`
    }
    const keys = Object.values(files).flatMap((src) => [...src.matchAll(/localStorage\.setItem\(\s*([^,]+),/g)].map((m) => resolve(src, m[1].trim())))
    expect(keys.length).toBeGreaterThan(0)
    expect(keys.every((k) => k === 'risk_theme')).toBe(true)
  })

  it('does not read or write the auth cookies from JavaScript, except the readable CSRF token and the notice cookie', () => {
    const touching = Object.entries(files).filter(([, src]) => /document\.cookie/.test(src)).map(([f]) => f.replace('../', ''))
    expect(touching.sort()).toEqual(['api.ts', 'components/CookieBanner.tsx'])
    expect(files['../api.ts']).not.toMatch(/risk_access|risk_refresh/)
  })
})
