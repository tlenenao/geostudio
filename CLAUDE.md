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
   phasage SP-1→SP-13, périmètre exact du remplacement de GeoNode (= l'interface
   `ItemClient`), modèle de données du cœur v0, **27 arbitrages tranchés (§8)**,
   jalons M1–M10. Un arbitrage ne se rediscute pas en session ; s'il doit changer,
   on met à jour ce document explicitement.
2. `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` — pourquoi
   l'option C, décisions produit (§9).
3. `docs/vision/2026-07-04-plateforme-webgis-nouvelle-generation.md` — vision
   long terme.
4. `docs/superpowers/specs/` + `plans/` — chaque SP a sa spec puis son plan datés.
5. `docs/archive/` — générations dépassées ; ne pas s'en inspirer sans lire la
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
- Post-v0.1 (SP-10→13, ordre figé par A27) : observabilité **OTel + profil
  `grafana/otel-lgtm`** ; lakehouse **CDC par réplication logique (worker
  maison) → GeoParquet plat** (Iceberg différé), **DuckDB côté serveur** (API
  structurée pour les widgets, SQL read-only réservé aux analystes) ; **STAC
  natif dans le cœur** + export DCAT-AP + moissonnage par référencement
  (connecteurs : STAC → GetCapabilities → CSW → CKAN) ; 3D **deck.gl
  Tile3DLayer + terrain raster-dem**, impression **Playwright en worker**.

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
npm run test         # Vitest (56 fichiers, 277 tests)
npm run e2e          # Playwright (13 specs, VITE_AUTH_MODE=mock)
npm run build        # tsc --noEmit + vite build

# cœur
cd core && uv sync
uv run pytest        # 155 tests

# stack
docker compose up -d # nécessite .env (cf. .env.example) ; 10 services
                      # (postgis, pgbouncer, minio, martin, titiler,
                      # pg-featureserv, core, keycloak, shell, traefik)
```

## État au 2026-07-09 (mise à jour à chaque jalon)

- **Fait** : tout SP-0 (shell : catalogue, partage/publication, éditeur de carte,
  builder complet — pages, variables, thèmes, templates, breakpoints, SDK
  embryonnaire ; core : configs versionnées + rollback). Renommage
  `builder-service/`→`core/` (A14). **Tout SP-1 (a→d)** : socle du cœur (auth
  JWT OIDC + mode mock, `tenants/users/audit_log`, lint de frontières, `GET
  /me`), module `items`, partage/publication (`can()`, groupes, items publics
  anonymes), bascule complète du shell sur le cœur (`CoreItemClient`, plus
  aucun appel GeoNode), réalm Keycloak réel câblé et validé end-to-end. **Jalon
  M1 (GeoNode-free) atteint** : GeoNode/Superset/Redis retirés du compose et du
  code.
- **Prochain chantier : SP-2** (serveur MCP v0 — voir feuille de route §M2 /
  "AI-operable") : un agent doit pouvoir créer un dashboard valide via MCP.
- Suivi non bloquant en attente : tags d'images Docker `pgbouncer`/`martin`/
  `titiler` repinnés vers des versions résolubles (2026-07-09) ; documenter
  dans `.env.example` si de nouveaux tags dérivent à nouveau.
- Questions produit encore ouvertes : Q2 (premiers utilisateurs réels),
  Q10 (temps réel), Q11 (offline) — cf. comparatif §8. Seule Q2 peut réordonner
  SP-3/SP-6.
