<script setup lang="ts">
const { loadIncludedMap } = useDashboard()

onMounted(() => {
  loadIncludedMap()
})
</script>

<template>
  <ChatInterface />
</template>
