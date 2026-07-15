<script setup lang="ts">
export interface DebugLogEntry {
  step: string
  message: string
  level: string
  elapsed_ms: number
}

defineProps<{
  logs: DebugLogEntry[]
  elapsedMs?: number
}>()
</script>

<template>
  <details class="mt-3 rounded-lg border border-amber-200 bg-amber-50 text-left">
    <summary class="cursor-pointer px-3 py-2 text-xs font-semibold text-amber-800">
      Depuración ({{ logs.length }} pasos<span v-if="elapsedMs"> · {{ elapsedMs }}ms total</span>)
    </summary>
    <div class="max-h-48 overflow-y-auto border-t border-amber-200 px-3 py-2 font-mono text-[10px] leading-relaxed">
      <div
        v-for="(entry, i) in logs"
        :key="i"
        class="mb-1"
        :class="{
          'text-red-700': entry.level === 'error',
          'text-amber-700': entry.level === 'warn',
          'text-gray-700': entry.level !== 'error' && entry.level !== 'warn',
        }"
      >
        <span class="text-gray-400">[{{ entry.elapsed_ms }}ms]</span>
        <span class="font-semibold">{{ entry.step }}:</span>
        {{ entry.message }}
      </div>
    </div>
  </details>
</template>
