import type { AxiosAdapter, AxiosRequestConfig, AxiosResponse } from 'axios'

export interface Reply {
  status: number
  data?: unknown
}

export type Route = (config: AxiosRequestConfig) => Reply | Promise<Reply>

/**
 * Serves axios from a routing table instead of the network.
 *
 * The interceptors are what is under test and they run on the instance, so
 * replacing the adapter exercises them exactly, in one process, with nothing
 * else in the way.
 */
export function routingAdapter(routes: Record<string, Route>): AxiosAdapter {
  return async (config) => {
    const method = (config.method ?? 'get').toUpperCase()
    const url = config.url ?? ''
    const route = routes[`${method} ${url}`]

    if (!route) throw new Error(`no route for ${method} ${url}`)

    const reply = await route(config)
    const response: AxiosResponse = {
      data: reply.data,
      status: reply.status,
      statusText: String(reply.status),
      headers: {},
      config: config as never,
    }

    if (reply.status >= 400) {
      const error = new Error(`Request failed with status code ${reply.status}`) as Error & {
        response?: AxiosResponse
        config?: AxiosRequestConfig
        isAxiosError?: boolean
      }
      error.response = response
      error.config = config
      error.isAxiosError = true
      throw error
    }
    return response
  }
}
