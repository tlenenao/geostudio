# j10 — Sites, storytelling, export d'apps (audit 2026-09-29)

## Périmètre couvert
- Sites : création (slug auto/explicite, collisions 409, invalides 422), cycle publier/dépublier, routes publiques (`/public/sites/{slug}`, `/public/configs/by-item`, sitemap, robots, aperçu social avec échappement), droits lecteur/analyste, changement de slug, création par l'UI depuis le modèle « Portail de données ».
- Rendu public anonyme d'un site : section riche Markdown (assainissement XSS, titre/description/canonical), fiche jeu de données (compte, téléchargement GeoJSON anonyme, page `/public/datasets/:id`, collection non publique), galerie (publiés vs brouillons, vignettes), site en mode story.
- Storytelling : navigation par chapitre, `onEnter` (variable), lien profond `/apps/:pk/:pageId`, chapitre inconnu, accès refusé à un lecteur, builder (mode Story relu, ajout de chapitre, enregistrement, actions d'entrée, lecteur : Enregistrer désactivé).
- Export d'apps : garde et gel/instantané lus dans le code ; capacité éteinte vérifiée (routes 404, panneau absent du builder) ; `printLayout` validé.

## Périmètre NON couvert (et pourquoi)
- Export d'app Statique/Connecté/Autoporté en exécution, rapports PDF et `ReportSchedule` : `CORE_APPEXPORT_ENABLED`, `CORE_EXPORT_ENABLED` et le worker d'export sont éteints (stack non modifiable). Garde, gel et instantané lus dans le code ; le gel (`freeze_config`) a été exécuté directement dans le conteneur cœur (j10-007). Cf. j10-011.
- Routage Traefik `seo-bots`, `/sitemap.xml` et `/robots.txt` à la racine : absents de la stack de dev (le shell :8300 répond le HTML de la SPA), déjà traité par j01-008.
- Vérification visuelle des cartes (widget carte, `flyTo` de story) : WebGL non exploité, le test d'`onEnter` passe par une variable.
- Import de données (POST /v1/uploads → 500, j03-001) : collections créées vides puis remplies par SQL, `feature_count` mis à jour par SQL. Écriture OGC sur collection vide en échec (j02-003).
- Édition riche dans le builder (glisser-déposer de widgets, panneau de propriétés) : seuls le chargement, l'ajout de page et l'enregistrement sont exercés.

## Méthode
Lecture du code (public/routes, items, configs, appexport guard/freeze/snapshot/jobs/routes, SitePublicPage, AppRenderer, PageManager/NavigationPanel, widgets richSection/hero/gallery/datasetCard), sondes curl, puis 30 tests Playwright (`shell/e2e/journeys/j10/`) : API réelle avec jetons Keycloak, UI réelle en OIDC (`spaGoto` : un rechargement complet perd l'authentification, j02-004) et en anonyme (contexte sans login). Résultat : 23 passent (régression), 7 sont `test.fixme` avec l'id du finding, chacun vérifié en échec réel avant d'être marqué. Trois findings (j10-008/009/010) sont issus de la lecture du code seule (confiance probable). j10-006 partage sa racine avec j04-001 (ActionsPanel) ; j10-003 concerne aussi le catalogue.

## Commandes lancées
- `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j10` (23 passed, 7 skipped)
- `npx eslint e2e/journeys/j10 && npx prettier --check e2e/journeys/j10` (verts)
- sondes curl : `/v1/public/*`, `/v1/items`, `/v1/configs`, `/v1/collections/*/sharing`, `/v1/instance`
- `docker exec … python` (freeze_config), `psql` (INSERT de lignes, feature_count)
- `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/j10 --repo-root ..`
