/**
 * Browser IO for the viewer: fetch artifact bytes, hash with WebCrypto.
 *
 * `crypto.subtle` exists only in a secure context, which `http://localhost`
 * is and `file://` is not.  That is why `viewer/serve.py` exists: opening
 * `index.html` straight off the disk would disable hash verification and
 * be blocked from fetching the JSON anyway.  The viewer says so out loud
 * rather than degrading quietly.
 */

const encoder = new TextEncoder();

export function browserIo({ base = '../' } = {}) {
  return {
    async readText(path) {
      let response;
      try {
        response = await fetch(`${base}${path}`, { cache: 'no-store' });
      } catch (error) {
        return { ok: false, error: `network error: ${error.message}` };
      }
      if (!response.ok) {
        return { ok: false, error: `HTTP ${response.status} ${response.statusText}` };
      }
      return { ok: true, text: await response.text() };
    },
    async sha256(text) {
      if (!globalThis.crypto || !globalThis.crypto.subtle) {
        throw new Error(
          'crypto.subtle is unavailable, so published hashes cannot be '
          + 'verified. Serve the repository over http://localhost (see '
          + 'viewer/serve.py) instead of opening the file directly.');
      }
      const digest = await globalThis.crypto.subtle.digest(
        'SHA-256', encoder.encode(text));
      return [...new Uint8Array(digest)]
        .map((byte) => byte.toString(16).padStart(2, '0')).join('');
    },
  };
}

export function hashingAvailable() {
  return Boolean(globalThis.crypto && globalThis.crypto.subtle);
}
