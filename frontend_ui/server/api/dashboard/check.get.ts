import { agentGet } from '~/server/utils/agentApi'

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const dax = String(query.dax_query ?? '').trim()
  if (!dax) {
    throw createError({ statusCode: 400, statusMessage: 'dax_query requerido.' })
  }
  return agentGet<{ included: boolean; item_id: string | null }>(
    '/api/v1/dashboard/check',
    { dax_query: dax },
  )
})
