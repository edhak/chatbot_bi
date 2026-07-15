<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, ref, watch } from 'vue'
import { applyBrandChartTheme } from '~/utils/brandTheme'
import { normalizeChartConfig } from '~/utils/normalizeChartConfig'
import {
  applyChartFilters,
  createDefaultFilterState,
  detectChartFilters,
  type ChartFilterDef,
  type ChartFilterState,
  type SortOrder,
} from '~/utils/chartFilters'

const props = defineProps<{
  config: EChartsOption | Record<string, unknown>
}>()

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

watch(
  () => props.config,
  (config) => {
    initFilters(config as EChartsOption)
  },
  { immediate: true, deep: true },
)

const chartOption = computed(() => {
  const base = normalizeChartConfig(props.config as Record<string, unknown>)
  const filtered = applyChartFilters(base, filterState.value)
  return applyBrandChartTheme(filtered)
})

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
  initFilters(props.config as EChartsOption)
}
</script>

<template>
  <div class="chart-with-filters">
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
            class="rounded-md border border-brand-light bg-[#F4F6F8] px-2 py-1.5 text-xs text-brand-dark outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
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
            class="rounded-md border border-brand-light bg-[#F4F6F8] px-2 py-1.5 text-xs text-brand-dark placeholder-[#9CA3AF] outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
          />
        </div>

        <div v-else-if="filter.type === 'sortOrder'" class="flex flex-col gap-1">
          <label class="text-[10px] font-semibold uppercase tracking-wider text-[#6B6B6A]">
            {{ filter.label }}
          </label>
          <select
            :value="filterState.sortOrder"
            class="rounded-md border border-brand-light bg-[#F4F6F8] px-2 py-1.5 text-xs text-brand-dark outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
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
              :class="
                filterState.visibleSeries[name]
                  ? 'bg-brand-blue text-white'
                  : 'border border-brand-light bg-[#F4F6F8] text-[#6B6B6A]'
              "
              @click="toggleSeries(name)"
            >
              {{ name }}
            </button>
          </div>
        </div>
      </template>

      <button
        type="button"
        class="ml-auto rounded-md border border-brand-light px-2.5 py-1.5 text-[11px] text-[#6B6B6A] transition hover:border-brand-blue hover:text-brand-blue"
        @click="resetFilters"
      >
        Restablecer
      </button>
    </div>

    <v-chart class="h-80 w-full" :option="chartOption" autoresize />
  </div>
</template>
