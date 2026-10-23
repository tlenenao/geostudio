// SPDX-License-Identifier: Apache-2.0
// L8 : solveur de preuve de travail (hashcash) de la soumission publique. Le cœur émet un défi ;
// il faut un `nonce` tel que SHA-256(`<défi>:<nonce>`) ait `bits` bits de tête à zéro.
//
// ponytail: SHA-256 synchrone écrit ici plutôt que `crypto.subtle` (un appel asynchrone par essai
// coûterait ~2^18 allers-retours de micro-tâches, de l'ordre de la dizaine de secondes sur un
// téléphone) et plutôt qu'un Worker : la recherche rend la main au navigateur toutes les ~25 ms.
// Un Worker dédié ne vaudrait que pour des défis bien plus difficiles que 18 bits.

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);
const IV = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];
const W = new Uint32Array(64);

function compress(h: Uint32Array, block: Uint8Array, off: number): void {
  for (let i = 0; i < 16; i++) {
    const j = off + i * 4;
    W[i] = (block[j] << 24) | (block[j + 1] << 16) | (block[j + 2] << 8) | block[j + 3];
  }
  for (let i = 16; i < 64; i++) {
    const a = W[i - 15];
    const b = W[i - 2];
    const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
    const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
    W[i] = (W[i - 16] + s0 + W[i - 7] + s1) | 0;
  }
  let [a, b, c, d, e, f, g, hh] = h;
  for (let i = 0; i < 64; i++) {
    const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
    const ch = (e & f) ^ (~e & g);
    const t1 = (hh + S1 + ch + K[i] + W[i]) | 0;
    const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
    const maj = (a & b) ^ (a & c) ^ (b & c);
    const t2 = (S0 + maj) | 0;
    hh = g;
    g = f;
    f = e;
    e = (d + t1) | 0;
    d = c;
    c = b;
    b = a;
    a = (t1 + t2) | 0;
  }
  h[0] += a;
  h[1] += b;
  h[2] += c;
  h[3] += d;
  h[4] += e;
  h[5] += f;
  h[6] += g;
  h[7] += hh;
}

/** État après les blocs complets d'un préfixe ; le reste est traité à chaque essai. */
type Midstate = { h: Uint32Array; tail: Uint8Array; consumed: number };

function midstate(prefix: Uint8Array): Midstate {
  const h = Uint32Array.from(IV);
  const full = prefix.length - (prefix.length % 64);
  for (let off = 0; off < full; off += 64) compress(h, prefix, off);
  return { h, tail: prefix.slice(full), consumed: full };
}

/** Digest (8 mots) de `prefix || suffix`, depuis un état précalculé. */
function finish(mid: Midstate, suffix: Uint8Array): Uint32Array {
  const h = Uint32Array.from(mid.h);
  const len = mid.tail.length + suffix.length;
  const padded = new Uint8Array(Math.ceil((len + 9) / 64) * 64);
  padded.set(mid.tail, 0);
  padded.set(suffix, mid.tail.length);
  padded[len] = 0x80;
  const bits = (mid.consumed + len) * 8;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, Math.floor(bits / 2 ** 32));
  view.setUint32(padded.length - 4, bits >>> 0);
  for (let off = 0; off < padded.length; off += 64) compress(h, padded, off);
  return h;
}

export function sha256Hex(text: string): string {
  const enc = new TextEncoder().encode(text);
  const digest = finish(midstate(new Uint8Array(0)), enc);
  return Array.from(digest, (w) => (w >>> 0).toString(16).padStart(8, "0")).join("");
}

function leadingZeroBits(words: Uint32Array): number {
  let n = 0;
  for (const w of words) {
    if (w === 0) {
      n += 32;
      continue;
    }
    return n + Math.clz32(w);
  }
  return n;
}

export type SolveOptions = {
  /** Rend la main au navigateur au bout de ce délai (ms) pour que la page reste réactive. */
  sliceMs?: number;
  signal?: AbortSignal;
};

/** Cherche un nonce valide ; la recherche est découpée en tranches pour ne pas figer l'UI. */
export async function solvePow(
  challenge: string,
  bits: number,
  { sliceMs = 25, signal }: SolveOptions = {},
): Promise<string> {
  const enc = new TextEncoder();
  const mid = midstate(enc.encode(`${challenge}:`));
  let counter = Math.floor(Math.random() * 2 ** 24);
  for (;;) {
    const deadline = performance.now() + sliceMs;
    do {
      const nonce = (counter++).toString(36);
      if (leadingZeroBits(finish(mid, enc.encode(nonce))) >= bits) return nonce;
    } while (performance.now() < deadline);
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
    await new Promise((r) => setTimeout(r, 0));
  }
}
