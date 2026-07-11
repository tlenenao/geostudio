# CLAUDE.md — guide de travail GeoStudio

Ce dépôt est développé **exclusivement par Claude** (sessions successives), piloté
par Tanguy. Ce fichier est le point d'entrée de chaque session : il dit où est la
vérité, ce qui est décidé, et comment on travaille ici.

## Ce qu'est ce projet

GeoStudio : plateforme d'applications géospatiales open-source (Apache-2.0).
Produit = le shell React (catalogue, éditeur de cartes, **builder no-code
config-driven**) + un cœur Python qui remplace progressivement GeoNode.
Fork de `gis-project` créé le 2026-07-05 pour exécuter l'« option C »
(refonte par étranglement) ; l'historique git (198 commits SP-0x) est conservé.

## Documents de référence (ordre d'autorité)

1. **`docs/vision/2026-07-04-feuille-de-route-geostudio.md`** — LA référence :
   phasage SP-1→SP-15, périmètre exact du remplacement de GeoNode (= l'interface
   `ItemClient`), modèle de données du cœur v0, **30 arbitrages tranchés (§8)**,
   jalons M1–M12. Un arbitrage ne se rediscute pas en session ; s'il doit changer,
   on met à jour ce document explicitement.
2. `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` — pourquoi
   l'option C, décisions produit (§9).
3. `docs/vision/2026-07-04-plateforme-webgis-nouvelle-generation.md` — vision
   long terme.
4. `docs/vision/2026-07-09-brainstorm-geostudio-analytics-platform.md` — vision
   analytics/BI/decision support (validée, déclinée en SP-14/SP-15 et A28–A30) :
   benchmark, architecture Datasets→Widgets, personas.
5. `docs/superpowers/specs/` + `plans/` — chaque SP a sa spec puis son plan datés.
6. `docs/archive/` — générations dépassées ; ne pas s'en inspirer sans lire la
   note d'archive.

## Décisions figées (ne pas re-débattre)

- Produit **open-source public**, licence **Apache-2.0**, nom **GeoStudio**.
- Cœur **Python/FastAPI** = `core/` (monolithe modulaire) ; **`tenant_id` et
  `audit_log` sur toute table/écriture dès la première migration** Alembic.
- Autorisation : tables maison, **une seule porte `can(user, action, object)`**.
- Groupes de partage gérés par le cœur (pas par Keycloak). Identité : OIDC
  délégué à Keycloak, jamais de mots de passe dans le cœur.
- API d'écriture des données : **OGC API Features dans le cœur** (sous-ensemble
  utile d'abord) ; RLS PostGIS sur les données métier à partir de SP-3.
- Jobs : **procrastinate** (file Postgres, pas de broker). Fichiers : S3 présigné.
- Expressions no-code : **CEL** (spike cel-js avant SP-5, repli JSONLogic).
- Formulaires : générés depuis le schéma des collections + overrides.
- SDK public : **Web Components (Lit) + pont React interne** — pas d'ouverture
  aux tiers avant ça ; le registre React actuel reste interne.
- Client TS du shell : types générés depuis l'OpenAPI du cœur.
- MCP : module du cœur, même process, permissions de l'utilisateur, audité.
- GeoNode/Superset/Redis : **sortis (jalon M1, 2026-07-09)** — retirés du
  compose et du code ; tout code de contenu passe par le cœur.
- Post-v0.1 (SP-10→15 ; A27 amendé : OTel puis Lakehouse, ordre SP-12→15
  ensuite à arbitrer avant leur lancement) : observabilité **OTel + profil
  `grafana/otel-lgtm`** ; lakehouse **CDC par réplication logique (worker
  maison) → GeoParquet plat** (Iceberg différé), **DuckDB côté serveur** (API
  structurée pour les widgets, SQL read-only réservé aux analystes) ; **STAC
  natif dans le cœur** + export DCAT-AP + moissonnage par référencement
  (connecteurs : STAC → **ArcGIS FS** → GetCapabilities → CSW → CKAN) ; 3D
  **deck.gl Tile3DLayer + terrain raster-dem**, impression **Playwright en
  worker**.
- Analytics (brainstorm 2026-07-09 validé) : **datasets = objets de plateforme**
  (nouveau type d'item, pipeline déclaratif + métriques CEL, A28) — SP-14
  Analytics UX (requête visuelle, contexte global temps×emprise — emprise
  opt-in par dataset, A29 —, cross-filter, SQL Lab) et SP-15 alertes & rapports
  planifiés (exports secs CSV/XLSX, A30) ; bindings CEL généralisés + variables
  typées entrent au périmètre SP-5.

## Règles d'architecture non négociables

1. **`ItemClient` (`shell/src/api/itemClient.ts`) est le sas** : le shell ne parle
   jamais à un backend de catalogue autrement qu'à travers cette interface.
2. **Tout objet de plateforme est un document déclaratif schématisé** (AppConfig,
   MapConfig, bientôt collections/formulaires) — c'est ce qui rend le MCP et la
   génération IA possibles. Pas de logique cachée hors config.
3. Apps et dashboards = **un seul runtime** `AppRenderer(config, mode)` avec modes
   edit/preview/runtime. Pas de deuxième moteur.
4. Frontières de modules du cœur outillées (lint d'imports) dès SP-1a.

## Comment on travaille

- **Workflow superpowers** : brainstorm → spec (`docs/superpowers/specs/`) → plan
  (`docs/superpowers/plans/`) → exécution TDD → E2E → review. Fichiers datés
  `YYYY-MM-DD-spX…`.
- **TDD systématique** ; chaque feature visible a sa spec E2E Playwright. Les
  13 specs E2E existantes sont le filet de la migration : elles restent vertes.
- Commits **conventional** (`feat(shell): …`, `fix(core): …`), petits, un sujet.
- Docs et messages utilisateur en **français** ; code/identifiants en anglais.
- Branche de travail : `dev` ; `main` reçoit les états stables (merge).

## Commandes

```bash
# shell
cd shell && npm ci
npm run test         # Vitest (57 fichiers, 332 tests)
npm run e2e          # Playwright (14 specs, VITE_AUTH_MODE=mock)
npm run build        # tsc --noEmit + vite build

# cœur
cd core && uv sync
uv run pytest        # 293 tests (263 exécutés + 30 marqués postgis, nécessitent docker)

# stack
docker compose up -d # nécessite .env (cf. .env.example) ; 9 services
                      # (postgis, pgbouncer, minio, martin, titiler,
                      # core, keycloak, shell, traefik)
```

## État au 2026-07-11 (mise à jour à chaque jalon)

- **Fait** : tout SP-0 (shell : catalogue, partage/publication, éditeur de carte,
  builder complet — pages, variables, thèmes, templates, breakpoints, SDK
  embryonnaire ; core : configs versionnées + rollback). Renommage
  `builder-service/`→`core/` (A14). **Tout SP-1 (a→d)** : socle du cœur (auth
  JWT OIDC + mode mock, `tenants/users/audit_log`, lint de frontières, `GET
  /me`), module `items`, partage/publication (`can()`, groupes, items publics
  anonymes), bascule complète du shell sur le cœur (`CoreItemClient`, plus
  aucun appel GeoNode), réalm Keycloak réel câblé et validé end-to-end. **Jalon
  M1 (GeoNode-free) atteint** : GeoNode/Superset/Redis retirés du compose et du
  code. **Tout SP-2 (a+b)** : serveur MCP v0 — `/mcp` authentifié OAuth
  2.1+PKCE (Keycloak Authorization Server, DCR, audience `geostudio-mcp`), puis
  les 7 outils métier (`list_items`, `get_item`, `get_app_config`,
  `save_app_config`, `create_item`, `get_sharing`, `set_sharing`, mêmes
  fonctions de repository et même porte `can()` que l'API REST,
  `actor_kind=agent` dans `audit_log`) + schéma JSON `AppConfig` publié
  (ressource MCP et endpoint HTTP). **Jalon M2 (AI-operable) atteint** : un
  agent MCP peut créer un dashboard valide qui s'ouvre dans le builder du shell.
- **SP-3a livré** (2026-07-10) : registre de collections (enregistrement
  admin, garde-fous, introspection vivante `GET /collections/{id}/schema`,
  partage groupes×rôles, accès anonyme aux collections publiques), rôle admin
  (`users.is_admin`, bootstrap `CORE_ADMIN_SUBS`, `GET/PATCH /users`), RLS
  générée par collection (rôle `gis_rls`, policy `tenant_isolation`), seed
  démo (`core/scripts/seed_demo.py`), infra de test PostGIS (marqueur
  `postgis`).
- **SP-3b livré** (2026-07-11) : OGC API Features Part 1+4 dans le cœur
  (landing, conformance, items GeoJSON — bbox, filtres, pagination avec
  liens —, POST/PUT/DELETE validés par schéma, audités), chaque requête
  métier sous `rls_scope` (rôle `gis_rls` + GUC tenant, validé à travers
  PgBouncer par `scripts/spike_pgbouncer_rls.py`).
- **SP-3c livré** (2026-07-11) : le shell lit ses couches "feature" (sélecteur
  de couches carte, sources de données du builder) directement depuis le
  cœur (`GET /collections`, `GET/POST/PUT/DELETE /collections/{id}/items`) ;
  `pg_featureserv` retiré du compose (10→9 services) et de toute la doc ;
  les 13 specs E2E restent vertes sur des mocks re-câblés. **SP-3 est clos.**
- **SP-4 livré et clos** (2026-07-11, sous-phases a+b+c) : formulaires dans le
  builder — nouveau widget Formulaire (schéma introspecté, overrides label/
  ordre/masquage/validation, écriture `feature.create`/`update`/`delete`,
  champ géométrie point, SP-4a), édition depuis la sélection carte/table
  (`itemSelected` émis par Carte et Table au clic, action `loadRecord` du
  Formulaire, mode édition avec bouton Annuler, préservation des champs/
  géométrie masqués à la modification, SP-4b), puis intégration (SP-4c) :
  `canWrite` par utilisateur exposé par le cœur sur les collections (miroir
  exact du prédicat serveur `_get_writable`), le Formulaire masque ses
  boutons d'écriture en fail-open quand `canWrite=false` (la frontière de
  sécurité reste le 403 serveur, inchangé), gabarit de galerie « Application
  de saisie » (Formulaire+Carte+Table pré-câblés sur une même source), spec
  E2E complète « déclarer un incident » + spec viewer-sans-boutons/403-forcé.
  **14 specs E2E vertes** (13 + `incident-form.spec.ts`).
- **SP-5a livré** (2026-07-11) : spike + moteur d'expressions CEL — spike
  `cel-js` validé (7/7, vocabulaire `vars`/`record`/`user`, gate A8 franchi),
  `shell/src/builder/expr.ts` (`evaluateExpression`/`validateExpression`,
  jamais throw), `visibleWhen` sur tout `WidgetItem` (masque un widget en
  preview/runtime, jamais en edit, `WidgetHost` câble `useAuth()` →
  `WidgetContext.user`), colonne calculée sur le widget Table (rétrocompatible
  avec les colonnes `string`), validation à l'édition (`getConfigExpressionErrors`,
  bouton **Enregistrer** désactivé si une expression est invalide), spec E2E
  `expressions.spec.ts`. **15 specs E2E vertes** (14 + `expressions.spec.ts`,
  20/20 tests). Revue finale de branche : aucun Critical/Important non résolu ;
  dette a11y notée hors périmètre (aria-label pré-existant sur le champ
  colonnes texte du Table, antérieur à SP-5a). Prochain chantier : **SP-5b**
  (actions composées avec condition — cf. spec SP-5
  `docs/superpowers/specs/2026-07-11-sp5-expressions-actions-composees-design.md`
  §1).
- 2026-07-09 : brainstorm **Analytics Platform** validé (Q-A1→Q-A5) et décliné
  dans la feuille de route — SP-14/SP-15, arbitrages A28–A30, amendements
  A22/A27, jalons M11/M12. Rien à exécuter avant SP-11 (sauf quick wins
  « vague 0 » opportunistes au fil de SP-4/SP-5).
- Suivi non bloquant en attente : tags d'images Docker `pgbouncer`/`martin`/
  `titiler` repinnés vers des versions résolubles (2026-07-09) ; documenter
  dans `.env.example` si de nouveaux tags dérivent à nouveau.
- Questions produit encore ouvertes : Q2 (premiers utilisateurs réels),
  Q10 (temps réel), Q11 (offline) — cf. comparatif §8. Seule Q2 peut réordonner
  SP-3/SP-6.
