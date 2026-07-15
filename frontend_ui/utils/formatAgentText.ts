/**
 * Formatea texto del agente sin dependencias pesadas (evita bloqueos con DOMPurify en Docker).
 */
export function formatAgentText(text: string): string {
  if (!text?.trim()) return ''

  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  let html = escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')

  const lines = html.split('\n')
  const parts: string[] = []
  let inList = false

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('- ')) {
      if (!inList) {
        parts.push('<ul class="list-disc pl-4 my-1">')
        inList = true
      }
      parts.push(`<li>${trimmed.slice(2)}</li>`)
    } else {
      if (inList) {
        parts.push('</ul>')
        inList = false
      }
      if (trimmed) {
        parts.push(`<p class="my-1">${trimmed}</p>`)
      }
    }
  }

  if (inList) {
    parts.push('</ul>')
  }

  return parts.join('')
}
