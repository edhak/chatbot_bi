/**
 * Ofusca datos sensibles para mostrar en UI (IP, host, tokens).
 * No altera el valor real usado en las conexiones.
 */

const IPV4_RE = /\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b/g
const DATA_SOURCE_RE = /(Data\s*Source\s*=\s*)([^;]+)/gi
const PASSWORD_RE = /\b((?:Password|Pwd|User\s*ID|UID)\s*=\s*)([^;]*)/gi
const POWERBI_TOKEN_RE = /([?&]r=)([^&#]+)/i

export function maskCubeAddress(value: string | null | undefined): string {
  if (!value?.trim()) return '—'
  let text = value.trim()

  text = text.replace(IPV4_RE, (_m, a: string, _b: string, _c: string, d: string) => `${a}....${d}`)

  text = text.replace(DATA_SOURCE_RE, (_m, prefix: string, host: string) => {
    const trimmed = host.trim()
    // Si ya quedó ofuscada por IP, no tocar; si es hostname, acortar
    if (trimmed.includes('....')) return `${prefix}${trimmed}`
    if (trimmed.length <= 4) return `${prefix}****`
    return `${prefix}${trimmed.slice(0, 2)}****${trimmed.slice(-2)}`
  })

  text = text.replace(PASSWORD_RE, (_m, prefix: string) => `${prefix}****`)

  return text
}

export function maskPowerBiUrl(value: string | null | undefined): string {
  if (!value?.trim()) return '—'
  const text = value.trim()
  try {
    const url = new URL(text)
    const maskedPath = url.pathname.length > 1 ? '/…' : ''
    let search = url.search
    search = search.replace(POWERBI_TOKEN_RE, (_m, prefix: string, token: string) => {
      if (token.length <= 12) return `${prefix}…`
      return `${prefix}${token.slice(0, 6)}…${token.slice(-4)}`
    })
    return `${url.origin}${maskedPath}${search || '…'}`
  } catch {
    if (text.length <= 24) return `${text.slice(0, 8)}…`
    return `${text.slice(0, 28)}…`
  }
}
