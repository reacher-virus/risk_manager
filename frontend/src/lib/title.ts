import { SITE } from './site'

const TITLES: Record<string, string> = {
  '/': `${SITE.name}: ${SITE.tagline}`,
  '/signin': `Sign in · ${SITE.name}`,
  '/signup': `Create your account · ${SITE.name}`,
  '/admin-login': `Administrator sign-in · ${SITE.name}`,
  '/forgot': `Reset your password · ${SITE.name}`,
  '/reset': `Choose a new password · ${SITE.name}`,
  '/terms': `Terms of Service · ${SITE.name}`,
  '/privacy': `Privacy Policy · ${SITE.name}`,
  '/hero': `Welcome · ${SITE.name}`,
}

const TAB_LABELS: Record<string, string> = {
  overview: 'Overview', alerts: 'Alerts', simulator: 'Simulator', threshold: 'Threshold & cost', rings: 'Networks',
  analytics: 'Analytics', monitoring: 'Monitoring', batch: 'Batch CSV', users: 'Users', settings: 'Settings',
}

/** The browser tab title for a route; `notFound` wins so a bad URL never keeps a misleading title. */
export function titleFor(path: string, notFound = false): string {
  if (notFound) return `Page not found · ${SITE.name}`
  if (path.startsWith('/app')) return `${TAB_LABELS[path.split('/')[2] ?? 'overview'] ?? 'Dashboard'} · ${SITE.name}`
  return TITLES[path] ?? `Page not found · ${SITE.name}`
}
