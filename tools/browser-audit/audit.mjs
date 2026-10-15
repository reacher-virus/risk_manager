import chromium from '@sparticuz/chromium'
import puppeteer from 'puppeteer-core'
import { launchOptions } from './launch.mjs'
import { mockFor } from './mock.mjs'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:4173'
const WIDTHS = [320, 375, 414, 768, 1024, 1440]
const PUBLIC = ['#/', '#/signin', '#/signup', '#/admin-login', '#/forgot', '#/reset', '#/terms', '#/privacy', '#/no-such-page']
const APP = ['#/hero', '#/app/overview', '#/app/alerts', '#/app/simulator', '#/app/threshold', '#/app/rings', '#/app/analytics', '#/app/monitoring', '#/app/batch', '#/app/users', '#/app/settings']

const browser = await puppeteer.launch(await launchOptions(chromium))

async function open(mode, width, height = 800) {
  const page = await browser.newPage()
  await page.setViewport({ width, height, deviceScaleFactor: 1, isMobile: width < 700, hasTouch: width < 700 })
  const problems = []
  page.on('pageerror', (e) => problems.push('PAGEERROR ' + e.message))
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) problems.push('CONSOLE ' + m.text().slice(0, 160)) })
  const mock = mockFor(mode)
  await page.setRequestInterception(true)
  page.on('request', (req) => {
    const url = new URL(req.url())
    const cors = { 'access-control-allow-origin': BASE, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,x-csrf-token', 'access-control-allow-methods': 'GET,POST,PUT,PATCH' }
    if (url.hostname === 'localhost' && url.port === '8000') {
      if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors })
      const r = mock(url.pathname)
      return req.respond({ status: r.status, headers: { ...cors, 'content-type': 'application/json' }, body: JSON.stringify(r.body) })
    }
    if (url.origin === BASE) return req.continue()
    return req.abort()                                         // fonts etc.: not reachable from the sandbox
  })
  return { page, problems }
}

const overflowProbe = () => {
  const de = document.documentElement, w = de.clientWidth, bad = []
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect()
    if (r.width === 0 || getComputedStyle(el).position === 'fixed') continue
    if (r.right > w + 1 || r.left < -1) {
      let p = el.parentElement, clipped = false
      while (p && p !== document.body) { const cs = getComputedStyle(p); if (['auto', 'scroll', 'hidden', 'clip'].includes(cs.overflowX) && p.getBoundingClientRect().right <= w + 1) { clipped = true; break } p = p.parentElement }
      if (!clipped) bad.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} [${Math.round(r.left)}..${Math.round(r.right)}]`)
    }
  }
  const inner = []
  if (w <= 620) for (const el of document.querySelectorAll('body *')) {                      // sideways-scrolling regions on phones
    const cs = getComputedStyle(el)
    if (['auto', 'scroll'].includes(cs.overflowX) && el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) inner.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} scrolls ${el.scrollWidth}>${el.clientWidth}`)
  }
  return { scrollW: de.scrollWidth, clientW: w, bad: [...new Set([...bad, ...inner])].slice(0, 5) }
}

let failures = 0
const report = []
for (const [mode, routes] of [['anon', PUBLIC], ['admin', APP]]) {
  for (const width of WIDTHS) {
    const { page, problems } = await open(mode, width)
    for (const route of routes) {
      await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
      await page.evaluate((r) => { window.location.hash = r }, route)
      await page.goto(`${BASE}/${route}`, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {})
      await new Promise((r) => setTimeout(r, 450))
      const o = await page.evaluate(overflowProbe)
      const hs = o.scrollW > o.clientW
      if (hs || o.bad.length) { failures++; report.push(`✗ ${mode} ${String(width).padStart(4)}px ${route.padEnd(18)} scrollW=${o.scrollW}/${o.clientW} ${o.bad.join(' | ')}`) }
    }
    if (problems.length) { report.push(`! ${mode} ${width}px console/page problems: ${[...new Set(problems)].slice(0, 4).join(' || ')}`) }
    await page.close()
  }
}
console.log(report.length ? report.join('\n') : 'no horizontal overflow and no console errors on any route at any width')
console.log(`\nroute×width combinations checked: ${(PUBLIC.length + APP.length) * WIDTHS.length}; overflow failures: ${failures}`)
await browser.close()
