import type { ReferenceItem } from '../src/types.ts'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseAnswerParts } from '../src/utils/answerParts.ts'

const reference = { index: 2, uuid: 'source-version-chunk' } as ReferenceItem

test('renders emphasis and both citation formats without changing source identity', () => {
  const parts = parseAnswerParts('至少 **20 秒**。[索引2] 或 [2]', [reference])
  assert.equal(parts.find(part => part.emphasis)?.text, '20 秒')
  assert.deepEqual(parts.filter(part => part.reference).map(part => part.reference), [reference, reference])
  assert.equal(parts.map(part => part.text).join(''), '至少 20 秒。[2] 或 [2]')
})

test('citation inside emphasis remains interactive while unknown references stay literal', () => {
  const parts = parseAnswerParts('__原文 [2]__ [99]', [reference])
  assert.equal(parts.find(part => part.reference)?.reference, reference)
  assert.ok(parts.find(part => part.reference)?.emphasis)
  assert.ok(parts.some(part => part.text.includes('[99]') && !part.reference))
})

test('HTML, script-like links, unmatched formatting and ordinary units remain text', () => {
  const text = '<img src=x onerror=alert(1)> [連結](javascript:alert(1)) 2*3 A_B **未結束'
  const parts = parseAnswerParts(text, [reference])
  assert.equal(parts.map(part => part.text).join(''), text)
  assert.ok(parts.every(part => !part.reference && !part.emphasis))
})
