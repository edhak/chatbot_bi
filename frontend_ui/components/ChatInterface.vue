<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { ref, nextTick, watch, computed, onUnmounted } from 'vue'
import { hasValidChartConfig, resolveChartTitle } from '~/utils/chartConfig'
import { formatAgentText } from '~/utils/formatAgentText'

interface DebugLogEntry {
  step: string
  message: string
  level: string
  elapsed_ms: number
}

interface ChatMessage {
  role: 'user' | 'agent'
  text: string
  question?: string
  chartConfig?: Record<string, unknown>
  dax?: string
  debugLog?: DebugLogEntry[]
  elapsedMs?: number
  hasChart?: boolean
}

interface AgentResponse {
  text: string
  dax: string
  chartConfig: EChartsOption
  debugLog?: DebugLogEntry[]
  elapsedMs?: number
  hasChart?: boolean
  textLength?: number
}

const CHAT_TIMEOUT_MS = 125_000

const messages = ref<ChatMessage[]>([])
const userInput = ref('')

const suggestedQuestions = [
  '¿Cuántos equipos hay registrados en total?',
  '¿Cuántos equipos hay por país destino?',
  '¿Cuáles son los 5 tipos de equipo más frecuentes?',
  '¿Cuántos equipos hay por mercado destino (Nacional vs Exterior)?',
  '¿Qué regiones tienen más equipos entregados?',
]

const isLoading = ref(false)
const loadingElapsed = ref(0)
const loadingStatus = ref('Enviando consulta...')
const messagesContainer = ref<HTMLElement | null>(null)
const expandedDax = ref<Set<number>>(new Set())

let loadingTimer: ReturnType<typeof setInterval> | null = null
let activeAbort: AbortController | null = null

function startLoadingTimer() {
  loadingElapsed.value = 0
  loadingStatus.value = 'Enviando consulta al BFF...'
  loadingTimer = setInterval(() => {
    loadingElapsed.value += 1
    if (loadingElapsed.value === 3) loadingStatus.value = 'BFF llamando al backend Python...'
    if (loadingElapsed.value === 8) loadingStatus.value = 'LLM generando DAX y ejecutando cubo...'
    if (loadingElapsed.value === 20) loadingStatus.value = 'Generando respuesta narrativa...'
    if (loadingElapsed.value === 45) {
      loadingStatus.value = 'Esperando respuesta del BFF...'
    }
  }, 1000)
}

function stopLoadingTimer() {
  if (loadingTimer) {
    clearInterval(loadingTimer)
    loadingTimer = null
  }
}

onUnmounted(() => {
  stopLoadingTimer()
  activeAbort?.abort()
})

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

watch(() => messages.value.length, scrollToBottom)

function toggleDax(index: number) {
  if (expandedDax.value.has(index)) {
    expandedDax.value.delete(index)
  } else {
    expandedDax.value.add(index)
  }
}

function canShowChart(msg: ChatMessage): boolean {
  if (msg.role !== 'agent' || !msg.chartConfig) return false
  if (hasValidChartConfig(msg.chartConfig)) return true
  // BFF puede marcar hasChart por series presentes aunque data sea atípica
  return msg.hasChart === true
}

function chartTitle(msg: ChatMessage): string {
  return resolveChartTitle(msg.chartConfig, {
    narrative: msg.text,
    question: msg.question || '',
  })
}

function questionForMessage(index: number): string {
  for (let i = index - 1; i >= 0; i--) {
    if (messages.value[i]?.role === 'user') {
      return messages.value[i].text
    }
  }
  return ''
}

const MAX_QUESTION_LENGTH = 500

async function sendMessage() {
  const text = userInput.value.trim()
  if (!text || isLoading.value) return
  if (text.length > MAX_QUESTION_LENGTH) return

  messages.value.push({ role: 'user', text })
  userInput.value = ''
  isLoading.value = true
  startLoadingTimer()

  activeAbort?.abort()
  activeAbort = new AbortController()
  const timeoutId = setTimeout(() => activeAbort?.abort(), CHAT_TIMEOUT_MS)

  try {
    const response = await $fetch<AgentResponse>('/api/chat', {
      method: 'POST',
      body: { message: text },
      signal: activeAbort.signal,
    })

    console.info('[Chat] Respuesta recibida:', {
      textLength: response.textLength ?? response.text?.length,
      hasChart: response.hasChart,
      elapsedMs: response.elapsedMs,
      debugSteps: response.debugLog?.length,
    })

    const hasChart = response.hasChart === true
      || hasValidChartConfig(response.chartConfig as Record<string, unknown>)

    const agentText = (response.text || '').trim()
      || '(Sin texto en la respuesta)'

    const agentMsg: ChatMessage = {
      role: 'agent',
      text: agentText,
      question: text,
      chartConfig: response.chartConfig
        ? (JSON.parse(JSON.stringify(response.chartConfig)) as Record<string, unknown>)
        : undefined,
      dax: response.dax,
      debugLog: response.debugLog ?? [],
      elapsedMs: response.elapsedMs,
      hasChart,
    }

    messages.value.push(agentMsg)

    console.info('[Chat] Gráfico:', {
      hasChart,
      valid: hasValidChartConfig(response.chartConfig as Record<string, unknown>),
      series: (response.chartConfig as Record<string, unknown>)?.series,
    })

    await scrollToBottom()
  } catch (error: unknown) {
    let detail: string | undefined
    let debugLog: DebugLogEntry[] = []

    if (error && typeof error === 'object') {
      const fetchError = error as {
        name?: string
        data?: {
          detail?: string
          data?: { detail?: string; debugLog?: DebugLogEntry[] }
          debugLog?: DebugLogEntry[]
        }
        statusMessage?: string
        message?: string
      }

      if (fetchError.name === 'AbortError') {
        detail = `Timeout (${CHAT_TIMEOUT_MS / 1000}s). El BFF no devolvió respuesta. Verifique que Docker alcance el backend en el puerto 8000.`
      } else {
        detail =
          fetchError.data?.data?.detail
          ?? fetchError.data?.detail
          ?? fetchError.statusMessage
          ?? fetchError.message
      }

      debugLog =
        fetchError.data?.data?.debugLog
        ?? fetchError.data?.debugLog
        ?? []
    }

    debugLog.push({
      step: 'frontend',
      message: detail ?? 'Error desconocido',
      level: 'error',
      elapsed_ms: loadingElapsed.value * 1000,
    })

    messages.value.push({
      role: 'agent',
      text: detail ?? 'Ocurrió un error al procesar tu consulta. Intenta de nuevo.',
      debugLog,
      elapsedMs: loadingElapsed.value * 1000,
    })
  } finally {
    clearTimeout(timeoutId)
    stopLoadingTimer()
    isLoading.value = false
    activeAbort = null
  }
}

function useSuggestedQuestion(question: string) {
  userInput.value = question
  sendMessage()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

const hasMessages = computed(() => messages.value.length > 0)
</script>

<template>
  <div class="flex h-full flex-col bg-[#F4F6F8] text-brand-dark">
    <div ref="messagesContainer" class="scrollbar-executive flex-1 overflow-y-auto px-4 py-6">
      <div class="mx-auto flex max-w-4xl flex-col gap-5">
        <div v-if="!hasMessages" class="flex flex-col items-center py-12 text-center">
          <div class="mb-6 w-full max-w-2xl rounded-2xl border border-brand-light bg-white p-8 shadow-card">
            <h2 class="mb-2 text-xl font-semibold text-brand-dark">
              Asistente de Análisis BI
            </h2>
            <p class="mb-6 text-sm leading-relaxed text-[#6B6B6A]">
              Consulte indicadores de la flota de equipos en lenguaje natural.
            </p>
            <div class="flex flex-wrap justify-center gap-2">
              <button
                v-for="(q, i) in suggestedQuestions"
                :key="i"
                class="rounded-lg border border-brand-light bg-[#F4F6F8] px-3 py-2 text-left text-xs text-brand-dark transition hover:border-brand-blue hover:bg-white disabled:opacity-50"
                :disabled="isLoading"
                @click="useSuggestedQuestion(q)"
              >
                {{ q }}
              </button>
            </div>
          </div>
        </div>

        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="flex"
          :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div class="max-w-[88%]" :class="msg.role === 'user' ? '' : 'w-full max-w-3xl'">
            <p
              class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider"
              :class="msg.role === 'user' ? 'text-right text-brand-blue' : 'text-[#6B6B6A]'"
            >
              {{ msg.role === 'user' ? 'Usted' : 'Analista BI' }}
            </p>

            <div
              class="rounded-xl px-5 py-4"
              :class="msg.role === 'user'
                ? 'bg-brand-blue text-white shadow-executive'
                : 'border border-brand-light bg-white text-brand-dark shadow-card'"
            >
              <p v-if="msg.role === 'user'" class="whitespace-pre-wrap text-sm leading-relaxed text-white">
                {{ msg.text }}
              </p>
              <div
                v-else
                class="agent-text text-sm leading-relaxed"
                v-html="formatAgentText(msg.text)"
              />

              <p v-if="msg.role === 'agent' && msg.hasChart === false" class="mt-2 text-xs text-amber-700">
                Sin gráfico (datos vacíos o config inválida)
              </p>

              <AgentChart
                v-if="canShowChart(msg)"
                :config="msg.chartConfig!"
                :title-fallback="chartTitle(msg)"
                class="mt-4 rounded-lg border border-brand-light bg-[#FAFBFC] p-3"
              />

              <DashboardToggleButton
                v-if="msg.role === 'agent' && canShowChart(msg)"
                :title="chartTitle(msg)"
                :question="msg.question || questionForMessage(index)"
                :dax-query="msg.dax || ''"
              />

              <div v-if="msg.role === 'agent' && msg.dax" class="mt-3">
                <button
                  class="flex items-center gap-1 text-xs text-[#6B6B6A] transition hover:text-brand-blue"
                  @click="toggleDax(index)"
                >
                  Ver consulta DAX
                </button>
                <pre
                  v-if="expandedDax.has(index)"
                  class="mt-2 overflow-x-auto rounded-lg bg-brand-dark p-3 text-xs text-brand-yellow"
                >{{ msg.dax }}</pre>
              </div>

              <AgentDebugPanel
                v-if="msg.role === 'agent' && msg.debugLog?.length"
                :logs="msg.debugLog"
                :elapsed-ms="msg.elapsedMs"
              />
            </div>
          </div>
        </div>

        <div v-if="isLoading" class="flex justify-start">
          <div class="w-full max-w-3xl rounded-xl border border-brand-light bg-white px-5 py-4 shadow-card">
            <div class="flex items-center gap-3 text-sm text-[#6B6B6A]">
              <span class="inline-flex gap-1">
                <span class="h-2 w-2 animate-bounce rounded-full bg-brand-blue [animation-delay:-0.3s]" />
                <span class="h-2 w-2 animate-bounce rounded-full bg-brand-blue [animation-delay:-0.15s]" />
                <span class="h-2 w-2 animate-bounce rounded-full bg-brand-blue" />
              </span>
              <span>{{ loadingStatus }} ({{ loadingElapsed }}s)</span>
            </div>
            <p class="mt-2 text-[10px] text-[#9CA3AF]">
              Si el backend ya terminó pero esto sigue cargando, el BFF Docker no recibe la respuesta.
              Ejecute: <code class="text-brand-blue">docker logs blissful_babbage --tail 30</code>
            </p>
          </div>
        </div>
      </div>
    </div>

    <footer class="border-t border-brand-light bg-white px-4 py-4 shadow-executive">
      <div class="mx-auto flex max-w-4xl items-end gap-3">
        <textarea
          v-model="userInput"
          rows="1"
          maxlength="500"
          placeholder="Escriba su consulta sobre la flota de equipos..."
          class="flex-1 resize-none rounded-xl border border-brand-light bg-[#F4F6F8] px-4 py-3 text-sm text-brand-dark placeholder-[#9CA3AF] outline-none transition focus:border-brand-blue focus:bg-white focus:ring-2 focus:ring-brand-blue/20"
          :disabled="isLoading"
          @keydown="handleKeydown"
        />
        <button
          class="rounded-xl bg-brand-blue px-6 py-3 text-sm font-semibold text-white shadow-executive transition hover:bg-[#0378A4] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="isLoading || !userInput.trim()"
          @click="sendMessage"
        >
          Consultar
        </button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.agent-text :deep(strong) {
  font-weight: 600;
}
.agent-text :deep(ul) {
  margin: 0.25rem 0;
}
</style>
