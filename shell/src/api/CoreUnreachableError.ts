// SPDX-License-Identifier: Apache-2.0
export class CoreUnreachableError extends Error {
  constructor(cause?: unknown) {
    super("Le cœur GeoStudio est injoignable");
    this.name = "CoreUnreachableError";
    this.cause = cause;
  }
}
