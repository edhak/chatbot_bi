<script setup lang="ts">
import type { DashboardEntry } from '~/composables/useDashboard'
import { hasValidChartConfig } from '~/utils/chartConfig'

const { fetchDashboard, refreshItem, refreshAll, removeById } = useDashboard()

const items = ref<DashboardEntry[]>([])
const isLoading = ref(true)
const isRefreshingAll = ref(false)
const refreshingIds = ref<Set<string>>(new Set())
const removingIds = ref<Set<string>>(new Set())
const pendingRemoveId = ref<string | null>(null)
const error = ref<string | null>(null)

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('es-PE', {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

async function loadDashboard() {
  isLoading.value = true
  error.value = null
  try {
    items.value = await fetchDashboard()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'No se pudo cargar el dashboard.'
  } finally {
    isLoading.value = false
  }
}

async function refreshOne(id: string) {
  refreshingIds.value = new Set([...refreshingIds.value, id])
  try {
    const updated = await refreshItem(id)
    const idx = items.value.findIndex((i) => i.id === id)
    if (idx >= 0) {
      items.value[idx] = updated
    }
  } catch (err: unknown) {
    const idx = items.value.findIndex((i) => i.id === id)
    if (idx >= 0) {
      items.value[idx] = {
        ...items.value[idx],
        last_error: err instanceof Error ? err.message : 'Error al actualizar',
      }
    }
  } finally {
    const next = new Set(refreshingIds.value)
    next.delete(id)
    refreshingIds.value = next
  }
}

async function refreshAllItems() {
  isRefreshingAll.value = true
  error.value = null
  try {
    items.value = await refreshAll()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Error al actualizar el dashboard.'
  } finally {
    isRefreshingAll.value = false
  }
}

function requestRemove(item: DashboardEntry) {
  pendingRemoveId.value = item.id
}

function cancelRemove() {
  pendingRemoveId.value = null
}

async function confirmRemove(item: DashboardEntry) {
  if (removingIds.value.has(item.id)) return
  removingIds.value = new Set([...removingIds.value, item.id])
  error.value = null
  try {
    await removeById(item.id)
    items.value = items.value.filter((i) => i.id !== item.id)
    pendingRemoveId.value = null
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'No se pudo quitar el indicador.'
  } finally {
    const next = new Set(removingIds.value)
    next.delete(item.id)
    removingIds.value = next
  }
}

onMounted(loadDashboard)
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="border-b border-brand-light bg-white px-6 py-4 shadow-sm">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-brand-dark">
            Dashboard Ejecutivo
          </h2>
          <p class="text-xs text-[#6B6B6A]">
            Indicadores guardados · datos en vivo desde el cubo SSAS
          </p>
        </div>
        <button
          class="flex items-center gap-2 rounded-lg bg-brand-blue px-4 py-2 text-sm font-semibold text-white shadow-executive transition hover:bg-[#0378A4] disabled:opacity-50"
          :disabled="isRefreshingAll || isLoading || items.length === 0"
          @click="refreshAllItems"
        >
          <svg
            class="h-4 w-4"
            :class="{ 'animate-spin': isRefreshingAll }"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          {{ isRefreshingAll ? 'Actualizando...' : 'Actualizar todo' }}
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-4 py-6">
      <div class="mx-auto max-w-6xl">
        <div v-if="isLoading" class="flex items-center justify-center py-20 text-sm text-[#6B6B6A]">
          Cargando indicadores del dashboard...
        </div>

        <div
          v-else-if="error"
          class="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800"
        >
          {{ error }}
        </div>

        <div
          v-else-if="items.length === 0"
          class="rounded-2xl border border-brand-light bg-white px-8 py-16 text-center shadow-card"
        >
          <p class="mb-2 text-lg font-semibold text-brand-dark">
            Sin indicadores guardados
          </p>
          <p class="mb-6 text-sm text-[#6B6B6A]">
            En la pestaña Consultas, use <strong>Incluir en Dashboard</strong> debajo de un gráfico.
          </p>
          <NuxtLink
            to="/"
            class="inline-flex rounded-lg bg-brand-blue px-5 py-2.5 text-sm font-semibold text-white"
          >
            Ir a Consultas
          </NuxtLink>
        </div>

        <div v-else class="grid gap-6 md:grid-cols-2">
          <article
            v-for="item in items"
            :key="item.id"
            class="flex flex-col rounded-xl border border-brand-light bg-white shadow-card"
          >
            <div class="border-b border-brand-light px-4 py-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <h3 class="truncate text-sm font-semibold text-brand-dark">
                    {{ item.title }}
                  </h3>
                  <p v-if="item.question" class="mt-0.5 truncate text-[11px] text-[#6B6B6A]">
                    {{ item.question }}
                  </p>
                </div>
                <div class="flex shrink-0 items-center gap-1.5">
                  <template v-if="pendingRemoveId === item.id">
                    <button
                      class="rounded-md border border-brand-light px-2.5 py-1.5 text-[11px] font-medium text-[#6B6B6A] transition hover:border-brand-blue hover:text-brand-blue disabled:opacity-50"
                      :disabled="removingIds.has(item.id)"
                      @click="cancelRemove"
                    >
                      Cancelar
                    </button>
                    <button
                      class="rounded-md border border-red-300 bg-red-50 px-2.5 py-1.5 text-[11px] font-semibold text-red-700 transition hover:bg-red-100 disabled:opacity-50"
                      :disabled="removingIds.has(item.id)"
                      @click="confirmRemove(item)"
                    >
                      {{ removingIds.has(item.id) ? '...' : 'Sí, quitar' }}
                    </button>
                  </template>
                  <template v-else>
                    <button
                      class="rounded-md border border-brand-light px-2.5 py-1.5 text-[11px] font-medium text-[#6B6B6A] transition hover:border-brand-blue hover:text-brand-blue disabled:opacity-50"
                      :disabled="refreshingIds.has(item.id) || isRefreshingAll || removingIds.has(item.id)"
                      @click="refreshOne(item.id)"
                    >
                      {{ refreshingIds.has(item.id) ? '...' : 'Actualizar' }}
                    </button>
                    <button
                      class="rounded-md border border-red-200 px-2.5 py-1.5 text-[11px] font-medium text-red-700 transition hover:border-red-400 hover:bg-red-50 disabled:opacity-50"
                      :disabled="removingIds.has(item.id) || isRefreshingAll"
                      title="Quitar del dashboard"
                      @click="requestRemove(item)"
                    >
                      Quitar
                    </button>
                  </template>
                </div>
              </div>
              <p
                v-if="pendingRemoveId === item.id"
                class="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-900"
              >
                ¿Está seguro de quitar este indicador del dashboard?
              </p>
              <div class="mt-2 flex flex-wrap gap-3 text-[10px] text-[#9CA3AF]">
                <span>{{ item.row_count ?? 0 }} filas</span>
                <span>Última act.: {{ formatDate(item.last_refresh_at) }}</span>
                <span v-if="item.elapsed_ms">{{ item.elapsed_ms }}ms</span>
              </div>
            </div>

            <div class="p-3">
              <p
                v-if="item.last_error"
                class="mb-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800"
              >
                {{ item.last_error }}
              </p>

              <AgentChart
                v-if="hasValidChartConfig(item.chartConfig)"
                :config="item.chartConfig"
              />
              <p v-else class="py-8 text-center text-xs text-[#9CA3AF]">
                Sin datos para graficar
              </p>
            </div>
          </article>
        </div>
      </div>
    </div>
  </div>
</template>
