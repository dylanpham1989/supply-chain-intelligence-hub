import clsx from 'clsx'
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from 'react'

export function Card({
  title,
  action,
  children,
  className,
}: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={clsx(
        'rounded-xl bg-(--color-surface-raised) p-5 shadow-sm ring-1 ring-black/5',
        className,
      )}
    >
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-medium tracking-wide">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function Button({
  variant = 'primary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' }) {
  return (
    <button
      {...props}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium',
        'transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-accent)',
        variant === 'primary' && 'bg-(--color-accent) text-white hover:brightness-110',
        variant === 'ghost' &&
          'bg-transparent text-(--color-ink-muted) hover:bg-black/5 dark:hover:bg-white/5',
        variant === 'danger' && 'bg-(--color-bad) text-white hover:brightness-110',
        className,
      )}
    />
  )
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        'w-full rounded-lg bg-(--color-surface) px-3 py-2 text-sm ring-1 ring-black/10',
        'focus:ring-2 focus:ring-(--color-accent) focus:outline-none',
        className,
      )}
    />
  )
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={clsx(
        'rounded-lg bg-(--color-surface) px-3 py-2 text-sm ring-1 ring-black/10',
        'focus:ring-2 focus:ring-(--color-accent) focus:outline-none',
        className,
      )}
    />
  )
}

const TONE = {
  neutral: 'bg-black/5 text-(--color-ink-muted) dark:bg-white/10',
  ok: 'bg-(--color-ok)/15 text-(--color-ok)',
  warn: 'bg-(--color-warn)/15 text-(--color-warn)',
  bad: 'bg-(--color-bad)/15 text-(--color-bad)',
} as const

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: keyof typeof TONE
  children: ReactNode
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        TONE[tone],
      )}
    >
      {children}
    </span>
  )
}

// A skeleton shaped like the thing it replaces, so nothing jumps when the data
// lands. A centred spinner would move the whole page.
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded bg-black/10 dark:bg-white/10', className)} />
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-sm text-sm text-(--color-ink-muted)">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-4 py-8 text-center">
      <p className="text-sm text-(--color-bad)">{message}</p>
      {onRetry && (
        <Button variant="ghost" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
