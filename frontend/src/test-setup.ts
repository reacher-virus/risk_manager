import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// vitest runs without globals, so Testing Library's automatic cleanup is not registered
afterEach(cleanup)

// jsdom has no matchMedia, no scrollTo and no WebGL. Stub them so components behave like they do in a browser without a GPU.
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })
}
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
vi.mock('three', () => ({ WebGLRenderer: class { constructor() { throw new Error('WebGL is not available in tests') } } }))   // components fall back to their static background
