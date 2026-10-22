// Soft-keyboard fallback for browsers that overlay the visual viewport instead of
// resizing the layout viewport (iOS Safari, older Android WebView). Chromium with
// `interactive-widget=resizes-content` already shrinks the layout viewport, so the
// measured inset stays 0 and no extra space is added there.
const TEXT_INPUT_TYPES = new Set(['text', 'search', 'email', 'url', 'tel', 'password', 'number', 'date', 'datetime-local', 'month', 'week', 'time'])
const KEYBOARD_THRESHOLD = 80

// Only controls that raise the on-screen keyboard count; checkboxes, files,
// ranges and select pickers do not shrink the visual viewport for typing.
function editableFocused(): boolean {
  const active = document.activeElement as HTMLElement | null
  if (!active) return false
  if (active.isContentEditable) return true
  if (active.tagName === 'TEXTAREA') return true
  if (active.tagName !== 'INPUT') return false
  return TEXT_INPUT_TYPES.has((active as HTMLInputElement).type)
}

/**
 * Publishes the part of the layout viewport hidden by the on-screen keyboard as
 * `--keyboard-inset` plus `html.keyboard-open`, so bottom actions and dialogs can
 * stay reachable while typing. Returns a cleanup function for unmount/HMR.
 */
export function installVisualViewportInset(): () => void {
  const viewport = window.visualViewport
  const root = document.documentElement
  if (!viewport) return () => {}
  let frame = 0
  const apply = () => {
    frame = 0
    const scale = viewport.scale || 1
    const inset = Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop))
    // Pinch-zoom shrinks the visual viewport too; only an unscaled, keyboard-sized
    // inset may reserve space. Focus can move to a bottom action while the keyboard
    // is still up, so an open reservation is kept until the viewport itself restores.
    const open = scale <= 1.01 && inset > KEYBOARD_THRESHOLD
      && (editableFocused() || root.classList.contains('keyboard-open'))
    root.classList.toggle('keyboard-open', open)
    if (open) root.style.setProperty('--keyboard-inset', inset + 'px')
    else root.style.removeProperty('--keyboard-inset')
  }
  const schedule = () => { if (!frame) frame = window.requestAnimationFrame(apply) }
  viewport.addEventListener('resize', schedule)
  viewport.addEventListener('scroll', schedule)
  document.addEventListener('focusin', schedule)
  document.addEventListener('focusout', schedule)
  apply() // Remount while the keyboard is already open must reserve immediately.
  return () => {
    if (frame) window.cancelAnimationFrame(frame)
    viewport.removeEventListener('resize', schedule)
    viewport.removeEventListener('scroll', schedule)
    document.removeEventListener('focusin', schedule)
    document.removeEventListener('focusout', schedule)
    root.classList.remove('keyboard-open')
    root.style.removeProperty('--keyboard-inset')
  }
}
