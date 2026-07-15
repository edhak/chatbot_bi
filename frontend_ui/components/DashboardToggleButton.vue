<script setup lang="ts">
const props = defineProps<{
  title: string
  question: string
  daxQuery: string
}>()

const { isIncluded, addToDashboard, removeFromDashboard, loadIncludedMap } = useDashboard()

const isBusy = ref(false)
const localError = ref<string | null>(null)

const included = computed(() => isIncluded(props.daxQuery))
const hasDax = computed(() => Boolean(props.daxQuery?.trim()))

async function toggle() {
  if (!props.daxQuery?.trim() || isBusy.value) return
  isBusy.value = true
  localError.value = null
  try {
    if (included.value) {
      await removeFromDashboard(props.daxQuery)
    } else {
      await addToDashboard({
        title: props.title,
        question: props.question,
        dax_query: props.daxQuery,
      })
    }
    await loadIncludedMap()
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : 'No se pudo actualizar el dashboard.'
  } finally {
    isBusy.value = false
  }
}
</script>

<template>
  <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-brand-light pt-3">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50"
      :class="included
        ? 'border border-brand-yellow/60 bg-brand-yellow/15 text-brand-dark hover:bg-brand-yellow/25'
        : 'bg-brand-blue text-white shadow-sm hover:bg-[#0378A4]'"
      :disabled="isBusy || !hasDax"
      :title="hasDax ? undefined : 'No hay consulta DAX disponible para guardar en el dashboard'"
      @click="toggle"
    >
      <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          v-if="!included"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M12 4v16m8-8H4"
        />
        <path
          v-else
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M20 12H4"
        />
      </svg>
      {{ isBusy ? 'Guardando...' : included ? 'Quitar del Dashboard' : 'Incluir en Dashboard' }}
    </button>

    <NuxtLink
      v-if="included"
      to="/dashboards"
      class="text-[11px] font-medium text-brand-blue hover:underline"
    >
      Ver en Dashboards →
    </NuxtLink>

    <p v-if="localError" class="w-full text-[11px] text-red-600">
      {{ localError }}
    </p>
  </div>
</template>
