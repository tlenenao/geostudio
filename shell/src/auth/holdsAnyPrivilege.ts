// SPDX-License-Identifier: Apache-2.0

/** Vrai si `held` contient AU MOINS un des privilèges requis (OU, comme
 * `require_any_privilege` côté cœur). */
export function holdsAnyPrivilege(held: readonly string[], required: string | readonly string[]) {
  return (typeof required === "string" ? [required] : required).some((p) => held.includes(p));
}
