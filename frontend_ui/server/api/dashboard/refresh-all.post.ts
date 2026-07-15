import { agentPost, defaultCubeBody } from '~/server/utils/agentApi'

export default defineEventHandler(async () => {
  const cube = defaultCubeBody().cube_address
  return agentPost(`/api/v1/dashboard/refresh-all?cube_address=${encodeURIComponent(cube)}`)
})
