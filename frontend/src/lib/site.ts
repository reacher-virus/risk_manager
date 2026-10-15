/** One place for the facts shown on the public site (header, footer, 404, legal pages, meta). */
export const SITE = {
  name: 'Risk Manager',
  owner: 'Yash',
  email: 'yashpree237915@gmail.com',
  github: 'https://github.com/reacher-virus/ai-risk-manager',
  tagline: 'AI fraud detection that explains every decision',
} as const

export const mailto = (subject: string): string => `mailto:${SITE.email}?subject=${encodeURIComponent(subject)}`
export const copyrightYear = (): number => new Date().getFullYear()

export const SECTIONS = [['features', 'Features'], ['how', 'How it works'], ['security', 'Security'], ['results', 'Results'], ['faq', 'FAQ']] as const
