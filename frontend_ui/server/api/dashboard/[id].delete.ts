import { agentDelete } from '~/server/utils/agentApi'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'ID requerido.' })
  }
  return agentDelete(`/api/v1/dashboard/${id}`)
})
