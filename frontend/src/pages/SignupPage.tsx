import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../hooks/auth-context'
import { ApiError } from '../lib/api-client'
import { Button, Card, Input } from '../components/ui'

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/

export default function SignupPage() {
  const { signup } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [slug, setSlug] = useState('')

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const tenant = String(form.get('tenant_slug'))

    if (!SLUG.test(tenant)) {
      setError('Workspace id must be lowercase words separated by single hyphens')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await signup({
        company_name: String(form.get('company_name')),
        tenant_slug: tenant,
        email: String(form.get('email')),
        password: String(form.get('password')),
        full_name: String(form.get('full_name')),
      })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Create a workspace</h1>
      <p className="mb-6 text-sm text-(--color-ink-muted)">You will be its first administrator.</p>

      <Card>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-(--color-ink-muted)">Company</span>
            <Input
              name="company_name"
              required
              minLength={2}
              onChange={(event) =>
                setSlug(
                  event.target.value
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-')
                    .replace(/^-+|-+$/g, ''),
                )
              }
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-(--color-ink-muted)">Workspace id</span>
            <Input
              name="tenant_slug"
              required
              minLength={3}
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-(--color-ink-muted)">Your name</span>
            <Input name="full_name" required minLength={2} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-(--color-ink-muted)">Email</span>
            <Input name="email" type="email" required autoComplete="username" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-(--color-ink-muted)">Password</span>
            <Input
              name="password"
              type="password"
              required
              minLength={10}
              autoComplete="new-password"
            />
            <span className="text-xs text-(--color-ink-muted)">At least 10 characters.</span>
          </label>

          {error && (
            <p role="alert" className="text-sm text-(--color-bad)">
              {error}
            </p>
          )}

          <Button type="submit" disabled={busy} className="mt-2">
            {busy ? 'Creating' : 'Create workspace'}
          </Button>
        </form>
      </Card>

      <p className="mt-4 text-center text-sm text-(--color-ink-muted)">
        Already have one?{' '}
        <Link to="/login" className="text-(--color-accent) underline-offset-2 hover:underline">
          Sign in
        </Link>
      </p>
    </main>
  )
}
