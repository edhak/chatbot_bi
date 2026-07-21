export interface DataSourceRow {
  seudonimo: string
  ruta_cubo: string | null
  ruta_power_bi: string | null
  ruta_diccionario: string | null
  diccionario_existe?: boolean
}

const STORAGE_KEY = 'bi-data-source-seudonimo-v2'

const sources = ref<DataSourceRow[]>([])
const selectedSeudonimo = ref('')
const cubeAddress = ref('')
const powerBiUrl = ref('')
const dictionaryPath = ref('')
const hydrated = ref(false)
const loadError = ref<string | null>(null)
const loading = ref(false)

function isConfigured(row: DataSourceRow | undefined): boolean {
  if (!row) return false
  return Boolean(row.ruta_cubo?.trim()) || Boolean(row.ruta_power_bi?.trim())
}

function applySelection(seudonimo: string) {
  const row = sources.value.find((s) => s.seudonimo === seudonimo)
  selectedSeudonimo.value = seudonimo
  cubeAddress.value = row?.ruta_cubo?.trim() || ''
  powerBiUrl.value = row?.ruta_power_bi?.trim() || ''
  dictionaryPath.value = row?.ruta_diccionario?.trim() || ''
  if (import.meta.client && seudonimo) {
    localStorage.setItem(STORAGE_KEY, seudonimo)
  }
}

export function useDataSources() {
  async function loadSources() {
    loading.value = true
    loadError.value = null
    try {
      const data = await $fetch<{ items: DataSourceRow[] }>('/api/data-sources')
      sources.value = data.items ?? []
      const stored = import.meta.client ? localStorage.getItem(STORAGE_KEY) : null
      const preferred =
        (stored && sources.value.some((s) => s.seudonimo === stored) ? stored : null)
        || sources.value.find((s) => isConfigured(s))?.seudonimo
        || sources.value[0]?.seudonimo
        || ''
      if (preferred) {
        applySelection(preferred)
      } else {
        selectedSeudonimo.value = ''
        cubeAddress.value = ''
        powerBiUrl.value = ''
        dictionaryPath.value = ''
      }
    } catch (err: unknown) {
      loadError.value =
        err instanceof Error ? err.message : 'No se pudo cargar fuentes_datos.csv'
      sources.value = []
    } finally {
      loading.value = false
      hydrated.value = true
    }
  }

  function hydrate() {
    if (!hydrated.value && !loading.value) {
      void loadSources()
    }
  }

  function selectSource(seudonimo: string) {
    applySelection(seudonimo)
  }

  const selectedSource = computed(() =>
    sources.value.find((s) => s.seudonimo === selectedSeudonimo.value),
  )

  const hasCube = computed(() => Boolean(cubeAddress.value.trim()))
  const hasPowerBi = computed(() => Boolean(powerBiUrl.value.trim()))
  const hasDictionary = computed(() => Boolean(dictionaryPath.value.trim()))

  return {
    sources,
    selectedSeudonimo,
    selectedSource,
    cubeAddress,
    powerBiUrl,
    dictionaryPath,
    hydrated,
    loading,
    loadError,
    hasCube,
    hasPowerBi,
    hasDictionary,
    hydrate,
    loadSources,
    selectSource,
  }
}
