<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '~/utils/renderMarkdown'

const props = defineProps<{
  content: string
  variant?: 'default' | 'inverse'
}>()

const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div
    class="chat-markdown"
    :class="variant === 'inverse' ? 'chat-markdown--inverse' : 'chat-markdown--default'"
    v-html="html"
  />
</template>
