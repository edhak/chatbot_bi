import { agentPost, defaultCubeBody } from '~/server/utils/agentApi'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'ID requerido.' })
  }
  const cube = defaultCubeBody().cube_address
  return agentPost(`/api/v1/dashboard/${id}/refresh?cube_address=${encodeURIComponent(cube)}`)
})
