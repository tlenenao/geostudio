# Baseline shell, 2026-10-16 (branche dev, c0251b66)

Lecture seule sur le code. Commandes lancées dans `shell/` ; Playwright en `--reporter=line`.

| Étape | Résultat |
|---|---|
| `npm ci` | OK, 24 s |
| `npm run test` (vitest) | 346 fichiers / 3221 tests, tous verts, 163 s (bruit jsdom "Not implemented: navigation", non bloquant) |
| `npm run lint` (eslint + 5 gardes i18n/couleurs/confirm/taille texte) | OK |
| `npm run format:check` | OK |
| `npm run build` (tsc + vite) | OK ; avertissement chunk > 500 kB (`MapView` 1 180 kB, 340 kB gzip) |
| `check-bundle-size` | 616,3 Ko initial / seuil 640 Ko (marge 23,7 Ko) |
| `npm run e2e` complet | 323 tests : 316 passed, 4 skipped, 3 failed (3 min 49) |

## Échecs E2E (1re passe) et rejeux (x2 chacun, groupés)

| Test | 1re passe | Rejeu 1 | Rejeu 2 | Rejeu 3 (extra) | Verdict |
|---|---|---|---|---|---|
| `ingestion-cancel.spec.ts:6` (annuler un import) | échec | OK | OK | OK | flaky |
| `analytics-context.spec.ts:2620` (SP-14h, carte sans encodages) | échec | OK | OK | OK | flaky |
| `touch-map.spec.ts:89` [tablet-touch] (pincement) | échec | OK | échec | OK | flaky (2 échecs sur 4 exécutions) |

Aucun échec reproductible à chaque rejeu : pas de régression déterministe. Les 3 sont flaky sous charge de la suite complète (workers parallèles).

### Causes observées

- `e2e/ingestion-cancel.spec.ts:40` : `getByText("Import annulé.")` en violation du mode strict : 2 éléments, le toast (`<div>Import annulé.</div>`) et la région live `<span role="status" aria-live="assertive">Notification Import annulé.</span>`. Selon le timing, la région live porte le texte au même moment que le toast. Correctif probable côté test : `getByText("Import annulé.", { exact: true })`.
- `e2e/analytics-context.spec.ts:2671` : `page.waitForRequest(... "/collections/parcelles/items")` attend 30 s sans requête (timeout du test). Posé avant `page.goto("/apps/9")`, donc soit la requête n'est pas émise sous charge (rendu lent de la carte), soit le chargement de la page est en retard. Cause exacte non établie.
- `e2e/touch-map.spec.ts:109` : le sondage de 8 s sur le changement de niveau de zoom des tuiles après un pincement CDP expire. Geste tactile synthétique sensible au timing, cause exacte non établie.

## Points d'attention

- Les 4 tests skipped n'ont pas été examinés.
- Marge du seuil de bundle faible (23,7 Ko).
