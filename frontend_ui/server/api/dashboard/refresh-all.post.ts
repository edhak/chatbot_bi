import { agentPost } from '~/server/utils/agentApi'

export default defineEventHandler(async () => {
  return agentPost('/api/v1/dashboard/refresh-all')
})
