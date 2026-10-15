/** The brand mark. Always a link, so the logo is clickable everywhere it appears (home for visitors, workspace for members). */
export function Logo({ href = '#/', size = 44 }: { href?: string; size?: number }) {
  return (
    <a className="auth-logo" href={href} aria-label="Risk Manager home" style={{ width: size, height: size }}>
      <svg viewBox="0 0 32 32" width={size * 0.64} height={size * 0.64} fill="none" aria-hidden="true">
        <path d="M4 16h5l3-9 5 18 3-9h8" stroke="#f97316" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </a>
  )
}
