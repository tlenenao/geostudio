# SP-22 « Filet qualité statique » — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** installer, dans `core/` et `shell/`, le filet de qualité statique décrit par la vague 2 du plan d'action (ruff, eslint+prettier, mypy progressif, couverture à seuil non régressif, pre-commit, contrat de couches complet, sécurité de chaîne d'outils), en 10 tâches indépendantes qui laissent l'arbre vert à chaque commit.

**Architecture:** chaque outil est configuré isolément (fichier de config + dépendance dev + job CI), avec une passe de mise en conformité automatisée en commit séparé quand l'outil corrige du code existant (ruff, eslint/prettier). Aucun code applicatif n'est modifié pour raison fonctionnelle — seulement pour raison de style/typage/frontière de module. `core/tests/test_deployability.py` (SP-21) n'est pas touché par ce plan.

**Tech Stack:** ruff, ESLint 9 (flat config) + typescript-eslint + Prettier, mypy, pytest-cov + `@vitest/coverage-v8`, pre-commit (hooks `language: system`), commitlint, CodeQL, gitleaks, Trivy, `anchore/sbom-action`, Dependabot.

**Spec de référence :** `docs/superpowers/specs/2026-08-20-sp22-filet-qualite-statique-design.md`.

## Global Constraints

- Docs, commentaires et messages utilisateur en **français** ; identifiants et code en anglais.
- Commits **conventional**, petits, un sujet (`chore(core):`, `style(core):`, `ci(core):`, `chore(shell):`, `style(shell):`, `ci(shell):`, `docs(sp22):`).
- **Aucune correction fonctionnelle** hors périmètre, même si un linter en révèle une — elle part en suivi non bloquant dans CLAUDE.md (tâche 10), sauf triviale et locale au fichier déjà touché par une passe de mise en conformité.
- Suite de référence : **mesurer en tout début de tâche 1** (`cd core && uv run pytest` et `cd shell && npm run test`) et noter les deux chiffres — ne pas réutiliser le chiffre du 2026-08-20 de SP-21, qui date d'avant ce plan et peut avoir bougé (SP-21 est en cours en parallèle). Aucune tâche de ce plan ne doit faire baisser ces deux chiffres.
- `ruff format`/`eslint --fix`/`prettier --write` ne doivent **jamais** changer de comportement, seulement du style — chaque passe de mise en conformité est suivie d'un run de la suite de tests concernée avant de committer.
- Ne pas toucher aux fichiers actuellement modifiés/non committés par SP-21 (`core/tests/test_deployability.py`, `deploy/postgis/Dockerfile`, `docker-compose.yml`, `deploy/postgis/pg_hba.conf`, `.env.example`) — ce sont des travaux en cours d'une autre vague, dans une autre session. Si `git status` montre ces fichiers modifiés en tâche 1, ne pas les stager, ne pas les committer, ne pas les discard.

## Décisions prises pendant la planification (précisions/écarts sur la spec)

1. **`line-length = 100`** pour ruff (mesuré : 788 lignes de `core/app/` dépassent 88 caractères contre 240 qui dépassent 100 — 100 minimise le bruit de reformattage sans laisser de lignes extrêmes, le max observé est 140).
2. **Le fichier d'exception de la règle `dangerouslySetInnerHTML`** est `shell/src/builder/widgets/richSection.tsx` (le seul appelant JSX réel), **pas** `sanitizeMarkdown.ts` comme la spec le disait — `sanitizeMarkdown.ts` est un `.ts` sans JSX, il ne fait que mentionner la prop dans un commentaire. Vérifié : `grep -rl dangerouslySetInnerHTML shell/src` ne renvoie que ces deux fichiers.
3. **Mypy strict par invocation `--strict` séparée**, pas par `[[tool.mypy.overrides]] strict = true`. Deux commandes : `uv run mypy --strict app/auth app/secrets app/analytics app/copilot` (bloquant) et `uv run mypy app/` (informatif, `continue-on-error`). Plus simple à raisonner que deux blocs d'overrides qui se chevauchent, résultat identique.
4. **Trivy et CodeQL sont en report-only** dans cette vague (résultats au format SARIF envoyés à l'onglet Security GitHub, `exit-code` non bloquant pour Trivy), **gitleaks reste bloquant**. Raison : `geostudio-postgis` et `geostudio-qgis-worker` dérivent d'images upstream (PostGIS, QGIS officiel) qui portent presque certainement des CVE `HIGH` non actionnables à court terme — bloquer la release dessus casserait le premier tag `v*` qui suit ce plan. Gitleaks n'a pas ce problème : un dépôt propre a zéro secret, donc bloquant dès le départ est le bon défaut. Durcir Trivy/CodeQL en bloquant est un choix produit pour une vague ultérieure, pas ce plan.
5. **SBOM publié comme artefact du run CI** (`actions/upload-artifact`), pas comme asset d'une GitHub Release — `release.yml` ne crée aujourd'hui **aucune** GitHub Release (juste un build+push d'images sur un tag `v*`), donc « attaché à la release » n'a rien à quoi s'attacher.
6. **Gitleaks scanne l'arbre de travail (`--no-git`), pas l'historique complet** — 1400+ commits contiennent presque certainement des secrets de test/dev déjà neutralisés (clés AES-GCM factices, JWT de fixtures) qui produiraient un bruit massif sans valeur ; auditer l'historique complet une fois, à la main, est hors périmètre de cette vague.
7. **Pas de `types-*` stubs ajoutés a priori** — tous les tiers importés par les 4 modules mypy stricts (`fastapi`, `pydantic`, `sqlalchemy`, `cryptography`, `httpx`, `pyjwt`) publient leurs propres types (`py.typed`) ; `duckdb`/`openpyxl` (sans stubs) sont couverts par `ignore_missing_imports = true` au niveau du fichier de config, qui s'applique quelle que soit l'invocation.

## File Structure

| Fichier | Rôle | Tâches |
|---|---|---|
| `core/pyproject.toml` | **modifié** — `[tool.ruff]`, `[tool.mypy]`, dépendances dev (`ruff`, `mypy`, `pytest-cov`), contrat de couches à 30 entrées | 1, 2, 4, 5 |
| `core/app/**/*.py` | **modifié** — passe `ruff check --fix` + `ruff format` (style seul) | 1 |
| `.github/workflows/ci.yml` | **modifié** — étapes ruff/mypy/couverture sur le job `core` ; étapes eslint/prettier/couverture sur le job `shell` | 1, 3, 4, 5 |
| `core/scripts/check_coverage.py` | **créé** — compare la couverture mesurée (XML) au seuil versionné | 5 |
| `core/tests/test_check_coverage.py` | **créé** — teste `check_coverage.py` | 5 |
| `core/.coverage-threshold` | **créé** — seuil de couverture core (entier) | 5 |
| `shell/eslint.config.js` | **créé** — ESLint 9 flat config | 3 |
| `shell/.prettierrc.json`, `shell/.prettierignore` | **créés** | 3 |
| `shell/package.json` | **modifié** — scripts `lint`/`format`/`format:check`, devDependencies eslint/prettier/typescript-eslint/react-hooks/vitest-coverage/commitlint | 3, 5, 6 |
| `shell/src/**/*.{ts,tsx}` | **modifié** — passe `eslint --fix` + `prettier --write` (style seul) | 3 |
| `shell/scripts/check-coverage.mjs` | **créé** — compare la couverture mesurée (`coverage-summary.json`) au seuil versionné | 5 |
| `shell/.coverage-threshold` | **créé** — seuil de couverture shell (entier) | 5 |
| `.pre-commit-config.yaml` | **créé** — hooks `language: system` (ruff, eslint, prettier, lint-imports, commitlint) | 6 |
| `commitlint.config.js` | **créé** — racine, `@commitlint/config-conventional` | 6 |
| `.github/workflows/codeql.yml` | **créé** — analyse Python + JS/TS | 7 |
| `.github/workflows/gitleaks.yml` | **créé** — scan de secrets, bloquant | 7 |
| `.gitleaks.toml` | **créé** — allowlist justifiée des faux positifs trouvés en tâche 7 | 7 |
| `.github/workflows/release.yml` | **modifié** — Trivy + SBOM par image publiée | 8 |
| `.github/dependabot.yml` | **créé** — écosystèmes `uv`/`pip`, `npm`, `github-actions` | 9 |
| `CLAUDE.md` | **modifié** — clôture SP-22, commandes pre-commit | 10 |

---

### Task 1: Ruff sur `core` (2.1)

**Files:**
- Modify: `core/pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: (auto) tous les fichiers `core/app/**/*.py` non conformes

**Interfaces:** aucune — tâche de tooling pure, ne produit ni ne consomme d'API pour les tâches suivantes.

- [ ] **Step 1: Mesurer la baseline de tests avant toute modification**

Run: `cd core && uv run pytest 2>&1 | tail -5` puis `cd ../shell && npm run test 2>&1 | tail -15`

Noter les deux chiffres (passed/skipped pour core, passed/failed pour shell) dans le message du premier commit de cette tâche — c'est la référence de non-régression pour tout le plan.

- [ ] **Step 2: Vérifier l'état de `git status` avant de commencer**

Run: `git status --short`

Confirmer que seuls les fichiers listés dans « Global Constraints » (travaux SP-21 en cours) apparaissent modifiés/non suivis, en plus des fichiers que cette tâche va créer. Ne rien stager qui appartienne à SP-21.

- [ ] **Step 3: Ajouter ruff comme dépendance dev et le configurer**

Run: `cd core && uv add --dev ruff`

Ajouter dans `core/pyproject.toml`, après la section `[tool.pytest.ini_options]` (avant `[tool.importlinter]`) :

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 4: Constater les violations existantes (rouge attendu, pour la bonne raison)**

Run: `uv run ruff check . 2>&1 | tail -20` et `uv run ruff format --check . 2>&1 | tail -5`

Attendu : des dizaines/centaines de violations et de fichiers « would reformat ». Si la commande échoue avec une erreur de configuration (pas une violation de règle), corriger `[tool.ruff]` avant de continuer — ne pas passer à l'étape suivante avec une config cassée.

- [ ] **Step 5: Commit — configuration seule**

```bash
git add core/pyproject.toml core/uv.lock
git commit -m "$(cat <<'EOF'
chore(core): ajoute et configure ruff (lint + format)
EOF
)"
```

- [ ] **Step 6: Passe de mise en conformité automatisée**

Run: `cd core && uv run ruff check --fix . && uv run ruff format .`

- [ ] **Step 7: Vérifier le vert — lint, format, et suite de tests inchangée**

Run: `uv run ruff check . && uv run ruff format --check .` → attendu : aucune sortie, code 0.
Run: `uv run pytest 2>&1 | tail -5` → comparer au chiffre noté en Step 1 (mêmes passed/skipped ; `ruff check --fix` peut supprimer des imports inutilisés donc une régression de comportement, bien qu'improbable, serait visible ici).

- [ ] **Step 8: Commit — passe de mise en conformité isolée**

```bash
git add core/app
git commit -m "$(cat <<'EOF'
style(core): ruff check --fix + format
EOF
)"
```

- [ ] **Step 9: Câbler ruff dans la CI**

Dans `.github/workflows/ci.yml`, job `core`, ajouter après l'étape `run: uv run pytest` et avant `run: uv run lint-imports` :

```yaml
      - run: uv run ruff check .
      - run: uv run ruff format --check .
```

- [ ] **Step 10: Vérifier localement que les commandes CI passent**

Run: `cd core && uv run ruff check . && uv run ruff format --check .`

- [ ] **Step 11: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci(core): ruff check + format dans la CI
EOF
)"
```

---

### Task 2: Compléter le contrat de couches (2.6)

**Files:**
- Modify: `core/pyproject.toml`

**Interfaces:** aucune.

**Prérequis vérifiés en amont de ce plan** (ne pas re-découvrir en tâche) :
- `app.cdc` importe `app.collections` et `app.ingestion` → doit être **au-dessus** des deux.
- `app.instance` importe `app.auth` → doit être **au-dessus** d'`app.auth`. Seul `app.main` importe `app.instance`.
- `app.search` et `app.analytics` n'importent **aucun** autre module `app.*` → peuvent aller tout en bas. `app.search` est importé par `app.copilot`, `app.items`, `app.collections` ; `app.analytics` est importé par `app.configs`, `app.features`, `app.appexport`, `app.mcp`, `app.pipelines`, `app.cdc`, `app.alerts`, `app.harvest` — tous plus haut dans la pile, donc compatible où qu'ils aillent en dessous d'eux.
- Aucun de ces 4 modules n'a de `models.py` → aucune entrée `ignore_imports` supplémentaire (`app.db -> app.X.models`) n'est nécessaire.

- [ ] **Step 1: Constater l'échec attendu**

Run: `cd core && uv run lint-imports`

Attendu : passe (les 4 nouveaux modules ne sont pas encore dans le contrat, donc rien ne les contrôle — ce n'est pas un rouge visible, c'est un **trou de couverture**, documenté ici plutôt que testé par une commande qui échoue).

- [ ] **Step 2: Modifier la liste `layers`**

Dans `core/pyproject.toml`, remplacer le bloc `layers` actuel :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.copilot",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.reports",
    "app.alerts",
    "app.export",
    "app.appexport",
    "app.tileset3d",
    "app.terrain3d",
    "app.secrets",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

par :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.copilot",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.reports",
    "app.alerts",
    "app.export",
    "app.appexport",
    "app.tileset3d",
    "app.terrain3d",
    "app.secrets",
    "app.cdc",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.instance",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
    "app.search",
    "app.analytics",
]
```

- [ ] **Step 3: Vérifier**

Run: `uv run lint-imports`

Attendu : `Contracts: 1 kept, 0 broken.` avec 30 couches. Si une couche casse, lire le message d'erreur (il nomme le module fautif et l'import interdit) — ne pas réordonner à l'aveugle, ré-vérifier l'import réel avec `grep -rh "^from app\.\|^import app\." app/<module>/*.py`.

- [ ] **Step 4: Commit**

```bash
git add core/pyproject.toml
git commit -m "$(cat <<'EOF'
chore(core): complète le contrat de couches — app.cdc, app.instance, app.search, app.analytics (I1)
EOF
)"
```

---

### Task 3: ESLint + Prettier sur `shell` (2.2)

**Files:**
- Create: `shell/eslint.config.js`
- Create: `shell/.prettierrc.json`
- Create: `shell/.prettierignore`
- Modify: `shell/package.json`
- Modify: (auto) tous les fichiers `shell/src/**/*.{ts,tsx}` non conformes

**Interfaces:** aucune.

- [ ] **Step 1: Installer les dépendances**

Run:
```bash
cd shell && npm install -D eslint@^9 @eslint/js@^9 typescript-eslint@^8 \
  eslint-plugin-react-hooks@^5 eslint-config-prettier@^9 prettier@^3
```

- [ ] **Step 2: Écrire la config Prettier**

Create `shell/.prettierrc.json`:

```json
{
  "printWidth": 100
}
```

Create `shell/.prettierignore`:

```
dist
dist-export
coverage
src/api/generated
```

- [ ] **Step 3: Écrire la config ESLint**

Create `shell/eslint.config.js`:

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import eslintConfigPrettier from "eslint-config-prettier";

export default tseslint.config(
  { ignores: ["dist", "dist-export", "coverage", "src/api/generated"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-floating-promises": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            "dangerouslySetInnerHTML interdit hors richSection.tsx — passer par sanitizeMarkdown() d'abord.",
        },
      ],
    },
  },
  {
    files: ["src/builder/widgets/richSection.tsx"],
    rules: { "no-restricted-syntax": "off" },
  },
  eslintConfigPrettier,
);
```

- [ ] **Step 4: Constater l'échec attendu**

Run: `cd shell && npx eslint . 2>&1 | tail -30`

Attendu : des violations (probablement surtout `no-floating-promises` et des soucis mineurs de hooks). Si `reactHooks.configs.recommended` n'existe pas sous ce nom dans la version installée, inspecter `node -e "console.log(Object.keys(require('eslint-plugin-react-hooks').configs))"` et utiliser la clé réellement exportée (`recommended` ou `recommended-latest` selon la version) — ne pas deviner, lire l'objet.

Run: `npx prettier --check . 2>&1 | tail -10` → attendu : liste de fichiers non formatés.

- [ ] **Step 5: Ajouter les scripts npm**

Dans `shell/package.json`, section `scripts`, ajouter :

```json
    "lint": "eslint .",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
```

- [ ] **Step 6: Commit — configuration seule**

```bash
git add shell/eslint.config.js shell/.prettierrc.json shell/.prettierignore shell/package.json shell/package-lock.json
git commit -m "$(cat <<'EOF'
chore(shell): ajoute et configure eslint (flat config) + prettier
EOF
)"
```

- [ ] **Step 7: Passe de mise en conformité automatisée**

Run: `cd shell && npx eslint . --fix && npx prettier --write .`

Toute violation `no-floating-promises` ou `no-restricted-syntax` qu'`--fix` ne corrige pas automatiquement doit être triée à la main :
- `no-floating-promises` : ajouter `void` devant l'appel si l'intention est de ne pas attendre, ou `await`/`.catch()` si une erreur silencieuse serait un bug.
- `no-restricted-syntax` (dangerouslySetInnerHTML) : ne devrait déclencher que si un **nouvel** usage existe hors `richSection.tsx` — dans ce cas, ne pas désactiver la règle, remonter le cas en suivi.

- [ ] **Step 8: Vérifier le vert — lint, format, tests, build**

Run: `npx eslint . && npx prettier --check .` → code 0.
Run: `npm run test 2>&1 | tail -15` → comparer au chiffre noté en tâche 1 Step 1.
Run: `npm run build` → doit toujours passer (`tsc --noEmit` inclus).

- [ ] **Step 9: Commit — passe de mise en conformité isolée**

```bash
git add shell/src
git commit -m "$(cat <<'EOF'
style(shell): eslint --fix + prettier
EOF
)"
```

- [ ] **Step 10: Câbler dans la CI**

Dans `.github/workflows/ci.yml`, job `shell`, ajouter après `run: npm ci` et avant `run: npm run test` :

```yaml
      - run: npm run lint
      - run: npm run format:check
```

- [ ] **Step 11: Vérifier et commit**

Run: `cd shell && npm run lint && npm run format:check`

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci(shell): eslint + prettier dans la CI
EOF
)"
```

---

### Task 4: Mypy progressif sur `core` (2.3)

**Files:**
- Modify: `core/pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: (probable) quelques fichiers dans `app/auth`, `app/secrets`, `app/analytics`, `app/copilot`

**Interfaces:** aucune.

- [ ] **Step 1: Installer et configurer**

Run: `cd core && uv add --dev mypy`

Ajouter dans `core/pyproject.toml`, après `[tool.ruff.lint]` :

```toml
[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
warn_redundant_casts = true
warn_unused_ignores = true
```

- [ ] **Step 2: Constater l'échec attendu sur le périmètre strict**

Run: `uv run mypy --strict app/auth app/secrets app/analytics app/copilot 2>&1 | tail -40`

Noter le nombre d'erreurs.

- [ ] **Step 3: Commit — configuration seule**

```bash
git add core/pyproject.toml core/uv.lock
git commit -m "$(cat <<'EOF'
chore(core): ajoute et configure mypy
EOF
)"
```

- [ ] **Step 4: Corriger les erreurs des 4 modules stricts**

Corriger fichier par fichier jusqu'à zéro erreur. Cas attendus les plus probables (à traiter au cas par cas, pas de correctif générique) :
- Paramètres/retours de fonction sans annotation → les ajouter.
- `Any` implicite sur un retour de bibliothèque non typée (`duckdb`, `openpyxl`) → soit annoter explicitement le type réel utilisé après l'appel, soit `# type: ignore[no-any-return]` avec un commentaire qui dit pourquoi (bibliothèque sans stubs).
- Après chaque fichier corrigé : `uv run mypy --strict <fichier>` pour vérifier localement avant de passer au suivant.

- [ ] **Step 5: Vérifier le vert complet**

Run: `uv run mypy --strict app/auth app/secrets app/analytics app/copilot` → 0 erreur.
Run: `uv run pytest 2>&1 | tail -5` → comparer au chiffre de référence (aucune correction mypy ne doit changer le comportement, seulement l'annotation — si un test casse, une correction a introduit un changement réel, à revoir).

- [ ] **Step 6: Commit — corrections de typage**

```bash
git add core/app/auth core/app/secrets core/app/analytics core/app/copilot
git commit -m "$(cat <<'EOF'
fix(core): corrige le typage strict de app.auth/secrets/analytics/copilot
EOF
)"
```

(Si Step 4 n'a trouvé aucune erreur à corriger, sauter ce commit.)

- [ ] **Step 7: Câbler dans la CI — bloquant sur le périmètre strict, informatif sur le reste**

Dans `.github/workflows/ci.yml`, job `core`, ajouter après l'étape `ruff format --check` :

```yaml
      - run: uv run mypy --strict app/auth app/secrets app/analytics app/copilot
      - name: Mypy (périmètre large, non bloquant)
        run: uv run mypy app/ || true
```

- [ ] **Step 8: Vérifier et commit**

Run: `cd core && uv run mypy --strict app/auth app/secrets app/analytics app/copilot`

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci(core): mypy strict sur auth/secrets/analytics/copilot + passe large informative
EOF
)"
```

---

### Task 5: Couverture, seuil non régressif (2.4)

**Files:**
- Create: `core/scripts/check_coverage.py`
- Create: `core/tests/test_check_coverage.py`
- Create: `core/.coverage-threshold`
- Create: `shell/scripts/check-coverage.mjs`
- Create: `shell/.coverage-threshold`
- Modify: `core/pyproject.toml` (dépendance `pytest-cov`)
- Modify: `shell/package.json` (dépendance `@vitest/coverage-v8`)
- Modify: `shell/vite.config.ts` (bloc `test.coverage`)
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produit : `core/scripts/check_coverage.py` — CLI `python check_coverage.py <coverage.xml> <threshold_file>`, sort avec le code 1 si la couverture mesurée est inférieure au seuil, sinon 0.
- Produit : `shell/scripts/check-coverage.mjs` — CLI `node check-coverage.mjs <coverage-summary.json> <threshold_file>`, même contrat.

- [ ] **Step 1: Écrire `check_coverage.py` et son test (rouge d'abord)**

Create `core/tests/test_check_coverage.py`:

```python
import subprocess
import sys
import textwrap

import pytest


COVERAGE_XML = textwrap.dedent(
    """\
    <?xml version="1.0" ?>
    <coverage line-rate="0.85">
    </coverage>
    """
)


def _run(xml_content: str, threshold: str, tmp_path):
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(xml_content)
    threshold_path = tmp_path / ".coverage-threshold"
    threshold_path.write_text(threshold)
    return subprocess.run(
        [sys.executable, "scripts/check_coverage.py", str(xml_path), str(threshold_path)],
        capture_output=True,
        text=True,
    )


def test_passes_when_coverage_meets_threshold(tmp_path):
    result = _run(COVERAGE_XML, "80", tmp_path)
    assert result.returncode == 0
    assert "85.00%" in result.stdout


def test_fails_when_coverage_below_threshold(tmp_path):
    result = _run(COVERAGE_XML, "90", tmp_path)
    assert result.returncode == 1
    assert "ÉCHEC" in result.stderr


def test_passes_when_coverage_exactly_at_threshold(tmp_path):
    result = _run(COVERAGE_XML, "85", tmp_path)
    assert result.returncode == 0
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `cd core && uv run pytest tests/test_check_coverage.py -v`
Expected: FAIL — `scripts/check_coverage.py` n'existe pas.

- [ ] **Step 3: Écrire le script**

Create `core/scripts/check_coverage.py`:

```python
import sys
import xml.etree.ElementTree as ET


def coverage_percent(xml_path: str) -> float:
    root = ET.parse(xml_path).getroot()
    return float(root.attrib["line-rate"]) * 100


def main(xml_path: str, threshold_path: str) -> int:
    measured = coverage_percent(xml_path)
    with open(threshold_path) as f:
        threshold = float(f.read().strip())
    print(f"Couverture mesurée : {measured:.2f}% (seuil : {threshold:.2f}%)")
    if measured < threshold:
        print(f"ÉCHEC : couverture {measured:.2f}% < seuil {threshold:.2f}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 4: Vérifier le vert**

Run: `cd core && uv run pytest tests/test_check_coverage.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Mesurer la couverture réelle et écrire le seuil**

Run: `cd core && uv add --dev pytest-cov && uv run pytest --cov=app --cov-report=term --cov-report=xml:coverage.xml`

Lire le pourcentage total affiché, écrire dans `core/.coverage-threshold` ce pourcentage **arrondi à l'entier inférieur** (pas la valeur exacte — absorbe la variance des tests `postgis`/`qgis`/`playwright` marqués, qui skippent parfois selon l'environnement). Exemple si mesuré 76.4% :

```
76
```

Ajouter `core/coverage.xml` à `.gitignore` s'il n'y est pas déjà (fichier généré, ne doit pas être commité).

- [ ] **Step 6: Écrire le script shell et sa config de couverture**

Run: `cd shell && npm install -D @vitest/coverage-v8@^3.2.6`

Dans `shell/vite.config.ts`, ajouter à `test:` :

```ts
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      exclude: ["e2e/**", "node_modules/**", "src/api/generated/**", "**/*.test.{ts,tsx}"],
    },
```

Create `shell/scripts/check-coverage.mjs`:

```js
#!/usr/bin/env node
import { readFileSync } from "node:fs";

function main(summaryPath, thresholdPath) {
  const summary = JSON.parse(readFileSync(summaryPath, "utf-8"));
  const measured = summary.total.lines.pct;
  const threshold = Number(readFileSync(thresholdPath, "utf-8").trim());
  console.log(`Couverture mesurée : ${measured.toFixed(2)}% (seuil : ${threshold.toFixed(2)}%)`);
  if (measured < threshold) {
    console.error(`ÉCHEC : couverture ${measured.toFixed(2)}% < seuil ${threshold.toFixed(2)}%`);
    process.exit(1);
  }
}

main(process.argv[2], process.argv[3]);
```

Run: `npm run test -- --coverage`, lire `coverage/coverage-summary.json` → `total.lines.pct`, écrire l'entier arrondi inférieur dans `shell/.coverage-threshold`. Ajouter `shell/coverage/` à `.gitignore` s'il n'y est pas déjà.

- [ ] **Step 7: Vérifier les deux scripts contre leur propre mesure**

Run: `cd core && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold` → code 0.
Run: `cd shell && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold` → code 0.

- [ ] **Step 8: Commit**

```bash
git add core/scripts/check_coverage.py core/tests/test_check_coverage.py core/.coverage-threshold core/pyproject.toml core/uv.lock core/.gitignore
git commit -m "$(cat <<'EOF'
test(core): couverture mesurée, seuil non régressif versionné
EOF
)"
git add shell/scripts/check-coverage.mjs shell/.coverage-threshold shell/vite.config.ts shell/package.json shell/package-lock.json shell/.gitignore
git commit -m "$(cat <<'EOF'
test(shell): couverture mesurée, seuil non régressif versionné
EOF
)"
```

- [ ] **Step 9: Câbler dans la CI**

Dans `.github/workflows/ci.yml`, job `core`, après `run: uv run mypy --strict ...` :

```yaml
      - run: uv run pytest --cov=app --cov-report=xml:coverage.xml
      - run: uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

(Cette étape **remplace** l'étape `run: uv run pytest` existante plus haut dans le job, pour ne pas lancer la suite deux fois — supprimer l'ancienne ligne `run: uv run pytest` du job `core`.)

Job `shell`, après `run: npm run test` :

```yaml
      - run: npm run test -- --coverage
      - run: node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

(Là aussi, supprimer l'ancienne ligne `run: npm run test` puisque `npm run test -- --coverage` la remplace.)

- [ ] **Step 10: Vérifier et commit**

Run localement les deux enchaînements ci-dessus pour confirmer le vert avant de committer.

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci: couverture mesurée + seuil non régressif dans core et shell
EOF
)"
```

---

### Task 6: Pre-commit (2.5)

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `commitlint.config.js`
- Modify: `shell/package.json` (devDependencies `@commitlint/cli`, `@commitlint/config-conventional`)
- Modify: `CLAUDE.md` (§ Commandes — setup one-time)

**Interfaces:** aucune.

- [ ] **Step 1: Installer commitlint**

Run: `cd shell && npm install -D @commitlint/cli@^19 @commitlint/config-conventional@^19`

- [ ] **Step 2: Écrire la config commitlint**

Create `commitlint.config.js` (racine du dépôt) :

```js
module.exports = { extends: ["@commitlint/config-conventional"] };
```

Run: `echo "feat(shell): message de test" | npx --prefix shell commitlint` → attendu : succès, aucune sortie d'erreur.
Run: `echo "message invalide sans type" | npx --prefix shell commitlint` → attendu : échec, message explicite.

- [ ] **Step 3: Écrire `.pre-commit-config.yaml`**

Create `.pre-commit-config.yaml` (racine) :

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check (core)
        entry: uv run --project core ruff check --fix
        language: system
        files: ^core/.*\.py$
      - id: ruff-format
        name: ruff format (core)
        entry: uv run --project core ruff format
        language: system
        files: ^core/.*\.py$
      - id: lint-imports
        name: import-linter (core)
        entry: uv run --project core lint-imports
        language: system
        files: ^core/app/.*\.py$
        pass_filenames: false
      - id: eslint
        name: eslint (shell)
        entry: bash -c 'cd shell && npx eslint --fix'
        language: system
        files: ^shell/src/.*\.(ts|tsx)$
      - id: prettier
        name: prettier (shell)
        entry: bash -c 'cd shell && npx prettier --write'
        language: system
        files: ^shell/src/.*\.(ts|tsx)$
      - id: commitlint
        name: commitlint
        entry: npx --prefix shell commitlint --edit
        language: system
        stages: [commit-msg]
```

- [ ] **Step 4: Installer et vérifier localement**

Run: `pip install --user pre-commit` (ou `uvx pre-commit`, si préféré — noter celle réellement utilisée dans le commit).
Run: `pre-commit install --hook-type pre-commit --hook-type commit-msg`
Run: `pre-commit run --all-files`

Attendu : vert (ruff/eslint/prettier/lint-imports ont déjà été appliqués aux tâches 1-3 ; `lint-imports` doit refléter la tâche 2). Si un hook échoue pour une raison de config (chemin `entry` incorrect selon l'OS/shell), corriger l'entrée avant de continuer — ne pas désactiver le hook.

- [ ] **Step 5: Documenter le setup one-time dans CLAUDE.md**

Dans `CLAUDE.md`, section `## Commandes`, ajouter avant le bloc `# shell` :

```markdown
# pre-commit (une fois par poste de travail)
pip install pre-commit  # ou: uvx pre-commit
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml commitlint.config.js shell/package.json shell/package-lock.json CLAUDE.md
git commit -m "$(cat <<'EOF'
chore: pre-commit (ruff, eslint, prettier, lint-imports, commitlint)
EOF
)"
```

---

### Task 7: CodeQL + gitleaks (2.7a)

**Files:**
- Create: `.github/workflows/codeql.yml`
- Create: `.github/workflows/gitleaks.yml`
- Create: `.gitleaks.toml` (si des faux positifs sont trouvés en Step 3)

**Interfaces:** aucune.

- [ ] **Step 1: Écrire le workflow CodeQL**

Create `.github/workflows/codeql.yml`:

```yaml
name: CodeQL

on:
  push:
    branches: [main, dev]
  pull_request:
  schedule:
    - cron: "0 6 * * 1"

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    strategy:
      matrix:
        language: ["python", "javascript-typescript"]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
      - uses: github/codeql-action/analyze@v3
```

- [ ] **Step 2: Écrire le workflow gitleaks**

Create `.github/workflows/gitleaks.yml`:

```yaml
name: gitleaks

on:
  push:
    branches: [main, dev]
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_CONFIG: .gitleaks.toml
          GITLEAKS_NO_GIT: "true"
```

- [ ] **Step 3: Scanner localement l'arbre de travail et trier les faux positifs**

Run (via Docker, sans installation locale) :
```bash
docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git -v
```

Pour chaque faux positif trouvé (candidats probables, à vérifier réellement plutôt que supposer) : le `CORE_SECRETS_MASTER_KEY` de test dans `.github/workflows/ci.yml` (clé AES-GCM factice encodée base64, haute entropie), tout JWT/secret de fixture dans `core/tests/`. Pour chacun confirmé inoffensif, ajouter une entrée dans `.gitleaks.toml` avec un commentaire qui dit pourquoi — même convention que `ALLOWLIST` dans `shell/scripts/check-npm-audit.mjs` :

```toml
[allowlist]
description = "Faux positifs triés le 2026-08-20 — tous des secrets de test/fixture, jamais des identifiants réels."
regexes = [
  # exemple, à remplacer par les regex/chemins réellement trouvés en Step 3 :
  # '''AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=''',
]
paths = [
  # exemple :
  # '''\.github/workflows/ci\.yml''',
]
```

Ne pas créer `.gitleaks.toml` du tout si le scan ne trouve aucun faux positif — un fichier vide n'apporte rien.

- [ ] **Step 4: Vérifier**

Run: `docker run --rm -v "$PWD":/repo -v "$PWD/.gitleaks.toml":/repo/.gitleaks.toml zricethezav/gitleaks:latest detect --source /repo --no-git --config /repo/.gitleaks.toml -v` (omettre `-v .../gitleaks.toml` si le fichier n'a pas été créé en Step 3) → code 0.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/codeql.yml .github/workflows/gitleaks.yml .gitleaks.toml
git commit -m "$(cat <<'EOF'
ci: CodeQL (report-only) + gitleaks (bloquant) sur push/PR
EOF
)"
```

(Si `.gitleaks.toml` n'a pas été créé, l'omettre du `git add`.)

---

### Task 8: Trivy + SBOM sur les images publiées (2.7b)

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:** aucune.

- [ ] **Step 1: Ajouter Trivy et SBOM après le push de chaque image**

Dans `.github/workflows/release.yml`, job `build-and-push`, après l'étape `docker/build-push-action@v6` existante, ajouter :

```yaml
      - name: Trivy (report-only)
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
          format: sarif
          output: trivy-${{ matrix.image }}.sarif
          severity: CRITICAL,HIGH
          exit-code: "0"

      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-${{ matrix.image }}.sarif
          category: trivy-${{ matrix.image }}

      - name: SBOM
        uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
          artifact-name: ${{ matrix.image }}-sbom.spdx.json
          output-file: ${{ matrix.image }}-sbom.spdx.json
```

Le job a besoin de `security-events: write` pour uploader le SARIF — ajouter à `permissions:` du job `build-and-push` (actuellement `contents: read` / `packages: write`) :

```yaml
    permissions:
      contents: read
      packages: write
      security-events: write
```

- [ ] **Step 2: Vérifier la syntaxe du workflow**

Run: `cd /home/lenen/projets/geostudio && docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest -color /repo/.github/workflows/release.yml` (si `actionlint` indisponible en sandbox, une relecture manuelle ligne à ligne des noms de step/clés YAML suffit — ne pas committer sans avoir au moins fait un `yamllint`/parse Python `import yaml; yaml.safe_load(open(...))` du fichier).

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` → aucune exception.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
ci(release): Trivy (report-only) + SBOM par image publiée
EOF
)"
```

Ce job ne peut être vérifié en vert qu'au prochain tag `v*` réel (il ne tourne pas sur push/PR) — noter dans le rapport de tâche que la vérification d'exécution réelle est différée au prochain release, comme SP-15d l'a fait pour les tests `@pytest.mark.qgis`.

---

### Task 9: Dependabot (2.7c)

**Files:**
- Create: `.github/dependabot.yml`

**Interfaces:** aucune.

- [ ] **Step 1: Vérifier le support de l'écosystème `uv`**

Consulter la documentation GitHub actuelle (`package-ecosystem` supportés) pour confirmer que `"uv"` est disponible. Si oui, l'utiliser directement ; si non, utiliser `"pip"` avec `directory: "/core"` (Dependabot lit `pyproject.toml` dans les deux cas pour un projet PEP 621, le `package-ecosystem: "uv"` change seulement s'il respecte le lockfile `uv.lock`).

- [ ] **Step 2: Écrire la config**

Create `.github/dependabot.yml` (avec `"uv"` — ajuster en `"pip"` selon le résultat du Step 1) :

```yaml
version: 2
updates:
  - package-ecosystem: "uv"
    directory: "/core"
    schedule:
      interval: "weekly"
    groups:
      core-dev-dependencies:
        dependency-type: "development"
      core-production-dependencies:
        dependency-type: "production"

  - package-ecosystem: "npm"
    directory: "/shell"
    schedule:
      interval: "weekly"
    groups:
      shell-dev-dependencies:
        dependency-type: "development"
      shell-production-dependencies:
        dependency-type: "production"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

- [ ] **Step 3: Vérifier la syntaxe**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"` → aucune exception.

- [ ] **Step 4: Commit**

```bash
git add .github/dependabot.yml
git commit -m "$(cat <<'EOF'
chore: Dependabot sur core (uv), shell (npm) et github-actions
EOF
)"
```

Dependabot ne peut être vérifié en vert qu'après son premier passage réel (planifié, pas déclenchable à la main dans ce plan) — même limite de vérification que la tâche 8.

---

### Task 10: Clôture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Lancer la suite complète des deux côtés**

Run: `cd core && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && uv run lint-imports`
Run: `cd shell && npm run lint && npm run format:check && npm run test && npm run build`

Comparer les comptes de tests aux chiffres de référence notés en tâche 1 Step 1 — aucune baisse.

- [ ] **Step 2: `pre-commit run --all-files` une dernière fois**

Run: `pre-commit run --all-files` → vert.

- [ ] **Step 3: Documenter SP-22 dans CLAUDE.md**

Ajouter une entrée `### Fait` (après l'entrée SP-21 si elle existe déjà côté `dev` à ce moment, sinon avant) résumant : les 7 chantiers livrés, les 3 écarts assumés avec la spec (fichier d'exception dangerouslySetInnerHTML, mypy `--strict` par invocation plutôt que par overrides, Trivy/CodeQL en report-only), et la limite de vérification des tâches 8/9 (jobs non déclenchables avant le prochain tag / le premier passage planifié).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(sp22): clôture — filet qualité statique (vague 2 du plan d'action)
EOF
)"
```

- [ ] **Step 5: Revue finale de branche**

Suivre `superpowers:requesting-code-review` sur l'ensemble des commits de ce plan avant merge, comme pour SP-21 et toutes les vagues précédentes.
