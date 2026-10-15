import chromium from '@sparticuz/chromium'
import puppeteer from 'puppeteer-core'
import { launchOptions } from './launch.mjs'
import { mockFor } from './mock.mjs'
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:4173', SHOTS = process.env.SHOTS_DIR ?? './shots'
import { mkdirSync } from 'node:fs'; mkdirSync(SHOTS, { recursive: true })
const browser = await puppeteer.launch(await launchOptions(chromium))
const results = []
const check = (name, ok, extra = '') => { results.push(`${ok ? '✓' : '✗'} ${name}${extra ? '  ' + extra : ''}`) }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function open(mode, width, height) {
  const page = await browser.newPage()
  await page.setViewport({ width, height, deviceScaleFactor: 1, isMobile: width < 700, hasTouch: width < 700 })
  const mock = mockFor(mode)
  await page.setRequestInterception(true)
  page.on('request', (req) => {
    const u = new URL(req.url())
    const cors = { 'access-control-allow-origin': BASE, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type,x-csrf-token', 'access-control-allow-methods': 'GET,POST,PUT,PATCH' }
    if (u.hostname === 'localhost' && u.port === '8000') { if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors }); const r = mock(u.pathname); return req.respond({ status: r.status, headers: { ...cors, 'content-type': 'application/json' }, body: JSON.stringify(r.body) }) }
    return u.origin === BASE ? req.continue() : req.abort()
  })
  await page.evaluateOnNewDocument(() => { document.cookie = 'risk_cookie_notice=1; Path=/' })     // keep screenshots uncluttered
  return page
}
const go = async (page, hash) => { await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {}); await wait(900) }

// ---------- landing: desktop ----------
let page = await open('anon', 1440, 900)
await go(page, '#/')
check('landing title', (await page.title()).startsWith('Risk Manager: AI fraud detection'), await page.title())
check('meta description present (<=160 chars)', await page.$eval('meta[name=description]', (m) => m.content.length > 50 && m.content.length <= 160))
check('favicon links present', (await page.$$eval('link[rel~=icon], link[rel=apple-touch-icon], link[rel=manifest]', (l) => l.length)) >= 5)
check('og:image present', !!(await page.$('meta[property="og:image"]')))
check('3D hero canvas rendered', await page.$eval('.net3d canvas', (c) => c.width > 100 && c.height > 100).catch(() => false))
const clip = await page.$eval('.net3d', (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height } })
const shotA = await page.screenshot({ clip })
const box = { x: clip.x + clip.width / 2, y: clip.y + clip.height / 2 }
await page.mouse.move(box.x, box.y); await page.mouse.down(); await page.mouse.move(box.x + 200, box.y + 40, { steps: 10 }); await page.mouse.up(); await wait(250)
const shotB = await page.screenshot({ clip })
check('3D hero draws and is draggable (screenshot differs after a drag)', Buffer.compare(shotA, shotB) !== 0)
await page.screenshot({ path: `${SHOTS}/landing-desktop.png` })
await page.evaluate(() => document.getElementById('features').scrollIntoView()); await wait(300)
await page.screenshot({ path: `${SHOTS}/landing-features.png` })
// footer
const links = await page.$$eval('.site-footer a', (as) => as.map((a) => [a.textContent.trim(), a.getAttribute('href'), a.getAttribute('target'), a.getAttribute('rel')]))
check('footer: no empty or "#" links', links.every(([, h]) => h && h !== '#'), `${links.length} links`)
check('footer: external link opens safely', links.filter(([, , t]) => t === '_blank').every(([, , , rel]) => /noopener/.test(rel || '')))
check('footer: contact is a mailto link to Yash', links.some(([, h]) => h.startsWith('mailto:yashpree237915@gmail.com')))
const yr = await page.$eval('.site-footer__copy', (e) => e.textContent)
check('footer: copyright year is current', yr.includes(String(new Date().getFullYear())) && yr.includes('Yash'), yr.slice(0, 40))
// logo clickable -> home
await go(page, '#/privacy')
await page.click('.site-header .auth-logo'); await wait(400)
check('logo click returns to home from /privacy', await page.evaluate(() => location.hash === '#/' || location.hash === ''))
// footer section link from another page scrolls home
await go(page, '#/terms'); await page.evaluate(() => [...document.querySelectorAll('.site-footer a')].find((a) => a.textContent.trim() === 'Security').click()); await wait(900)
check('footer "Security" link from /terms goes home and scrolls to the section', await page.evaluate(() => location.hash === '#/' && document.getElementById('security').getBoundingClientRect().top < 400))
await page.close()

// ---------- titles + 404 ----------
page = await open('anon', 1280, 800)
for (const [h, t] of [['#/signin', 'Sign in'], ['#/signup', 'Create your account'], ['#/terms', 'Terms of Service'], ['#/privacy', 'Privacy Policy'], ['#/zzz', 'Page not found']]) { await go(page, h); check(`title for ${h}`, (await page.title()).startsWith(t), await page.title()) }
await go(page, '#/zzz')
check('custom 404 renders with a way home', await page.evaluate(() => !!document.querySelector('.notfound') && document.querySelector('.notfound h1').textContent.includes('could not be found') && !!document.querySelector('.notfound a[href="#/"]')))
await page.screenshot({ path: `${SHOTS}/404.png` })
const st = await page.goto(`${BASE}/404.html`); check('static /404.html exists', st.status() === 200)
await go(page, '#/signin'); await page.screenshot({ path: `${SHOTS}/signin-desktop.png` })
check('sign-in card + dot canvas present', await page.evaluate(() => !!document.querySelector('.dotbg') && !!document.querySelector('.auth__card')))
check('sign-in logo is a link home', await page.$eval('.auth__card .auth-logo', (a) => a.getAttribute('href') === '#/'))
check('no social login buttons left (nothing broken)', !(await page.evaluate(() => /Continue with (Google|GitHub|Apple)/.test(document.body.innerText))))
await go(page, '#/signup'); await page.screenshot({ path: `${SHOTS}/signup-desktop.png` })
await page.close()

// ---------- mobile: landing menu ----------
page = await open('anon', 375, 760)
await go(page, '#/'); await page.screenshot({ path: `${SHOTS}/landing-mobile.png` })
check('mobile header: Sign in + Get started hidden (they live in the menu) and nothing overlaps', await page.evaluate(() => { const d = (s) => getComputedStyle(document.querySelector(s)).display; const name = document.querySelector('.site-header__name').getBoundingClientRect(); const first = document.querySelector('.site-header__actions .icon-btn').getBoundingClientRect(); return d('.site-header__signin') === 'none' && d('.site-header__cta') === 'none' && name.right <= first.left }))
check('mobile: desktop nav hidden, hamburger visible', await page.evaluate(() => getComputedStyle(document.querySelector('.site-nav')).display === 'none' && getComputedStyle(document.querySelector('.menu-btn')).display !== 'none'))
await page.click('.menu-btn'); await wait(300)
check('mobile menu opens (aria-expanded + panel visible)', await page.evaluate(() => document.querySelector('.menu-btn').getAttribute('aria-expanded') === 'true' && document.querySelector('.menu-panel').getBoundingClientRect().width > 200))
check('page behind is scroll-locked while open', await page.evaluate(() => document.body.style.overflow === 'hidden'))
check('mobile menu is a full-height panel (portal, not clipped to the header)', await page.evaluate(() => { const r = document.querySelector('.menu-panel').getBoundingClientRect(); return r.top <= 1 && r.height >= innerHeight - 2 && r.right >= innerWidth - 1 }))
check('menu backdrop covers the whole page', await page.evaluate(() => { const r = document.querySelector('.menu-backdrop').getBoundingClientRect(); return r.width >= innerWidth - 1 && r.height >= innerHeight - 1 }))
await page.screenshot({ path: `${SHOTS}/menu-open-mobile.png` })
check('menu has its own visible close button', await page.evaluate(() => { const b = document.querySelector('.menu-panel .menu-close'); if (!b) return false; const r = b.getBoundingClientRect(); return r.width > 30 && r.top >= 0 && r.right <= innerWidth }))
await page.click('.menu-panel .menu-close'); await wait(250)
check('close button closes the menu and unlocks scrolling', await page.evaluate(() => document.querySelector('.menu-btn').getAttribute('aria-expanded') === 'false' && document.body.style.overflow !== 'hidden'))
await page.click('.menu-btn'); await wait(250)
await page.keyboard.press('Escape'); await wait(250)
check('Escape closes the menu and unlocks scrolling', await page.evaluate(() => document.querySelector('.menu-btn').getAttribute('aria-expanded') === 'false' && document.body.style.overflow !== 'hidden'))
await page.click('.menu-btn'); await wait(200); await page.evaluate(() => [...document.querySelectorAll('.menu-panel a')].find((a) => a.textContent.trim() === 'FAQ').click()); await wait(900)
check('menu link scrolls to its section and closes the menu', await page.evaluate(() => document.getElementById('faq').getBoundingClientRect().top < 300 && document.querySelector('.menu-btn').getAttribute('aria-expanded') === 'false'))
await go(page, '#/signup')
const su = await page.evaluate(() => ({ y: Math.round(scrollY), active: document.activeElement?.tagName + '.' + (document.activeElement?.className || document.activeElement?.name || '') }))
check('sign-up opens at the top and does not auto-open the keyboard on phones', su.y === 0 && su.active.startsWith('BODY'), JSON.stringify(su))
await page.screenshot({ path: `${SHOTS}/signup-mobile.png` })
await go(page, '#/signin'); await page.screenshot({ path: `${SHOTS}/signin-mobile.png` })
await page.close()

// ---------- signed in: hero, dashboard, mobile menu, toast ----------
page = await open('admin', 1440, 900)
await go(page, '#/hero'); await page.screenshot({ path: `${SHOTS}/hero-page.png` })
check('hero page title', (await page.title()).startsWith('Welcome'))
await go(page, '#/app/overview'); await page.screenshot({ path: `${SHOTS}/dashboard-desktop.png` })
check('dashboard title from tab', (await page.title()).startsWith('Overview'))
check('dashboard logo links to workspace home', await page.$eval('.topbar .auth-logo', (a) => a.getAttribute('href') === '#/hero'))
await page.close()
page = await open('admin', 375, 760)
await go(page, '#/app/alerts')
check('alert table is stacked into cards on phones (no sideways scrolling)', await page.evaluate(() => getComputedStyle(document.querySelector('.table--stack thead')).display === 'none' && document.querySelector('.table--stack td[data-label]') !== null && document.querySelector('.table-wrap').scrollWidth <= document.querySelector('.table-wrap').clientWidth + 1))
check('dashboard header stays on one row on phones', await page.evaluate(() => { const t = document.querySelector('.topbar'); return t.getBoundingClientRect().height < 80 }))
await page.screenshot({ path: `${SHOTS}/dashboard-mobile.png` })
await page.click('.menu-btn'); await wait(300)
check('dashboard mobile menu lists the sections', await page.evaluate(() => document.querySelectorAll('.menu-panel .menu-tab').length >= 8))
await page.screenshot({ path: `${SHOTS}/dashboard-menu-mobile.png` })
await page.evaluate(() => [...document.querySelectorAll('.menu-panel .menu-tab')].find((b) => b.textContent.trim() === 'Users').click()); await wait(700)
check('dashboard menu navigates (Users tab)', await page.evaluate(() => location.hash === '#/app/users'))
await go(page, '#/app/alerts')
await page.click('.table--clickable tbody tr'); await wait(700)
check('alert drawer opens on mobile without horizontal overflow', await page.evaluate(() => { const d = document.querySelector('.drawer'); return !!d && d.scrollWidth <= d.clientWidth + 1 }))
await page.screenshot({ path: `${SHOTS}/drawer-mobile.png` })
await page.close()

console.log(results.join('\n'))
console.log(`\n${results.filter((r) => r.startsWith('✓')).length}/${results.length} behaviours verified`)
await browser.close()
