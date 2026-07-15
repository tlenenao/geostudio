# SP-9 — CI publique & release : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire tourner l'intégralité du filet de tests (pytest + Vitest + 34
E2E Playwright) en CI publique à chaque push/PR, et faire d'un tag `vX.Y.Z`
poussé sur GitHub la source de 3 images versionnées publiées sur GHCR, avec un
`CHANGELOG.md` tenu à la main et un process de release documenté.

**Architecture:** Un nouveau job `shell` ajouté à `.github/workflows/ci.yml`
(existant : jobs `migrations`, `core`, `api-types-drift`) exécute
`npm run test` / `npm run e2e` / `npm run build`. Un nouveau workflow
`.github/workflows/release.yml`, déclenché sur push de tag `v*.*.*`, ré-exécute
les mêmes gardes de test puis build+push les 3 images du compose
(`deploy/postgis`, `core`, `shell`) vers `ghcr.io/tlenenao/geostudio-*` avec un
double tag (`${{ github.ref_name }}` + `latest`), authentifié par le
`GITHUB_TOKEN` du workflow (`packages: write`). `CHANGELOG.md` (Keep a
Changelog) et une section « Release process » dans `CONTRIBUTING.md`
complètent l'outillage — pas d'automatisation de versionning (`release-please`
etc. explicitement hors périmètre, cf. spec §2).

**Tech Stack:** GitHub Actions, `docker/build-push-action`,
`docker/login-action`, `docker/setup-buildx-action`, Playwright, Vitest,
pytest, uv.

## Global Constraints

- Registre : GHCR uniquement, sous `ghcr.io/tlenenao/geostudio-{core,shell,postgis}`
  — pas Docker Hub (spec §2, hors périmètre).
- Deux tags par image publiée : `${{ github.ref_name }}` (ex. `v0.1.0`) et
  `latest` — jamais un seul des deux.
- Aucune image dédiée pour le service `worker` du compose : il réutilise
  l'image `core` (même Dockerfile, `command:` différent dans le compose,
  inchangé par cette sous-partie).
- Pas d'automatisation de versionning/changelog (`release-please`,
  `changesets`) — bump de version et rédaction d'entrée CHANGELOG **manuels**,
  documentés dans `CONTRIBUTING.md`.
- Pas de signature d'image (cosign/sigstore) ni de SBOM — hors périmètre v1.
- `release.yml` duplique les steps de test plutôt que d'appeler `ci.yml` via
  `workflow_call`/`workflow_run` (choix assumé du spec, cf. §3.2).
- Chromium seul pour Playwright en CI (`--with-deps chromium`), pas les 3
  navigateurs — cohérent avec l'usage actuel local.
- Toute action qui pousse réellement un tag git sur `origin` ou déclenche un
  workflow GitHub réel (Task 5) est une action visible/difficile à annuler :
  **elle doit être confirmée explicitement par l'utilisateur avant
  exécution**, ne jamais la lancer de façon autonome.

---

## File Structure

- Modify `shell/playwright.config.ts` — ajoute des `retries` en CI (le job
  `shell` de Task 1 tourne pour la première fois en environnement CI partagé,
  8 workers ; un flake E2E y a déjà été observé une fois par le passé, cf.
  CLAUDE.md entrée SP-6a — donc autant le couvrir dès l'ajout du job plutôt
  que d'attendre un flake réel).
- Modify `.github/workflows/ci.yml` — ajoute le job `shell`.
- Create `.github/workflows/release.yml` — build+push GHCR sur tag.
- Create `CHANGELOG.md` — Keep a Changelog, entrée `[0.1.0]` rétroactive.
- Modify `CONTRIBUTING.md` — section « Release process ».

---

### Task 1: Job `shell` dans la CI (test + e2e + build à chaque push/PR)

**Files:**
- Modify: `shell/playwright.config.ts`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: scripts npm existants `shell/package.json` (`test`, `e2e`,
  `build` — inchangés, déjà verts en local : 466 tests Vitest, 34 specs
  Playwright).
- Produces: rien consommé par une tâche suivante (job CI autonome).

- [ ] **Step 1: Ajouter des retries Playwright en CI**

Lire d'abord le fichier actuel pour confirmer l'absence de `retries` :

```bash
cat shell/playwright.config.ts
```

Remplacer le contenu de `shell/playwright.config.ts` par :

```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  retries: process.env.CI ? 2 : 0,
  webServer: [
    {
      command: "npm run build && npm run preview -- --port 4173",
      url: "http://localhost:4173",
      reuseExistingServer: false,
      env: {
        VITE_AUTH_MODE: "mock",
        VITE_CORE_URL: "https://core.test",
        VITE_MARTIN_URL: "https://martin.test",
      },
    },
    {
      command: "node e2e/external-widget-server.mjs",
      url: "http://localhost:4174/widget.js",
      reuseExistingServer: false,
    },
  ],
});
```

Seul ajout : la ligne `retries: process.env.CI ? 2 : 0,`. Aucun changement de
comportement en local (`CI` non défini → 0 retry, identique à aujourd'hui).

- [ ] **Step 2: Vérifier que les E2E passent toujours en local**

Run: `cd shell && npm run e2e`
Expected: les 34 specs passent (34/34), comme avant le changement — la clause
`retries` ne s'active qu'avec `CI=true`.

- [ ] **Step 3: Ajouter le job `shell` à `ci.yml`**

Lire le fichier actuel pour confirmer la structure (3 jobs : `migrations`,
`core`, `api-types-drift`) :

```bash
cat .github/workflows/ci.yml
```

Ajouter le job suivant, à la suite du job `api-types-drift` (fin de fichier) :

```yaml
  shell:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: shell
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run test
      - run: npx playwright install --with-deps chromium
      - run: npm run e2e
      - run: npm run build
```

Le fichier complet `.github/workflows/ci.yml` doit ressembler à :

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:

jobs:
  migrations:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: core
    env:
      DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis
    steps:
      - uses: actions/checkout@v4
      - name: Build postgis+pgvector image
        run: docker build -t geostudio-postgis-ci:latest ../deploy/postgis
      - name: Start Postgres
        run: |
          docker run -d --name ci-postgres \
            -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis \
            -p 5432:5432 geostudio-postgis-ci:latest
          for i in $(seq 1 30); do
            docker exec ci-postgres pg_isready -U gis && break
            sleep 2
          done
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run alembic upgrade head
      - run: uv run alembic downgrade base

  core:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: core
    env:
      CORE_TEST_DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis_test
    steps:
      - uses: actions/checkout@v4
      - name: Build postgis+pgvector image
        run: docker build -t geostudio-postgis-ci:latest ../deploy/postgis
      - name: Start Postgres
        run: |
          docker run -d --name ci-postgres \
            -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis_test \
            -p 5432:5432 geostudio-postgis-ci:latest
          for i in $(seq 1 30); do
            docker exec ci-postgres pg_isready -U gis && break
            sleep 2
          done
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pytest
      - run: uv run lint-imports

  api-types-drift:
    runs-on: ubuntu-latest
    needs: core
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: uv sync
        working-directory: core
      - run: uv run python scripts/export_openapi.py openapi.json
        working-directory: core
        env:
          PYTHONPATH: .
      - run: npm ci
        working-directory: shell
      - run: npm run gen:api-types
        working-directory: shell
      - run: git diff --exit-code -- shell/src/api/generated/core-schema.d.ts

  shell:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: shell
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run test
      - run: npx playwright install --with-deps chromium
      - run: npm run e2e
      - run: npm run build
```

- [ ] **Step 4: Valider le YAML localement**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo OK`
Expected: `OK` (pas d'erreur de syntaxe YAML).

- [ ] **Step 5: Commit**

```bash
git add shell/playwright.config.ts .github/workflows/ci.yml
git commit -m "ci(shell): run npm test/e2e/build on every push and PR"
```

---

### Task 2: Workflow `release.yml` — build + push GHCR sur tag `vX.Y.Z`

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: mêmes commandes de test que Task 1 et que les jobs `migrations`/
  `core` de `ci.yml` (dupliquées ici par choix de design, cf. Global
  Constraints) ; `deploy/postgis/Dockerfile`, `core/Dockerfile`,
  `shell/Dockerfile` existants, inchangés.
- Produces: 3 images sur `ghcr.io/tlenenao/geostudio-{core,shell,postgis}`,
  tags `${{ github.ref_name }}` + `latest`, à chaque push de tag `v*.*.*`.

- [ ] **Step 1: Écrire `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags:
      - "v*.*.*"

jobs:
  test-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build postgis+pgvector image
        run: docker build -t geostudio-postgis-ci:latest ./deploy/postgis

      - name: Start Postgres
        run: |
          docker run -d --name ci-postgres \
            -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis \
            -p 5432:5432 geostudio-postgis-ci:latest
          for i in $(seq 1 30); do
            docker exec ci-postgres pg_isready -U gis && break
            sleep 2
          done

      - uses: astral-sh/setup-uv@v3

      - name: Migrations up/down
        working-directory: core
        env:
          DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis
        run: |
          uv sync
          uv run alembic upgrade head
          uv run alembic downgrade base

      - name: Core tests
        working-directory: core
        env:
          CORE_TEST_DATABASE_URL: postgresql+psycopg://gis:gis@localhost:5432/gis
        run: |
          uv run pytest
          uv run lint-imports

      - uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Shell tests
        working-directory: shell
        run: |
          npm ci
          npm run test
          npx playwright install --with-deps chromium
          npm run e2e
          npm run build

  build-and-push:
    needs: test-gate
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        include:
          - image: geostudio-core
            context: ./core
          - image: geostudio-shell
            context: ./shell
          - image: geostudio-postgis
            context: ./deploy/postgis
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          tags: |
            ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
            ghcr.io/tlenenao/${{ matrix.image }}:latest
```

Notes de conception câblées dans ce YAML :
- `test-gate` duplique volontairement les steps de `migrations`+`core`+`shell`
  de `ci.yml` (choix de design du spec §3.2 — un tag est un événement rare,
  la duplication coûte moins cher que `workflow_call`).
- `build-and-push` a `needs: test-gate` : aucune image n'est publiée si les
  tests échouent sur le tag (spec §4 — le tag reste, aucune image publiée,
  pas de suppression automatique).
- `permissions: packages: write` scoppé au job `build-and-push` seulement
  (principe du moindre privilège — `test-gate` n'a besoin d'aucune
  permission d'écriture).
- Le job `shell` du matrix construit l'image avec les `ARG` par défaut du
  `Dockerfile` (`VITE_CORE_URL=http://localhost:8200` etc., cf.
  `shell/Dockerfile` déjà lu — mêmes valeurs par défaut que
  `docker-compose.yml`, qui ne passe aucun `build-arg`) — limitation connue
  et déjà documentée dans le spec §2 (config runtime hors périmètre v1).

- [ ] **Step 2: Valider le YAML localement**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))" && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): build and push core/shell/postgis images to GHCR on tag push"
```

---

### Task 3: `CHANGELOG.md` — entrée rétroactive `[0.1.0]`

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: l'historique des entrées « État » de `CLAUDE.md` (source de
  vérité existante pour ce qui a été livré, pas une nouvelle recherche).
- Produces: rien consommé par une tâche suivante (document éditorial).

- [ ] **Step 1: Écrire `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-16

Retroactive entry covering everything shipped since the fork from
`gis-project` (2026-07-05, "option C" strangler rewrite) through SP-9's
governance/legal sub-part. See `CLAUDE.md` for the full session-by-session
history this summarizes.

### Added

- **Shell (builder & catalog)**: catalog, sharing/publication, map editor,
  full no-code builder (pages, variables, themes, templates, breakpoints,
  embryonic SDK).
- **Core platform**: JWT/OIDC auth (with a mock mode), `tenants`/`users`/
  `audit_log`, module-boundary linting, `items` module with sharing/
  publication (`can()`, groups, anonymous public items), collection registry
  with live schema introspection and per-collection RLS, OGC API Features
  (Part 1+4) for reading/writing collection data, feature-count tracking.
- **MCP server**: OAuth 2.1 + PKCE authenticated `/mcp` endpoint, 7 business
  tools (`list_items`, `get_item`, `get_app_config`, `save_app_config`,
  `create_item`, `get_sharing`, `set_sharing`), then a v1 with
  `search_catalog`, `query_features`, `create_form_app`. Same repository
  functions and `can()` gate as the REST API.
- **No-code builder features**: Formulaire widget (schema-driven forms with
  overrides, create/update/delete, geometry field), edit-from-selection on
  map/table click, CEL expressions (`visibleWhen`, calculated columns,
  generalized `{ $expr: ... }` bindings on any widget prop), composed
  actions with optional CEL conditions, typed variables.
- **Ingestion pipeline**: background jobs on Postgres (`procrastinate`, no
  broker), file upload via presigned S3 URLs, parsers for GeoJSON/CSV/
  GeoPackage/zipped Shapefile (pure Python + `pyogrio`/`pyproj`, automatic
  CRS reprojection to WGS84), automatic collection + map item creation.
- **Semantic search**: pgvector-backed hybrid search (trigram + vector,
  Reciprocal Rank Fusion) across items and collections, permission-filtered
  before scoring.
- **Web Component SDK**: widget contract for standard Web Components (no
  React required), `WcHost` bridge (props/data/user/navigate as DOM
  properties, event/action wiring, native theme inheritance), a dynamic
  extension registry (`app.extensions`) letting an admin register and
  activate/deactivate externally-hosted widget modules without a shell
  redeploy, server-side permission scoping for extension widget data
  sources, a zero-dependency reference external widget and authoring guide.
- **Collections administration**: admin UI to list, register (from
  introspected PostGIS candidates), edit, share (groups × roles), and
  unregister collections, entirely as a façade over already-audited routes.
- **Governance & legal**: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant v2.1), SPDX Apache-2.0 headers across
  `core/app/`, `core/tests/`, `shell/src/`.
- **CI**: `shell` job (`npm run test`/`npm run e2e`/`npm run build`) added
  alongside the existing `migrations`/`core`/`api-types-drift` jobs; a
  `release.yml` workflow builds and publishes versioned `core`/`shell`/
  `postgis` images to `ghcr.io/tlenenao/geostudio-*` on `vX.Y.Z` tags.

### Changed

- GeoNode, Superset, and Redis fully removed from the compose stack and the
  codebase (milestone M1, 2026-07-09) — all content operations now go
  through the core.
- `pg_featureserv` removed from the compose stack once the shell reads its
  feature layers directly from the core's OGC API Features endpoints.

### Fixed

- Several latent bugs found and fixed during branch-final reviews across
  SP-5 through SP-8 (see `CLAUDE.md` for the detailed list per sub-part):
  notably a `procrastinate` connector that prevented the worker service
  from starting under `docker compose up`, a missing `tenant_id` on the
  `Config`/`ConfigRevision` ORM models that a real Alembic-migrated
  deployment would have hit as an `IntegrityError`, and an MCP write path
  that bypassed the extension-widget permission-scope check enforced on
  the equivalent REST routes.

[Unreleased]: https://github.com/tlenenao/geostudio/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tlenenao/geostudio/releases/tag/v0.1.0
```

- [ ] **Step 2: Relecture manuelle**

Ce document est éditorial (spec §5 : « vérification manuelle de lisibilité,
pas de test automatisé »). Relire `CHANGELOG.md` en entier et vérifier :
- Chaque section correspond à un jalon réellement clos dans `CLAUDE.md`
  (comparer avec les entrées « État » de ce fichier).
- Aucune mention d'un jalon non livré (pas de SP-10+ ni des 4 sous-parties
  SP-9 non encore exécutées à la date d'écriture de ce plan : install/
  secrets, sécurité minimale, démo lecture seule).

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG.md (Keep a Changelog), retroactive [0.1.0] entry"
```

---

### Task 4: `CONTRIBUTING.md` — section « Release process »

**Files:**
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: rien de nouveau (document éditorial, référence les workflows
  créés en Task 1/2 et le fichier créé en Task 3).
- Produces: rien consommé par une tâche suivante.

- [ ] **Step 1: Lire le fichier actuel pour localiser le point d'insertion**

```bash
grep -n "^## " CONTRIBUTING.md
```

Insérer la nouvelle section juste avant `## Reporting a bug or proposing a
feature` (dernière section du fichier).

- [ ] **Step 2: Ajouter la section**

Insérer ce bloc avant `## Reporting a bug or proposing a feature` :

```markdown
## Release process

Releases are manual and tag-driven — there is no automated versioning tool
(`release-please`, `changesets`, etc.) in this repo today, by explicit
choice (single human committer, cf. `docs/superpowers/specs/2026-07-15-sp9-
ci-publique-release-design.md`).

To cut a release:

1. Make sure `dev` is green (all CI jobs passing) and merged into `main`.
2. Bump the version in both `core/pyproject.toml` (`[project].version`) and
   `shell/package.json` (`.version`) to the new `X.Y.Z`. Keep them in sync.
3. In `CHANGELOG.md`, move the `## [Unreleased]` entries under a new
   `## [X.Y.Z] - YYYY-MM-DD` heading (create the entries if `Unreleased` was
   empty, by summarizing the commits since the previous tag — the
   `type(scope): …` convention makes this easy to skim — but write the
   final wording by hand, not a raw commit list).
4. Commit: `git commit -m "chore: release vX.Y.Z"`.
5. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
6. Pushing the tag triggers `.github/workflows/release.yml`, which
   re-runs the full test suite and, if it passes, builds and pushes three
   images to `ghcr.io/tlenenao/geostudio-{core,shell,postgis}`, tagged both
   `vX.Y.Z` and `latest`.
7. Verify the images are pullable:
   `docker pull ghcr.io/tlenenao/geostudio-core:vX.Y.Z` (repeat for `shell`
   and `postgis`).

If the tests fail on a tag that's already been pushed, the tag stays (tags
are not deleted automatically — that's a destructive action, out of scope
here) and no image is published. Fix the issue, then cut a new tag
(`vX.Y.Z+1` or a corrected `vX.Y.Z`, whichever fits) rather than force-moving
the existing one.

Note: the published `geostudio-shell` image bakes `VITE_CORE_URL`/
`VITE_OIDC_*` at build time with the same defaults as the dev compose file
(`localhost`-based). It's directly usable only for that default config or
after a local rebuild with different `--build-arg` values — see the
Dockerfile. Making these configurable at container start is a separate, not-yet-scheduled
piece of work.
```

- [ ] **Step 3: Corriger la coquille dans ce même fichier (déjà notée dans
  `CLAUDE.md`, restée après la revue finale de la sous-partie gouvernance)**

Vérifier que la phrase suivante, juste après le bloc de commandes de test,
lit bien "five commands" (déjà corrigé lors de la sous-partie gouvernance,
commit `698187b docs: fix command count in CONTRIBUTING.md`) :

```bash
grep -n "must be green before opening a pull request" CONTRIBUTING.md
```

Expected: la ligne contient "All five commands" — si ce n'est pas déjà le
cas, corriger. (Ce point est probablement déjà résolu ; vérifier seulement,
ne rien changer si c'est déjà correct.)

- [ ] **Step 4: Relecture du rendu Markdown**

```bash
sed -n '/^## Release process/,/^## Reporting a bug/p' CONTRIBUTING.md
```

Expected: la section s'affiche complète, sans caractère non-ASCII parasite.

- [ ] **Step 5: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: document the tag-driven release process in CONTRIBUTING.md"
```

---

### Task 5: Validation réelle — run CI + dry-run de release (nécessite confirmation utilisateur)

**Files:** aucun fichier modifié dans cette tâche — validation seulement.

**Interfaces:**
- Consumes: les artefacts des Tasks 1-4, poussés sur une branche réelle.
- Produces: confirmation que les critères d'acceptation du spec (§6) sont
  remplis par une observation réelle, pas une lecture de logs.

**⚠️ Cette tâche pousse du code et un tag sur `origin` (dépôt GitHub réel,
`tlenenao/geostudio`) et publie potentiellement des images sous le compte
GitHub de l'utilisateur. Ce sont des actions visibles/difficiles à annuler.
Ne pas les exécuter de façon autonome — présenter ce plan à l'utilisateur et
obtenir une confirmation explicite avant chaque `git push`.**

- [ ] **Step 1: Pousser la branche et observer le job `shell`**

Après confirmation utilisateur :
```bash
git push origin <branche-de-travail>
```
Ouvrir l'onglet Actions du dépôt GitHub et vérifier que les 4 jobs
(`migrations`, `core`, `api-types-drift`, `shell`) sont déclenchés et
passent au vert. Si `shell` échoue, lire les logs du job (pas seulement
son statut) avant de corriger — cf. `superpowers:systematic-debugging` si la
cause n'est pas évidente en un coup d'œil (flake E2E vs régression réelle).

- [ ] **Step 2: Dry-run de `release.yml` sur un tag jetable**

Après confirmation utilisateur explicite (cette étape publie des images
publiques, même temporairement) :
```bash
git tag v0.1.0-rc1
git push origin v0.1.0-rc1
```
Observer le workflow `Release` dans l'onglet Actions : `test-gate` puis
`build-and-push` (3 jobs matriciels) doivent passer au vert.

- [ ] **Step 3: Vérifier les 3 images publiées par un pull réel**

```bash
docker pull ghcr.io/tlenenao/geostudio-core:v0.1.0-rc1
docker pull ghcr.io/tlenenao/geostudio-shell:v0.1.0-rc1
docker pull ghcr.io/tlenenao/geostudio-postgis:v0.1.0-rc1
```
Expected: les 3 `docker pull` réussissent (pas de 404/`manifest unknown`).

- [ ] **Step 4: Nettoyer le tag jetable (après confirmation utilisateur)**

Le tag `v0.1.0-rc1` était un tag de test (spec §5 : « supprimé après
vérification »). Après confirmation utilisateur explicite (suppression de
tag = action destructive) :
```bash
git push origin --delete v0.1.0-rc1
git tag -d v0.1.0-rc1
```
Les images GHCR déjà publiées sous ce tag peuvent rester (le spec ne demande
pas de les supprimer, seulement le tag git) — signaler leur présence à
l'utilisateur pour qu'il décide s'il veut les retirer manuellement depuis
l'interface GitHub Packages.

- [ ] **Step 5: Confirmer les critères d'acceptation du spec**

Relire `docs/superpowers/specs/2026-07-15-sp9-ci-publique-release-design.md`
§6 et cocher chaque critère contre l'observation réelle des Steps 1-3 (pas
contre une lecture de ce plan) :
- `npm run test`/`npm run e2e` tournent en CI à chaque push/PR — confirmé
  Step 1.
- Un tag `vX.Y.Z` produit 3 images versionnées + `latest`, installables par
  un tiers — confirmé Step 3.
- `CHANGELOG.md` existe avec une entrée `[0.1.0]` rétroactive complète —
  Task 3.
- `CONTRIBUTING.md` documente le process de tag/release à la main — Task 4.
- Aucune régression sur `migrations`/`core`/`api-types-drift` — confirmé
  Step 1 (les 3 jobs existants restent verts, inchangés).

---

## Self-Review Notes

- **Couverture spec** : job `shell` (§3.1, Task 1) ; `release.yml` (§3.2,
  Task 2) ; `CHANGELOG.md` (§3.3, Task 3) ; process de release documenté
  dans `CONTRIBUTING.md` (§2, Task 4) ; validation réelle par run CI + dry-run
  de tag + `docker pull` (§5/§6, Task 5). Le point "retries Playwright à
  vérifier/ajuster" du §4 est traité explicitement en Task 1 Step 1 plutôt
  que laissé implicite.
- **Pas de placeholder** : chaque step montre le YAML/Markdown complet à
  écrire, pas de "TODO" ni de renvoi à une autre tâche pour le contenu réel.
- **Cohérence des noms** : `geostudio-core`/`geostudio-shell`/
  `geostudio-postgis` (noms d'image) et `ghcr.io/tlenenao/...` (registre)
  identiques entre Task 2 (workflow), Task 3 (CHANGELOG, pas de nom d'image
  cité) et Task 4 (CONTRIBUTING, mêmes commandes `docker pull`).
