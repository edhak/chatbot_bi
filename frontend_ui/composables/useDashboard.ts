export interface DashboardEntry {
  id: string
  title: string
  question: string
  dax_query: string
  cube_address?: string | null
  seudonimo?: string | null
  chartConfig: Record<string, unknown>
  created_at?: string
  updated_at?: string
  last_refresh_at?: string | null
  last_error?: string | null
  elapsed_ms?: number
  row_count?: number
}

const includedDaxSet = ref<Set<string>>(new Set())
const dashboardIdsByDax = ref<Map<string, string>>(new Map())

function normalizeDax(dax: string): string {
  return dax.trim()
}

export function useDashboard() {
  const { cubeAddress, selectedSeudonimo, hydrate } = useDataSources()

  function activeCube(): string {
    hydrate()
    return cubeAddress.value?.trim() || ''
  }

  function activeSeudonimo(): string {
    hydrate()
    return selectedSeudonimo.value?.trim() || ''
  }

  async function loadIncludedMap() {
    try {
      // Sin forzar el cubo activo: cada ítem usa su fuente guardada
      const data = await $fetch<{ items: DashboardEntry[] }>('/api/dashboard')
      const daxSet = new Set<string>()
      const idMap = new Map<string, string>()
      for (const item of data.items ?? []) {
        const key = normalizeDax(item.dax_query)
        daxSet.add(key)
        idMap.set(key, item.id)
      }
      includedDaxSet.value = daxSet
      dashboardIdsByDax.value = idMap
    } catch {
      includedDaxSet.value = new Set()
      dashboardIdsByDax.value = new Map()
    }
  }

  function isIncluded(daxQuery: string | undefined): boolean {
    if (!daxQuery) return false
    return includedDaxSet.value.has(normalizeDax(daxQuery))
  }

  async function addToDashboard(payload: {
    title: string
    question: string
    dax_query: string
    cube_address?: string
    seudonimo?: string
  }): Promise<DashboardEntry> {
    const entry = await $fetch<DashboardEntry>('/api/dashboard', {
      method: 'POST',
      body: {
        ...payload,
        cube_address: payload.cube_address || activeCube(),
        seudonimo: payload.seudonimo || activeSeudonimo() || undefined,
      },
    })
    const key = normalizeDax(entry.dax_query)
    includedDaxSet.value = new Set([...includedDaxSet.value, key])
    dashboardIdsByDax.value = new Map(dashboardIdsByDax.value).set(key, entry.id)
    return entry
  }

  async function removeFromDashboard(daxQuery: string): Promise<void> {
    const key = normalizeDax(daxQuery)
    const id = dashboardIdsByDax.value.get(key)
    if (!id) return
    await removeById(id)
  }

  async function removeById(id: string): Promise<void> {
    await $fetch(`/api/dashboard/${id}`, { method: 'DELETE' })
    const map = new Map(dashboardIdsByDax.value)
    for (const [dax, itemId] of map.entries()) {
      if (itemId === id) {
        map.delete(dax)
        const next = new Set(includedDaxSet.value)
        next.delete(dax)
        includedDaxSet.value = next
        break
      }
    }
    dashboardIdsByDax.value = map
  }

  async function fetchDashboard(): Promise<DashboardEntry[]> {
    const data = await $fetch<{ items: DashboardEntry[] }>('/api/dashboard')
    await loadIncludedMap()
    return data.items ?? []
  }

  async function refreshItem(id: string): Promise<DashboardEntry> {
    // No enviar cubo activo: el backend usa cube_address/seudonimo del ítem
    return $fetch<DashboardEntry>(`/api/dashboard/${id}/refresh`, {
      method: 'POST',
    })
  }

  async function refreshAll(): Promise<DashboardEntry[]> {
    const data = await $fetch<{ items: DashboardEntry[] }>('/api/dashboard/refresh-all', {
      method: 'POST',
    })
    return data.items ?? []
  }

  return {
    includedDaxSet,
    isIncluded,
    loadIncludedMap,
    addToDashboard,
    removeFromDashboard,
    removeById,
    fetchDashboard,
    refreshItem,
    refreshAll,
  }
}
