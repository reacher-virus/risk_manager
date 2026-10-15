"use client";

import type { ReactNode } from 'react'
import { Logo } from '@/components/Logo'
import { DotShaderBackground } from '@/components/ui/dot-shader-background'

/**
 * The visual shell from the original `modern-login-signup` component: black page, animated dot-matrix canvas, radial
 * vignette and a centred dark card. It wraps every public auth screen (sign in, sign up, admin, forgot, reset).
 */
export function AuthShell({ title, subtitle, children, footer, variant = 'user' }: {
  title: string; subtitle?: string; children: ReactNode; footer?: ReactNode; variant?: 'user' | 'admin'
}) {
  return (
    <main className={`auth force-dark auth--${variant}`}>
      <DotShaderBackground />
      <div className="auth__vignette" aria-hidden="true" />
      <section className="auth__card" aria-labelledby="auth-title">
        <Logo />
        {variant === 'admin' && <span className="auth__badge">Administrator console</span>}
        <h1 id="auth-title" className="auth__title">{title}</h1>
        {subtitle && <p className="auth__subtitle">{subtitle}</p>}
        <div className="auth__body">{children}</div>
        {footer && <footer className="auth__footer">{footer}</footer>}
        <p className="auth__legal">By continuing you agree to the <a href="#/terms">Terms of Service</a> and <a href="#/privacy">Privacy Policy</a>.</p>
      </section>
    </main>
  )
}
