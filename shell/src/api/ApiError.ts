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
  // P26.09 : `type` problem+json (« quota-exceeded ») et ses champs, pour un message traduit.
  readonly problemType?: string;
  readonly quota?: { kind: string; current: number; limit: number };
  // P22.04 : membre `errors[]` du problem+json (P21 : `{field, code, message}`).
  readonly errors?: { field: string; code: string; message: string }[];

  constructor(
    status: number,
    options?: {
      title?: string;
      detail?: string;
      retryAfter?: number;
      problemType?: string;
      quota?: { kind: string; current: number; limit: number };
      errors?: { field: string; code: string; message: string }[];
    },
  ) {
    super(options?.detail ?? `Erreur HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.title = options?.title;
    this.detail = options?.detail;
    this.retryAfter = options?.retryAfter;
    this.problemType = options?.problemType;
    this.quota = options?.quota;
    this.errors = options?.errors;
  }
}

// REV-271 : 412 = le cœur a refusé une écriture dont `If-Match` n'est plus la
// version courante (conflit d'édition) — distinct d'un échec d'enregistrement.
export function isConflictError(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 412;
}
