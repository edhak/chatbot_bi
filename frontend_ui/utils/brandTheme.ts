import type { EChartsOption } from 'echarts'

/** Colores del UI — solo para ejes, textos y contenedor del gráfico */
const UI = {
  text: '#3C3C3B',
  textMuted: '#6B6B6A',
  border: '#DDE1E5',
  surface: '#FAFBFC',
  tooltipBg: '#FFFFFF',
} as const

/** Paleta neutra de respaldo solo si el agente no define colores de serie */
const LIGHT_BG_SERIES_FALLBACK = [
  '#4A7C9B',
  '#6B8F71',
  '#8B7E9B',
  '#C4925A',
  '#5B8A9A',
  '#9A7B6B',
  '#7A8FA6',
  '#5C7A6E',
] as const

const axisDefaults = {
  axisLine: { lineStyle: { color: UI.border } },
  axisLabel: { color: UI.textMuted },
  splitLine: { lineStyle: { color: UI.border, type: 'dashed' as const } },
}

function asArray<T>(value: T | T[] | undefined): T[] {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

function seriesItems(option: EChartsOption): Record<string, unknown>[] {
  return asArray(option.series).filter(
    (item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'),
  )
}

function isHorizontalBar(option: EChartsOption): boolean {
  return asArray(option.yAxis).some(
    (axis) => axis && typeof axis === 'object' && (axis as { type?: string }).type === 'category',
  )
}

function legendSeriesNames(option: EChartsOption): string[] {
  const names: string[] = []
  for (const item of seriesItems(option)) {
    const type = String(item.type ?? 'bar').toLowerCase()
    if (type === 'pie') {
      const data = Array.isArray(item.data) ? item.data : []
      for (const point of data) {
        if (point && typeof point === 'object' && 'name' in point && point.name) {
          names.push(String(point.name))
        }
      }
      if (!names.length && item.name) names.push(String(item.name))
    } else if (item.name) {
      names.push(String(item.name))
    }
  }
  return names
}

/**
 * Leyenda siempre abajo o a la derecha; título arriba centrado sin solaparse.
 */
export function applyLegendLayout(option: EChartsOption): EChartsOption {
  const result = { ...option } as EChartsOption
  const items = seriesItems(result)
  if (!items.length) return result

  const hasPie = items.some((s) => String(s.type ?? '').toLowerCase() === 'pie')
  const multiSeries = items.length > 1
  const legendNames = legendSeriesNames(result)
  const needsLegend = hasPie || multiSeries || legendNames.length > 1

  if (typeof result.title === 'object' && !Array.isArray(result.title)) {
    result.title = {
      ...result.title,
      left: result.title.left ?? 'center',
      top: result.title.top ?? 8,
      textStyle: {
        fontSize: 14,
        fontWeight: 600,
        color: UI.text,
        ...result.title.textStyle,
      },
    }
  }

  const baseGrid =
    typeof result.grid === 'object' && !Array.isArray(result.grid)
      ? { ...result.grid }
      : {}

  const grid: Record<string, unknown> = {
    left: '3%',
    right: '4%',
    containLabel: true,
    top: 52,
    ...baseGrid,
  }

  if (!needsLegend) {
    result.legend = { show: false }
    grid.bottom = grid.bottom ?? '8%'
    result.grid = grid as EChartsOption['grid']
    return result
  }

  const useRight = isHorizontalBar(result) && (multiSeries || legendNames.length > 4)

  if (useRight) {
    result.legend = {
      show: true,
      type: 'scroll',
      orient: 'vertical',
      right: 8,
      top: 'middle',
      data: legendNames.length ? legendNames : undefined,
      textStyle: { color: UI.text, fontSize: 11 },
    }
    grid.right = '16%'
    grid.bottom = grid.bottom ?? '10%'
  } else {
    result.legend = {
      show: true,
      type: 'scroll',
      orient: 'horizontal',
      bottom: 8,
      left: 'center',
      data: legendNames.length ? legendNames : undefined,
      textStyle: { color: UI.text, fontSize: 11 },
    }
    const bottom = grid.bottom
    if (bottom === undefined || bottom === '3%' || bottom === '8%' || bottom === '10%') {
      grid.bottom = '14%'
    } else if (typeof bottom === 'number' && bottom < 40) {
      grid.bottom = 48
    }
  }

  result.grid = grid as EChartsOption['grid']
  return result
}

function styleAxis(axis: EChartsOption['xAxis'] | EChartsOption['yAxis']) {
  if (!axis) return axisDefaults

  const merge = (item: Record<string, unknown>) => ({
    ...item,
    axisLine: { ...(item.axisLine as object), lineStyle: { color: UI.border } },
    axisLabel: { ...(item.axisLabel as object), color: UI.textMuted },
    splitLine: {
      ...(item.splitLine as object),
      lineStyle: { color: UI.border, type: 'dashed' as const },
    },
  })

  return Array.isArray(axis)
    ? axis.map((item) => merge(item as Record<string, unknown>))
    : merge(axis as Record<string, unknown>)
}

/**
 * Armoniza el gráfico con el fondo claro del dashboard.
 * No sobrescribe la paleta de series que venga del agente.
 */
export function applyBrandChartTheme(option: EChartsOption): EChartsOption {
  const withLegend = applyLegendLayout(option)

  const tooltip =
    typeof withLegend.tooltip === 'object' && !Array.isArray(withLegend.tooltip)
      ? {
          ...withLegend.tooltip,
          backgroundColor: UI.tooltipBg,
          borderColor: UI.border,
          textStyle: { color: UI.text, ...withLegend.tooltip.textStyle },
        }
      : withLegend.tooltip

  return {
    ...withLegend,
    color: withLegend.color ?? [...LIGHT_BG_SERIES_FALLBACK],
    backgroundColor: 'transparent',
    textStyle: {
      fontFamily: 'Segoe UI, Inter, system-ui, sans-serif',
      color: UI.text,
      ...withLegend.textStyle,
    },
    tooltip,
    xAxis: styleAxis(withLegend.xAxis),
    yAxis: styleAxis(withLegend.yAxis),
  } as EChartsOption
}
