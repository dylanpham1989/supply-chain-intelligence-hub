import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from './lib/health'

type Probe = { state: 'loading' } | { state: 'ready'; health: Health } | { state: 'error' }

export default function App() {
  const [probe, setProbe] = useState<Probe>({ state: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => setProbe({ state: 'ready', health }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setProbe({ state: 'error' })
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-4 py-12">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Supply Chain Intelligence Hub</h1>
        <p className="mt-1 text-sm text-(--color-ink-muted)">
          Multi-tenant analytics for shipments, suppliers and contracts.
        </p>
      </header>

      <section
        aria-labelledby="stack-status"
        className="rounded-xl bg-(--color-surface-raised) p-5 shadow-sm"
      >
        <h2 id="stack-status" className="text-sm font-medium tracking-wide uppercase">
          Stack status
        </h2>
        <div className="mt-4">
          {probe.state === 'loading' && (
            <p role="status" className="text-sm text-(--color-ink-muted)">
              Checking services
            </p>
          )}
          {probe.state === 'error' && (
            <p role="alert" className="text-sm text-(--color-bad)">
              API unreachable. Is the stack running? Try <code>make up</code>.
            </p>
          )}
          {probe.state === 'ready' && (
            <dl className="grid grid-cols-3 gap-3 text-sm">
              <Item label="API" ok={probe.health.status === 'ok'} />
              <Item label="Database" ok={probe.health.db} />
              <Item label="Redis" ok={probe.health.redis} />
            </dl>
          )}
        </div>
      </section>
    </main>
  )
}

function Item({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div>
      <dt className="text-(--color-ink-muted)">{label}</dt>
      <dd
        className={`mt-1 font-medium ${ok ? 'text-(--color-ok)' : 'text-(--color-bad)'}`}
        data-testid={`status-${label.toLowerCase()}`}
      >
        {ok ? 'up' : 'down'}
      </dd>
    </div>
  )
}
