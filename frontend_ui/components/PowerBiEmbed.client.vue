<script setup lang="ts">
import { POWER_BI_REPORT_TITLE, POWER_BI_VIEW_URL } from '~/utils/powerBiConfig'
</script>

<template>
  <iframe
    :title="POWER_BI_REPORT_TITLE"
    class="h-full min-h-[480px] w-full border-0"
    :src="POWER_BI_VIEW_URL"
    allowfullscreen
  />
</template>
