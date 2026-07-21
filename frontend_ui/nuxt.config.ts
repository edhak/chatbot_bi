// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: process.env.NUXT_DEVTOOLS !== 'false' },

  experimental: {
    appManifest: false,
  },

  modules: ['@nuxtjs/tailwindcss'],

  css: ['~/assets/css/main.css'],

  app: {
    head: {
      title: 'BI Analytics',
      meta: [
        { name: 'description', content: 'Asistente de inteligencia de negocios multi-fuente (SSAS + Power BI)' },
      ],
    },
  },

  runtimeConfig: {
    agentApiUrl: process.env.AGENT_API_URL || 'http://localhost:8000',
    defaultCubeAddress: process.env.DEFAULT_CUBE_ADDRESS || '',
    allowClientCubeAddress: process.env.ALLOW_CLIENT_CUBE_ADDRESS !== 'false',
    chatTimeoutMs: Number(process.env.CHAT_TIMEOUT_MS || 125_000),
  },

  vite: {
    optimizeDeps: {
      include: ['echarts', 'vue-echarts'],
    },
  },

  build: {
    transpile: ['vue-echarts', 'echarts', 'resize-detector'],
  },
})
