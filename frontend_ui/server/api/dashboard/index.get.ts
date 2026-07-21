import { agentGet } from '~/server/utils/agentApi'

export default defineEventHandler(async () => {
  // Cada indicador del dashboard conserva su propia fuente; no forzar cubo activo
  return agentGet('/api/v1/dashboard')
})
