<script setup lang="ts">
import { POWER_BI_REPORT_TITLE } from '~/utils/powerBiConfig'

const { powerBiUrl, selectedSeudonimo, hydrate } = useDataSources()
onMounted(() => hydrate())

const embedUrl = computed(() => powerBiUrl.value?.trim() || '')
const iframeTitle = computed(() => selectedSeudonimo.value || POWER_BI_REPORT_TITLE)
</script>

<template>
  <iframe
    v-if="embedUrl"
    :title="iframeTitle"
    class="h-full min-h-[480px] w-full border-0"
    :src="embedUrl"
    allowfullscreen
  />
  <div
    v-else
    class="flex h-full min-h-[480px] items-center justify-center px-6 text-center text-sm text-[#6B6B6A]"
  >
    Esta fuente no tiene URL de Power BI. Configure ruta_power_bi en fuentes_datos.csv.
  </div>
</template>
