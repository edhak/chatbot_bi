import type { EChartsOption } from 'echarts'

export interface DebugLogEntry {
  step: string
  message: string
  level: string
  elapsed_ms: number
}

export interface AgentQueryResult {
  text_response: string
  dax_query: string
  echarts_config: EChartsOption
  debug_log?: DebugLogEntry[]
  elapsed_ms?: number
}

type AttemptLogger = (message: string, level?: string) => void

function candidateAgentUrls(primary: string): string[] {
  const gateway = process.env.DOCKER_GATEWAY?.trim()
  const hostIp = process.env.HOST_IP?.trim()

  const urls = new Set<string>([
    primary,
    process.env.AGENT_API_URL?.trim(),
    gateway ? `http://${gateway}:8000` : '',
    hostIp ? `http://${hostIp}:8000` : '',
    'http://host.docker.internal:8000',
    'http://gateway.docker.internal:8000',
    'http://172.17.0.1:8000',
    'http://172.18.0.1:8000',
  ])

  return [...urls].filter((u) => u && u.startsWith('http'))
}

export async function fetchAgentQuery(
  agentApiUrl: string,
  body: { question: string; cube_address: string },
  signal: AbortSignal,
  onAttempt?: AttemptLogger,
): Promise<{ data: AgentQueryResult; usedUrl: string }> {
  const urls = candidateAgentUrls(agentApiUrl)
  const errors: string[] = []

  if (urls.length === 0) {
    throw new Error('Sin URLs de backend configuradas')
  }

  onAttempt?.(`Probando ${urls.length} URLs: ${urls.join(', ')}`)

  for (const baseUrl of urls) {
    const url = `${baseUrl.replace(/\/$/, '')}/api/v1/query`
    onAttempt?.(`Intentando ${url}`)
    console.info(`[BFF] Intentando backend: ${url}`)

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Connection: 'close',
        },
        body: JSON.stringify(body),
        signal,
      })

      if (!response.ok) {
        const errText = await response.text()
        const err = `[${response.status}] ${errText.slice(0, 200)}`
        errors.push(`${baseUrl}: ${err}`)
        onAttempt?.(`Falló ${baseUrl}: ${err}`, 'warn')
        console.warn(`[BFF] Backend error en ${url}: ${err}`)
        continue
      }

      const data = (await response.json()) as AgentQueryResult
      onAttempt?.(`OK vía ${baseUrl} (${data.text_response?.length ?? 0} chars)`)
      console.info(
        `[BFF] OK ${url} | text=${data.text_response?.length ?? 0} chars | chart=${Boolean(data.echarts_config?.series)}`,
      )
      return { data, usedUrl: baseUrl }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error)
      errors.push(`${baseUrl}: ${msg}`)
      onAttempt?.(`Falló ${baseUrl}: ${msg}`, 'warn')
      console.warn(`[BFF] Falló ${url}: ${msg}`)
    }
  }

  const hint = [
    'El contenedor Docker no alcanza el backend en el puerto 8000.',
    'Verifique: 1) uvicorn --host 0.0.0.0 --port 8000',
    '2) Firewall Windows permite puerto 8000 desde Docker',
    '3) Ejecute scripts\\docker-up.ps1 o use scripts\\run_frontend.bat sin Docker',
  ].join(' ')

  throw new Error(`${errors.join(' | ')}. ${hint}`)
}

export async function probeAgentHealth(
  agentApiUrl: string,
): Promise<{ ok: boolean; usedUrl?: string; errors: string[] }> {
  const urls = candidateAgentUrls(agentApiUrl)
  const errors: string[] = []

  for (const baseUrl of urls) {
    const url = `${baseUrl.replace(/\/$/, '')}/health`
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(5000) })
      if (response.ok) {
        return { ok: true, usedUrl: baseUrl, errors }
      }
      errors.push(`${baseUrl}: HTTP ${response.status}`)
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error)
      errors.push(`${baseUrl}: ${msg}`)
    }
  }

  return { ok: false, errors }
}
