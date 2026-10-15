import chromium from '@sparticuz/chromium'
import puppeteer from 'puppeteer-core'
import { launchOptions } from './launch.mjs'
import { mockFor } from './mock.mjs'
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:4174'
const browser = await puppeteer.launch(await launchOptions(chromium))
const out = []
for (const [mode, route] of [['anon', '#/'], ['anon', '#/signin'], ['anon', '#/signup'], ['admin', '#/hero'], ['admin', '#/app/overview'], ['admin', '#/app/analytics'], ['admin', '#/app/threshold'], ['admin', '#/app/rings']]) {
  const page = await browser.newPage(); await page.setViewport({ width: 1280, height: 800 })
  const mock = mockFor(mode)
  await page.setRequestInterception(true)
  page.on('request', (req) => { const u = new URL(req.url()); if (u.origin === BASE && u.pathname.startsWith('/api/')) { const r = mock(u.pathname.slice(4)); return req.respond({ status: r.status, contentType: 'application/json', body: JSON.stringify(r.body) }) } return u.origin === BASE ? req.continue() : req.abort() })
  await page.evaluateOnNewDocument(() => { window.__csp = []; document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.violatedDirective} blocked ${e.blockedURI || 'inline'}`)); document.cookie = 'risk_cookie_notice=1; Path=/' })
  const consoleCsp = []; page.on('console', (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) consoleCsp.push(m.text().slice(0, 140)) })
  const errs = []; page.on('pageerror', (e) => errs.push(e.message))
  await page.goto(`${BASE}/${route}`, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {}); await new Promise((r) => setTimeout(r, 900))
  const v = await page.evaluate(() => window.__csp)
  const rendered = await page.evaluate(() => document.body.innerText.length > 100)
  const canvas = await page.evaluate(() => !!document.querySelector('canvas'))
  out.push(`${v.length || consoleCsp.length || errs.length ? '✗' : '✓'} ${mode} ${route.padEnd(18)} rendered=${rendered} canvas=${canvas} csp-violations=${v.length + consoleCsp.length} js-errors=${errs.length} ${[...v, ...consoleCsp, ...errs].slice(0, 2).join(' | ')}`)
  await page.close()
}
console.log(out.join('\n')); await browser.close()
