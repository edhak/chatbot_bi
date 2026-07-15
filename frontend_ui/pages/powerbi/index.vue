<template>
  <div class="flex h-full flex-col">
    <div class="border-b border-brand-light bg-white px-6 py-4 shadow-sm">
      <div class="mx-auto max-w-6xl">
        <h2 class="text-lg font-semibold text-brand-dark">
          BI FlotHs
        </h2>
        <p class="text-xs text-[#6B6B6A]">
          Dashboard publicado en Power BI · BI_FlotHs_v0201
        </p>
      </div>
    </div>

    <div
      class="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col overflow-hidden p-4 md:p-6"
    >
      <div
        class="flex h-full min-h-[480px] flex-1 flex-col overflow-hidden rounded-xl border border-brand-light bg-white shadow-card"
      >
        <ClientOnly>
          <PowerBiEmbed :visible="true" />
          <template #fallback>
            <div class="flex h-full min-h-[480px] items-center justify-center text-sm text-[#6B6B6A]">
              Cargando dashboard Power BI…
            </div>
          </template>
        </ClientOnly>
      </div>
    </div>
  </div>
</template>
