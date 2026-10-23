// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { ApiError } from "../api/ApiError";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import { FeatureValidationError } from "../api/base";
import { BACKOFF_BASE_MS, BACKOFF_MAX_MS, backoffMs, decide } from "./decision";

test("backoff exponentiel de 5 s à 15 min, Retry-After fait plancher", () => {
  expect([0, 1, 2, 3].map((n) => backoffMs(n))).toEqual([5000, 10000, 20000, 40000]);
  expect(backoffMs(50)).toBe(BACKOFF_MAX_MS);
  expect(backoffMs(0, 120)).toBe(120_000);
  expect(backoffMs(0, 1)).toBe(BACKOFF_BASE_MS); // un Retry-After court n'écourte pas le backoff
});

test("réseau, 5xx, 408 : réessai avec backoff croissant", () => {
  for (const err of [
    new CoreUnreachableError(),
    new TypeError("Failed to fetch"),
    new Error("Upload failed: 403"),
    new ApiError(500),
    new ApiError(503),
    new ApiError(408),
  ]) {
    expect(decide(err, 2)).toMatchObject({ action: "retry", delayMs: 20_000 });
  }
});

test("429 : réessai à Retry-After ; quota de jeton épuisé : échec définitif", () => {
  expect(decide(new ApiError(429, { retryAfter: 90 }), 0)).toMatchObject({
    action: "retry",
    delayMs: 90_000,
    reason: "rate_limited",
  });
  expect(decide(new ApiError(429, { detail: "submission quota exhausted" }), 0)).toMatchObject({
    action: "failed_permanent",
    reason: "quota",
  });
});

test("401 : pause globale (la file reste intacte)", () => {
  expect(decide(new ApiError(401), 3)).toEqual({ action: "pause_auth" });
});

test("403 / 404 / 410 : conflit non rejoué ; 403 de preuve de travail : réessai", () => {
  expect(decide(new ApiError(403, { detail: "forbidden" }), 0)).toMatchObject({
    action: "conflict",
    reason: "forbidden",
  });
  expect(decide(new ApiError(404), 0)).toMatchObject({ action: "conflict", reason: "gone" });
  expect(decide(new ApiError(410), 0)).toMatchObject({ action: "conflict", reason: "gone" });
  expect(
    decide(new ApiError(403, { detail: "proof of work missing, invalid or expired" }), 0),
  ).toMatchObject({ action: "retry", reason: "pow" });
});

test("400 / 413 / 415 / 422 : conflit avec les erreurs de champ du serveur", () => {
  const errors = [{ field: "nom", code: "required", message: "obligatoire" }];
  for (const status of [400, 413, 415, 422])
    expect(decide(new ApiError(status, { errors }), 0)).toMatchObject({
      action: "conflict",
      reason: "invalid",
      errors,
    });
  expect(decide(new FeatureValidationError(errors), 0)).toMatchObject({
    action: "conflict",
    reason: "invalid",
    errors,
  });
});

test("409 : conflit d'unicité, sauf « opération en cours » (course d'idempotence) : réessai", () => {
  expect(decide(new ApiError(409, { detail: "feature conflicts" }), 0)).toMatchObject({
    action: "conflict",
    reason: "unique",
  });
  expect(
    decide(new ApiError(409, { detail: "idempotent operation in progress" }), 0),
  ).toMatchObject({ action: "retry", reason: "busy" });
});

test("autre 4xx inattendu : conflit, jamais rejoué en boucle", () => {
  expect(decide(new ApiError(418), 0)).toMatchObject({ action: "conflict", reason: "other" });
});
