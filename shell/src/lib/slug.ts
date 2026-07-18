// SPDX-License-Identifier: Apache-2.0
// Miroir client du slugify serveur (core/app/items/slug.py) — écho documenté,
// PAS une frontière : le serveur reste l'autorité (409/422). Voir SP-16a.
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_LEN = 100;

export function slugify(text: string): string {
  const ascii = text.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  const dashed = ascii.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const result = dashed.slice(0, MAX_LEN).replace(/^-+|-+$/g, "");
  return result || "site";
}

export function isValidSlug(slug: string): boolean {
  return slug.length <= MAX_LEN && SLUG_RE.test(slug);
}
