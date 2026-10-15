import type { ReactNode } from 'react'
import { scrollToSection } from '@/lib/scroll'

export function ScrollLink({ to, children, onNavigate, className }: { to: string; children: ReactNode; onNavigate?: () => void; className?: string }) {
  return (
    <a className={className} href="#/" onClick={(e) => { e.preventDefault(); onNavigate?.(); scrollToSection(to) }}>{children}</a>
  )
}
