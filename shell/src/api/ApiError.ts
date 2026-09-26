// SPDX-License-Identifier: Apache-2.0

// SP-B5 : le cœur répond en RFC 7807 (`application/problem+json`, champs
// `title`+`detail`) sur toute erreur HTTP depuis SP-26, et porte un en-tête
// `Retry-After` (secondes) sur un 429 (`core/app/main.py` middleware
// `rate_limit_guard`). `request()`/`requestBlob()` (base.ts) jetaient jusqu'ici
// une `Error` générique qui perdait ces trois champs — `ApiError` les porte
// jusqu'à l'UI pour que chaque appelant puisse afficher le détail réel du
// cœur plutôt qu'un message générique, avec une branche dédiée pour le 429.
export class ApiError extends Error {
  readonly status: number;
  readonly title?: string;
  readonly detail?: string;
  readonly retryAfter?: number;

  constructor(status: number, options?: { title?: string; detail?: string; retryAfter?: number }) {
    super(options?.detail ?? `Erreur HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.title = options?.title;
    this.detail = options?.detail;
    this.retryAfter = options?.retryAfter;
  }
}
