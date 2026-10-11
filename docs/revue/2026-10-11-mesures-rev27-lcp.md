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
