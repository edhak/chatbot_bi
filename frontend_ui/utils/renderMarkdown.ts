import { marked } from 'marked'
import DOMPurify from 'isomorphic-dompurify'

marked.setOptions({
  breaks: true,
  gfm: true,
})

const SANITIZE_OPTIONS = {
  ALLOWED_TAGS: [
    'p', 'br', 'strong', 'em', 'b', 'i', 'u', 's',
    'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'span', 'hr',
  ],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'title', 'class'],
}

export function renderMarkdown(text: string): string {
  if (!text?.trim()) return ''

  const raw = marked.parse(text, { async: false }) as string
  return DOMPurify.sanitize(raw, SANITIZE_OPTIONS)
}
