import type { EChartsOption } from 'echarts'

export interface DashboardEntry {
  id: string
  title: string
  question: string
  dax_query: string
  cube_address?: string | null
  seudonimo?: string | null
  chartConfig: EChartsOption | Record<string, unknown>
  created_at?: string
  updated_at?: string
  last_refresh_at?: string | null
  last_error?: string | null
  elapsed_ms?: number
  row_count?: number
}

function getAgentApiUrl(): string {
  const config = useRuntimeConfig()
  return config.agentApiUrl as string
}

function getDefaultCubeAddress(): string {
  const config = useRuntimeConfig()
  return (config.defaultCubeAddress as string) || ''
}

export async function agentGet<T>(path: string, query?: Record<string, string>): Promise<T> {
  const base = getAgentApiUrl().replace(/\/$/, '')
  const qs = query ? `?${new URLSearchParams(query)}` : ''
  return $fetch<T>(`${base}${path}${qs}`)
}

export async function agentPost<T>(path: string, body?: unknown): Promise<T> {
  const base = getAgentApiUrl().replace(/\/$/, '')
  return $fetch<T>(`${base}${path}`, { method: 'POST', body })
}

export async function agentDelete<T>(path: string): Promise<T> {
  const base = getAgentApiUrl().replace(/\/$/, '')
  return $fetch<T>(`${base}${path}`, { method: 'DELETE' })
}

/** Cubo de fallback (env). Preferir el enviado por el cliente desde Fuentes de datos. */
export function resolveCubeAddress(clientCube?: string | null): string {
  const fromClient = (clientCube || '').trim()
  if (fromClient) return fromClient
  return getDefaultCubeAddress()
}

export function defaultCubeBody(clientCube?: string | null) {
  return { cube_address: resolveCubeAddress(clientCube) }
}
