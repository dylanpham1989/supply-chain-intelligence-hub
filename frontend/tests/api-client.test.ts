import axios from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, setSessionLostHandler } from '../src/lib/api-client'
import { getAccessToken, setAccessToken } from '../src/lib/auth-store'
import { routingAdapter, type Route } from './support/adapter'

function install(routes: Record<string, Route>): void {
  const adapter = routingAdapter(routes)
  api.defaults.adapter = adapter
  // The refresh call is made on the bare axios instance so it skips the
  // interceptors; it needs the same adapter.
  axios.defaults.adapter = adapter
}

beforeEach(() => {
  setAccessToken(null)
  setSessionLostHandler(() => {})
})

describe('token refresh', () => {
  it('refreshes once when several requests expire together', async () => {
    // Rotation revokes the previous token, so five parallel refreshes would
    // revoke four of each other and sign the user out for no visible reason.
    let refreshCalls = 0
    let issued = false

    install({
      'POST /api/v1/auth/refresh': async () => {
        refreshCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 20))
        issued = true
        return { status: 200, data: { access_token: 'fresh-token' } }
      },
      'GET /api/v1/shipments': (config) =>
        issued && config.headers?.Authorization === 'Bearer fresh-token'
          ? { status: 200, data: { items: [] } }
          : { status: 401, data: { code: 'unauthenticated', message: 'expired' } },
    })

    const results = await Promise.all(Array.from({ length: 5 }, () => api.get('/api/v1/shipments')))

    expect(refreshCalls).toBe(1)
    expect(results).toHaveLength(5)
    expect(getAccessToken()).toBe('fresh-token')
  })

  it('retries the original request with the new token', async () => {
    const seen: unknown[] = []
    install({
      'POST /api/v1/auth/refresh': () => ({
        status: 200,
        data: { access_token: 'second-token' },
      }),
      'GET /api/v1/shipments': (config) => {
        seen.push(config.headers?.Authorization)
        return config.headers?.Authorization === 'Bearer second-token'
          ? { status: 200, data: { items: [] } }
          : { status: 401, data: { code: 'unauthenticated', message: 'expired' } }
      },
    })
    setAccessToken('stale-token')

    await api.get('/api/v1/shipments')

    expect(seen).toEqual(['Bearer stale-token', 'Bearer second-token'])
  })

  it('gives up rather than looping when the refresh itself fails', async () => {
    let refreshCalls = 0
    const sessionLost = vi.fn()
    setSessionLostHandler(sessionLost)

    install({
      'POST /api/v1/auth/refresh': () => {
        refreshCalls += 1
        return { status: 401, data: { code: 'unauthenticated', message: 'gone' } }
      },
      'GET /api/v1/shipments': () => ({
        status: 401,
        data: { code: 'unauthenticated', message: 'expired' },
      }),
    })

    await expect(api.get('/api/v1/shipments')).rejects.toBeInstanceOf(ApiError)

    expect(refreshCalls).toBe(1)
    expect(sessionLost).toHaveBeenCalledOnce()
    expect(getAccessToken()).toBeNull()
  })

  it('does not try to refresh a failing refresh', async () => {
    let calls = 0
    install({
      'POST /api/v1/auth/refresh': () => {
        calls += 1
        return { status: 401, data: { code: 'unauthenticated', message: 'no cookie' } }
      },
    })

    await expect(api.post('/api/v1/auth/refresh')).rejects.toBeInstanceOf(ApiError)

    expect(calls).toBe(1)
  })

  it('does not retry a request twice', async () => {
    let attempts = 0
    install({
      'POST /api/v1/auth/refresh': () => ({ status: 200, data: { access_token: 'never-works' } }),
      'GET /api/v1/shipments': () => {
        attempts += 1
        return { status: 401, data: { code: 'unauthenticated', message: 'still expired' } }
      },
    })

    await expect(api.get('/api/v1/shipments')).rejects.toBeInstanceOf(ApiError)

    expect(attempts).toBe(2)
  })
})

describe('errors', () => {
  it('surfaces the code and message the api sent', async () => {
    install({
      'GET /api/v1/users': () => ({
        status: 403,
        data: { code: 'forbidden', message: 'Requires user:read' },
      }),
    })

    await expect(api.get('/api/v1/users')).rejects.toMatchObject({
      status: 403,
      code: 'forbidden',
      message: 'Requires user:read',
    })
  })

  it('carries the field problems from a validation failure', async () => {
    install({
      'POST /api/v1/auth/login': () => ({
        status: 422,
        data: {
          code: 'validation_error',
          message: 'Request is invalid',
          fields: [{ field: 'email', problem: 'Field required' }],
        },
      }),
    })

    await expect(api.post('/api/v1/auth/login', {})).rejects.toMatchObject({
      code: 'validation_error',
      fields: [{ field: 'email', problem: 'Field required' }],
    })
  })

  it('sends no authorization header when there is no token', async () => {
    let header: unknown = 'unset'
    install({
      'GET /api/v1/shipments': (config) => {
        header = config.headers?.Authorization
        return { status: 200, data: { items: [] } }
      },
    })

    await api.get('/api/v1/shipments')

    expect(header).toBeUndefined()
  })
})
