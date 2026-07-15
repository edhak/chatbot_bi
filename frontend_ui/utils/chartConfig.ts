/**
 * Determina si hay un gráfico ECharts renderizable.
 */
export function hasValidChartConfig(
  config: Record<string, unknown> | undefined | null,
): boolean {
  if (!config || typeof config !== 'object') return false

  const series = config.series
  if (!series) return false

  const items = Array.isArray(series) ? series : [series]

  return items.some((item) => {
    if (!item || typeof item !== 'object') return false
    const data = (item as { data?: unknown }).data
    if (!Array.isArray(data) || data.length === 0) return false
    const type = String((item as { type?: string }).type ?? 'bar').toLowerCase()
    if (type === 'pie') {
      return data.some((d) => d !== null && d !== undefined)
    }
    return data.some((d) => d !== null && d !== undefined && d !== '')
  })
}

const DAX_MARKERS = [
  'EVALUATE',
  'SUMMARIZECOLUMNS',
  'COUNTROWS(',
  'TOPN(',
  'ORDER BY',
  'DEFINE',
  'VAR ',
  "'BI_FLOTHS",
  'MOD01_EQUIPO',
]

export function looksLikeDax(text: string): boolean {
  const stripped = text.trim()
  if (!stripped) return true
  const upper = stripped.toUpperCase()
  return DAX_MARKERS.some((marker) => upper.includes(marker))
}

export function sanitizeChartTitle(
  text: string | undefined | null,
  fallback = 'Indicador BI',
): string {
  if (!text?.trim()) return fallback
  const cleaned = text.trim().replace(/^\*\*|\*\*$/g, '').replace(/^#+\s*/, '').trim()
  if (!cleaned || looksLikeDax(cleaned) || cleaned.startsWith('```')) {
    return fallback
  }
  return cleaned.slice(0, 120)
}

export function resolveChartTitle(
  chartConfig: Record<string, unknown> | undefined,
  options?: { narrative?: string; question?: string },
): string {
  const raw = chartConfig?.title
  if (raw && typeof raw === 'object' && raw !== null && 'text' in raw) {
    const fromConfig = sanitizeChartTitle(String((raw as { text: string }).text), '')
    if (fromConfig) return fromConfig
  }

  if (options?.narrative) {
    for (const line of options.narrative.split('\n')) {
      const candidate = sanitizeChartTitle(line, '')
      if (candidate) return candidate
    }
  }

  const fromQuestion = sanitizeChartTitle(options?.question, '')
  if (fromQuestion) return fromQuestion

  return 'Indicador BI'
}
