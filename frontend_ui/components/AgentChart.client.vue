<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart, TreemapChart, HeatmapChart, ScatterChart, RadarChart, GaugeChart, FunnelChart, CandlestickChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  VisualMapComponent,
  RadarComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { computed, ref, shallowRef, watch } from 'vue'
import { applyBrandChartTheme } from '~/utils/brandTheme'
import { normalizeChartConfig } from '~/utils/normalizeChartConfig'
import { hasValidChartConfig, looksLikeDax, sanitizeChartTitle } from '~/utils/chartConfig'
import {
  applyChartFilters,
  createDefaultFilterState,
  detectChartFilters,
  type ChartFilterDef,
  type ChartFilterState,
  type SortOrder,
} from '~/utils/chartFilters'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  TreemapChart,
  HeatmapChart,
  ScatterChart,
  RadarChart,
  GaugeChart,
  FunnelChart,
  CandlestickChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  VisualMapComponent,
  RadarComponent,
])

const props = defineProps<{
  config: EChartsOption | Record<string, unknown>
  titleFallback?: string
}>()

const chartReady = ref(false)
const chartError = ref<string | null>(null)

/** Evita pasar Proxies reactivos a ECharts (causa render vacío). */
function toPlainOption(config: Record<string, unknown>): EChartsOption {
  return JSON.parse(JSON.stringify(config)) as EChartsOption
}

const plainConfig = shallowRef<EChartsOption>({})

watch(
  () => props.config,
  (config) => {
    chartReady.value = false
    chartError.value = null
    try {
      if (!hasValidChartConfig(config as Record<string, unknown>)) {
        chartError.value = 'Configuración de gráfico inválida'
        plainConfig.value = {}
        return
      }
      plainConfig.value = toPlainOption(config as Record<string, unknown>)
    } catch {
      chartError.value = 'No se pudo procesar el gráfico'
      plainConfig.value = {}
    }
  },
  { immediate: true, deep: true },
)

const filters = ref<ChartFilterDef[]>([])
const filterState = ref<ChartFilterState>({
  topN: 9999,
  categorySearch: '',
  visibleSeries: {},
  sortOrder: 'original',
})

function initFilters(config: EChartsOption) {
  const normalized = normalizeChartConfig(config as Record<string, unknown>)
  filters.value = detectChartFilters(normalized)
  filterState.value = createDefaultFilterState(filters.value)
}

watch(plainConfig, (config) => {
  if (config && Object.keys(config).length > 0) {
    initFilters(config)
  } else {
    filters.value = []
  }
}, { immediate: true })

const chartOption = computed(() => {
  if (!plainConfig.value || !Object.keys(plainConfig.value).length) {
    return null
  }
  const base = normalizeChartConfig(plainConfig.value as Record<string, unknown>)
  const filtered = applyChartFilters(base, filterState.value)
  const themed = applyBrandChartTheme(filtered)

  // chart_meta es metadata del backend; no lo envíe a ECharts
  const { chart_meta: _meta, ...clean } = themed as Record<string, unknown>

  const title = clean.title
  if (title && typeof title === 'object' && !Array.isArray(title) && 'text' in title) {
    const current = String((title as { text?: string }).text ?? '')
    if (looksLikeDax(current)) {
      const fallback = sanitizeChartTitle(props.titleFallback, 'Indicador BI')
      return { ...clean, title: { ...(title as object), text: fallback } } as EChartsOption
    }
  }

  return clean as EChartsOption
})

function onChartFinished() {
  chartReady.value = true
}

function setTopN(value: number) {
  filterState.value.topN = value
}

function setSortOrder(value: SortOrder) {
  filterState.value.sortOrder = value
}

function toggleSeries(name: string) {
  filterState.value.visibleSeries[name] = !filterState.value.visibleSeries[name]
}

function resetFilters() {
  initFilters(plainConfig.value)
}
</script>

<template>
  <div class="agent-chart">
    <p v-if="chartError" class="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
      {{ chartError }}
    </p>

    <template v-else-if="chartOption">
      <div
        v-if="filters.length > 0"
        class="mb-3 flex flex-wrap items-end gap-3 rounded-lg border border-brand-light bg-white px-3 py-2.5"
      >
        <template v-for="(filter, idx) in filters" :key="idx">
          <div v-if="filter.type === 'topN'" class="flex flex-col gap-1">
            <label class="text-[10px] font-semibold uppercase tracking-wider text-[#6B6B6A]">
              {{ filter.label }}
            </label>
            <select
              :value="filterState.topN"
              class="rounded-md border border-brand-light bg-[#F4F6F8] px-2 py-1.5 text-xs text-brand-dark outline-none focus:border-brand-blue"
              @change="setTopN(Number(($event.target as HTMLSelectElement).value))"
            >
              <option v-for="n in filter.options" :key="n" :value="n">
                {{ n === filter.options[filter.options.length - 1] ? `Todos (${n})` : `Top ${n}` }}
              </option>
            </select>
          </div>

          <div v-else-if="filter.type === 'categorySearch'" class="flex min-w-[160px] flex-1 flex-col gap-1">
            <label class="text-[10px] font-semibold uppercase tracking-wider text-[#6B6B6A]">
              {{ filter.label }}
            </label>
            <input
              v-model="filterState.categorySearch"
              type="text"
              :placeholder="filter.placeholder"
              class="rounded-md border border-brand-light bg-[#F4F6F8] px-2 py-1.5 text-xs text-brand-dark outline-none focus:border-brand-blue"
            />
          </div>

          <div v-else-if="filter.type === 'sortOrder'" class="flex flex-col gap-1">
            <label class="text-[10px] font-semibold uppercase tracking-wider text-[#6B6B6A]">
              {{ filter.label }}
            </label>
            <select
              :value="filterState.sortOrder"
              class="rounded-md border border-brand-light bg-[#F4F6F8] px-2 py-1.5 text-xs text-brand-dark outline-none focus:border-brand-blue"
              @change="setSortOrder(($event.target as HTMLSelectElement).value as SortOrder)"
            >
              <option value="original">Original</option>
              <option value="desc">Mayor a menor</option>
              <option value="asc">Menor a mayor</option>
            </select>
          </div>

          <div v-else-if="filter.type === 'seriesToggle'" class="flex flex-col gap-1">
            <label class="text-[10px] font-semibold uppercase tracking-wider text-[#6B6B6A]">
              {{ filter.label }}
            </label>
            <div class="flex flex-wrap gap-1">
              <button
                v-for="name in filter.series"
                :key="name"
                type="button"
                class="rounded-full px-2.5 py-1 text-[11px] transition"
                :class="filterState.visibleSeries[name]
                  ? 'bg-brand-blue text-white'
                  : 'border border-brand-light bg-[#F4F6F8] text-[#6B6B6A]'"
                @click="toggleSeries(name)"
              >
                {{ name }}
              </button>
            </div>
          </div>
        </template>

        <button
          type="button"
          class="ml-auto rounded-md border border-brand-light px-2.5 py-1.5 text-[11px] text-[#6B6B6A] hover:border-brand-blue hover:text-brand-blue"
          @click="resetFilters"
        >
          Restablecer
        </button>
      </div>

      <div class="chart-canvas-wrapper">
        <VChart
          :option="chartOption"
          autoresize
          class="chart-canvas"
          @finished="onChartFinished"
        />
      </div>
      <p v-if="!chartReady" class="mt-1 text-center text-[10px] text-[#9CA3AF]">
        Renderizando gráfico...
      </p>
    </template>
  </div>
</template>

<style scoped>
.chart-canvas-wrapper {
  width: 100%;
  min-height: 320px;
  height: 320px;
}

.chart-canvas {
  width: 100%;
  height: 320px;
  min-height: 320px;
}
</style>
