<script setup lang="ts">
const route = useRoute()

const tabs = [
  { label: 'Consultas', to: '/', icon: 'chat' },
  { label: 'Dashboards', to: '/dashboards', icon: 'dashboard' },
  { label: 'Power BI', to: '/powerbi', icon: 'powerbi' },
]

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <header class="bg-brand-dark shadow-executive">
    <div class="h-1 bg-brand-yellow" />
    <div class="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
      <div class="flex items-center gap-4">
        <div class="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-blue">
          <svg class="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.5"
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </div>
        <div>
          <h1 class="text-lg font-semibold tracking-tight text-white">
            Inteligencia de Negocios
          </h1>
          <p class="text-xs text-brand-light/80">
            Cubo CB_BI_FlotHs · Flota de Equipos
          </p>
        </div>
      </div>

      <nav class="flex items-center gap-1 rounded-lg border border-white/15 bg-white/5 p-1">
        <NuxtLink
          v-for="tab in tabs"
          :key="tab.to"
          :to="tab.to"
          class="rounded-md px-4 py-2 text-xs font-semibold transition"
          :class="isActive(tab.to)
            ? 'bg-brand-blue text-white shadow-sm'
            : 'text-brand-light hover:bg-white/10 hover:text-white'"
        >
          {{ tab.label }}
        </NuxtLink>
      </nav>
    </div>
  </header>
</template>
