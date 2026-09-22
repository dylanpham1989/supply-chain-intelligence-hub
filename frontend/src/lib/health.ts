export type HealthStatus = 'ok' | 'degraded'

export interface Health {
  status: HealthStatus
  db: boolean
  redis: boolean
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch('/health', { signal: signal ?? null })
  // A degraded stack answers 503 with the same body, which is still useful here.
  if (response.status !== 200 && response.status !== 503) {
    throw new Error(`health check failed with status ${response.status}`)
  }
  return (await response.json()) as Health
}
