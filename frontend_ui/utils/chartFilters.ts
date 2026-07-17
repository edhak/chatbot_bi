import type { EChartsOption } from 'echarts'

export type SortOrder = 'original' | 'desc' | 'asc'

export interface SeriesToggleFilter {
  type: 'seriesToggle'
  label: string
  series: string[]
}

export interface TopNFilter {
  type: 'topN'
  label: string
  options: number[]
  default: number
}

export interface CategorySearchFilter {
  type: 'categorySearch'
  label: string
  placeholder: string
}

export interface SortOrderFilter {
  type: 'sortOrder'
  label: string
}

export type ChartFilterDef =
  | SeriesToggleFilter
  | TopNFilter
  | CategorySearchFilter
  | SortOrderFilter

export interface ChartFilterState {
  topN: number
  categorySearch: string
  visibleSeries: Record<string, boolean>
  sortOrder: SortOrder
}

interface SeriesItem {
  name: string
  type: string
  data: number[]
}

interface ChartDataset {
  kind: 'category' | 'pie' | 'treemap' | 'heatmap' | 'none'
  categories: string[]
  series: SeriesItem[]
  pieItems: Array<{ name: string; value: number }>
  treemapItems: Array<{ name: string; value: number }>
  categoryAxis: 'x' | 'y'
}

function asArray<T>(value: T | T[] | undefined): T[] {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

function toNumber(value: unknown): number {
  if (typeof value === 'number') return value
  if (typeof value === 'string') return Number(value) || 0
  if (value && typeof value === 'object' && 'value' in value) {
    return toNumber((value as { value: unknown }).value)
  }
  return 0
}

function emptyDataset(kind: ChartDataset['kind'] = 'none'): ChartDataset {
  return {
    kind,
    categories: [],
    series: [],
    pieItems: [],
    treemapItems: [],
    categoryAxis: 'x',
  }
}

function extractDataset(option: EChartsOption): ChartDataset {
  const rawSeriesList = asArray(option.series)

  const heatmapRaw = rawSeriesList.find(
    (item) => String((item as { type?: string })?.type ?? '').toLowerCase() === 'heatmap',
  )
  if (heatmapRaw) {
    return emptyDataset('heatmap')
  }

  const noFilterTypes = new Set(['gauge', 'radar', 'funnel', 'scatter', 'candlestick'])
  const specialRaw = rawSeriesList.find((item) =>
    noFilterTypes.has(String((item as { type?: string })?.type ?? '').toLowerCase()),
  )
  if (specialRaw) {
    return emptyDataset('none')
  }

  const seriesList = rawSeriesList.map((item) => {
    const raw = item as Record<string, unknown>
    const data = Array.isArray(raw.data) ? raw.data.map(toNumber) : []
    return {
      name: String(raw.name ?? 'Serie'),
      type: String(raw.type ?? 'bar'),
      data,
    }
  })

  const pieSeries = seriesList.find((s) => s.type === 'pie')
  if (pieSeries) {
    const rawSeries = rawSeriesList[0] as Record<string, unknown>
    const pieItems = Array.isArray(rawSeries?.data)
      ? (rawSeries.data as Array<Record<string, unknown>>).map((item) => ({
          name: String(item.name ?? ''),
          value: toNumber(item.value),
        }))
      : []
    return { ...emptyDataset('pie'), pieItems }
  }

  const treemapSeries = seriesList.find((s) => s.type === 'treemap')
  if (treemapSeries) {
    const rawSeries = rawSeriesList[0] as Record<string, unknown>
    const treemapItems = Array.isArray(rawSeries?.data)
      ? (rawSeries.data as Array<Record<string, unknown>>).map((item) => ({
          name: String(item.name ?? ''),
          value: toNumber(item.value),
        }))
      : []
    return { ...emptyDataset('treemap'), treemapItems }
  }

  const xAxes = asArray(option.xAxis)
  const yAxes = asArray(option.yAxis)

  const xCategory = xAxes.find((axis) => (axis as { type?: string }).type === 'category')
  const yCategory = yAxes.find((axis) => (axis as { type?: string }).type === 'category')

  if (yCategory && Array.isArray((yCategory as { data?: unknown }).data)) {
    return {
      kind: 'category',
      categories: ((yCategory as { data: unknown[] }).data).map(String),
      series: seriesList,
      pieItems: [],
      treemapItems: [],
      categoryAxis: 'y',
    }
  }

  if (xCategory && Array.isArray((xCategory as { data?: unknown }).data)) {
    return {
      kind: 'category',
      categories: ((xCategory as { data: unknown[] }).data).map(String),
      series: seriesList,
      pieItems: [],
      treemapItems: [],
      categoryAxis: 'x',
    }
  }

  if (seriesList.length > 0 && seriesList[0].data.length > 0) {
    const length = Math.max(...seriesList.map((s) => s.data.length))
    return {
      kind: 'category',
      categories: Array.from({ length }, (_, i) => `Item ${i + 1}`),
      series: seriesList,
      pieItems: [],
      treemapItems: [],
      categoryAxis: 'x',
    }
  }

  return emptyDataset('none')
}

export function detectChartFilters(option: EChartsOption): ChartFilterDef[] {
  const dataset = extractDataset(option)
  const filters: ChartFilterDef[] = []

  if (dataset.kind === 'category') {
    const count = dataset.categories.length
    const seriesNames = dataset.series.map((s) => s.name)

    if (count >= 4) {
      const steps = [5, 10, 15, 20].filter((n) => n < count)
      filters.push({
        type: 'topN',
        label: 'Mostrar',
        options: [...steps, count],
        default: Math.min(10, count),
      })
      filters.push({
        type: 'categorySearch',
        label: 'Buscar',
        placeholder: 'Filtrar categoría...',
      })
    }

    if (count >= 2 && dataset.series.some((s) => s.type === 'bar' || s.type === 'line')) {
      filters.push({ type: 'sortOrder', label: 'Ordenar' })
    }

    if (seriesNames.length > 1) {
      filters.push({
        type: 'seriesToggle',
        label: 'Series',
        series: seriesNames,
      })
    }
  }

  if (dataset.kind === 'pie' && dataset.pieItems.length >= 4) {
    const count = dataset.pieItems.length
    const steps = [5, 8, 10].filter((n) => n < count)
    filters.push({
      type: 'topN',
      label: 'Segmentos',
      options: [...steps, count],
      default: Math.min(8, count),
    })
  }

  if (dataset.kind === 'treemap' && dataset.treemapItems.length >= 7) {
    const count = dataset.treemapItems.length
    const steps = [8, 12, 20].filter((n) => n < count)
    filters.push({
      type: 'topN',
      label: 'Áreas',
      options: [...steps, count],
      default: Math.min(12, count),
    })
  }

  // Heatmap: sin filtros de topN (rompe la matriz); se deja la visualMap del backend.
  return filters
}

export function createDefaultFilterState(filters: ChartFilterDef[]): ChartFilterState {
  const state: ChartFilterState = {
    topN: 9999,
    categorySearch: '',
    visibleSeries: {},
    sortOrder: 'original',
  }

  for (const filter of filters) {
    if (filter.type === 'topN') state.topN = filter.default
    if (filter.type === 'seriesToggle') {
      for (const name of filter.series) state.visibleSeries[name] = true
    }
  }

  return state
}

function sortIndices(values: number[], order: SortOrder): number[] {
  const indices = values.map((_, i) => i)
  if (order === 'original') return indices
  indices.sort((a, b) => (order === 'desc' ? values[b] - values[a] : values[a] - values[b]))
  return indices
}

function filterCategoryDataset(
  dataset: ChartDataset,
  state: ChartFilterState,
): { categories: string[]; series: SeriesItem[] } {
  let categories = [...dataset.categories]
  let series = dataset.series.map((s) => ({ ...s, data: [...s.data] }))

  if (state.categorySearch.trim()) {
    const term = state.categorySearch.trim().toLowerCase()
    const indices = categories
      .map((cat, i) => (cat.toLowerCase().includes(term) ? i : -1))
      .filter((i) => i >= 0)
    categories = indices.map((i) => categories[i])
    series = series.map((s) => ({ ...s, data: indices.map((i) => s.data[i] ?? 0) }))
  }

  if (state.sortOrder !== 'original' && series.length > 0) {
    const base = series[0].data
    const indices = sortIndices(base, state.sortOrder)
    categories = indices.map((i) => categories[i])
    series = series.map((s) => ({ ...s, data: indices.map((i) => s.data[i] ?? 0) }))
  }

  if (state.topN < categories.length) {
    categories = categories.slice(0, state.topN)
    series = series.map((s) => ({ ...s, data: s.data.slice(0, state.topN) }))
  }

  series = series.filter((s) => state.visibleSeries[s.name] !== false)

  return { categories, series }
}

function filterTreemapDataset(
  dataset: ChartDataset,
  state: ChartFilterState,
): Array<{ name: string; value: number }> {
  const sorted = [...dataset.treemapItems].sort((a, b) => b.value - a.value)
  if (state.topN >= sorted.length) return sorted
  return sorted.slice(0, state.topN)
}

function filterPieDataset(
  dataset: ChartDataset,
  state: ChartFilterState,
): Array<{ name: string; value: number }> {
  const sorted = [...dataset.pieItems].sort((a, b) => b.value - a.value)
  if (state.topN >= sorted.length) return sorted

  const top = sorted.slice(0, state.topN)
  const rest = sorted.slice(state.topN)
  const othersValue = rest.reduce((sum, item) => sum + item.value, 0)
  if (othersValue > 0) top.push({ name: 'Otros', value: othersValue })
  return top
}

function withDataZoom(option: EChartsOption, categoryCount: number, axis: 'x' | 'y'): EChartsOption {
  if (categoryCount <= 8) return option

  const existing = asArray(option.dataZoom)
  if (existing.length > 0) return option

  const isHorizontal = axis === 'y'
  return {
    ...option,
    grid: {
      ...(typeof option.grid === 'object' && !Array.isArray(option.grid) ? option.grid : {}),
      bottom: isHorizontal ? '8%' : '14%',
    },
    dataZoom: [
      {
        type: 'slider',
        [isHorizontal ? 'yAxisIndex' : 'xAxisIndex']: 0,
        height: isHorizontal ? undefined : 18,
        width: isHorizontal ? 18 : undefined,
        bottom: isHorizontal ? undefined : 4,
        right: isHorizontal ? 4 : undefined,
        borderColor: '#DDE1E5',
        fillerColor: 'rgba(4, 150, 205, 0.15)',
        handleStyle: { color: '#0496CD' },
        textStyle: { color: '#6B6B6A', fontSize: 10 },
      },
      {
        type: 'inside',
        [isHorizontal ? 'yAxisIndex' : 'xAxisIndex']: 0,
      },
    ],
  }
}

export function applyChartFilters(
  option: EChartsOption,
  state: ChartFilterState,
): EChartsOption {
  const dataset = extractDataset(option)
  const result = structuredClone(option) as EChartsOption

  if (dataset.kind === 'category' && dataset.categories.length > 0) {
    const { categories, series } = filterCategoryDataset(dataset, state)

    if (dataset.categoryAxis === 'y') {
      result.yAxis = asArray(result.yAxis).map((axis, i) =>
        i === 0 ? { ...(axis as object), data: categories } : axis,
      )
    } else {
      result.xAxis = asArray(result.xAxis).map((axis, i) =>
        i === 0 ? { ...(axis as object), data: categories } : axis,
      )
    }

    result.series = asArray(result.series)
      .map((item) => {
        const name = String((item as { name?: string }).name ?? 'Serie')
        const match = series.find((s) => s.name === name)
        if (!match) return null
        return { ...(item as object), data: match.data }
      })
      .filter(Boolean) as EChartsOption['series']

    return withDataZoom(result, categories.length, dataset.categoryAxis)
  }

  if (dataset.kind === 'pie' && dataset.pieItems.length > 0) {
    const pieData = filterPieDataset(dataset, state)
    result.series = asArray(result.series).map((item, i) =>
      i === 0 ? { ...(item as object), data: pieData } : item,
    )
    return result
  }

  if (dataset.kind === 'treemap' && dataset.treemapItems.length > 0) {
    const treemapData = filterTreemapDataset(dataset, state)
    result.series = asArray(result.series).map((item, i) =>
      i === 0 ? { ...(item as object), data: treemapData } : item,
    )
    return result
  }

  if (dataset.kind === 'heatmap') {
    return result
  }

  return result
}

export function hasChartFilters(option: EChartsOption): boolean {
  return detectChartFilters(option).length > 0
}
