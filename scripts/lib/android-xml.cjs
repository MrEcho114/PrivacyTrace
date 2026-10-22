'use strict'

/**
 * Dependency-free scanner for the small Android resource XML used by the brand
 * icon pipeline (adaptive-icon and vector drawables: no CDATA, entities or
 * text content). Both the overlay script and the verifier import this one
 * implementation so their malformed-XML rules cannot drift.
 *
 * `onError` lets each caller keep its own failure style: the overlay script
 * exits with a readable reason, the verifier throws for the check report.
 */
function parseAttributes(raw, label, fail) {
  const attributes = {}
  let index = 0
  const pattern = /([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g
  let match
  while ((match = pattern.exec(raw)) !== null) {
    const between = raw.slice(index, match.index)
    if (between.trim() !== '') {
      fail(`${label}: malformed XML attributes near ${JSON.stringify(between.trim().slice(0, 40))}`)
    }
    const name = match[1]
    if (Object.prototype.hasOwnProperty.call(attributes, name)) {
      fail(`${label}: duplicate XML attribute ${name}`)
    }
    attributes[name] = match[2] !== undefined ? match[2] : match[3]
    index = pattern.lastIndex
  }
  if (raw.slice(index).trim() !== '') {
    fail(`${label}: malformed XML attributes near ${JSON.stringify(raw.slice(index).trim().slice(0, 40))}`)
  }
  return attributes
}

function parseXml(text, label, onError = (message) => { throw new Error(message) }) {
  const source = text.replace(/^\uFEFF/, '')
  const fail = (message) => onError(message)
  let index = 0
  const stack = []
  const elements = []
  let root = null

  const skipWhitespace = () => {
    while (index < source.length && /\s/.test(source[index])) index += 1
  }

  while (true) {
    skipWhitespace()
    if (index >= source.length) break

    if (source.startsWith('<?', index)) {
      const end = source.indexOf('?>', index + 2)
      if (end < 0) fail(`${label}: unterminated XML declaration`)
      index = end + 2
      continue
    }
    if (source.startsWith('<!--', index)) {
      const end = source.indexOf('-->', index + 4)
      if (end < 0) fail(`${label}: unterminated XML comment`)
      index = end + 3
      continue
    }
    if (source.startsWith('<!', index)) {
      fail(`${label}: unsupported XML declaration near offset ${index}`)
    }
    if (source[index] !== '<') {
      fail(`${label}: unexpected text outside XML elements near offset ${index}`)
    }

    let quote = null
    let end = -1
    for (let cursor = index + 1; cursor < source.length; cursor += 1) {
      const character = source[cursor]
      if (quote) {
        if (character === quote) quote = null
        continue
      }
      if (character === '"' || character === "'") {
        quote = character
        continue
      }
      if (character === '>') {
        end = cursor
        break
      }
      if (character === '<') fail(`${label}: unterminated XML tag near offset ${index}`)
    }
    if (end < 0) fail(`${label}: unterminated XML tag near offset ${index}`)

    const rawTag = source.slice(index + 1, end).trim()
    index = end + 1
    if (rawTag === '') fail(`${label}: empty XML tag`)

    if (rawTag.startsWith('/')) {
      const name = rawTag.slice(1).trim()
      if (!/^[A-Za-z_][\w:.-]*$/.test(name)) fail(`${label}: malformed closing tag </${name}>`)
      const open = stack.pop()
      if (!open || open.name !== name) {
        fail(`${label}: mismatched closing tag </${name}>${open ? `, expected </${open.name}>` : ''}`)
      }
      continue
    }

    const selfClosing = rawTag.endsWith('/')
    const body = selfClosing ? rawTag.slice(0, -1).trim() : rawTag
    const nameMatch = /^([A-Za-z_][\w:.-]*)([\s\S]*)$/.exec(body)
    if (!nameMatch) fail(`${label}: malformed opening tag near ${JSON.stringify(rawTag.slice(0, 40))}`)
    const name = nameMatch[1]
    const attributes = parseAttributes(nameMatch[2], label, fail)
    const parent = stack.length > 0 ? stack[stack.length - 1].name : null
    if (parent === null && root !== null) fail(`${label}: multiple root elements`)
    if (root === null) root = name
    elements.push({ name, attributes, parent, depth: stack.length })
    if (!selfClosing) stack.push({ name })
  }

  if (stack.length > 0) fail(`${label}: unclosed XML element <${stack[stack.length - 1].name}>`)
  if (root === null) fail(`${label}: no root element`)
  return { root, elements }
}

module.exports = { parseXml }
