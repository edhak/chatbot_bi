import { agentGet } from '~/server/utils/agentApi'

export default defineEventHandler(async () => {
  return agentGet('/api/v1/data-sources')
})
