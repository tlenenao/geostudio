# Filet qualité statique (SP-22)

> Vague 2 du plan d'action `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
> (§4, chantiers 2.1 → 2.7). Spec écrite le 2026-08-20, après vérification de
> l'état réel du dépôt (aucun outil de la vague n'existe encore).

## 1. Contexte & objectif

Le dépôt n'a aujourd'hui **aucun** filet de qualité statique : pas de linter ni
de formatter Python (`core/pyproject.toml` ne déclare ni `ruff` ni `mypy`), pas
d'ESLint/Prettier côté `shell` (`package.json` n'a ni script `lint` ni ces
dépendances), pas de `.pre-commit-config.yaml`, pas de seuil de couverture, et
le contrat `import-linter` ne couvre que 26 des 30 couches visées par le
constat I1 de la revue de projet (`app.cdc`, `app.analytics`, `app.search`,
`app.instance` manquent). Aucun scan de sécurité de chaîne d'outils
(SAST, secrets, images, SBOM, dépendances) n'existe.

C'est, dans les mots du plan d'action, « le levier le moins cher du dépôt, et
celui qui bénéficie le plus au modèle de développement » : des sessions LLM
successives sans mémoire partagée régressent plus facilement sur du style, du
typage ou une frontière de module qu'un humain qui garde le contexte en tête.
Un filet statique attrape ça en CI, avant la revue.

Objectif de sortie : `uv run ruff check`/`ruff format --check`, ESLint/Prettier,
mypy (périmètre déclaré), couverture (seuil non régressif), `pre-commit run
--all-files`, `lint-imports` (30 couches) et 4 jobs de sécurité de chaîne
d'outils sont tous verts en CI, avec un commit isolé de mise en conformité par
outil.

## 2. Périmètre

Les 7 chantiers du plan d'action, sans extension ni réduction.

| # | Chantier | Constat source |
|---|---|---|
| 2.1 | Ruff (lint + format) sur `core` | — |
| 2.2 | ESLint + Prettier sur `shell` | — |
| 2.3 | Mypy sur `core`, périmètre progressif | — |
| 2.4 | Couverture mesurée, seuil non régressif | — |
| 2.5 | Pre-commit | — |
| 2.6 | Compléter le contrat de couches | I1 |
| 2.7 | Sécurité de chaîne d'outils | — |

Hors périmètre (explicitement) : corriger tout le dépôt pour un mypy strict
partout (2.3 est volontairement progressif), remplacer `core-deps-audit`/
`shell-deps-audit` existants (2.7 les complète, ne les remplace pas), toute
correction fonctionnelle trouvée en passant (si un linter révèle un bug réel,
il est noté en suivi non bloquant, pas corrigé dans cette vague — sauf s'il
est trivial et dans le fichier déjà touché).

## 3. Mécanisme, par chantier

### 3.1 — Ruff (2.1)

- `uv add --dev ruff` dans `core/`.
- `[tool.ruff]` dans `core/pyproject.toml` : `target-version = "py312"`,
  `line-length` alignée sur l'existant (mesurer la longueur de ligne courante
  avant de choisir 88 vs 100 — ne pas deviner). Règles activées a minima :
  `E`, `F`, `I` (isort), `UP` (pyupgrade), `B` (bugbear) ; pas de règles
  stylistiques agressives (`D` docstrings notamment — CLAUDE.md interdit les
  commentaires superflus, un linter de docstrings obligatoires serait
  contradictoire).
- Une passe `ruff check --fix` + `ruff format` en **un seul commit isolé**
  (`style(core): ruff check --fix + format`), aucune autre modification dans
  ce commit.
- Job CI `core-lint` (ou étension du job `core` existant) : `uv run ruff check`
  et `uv run ruff format --check`.

### 3.2 — ESLint + Prettier (2.2)

- ESLint 9 (flat config, `shell/eslint.config.js`), cohérent avec React 19 /
  TS 5.6 déjà en place. Dépendances : `eslint`, `typescript-eslint`,
  `eslint-plugin-react-hooks`, `eslint-config-prettier` (désactive les règles
  de style qui entreraient en conflit avec Prettier), `prettier`.
- Règles ciblées mentionnées par le plan, à activer explicitement (pas par un
  preset générique) :
  - `react-hooks/rules-of-hooks` + `react-hooks/exhaustive-deps`.
  - Interdiction de `dangerouslySetInnerHTML` **hors**
    `shell/src/builder/widgets/sanitizeMarkdown.ts` — via
    `no-restricted-syntax` ciblé sur le nom de la prop JSX, avec une
    exception de fichier (`overrides` sur ce chemin).
  - `@typescript-eslint/no-floating-promises` — nécessite le linting
    type-aware (`parserOptions.project` pointant sur `shell/tsconfig.json`).
    Attendu **plus lent** et potentiellement bruyant au premier passage :
    prévoir une sous-étape de triage (corriger vs. `void` explicite vs.
    `// eslint-disable-next-line` documenté) avant d'activer en bloquant.
- Prettier : config par défaut du dépôt (pas de config custom sauf si le
  style existant diverge nettement après un premier `prettier --check`).
- Script `shell/package.json` : `"lint": "eslint ."`, `"format:check":
  "prettier --check ."`.
- Passe de mise en conformité en un commit isolé
  (`style(shell): eslint --fix + prettier`).
- Job CI `shell-lint` (ou extension du job `shell`) : `npm run lint` et
  `npm run format:check`.

### 3.3 — Mypy progressif (2.3)

- `uv add --dev mypy` dans `core/`.
- `[tool.mypy]` : `python_version = "3.12"`, config de base permissive
  (`ignore_errors = true` par défaut au niveau global n'est pas une option
  mypy réelle — le mécanisme correct est `[[tool.mypy.overrides]]` par module
  avec `disallow_untyped_defs = false` etc. pour tout, **puis** un override
  `strict = true` explicite sur les 4 modules ciblés :
  - `app.auth`
  - `app.secrets`
  - `app.analytics`
  - `app.copilot`
- Job CI `core-mypy` : `uv run mypy app/` en mode non-bloquant sur l'ensemble
  (`|| true` documenté comme transitoire, ou `continue-on-error: true` sur le
  job) **sauf** que le job échoue si un des 4 modules stricts a une erreur
  (deux invocations mypy séparées : une stricte sur les 4 modules qui bloque,
  une large sur `app/` qui ne bloque pas mais publie son compte d'erreurs
  dans les logs pour suivi).
- Toute erreur trouvée dans les 4 modules stricts est corrigée dans la même
  tâche (pas de `# type: ignore` de complaisance sans commentaire du
  pourquoi).

### 3.4 — Couverture, seuil non régressif (2.4)

- Core : `uv add --dev pytest-cov`. `uv run pytest --cov=app --cov-report=term
  --cov-report=xml`. Mesurer le chiffre actuel, l'écrire dans
  `core/.coverage-threshold` (entier, pourcentage arrondi **en dessous** de la
  mesure réelle pour absorber la variance des tests marqués `postgis` qui
  skippent parfois).
- Shell : `vitest run --coverage` (ajouter `@vitest/coverage-v8` en
  devDependency — package cohérent avec `vitest@^3`). Même mécanisme,
  `shell/.coverage-threshold`.
- Script de comparaison : un petit script (`core/scripts/check_coverage.py`
  et un équivalent shell, ou un seul script Python invoqué deux fois avec le
  chemin du rapport et du seuil) qui lit le pourcentage total du rapport XML/
  JSON et échoue si `mesuré < seuil`. Pas de service tiers (Codecov/Coveralls)
  — décision prise en session (§4).
- Job CI : les jobs `core` et `shell` existants gagnent une étape
  supplémentaire après les tests (pas un job séparé, pour éviter de relancer
  la suite deux fois).
- Le seuil ne descend jamais dans cette vague ; le faire remonter (quand la
  couverture progresse réellement) est un geste manuel volontaire d'une
  session future, pas automatisé ici.

### 3.5 — Pre-commit (2.5)

- `.pre-commit-config.yaml` à la racine, hooks en **`language: system`**
  (pas les hooks miroir habituels) : le monorepo mélange `uv` et `npm`, et un
  hook système réutilise l'environnement déjà installé par `uv sync`/`npm ci`
  plutôt que de faire gérer un venv/node_modules séparé par `pre-commit`
  lui-même. Chaque hook a un `files:` en regex pour ne tourner que sur les
  fichiers pertinents :
  - `ruff-check` / `ruff-format` : `entry: uv run --project core ruff check
    --fix` / `... ruff format`, `files: ^core/.*\.py$`.
  - `eslint` / `prettier` : `entry: npm --prefix shell run lint -- --fix` /
    `npm --prefix shell exec prettier -- --write`, `files: ^shell/src/.*\.
    (ts|tsx)$`.
  - `lint-imports` : `entry: uv run --project core lint-imports`,
    `files: ^core/app/.*\.py$`, `pass_filenames: false`.
  - `commitlint` (stage `commit-msg`) : `entry: npm --prefix shell exec
    commitlint --edit`, dépendance `@commitlint/config-conventional` +
    `@commitlint/cli` ajoutées à `shell/devDependencies` (pas de nouveau
    `package.json` racine), config `commitlint.config.js` à la racine
    (`module.exports = { extends: ['@commitlint/config-conventional'] }`).
    Règle vérifiée contre les types déjà utilisés par l'historique du dépôt
    (`feat`, `fix`, `test`, `docs`, `ci`, `style`, `refactor`, `chore`) — la
    config par défaut de `config-conventional` les couvre tous.
- `README.md` ou une note dans `CLAUDE.md` § Commandes : `pip install
  pre-commit && pre-commit install --hook-type pre-commit --hook-type
  commit-msg` en setup one-time (hors CI, chaque session/développeur
  l'installe une fois).
- Preuve de sortie : `pre-commit run --all-files` vert sur le dépôt après la
  passe de mise en conformité de 3.1/3.2.

### 3.6 — Compléter le contrat de couches (2.6)

- Ajouter à `[[tool.importlinter.contracts]].layers` dans
  `core/pyproject.toml` :
  - `app.cdc` juste au-dessus d'`app.ingestion` (position dans la liste
    actuelle : entre `app.secrets` et `app.ingestion`).
  - `app.analytics` et `app.search` tout en bas de la pile (après
    `app.tenants`, avant... — en fait la couche la plus basse de la liste
    actuelle est `app.tenants` ; ces deux modules n'ont probablement aucune
    dépendance montante donc leur position exacte entre elles n'a pas
    d'impact, à vérifier avec `lint-imports` après ajout).
  - `app.instance` — module à confirmer par grep (`ls core/app/instance`)
    avant d'écrire sa position ; s'il n'existe pas encore comme module
    réel, ne pas l'ajouter au contrat (un module fantôme dans le contrat
    `layers` fait échouer `import-linter` s'il est absent — **à vérifier
    empiriquement en tâche**, ne pas supposer).
- Le plan affirme « correctif déjà validé empiriquement : le contrat passe » —
  la tâche correspondante revérifie avec `uv run lint-imports` avant de
  committer, ne fait pas confiance à l'affirmation seule.
- Preuve de sortie : `uv run lint-imports` → *N kept, 0 broken* avec le
  nombre de couches réellement obtenu (30 si les 4 s'ajoutent proprement).

### 3.7 — Sécurité de chaîne d'outils (2.7)

Décisions prises en session (dépôt confirmé public) :

- **CodeQL** : nouveau `.github/workflows/codeql.yml`, setup avancé (pas le
  « default setup » de l'onglet Security, pour garder la config versionnée
  et revuable comme le reste du dépôt), langages `python` et
  `javascript-typescript`, déclenché sur push/PR vers `main`/`dev` + un
  cron hebdomadaire.
- **gitleaks** : job CI dédié (`gitleaks/gitleaks-action`), sur push/PR ;
  pas ajouté à pre-commit dans cette vague (le plan ne le demande qu'en CI —
  2.5 liste `ruff, eslint, prettier, lint-imports, conventional`, pas
  gitleaks).
- **Trivy** : job dans `release.yml`, après le build des 8 images (dépend de
  la matrice `build-and-push` de SP-21 tâche 1), scan de chaque image
  publiée (`aquasecurity/trivy-action`), échoue sur `CRITICAL,HIGH` par
  défaut — seuil à discuter si trop bruyant sur les images tierces
  (`postgis`, `qgis-worker` embarque QGIS upstream).
- **SBOM** : `anchore/sbom-action` (génère un SBOM SPDX par image), attaché
  aux assets de la release GitHub.
- **Dependabot** : `.github/dependabot.yml`, 3 écosystèmes :
  `package-ecosystem: "uv"` (répertoire `/core` — **à vérifier en tâche** que
  Dependabot supporte nativement l'écosystème `uv` à la date d'exécution ;
  repli sur `"pip"` avec `core/requirements.txt` généré si `uv` n'est pas
  encore supporté), `"npm"` (répertoire `/shell`), `"github-actions"`
  (répertoire `/`). Cadence hebdomadaire, groupées par type (`dev`
  vs. `prod`) pour limiter le bruit de PR.

Ces 4 mécanismes sont additifs : ils ne remplacent ni `core-deps-audit`
(`pip-audit --strict`) ni `shell-deps-audit` (`npm audit`) déjà existants.

## 4. Décisions prises en session (2026-08-20)

- **2.7 conservé dans le périmètre** (pas reporté à une vague séparée).
- **CodeQL plutôt que Semgrep** — le dépôt est public sur GitHub, CodeQL est
  gratuit et natif (onglet Security), pas de compte tiers.
- **Dependabot plutôt que Renovate** — natif GitHub, aucune app tierce à
  installer sur le dépôt.
- **Seuil de couverture par fichier versionné** plutôt qu'un service tiers
  (Codecov/Coveralls) — pas de compte externe ni de secret CI à gérer.
- **commitlint plutôt qu'un hook shell maison** pour la vérification de
  message conventional — standard de facto, config minimale.

## 5. Ordre d'exécution recommandé

1. 2.1 (ruff) et 2.6 (couches) sont indépendants et rapides — bon point de
   départ, aucune dépendance croisée.
2. 2.2 (eslint/prettier) ensuite — même nature que 2.1, module `shell`
   indépendant.
3. 2.3 (mypy) et 2.4 (couverture) après — nécessitent un dépôt déjà propre
   (ruff/eslint) pour ne pas mélanger deux classes de correctifs dans un
   même diff.
4. 2.5 (pre-commit) en avant-dernier — assemble les outils des chantiers
   1→4, n'a de sens qu'une fois qu'ils existent tous.
5. 2.7 (sécurité) en dernier, indépendant du reste mais volumineux (4 jobs) —
   éviter qu'un job de sécurité bruyant bloque la mise en place du filet de
   base.

## 6. Validation & preuves de sortie

- `cd core && uv run ruff check && uv run ruff format --check` → vert.
- `cd shell && npm run lint && npm run format:check` → vert.
- `cd core && uv run mypy app/auth app/secrets app/analytics app/copilot`
  → 0 erreur ; `uv run mypy app/` (large) → compte publié, non bloquant.
- `cd core && uv run pytest --cov=app` → pourcentage ≥ contenu de
  `.coverage-threshold` ; idem `npm run test -- --coverage` côté shell.
- `pre-commit run --all-files` → vert.
- `cd core && uv run lint-imports` → *N kept, 0 broken*, 30 couches.
- Les 4 jobs de sécurité tournent verts sur une PR de test (ou au minimum
  s'exécutent sans erreur de configuration — un vrai `HIGH` trouvé par Trivy
  sur une image tierce n'est pas un échec de la vague, c'est un suivi noté).
- Suite de référence avant de commencer (comme SP-21) : mesurer
  `cd core && uv run pytest` et le nombre shell (`npm run test`) ; aucune
  tâche ne doit faire baisser ces chiffres.

## 7. Risques et limites connues

- `no-floating-promises` type-aware peut être lent et bruyant au premier
  passage — budget de triage explicite dans la tâche 2.2, pas une simple
  activation.
- `app.instance` (2.6) n'est peut-être pas un module réel aujourd'hui — la
  tâche vérifie avant d'écrire, n'ajoute pas de couche fantôme.
- L'écosystème Dependabot `uv` est récent : à reconfirmer au moment de la
  tâche 2.7, avec repli documenté sur `pip`.
- Trivy sur `postgis`/`qgis-worker` (images dérivées d'upstreams tiers,
  QGIS notamment) peut remonter des `HIGH` non actionnables à court terme —
  le seuil de sévérité peut nécessiter un ajustement après un premier run
  réel, pas deviné à l'avance.
- Aucune correction fonctionnelle hors périmètre n'est faite dans cette
  vague, même si un linter en révèle une — elle part en suivi non bloquant
  dans CLAUDE.md, sauf triviale et locale au fichier déjà touché par la
  passe de mise en conformité.
