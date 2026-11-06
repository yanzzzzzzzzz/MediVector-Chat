import type { ReferenceItem } from '@/types'

export interface InlineAnswerPart {
  text: string
  emphasis?: boolean
  reference?: ReferenceItem
}

// Render only emphasis and existing citation IDs; all other input stays literal text.
export function parseAnswerParts (text: string, references: ReferenceItem[] = []): InlineAnswerPart[] {
  const byIndex = new Map(references.map(reference => [String(reference.index), reference]))
  const pattern = /\*\*([^\n]+?)\*\*|__([^\n]+?)__|\[(?:索引\s*)?(\d+)\]/g
  const parts: InlineAnswerPart[] = []
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      parts.push({ text: text.slice(cursor, match.index) })
    }
    if (match[1] !== undefined || match[2] !== undefined) {
      parts.push(...parseAnswerParts(match[1] ?? match[2] ?? '', references).map(part => ({ ...part, emphasis: true })))
    } else {
      const reference = byIndex.get(match[3] || '')
      parts.push(reference ? { text: `[${reference.index}]`, reference } : { text: match[0] })
    }
    cursor = pattern.lastIndex
  }
  if (cursor < text.length) {
    parts.push({ text: text.slice(cursor) })
  }
  return parts
}
