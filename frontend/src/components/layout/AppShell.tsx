import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import clsx from 'clsx'
import { alerts } from '../../api'
import { useAuth } from '../../hooks/auth-context'
import { can } from '../../lib/permissions'
import { qk } from '../../lib/query-keys'
import { Badge, Button } from '../ui'

const NAV = [
  { to: '/', label: 'Dashboard', end: true, permission: 'shipment:read' },
  { to: '/shipments', label: 'Shipments', permission: 'shipment:read' },
  { to: '/suppliers', label: 'Suppliers', permission: 'supplier:read' },
  { to: '/documents', label: 'Documents', permission: 'document:read' },
  { to: '/ask', label: 'Ask', permission: 'insight:read' },
  { to: '/alerts', label: 'Alerts', permission: 'alert:read' },
  { to: '/settings', label: 'Settings', permission: 'user:write' },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const [navOpen, setNavOpen] = useState(false)

  const unread = useQuery({
    queryKey: qk.unreadCount,
    queryFn: alerts.unreadCount,
    enabled: can(user?.role, 'alert:read'),
    refetchInterval: 60_000,
  })

  const items = NAV.filter((item) => can(user?.role, item.permission))

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-black/5 bg-(--color-surface-raised)/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Button
            variant="ghost"
            className="md:hidden"
            aria-label="Toggle navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen((open) => !open)}
          >
            Menu
          </Button>
          <span className="font-semibold tracking-tight">Supply Chain Intelligence</span>

          <nav className="ml-6 hidden gap-1 md:flex">
            {items.map((item) => (
              <NavItem
                key={item.to}
                {...item}
                badge={item.to === '/alerts' ? unread.data : undefined}
              />
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="hidden text-sm text-(--color-ink-muted) sm:inline">
                {user.full_name} · {user.role}
              </span>
            )}
            <Button variant="ghost" onClick={() => void logout()}>
              Sign out
            </Button>
          </div>
        </div>

        {navOpen && (
          <nav className="flex flex-col gap-1 border-t border-black/5 px-4 py-2 md:hidden">
            {items.map((item) => (
              <NavItem key={item.to} {...item} onClick={() => setNavOpen(false)} />
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

function NavItem({
  to,
  label,
  end,
  badge,
  onClick,
}: {
  to: string
  label: string
  end?: boolean
  badge?: number
  onClick?: () => void
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        clsx(
          'rounded-lg px-3 py-1.5 text-sm transition-colors',
          isActive
            ? 'bg-(--color-accent)/15 font-medium text-(--color-accent)'
            : 'text-(--color-ink-muted) hover:bg-black/5 dark:hover:bg-white/5',
        )
      }
    >
      {label}
      {badge ? (
        <span className="ml-2">
          <Badge tone="bad">{badge}</Badge>
        </span>
      ) : null}
    </NavLink>
  )
}
