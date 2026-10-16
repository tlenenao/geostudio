# Mesures REV-267 (LCP) et REV-283 (t03) — voie E, 2026-10-11

## Méthode LCP

Lighthouse (npx, mobile, throttling simulé par défaut, perf uniquement), Chromium Playwright 1234, build du shell servi par nginx 1.27 avec la `nginx.conf` du dépôt (gzip) sur `:8301`, cœur réel `:8200`. 3 passages par état. `/` n'est pas mesurable hors session : un visiteur anonyme est redirigé vers Keycloak (LCP 14,1 s mesuré sur la page de login Keycloak, sans rapport avec le shell) — seule `/public` (page d'atterrissage anonyme) est mesurée.

## Résultats `/public`

| État | LCP (ms) | FCP (ms) | Score |
|---|---|---|---|
| Image de la stack (référence) | 3051 / 2982 / 3319 | 2664 / 2635 / 2956 | 0,90 / 0,90 / 0,82 |
| Avant (build `dev` 28b1c713) | 2918 / 3019 / 3251 | 2703 / 2657 / 2828 | 0,91 / 0,90 / 0,87 |
| Après (`PublicCatalogPage` sans `lazy()`) | 2757 / 2796 / 2903 | 2312 / 2330 / 2386 | 0,93 / 0,92 / 0,89 |

Médiane LCP : 3019 -> 2796 ms (-220 ms, -7 %). **Cible 2,5 s non atteinte.**

## Ce que la mesure a montré

- Réseau fini à ~450 ms, LCP simulé à ~3 s : le coût est le poids du chemin critique (HTML -> `index.js` + 11 modulepreload ≈ 190 Ko gzip, `index.js` 124 Ko gzip dont 58 % inutilisé selon Lighthouse) multiplié par le ralentissement CPU 4x, pas la latence.
- Profil CPU réel : exécution JS ≈ 100 ms (négligeable) ; le temps simulé vient des octets à télécharger/parser.
- Contenu de `index.js` (source-map-explorer) : react-dom 175 Ko, **oidc-client-ts 67 Ko**, `src/api/domains` 27 Ko, Radix tooltip/popover/floating-ui ≈ 30 Ko.
- L'élément LCP est un texte statique (`<p>` de description) : il attendait le chunk lazy de la page (un aller-retour de plus). Levier appliqué : import statique de `PublicCatalogPage` (+12 Ko en charge initiale, 628,2 -> 640,4 Ko, seuil 735 Ko).

## Levier suivant (non fait, hors périmètre de la tâche)

`oidc-client-ts` + `react-oidc-context` (~67 Ko bruts, ~20 Ko gzip) ne servent à rien sur `/public` (le magasin utilisateur est en mémoire : un chargement frais est toujours anonyme) mais 17 consommateurs de `useAuth` exigent le contexte : sortir OIDC du chemin critique demande un `AuthProvider` à chargement différé avec un état « anonyme » par défaut. Estimé -200 ms, ce qui amènerait ~2,6 s : insuffisant seul. REV-267 reste **partiellement fermée** (filet canvas fait, LCP 2,8 s).

## t03 « 4 repositionnements < 2 s » (REV-283)

5 mesures (stack réelle OIDC, 500k, load average 7 à 20 pendant les mesures, autres voies actives) : étapes 1-4 = `641/316/311/2279`, `632/305/315/2260`, `924/314/311/2419`, `634/308/327/2786`, `638/346/300/2459` ms. Seule la 4e étape dépasse 2 s, systématiquement (2,26 à 2,79 s, pas 2 050 ms).

Cause identifiée côté code, pas machine : les tuiles z5 agrégées des zones de données coûtent 330-560 ms chacune côté cœur (mesure directe sur 15 tuiles autour du centre de l'étape 4 : 333, 362, 392, 557 ms pour les tuiles non vides, ~165 ms pour les vides), et se sérialisent. Le seuil n'est donc **pas relevé** ; le test reste rouge jusqu'à l'optimisation de l'agrégation de tuiles (voie A, A2). `t03-009` et `t03b-002` : à rejouer après fusion de A2 (non disponible dans cette voie).

## REV-267 — leviers E-bis-2 (OIDC différé + gzip niveau 6)

Même méthode (Lighthouse, mobile par défaut, 3 passages, build servi par nginx 1.27-alpine avec la `nginx.conf` du dépôt sur `:8301`, cœur réel `:8200`), `/public`, machine peu chargée pendant les mesures (load < 5).

| État | LCP (ms) | FCP (ms) | Score |
|---|---|---|---|
| Avant (commit `35047c55`, nginx gzip niveau 1) | 2830 / 2807 / 2801 | 2403 / 2407 / 2407 | 0,92-0,93 |
| (a) OIDC chargé à la demande, gzip niveau 1 | 2735 / 2801 / 2804 | 2320 / 2407 / 2405 | 0,93 |
| (b) gzip niveau 6 seul (sans (a)) | 2562 / 2664 / 2655 | 2149 / 2256 / 2257 | 0,94-0,95 |
| (a) + (b) | **2402 / 2398 / 2409** | 2160 / 2151 / 2157 | 0,96 |

Médiane LCP : 2807 -> **2402 ms (-405 ms)**, cible 2,5 s atteinte sur cette méthode.

### Ce que la mesure a montré

- (a) seul ne bouge presque pas le LCP simulé (médiane 2807 -> 2801) alors que `index.js` passe de 129 à 110 Ko gzip (niveau 6) et la charge initiale de 640,0 à 569,5 Ko bruts : Lantern simule le slow start TCP, donc les octets comptent par paliers d'aller-retour (fenêtre initiale ~14 Ko, doublement à chaque RTT : 14/42/98/210 Ko cumulés). `index.js` à 125 Ko (gzip niveau 1 de nginx) ou 129 Ko tient dans le même nombre de RTT ; seul un changement de palier fait gagner.
- nginx compresse par défaut en niveau 1 : `index.js` pèse 125 Ko transférés contre ~110 Ko au niveau 6. Avec (a) + (b), `index.js` franchit le palier (~98-110 Ko) et le LCP perd un RTT simulé. (b) seul gagne 150 ms, (a) + (b) 400 ms : les deux se cumulent car (a) fait passer `index.js` sous le palier suivant.
- L'élément LCP reste le `<p>` de description (rendu observé à 113 ms en conditions réelles ; seul le LCP simulé est au-dessus de la cible).

### Leviers appliqués

1. `perf(shell): charge oidc à la demande` : `AuthProvider` fournit un état anonyme sur `/public` sans retour de callback (`isAnonymousLanding`), `OidcAuthProvider` (react-oidc-context + oidc-client-ts) est un chunk `lazy()` chargé sur toute autre route, ou à la demande quand `signIn()` est appelé depuis l'état anonyme (connexion enchaînée au montage, `signInOnMount`). `useAuth()` lit un `AuthContext` (plus aucun import oidc statique). Charge initiale 640,0 -> 569,5 Ko (seuil 735 Ko).
2. `perf(shell): nginx gzip_comp_level 6` + test `src/test/nginxGzip.test.ts`.

### Non fait (non rentable ou hors périmètre)

`manualChunks`/modulepreload et icônes/i18n : non explorés, la cible étant atteinte ; `index.js` contient encore react-dom (175 Ko bruts), Radix tooltip/popover/floating-ui (~30 Ko), `src/api/domains` (27 Ko). Reste ouvert si une régression de budget survient : sortir Radix tooltip/popover du chunk d'entrée.

### Vérifications

Vitest `src/auth` + `builder/copilot` verts (129 tests), suite complète : 3055 passés, 1 échec préexistant sur `dev` (`hGuard.test.ts`, `CollectionProfilePanel.tsx` contient un `h-8`, sans lien). `npm run build` + `check-bundle-size` verts (569,5 Ko). E2E mock : 247 passés / 4 skipped / 2 échecs sous 4 workers (`extension-widget`, `pipeline-builder`), les deux verts rejoués isolément (`--workers=1`) avec `canvas-render`. Parcours OIDC réel contre Keycloak (`:8180`, shell servi sur `:8301` mappé en `:8300` par `--host-resolver-rules`) : `/public` anonyme ne requête ni `OidcAuthProvider` ni `react-oidc-context` ; une navigation client vers `/` charge le provider puis redirige vers Keycloak ; la connexion `alice` revient authentifiée sur le shell (appels cœur émis avec session) mais le cœur de cette stack refuse l'origine `:8300` en CORS (config de stack, identique sur l'ancien build) : la suite `e2e-oidc/` complète n'a pas pu être rejouée (le shell `:8300` de la stack n'est pas configuré en OIDC).

## REV-267 — remesure de clôture (lot 2, 2026-10-15)

Objectif fixé AVANT la mesure : LCP mobile `/public` < 2,5 s. Même méthode (Lighthouse CLI, mobile, throttling simulé par défaut, perf seule, Chromium Playwright 1234, build `dev` servi par nginx 1.27-alpine avec la `nginx.conf` du dépôt, cœur local mock sur `:8201`, 3 passages).

| LCP (ms) | FCP (ms) | Score |
|---|---|---|
| 2651 / 2576 / 2624 | 2190 / 2158 / 2167 | 0,94 |

Médiane **2624 ms : cible non atteinte** (2402 ms mesuré le 2026-10-11). La charge initiale est repassée de 569,5 à 615,2 Ko bruts (`index.js` 438 Ko) avec les vagues ARC/FME : `react-dom` 171 Ko, `react-router` 93 Ko, **`src/api/domains` 40 Ko** (client cœur monolithique), `shell/chrome` 10 Ko, Radix tooltip/popover/floating-ui ≈ 40 Ko.

Décision : REV-267 fermée avec mesure et résiduel. Seuil `shell/.bundle-size-threshold` abaissé de 735 à 640 Ko (plancher actuel + ~4 %), pour qu'une nouvelle régression soit visible. Levier restant, non fait : sortir `api/domains` (chargement par domaine) et Radix tooltip/popover du chunk d'entrée (~-15 Ko gzip estimés, soit un palier de slow start). `/` reste non mesurable hors session (redirection Keycloak) ; non rejoué sur stack OIDC réelle.
