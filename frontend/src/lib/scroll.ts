import { navigate, parseHash } from '@/lib/route'

let raf = 0
const USER_INPUT = ['wheel', 'touchstart', 'keydown', 'mousedown'] as const

/** Stops a running section scroll (route changes and any user input call this). The browser's own smooth scroll cannot be cancelled. */
export function cancelSmoothScroll(): void {
  cancelAnimationFrame(raf)
  USER_INPUT.forEach((e) => window.removeEventListener(e, cancelSmoothScroll))
}

function animateTo(top: number): void {
  cancelSmoothScroll()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { window.scrollTo(0, top); return }
  const start = window.scrollY, dist = top - start, t0 = performance.now()
  const dur = Math.min(700, 250 + Math.abs(dist) * 0.15)
  const step = (t: number) => {
    const p = Math.min(1, (t - t0) / dur)
    window.scrollTo(0, start + dist * (1 - Math.pow(1 - p, 3)))        // ease-out cubic
    if (p < 1) raf = requestAnimationFrame(step); else cancelSmoothScroll()
  }
  USER_INPUT.forEach((e) => window.addEventListener(e, cancelSmoothScroll, { passive: true, once: true }))
  raf = requestAnimationFrame(step)
}

/** In-page section link that works with hash routing: it scrolls on the landing page and, from any other page, goes home first. */
export function scrollToSection(id: string): void {
  const go = () => {
    const el = document.getElementById(id)
    if (el) animateTo(Math.max(0, el.getBoundingClientRect().top + window.scrollY - 60))   // 60px: the sticky header
  }
  if (parseHash(window.location.hash).path === '/') go()
  else { navigate('/'); setTimeout(go, 60) }
}

