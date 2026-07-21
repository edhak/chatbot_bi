<script setup lang="ts">
import { maskCubeAddress, maskPowerBiUrl } from '~/utils/maskSensitive'

const SIDEBAR_KEY = 'bi-sources-sidebar-open-v1'

const {
  sources,
  selectedSeudonimo,
  cubeAddress,
  powerBiUrl,
  dictionaryPath,
  loading,
  loadError,
  hydrate,
  loadSources,
  selectSource,
  hasCube,
  hasPowerBi,
  hasDictionary,
} = useDataSources()

const open = useState('data-sources-sidebar-open', () => true)

const maskedCube = computed(() => maskCubeAddress(cubeAddress.value))
const maskedPowerBi = computed(() => maskPowerBiUrl(powerBiUrl.value))

onMounted(() => {
  hydrate()
  if (import.meta.client) {
    const stored = localStorage.getItem(SIDEBAR_KEY)
    if (stored === '0') open.value = false
    if (stored === '1') open.value = true
  }
})

watch(open, (value) => {
  if (import.meta.client) {
    localStorage.setItem(SIDEBAR_KEY, value ? '1' : '0')
  }
})

function labelFor(seudonimo: string): string {
  return seudonimo.replace(/_/g, ' ')
}

function statusFor(row: {
  ruta_cubo: string | null
  ruta_power_bi: string | null
  ruta_diccionario?: string | null
  diccionario_existe?: boolean
}): string {
  const parts: string[] = []
  if (row.ruta_cubo) parts.push('cubo')
  if (row.ruta_power_bi) parts.push('Power BI')
  if (row.ruta_diccionario) {
    parts.push(row.diccionario_existe === false ? 'diccionario (falta archivo)' : 'diccionario')
  }
  return parts.length ? parts.join(' · ') : 'sin rutas (None)'
}

function closeSidebar() {
  open.value = false
}
</script>

<template>
  <!-- Rail estrecho cuando está oculto -->
  <aside
    v-if="!open"
    class="flex w-11 shrink-0 flex-col items-center border-r border-brand-light bg-white py-3"
  >
    <button
      type="button"
      class="flex h-9 w-9 items-center justify-center rounded-lg text-brand-blue hover:bg-[#E8F7FC]"
      title="Mostrar fuentes"
      aria-label="Mostrar fuentes"
      @click="open = true"
    >
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.75" d="M4 6h16M4 12h10M4 18h14" />
      </svg>
    </button>
    <span
      class="mt-3 origin-center rotate-180 text-[10px] font-semibold tracking-wide text-[#9CA3AF]"
      style="writing-mode: vertical-rl"
    >
      Fuentes
    </span>
  </aside>

  <!-- Sidebar completo -->
  <aside
    v-else
    class="flex w-[280px] shrink-0 flex-col border-r border-brand-light bg-white"
  >
    <div class="flex items-start justify-between gap-2 border-b border-brand-light px-3 py-3">
      <div class="min-w-0">
        <h2 class="text-sm font-semibold text-brand-dark">
          Fuentes
        </h2>
        <p class="mt-0.5 text-[10px] leading-snug text-[#6B6B6A]">
          Catálogo CSV editable
        </p>
      </div>
      <button
        type="button"
        class="shrink-0 rounded-md p-1.5 text-[#6B6B6A] hover:bg-[#F4F6F8] hover:text-brand-dark"
        title="Ocultar panel"
        aria-label="Ocultar panel"
        @click="closeSidebar"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
    </div>

    <div class="flex items-center gap-2 border-b border-brand-light px-3 py-2">
      <button
        type="button"
        class="flex-1 rounded-lg border border-brand-light bg-white px-2 py-1.5 text-[11px] font-semibold text-brand-dark hover:bg-[#F4F6F8] disabled:opacity-50"
        :disabled="loading"
        @click="loadSources"
      >
        {{ loading ? 'Cargando…' : 'Recargar CSV' }}
      </button>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
      <p v-if="loadError" class="text-[11px] text-red-600">
        {{ loadError }}
      </p>
      <p v-else-if="loading && !sources.length" class="text-[11px] text-[#6B6B6A]">
        Cargando fuentes…
      </p>
      <fieldset v-else class="space-y-2">
        <legend class="sr-only">Fuente activa</legend>
        <label
          v-for="row in sources"
          :key="row.seudonimo"
          class="flex cursor-pointer items-start gap-2.5 rounded-lg border px-2.5 py-2 transition"
          :class="selectedSeudonimo === row.seudonimo
            ? 'border-brand-blue bg-[#E8F7FC]'
            : 'border-brand-light bg-white hover:border-brand-blue/40'"
        >
          <input
            type="radio"
            name="data-source"
            class="mt-1 h-3.5 w-3.5 accent-brand-blue"
            :value="row.seudonimo"
            :checked="selectedSeudonimo === row.seudonimo"
            @change="selectSource(row.seudonimo)"
          >
          <span class="min-w-0 flex-1">
            <span class="block text-xs font-semibold text-brand-dark">
              {{ labelFor(row.seudonimo) }}
            </span>
            <span class="mt-0.5 block font-mono text-[10px] text-[#9CA3AF]">
              {{ row.seudonimo }}
            </span>
            <span class="mt-0.5 block text-[10px] text-[#6B6B6A]">
              {{ statusFor(row) }}
            </span>
          </span>
        </label>
      </fieldset>
    </div>

    <div class="border-t border-brand-light px-3 py-3 text-[10px] text-[#6B6B6A]">
      <p v-if="selectedSeudonimo" class="font-semibold text-brand-dark">
        Activo: {{ selectedSeudonimo }}
      </p>
      <p v-if="!hasCube" class="mt-1 text-amber-700">
        Sin cubo configurado
      </p>
      <p v-else class="mt-1 break-all font-mono leading-snug" :title="maskedCube">
        {{ maskedCube }}
      </p>
      <p v-if="!hasPowerBi" class="mt-1 text-amber-700">
        Sin Power BI
      </p>
      <p v-else class="mt-1 break-all font-mono leading-snug" :title="maskedPowerBi">
        {{ maskedPowerBi }}
      </p>
      <p v-if="!hasDictionary" class="mt-1 text-amber-700">
        Sin diccionario
      </p>
      <p v-else class="mt-1 break-all font-mono leading-snug" :title="dictionaryPath">
        Diccionario: {{ dictionaryPath }}
      </p>
      <p class="mt-2 text-[9px] leading-snug text-[#9CA3AF]">
        Edite <code>agent_api/data/fuentes_datos.csv</code>
      </p>
    </div>
  </aside>
</template>
