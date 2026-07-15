import { agentGet } from '~/server/utils/agentApi'

export default defineEventHandler(async () => {
  const config = useRuntimeConfig()
  const cube = config.defaultCubeAddress as string
  const data = await agentGet<{ items: unknown[]; count: number }>(
    '/api/v1/dashboard',
    { cube_address: cube },
  )
  return data
})
