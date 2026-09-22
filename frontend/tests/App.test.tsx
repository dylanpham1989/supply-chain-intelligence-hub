import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'

function mockHealth(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, json: async () => body } as Response))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('shows every dependency as up when the stack is healthy', async () => {
    mockHealth({ status: 'ok', db: true, redis: true })

    render(<App />)

    expect(await screen.findByTestId('status-api')).toHaveTextContent('up')
    expect(screen.getByTestId('status-database')).toHaveTextContent('up')
    expect(screen.getByTestId('status-redis')).toHaveTextContent('up')
  })

  it('reports the failing dependency when the stack is degraded', async () => {
    mockHealth({ status: 'degraded', db: false, redis: true }, 503)

    render(<App />)

    expect(await screen.findByTestId('status-database')).toHaveTextContent('down')
    expect(screen.getByTestId('status-redis')).toHaveTextContent('up')
  })

  it('tells the user how to recover when the api cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('API unreachable')
  })
})
