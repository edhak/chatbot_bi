import { agentPost, defaultCubeBody } from '~/server/utils/agentApi'

export default defineEventHandler(async (event) => {
  const body = await readBody<{
    title?: string
    question?: string
    dax_query?: string
  }>(event)

  if (!body?.title?.trim() || !body?.dax_query?.trim()) {
    throw createError({
      statusCode: 400,
      statusMessage: 'title y dax_query son obligatorios.',
    })
  }

  return agentPost('/api/v1/dashboard', {
    title: body.title.trim(),
    question: body.question?.trim() ?? '',
    dax_query: body.dax_query.trim(),
    ...defaultCubeBody(),
  })
})
