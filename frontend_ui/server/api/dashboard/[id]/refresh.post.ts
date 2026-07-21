import { agentPost } from '~/server/utils/agentApi'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'id requerido' })
  }
  // Usa la fuente guardada en el ítem (no el cubo seleccionado en la UI)
  return agentPost(`/api/v1/dashboard/${id}/refresh`)
})
