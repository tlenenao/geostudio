// SPDX-License-Identifier: Apache-2.0
import { createHash } from "node:crypto";
import { expect, test } from "vitest";
import { sha256Hex, solvePow } from "./pow";

const ref = (s: string) => createHash("sha256").update(s).digest("hex");

test("SHA-256 : vecteurs connus et toutes les longueurs autour des frontières de bloc", () => {
  expect(sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  expect(sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  for (const n of [1, 54, 55, 56, 57, 63, 64, 65, 119, 120, 128, 200]) {
    const s = "x".repeat(n);
    expect(sha256Hex(s)).toBe(ref(s));
  }
});

test("solvePow : le nonce trouvé satisfait la difficulté, vérifiée par l'implémentation de Node", async () => {
  const challenge = "v1.1999999999.0123456789abcdef." + "a".repeat(64);
  for (const bits of [8, 12, 16]) {
    const nonce = await solvePow(challenge, bits);
    const digest = createHash("sha256").update(`${challenge}:${nonce}`).digest();
    const n = BigInt("0x" + digest.toString("hex"));
    expect(256 - n.toString(2).length).toBeGreaterThanOrEqual(bits);
  }
});

test("solvePow : difficulté de production (18 bits) résolue en temps raisonnable", async () => {
  const challenge = "v1.1999999999.fedcba9876543210." + "b".repeat(64);
  const t0 = performance.now();
  const nonce = await solvePow(challenge, 18);
  expect(createHash("sha256").update(`${challenge}:${nonce}`).digest()[0]).toBe(0);
  expect(performance.now() - t0).toBeLessThan(20_000);
}, 30_000); // le délai vitest par défaut (5 s) coupait avant la borne de 20 s sur un runner chargé

test("solvePow : s'interrompt sur un signal d'annulation", async () => {
  const ctl = new AbortController();
  ctl.abort();
  await expect(solvePow("v1.x", 60, { signal: ctl.signal })).rejects.toThrow("aborted");
});
