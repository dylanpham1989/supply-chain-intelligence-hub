import { useEffect, useRef, type ReactNode } from 'react'
import { Button } from './index'

/**
 * A slide-over that a keyboard can also leave.
 *
 * Escape closes it and focus moves inside on open, because the backdrop click
 * and the close button are both mouse-only routes out.
 */
export function SidePanel({
  title,
  subtitle,
  onClose,
  children,
  width = 'max-w-md',
}: {
  title: string
  subtitle?: string
  onClose: () => void
  children: ReactNode
  width?: string
}) {
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`h-full w-full ${width} overflow-y-auto bg-(--color-surface) p-5 shadow-xl outline-none`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">{title}</h2>
            {subtitle && <p className="text-sm text-(--color-ink-muted)">{subtitle}</p>}
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            Close
          </Button>
        </header>
        {children}
      </aside>
    </div>
  )
}
