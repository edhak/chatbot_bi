import type { EChartsOption } from 'echarts'
import { fetchAgentQuery, type DebugLogEntry } from '../utils/fetchAgent'

const MAX_MESSAGE_LENGTH = 500

function pushLog(logs: DebugLogEntry[], step: string, message: string, level = 'info', elapsed_ms = 0) {
  logs.push({ step, message, level, elapsed_ms })
}

export default defineEventHandler(async (event) => {
  const bffLogs: DebugLogEntry[] = []
  const t0 = Date.now()
  pushLog(bffLogs, 'bff', 'Recibida petición del navegador')

  const body = await readBody<{
    message?: string
    cube_address?: string
    seudonimo?: string
    dictionary_path?: string
  }>(event)

  if (!body?.message?.trim()) {
    throw createError({ statusCode: 400, statusMessage: 'El campo "message" es obligatorio.' })
  }

  const message = body.message.trim()
  if (message.length > MAX_MESSAGE_LENGTH) {
    throw createError({
      statusCode: 400,
      statusMessage: `La pregunta no puede superar ${MAX_MESSAGE_LENGTH} caracteres.`,
    })
  }

  const config = useRuntimeConfig()
  const chatTimeoutMs = Number(config.chatTimeoutMs || process.env.CHAT_TIMEOUT_MS || 125_000)
  const agentApiUrl = config.agentApiUrl as string
  // Solo el cubo de la fuente seleccionada (NO forzar DEFAULT_CUBE_ADDRESS aquí)
  const cubeAddress = body.cube_address?.trim() || ''
  const seudonimo = body.seudonimo?.trim() || undefined
  const dictionaryPath = body.dictionary_path?.trim() || undefined

  if (!cubeAddress && process.env.SSAS_USE_MOCK !== 'true') {
    pushLog(
      bffLogs,
      'bff',
      'Sin ruta_cubo en la fuente; el backend resolverá por seudónimo o DEFAULT',
      'warn',
      Date.now() - t0,
    )
  }
  pushLog(bffLogs, 'bff', `URL primaria: ${agentApiUrl}`, 'info', Date.now() - t0)
  if (seudonimo) {
    pushLog(bffLogs, 'bff', `Fuente: ${seudonimo}`, 'info', Date.now() - t0)
  }
  if (dictionaryPath) {
    pushLog(bffLogs, 'bff', `Diccionario: ${dictionaryPath}`, 'info', Date.now() - t0)
  }
  if (process.env.DOCKER_GATEWAY) {
    pushLog(bffLogs, 'bff', `Gateway Docker: ${process.env.DOCKER_GATEWAY}`, 'info', Date.now() - t0)
  }
  if (process.env.HOST_IP) {
    pushLog(bffLogs, 'bff', `HOST_IP: ${process.env.HOST_IP}`, 'info', Date.now() - t0)
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), chatTimeoutMs)

  try {
    const { data: response, usedUrl } = await fetchAgentQuery(
      agentApiUrl,
      {
        question: message,
        cube_address: cubeAddress,
        seudonimo,
        dictionary_path: dictionaryPath,
      },
      controller.signal,
      (message, level = 'info') => pushLog(bffLogs, 'bff', message, level, Date.now() - t0),
    )

    pushLog(bffLogs, 'bff', `Conectado vía ${usedUrl}`, 'info', Date.now() - t0)
    pushLog(
      bffLogs,
      'bff',
      `Backend respondió en ${response.elapsed_ms ?? '?'}ms`,
      'info',
      Date.now() - t0,
    )

    const mergedLogs = [...bffLogs, ...(response.debug_log ?? [])]
    const chartConfig = (response.echarts_config ?? {}) as Record<string, unknown>
    const series = chartConfig.series
    const seriesItems = Array.isArray(series) ? series : series ? [series] : []
    const hasSeriesData = seriesItems.some((item) => {
      if (!item || typeof item !== 'object') return false
      const data = (item as { data?: unknown }).data
      return Array.isArray(data) && data.length > 0
    })
    const payload = {
      text: response.text_response || '(Respuesta vacía del backend)',
      dax: response.dax_query,
      chartConfig,
      debugLog: mergedLogs,
      elapsedMs: Date.now() - t0,
      hasChart: hasSeriesData,
      textLength: (response.text_response || '').length,
    }

    console.info(
      `[BFF] Enviando respuesta al navegador (${payload.textLength} chars, chart=${hasSeriesData}, series=${seriesItems.length}, ${payload.elapsedMs}ms)`,
    )
    return payload
  } catch (error: unknown) {
    let errMsg = 'Error desconocido al comunicarse con el agente analítico.'
    let statusCode = 500

    if (error && typeof error === 'object') {
      const fetchError = error as { name?: string; message?: string }
      if (fetchError.name === 'AbortError') {
        errMsg = `Timeout del BFF (${chatTimeoutMs / 1000}s). El backend no respondió a tiempo.`
        statusCode = 504
      } else {
        errMsg = fetchError.message ?? errMsg
      }
    }

    pushLog(bffLogs, 'bff', errMsg, 'error', Date.now() - t0)
    console.error(`[BFF] Error final: ${errMsg}`)

    throw createError({
      statusCode,
      statusMessage: 'Error al procesar la consulta.',
      data: { detail: errMsg, debugLog: bffLogs },
    })
  } finally {
    clearTimeout(timeout)
  }
})
