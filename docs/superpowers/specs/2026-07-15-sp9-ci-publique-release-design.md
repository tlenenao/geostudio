# SP-9 — CI publique & release : design

> Sous-partie de SP-9 (Durcissement produit public v0.1). Brainstormée le
> 2026-07-15, en même temps que le reste de SP-9 — planifiable et exécutable
> indépendamment, comme `2026-07-13-sp9-gestion-collections-design.md`.

## 1. Contexte et objectif

**Constat, `​.github/workflows/ci.yml` actuel (lu intégralement) :**
- Job `migrations` : build de l'image `deploy/postgis` + `alembic upgrade
  head` / `downgrade base`.
- Job `core` : `uv run pytest` + `uv run lint-imports` contre un Postgres
  jetable réel.
- Job `api-types-drift` : régénère `openapi.json` + `core-schema.d.ts`,
  échoue si le diff n'est pas vide.
- **Rien côté shell** : ni `npm run test` (445 tests Vitest), ni
  `npm run e2e` (34 specs Playwright, auto-suffisant — `webServer` lance son
  propre build+preview, `VITE_AUTH_MODE=mock`, aucune dépendance Docker/
  réseau) ne tournent en CI aujourd'hui. Seule la génération de types passe
  par `npm ci`.
- **Aucune publication d'image** : les 3 images custom du compose
  (`deploy/postgis`, `core` — réutilisée telle quelle par le service
  `worker`, même Dockerfile — et `shell`) ne sont buildées qu'en local via
  `build:`, jamais poussées sur un registre.
- **Aucun versionning formel** : `core/pyproject.toml` et
  `shell/package.json` sont figés à `0.1.0` depuis la création du fork,
  aucun tag git, aucun `CHANGELOG.md`.

**Objectif.** La CI publique du dépôt devient la preuve visible qu'un
contributeur/évaluateur externe peut se fier à `main`/`dev` : tout le filet
de tests existant (pytest + Vitest + les 34 E2E) tourne à chaque push/PR, et
un tag `vX.Y.Z` produit des images versionnées publiées sur GHCR + une entrée
de CHANGELOG — sans introduire d'outillage de release automatisé (décision
utilisateur : manuel outillé, pas de `release-please`).

## 2. Périmètre

**Dans le périmètre v1 :**
- Nouveau job `shell` dans `ci.yml` : `npm ci` → `npm run test` →
  `npm run e2e` → `npm run build` (le build est déjà indirectement couvert
  par le `webServer` de Playwright, mais on le garde comme étape explicite et
  rapide en cas d'échec E2E dû à autre chose qu'un problème de build).
- Nouveau workflow `.github/workflows/release.yml`, déclenché sur push d'un
  tag `v*.*.*` : build + push des 3 images vers `ghcr.io/tlenenao/geostudio-
  {core,shell,postgis}:<version>` **et** `:latest` (les deux tags, comme la
  convention GHCR habituelle). Le service `worker` du compose n'a pas
  d'image dédiée — même image que `core`, commande différente (`command:` du
  compose reste inchangé) ; pas de 4ᵉ image à publier.
- `CHANGELOG.md` (racine, format Keep a Changelog) tenu à la main, une entrée
  par tag — la convention `type(scope): …` déjà en usage dans l'historique
  git permet de générer un premier jet des entrées en résumant les commits
  depuis le tag précédent, mais l'entrée finale est rédigée à la main
  (résumé produit, pas liste brute de commits).
- Bump manuel synchronisé `core/pyproject.toml`
  `[project].version`/`shell/package.json` `.version` au moment du tag —
  documenté dans `CONTRIBUTING.md` (cf. spec gouvernance) comme étape du
  process de release.

**Hors périmètre v1 (explicitement différé) :**
- Automatisation du versionning/CHANGELOG (`release-please`, `changesets`) —
  écarté par choix explicite (projet à un seul committer humain aujourd'hui,
  l'outillage de plus alourdirait sans bénéfice net immédiat).
- Configuration runtime des images `shell` publiées : le `Dockerfile` actuel
  bake `VITE_CORE_URL`/`VITE_OIDC_*` **au build** (`ARG` + `vite build`), donc
  l'image `geostudio-shell:vX.Y.Z` publiée sur GHCR n'est utilisable telle
  quelle que pour la config par défaut (`localhost`) ou après un rebuild
  local avec les bons `--build-arg`. Rendre ces variables configurables **au
  démarrage du conteneur** (injection runtime via `envsubst` dans
  `nginx.conf`/un fichier JS chargé par `index.html`) est un vrai chantier
  (le shell est un bundle statique, ces valeurs sont aujourd'hui inlinées
  par Vite) — noté comme limitation connue de cette sous-partie, pas résolu
  ici ; l'installation documentée (`sp9-install-secrets`) continue de
  recommander `docker compose up` (build local), pas de tirer l'image GHCR
  telle quelle pour une install personnalisée.
- Signature d'images (cosign/sigstore), SBOM — au-delà du « minimal » demandé
  par la roadmap pour v0.1.
- Publication sur un registre autre que GHCR (Docker Hub, etc.).

## 3. Architecture

### 3.1 Job `shell` (ajout à `ci.yml`)

```yaml
shell:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: shell
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with: { node-version: 20 }
    - run: npm ci
    - run: npm run test
    - run: npx playwright install --with-deps chromium
    - run: npm run e2e
    - run: npm run build
```
Chromium seul (pas les 3 navigateurs Playwright) — cohérent avec l'usage
actuel en local (mode mock, pas de test cross-browser explicite dans ce
projet à ce jour ; élargir si un besoin réel apparaît, YAGNI sinon).

### 3.2 Workflow `release.yml`

Déclenché sur `push: tags: ["v*.*.*"]`. Trois jobs matriciels (ou un job à 3
étapes séquentielles, plus simple à lire pour un dépôt à cette échelle) :
build+push `ghcr.io/tlenenao/geostudio-core` (contexte `./core`),
`geostudio-shell` (contexte `./shell`, mêmes `--build-arg` par défaut que le
compose de dev), `geostudio-postgis` (contexte `./deploy/postgis`).
Authentification `docker/login-action` avec `GITHUB_TOKEN` (permissions
`packages: write` sur le workflow — pas de PAT à gérer). Tag double
`${{ github.ref_name }}` + `latest`.

**Garde avant publication** : `release.yml` duplique les steps de test
(migrations + pytest + Vitest + E2E) avant le build, plutôt que de dépendre
de `ci.yml` via `workflow_call`/`workflow_run` — un tag est un événement
rare, dupliquer ~10 lignes de steps coûte moins cher à comprendre et à
maintenir qu'un couplage inter-workflows pour un dépôt à cette échelle.

### 3.3 `CHANGELOG.md`

Format Keep a Changelog standard (`## [Unreleased]`, `## [X.Y.Z] - date`,
sous-sections Added/Changed/Fixed). Première entrée `[0.1.0]` rédigée
rétroactivement en résumant les jalons déjà livrés (M1 GeoNode-free → SP-8c),
en s'appuyant sur les entrées « État » déjà écrites dans `CLAUDE.md` (source
de vérité existante, pas une nouvelle recherche depuis zéro).

## 4. Flux et gestion d'erreurs

**Push sur `dev`/`main` ou PR :** tous les jobs (`migrations`, `core`, `shell`,
`api-types-drift`) tournent en parallèle ; un seul échec bloque le merge (si
des branch protections sont configurées — hors périmètre technique de ce
spec, recommandation notée dans `CONTRIBUTING.md`).

**Tag `vX.Y.Z` poussé :** `release.yml` re-exécute les tests puis build+push.
Si les tests échouent sur un tag déjà poussé publiquement, le tag reste mais
aucune image n'est publiée — pas de suppression automatique de tag (action
destructive, hors périmètre ; le correctif est de retag après fix, documenté
dans `CONTRIBUTING.md`).

**E2E flaky en CI** (déjà observé une fois en session, cf. entrée SP-6a de
`CLAUDE.md` — un flake `publication.spec.ts` sous contention 8 workers, sans
rapport avec le code touché) : `playwright.config.ts` définit déjà `retries`
pour CI (à vérifier/ajuster en tâche plutôt que supposé ici) — géré comme un
détail d'implémentation, pas une question de design.

## 5. Tests

Cette sous-partie *est* de l'outillage CI — sa propre validation consiste à
observer un run réel :
- Un push sur une branche de travail déclenche `shell` (nouveau job) en plus
  des 3 jobs existants, les 4 verts.
- Un tag de test (`v0.1.0-rc1` sur une branche jetable, supprimé après
  vérification) déclenche `release.yml`, produit bien 3 images visibles dans
  `ghcr.io/tlenenao/geostudio-*` avec le bon tag — vérifié par un
  `docker pull` réel des 3 images après publication, pas seulement en lisant
  les logs du workflow.
- `CHANGELOG.md` : vérification manuelle de lisibilité (relecture), pas de
  test automatisé (document éditorial).

## 6. Critères d'acceptation

- `npm run test`/`npm run e2e` (shell) tournent en CI à chaque push/PR, aux
  côtés des jobs cœur existants.
- Un tag `vX.Y.Z` produit 3 images versionnées + `latest` sur GHCR,
  installables par un tiers via `docker pull`.
- `CHANGELOG.md` existe avec une entrée `[0.1.0]` rétroactive complète.
- `CONTRIBUTING.md` (spec gouvernance) documente le process de tag/release à
  la main.
- Aucune régression sur les jobs `migrations`/`core`/`api-types-drift`
  existants.
