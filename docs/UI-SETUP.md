# UI integration notes

How the login/sign-up component and the landing page were integrated, what was changed, and how to extend the setup.

## What went where

| File | Role |
|---|---|
| `frontend/src/components/ui/modern-login-signup.tsx` | The login/sign-up component (default export, same file name as the original). Card + toggle + footer; the forms inside are the real two-step auth flows |
| `frontend/src/components/ui/auth-shell.tsx` | The component's visual shell (black page, dot-matrix canvas, vignette, dark card). Wraps **every** public auth screen: sign in, sign up, admin, forgot, reset |
| `frontend/src/components/ui/dot-shader-background.tsx` | The original WebGL dot-matrix shader, bundled and with a clean lifecycle |
| `frontend/src/components/ui/network-hero-3d.tsx` | Draggable 3D "linked-account network" for the landing hero (the template reference's 3D hero, built around this product's core idea) |
| `frontend/src/components/ui/index.tsx` | The app's existing primitives (Card, Button, Stat...), moved from `ui.tsx` so `components/ui/` is a folder. Existing imports of `'../components/ui'` still resolve |
| `frontend/src/demo.tsx` | The demo from the brief: `import Component from "@/components/ui/modern-login-signup"` |
| `frontend/src/pages/LandingPage.tsx`, `NotFoundPage.tsx`, `LegalPages.tsx` | Public site: landing, custom 404, privacy and terms |
| `frontend/src/lib/site.ts` | **One place for your name, email, GitHub URL and section list.** Header, footer, 404, legal pages and mailto links all read it |

## Project compatibility check

| Requirement | State | Notes |
|---|---|---|
| TypeScript | yes | strict, `tsc -b` in the build |
| Tailwind CSS | **no** | not needed: the original component was fully inline-styled, and it is ported to the app's CSS classes (`index.css`, design tokens at the top) |
| shadcn project structure | **no** (`components.json` absent) | the folder convention is followed (`components/ui`, `@/` alias) so the CLI can be added later |
| `@/` path alias | added | `vite.config.ts` (`resolve.alias`) and `tsconfig.app.json` (`paths`) |

### Why `components/ui` matters

shadcn's CLI writes primitives (button, input, dialog...) into `components/ui`, and `components.json` maps the alias `@/components/ui` to it.
Keeping reusable, presentation-only building blocks in one folder (and feature screens elsewhere) means: the CLI never overwrites your feature code,
imports are short and stable (`@/components/ui/...` instead of `../../../`), and a new contributor knows where a "Button" lives.
That is why the existing `ui.tsx` file became `ui/index.tsx` rather than leaving a file and a folder of the same name side by side.

## If you want Tailwind + shadcn later (Vite, React, TypeScript)

```bash
cd frontend
npm install tailwindcss @tailwindcss/vite
```

1. `vite.config.ts`: `import tailwindcss from '@tailwindcss/vite'` and `plugins: [react(), tailwindcss(), siteUrl()]`.
2. `src/index.css`: add `@import "tailwindcss";` as the first line. Tailwind's reset can change plain elements (buttons, headings), so migrate screen by screen and re-run the browser audit (`tools/browser-audit`).
3. `npx shadcn@latest init`, then confirm `components.json` aliases: `components: "@/components"`, `ui: "@/components/ui"`, `utils: "@/lib/utils"` (the `@/*` path already exists).
4. Add primitives as needed: `npx shadcn@latest add button input dialog`. They land in `src/components/ui/` next to the files above.

## Dependencies added

| Package | Why |
|---|---|
| `three` (+ `@types/three`) | Bundled and loaded with a dynamic `import()` (its own ~130 KB gzipped chunk, fetched only by the landing and auth pages). The original loaded three.js from a CDN `<script>`: that is a third-party script on a sign-in page (supply-chain risk) and is blocked by this app's `script-src 'self'` Content-Security-Policy |
| `lucide-react` | Icons for the landing page, menu and toasts (tree-shaken: only the icons used ship) |

No stock photos are used: the brief's "fill image assets with Unsplash" does not apply, since the design needs none, and `img-src 'self' data:` in the CSP would block hot-linked images anyway.

## Changes made to the original component

- **Real auth.** The forms were `onSubmit={e => e.preventDefault()}` stubs. They are now the app's CAPTCHA + emailed-code flows.
- **Removed the Google / GitHub / Apple buttons.** There is no OAuth backend, and a button that does nothing is worse than none. Footer text about "creating a Vercel account" now points to this product's Terms and Privacy Policy pages (which exist).
- **Logo** is a link home (and, signed in, to the workspace).
- **WebGL hygiene:** cleanup of the resize listener, animation frame and GPU resources (the original's script-onload path never cleaned up), pauses when the tab is hidden, honours `prefers-reduced-motion`, falls back to a plain black page without WebGL2.
- **Auth screens are always dark** (`.force-dark`), as designed; the landing page and dashboard support light and dark.

## Props, state and where it is used

- `Component({ initialMode?: 'signin' | 'signup' })`: internal state is just the mode. It must sit inside `<AuthProvider>` (it signs the user in). Responsive down to 320 px.
- The routes (`#/signin`, `#/signup`, `#/admin-login`, `#/forgot`, `#/reset`) use `AuthShell` directly so URLs reflect the screen; the default export is for embedding and the demo.

## Customising

- **Your details:** `frontend/src/lib/site.ts` (name shown in the footer's copyright, contact email, GitHub link).
- **Colours / fonts:** the tokens at the top of `frontend/src/index.css` (dark `:root`, `:root[data-theme='light']`).
- **Page title and description, social-share tags:** `frontend/index.html`; set `VITE_SITE_URL` (e.g. `https://risk.example.com`) at build time so `og:image` and the canonical URL are absolute. Per-page titles come from `src/lib/title.ts`.
- **Icons and share image:** edit `BRAND` in `scripts/generate_brand_assets.py` and run it.
- **Legal pages:** `LegalPages.tsx` describes what the software actually does; have it reviewed before commercial use.
- **Not included on purpose:** testimonials and pricing sections (the reference template has them). There are no real customers or plans to show; add them when they exist.
