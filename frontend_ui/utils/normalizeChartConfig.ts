import type { EChartsOption } from 'echarts'

const SUPPORTED_TYPES = new Set([
  'bar',
  'line',
  'pie',
  'treemap',
  'heatmap',
  'scatter',
  'radar',
  'gauge',
  'funnel',
  'candlestick',
])

/**
 * Asegura que series sea un array y convierte tipos no registrados en ECharts del frontend.
 */
export function normalizeChartConfig(
  config: Record<string, unknown> | EChartsOption,
): EChartsOption {
  const option = { ...config } as EChartsOption
  const rawSeries = option.series
  const items = Array.isArray(rawSeries) ? rawSeries : rawSeries ? [rawSeries] : []

  const normalized = items
    .map((item) => {
      if (!item || typeof item !== 'object') return null
      const series = item as Record<string, unknown>
      const type = String(series.type ?? 'bar').toLowerCase()

      if (SUPPORTED_TYPES.has(type)) {
        return series
      }

      const data = Array.isArray(series.data) ? series.data : []
      const values: number[] = []
      const categories: string[] = []

      data.forEach((point, idx) => {
        if (point && typeof point === 'object' && 'value' in point) {
          const obj = point as { name?: string; value?: unknown }
          categories.push(String(obj.name ?? `Item ${idx + 1}`))
          values.push(Number(obj.value) || 0)
        } else {
          categories.push(String(idx + 1))
          values.push(Number(point) || 0)
        }
      })

      if (!values.length) return null

      if (!option.xAxis && categories.length) {
        option.xAxis = { type: 'category', data: categories }
        option.yAxis = { type: 'value' }
      }

      return {
        name: String(series.name ?? 'Valor'),
        type: 'bar',
        data: values,
      }
    })
    .filter(Boolean)

  option.series = normalized as EChartsOption['series']
  return option
}
