"use client";

import { useState } from 'react'
import { AuthShell } from '@/components/ui/auth-shell'
import { SignInForm } from '@/pages/auth/SignInPage'
import { SignUpForm } from '@/pages/auth/SignUpPage'

/**
 * Drop-in version of the original component: sign in / sign up in one card with a toggle. It needs an <AuthProvider>
 * above it. The app's routes use AuthShell directly (#/signin, #/signup); this default export is for embedding and demos.
 */
export default function Component({ initialMode = 'signin' }: { initialMode?: 'signin' | 'signup' }) {
  const [mode, setMode] = useState(initialMode)
  const signin = mode === 'signin'
  return (
    <AuthShell
      title={signin ? 'Sign in to Account' : 'Sign up for Account'}
      footer={signin
        ? <>Don't have an account? <button type="button" className="linklike" onClick={() => setMode('signup')}>Sign up</button></>
        : <>Already have an account? <button type="button" className="linklike" onClick={() => setMode('signin')}>Sign in</button></>}
    >
      {signin ? <SignInForm /> : <SignUpForm />}
    </AuthShell>
  )
}

