import type { EChartsOption } from 'echarts'

export interface DashboardEntry {
  id: string
  title: string
  question: string
  dax_query: string
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

function getCubeAddress(): string {
  const config = useRuntimeConfig()
  return config.defaultCubeAddress as string
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

export function defaultCubeBody() {
  return { cube_address: getCubeAddress() }
}
