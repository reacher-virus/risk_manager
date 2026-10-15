import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Menu, X } from 'lucide-react'

/**
 * Hamburger button + slide-down panel. Accessible: aria-expanded/controls, Escape closes, focus moves into the panel and
 * returns to the button, the page behind does not scroll while it is open. Only visible below the breakpoint (CSS).
 */
export function MobileMenu({ id, open, onToggle, onClose, label = 'menu', children }: {
  id: string; open: boolean; onToggle: () => void; onClose: () => void; label?: string; children: ReactNode
}) {
  const button = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { onClose(); button.current?.focus() } }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.querySelector<HTMLElement>('a, button')?.focus()
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = previous }
  }, [open, onClose])

  useEffect(() => {                                   // growing past the breakpoint (rotate / resize) must not leave the page locked
    const mq = window.matchMedia('(min-width: 901px)')
    const onChange = () => { if (mq.matches) onClose() }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [onClose])

  return (
    <>
      <button ref={button} type="button" className="menu-btn" aria-expanded={open} aria-controls={id} aria-label={open ? `Close ${label}` : `Open ${label}`} onClick={onToggle}>
        {open ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
      </button>
      {/* portal: the header uses backdrop-filter, which would turn it into the containing block for these fixed elements */}
      {createPortal(
        <>
          {open && <div className="menu-backdrop" onClick={onClose} aria-hidden="true" />}
          <div ref={panel} id={id} className={`menu-panel ${open ? 'menu-panel--open' : ''}`} hidden={!open}>
            <button type="button" className="menu-close" onClick={() => { onClose(); button.current?.focus() }} aria-label={`Close ${label}`}><X size={22} aria-hidden="true" /></button>
            {children}
          </div>
        </>,
        document.body,
      )}
    </>
  )
}
