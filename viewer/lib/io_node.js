/**
 * Node IO for the viewer: read artifact bytes off disk, hash with
 * `node:crypto`.  Used by `viewer/node_driver.js`, which the automated
 * equivalence test drives so the test exercises the viewer's own
 * assembly and rendering rather than a Python re-implementation of them.
 */

import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

export function nodeIo(repoRoot) {
  return {
    async readText(path) {
      try {
        return { ok: true, text: await readFile(resolve(repoRoot, path), 'utf8') };
      } catch (error) {
        return { ok: false, error: `${error.code || 'read error'}: ${error.message}` };
      }
    },
    async sha256(text) {
      return createHash('sha256').update(text, 'utf8').digest('hex');
    },
  };
}
