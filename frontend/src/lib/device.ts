/** Only auto-focus a field on large screens with a real pointer: on phones it pops the keyboard open uninvited and scrolls the page. */
export const canAutoFocus = (): boolean =>
  typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(min-width: 901px) and (pointer: fine)').matches
