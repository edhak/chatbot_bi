import { agentPost } from '~/server/utils/agentApi'

export default defineEventHandler(async (event) => {
  const body = await readBody<{
    title?: string
    question?: string
    dax_query?: string
    cube_address?: string
    seudonimo?: string
  }>(event)

  if (!body?.title?.trim() || !body?.dax_query?.trim()) {
    throw createError({
      statusCode: 400,
      detail: 'title y dax_query son obligatorios.',
      statusMessage: 'title y dax_query son obligatorios.',
    })
  }

  return agentPost('/api/v1/dashboard', {
    title: body.title.trim(),
    question: body.question?.trim() ?? '',
    dax_query: body.dax_query.trim(),
    cube_address: body.cube_address?.trim() || undefined,
    seudonimo: body.seudonimo?.trim() || undefined,
  })
})
