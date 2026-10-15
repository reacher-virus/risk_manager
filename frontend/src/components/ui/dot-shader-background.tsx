"use client";

import { useEffect, useRef } from 'react'

/**
 * Animated dot-matrix WebGL background (the shader from the original modern-login-signup component).
 *
 * Differences from the original, on purpose:
 *  - `three` is a bundled dependency loaded with a dynamic import (code-split), not a <script> from a CDN. A third-party
 *    script on a sign-in page is a supply-chain risk and is blocked by this app's Content-Security-Policy anyway.
 *  - Complete clean-up (resize listener, animation frame, GPU resources), including when unmounted mid-load.
 *  - Honours `prefers-reduced-motion` (draws one still frame), pauses when the tab is hidden, caps the pixel ratio.
 *  - Falls back silently to a plain dark background when WebGL2 is unavailable.
 */
export function DotShaderBackground({ className = '' }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let active = true
    let cleanup: (() => void) | undefined

    void import('three').then((THREE) => {
      const canvas = canvasRef.current
      if (!canvas || !active) return
      let renderer: InstanceType<typeof THREE.WebGLRenderer>
      try {
        renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false })
      } catch {
        return                                              // no WebGL: the CSS background is the fallback
      }
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      const size = () => ({ w: canvas.clientWidth || window.innerWidth, h: canvas.clientHeight || window.innerHeight })
      let { w, h } = size()
      renderer.setSize(w, h, false)

      const scene = new THREE.Scene()
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
      const uniforms = {
        u_time: { value: 0 },
        u_resolution: { value: new THREE.Vector2(w * 2, h * 2) },
        u_opacities: { value: [0.3, 0.3, 0.3, 0.5, 0.5, 0.5, 0.8, 0.8, 0.8, 1.0] },
        u_colors: { value: Array.from({ length: 6 }, () => new THREE.Vector3(1, 1, 1)) },
        u_total_size: { value: 20.0 },
        u_dot_size: { value: 6.0 },
        u_reverse: { value: 0 },
      }
      const material = new THREE.ShaderMaterial({
        vertexShader: `
          precision mediump float;
          uniform vec2 u_resolution;
          out vec2 fragCoord;
          void main() {
            gl_Position = vec4(position, 1.0);
            fragCoord = (position.xy + 1.0) * 0.5 * u_resolution;
            fragCoord.y = u_resolution.y - fragCoord.y;
          }
        `,
        fragmentShader: `
          precision mediump float;
          in vec2 fragCoord;
          uniform float u_time;
          uniform float u_opacities[10];
          uniform vec3 u_colors[6];
          uniform float u_total_size;
          uniform float u_dot_size;
          uniform vec2 u_resolution;
          uniform int u_reverse;
          out vec4 fragColor;
          float PHI = 1.61803398874989484820459;
          float random(vec2 xy) { return fract(tan(distance(xy * PHI, xy) * 0.5) * xy.x); }
          void main() {
            vec2 st = fragCoord.xy;
            st.x -= abs(floor((mod(u_resolution.x, u_total_size) - u_dot_size) * 0.5));
            st.y -= abs(floor((mod(u_resolution.y, u_total_size) - u_dot_size) * 0.5));
            float opacity = step(0.0, st.x) * step(0.0, st.y);
            vec2 st2 = vec2(int(st.x / u_total_size), int(st.y / u_total_size));
            float frequency = 5.0;
            float show_offset = random(st2);
            float rand = random(st2 * floor((u_time / frequency) + show_offset + frequency));
            opacity *= u_opacities[int(rand * 10.0)];
            opacity *= 1.0 - step(u_dot_size / u_total_size, fract(st.x / u_total_size));
            opacity *= 1.0 - step(u_dot_size / u_total_size, fract(st.y / u_total_size));
            vec3 color = u_colors[int(show_offset * 6.0)];
            float animation_speed_factor = 3.0;
            vec2 center_grid = u_resolution / 2.0 / u_total_size;
            float dist_from_center = distance(center_grid, st2);
            float timing_offset_intro = dist_from_center * 0.01 + (random(st2) * 0.15);
            float current_timing_offset = timing_offset_intro;
            opacity *= step(current_timing_offset, u_time * animation_speed_factor);
            opacity *= clamp((1.0 - step(current_timing_offset + 0.1, u_time * animation_speed_factor)) * 1.25, 1.0, 1.25);
            fragColor = vec4(color, opacity);
            fragColor.rgb *= fragColor.a;
          }
        `,
        uniforms,
        glslVersion: THREE.GLSL3,
        blending: THREE.CustomBlending,
        blendSrc: THREE.SrcAlphaFactor,
        blendDst: THREE.OneFactor,
        transparent: true,
      })
      const geometry = new THREE.PlaneGeometry(2, 2)
      scene.add(new THREE.Mesh(geometry, material))

      const start = performance.now()
      let frame = 0
      const draw = () => { uniforms.u_time.value = reduceMotion ? 10 : (performance.now() - start) / 1000; renderer.render(scene, camera) }
      const loop = () => { frame = requestAnimationFrame(loop); draw() }
      const onVisibility = () => { cancelAnimationFrame(frame); if (!document.hidden && !reduceMotion) loop() }
      const onResize = () => { ({ w, h } = size()); renderer.setSize(w, h, false); uniforms.u_resolution.value.set(w * 2, h * 2); if (reduceMotion) draw() }

      if (reduceMotion) draw(); else loop()
      window.addEventListener('resize', onResize)
      document.addEventListener('visibilitychange', onVisibility)
      cleanup = () => {
        cancelAnimationFrame(frame)
        window.removeEventListener('resize', onResize)
        document.removeEventListener('visibilitychange', onVisibility)
        geometry.dispose(); material.dispose(); renderer.dispose()
      }
      if (!active) cleanup()
    })

    return () => { active = false; cleanup?.() }
  }, [])

  return <canvas ref={canvasRef} className={`dotbg ${className}`} aria-hidden="true" />
}
