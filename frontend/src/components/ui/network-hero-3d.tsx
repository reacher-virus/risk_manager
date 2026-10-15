"use client";

import { useEffect, useRef } from 'react'

/**
 * Draggable 3D "linked-account network" for the landing hero: drag (or swipe) to rotate, it also drifts slowly on its own.
 * Grey points are ordinary accounts; the glowing orange cluster is a fraud ring sharing one device. It is the product's
 * core idea (network detection) as a generative sculpture. Lazy-loads three.js, respects reduced motion, pauses off-screen.
 */
export function NetworkHero3D({ className = '' }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    let cleanup: (() => void) | undefined

    void import('three').then((THREE) => {
      const el = host.current
      if (!el || !active) return
      let renderer: InstanceType<typeof THREE.WebGLRenderer>
      try {
        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
      } catch {
        return                                                         // no WebGL: the static CSS glow remains
      }
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      el.appendChild(renderer.domElement)
      renderer.domElement.setAttribute('aria-hidden', 'true')
      renderer.domElement.style.touchAction = 'pan-y'                    // vertical page scroll still works on touch

      const scene = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100)
      camera.position.z = 9
      const group = new THREE.Group()
      scene.add(group)

      // deterministic pseudo-random so the sculpture looks the same on every load
      let seed = 7
      const rand = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646 }
      const onSphere = (r: number, spread: number) => {
        const u = rand() * 2 - 1, t = rand() * Math.PI * 2, s = Math.sqrt(1 - u * u)
        const rr = r * (1 - spread * rand())
        return new THREE.Vector3(rr * s * Math.cos(t), rr * u, rr * s * Math.sin(t))
      }

      const normal = Array.from({ length: 140 }, () => onSphere(3.4, 0.55))
      const ringCenter = new THREE.Vector3(1.9, 1.1, 1.2)
      const ring = Array.from({ length: 9 }, () => ringCenter.clone().add(new THREE.Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).multiplyScalar(1.7)))

      // soft round sprite so points are discs, not square pixels
      const spriteCanvas = document.createElement('canvas')
      spriteCanvas.width = spriteCanvas.height = 64
      const sctx = spriteCanvas.getContext('2d')
      if (sctx) {
        const grad = sctx.createRadialGradient(32, 32, 0, 32, 32, 32)
        grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.55, 'rgba(255,255,255,1)'); grad.addColorStop(1, 'rgba(255,255,255,0)')
        sctx.fillStyle = grad; sctx.fillRect(0, 0, 64, 64)
      }
      const sprite = new THREE.CanvasTexture(spriteCanvas)

      const pointsOf = (pts: InstanceType<typeof THREE.Vector3>[], color: number, size: number, opacity: number) => {
        const g = new THREE.BufferGeometry().setFromPoints(pts)
        const m = new THREE.PointsMaterial({ color, size, map: sprite, alphaTest: 0.02, sizeAttenuation: false, transparent: true, opacity, depthWrite: false })
        const obj = new THREE.Points(g, m)
        group.add(obj)
        return { g, m, obj }
      }
      const linesOf = (pairs: [InstanceType<typeof THREE.Vector3>, InstanceType<typeof THREE.Vector3>][], color: number, opacity: number) => {
        const g = new THREE.BufferGeometry().setFromPoints(pairs.flat())
        const m = new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false })
        group.add(new THREE.LineSegments(g, m))
        return { g, m }
      }

      const dots = pointsOf(normal, 0xd4d4d8, 6 * Math.min(window.devicePixelRatio, 2), 0.9)
      const hot = pointsOf([ringCenter, ...ring], 0xf97316, 13 * Math.min(window.devicePixelRatio, 2), 1)
      const near: [InstanceType<typeof THREE.Vector3>, InstanceType<typeof THREE.Vector3>][] = []
      normal.forEach((a, i) => {
        const closest = normal.map((b, j) => [a.distanceTo(b), j] as const).filter(([, j]) => j !== i).sort((x, y) => x[0] - y[0]).slice(0, 2)
        closest.forEach(([d, j]) => { if (d < 1.5 && j > i) near.push([a, normal[j]]) })
      })
      const grey = linesOf(near, 0xa1a1aa, 0.22)
      const red = linesOf(ring.map((p) => [ringCenter, p] as [InstanceType<typeof THREE.Vector3>, InstanceType<typeof THREE.Vector3>]), 0xf97316, 0.75)

      let rotY = 0.6, rotX = 0.18, vy = 0, vx = 0, dragging = false, lastX = 0, lastY = 0, visible = true, frame = 0
      const resize = () => {
        const w = el.clientWidth || 1, h = el.clientHeight || 1
        renderer.setSize(w, h)
        camera.aspect = w / h
        camera.position.z = w / h < 0.9 ? 12 : 9                          // pull back on tall (phone) viewports so nothing is clipped
        camera.updateProjectionMatrix()
      }
      const down = (e: PointerEvent) => { dragging = true; lastX = e.clientX; lastY = e.clientY; renderer.domElement.setPointerCapture(e.pointerId); el.classList.add('is-dragging') }
      const move = (e: PointerEvent) => { if (!dragging) return; vy = (e.clientX - lastX) * 0.006; vx = (e.clientY - lastY) * 0.004; rotY += vy; rotX = Math.max(-0.9, Math.min(0.9, rotX + vx)); lastX = e.clientX; lastY = e.clientY }
      const up = () => { dragging = false; el.classList.remove('is-dragging') }
      const draw = (t: number) => {
        if (!dragging) { rotY += vy + (reduceMotion ? 0 : 0.0016); vy *= 0.95; rotX += vx; vx *= 0.9 }
        group.rotation.set(rotX, rotY, 0)
        hot.m.opacity = reduceMotion ? 1 : 0.7 + 0.3 * Math.sin(t / 420)
        renderer.render(scene, camera)
      }
      const loop = (t: number) => { frame = requestAnimationFrame(loop); if (visible && !document.hidden) draw(t) }

      resize()
      draw(0)
      if (!reduceMotion) frame = requestAnimationFrame(loop)
      const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting }, { threshold: 0.01 })
      io.observe(el)
      const ro = new ResizeObserver(resize)
      ro.observe(el)
      const c = renderer.domElement
      c.addEventListener('pointerdown', down); c.addEventListener('pointermove', move); c.addEventListener('pointerup', up); c.addEventListener('pointercancel', up)
      if (reduceMotion) c.addEventListener('pointermove', () => draw(0))

      cleanup = () => {
        cancelAnimationFrame(frame); io.disconnect(); ro.disconnect()
        c.removeEventListener('pointerdown', down); c.removeEventListener('pointermove', move); c.removeEventListener('pointerup', up); c.removeEventListener('pointercancel', up)
        ;[dots, hot].forEach((p) => { p.g.dispose(); p.m.dispose() })
        ;[grey, red].forEach((l) => { l.g.dispose(); l.m.dispose() })
        sprite.dispose(); renderer.dispose(); c.remove()
      }
      if (!active) cleanup()
    })

    return () => { active = false; cleanup?.() }
  }, [])

  return <div ref={host} className={`net3d ${className}`} role="img" aria-label="Interactive 3D diagram of a network of linked accounts. A cluster of orange points is a fraud ring. Drag to rotate." />
}
