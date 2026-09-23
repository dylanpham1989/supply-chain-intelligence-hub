import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { getAccessToken, setAccessToken } from './auth-store'
import type { ApiErrorBody } from '../types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export interface FieldProblem {
  field: string
  problem: string
}

export class ApiError extends Error {
  status: number
  code: string
  fields: FieldProblem[] | undefined

  constructor(status: number, code: string, message: string, fields?: FieldProblem[]) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

export const api = axios.create({
  baseURL: BASE_URL,
  // Needed for the refresh cookie, which is httpOnly and scoped to /api/v1/auth.
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

type Retriable = AxiosRequestConfig & { _retried?: boolean }

// One refresh at a time. Without this, five requests expiring together fire
// five refreshes, rotation revokes four of them, and the user is logged out for
// no reason they can see.
let refreshInFlight: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const response = await axios.post<{ access_token: string }>(
    `${BASE_URL}/api/v1/auth/refresh`,
    null,
    { withCredentials: true },
  )
  const token = response.data.access_token
  setAccessToken(token)
  return token
}

let onSessionLost: (() => void) | null = null

export function setSessionLostHandler(handler: () => void): void {
  onSessionLost = handler
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as Retriable | undefined
    const status = error.response?.status

    const isRefreshCall = config?.url?.includes('/auth/refresh')
    if (status === 401 && config && !config._retried && !isRefreshCall) {
      config._retried = true
      try {
        refreshInFlight ??= refreshAccessToken().finally(() => {
          refreshInFlight = null
        })
        const token = await refreshInFlight
        config.headers = { ...config.headers, Authorization: `Bearer ${token}` }
        return api(config)
      } catch {
        setAccessToken(null)
        onSessionLost?.()
      }
    }

    const body = error.response?.data
    throw new ApiError(
      status ?? 0,
      body?.code ?? 'network_error',
      body?.message ?? error.message,
      body?.fields,
    )
  },
)
