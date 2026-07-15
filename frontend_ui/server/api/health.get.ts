import { probeAgentHealth } from '../utils/fetchAgent'

export default defineEventHandler(async () => {
  const config = useRuntimeConfig()
  const agentApiUrl = config.agentApiUrl as string
  const gateway = process.env.DOCKER_GATEWAY ?? null
  const hostIp = process.env.HOST_IP ?? null

  const probe = await probeAgentHealth(agentApiUrl)

  return {
    bff: 'ok',
    agentApiUrl,
    dockerGateway: gateway,
    hostIp,
    backendReachable: probe.ok,
    backendUrl: probe.usedUrl ?? null,
    errors: probe.errors,
    hint: probe.ok
      ? null
      : 'Inicie el backend con: uvicorn agent_api.main:app --host 0.0.0.0 --port 8000. Si usa Docker, ejecute scripts\\docker-up.ps1',
  }
})
