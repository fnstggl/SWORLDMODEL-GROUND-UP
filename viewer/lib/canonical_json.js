/**
 * Canonical JSON that reproduces, byte for byte, what the harness hashed.
 *
 * The recording harness hashes with:
 *
 *     json.dumps(value, sort_keys=True, separators=(",", ":"),
 *                ensure_ascii=False)
 *
 * `JSON.stringify` is NOT equivalent: Python writes floats with
 * `repr(float)` (`0.0`, `2.0`), while JavaScript's number formatting drops
 * the fractional part (`0`, `2`).  A viewer that used `JSON.stringify`
 * would report a hash MISMATCH on a perfectly intact artifact -- a false
 * accusation, which is worse than not checking at all.
 *
 * So this module parses JSON from its raw text and keeps each number's
 * ORIGINAL literal, then re-serialises with sorted keys and no spacing.
 * Every artifact in this repository was written by `json.dumps`, so the
 * literal in the file already is `repr()` of the value the harness hashed.
 *
 * Nothing here is specific to any scenario; it is a JSON codec.
 */

/** A number that must be re-emitted exactly as it was written. */
export class RawNumber {
  constructor(literal) {
    this.literal = literal;
  }
  valueOf() {
    return Number(this.literal);
  }
  toString() {
    return this.literal;
  }
}

export class JsonParseError extends Error {
  constructor(message, position) {
    super(message);
    this.name = 'JsonParseError';
    this.position = position;
  }
}

const WHITESPACE = new Set([' ', '\t', '\n', '\r']);

/**
 * Parse JSON text into a tree in which every number is a {@link RawNumber}.
 * Objects become `Map`s so key order is preserved for diagnostics (the
 * canonical serialiser sorts them anyway).
 *
 * @param {string} text
 * @returns {*} the parsed tree
 * @throws {JsonParseError} on malformed input, naming the byte offset
 */
export function parseJsonPreservingNumbers(text) {
  let i = 0;

  function fail(message) {
    throw new JsonParseError(`${message} at position ${i}`, i);
  }

  function skipWhitespace() {
    while (i < text.length && WHITESPACE.has(text[i])) i += 1;
  }

  function parseValue() {
    skipWhitespace();
    if (i >= text.length) fail('unexpected end of input');
    const ch = text[i];
    if (ch === '{') return parseObject();
    if (ch === '[') return parseArray();
    if (ch === '"') return parseString();
    if (ch === 't') return parseLiteral('true', true);
    if (ch === 'f') return parseLiteral('false', false);
    if (ch === 'n') return parseLiteral('null', null);
    if (ch === '-' || (ch >= '0' && ch <= '9')) return parseNumber();
    return fail(`unexpected character ${JSON.stringify(ch)}`);
  }

  function parseLiteral(word, value) {
    if (text.slice(i, i + word.length) !== word) fail(`expected ${word}`);
    i += word.length;
    return value;
  }

  function parseNumber() {
    const start = i;
    if (text[i] === '-') i += 1;
    while (i < text.length && text[i] >= '0' && text[i] <= '9') i += 1;
    if (text[i] === '.') {
      i += 1;
      while (i < text.length && text[i] >= '0' && text[i] <= '9') i += 1;
    }
    if (text[i] === 'e' || text[i] === 'E') {
      i += 1;
      if (text[i] === '+' || text[i] === '-') i += 1;
      while (i < text.length && text[i] >= '0' && text[i] <= '9') i += 1;
    }
    const literal = text.slice(start, i);
    if (!/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(literal)) {
      fail(`malformed number ${JSON.stringify(literal)}`);
    }
    return new RawNumber(literal);
  }

  function parseString() {
    if (text[i] !== '"') fail('expected a string');
    i += 1;
    let out = '';
    while (true) {
      if (i >= text.length) fail('unterminated string');
      const ch = text[i];
      if (ch === '"') {
        i += 1;
        return out;
      }
      if (ch === '\\') {
        i += 1;
        const esc = text[i];
        i += 1;
        if (esc === '"') out += '"';
        else if (esc === '\\') out += '\\';
        else if (esc === '/') out += '/';
        else if (esc === 'b') out += '\b';
        else if (esc === 'f') out += '\f';
        else if (esc === 'n') out += '\n';
        else if (esc === 'r') out += '\r';
        else if (esc === 't') out += '\t';
        else if (esc === 'u') {
          const hex = text.slice(i, i + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail('malformed \\u escape');
          out += String.fromCharCode(parseInt(hex, 16));
          i += 4;
        } else fail(`unknown escape \\${esc}`);
        continue;
      }
      out += ch;
      i += 1;
    }
  }

  function parseArray() {
    i += 1;
    const items = [];
    skipWhitespace();
    if (text[i] === ']') {
      i += 1;
      return items;
    }
    while (true) {
      items.push(parseValue());
      skipWhitespace();
      if (text[i] === ',') {
        i += 1;
        continue;
      }
      if (text[i] === ']') {
        i += 1;
        return items;
      }
      return fail('expected "," or "]" in array');
    }
  }

  function parseObject() {
    i += 1;
    const map = new Map();
    skipWhitespace();
    if (text[i] === '}') {
      i += 1;
      return map;
    }
    while (true) {
      skipWhitespace();
      const key = parseString();
      skipWhitespace();
      if (text[i] !== ':') return fail('expected ":" in object');
      i += 1;
      map.set(key, parseValue());
      skipWhitespace();
      if (text[i] === ',') {
        i += 1;
        continue;
      }
      if (text[i] === '}') {
        i += 1;
        return map;
      }
      return fail('expected "," or "}" in object');
    }
  }

  const value = parseValue();
  skipWhitespace();
  if (i !== text.length) fail('trailing data after the JSON value');
  return value;
}

/**
 * Escape a string exactly the way Python's json does with
 * `ensure_ascii=False`: only `"`, `\` and the C0 control characters.
 */
function encodeString(value) {
  let out = '"';
  for (const ch of value) {
    const code = ch.codePointAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (ch === '\b') out += '\\b';
    else if (ch === '\f') out += '\\f';
    else if (code < 0x20) out += `\\u${code.toString(16).padStart(4, '0')}`;
    else out += ch;
  }
  return `${out}"`;
}

/**
 * Serialise a tree canonically: sorted keys, `,`/`:` separators, no spaces,
 * non-ASCII left as-is, numbers emitted from their preserved literal.
 *
 * Accepts trees from {@link parseJsonPreservingNumbers} (Maps, RawNumbers)
 * and ordinary JavaScript values (plain objects, numbers).
 *
 * @param {*} value
 * @returns {string}
 */
export function canonicalize(value) {
  if (value === null) return 'null';
  if (value instanceof RawNumber) return value.literal;
  const type = typeof value;
  if (type === 'boolean') return value ? 'true' : 'false';
  if (type === 'string') return encodeString(value);
  if (type === 'number') {
    if (!Number.isFinite(value)) {
      throw new TypeError(`cannot canonicalise non-finite number ${value}`);
    }
    // Integral JavaScript numbers are ambiguous (Python would write `1.0`
    // for a float and `1` for an int).  Only reachable for values this
    // viewer builds itself, never for parsed artifact text.
    return Number.isInteger(value) ? String(value) : String(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(',')}]`;
  }
  if (value instanceof Map) {
    const keys = [...value.keys()].sort(comparePythonStrings);
    return `{${keys
      .map((key) => `${encodeString(key)}:${canonicalize(value.get(key))}`)
      .join(',')}}`;
  }
  if (type === 'object') {
    const keys = Object.keys(value).sort(comparePythonStrings);
    return `{${keys
      .map((key) => `${encodeString(key)}:${canonicalize(value[key])}`)
      .join(',')}}`;
  }
  throw new TypeError(`cannot canonicalise a value of type ${type}`);
}

/** Sort like Python's `sorted()` on `str`: by Unicode code point. */
function comparePythonStrings(a, b) {
  const aPoints = [...a].map((c) => c.codePointAt(0));
  const bPoints = [...b].map((c) => c.codePointAt(0));
  const n = Math.min(aPoints.length, bPoints.length);
  for (let k = 0; k < n; k += 1) {
    if (aPoints[k] !== bPoints[k]) return aPoints[k] - bPoints[k];
  }
  return aPoints.length - bPoints.length;
}

/** Canonical JSON for the value written in `text`. */
export function canonicalFromText(text) {
  return canonicalize(parseJsonPreservingNumbers(text));
}

/** Read `tree[key0][key1]...`, returning `undefined` if any hop is absent. */
export function selectPath(tree, path) {
  let node = tree;
  for (const key of path) {
    if (node instanceof Map) {
      if (!node.has(key)) return undefined;
      node = node.get(key);
    } else if (Array.isArray(node) && typeof key === 'number') {
      node = node[key];
    } else if (node && typeof node === 'object' && key in node) {
      node = node[key];
    } else {
      return undefined;
    }
  }
  return node;
}

/** Convert a preserved-number tree into ordinary JavaScript values. */
export function toPlain(value) {
  if (value instanceof RawNumber) return Number(value.literal);
  if (Array.isArray(value)) return value.map(toPlain);
  if (value instanceof Map) {
    const out = {};
    for (const [key, item] of value) out[key] = toPlain(item);
    return out;
  }
  return value;
}
