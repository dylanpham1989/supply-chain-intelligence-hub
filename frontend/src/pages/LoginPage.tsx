import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../hooks/auth-context'
import { ApiError } from '../lib/api-client'
import { Button, Card, Input } from '../components/ui'

export default function LoginPage() {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await login({
        tenant_slug: String(form.get('tenant_slug')),
        email: String(form.get('email')),
        password: String(form.get('password')),
      })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Supply Chain Intelligence</h1>
      <p className="mb-6 text-sm text-(--color-ink-muted)">Sign in to your workspace.</p>

      <Card>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <Field
            label="Workspace"
            name="tenant_slug"
            defaultValue="acme-logistics"
            autoComplete="organization"
          />
          <Field
            label="Email"
            name="email"
            type="email"
            defaultValue="admin@acme.test"
            autoComplete="username"
          />
          <Field label="Password" name="password" type="password" autoComplete="current-password" />

          {error && (
            <p role="alert" className="text-sm text-(--color-bad)">
              {error}
            </p>
          )}

          <Button type="submit" disabled={busy} className="mt-2">
            {busy ? 'Signing in' : 'Sign in'}
          </Button>
        </form>
      </Card>

      <p className="mt-4 text-center text-sm text-(--color-ink-muted)">
        No workspace yet?{' '}
        <Link to="/signup" className="text-(--color-accent) underline-offset-2 hover:underline">
          Create one
        </Link>
      </p>
      <p className="mt-6 text-center text-xs text-(--color-ink-muted)">
        Demo seed: admin@acme.test / Demo1234! in workspace acme-logistics
      </p>
    </main>
  )
}

function Field({
  label,
  name,
  ...props
}: { label: string; name: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-(--color-ink-muted)">{label}</span>
      <Input name={name} required {...props} />
    </label>
  )
}
