# Faire passer les 33 fonctionnalités « priorité moyenne » sous 90 au-dessus de 90 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire passer 32 des 33 fonctionnalités `priorite: "moyenne"` du bilan SP-61 actuellement
sous 90 de santé au-dessus de 90, et verrouiller ce résultat en CI (nouveau plancher
`plancher_priorite_moyenne`). La 33e (`catalogue-mes-vues-signets`, « Mes vues ») ne peut pas
dépasser 90 dans un périmètre raisonnable (spec §4.bis) — traitée comme une exception nommée et
documentée, jamais forcée artificiellement.

**Architecture:** Quatre volets, dans l'ordre de dépendance. **(A) Outil** — généraliser deux
mécanismes de `core/scripts/feature_health/` : `deployability_rules()` (chaîne de divisions
arbitraire, scan de tous les `test_*.py`, repli par sous-chaîne littérale — Task 1) et
`score_guard()` (nouvelle catégorie déclarée « garde auto-scopée » — Task 2). **(C) Vrais trous de
test** — 5 tests structurels d'infrastructure jamais écrits (Task 3), la couverture de `useAuth.ts`
(Task 4), et 19 fonctionnalités du Builder/Catalogue/Automatisation regroupées par fichier partagé
(Tasks 5-11). **(D) Clôture** — régénérer le bilan, vérifier 32 des 33 lignes ≥ 90, généraliser et
fixer le plancher CI avec une exception nommée pour la 33e (Task 12, dernière).

**Tech Stack:** Python 3.14 / pytest / AST stdlib (cœur), TypeScript / React / Vitest / Testing
Library (shell).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-15-priorite-moyenne-sante-90-design.md`.
- Aucune nouvelle route REST/MCP/route shell n'est créée par ce plan — `docs/revue/
  inventaire-fonctionnalites.jsonl` ne gagne aucune nouvelle ligne, seules 6 lignes existantes
  gagnent `garde_auto_scopee` (Task 2).
- Toute modification de `core/scripts/feature_health/*.py` doit rester un élargissement
  **générique** des mécanismes déjà en place — jamais un cas particulier nommé sans justification
  vérifiée dans le code réel (l'exception `catalogue-mes-vues-signets` de Task 12 est le seul cas
  nommé de ce plan, délibérément, documentée en spec §4.bis).
- Chaque nouveau test doit exercer un comportement réel, falsifiable (retirer l'assertion/le
  correctif, confirmer que le test casse, remettre) — jamais un test qui passerait aussi bien sur
  une implémentation vide. Pour les tâches de pure couverture (Tasks 4-11), zéro ligne de production
  n'est modifiée — seuls les fichiers de test changent (sauf falsification temporaire, toujours
  restaurée avant le commit).
- Chaque tâche de couverture (Tasks 4-11) mesure la couverture RÉELLE avant/après avec la commande
  exacte donnée — jamais une valeur supposée ou recopiée d'une autre exécution.
- Docs et commentaires de code en français, identifiants en anglais (convention du dépôt).
- Commits conventionnels, un sujet par commit (`fix(core): …`, `test(core): …`, `test(shell): …`,
  `feat(core): …`).
- **Task 12 (Volet D) ne peut s'exécuter qu'après TOUTES les tâches précédentes** — elle lit la
  valeur réellement mesurée du plancher et régénère le bilan complet. Les Tasks 1-11 sont, elles,
  indépendantes entre elles (aucune ne modifie un fichier qu'une autre touche) et peuvent s'exécuter
  dans n'importe quel ordre ou en parallèle — à l'exception de la Task 11, qui suppose Task 1 déjà
  fusionnée avant de conclure que « Transformer spatialement via QGIS Processing » n'a besoin
  d'aucun travail supplémentaire (elle ne modifie aucun fichier de Task 1, juste une hypothèse de
  lecture à revérifier).

---

## File Structure

- **Modify** `core/scripts/feature_health/coverage_facts.py` — `deployability_rules()` généralisé
  (Task 1).
- **Modify** `deploy/backup/test_retention.py` — docstring de référence littérale (Task 1).
- **Modify** `core/tests/test_feature_health_coverage.py` — 3 nouveaux tests (Task 1).
- **Modify** `core/scripts/feature_health/model.py` — `Feature.auto_scoped_guard` additif (Task 2).
- **Modify** `core/scripts/feature_health/rest_surface.py` — branche `score_guard` (Task 2).
- **Modify** `docs/revue/inventaire-fonctionnalites.jsonl` — 6 lignes gagnent `garde_auto_scopee`
  (Task 2).
- **Modify** `core/tests/test_feature_health_rest_surface.py` — 3 nouveaux tests (Task 2).
- **Modify** `core/tests/test_deployability.py` — 5 nouveaux tests structurels (Task 3).
- **Create** `shell/src/auth/useAuth.test.ts` — 5 tests, aucun test dédié n'existait (Task 4).
- **Modify** `shell/src/builder/widgets/{hero,datasetCard,gallery,richSection}.test.tsx` (Task 5).
- **Modify** `shell/src/builder/widgets/{chart,tabs,navigation}.test.tsx` (Task 6).
- **Modify** `shell/src/builder/CrossFilterLinkEditor.test.tsx`,
  `shell/src/builder/widgets/selectFilter.test.tsx` (Task 7).
- **Modify** `shell/src/builder/{GridCanvas,VariablesPanel}.test.tsx`,
  `shell/src/builder/visualQuery/QueryJoinPicker.test.tsx` (Task 8).
- **Modify** `shell/src/builder/appexport/AppExportPanel.test.tsx`,
  `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx` (Task 9).
- **Modify** `shell/src/shell/{EditCollectionPanel,routes}.test.tsx` (Task 10).
- **Modify** `core/tests/test_report_jobs.py` ; **Create** `core/tests/test_cdc_jobs.py`,
  `shell/src/builder/report/ReportScheduleEditor.test.tsx` ; **Modify**
  `shell/src/pages/ReportEditPage.test.tsx` (Task 11).
- **Modify** `core/scripts/feature_health/scoring.py`, `core/scripts/feature_health_cli.py`,
  `core/scripts/feature_health_thresholds.json`, `core/tests/test_feature_health_{scoring,cli}.py`,
  `docs/revue/bilan-fonctionnalites.{html,md}`, `docs/revue/historique-sante.jsonl`,
  `docs/revue/2026-09-04-backlog.md` (Task 12, dernière).

---

### Task 1: généraliser `deployability_rules()` (chaîne de divisions, multi-fichiers, repli littéral)

**Files:**
- Modify: `core/scripts/feature_health/coverage_facts.py`
- Modify: `deploy/backup/test_retention.py`
- Test: `core/tests/test_feature_health_coverage.py`

**Interfaces:**
- Consomme : rien de nouveau — `deployability_rules(repo: pathlib.Path) -> dict[str, tuple[str, ...]]`
  garde exactement sa signature.
- Produit : `deployability_rules()` reconnaît désormais 3 fichiers de preuve supplémentaires sans
  aucun nouveau test applicatif : `deploy/qgis-worker/Dockerfile`, `deploy/backup/retention.py`,
  `deploy/qgis-worker/server.py` — consommé tel quel par les tâches suivantes de ce plan (Task
  [C.2-C.6] s'appuie sur le même mécanisme généralisé pour `deploy/backup/Dockerfile`).

**Contexte vérifié en exécutant le code réel** (pas supposé) :

```
$ PYTHONPATH=. uv run python3 -c "...deployability_rules(repo)..."
deploy/qgis-worker/Dockerfile -> AUCUNE RÈGLE
```

... alors que `core/tests/test_deployability.py` porte
`QGIS_DOCKERFILE = REPO / "deploy" / "qgis-worker" / "Dockerfile"` (chaîne à 3 segments), référencée
par un test réel (`test_core_and_qgis_worker_pin_the_same_scratch_uid`). Le détecteur actuel ne suit
qu'un seul niveau de division `REPO / "chemin"` — une chaîne plus longue lui est invisible.

Par ailleurs (REV-189, `docs/revue/2026-09-04-backlog.md`, déjà disclosé le 2026-09-14, non
corrigé) : `deployability_rules()` ne lit que `core/tests/test_deployability.py`. Deux preuves ont un
vrai test ailleurs, qui ne construit d'ailleurs aucune constante `REPO / "..."` :
`deploy/backup/test_retention.py` (`from retention import select_files_to_delete`, import nu) et
`core/tests/test_qgis_worker_server_handler.py` (`_SERVER_PATH = Path(__file__).resolve().parents[2]
/ "deploy" / "qgis-worker" / "server.py"` — un chemin construit dynamiquement, jamais une constante
`REPO`-relative).

- [ ] **Step 1: Write the failing tests**

Dans `core/tests/test_feature_health_coverage.py`, juste après le test existant
`test_deployability_rules_map_infra_paths_to_test_functions`, ajouter :

```python
def test_deployability_rules_follow_a_chain_of_divisions_not_just_one_hop():
    """`QGIS_DOCKERFILE = REPO / "deploy" / "qgis-worker" / "Dockerfile"`
    (core/tests/test_deployability.py) est une chaîne à 3 segments — un
    détecteur limité à un seul saut la manque entièrement (vérifié avant ce
    correctif : `deployability_rules()` ne renvoyait aucune règle pour ce
    chemin malgré un test réel qui l'exerce)."""
    rules = deployability_rules(REPO)
    assert "deploy/qgis-worker/Dockerfile" in rules


def test_deployability_rules_scan_test_files_beyond_test_deployability_py():
    """Généralise REV-189 (`docs/revue/2026-09-04-backlog.md`) : un test réel
    qui ne vit pas dans le seul `core/tests/test_deployability.py` (ici
    `deploy/backup/test_retention.py`) était invisible à ce mécanisme."""
    rules = deployability_rules(REPO)
    assert rules["deploy/backup/retention.py"] == (
        "référence littérale dans test_retention.py",
    )


def test_deployability_rules_fall_back_to_a_literal_path_reference():
    """`deploy/qgis-worker/server.py` n'est jamais nommé par une constante
    `REPO / "..."` (`core/tests/test_qgis_worker_server_handler.py` le
    référence via un chemin construit dynamiquement) — seule sa mention
    littérale dans le docstring du module le rend détectable."""
    rules = deployability_rules(REPO)
    assert "deploy/qgis-worker/server.py" in rules
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_coverage.py -k "chain_of_divisions or scan_test_files or fall_back_to_a_literal" -v`
Expected: 3 FAILED — les deux premiers car `"deploy/qgis-worker/Dockerfile"`/
`"deploy/backup/retention.py"` sont absents de `rules` (`KeyError`/assertion sur `in`) ; le
troisième pour la même raison (aucun repli littéral n'existe encore).

- [ ] **Step 3: Implement `_resolve_repo_relative`, `_test_files`, and the literal fallback**

Dans `core/scripts/feature_health/coverage_facts.py`, ajouter `import re` à la liste des imports en
tête de fichier (avec `ast`, `dataclasses`, `json`, `pathlib`, avant `xml.etree.ElementTree`).

Remplacer entièrement la fonction `deployability_rules` existante par :

```python
def _resolve_repo_relative(value: ast.expr) -> str | None:
    """Résout `REPO / "a" / "b" / ...` en chemin repo-relatif, en suivant une
    chaîne de divisions de profondeur arbitraire — pas seulement un saut.

    SP « priorite-moyenne-sante-90 » Volet A.1 : le détecteur d'origine ne
    reconnaissait qu'un seul `REPO / "chemin"` — `QGIS_DOCKERFILE = REPO /
    "deploy" / "qgis-worker" / "Dockerfile"` (`core/tests/test_deployability.py`)
    lui était invisible (vérifié : `deployability_rules()` renvoyait
    `AUCUNE RÈGLE` pour ce fichier malgré un test réel qui l'exerce)."""
    if isinstance(value, ast.Name) and value.id == "REPO":
        return ""
    if (
        isinstance(value, ast.BinOp)
        and isinstance(value.op, ast.Div)
        and isinstance(value.right, ast.Constant)
    ):
        base = _resolve_repo_relative(value.left)
        if base is None:
            return None
        segment = str(value.right.value)
        return f"{base}/{segment}" if base else segment
    return None


def _test_files(repo: pathlib.Path) -> list[pathlib.Path]:
    """Tout fichier `test_*.py` sous `core/tests/` ou `deploy/**`, à
    l'exception des tests du mécanisme de mesure lui-même
    (`test_feature_health*.py`) — généralise REV-189
    (`docs/revue/2026-09-04-backlog.md`, 2026-09-14) : un test réel qui ne
    vit pas dans le seul `core/tests/test_deployability.py` (par ex.
    `deploy/backup/test_retention.py`) était invisible à ce mécanisme.

    L'exclusion de `test_feature_health*.py` n'est pas cosmétique : ces
    fichiers citent en toutes lettres, dans leurs docstrings et assertions,
    des chemins d'infrastructure réels à titre d'exemple (cf. les tests du
    présent module) — sans elle, le repli par sous-chaîne littérale
    ci-dessous les confondrait avec une vraie preuve de test."""
    return sorted(
        path
        for path in repo.glob("core/tests/test_*.py")
        if not path.name.startswith("test_feature_health")
    ) + sorted(repo.glob("deploy/**/test_*.py"))


_PATH_LOOKALIKE = re.compile(r"(?:deploy|scripts|\.github)/[\w.\-/]+\.\w+")


def deployability_rules(repo: pathlib.Path) -> dict[str, tuple[str, ...]]:
    rules: dict[str, list[str]] = {}
    for path in _test_files(repo):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        constants: dict[str, str] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target, value = node.targets[0], node.value
            if not isinstance(target, ast.Name):
                continue
            candidate = _resolve_repo_relative(value)
            if candidate is not None and (repo / candidate).is_file():
                constants[target.id] = candidate
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            for constant, file_path in constants.items():
                if constant in names:
                    rules.setdefault(file_path, []).append(node.name)
        # Repli par sous-chaîne littérale (même esprit que `e2e_specs()`
        # ci-dessous) : un test qui exerce un fichier sans jamais construire
        # de constante `REPO / "..."` — import nu, chemin construit
        # dynamiquement — reste invisible au mécanisme ci-dessus. Si le
        # fichier de test le cite en toutes lettres (docstring/commentaire),
        # et que le chemin cité existe réellement, c'est une preuve valide.
        for match in sorted(set(_PATH_LOOKALIKE.findall(text))):
            if match not in rules and (repo / match).is_file():
                rules.setdefault(match, []).append(f"référence littérale dans {path.name}")
    return {key: tuple(value) for key, value in rules.items()}
```

- [ ] **Step 4: Add the missing literal reference to `deploy/backup/test_retention.py`**

`deploy/qgis-worker/server.py` est déjà cité en toutes lettres dans
`core/tests/test_qgis_worker_server_handler.py` (`_SERVER_PATH = ... / "deploy" / "qgis-worker" /
"server.py"` — capturé par le repli littéral ci-dessus sans rien changer à ce fichier). Ce n'est PAS
le cas de `deploy/backup/retention.py` : `deploy/backup/test_retention.py` n'a aucun docstring de
module. Remplacer :

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta

from retention import select_files_to_delete
```

par :

```python
# SPDX-License-Identifier: Apache-2.0
"""Exerce réellement `deploy/backup/retention.py` (rotation des sauvegardes,
fenêtre quotidienne de 7 + 4 semaines ISO distinctes hors fenêtre)."""

from datetime import datetime, timedelta

from retention import select_files_to_delete
```

- [ ] **Step 5: Run the tests, verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_coverage.py -v`
Expected (vérifié réellement en session) :
```
test_deployability_rules_map_infra_paths_to_test_functions PASSED
test_deployability_rules_follow_a_chain_of_divisions_not_just_one_hop PASSED
test_deployability_rules_scan_test_files_beyond_test_deployability_py PASSED
test_deployability_rules_fall_back_to_a_literal_path_reference PASSED
test_score_of_an_infra_proof_is_binary_on_deployability_rules PASSED
```
(les tests `test_core_rates_...`/`test_shell_rates_...`/`test_collect_refuses_...` dépendent
d'artefacts de couverture externes — cf. leur propre `skipif`/le commentaire de ce fichier, sans
rapport avec cette tâche.)

- [ ] **Step 6: Falsify — confirm the exclusion of `test_feature_health*.py` is load-bearing**

Retirer temporairement la condition d'exclusion dans `_test_files` (remplacer
`repo.glob("core/tests/test_*.py") if not path.name.startswith("test_feature_health")` par
`repo.glob("core/tests/test_*.py")` sans filtre).

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_coverage.py -k scan_test_files -v`
Expected: FAIL — `rules["deploy/backup/retention.py"]` vaut désormais
`('référence littérale dans test_feature_health_coverage.py',)` (ce fichier de test cite lui-même le
chemin dans ses propres docstrings), pas `test_retention.py` : preuve que l'exclusion empêche une
auto-contamination réelle, pas hypothétique.

Restaurer l'exclusion, relancer, `1 passed`.

- [ ] **Step 7: Commit**

```bash
git add core/scripts/feature_health/coverage_facts.py deploy/backup/test_retention.py \
  core/tests/test_feature_health_coverage.py
git commit -m "$(cat <<'EOF'
fix(core): deployability_rules suit les chaînes de divisions et scanne
tous les test_*.py

Chaîne REPO / "a" / "b" / "c" (deploy/qgis-worker/Dockerfile) invisible
au détecteur à un seul saut ; REV-189 généralisé (test_*.py hors du seul
test_deployability.py) ; repli par sous-chaîne littérale pour un test
qui n'utilise jamais REPO/"..." (import nu, chemin dynamique). Ferme la
preuve de test de la rotation de sauvegarde (docstring ajouté) et du
sidecar QGIS (déjà cité ailleurs). test_feature_health*.py exclu du
scan pour ne pas se citer lui-même comme preuve — falsifié.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `garde_auto_scopee` — nouvelle catégorie déclarée de garde auto-scopée

**Files:**
- Modify: `core/scripts/feature_health/model.py`
- Modify: `core/scripts/feature_health/rest_surface.py`
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl`
- Test: `core/tests/test_feature_health_rest_surface.py`

**Interfaces:**
- Consomme : `Feature` (dataclass existante), `score_guard(feature, routes)` (signature inchangée).
- Produit : `Feature.auto_scoped_guard: tuple[str, ...]` — champ additif avec défaut `()`, aucun des
  7 fichiers de test qui construisent `Feature(...)` sans ce champ ne casse (vérifié : `raw`/`priority`
  restent les seuls champs obligatoires en position ; `auto_scoped_guard` est le tout dernier champ
  du dataclass, avec un défaut).

**Context vérifié** (lecture directe du code, pas supposée) :
- `core/app/notifications/routes.py` — les 6 routes filtrent par `recipient_user_id=user.id` /
  `user_id=user.id` : `GET /v1/notifications`, `GET /v1/notifications/preference`,
  `GET /v1/notifications/unread-count`, `PATCH /v1/notifications/preference`,
  `POST /v1/notifications/read-all`, `POST /v1/notifications/{notification_id}/read`.
- `core/app/mapicons/routes.py` — les 4 routes filtrent par `tenant_id=user.tenant_id` :
  `POST /v1/map-icons`, `GET /v1/map-icons`, `GET /v1/map-icons/{icon_id}/file`,
  `DELETE /v1/map-icons/{icon_id}`.
- `core/app/copilot/routes.py::copilot_turn` — `if token_subject != user.oidc_sub: raise
  HTTPException(403, ...)` avant tout traitement : `POST /v1/copilot/turn`.
- `core/app/catalog/routes.py::get_metadata_catalog` — liste fixe, aucune notion de propriétaire :
  `GET /v1/metadata-catalog`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_feature_health_rest_surface.py` :

```python
def test_a_declared_auto_scoped_surface_scores_100():
    """Une route authentifiée mais sans garde nommée reconnue peut être
    déclarée « auto-scopée » (tenant/utilisateur, ou donnée de référence
    sans propriétaire) — vérifié route par route avant déclaration, jamais
    un totem générique (SP « priorite-moyenne-sante-90 » Volet A.3)."""
    routes = (
        RouteFact(
            method="GET",
            path="/v1/notifications",
            module="app.notifications.routes",
            function="get_notifications",
            guards=frozenset(),
            auth="required",
            flag=None,
        ),
    )
    feature = _feature(
        rest=("GET /v1/notifications",),
        auto_scoped_guard=("GET /v1/notifications",),
    )
    score = score_guard(feature, routes)
    assert score.value == 100.0
    assert "auto-restreint" in score.evidence["GET /v1/notifications"]


def test_an_undeclared_authenticated_only_surface_still_scores_50():
    """Non-régression : ne pas déclarer une route dans `auto_scoped_guard`
    doit laisser le score existant (50) inchangé — la déclaration n'élève
    jamais un score par défaut, seulement une route vérifiée une à une."""
    routes = (
        RouteFact(
            method="GET",
            path="/v1/notifications",
            module="app.notifications.routes",
            function="get_notifications",
            guards=frozenset(),
            auth="required",
            flag=None,
        ),
    )
    feature = _feature(rest=("GET /v1/notifications",))
    assert score_guard(feature, routes).value == 50.0


def test_the_real_inventory_declares_the_six_auto_scoped_features_correctly():
    """Contre-témoin sur le dépôt réel : les 6 fonctionnalités visées par le
    Volet A.3 atteignent bien 100 de garde une fois déclarées — pas une
    fixture, le vrai `docs/revue/inventaire-fonctionnalites.jsonl` et le vrai
    index de routes."""
    features = {f.identifier: f for f in load_inventory(REPO / "docs/revue/inventaire-fonctionnalites.jsonl")}
    routes = index_rest_routes(REPO)
    targeted = [
        "automatisation-marquer-une-ou-toutes-les-notifications-comme-lues",
        "automatisation-choisir-sa-preference-de-notification-toutes-echecs-seulement-auc",
        "automatisation-etre-notifie-dans-une-cloche-persistante-du-shell-des-jobs-en-ech",
        "cartographie-uploader-une-icone-svg-personnalisee-dans-une-bibliotheque-d-icones",
        "administration-copilote-ia-dans-le-builder-d-app-orchestrant-des-outils-mcp-reel",
        "catalogue-metadonnees-catalogue-curate-de-licences-frequences-langues",
    ]
    for identifier in targeted:
        feature = features[identifier]
        assert feature.auto_scoped_guard, identifier
        assert score_guard(feature, routes).value == 100.0, identifier
```

Il faut aussi importer `load_inventory`, `RouteFact` et `index_rest_routes` en tête du fichier s'ils
n'y sont pas déjà (vérifier — `index_rest_routes`/`RouteFact` le sont déjà d'après les imports
existants ; ajouter `load_inventory` depuis `scripts.feature_health.model`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -k "auto_scoped" -v`
Expected: 3 FAILED — `TypeError: Feature.__init__() got an unexpected keyword argument
'auto_scoped_guard'` sur les deux premiers, le troisième échoue de la même façon dès la
construction via `_feature`/`load_inventory` (le champ n'existe pas encore).

- [ ] **Step 3: Add `Feature.auto_scoped_guard`**

Dans `core/scripts/feature_health/model.py`, remplacer :

```python
@dataclasses.dataclass(frozen=True)
class Feature:
    """Une ligne de `docs/revue/inventaire-fonctionnalites.jsonl`.

    `proofs` ne porte que des **chemins de fichier**, jamais `chemin:ligne` :
    les numéros de ligne dérivent en quelques jours (spec §8, mesuré)."""

    identifier: str
    domain: str
    name: str
    proofs: tuple[str, ...]
    rest: tuple[str, ...]
    mcp: tuple[str, ...]
    shell: tuple[str, ...]
    public: tuple[str, ...]
    priority: str
    priority_source: str
    raw: dict
```

par :

```python
@dataclasses.dataclass(frozen=True)
class Feature:
    """Une ligne de `docs/revue/inventaire-fonctionnalites.jsonl`.

    `proofs` ne porte que des **chemins de fichier**, jamais `chemin:ligne` :
    les numéros de ligne dérivent en quelques jours (spec §8, mesuré).

    `auto_scoped_guard` (additif, défaut vide) déclare des surfaces REST déjà
    correctement autorisées par un mécanisme que `score_guard` ne modélise
    pas nativement — portée tenant/utilisateur via une requête filtrée, ou
    donnée de référence partagée sans notion de propriétaire. Chaque entrée
    est vérifiée route par route avant déclaration (SP
    « priorite-moyenne-sante-90 » Volet A.3), jamais un totem générique."""

    identifier: str
    domain: str
    name: str
    proofs: tuple[str, ...]
    rest: tuple[str, ...]
    mcp: tuple[str, ...]
    shell: tuple[str, ...]
    public: tuple[str, ...]
    priority: str
    priority_source: str
    raw: dict
    auto_scoped_guard: tuple[str, ...] = ()
```

Et dans `load_inventory`, remplacer :

```python
                public=tuple(row.get("publiques", ())),
                priority=row["priorite"],
                priority_source=row.get("priorite_source", "declaree"),
                raw=row,
            )
        )
```

par :

```python
                public=tuple(row.get("publiques", ())),
                priority=row["priorite"],
                priority_source=row.get("priorite_source", "declaree"),
                raw=row,
                auto_scoped_guard=tuple(row.get("garde_auto_scopee", ())),
            )
        )
```

- [ ] **Step 4: Add the `score_guard` branch**

Dans `core/scripts/feature_health/rest_surface.py`, remplacer :

```python
    for surface in feature.rest:
        if surface in feature.public:
            scores.append(100.0)
            evidence[surface] = "publique par conception (déclarée)"
            continue
        fact = by_id.get(surface)
```

par :

```python
    for surface in feature.rest:
        if surface in feature.public:
            scores.append(100.0)
            evidence[surface] = "publique par conception (déclarée)"
            continue
        if surface in feature.auto_scoped_guard:
            scores.append(100.0)
            evidence[surface] = (
                "auto-restreint par tenant_id/user_id, ou donnée de référence "
                "partagée sans notion de propriétaire — déclaré, vérifié en "
                "lecture de code (SP « priorite-moyenne-sante-90 » Volet A.3)"
            )
            continue
        fact = by_id.get(surface)
```

- [ ] **Step 5: Declare the 6 real surfaces in the inventory**

Dans `docs/revue/inventaire-fonctionnalites.jsonl`, pour chacune des 6 lignes suivantes, ajouter la
clé `"garde_auto_scopee"` (même niveau que `"publiques"`) :

- `automatisation-marquer-une-ou-toutes-les-notifications-comme-lues`,
  `automatisation-choisir-sa-preference-de-notification-toutes-echecs-seulement-auc`,
  `automatisation-etre-notifie-dans-une-cloche-persistante-du-shell-des-jobs-en-ech` :
  ```json
  "garde_auto_scopee": ["GET /v1/notifications", "GET /v1/notifications/preference", "GET /v1/notifications/unread-count", "PATCH /v1/notifications/preference", "POST /v1/notifications/read-all", "POST /v1/notifications/{notification_id}/read"]
  ```
- `cartographie-uploader-une-icone-svg-personnalisee-dans-une-bibliotheque-d-icones` :
  ```json
  "garde_auto_scopee": ["POST /v1/map-icons", "GET /v1/map-icons", "GET /v1/map-icons/{icon_id}/file", "DELETE /v1/map-icons/{icon_id}"]
  ```
- `administration-copilote-ia-dans-le-builder-d-app-orchestrant-des-outils-mcp-reel` :
  ```json
  "garde_auto_scopee": ["POST /v1/copilot/turn"]
  ```
- `catalogue-metadonnees-catalogue-curate-de-licences-frequences-langues` :
  ```json
  "garde_auto_scopee": ["GET /v1/metadata-catalog"]
  ```

- [ ] **Step 6: Run the tests, verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -v`
Expected: tous les tests du fichier passent (les 3 nouveaux compris), aucune régression sur les
tests existants (`test_index_finds_every_declared_route`, etc.).

- [ ] **Step 7: Falsify the non-regression test**

Retirer temporairement le `if surface in feature.auto_scoped_guard:` (le commenter), relancer :

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -k "declared_auto_scoped" -v`
Expected: FAIL (le score retombe à 50.0). Restaurer le bloc, relancer, `1 passed`.

- [ ] **Step 8: Commit**

```bash
git add core/scripts/feature_health/model.py core/scripts/feature_health/rest_surface.py \
  docs/revue/inventaire-fonctionnalites.jsonl core/tests/test_feature_health_rest_surface.py
git commit -m "$(cat <<'EOF'
feat(core): garde auto-scopée déclarée pour 6 routes déjà auto-restreintes

notifications (x6 routes), icônes carte (x4), copilote IA, catalogue de
métadonnées : authentifiées mais sans garde nommée reconnue par
score_guard — vérifié route par route qu'elles sont déjà correctement
scopées (tenant_id/user_id en filtre de requête, comparaison d'identité
inline pour le copilote, donnée de référence partagée sans propriétaire
pour le catalogue). Champ additif Feature.auto_scoped_guard (défaut
vide), aucun appelant existant à modifier.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 5 tests structurels d'infrastructure (CodeQL, gitleaks, Proxmox, conteneur `deploy/backup` non-root, alerte SLO webhook)

**Files:**
- Modify: `core/tests/test_deployability.py`

**Interfaces:**
- Consomme : `REPO` (constante module existante), `yaml`/`re`/`pathlib` (déjà importés en tête de fichier).
- Produit : rien de consommable par d'autres tâches — 5 tests indépendants, purement additifs.
  (NOTE de séquencement : cette tâche doit être fusionnée APRÈS ou AVEC Task 1, qui généralise la
  résolution de constantes `REPO / "a" / "b" / "c"` à une chaîne arbitraire — `BACKUP_DOCKERFILE`
  ci-dessous est une chaîne à 3 segments, invisible à `deployability_rules()` sans ce correctif.)

**Context vérifié** : aucun des 5 fichiers ci-dessous n'a de test nulle part dans le dépôt (confirmé par grep avant d'écrire ce plan). Piège vérifié en écrivant ces tests : `yaml.safe_load()` résout une clé nue `on:` en YAML 1.1 comme le booléen `True`, jamais la chaîne `"on"` (`doc.keys() == ['name', True, 'jobs']`, vérifié empiriquement sur `codeql.yml`) — les deux tests de workflow lisent `doc[True]`.

- [ ] **Step 1: Write the 5 tests**

À la fin de `core/tests/test_deployability.py`, ajouter :

```python
CODEQL_WORKFLOW = REPO / ".github/workflows/codeql.yml"
GITLEAKS_WORKFLOW = REPO / ".github/workflows/gitleaks.yml"
PROXMOX_PLAYBOOK = REPO / "deploy" / "proxmox" / "ansible" / "playbook.yml"
SLO_RULES = REPO / "deploy" / "observability" / "grafana" / "provisioning" / "alerting" / "rules.yaml"
BACKUP_DOCKERFILE = REPO / "deploy" / "backup" / "Dockerfile"


def test_codeql_workflow_runs_on_push_and_pr_with_security_events_write():
    doc = yaml.safe_load(CODEQL_WORKFLOW.read_text())
    # Piège YAML 1.1 : une clé nue `on:` est résolue par PyYAML comme le
    # booléen True, jamais la chaîne "on" — vérifié empiriquement
    # (`yaml.safe_load` sur ce fichier donne `doc.keys() ==
    # ['name', True, 'jobs']`).
    on = doc[True]
    assert set(on["push"]["branches"]) >= {"main", "dev"}
    assert "pull_request" in on
    job = doc["jobs"]["analyze"]
    assert job["permissions"]["security-events"] == "write"
    assert set(job["strategy"]["matrix"]["language"]) == {"python", "javascript-typescript"}
    uses = [step.get("uses", "") for step in job["steps"]]
    assert any(u.startswith("github/codeql-action/init@") for u in uses)
    assert any(u.startswith("github/codeql-action/analyze@") for u in uses)


def test_gitleaks_workflow_scans_worktree_only_never_git_history():
    doc = yaml.safe_load(GITLEAKS_WORKFLOW.read_text())
    on = doc[True]
    assert set(on.keys()) == {"push", "pull_request"}, (
        "gitleaks.yml ne doit déclencher que sur push/pull_request — un "
        "schedule/workflow_dispatch inviterait à basculer `dir .` vers un "
        "scan d'historique qui retrouverait la clé age de test toujours "
        "présente dans l'historique public (cf. commentaire du fichier)."
    )
    scan_step = next(s for s in doc["jobs"]["scan"]["steps"] if "run" in s)
    run = scan_step["run"]
    assert "dir ." in run
    assert "git ." not in run
    assert scan_step.get("continue-on-error") is not True


def test_proxmox_playbook_provisions_and_deploys_geostudio():
    doc = yaml.safe_load(PROXMOX_PLAYBOOK.read_text())
    play = doc[0]
    assert play["hosts"] == "geostudio"
    task_names = [t["name"] for t in play["tasks"]]
    install_tasks = [
        t
        for t in play["tasks"]
        if t.get("ansible.builtin.command", {}).get("cmd") == "./scripts/install.sh"
    ]
    assert len(install_tasks) == 2, (
        f"le playbook doit lancer scripts/install.sh en deux passes (avant/"
        f"après le reset de connexion post-installation Docker) : {task_names}"
    )
    assert any(
        t.get("ansible.builtin.git", {}).get("repo") == "{{ geostudio_repo_url }}"
        for t in play["tasks"]
    )


def test_backup_dockerfile_creates_and_chowns_backup_dir_before_switching_user():
    text = BACKUP_DOCKERFILE.read_text()
    mkdir_pos = text.find("mkdir -p /backup/archives /backup/work")
    user_pos = text.find("\nUSER backup")
    assert mkdir_pos != -1, "deploy/backup/Dockerfile doit créer /backup/{archives,work}"
    assert user_pos != -1, "deploy/backup/Dockerfile doit passer USER backup"
    assert mkdir_pos < user_pos, "/backup doit être créé/chown avant le passage non-root"
    chown_line = re.search(r"^RUN .*chown[^\n]*$", text, re.MULTILINE)
    assert chown_line is not None and "/backup" in chown_line.group(0)


def test_slo_rules_cover_the_four_documented_slos_and_are_active():
    doc = yaml.safe_load(SLO_RULES.read_text())
    slo_group = next(g for g in doc["groups"] if g["name"] == "SLO")
    rules_by_uid = {r["uid"]: r for r in slo_group["rules"]}
    expected = {
        "slo-api-features-latency-p95": 200,
        "slo-martin-tiles-latency-p95": 0.05,
        "slo-jobs-backlog": 50,
        "slo-api-5xx-rate": 0.01,
    }
    assert set(expected) <= set(rules_by_uid), sorted(set(expected) - set(rules_by_uid))
    for uid, threshold in expected.items():
        rule = rules_by_uid[uid]
        assert rule["isPaused"] is False, f"{uid} ne doit pas être en pause"
        assert "slo" in rule["labels"], f"{uid} doit porter un label slo (routage policies.yaml)"
        threshold_expr = next(d for d in rule["data"] if d["refId"] == "B")
        params = threshold_expr["model"]["conditions"][0]["evaluator"]["params"]
        assert params == [threshold], f"{uid}: seuil attendu {threshold}, trouvé {params}"
```

- [ ] **Step 2: Run all 5 to verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_deployability.py -k "codeql_workflow or gitleaks_workflow or proxmox_playbook or backup_dockerfile_creates or slo_rules_cover" -v`
Expected: `5 passed` (vérifié réellement en session).

- [ ] **Step 3: Falsify the CodeQL test**

```bash
sed -i 's/security-events: write/security-events: read/' ../.github/workflows/codeql.yml
```

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_deployability.py -k codeql_workflow -v`
Expected: FAIL — `AssertionError: assert 'read' == 'write'`.

Restaurer : `git checkout -- ../.github/workflows/codeql.yml`, relancer, `1 passed`.

- [ ] **Step 4: Falsify the gitleaks test**

```bash
sed -i "s/dir \. --redact --exit-code 1/git . --redact --exit-code 1/" ../.github/workflows/gitleaks.yml
```

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_deployability.py -k gitleaks_workflow -v`
Expected: FAIL — `assert 'dir .' in 'docker run ... git . --redact --exit-code 1\n'`.

Restaurer : `git checkout -- ../.github/workflows/gitleaks.yml`, relancer, `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_deployability.py
git commit -m "$(cat <<'EOF'
test(core): couvre CodeQL/gitleaks/Proxmox/backup non-root/alerte SLO

5 fichiers d'infrastructure sans aucun test (vérifié par grep) — la
santé mesurée de ces 5 fonctionnalités priorité moyenne était plafonnée
à 40 faute de toute preuve. Tests structurels (câblage réel, jamais
d'exécution de l'outil externe), même registre que les tests
docker-compose déjà présents dans ce fichier. Falsifiés (CodeQL
security-events, gitleaks dir/git) avant ce commit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Couverture de `useAuth.ts` — 5 tests ciblés (mode OIDC réel + mode mock)

**Files:**
- Create: `shell/src/auth/useAuth.test.ts`

**Interfaces:**
- Consomme : `useAuth`, `enableMockAuth`, `isMockMode` (`shell/src/auth/useAuth.ts`, inchangé — aucune ligne de production n'est modifiée par cette tâche), `useAuth` de `react-oidc-context` (mocké).
- Produit : aucune interface nouvelle — tâche de couverture pure.

**Contexte vérifié** : `shell/src/auth/useAuth.ts` n'avait **aucun fichier de test dédié** (`find shell/src -iname "*useAuth*"` ne retourne que le fichier de production). Le score 45.5 % mesuré par le bilan vient d'un exercice incident par d'autres suites de tests (composants qui appellent `enableMockAuth()` en amont), jamais d'une vérification directe du fichier — en particulier, la branche OIDC réelle (lignes 34-44 : `useOidcAuth()`, `signIn`/`signOut` réels, calcul de `username`/`error`/`getAccessToken`) n'est exercée nulle part. Patron de mock repris tel quel de `shell/src/builder/copilot/useMcpTokenOidc.test.tsx` (`vi.mock("react-oidc-context", () => ({ useAuth: () => oidc }))`).

- [ ] **Step 1: Write the 5 tests**

```ts
// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const oidc: {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: { profile: { preferred_username?: string }; access_token: string } | undefined;
  error: Error | undefined;
  signinRedirect: ReturnType<typeof vi.fn>;
  signoutRedirect: ReturnType<typeof vi.fn>;
} = {
  isLoading: false,
  isAuthenticated: false,
  user: undefined,
  error: undefined,
  signinRedirect: vi.fn(),
  signoutRedirect: vi.fn(),
};
vi.mock("react-oidc-context", () => ({ useAuth: () => oidc }));

beforeEach(() => {
  oidc.isLoading = false;
  oidc.isAuthenticated = false;
  oidc.user = undefined;
  oidc.error = undefined;
  oidc.signinRedirect.mockReset();
  oidc.signoutRedirect.mockReset();
});

describe("useAuth (real OIDC mode)", () => {
  it("reflects the oidc-client loading/authenticated/username/error state", async () => {
    oidc.isLoading = true;
    oidc.isAuthenticated = true;
    oidc.user = { profile: { preferred_username: "alice" }, access_token: "tok-1" };
    oidc.error = new Error("boom");
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe("alice");
    expect(result.current.error).toBe("boom");
    expect(result.current.getAccessToken()).toBe("tok-1");
  });

  it("reports no username, no error and no access token when signed out", async () => {
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    expect(result.current.username).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.getAccessToken()).toBeUndefined();
  });

  it("signIn triggers oidc signinRedirect", async () => {
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    result.current.signIn();
    expect(oidc.signinRedirect).toHaveBeenCalledTimes(1);
  });

  it("signOut triggers oidc signoutRedirect", async () => {
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    result.current.signOut();
    expect(oidc.signoutRedirect).toHaveBeenCalledTimes(1);
  });
});

describe("useAuth (mock mode)", () => {
  it("enableMockAuth switches every consumer to the fixed mock state", async () => {
    const { useAuth, enableMockAuth, isMockMode } = await import("./useAuth");
    enableMockAuth();
    expect(isMockMode()).toBe(true);
    const { result } = renderHook(() => useAuth());
    expect(result.current).toMatchObject({
      isLoading: false,
      isAuthenticated: true,
      username: "mockuser",
      error: null,
    });
    expect(result.current.getAccessToken()).toBe("mock-token");
    // signIn/signOut are no-ops in mock mode — must not touch the real oidc client.
    result.current.signIn();
    result.current.signOut();
    expect(oidc.signinRedirect).not.toHaveBeenCalled();
    expect(oidc.signoutRedirect).not.toHaveBeenCalled();
  });
});
```

Note d'implémentation : le test de mode mock doit rester **après** le bloc « real OIDC mode » dans le fichier — `enableMockAuth()` positionne un flag module-scope irréversible (`mockMode = true`, aucun `disableMockAuth`), et Vitest exécute les tests d'un même fichier dans l'ordre de déclaration.

- [ ] **Step 2: Run the tests and verify coverage**

Run: `cd shell && npx vitest run src/auth/useAuth.test.ts --coverage --coverage.include='src/auth/useAuth.ts'`
Expected (vérifié en session) : `Test Files 1 passed (1)`, `Tests 5 passed (5)`, couverture `Statements 100% (12/12)`, `Branches 100% (6/6)`, `Functions 100% (9/9)`, `Lines 100% (11/11)`.

- [ ] **Step 3: Falsify one test to prove it exercises real behaviour**

Dans `shell/src/auth/useAuth.ts`, remplacer temporairement `signOut: () => void oidc.signoutRedirect(),` par `signOut: () => {},`.

Run: `cd shell && npx vitest run src/auth/useAuth.test.ts -t "signOut triggers"`
Expected : FAIL — `AssertionError: expected "vi.fn()" to be called 1 times, but got 0 times`.

Restaurer (`git checkout -- shell/src/auth/useAuth.ts`), relancer :

Run: `cd shell && npx vitest run src/auth/useAuth.test.ts -t "signOut triggers"`
Expected : PASS.

- [ ] **Step 4: Commit**

```bash
git add shell/src/auth/useAuth.test.ts
git commit -m "$(cat <<'EOF'
test(shell): couvre useAuth en mode OIDC réel et en mode mock

Aucun fichier de test dédié n'existait — le 45.5 % mesuré par le bilan
venait d'un exercice incident par d'autres suites, jamais de la branche
OIDC réelle (signIn/signOut/username/error/getAccessToken). 5 tests
ciblés, 100 % de lignes sur ce fichier seul. Falsifié (signOut rendu
no-op temporairement, confirmation d'échec, restauration). Aucune ligne
de production touchée.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Couverture des widgets de contenu (hero/datasetCard/gallery/richSection)

**Files:**
- Modify: `shell/src/builder/widgets/hero.test.tsx`
- Modify: `shell/src/builder/widgets/datasetCard.test.tsx`
- Modify: `shell/src/builder/widgets/gallery.test.tsx`
- Modify: `shell/src/builder/widgets/richSection.test.tsx`

**Interfaces:**
- Consomme : `hero.tsx`/`datasetCard.tsx`/`gallery.tsx`/`richSection.tsx` (inchangés — aucune ligne
  de production modifiée par cette tâche), leurs clés i18n existantes (`widgetHero.*`,
  `widgetDatasetCard.*`, `widgetGallery.*`, `widgetRichSection.*`, `dataSourceSelect.label` —
  toutes vérifiées dans `shell/src/i18n/catalog.fr.ts`, inchangées).
- Produit : rien de nouveau pour les tâches suivantes — tests purs.

**Contexte vérifié** (mesuré, pas deviné — `npx vitest run <fichier> --coverage
--coverage.include='src/builder/widgets/<fichier>.tsx' --coverage.reportsDirectory=<répertoire
dédié, pour éviter une collision si une autre tâche mesure une couverture en parallèle>`) :
dans les 4 fichiers, le seul angle mort réel est le `PropsPanel` (jamais rendu par les tests
existants, qui ne couvrent que `Component`) :
- `hero.tsx` : 59.09 % de lignes → **100 %** après les 4 tests ci-dessous (branche restante à
  87.5 % : garde-fous `??` non exercés séparément, jugé suffisant).
- `datasetCard.tsx` : 73.68 % → **100 %**.
- `gallery.tsx` : 75 % → **100 %**.
- `richSection.tsx` : 75 % → **100 %**.

- [ ] **Step 1: Ajouter les tests `hero.tsx`**

Dans `shell/src/builder/widgets/hero.test.tsx`, ajouter l'import `import { isSafeHref } from
"./hero";` à côté des imports existants, puis, avant le test `"hero cta click with a relative
ctaHref still opens it"`, ajouter :

```tsx
test("isSafeHref rejects an unparseable href", () => {
  expect(isSafeHref("http://[::1")).toBe(false);
});

test("hero PropsPanel edits title, subtitle, background image, cta label and href", async () => {
  const onChange = vi.fn();
  const PropsPanel = getWidget("hero")!.PropsPanel!;
  render(
    <PropsPanel
      props={{ title: "Bienvenue" }}
      onChange={onChange}
      ctx={{ mode: "edit" } as WidgetContext}
    />,
  );
  await userEvent.type(screen.getByLabelText("Titre du bandeau"), "!");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ title: "Bienvenue!" });

  await userEvent.type(screen.getByLabelText("Sous-titre"), "s");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ subtitle: "s" });

  await userEvent.type(screen.getByLabelText("URL de l'image de fond"), "u");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ backgroundImageUrl: "u" });

  await userEvent.type(screen.getByLabelText("Libellé du CTA"), "c");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ ctaLabel: "c" });

  await userEvent.type(screen.getByLabelText("Lien du CTA"), "h");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ ctaHref: "h" });
});

test("hero PropsPanel switches alignment to center", async () => {
  const onChange = vi.fn();
  const PropsPanel = getWidget("hero")!.PropsPanel!;
  render(
    <PropsPanel
      props={{ title: "Bienvenue", align: "left" }}
      onChange={onChange}
      ctx={{ mode: "edit" } as WidgetContext}
    />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Alignement"), "center");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ align: "center" });
});

test("hero with align center centers its content", () => {
  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", align: "center" }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  expect(screen.getByText("Bienvenue").parentElement).toHaveClass("items-center", "text-center");
});
```

- [ ] **Step 2: Verify `hero.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/hero.test.tsx --coverage --coverage.include='src/builder/widgets/hero.tsx' --coverage.reportsDirectory=/tmp/cov-c8`
Expected: 12 tests passed, `Lines : 100%` (22/22).

- [ ] **Step 3: Falsify one test to prove it exercises real behaviour**

Dans `shell/src/builder/widgets/hero.tsx`, changer temporairement
`onChange={(e) => set({ align: e.target.value })}` (ligne ~104, `select` d'alignement) en
`onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/hero.test.tsx -t "switches alignment"`
Expected: FAIL (`TypeError: Cannot read properties of undefined`, `onChange.mock.calls.at(-1)`
est `undefined`).

Restaurer : `git checkout -- shell/src/builder/widgets/hero.tsx`, relancer la même commande.
Expected: PASS.

- [ ] **Step 4: Ajouter les tests `datasetCard.tsx`**

Dans `shell/src/builder/widgets/datasetCard.test.tsx`, ajouter `userEvent` (import
`@testing-library/user-event`) et `DataSource` au type-import existant
(`import type { CollectionAdmin, DataSource, ItemClient } from "../../api/types";`), puis, avant
le test `"shows a discreet message when no data source is bound"`, ajouter :

```tsx
function renderPanel(props: Record<string, unknown>, dataSources: DataSource[] = []) {
  const onChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = getWidget("datasetCard")!.PropsPanel!;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={props} dataSources={dataSources} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return onChange;
}

test("PropsPanel binds a features data source", async () => {
  const source: DataSource = { id: "ds1", type: "features", service: "core", layer: "parcs" };
  const onChange = renderPanel({}, [source]);
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds1");
  expect(onChange).toHaveBeenCalledWith({ dataSourceId: "ds1" });
});

test("PropsPanel edits the optional title override", async () => {
  const onChange = renderPanel({});
  await userEvent.type(screen.getByLabelText("Titre (optionnel)"), "x");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ title: "x" });
});

test("PropsPanel toggles the download buttons checkbox", async () => {
  const onChange = renderPanel({ showDownload: true });
  await userEvent.click(screen.getByLabelText("Afficher le téléchargement"));
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ showDownload: false });
});
```

- [ ] **Step 5: Verify `datasetCard.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/datasetCard.test.tsx --coverage --coverage.include='src/builder/widgets/datasetCard.tsx' --coverage.reportsDirectory=/tmp/cov-c8`
Expected: 9 tests passed, `Lines : 100%` (19/19).

- [ ] **Step 6: Falsify one test**

Dans `datasetCard.tsx`, changer `onChange={(e) => onChange({ ...props, showDownload:
e.target.checked })}` (case à cocher, ligne ~51) en `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/datasetCard.test.tsx -t "toggles the download"`
Expected: FAIL. Restaurer (`git checkout -- shell/src/builder/widgets/datasetCard.tsx`), relancer :
PASS.

- [ ] **Step 7: Ajouter les tests `gallery.tsx`**

Dans `shell/src/builder/widgets/gallery.test.tsx`, ajouter `fireEvent` à l'import
`@testing-library/react` existant et `userEvent` (`@testing-library/user-event`), puis, avant le
test `"gallery calls listPublicItems with the author's fixed filter props"`, ajouter :

```tsx
test("PropsPanel edits the type, tag, limit and columns", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("gallery")!.PropsPanel!;
  render(<Panel props={{}} onChange={onChange} />);

  await userEvent.selectOptions(screen.getByLabelText("Type d'élément"), "app");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ type: "app" });

  await userEvent.type(screen.getByLabelText("Tag"), "x");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ tag: "x" });

  fireEvent.change(screen.getByLabelText("Limite"), { target: { value: "24" } });
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ limit: 24 });

  fireEvent.change(screen.getByLabelText("Colonnes"), { target: { value: "4" } });
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ columns: 4 });
});
```

- [ ] **Step 8: Verify `gallery.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/gallery.test.tsx --coverage --coverage.include='src/builder/widgets/gallery.tsx' --coverage.reportsDirectory=/tmp/cov-c8`
Expected: 5 tests passed, `Lines : 100%` (28/28).

- [ ] **Step 9: Falsify one test**

Dans `gallery.tsx`, changer `onChange={(e) => set({ tag: e.target.value })}` (input Tag, ligne
~56) en `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/gallery.test.tsx -t "PropsPanel edits"`
Expected: FAIL. Restaurer (`git checkout -- shell/src/builder/widgets/gallery.tsx`), relancer :
PASS.

- [ ] **Step 10: Ajouter le test `richSection.tsx`**

Dans `shell/src/builder/widgets/richSection.test.tsx`, ajouter `userEvent` et `vi` aux imports
existants, puis, avant le test `"richSection renders sanitized Markdown"`, ajouter :

```tsx
test("PropsPanel edits the markdown source", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("richSection")!.PropsPanel!;
  render(<Panel props={{}} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Markdown"), "#");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ markdown: "#" });
});
```

- [ ] **Step 11: Verify `richSection.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/richSection.test.tsx --coverage --coverage.include='src/builder/widgets/richSection.tsx' --coverage.reportsDirectory=/tmp/cov-c8`
Expected: 5 tests passed, `Lines : 100%` (8/8).

- [ ] **Step 12: Falsify one test**

Dans `richSection.tsx`, changer `onChange={(e) => onChange({ ...props, markdown: e.target.value
})}` en `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/richSection.test.tsx -t "PropsPanel edits"`
Expected: FAIL. Restaurer (`git checkout -- shell/src/builder/widgets/richSection.tsx`), relancer :
PASS.

- [ ] **Step 13: Full-suite sanity + commit**

Run: `cd shell && npx vitest run src/builder/widgets/hero.test.tsx src/builder/widgets/datasetCard.test.tsx src/builder/widgets/gallery.test.tsx src/builder/widgets/richSection.test.tsx`
Expected: 4 files, 0 failed.

```bash
git add shell/src/builder/widgets/hero.test.tsx shell/src/builder/widgets/datasetCard.test.tsx \
  shell/src/builder/widgets/gallery.test.tsx shell/src/builder/widgets/richSection.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre les PropsPanel des widgets Hero/Fiche jeu de données/Galerie/Section riche

4 fichiers dont le seul angle mort réel était le panneau d'édition (jamais
rendu par les tests existants, qui ne couvrent que le rendu runtime) :
hero.tsx 59%→100%, datasetCard.tsx 74%→100%, gallery.tsx 75%→100%,
richSection.tsx 75%→100% (lignes). Aucune ligne de production touchée ;
un test par fichier falsifié (handler d'édition temporairement neutralisé,
confirmation d'échec, restauration).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Couverture des widgets d'interaction avancée (chart/tabs/navigation)

**Files:**
- Modify: `shell/src/builder/widgets/chart.test.tsx`
- Modify: `shell/src/builder/widgets/tabs.test.tsx`
- Modify: `shell/src/builder/widgets/navigation.test.tsx`

**Interfaces:**
- Consomme : `chart.tsx`/`tabs.tsx`/`navigation.tsx` (inchangés), clés i18n existantes
  (`widgetChart.*`, `widgetTabs.*`, `widgetNavigation.*`, toutes vérifiées dans
  `shell/src/i18n/catalog.fr.ts`).
- Produit : rien pour les tâches suivantes — tests purs.

**Contexte vérifié** :
- `chart.tsx` : 75.29 % de lignes (mesure isolée) → **95.29 %** après les tests ci-dessous — le
  gros de l'écart était le `PropsPanel` (dataSourceId/categoryField/valueField/target sankey/
  niveaux de hiérarchie/comparePeriod/axes/titre/stack/legend/zoom/option avancée, jamais testés
  individuellement) plus les états chargement/erreur du mode comparaison. **Trouvaille
  informationnelle, sans rapport avec cette tâche** : le rendu de succès du mode comparaison
  (lignes 430-437) est bien exercé quand le fichier de test est lancé seul, mais ressort comme
  non couvert quand tout `chart.test.tsx` tourne ensemble (23 tests) — un artefact de fusion de
  couverture v8/vitest déjà présent **avant** cette tâche (vérifié : le même écart existe sur la
  mesure de référence, avant tout ajout). Le nombre qui comptera réellement pour le bilan de
  fonctionnalités est celui de `shell/coverage/coverage-summary.json`, produit par la suite
  complète (`npm run test -- --coverage`) — à relire après cette tâche plutôt que supposé égal à
  la mesure isolée ci-dessus.
- `tabs.tsx` : 78.04 % → **100 %** de lignes (renommage d'onglet, suppression réelle avec ≥2
  onglets, réordonnancement vers le haut, et le cas 0 onglet du `Component` n'étaient testés par
  aucun des 8 tests existants).
- `navigation.tsx` : 80 % → **100 %** (le `PropsPanel`, sélecteur d'orientation, n'était pas
  testé).

- [ ] **Step 1: Ajouter les tests `chart.tsx` — PropsPanel**

Dans `shell/src/builder/widgets/chart.test.tsx`, ajouter `DataSource` au type-import existant
(`import type { DataSource, DataSourceState, ItemClient } from "../../api/types";`), puis, avant
le test `"PropsPanel shows the compare-periods toggle only for line/area chart types"`, ajouter :

```tsx
test("PropsPanel edits the data source, category and value fields for a bar chart", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const source: DataSource = { id: "ds1", type: "features", service: "core", layer: "parcs" };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[source]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds1");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ dataSourceId: "ds1" }));

  await userEvent.type(screen.getByLabelText("Champ catégorie"), "r");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ categoryField: "r" }));

  await userEvent.type(screen.getByLabelText("Champ valeur"), "v");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ valueField: "v" }));
});

test("PropsPanel edits the sankey target field", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "sankey" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByLabelText("Champ cible"), "d");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { target: "d" } }));
});

test("PropsPanel edits and removes an existing hierarchy level", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel
          props={{ chartType: "treemap", encodings: { levels: ["region"] } }}
          dataSources={[]}
          onChange={onChange}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByLabelText("Niveau 1"), "x");
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ encodings: { levels: ["regionx"] } }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le niveau 1" }));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { levels: [] } }));
});

test("PropsPanel edits comparePeriod, axis, title, stack/legend/zoom toggles and the advanced option", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "line" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.selectOptions(screen.getByLabelText("Période de référence"), "sameLastYear");
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ comparePeriod: "sameLastYear" }),
  );

  await userEvent.selectOptions(screen.getByLabelText("Type d'axe X"), "time");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ xAxisType: "time" }));

  await userEvent.selectOptions(screen.getByLabelText("Type d'axe Y"), "log");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ yAxisType: "log" }));

  await userEvent.type(screen.getByLabelText("Unité de l'axe Y"), "€");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ yAxisUnit: "€" }));

  await userEvent.type(screen.getByLabelText("Titre du graphique"), "T");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ title: "T" }));

  await userEvent.click(screen.getByLabelText("Empiler les séries"));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ stack: true }));

  await userEvent.click(screen.getByLabelText("Afficher la légende"));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ legend: false }));

  await userEvent.click(screen.getByLabelText("Activer le zoom"));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ zoom: true }));

  await userEvent.type(screen.getByLabelText("Option ECharts avancée (JSON)"), "x");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ advancedOption: "x" }));
});
```

- [ ] **Step 2: Ajouter les tests `chart.tsx` — états du mode comparaison**

Après le test `"compareEnabled builds a 2-series compare option once timeRange + timeField are
both active"`, ajouter d'abord une ligne à l'intérieur de ce test existant, juste avant son
accolade fermante (après `await waitFor(() => expect(el).toHaveAttribute("data-series", "2"));`) :

```tsx
  // Distingue la branche de comparaison du graphique par-colonne ordinaire :
  // ce dernier n'appelle jamais queryDataSource (les données viennent de
  // ctx.data), seule la branche de comparaison le fait (fenêtre courante +
  // fenêtre de référence).
  expect(queryDataSource).toHaveBeenCalledTimes(2);
```

Puis, juste après ce test (avant `"two chart widgets in compare mode..."`), ajouter :

```tsx
test("compare mode shows a loading state while the current/reference windows are in flight", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({
    source: "collection",
    collectionId: "events",
    columns: {},
    timeField: "date",
    reactsToExtent: false,
  });
  const queryDataSource = vi.fn().mockReturnValue(new Promise(() => {}));
  renderChart(
    { chartType: "line", compareEnabled: true },
    { data: { ...wide, datasetId: "ds-1" } },
    { getDatasetConfig, queryDataSource },
    { from: "2026-01-01", to: "2026-01-02" },
  );
  expect(await screen.findByText(/chargement/i)).toBeInTheDocument();
  expect(screen.queryByTestId("echart")).not.toBeInTheDocument();
});

test("compare mode shows an error state when the reference window fails to load", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({
    source: "collection",
    collectionId: "events",
    columns: {},
    timeField: "date",
    reactsToExtent: false,
  });
  const queryDataSource = vi
    .fn()
    .mockImplementation((source: { query: Record<string, unknown> }) =>
      source.query.date__gte === "2026-01-01"
        ? Promise.resolve([])
        : Promise.reject(new Error("fail")),
    );
  renderChart(
    { chartType: "line", compareEnabled: true },
    { data: { ...wide, datasetId: "ds-1" } },
    { getDatasetConfig, queryDataSource },
    { from: "2026-01-01", to: "2026-01-02" },
  );
  expect(await screen.findByText(/erreur/i)).toBeInTheDocument();
});
```

- [ ] **Step 3: Verify `chart.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx --coverage --coverage.include='src/builder/widgets/chart.tsx' --coverage.reportsDirectory=/tmp/cov-c9`
Expected: 23 tests passed, `Lines : 95.29%` (81/85, uncovered `56,430-437` — cf. Contexte vérifié
sur l'artefact de fusion de couverture).

- [ ] **Step 4: Falsify one test**

Dans `chart.tsx`, changer `onChange={(e) => set({ comparePeriod: e.target.value })}` (select
« Période de référence », ligne ~251) en `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx -t "PropsPanel edits comparePeriod"`
Expected: FAIL. Restaurer (`git checkout -- shell/src/builder/widgets/chart.tsx`), relancer :
PASS. Puis relancer la suite complète du fichier (`npx vitest run
src/builder/widgets/chart.test.tsx`) pour confirmer 23/23 verts après restauration.

- [ ] **Step 5: Ajouter les tests `tabs.tsx`**

Dans `shell/src/builder/widgets/tabs.test.tsx`, avant le test `"PropsPanel refuses to remove the
last remaining tab"`, ajouter :

```tsx
test("PropsPanel renames a tab", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{ tabs: [{ id: "t1", label: "Onglet 1", items: [] }] }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.type(screen.getByLabelText("Nom de l'onglet Onglet 1"), "x");
  const tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs[0].label).toBe("Onglet 1x");
});

test("PropsPanel removes a tab and re-selects the first remaining one", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{
        tabs: [
          { id: "t1", label: "Onglet 1", items: [] },
          { id: "t2", label: "Onglet 2", items: [] },
        ],
      }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Supprimer l'onglet Onglet 1" }));
  const tabs = onChange.mock.calls.at(-1)![0].tabs;
  expect(tabs.map((t: { label: string }) => t.label)).toEqual(["Onglet 2"]);
});

test("PropsPanel reorders tabs with the up button", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("tabs")!.PropsPanel;
  render(
    <Panel
      props={{
        tabs: [
          { id: "t1", label: "Onglet 1", items: [] },
          { id: "t2", label: "Onglet 2", items: [] },
        ],
      }}
      dataSources={[]}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Monter l'onglet Onglet 2" }));
  const tabs = onChange.mock.calls.at(-1)![0].tabs as Array<{ label: string }>;
  expect(tabs.map((t) => t.label)).toEqual(["Onglet 2", "Onglet 1"]);
});

test("Component shows a placeholder when there are no tabs at all", () => {
  const Tabs = getWidget("tabs")!.Component;
  render(<Tabs props={{ tabs: [] }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Aucun onglet")).toBeInTheDocument();
});
```

- [ ] **Step 6: Verify `tabs.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx --coverage --coverage.include='src/builder/widgets/tabs.tsx' --coverage.reportsDirectory=/tmp/cov-c9`
Expected: 11 tests passed, `Lines : 100%` (41/41).

- [ ] **Step 7: Falsify one test**

Dans `tabs.tsx`, changer `onChange={(e) => renameTab(tab.id, e.target.value)}` (ligne ~74) en
`onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx -t "renames a tab"`
Expected: FAIL. Restaurer (`git checkout -- shell/src/builder/widgets/tabs.tsx`), relancer : PASS.

- [ ] **Step 8: Ajouter le test `navigation.tsx`**

Dans `shell/src/builder/widgets/navigation.test.tsx`, avant le test `"supports a vertical
orientation prop"`, ajouter :

```tsx
test("PropsPanel switches the orientation to vertical", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("nav")!.PropsPanel!;
  render(<Panel props={{}} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Orientation du menu"), "vertical");
  expect(onChange).toHaveBeenCalledWith({ direction: "vertical" });
});
```

- [ ] **Step 9: Verify `navigation.tsx` coverage**

Run: `cd shell && npx vitest run src/builder/widgets/navigation.test.tsx --coverage --coverage.include='src/builder/widgets/navigation.tsx' --coverage.reportsDirectory=/tmp/cov-c9`
Expected: 4 tests passed, `Lines : 100%` (10/10).

- [ ] **Step 10: Falsify one test**

Dans `navigation.tsx`, changer `onChange={(e) => onChange({ ...props, direction: e.target.value
})}` en `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/navigation.test.tsx -t "switches the orientation"`
Expected: FAIL. Restaurer (`git checkout -- shell/src/builder/widgets/navigation.tsx`), relancer :
PASS.

- [ ] **Step 11: Full-suite sanity + commit**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx src/builder/widgets/tabs.test.tsx src/builder/widgets/navigation.test.tsx`
Expected: 3 files, 0 failed.

```bash
git add shell/src/builder/widgets/chart.test.tsx shell/src/builder/widgets/tabs.test.tsx \
  shell/src/builder/widgets/navigation.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre le PropsPanel de Graphique/le cycle de vie des onglets/l'orientation de Navigation

chart.tsx 75%→95% (lignes, mesure isolée) : dataSourceId/categoryField/
valueField/cible sankey/niveaux de hiérarchie/comparePeriod/axes/titre/
stack/legend/zoom/option avancée du PropsPanel, plus les états chargement/
erreur du mode comparaison, n'étaient testés par aucun des 17 tests
existants. tabs.tsx 78%→100% : renommage, suppression réelle (≥2 onglets),
réordonnancement vers le haut, cas 0 onglet du Component. navigation.tsx
80%→100% : sélecteur d'orientation du PropsPanel. Aucune ligne de
production touchée ; un test par fichier falsifié (handler temporairement
neutralisé, confirmation d'échec, restauration).

Note pour la clôture du plan : la mesure agrégée de chart.tsx (lignes
430-437, rendu de succès du mode comparaison) diffère entre une exécution
isolée du fichier et son exécution dans la suite complète — artefact de
fusion de couverture v8/vitest déjà présent avant cette tâche, sans
rapport avec les tests ajoutés ici. Revérifier le vrai pourcentage sur
shell/coverage/coverage-summary.json (suite complète) plutôt que sur la
mesure isolée avant de conclure que la fonctionnalité franchit 90.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Couverture de `CrossFilterLinkEditor.tsx` et `selectFilter.tsx` (cross-filter)

**Files:**
- Modify: `shell/src/builder/CrossFilterLinkEditor.test.tsx`
- Modify: `shell/src/builder/widgets/selectFilter.test.tsx`

**Interfaces:**
- Consomme : `CrossFilterLinkEditor` (`shell/src/builder/CrossFilterLinkEditor.tsx`, inchangé), `registerSelectFilterWidget`/`getWidget("selectFilter")` (`shell/src/builder/widgets/selectFilter.tsx`, inchangé) — aucune ligne de production modifiée par cette tâche.
- Produit : aucune interface nouvelle, uniquement de la couverture de test.

**Context vérifié** :
- `CrossFilterLinkEditor.tsx` : baseline mesurée `npx vitest run src/builder/CrossFilterLinkEditor.test.tsx --coverage --coverage.include='src/builder/CrossFilterLinkEditor.tsx'` → **76.47 % lignes (13/17)**, non couvert `89,105-124` — le gestionnaire `onChange` du select « Champ source » (ligne 89), celui du select « Champ cible » (ligne 105), et celui du select « Précision spatiale du lien » (ligne 124) ne sont jamais déclenchés par les 8 tests existants (ils rendent ces selects mais ne les manipulent jamais).
- `selectFilter.tsx` : baseline **82.75 % lignes (24/29)**, non couvert `33-54,95` — le `PropsPanel` (lignes 33-54) n'est rendu par aucun test existant, et la branche d'erreur de la requête (`query.isError`, ligne 95→98) n'est jamais exercée (tous les tests existants résolvent `queryDataSource`).

- [ ] **Step 1: Run coverage to confirm the current baseline (CrossFilterLinkEditor)**

Run: `cd shell && npx vitest run src/builder/CrossFilterLinkEditor.test.tsx --coverage --coverage.include='src/builder/CrossFilterLinkEditor.tsx'`
Expected: `Lines : 76.47%` (13/17), 7 tests passed.

- [ ] **Step 2: Add 3 tests to `CrossFilterLinkEditor.test.tsx`**

À la fin du fichier, après le test `"clicking remove calls onRemove"` :

```tsx
test("selecting a source field calls onChange with the updated sourceField", async () => {
  const { onChange } = renderEditor(
    {},
    { link: { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" } },
  );
  await userEvent.selectOptions(screen.getByLabelText("Champ source"), "commune");
  expect(onChange).toHaveBeenCalledWith({
    targetDatasetId: "ds-2",
    mode: "attribute",
    sourceField: "commune",
    targetField: "",
  });
});

test("selecting a target field calls onChange with the updated targetField", async () => {
  const { onChange } = renderEditor(
    {
      getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset),
      getCollectionSchema: vi.fn().mockResolvedValue(incidentsSchema),
    },
    { link: { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" } },
  );
  // Attendre "titre" (unique à la cible) plutôt que "commune" (présent dans
  // les deux selects — Champ source ET Champ cible — ce qui rendrait
  // getByRole("option", { name: "commune" }) ambigu).
  await waitFor(() => expect(screen.getByRole("option", { name: "titre" })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Champ cible"), "commune");
  expect(onChange).toHaveBeenCalledWith({
    targetDatasetId: "ds-2",
    mode: "attribute",
    sourceField: "",
    targetField: "commune",
  });
});

test("selecting a spatial precision calls onChange with the updated precision", async () => {
  const { onChange } = renderEditor(
    {
      getDatasetConfig: vi.fn().mockResolvedValue(incidentsDataset),
      getCollectionSchema: vi.fn().mockResolvedValue(incidentsSchema),
    },
    { link: { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" } },
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Précision spatiale du lien")).toBeInTheDocument(),
  );
  await userEvent.selectOptions(screen.getByLabelText("Précision spatiale du lien"), "exact");
  expect(onChange).toHaveBeenCalledWith({
    targetDatasetId: "ds-2",
    mode: "spatial",
    precision: "exact",
  });
});
```

- [ ] **Step 3: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/CrossFilterLinkEditor.test.tsx --coverage --coverage.include='src/builder/CrossFilterLinkEditor.tsx'`
Expected: 10 tests passed, `Lines : 100%` (17/17).

- [ ] **Step 4: Falsify one test**

Dans `shell/src/builder/CrossFilterLinkEditor.tsx` ligne 105, remplacer temporairement
`onChange={(e) => onChange({ ...link, targetField: e.target.value })}` par `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/CrossFilterLinkEditor.test.tsx -t "selecting a target field"`
Expected: FAIL (`expect(onChange).toHaveBeenCalledWith(...)` jamais satisfait).

Restaurer : `git checkout -- shell/src/builder/CrossFilterLinkEditor.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 5: Run coverage to confirm the current baseline (selectFilter)**

Run: `cd shell && npx vitest run src/builder/widgets/selectFilter.test.tsx --coverage --coverage.include='src/builder/widgets/selectFilter.tsx'`
Expected: `Lines : 82.75%` (24/29), 4 tests passed.

- [ ] **Step 6: Add 2 tests to `selectFilter.test.tsx`**

À la fin du fichier :

```tsx
test("PropsPanel edits dataSourceId, field and label", async () => {
  const onChange = vi.fn();
  const PropsPanel = getWidget("selectFilter")!.PropsPanel!;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn() } as unknown as ItemClient;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <PropsPanel
          props={{ dataSourceId: "", field: "", label: "" }}
          onChange={onChange}
          dataSources={[{ id: "src-1", type: "features", service: "core", layer: "parcs", query: {} }]}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.selectOptions(screen.getByRole("combobox"), "src-1");
  expect(onChange).toHaveBeenLastCalledWith({ dataSourceId: "src-1", field: "", label: "" });
  await userEvent.type(screen.getByLabelText("Champ"), "region");
  expect(onChange).toHaveBeenLastCalledWith({ dataSourceId: "", field: "n", label: "" });
  await userEvent.type(screen.getByLabelText("Libellé"), "Région");
  expect(onChange).toHaveBeenLastCalledWith({ dataSourceId: "", field: "", label: "n" });
});

test("shows an alert message when the options query fails", async () => {
  const queryDataSource = vi.fn().mockRejectedValue(new Error("boom"));
  renderSelect({}, queryDataSource);
  expect(await screen.findByRole("alert")).toHaveTextContent(/Impossible de charger/);
});
```

Note : `QueryClient`/`QueryClientProvider`/`ItemClient` sont déjà importés en tête de fichier (utilisés par `renderSelect`) — aucun nouvel import requis. `PropsPanel` doit être rendu sous `QueryClientProvider`+`ItemClientProvider` : `DataSourceSelect` (utilisé par `PropsPanel`) appelle `useItems`, qui lève sans ces deux providers (vérifié).

- [ ] **Step 7: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/widgets/selectFilter.test.tsx --coverage --coverage.include='src/builder/widgets/selectFilter.tsx'`
Expected: 6 tests passed, `Lines : 100%` (29/29).

- [ ] **Step 8: Falsify one test**

Dans `shell/src/builder/widgets/selectFilter.tsx` ligne 45, remplacer temporairement
`onChange={(e) => onChange({ ...props, field: e.target.value })}` par `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/widgets/selectFilter.test.tsx -t "PropsPanel"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/widgets/selectFilter.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/CrossFilterLinkEditor.test.tsx shell/src/builder/widgets/selectFilter.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre les selects de champ/précision de CrossFilterLinkEditor et le PropsPanel/l'erreur de selectFilter

CrossFilterLinkEditor.tsx : 76,47% -> 100% (champ source/cible,
précision spatiale, jamais manipulés par les tests existants).
selectFilter.tsx : 82,75% -> 100% (PropsPanel jamais rendu, branche
d'erreur de la requête jamais exercée). Aucune ligne de production
modifiée ; falsifié (retrait temporaire d'un handler par fichier,
confirmation d'échec, restauration).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Couverture de `GridCanvas.tsx`, `VariablesPanel.tsx` et `QueryJoinPicker.tsx` (infra builder, lot simple)

**Files:**
- Modify: `shell/src/builder/GridCanvas.test.tsx`
- Modify: `shell/src/builder/VariablesPanel.test.tsx`
- Modify: `shell/src/builder/visualQuery/QueryJoinPicker.test.tsx`

**Interfaces:**
- Consomme : `GridCanvas`, `VariablesPanel`, `QueryJoinPicker` — tous inchangés, aucune ligne de production modifiée.
- Produit : aucune interface nouvelle.

**Context vérifié** :
- `GridCanvas.tsx` : baseline **58.82 % lignes (10/17)**, non couvert `42,76-77,98-110` — seul le bouton « à droite » est cliqué par les tests existants ; « à gauche »/« en bas »/« en haut » et le clic sur le fond du canevas (désélection) ne le sont jamais.
- `VariablesPanel.tsx` : baseline **80 % lignes (20/25)**, non couvert `19-25,117` — `defaultValueFor()` n'est exercé que pour les cas `number` (via un test existant) ; les cas `bool`/`record`/`list`/`string` (par défaut) et l'édition d'une valeur `date` ne le sont jamais.
- `QueryJoinPicker.tsx` : baseline **77.77 % lignes (7/9)**, non couvert `32,52` — le changement de collection jointe et le changement de colonne de jointure ne sont jamais déclenchés par les 3 tests existants.

- [ ] **Step 1: Run coverage to confirm the current baseline (GridCanvas)**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx --coverage --coverage.include='src/builder/GridCanvas.tsx'`
Expected: `Lines : 58.82%` (10/17), 5 tests passed.

- [ ] **Step 2: Add 3 tests to `GridCanvas.test.tsx`**

À la fin du fichier :

```tsx
test("the move handle nudges the item left, down and up by one cell", async () => {
  const onMoveItem = vi.fn();
  renderCanvas({ selectedId: "a", onMoveItem });
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a à gauche" }));
  expect(onMoveItem).toHaveBeenCalledWith("a", -1, 0);
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a en bas" }));
  expect(onMoveItem).toHaveBeenCalledWith("a", 0, 1);
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a en haut" }));
  expect(onMoveItem).toHaveBeenCalledWith("a", 0, -1);
});

test("clicking the empty canvas backdrop deselects while editable", async () => {
  const onSelect = vi.fn();
  const { container } = renderCanvas({ selectedId: "a", onSelect });
  await userEvent.click(container.firstChild as Element);
  expect(onSelect).toHaveBeenCalledWith(null);
});

test("clicking the canvas backdrop is a no-op when not editable", async () => {
  const onSelect = vi.fn();
  const { container } = renderCanvas({ editable: false, selectedId: null, onSelect });
  await userEvent.click(container.firstChild as Element);
  expect(onSelect).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx --coverage --coverage.include='src/builder/GridCanvas.tsx'`
Expected: 8 tests passed, `Lines : 100%` (17/17).

- [ ] **Step 4: Falsify one test**

Dans `shell/src/builder/GridCanvas.tsx`, ligne 77 (`onMoveItem(item.id, -1, 0);` du bouton « à gauche »), remplacer temporairement par `onMoveItem(item.id, 0, 0);`.

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx -t "left, down and up"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/GridCanvas.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 5: Run coverage to confirm the current baseline (VariablesPanel)**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx --coverage --coverage.include='src/builder/VariablesPanel.tsx'`
Expected: `Lines : 80%` (20/25), 8 tests passed.

- [ ] **Step 6: Add 5 tests to `VariablesPanel.test.tsx`**

D'abord, ajouter `fireEvent` à l'import existant en tête de fichier :

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
```

Puis, à la fin du fichier :

```tsx
test("changes a variable's type to bool resets its initial value to false", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "gate", type: "string", initialValue: "x" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Type de la variable v1"), "bool");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0]).toEqual({ id: "v1", name: "gate", type: "bool", initialValue: false });
});

test("changes a variable's type to record resets its initial value to null", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "sel", type: "string", initialValue: "x" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Type de la variable v1"), "record");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0]).toEqual({ id: "v1", name: "sel", type: "record", initialValue: null });
});

test("changes a variable's type to list resets its initial value to an empty array", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "items", type: "string", initialValue: "x" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Type de la variable v1"), "list");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0]).toEqual({ id: "v1", name: "items", type: "list", initialValue: [] });
});

test("edits a date variable's initial value", () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "when", type: "date", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Valeur initiale de la variable v1"), {
    target: { value: "2026-09-15" },
  });
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].initialValue).toBe("2026-09-15");
});

test("changes a variable's type back to string resets its initial value to an empty string", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "count", type: "number", initialValue: 5 }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Type de la variable v1"), "string");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0]).toEqual({ id: "v1", name: "count", type: "string", initialValue: "" });
});
```

- [ ] **Step 7: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx --coverage --coverage.include='src/builder/VariablesPanel.tsx'`
Expected: 13 tests passed, `Lines : 100%` (25/25).

- [ ] **Step 8: Falsify one test**

Dans `shell/src/builder/VariablesPanel.tsx`, ligne 23 (`case "list": return [];`), remplacer temporairement par
`case "list": return { broken: true } as unknown as Variable["initialValue"];`.

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx -t "type to list"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/VariablesPanel.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 9: Run coverage to confirm the current baseline (QueryJoinPicker)**

Run: `cd shell && npx vitest run src/builder/visualQuery/QueryJoinPicker.test.tsx --coverage --coverage.include='src/builder/visualQuery/QueryJoinPicker.tsx'`
Expected: `Lines : 77.77%` (7/9), 3 tests passed.

- [ ] **Step 10: Add 2 tests to `QueryJoinPicker.test.tsx`**

Avant la fermeture finale du `describe("QueryJoinPicker", ...)` (juste après le test « change how notifie le parent ») :

```tsx
test("changer la collection jointe notifie le parent et réinitialise la colonne de jointure", async () => {
  const onChange = vi.fn();
  render(
    <QueryJoinPicker
      baseSchema={BASE}
      joinedSchema={null}
      collections={[{ id: "communes", title: "Communes" }]}
      value={{ collectionId: "", on: "", how: "inner" }}
      onChange={onChange}
    />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Collection à joindre"), "communes");
  expect(onChange).toHaveBeenCalledWith({ collectionId: "communes", on: "", how: "inner" });
});

test("changer la colonne de jointure notifie le parent", async () => {
  const onChange = vi.fn();
  render(
    <QueryJoinPicker
      baseSchema={BASE}
      joinedSchema={JOINED}
      collections={[{ id: "communes", title: "Communes" }]}
      value={{ collectionId: "communes", on: "", how: "inner" }}
      onChange={onChange}
    />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Colonne de jointure"), "commune");
  expect(onChange).toHaveBeenCalledWith({ collectionId: "communes", on: "commune", how: "inner" });
});
```

- [ ] **Step 11: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/visualQuery/QueryJoinPicker.test.tsx --coverage --coverage.include='src/builder/visualQuery/QueryJoinPicker.tsx'`
Expected: 5 tests passed, `Lines : 100%` (9/9).

- [ ] **Step 12: Falsify one test**

Dans `shell/src/builder/visualQuery/QueryJoinPicker.tsx` ligne 32, remplacer temporairement
`onChange={(e) => onChange({ ...value, collectionId: e.target.value, on: "" })}` par `onChange={() => {}}`.

Run: `cd shell && npx vitest run src/builder/visualQuery/QueryJoinPicker.test.tsx -t "changer la collection"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/visualQuery/QueryJoinPicker.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 13: Commit**

```bash
git add shell/src/builder/GridCanvas.test.tsx shell/src/builder/VariablesPanel.test.tsx shell/src/builder/visualQuery/QueryJoinPicker.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre les 3 déplacements/désélection de GridCanvas, les 4 types de variable non testés de VariablesPanel et les 2 selects de QueryJoinPicker

GridCanvas.tsx : 58,82% -> 100% (gauche/bas/haut, désélection sur fond
de canevas). VariablesPanel.tsx : 80% -> 100% (bool/record/list/string
par défaut, valeur de date). QueryJoinPicker.tsx : 77,77% -> 100%
(changement de collection jointe, changement de colonne de jointure).
Aucune ligne de production modifiée ; falsifié (retrait temporaire d'un
comportement réel par fichier, confirmation d'échec, restauration).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Couverture de `AppExportPanel.tsx` et `PipelineScheduleEditor.tsx` (infra builder, lot async/temporisé)

**Files:**
- Modify: `shell/src/builder/appexport/AppExportPanel.test.tsx`
- Modify: `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx`

**Interfaces:**
- Consomme : `AppExportPanel`, `PipelineScheduleEditor`/`parseCron`/`compileCron` — tous inchangés, aucune ligne de production modifiée.
- Produit : aucune interface nouvelle.

**Context vérifié** :
- `AppExportPanel.tsx` : baseline **80 % lignes (40/50)**, non couvert `44-52,65,104,129` — la boucle de poll qui continue tant que le job est `pending`/`running` (44-52) n'est jamais exercée au-delà d'un seul appel « done » immédiat ; le `catch` de `runExport` (65, échec de `createAppExport`) n'est jamais déclenché ; le bouton « Fermer » (104) et le bouton « Ne pas exporter » (129) ne sont jamais cliqués. Le composant partage déjà le patron de poll de `shell/src/builder/print/ExportPanel.tsx` (commentaire de tête du fichier) — `ExportPanel.test.tsx` porte déjà un test de plafond de poll avec fake timers (`describe("ExportPanel — plafond de poll (finding I7)")`) repris ici à l'identique pour `AppExportPanel`.
- `PipelineScheduleEditor.tsx` : baseline **80.43 % lignes (37/46)**, non couvert `13,122-185` — le mode `weekly` (sélection du mode, jour, heure) n'est jamais exercé par l'UI dans aucun des 8 tests existants (`dayLabels()`, appelée uniquement en rendu du mode weekly, n'est donc jamais invoquée non plus — ligne 13).

- [ ] **Step 1: Run coverage to confirm the current baseline (AppExportPanel)**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx --coverage --coverage.include='src/builder/appexport/AppExportPanel.tsx'`
Expected: `Lines : 80%` (40/50), 5 tests passed.

- [ ] **Step 2: Update imports in `AppExportPanel.test.tsx`**

Remplacer la ligne d'import existante :

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
```

par :

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
```

- [ ] **Step 3: Add 5 tests, après la fermeture du `describe("AppExportPanel", ...)` existant**

```tsx
it("polls again while the job is still pending, then shows the download link", async () => {
  let call = 0;
  const getAppExportJob = vi.fn().mockImplementation(() => {
    call += 1;
    const status = call < 2 ? "pending" : "done";
    return Promise.resolve({
      id: "job1",
      status,
      resultUrl: status === "done" ? "https://x.test/bundle.zip" : null,
      error: null,
    });
  });
  const client = makeClient({
    createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
    getAppExportJob,
  });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config()} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  await userEvent.click(screen.getByRole("button", { name: /statique/i }));
  await waitFor(
    () => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument(),
    { timeout: 5000 },
  );
  expect(call).toBeGreaterThanOrEqual(2);
});

it("surfaces a failure to even create the job", async () => {
  const client = makeClient({
    createAppExport: vi.fn().mockRejectedValue(new Error("Request failed: 500")),
    getAppExportJob: vi.fn(),
  });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config()} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  await userEvent.click(screen.getByRole("button", { name: /statique/i }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/échec/i));
});

it("closes the mode picker without exporting", async () => {
  const createAppExport = vi.fn();
  const client = makeClient({ createAppExport, getAppExportJob: vi.fn() });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config()} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  expect(screen.getByText(/mode d.export/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /fermer/i }));
  expect(screen.queryByText(/mode d.export/i)).not.toBeInTheDocument();
  expect(createAppExport).not.toHaveBeenCalled();
});

it("dismisses the write-widget warning without exporting", async () => {
  const createAppExport = vi.fn();
  const client = makeClient({ createAppExport, getAppExportJob: vi.fn() });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config(true)} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  await userEvent.click(screen.getByRole("button", { name: /statique/i }));
  expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /ne pas exporter/i }));
  expect(screen.queryByText(/écriture.*désactivée/i)).not.toBeInTheDocument();
  expect(createAppExport).not.toHaveBeenCalled();
});

describe("AppExportPanel — plafond de poll", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stops polling after the max attempt budget and surfaces a clear error instead of polling forever", async () => {
    const createAppExport = vi.fn().mockResolvedValue({ jobId: "job1" });
    const getAppExportJob = vi
      .fn()
      .mockResolvedValue({ id: "job1", status: "running", resultUrl: null, error: null });
    const client = makeClient({ createAppExport, getAppExportJob });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /exporter/i }));
    fireEvent.click(screen.getByRole("button", { name: /statique/i }));

    // 200 tentatives x 1500ms (MAX_POLL_ATTEMPTS x POLL_INTERVAL_MS) — même
    // patron que ExportPanel.test.tsx (« plafond de poll », finding I7).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 200);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/toujours en cours/i);
    const callsAtCap = getAppExportJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 10);
    });
    expect(getAppExportJob.mock.calls.length).toBe(callsAtCap);
  });
});
```

Note : ces 4 premiers `it(...)` sont volontairement hors du `describe("AppExportPanel", ...)` existant (qui se ferme juste avant) — syntaxe valide (vitest accepte des `it()` de niveau module), pas de restructuration du describe existant.

- [ ] **Step 4: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx --coverage --coverage.include='src/builder/appexport/AppExportPanel.tsx'`
Expected: 10 tests passed, `Lines : 100%` (50/50).

- [ ] **Step 5: Falsify one test**

Dans `shell/src/builder/appexport/AppExportPanel.tsx` ligne 104, remplacer temporairement
`onClick={() => setPickerOpen(false)}` (bouton Fermer) par `onClick={() => {}}`.

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx -t "closes the mode picker"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/appexport/AppExportPanel.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 6: Run coverage to confirm the current baseline (PipelineScheduleEditor)**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx --coverage --coverage.include='src/builder/pipeline/PipelineScheduleEditor.tsx'`
Expected: `Lines : 80.43%` (37/46), 14 tests passed.

- [ ] **Step 7: Update import and add 5 tests to `PipelineScheduleEditor.test.tsx`**

D'abord, ajouter `fireEvent` à l'import existant :

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
```

Puis, à la fin du fichier :

```tsx
test("switching to weekly mode compiles a default weekly cron and lists all 7 days", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "weekly");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "0 2 * * 1" });
  expect(screen.getByRole("option", { name: "Dimanche" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Samedi" })).toBeInTheDocument();
});

test("changing the weekly day recompiles the cron with the new day", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "30 9 * * 1" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Jour"), "3");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "30 9 * * 3" });
});

test("changing the weekly execution time recompiles the cron with the new time", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "30 9 * * 1" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Heure d'exécution"), { target: { value: "14:45" } });
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "45 14 * * 1" });
});

test("changing the interval minutes recompiles the cron", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Intervalle en minutes"), { target: { value: "5" } });
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "*/5 * * * *" });
});

test("switching to advanced mode keeps the current cron as the raw value", async () => {
  const onChange = vi.fn();
  const value: PipelineRefreshPolicy = { enabled: true, cron: "*/15 * * * *" };
  render(<PipelineScheduleEditor value={value} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Mode de planification"), "advanced");
  expect(onChange).toHaveBeenLastCalledWith({ enabled: true, cron: "*/15 * * * *" });
  expect(screen.getByLabelText("Expression cron")).toHaveValue("*/15 * * * *");
});
```

Note : le champ heure (`type="time"`) et le champ minutes ne sont pas fiables avec `userEvent.type` (saisie caractère par caractère sur un input natif `time`/`number`, l'état intermédiaire ne correspond pas à la valeur finale attendue — vérifié en session, `userEvent.type` sur « Heure d'exécution » produit `"59 9 * * 1"` au lieu de `"45 14 * * 1"`) : utiliser `fireEvent.change` comme ci-dessus.

- [ ] **Step 8: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx --coverage --coverage.include='src/builder/pipeline/PipelineScheduleEditor.tsx'`
Expected: 19 tests passed, `Lines : 97.82%` (45/46) — largement au-dessus du seuil requis (~83,3%), la ligne restante non couverte (154, un embranchement de `advanced`) est un résidu mineur, non bloquant.

- [ ] **Step 9: Falsify one test**

Dans `shell/src/builder/pipeline/PipelineScheduleEditor.tsx` ligne 167, remplacer temporairement
`handleSetForm({ mode: "weekly", day: e.target.value, time: form.time })` par
`handleSetForm({ mode: "weekly", day: form.day, time: form.time })`.

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx -t "changing the weekly day"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/pipeline/PipelineScheduleEditor.tsx`, relancer, `Expected: PASS`.

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/appexport/AppExportPanel.test.tsx shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre la boucle de poll/l'échec de création/Fermer/Ne pas exporter d'AppExportPanel et le mode hebdomadaire de PipelineScheduleEditor

AppExportPanel.tsx : 80% -> 100% (poll qui continue tant que pending,
échec de createAppExport, boutons Fermer et Ne pas exporter, plafond de
poll repris du patron ExportPanel/finding I7). PipelineScheduleEditor.tsx :
80,43% -> 97,82% (mode hebdomadaire jamais exercé : sélection, jour,
heure ; plus intervalle et bascule vers le mode avancé). Aucune ligne de
production modifiée ; falsifié (retrait temporaire d'un comportement réel
par fichier, confirmation d'échec, restauration).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Couverture de `EditCollectionPanel.tsx` et `routes.tsx` (pages shell)

**Files:**
- Modify: `shell/src/shell/EditCollectionPanel.test.tsx`
- Modify: `shell/src/shell/routes.test.tsx`

**Interfaces:**
- Consomme : `EditCollectionPanel` (`shell/src/shell/EditCollectionPanel.tsx`), `AppRoutes`/`useOpenItem` (`shell/src/shell/routes.tsx`) — inchangés, zéro ligne de production modifiée.
- Produit : rien de nouveau pour les tâches suivantes — tests purs.

**Context vérifié** (mesuré avec `npx vitest run <fichier> --coverage --coverage.include='<chemin>' --coverage.reportsDirectory=/tmp/cov-c12`, jamais deviné) :
- `EditCollectionPanel.tsx` : baseline **79.36 % lignes (50/63)**, non couvert `103,110,115,142,150,158,167,194,203,211,228,245,255,264,297` — l'onglet Général (titre/description/public/éditable) n'était jamais interagi (seulement pré-rempli et vérifié en lecture) ; producteur/contact/généalogie/version/emprise temporelle/URI de licence « Autre » idem côté onglet Métadonnées ; suppression d'un champ pièce jointe jamais exercée ; désactivation d'un champ déjà sensible jamais exercée ; ajout d'une clé déjà existante (`attachmentFields.some(...)`) jamais exercé.
- `routes.tsx` : baseline **61.29 % lignes (76/124)**. **Trouvaille importante, corrige l'analyse initiale de la spec** : la logique de restauration de contexte du signet elle-même (`getBookmarkConfig`, reconstruction d'URL avec `timeRange`/`extent`/`crossFilter`) est déjà **100 % couverte** par 2 tests existants (`"opening a bookmark navigates..."`, `"a failed bookmark config fetch..."`). Le déficit de ce fichier vient d'ailleurs : `useOpenItem` est une fonction **partagée** par 8 types d'item (`bookmark`/`pipeline`/`report`/`tileset3d`/`terrain3d`/`alert`/`external`/défaut), et 4 des 8 branches (`pipeline`, `report`, `tileset3d`, `terrain3d`) n'avaient aucun test — plus 15 imports `lazy()` de pages sans rapport avec les signets (Sites, SQL Lab, 6 pages Admin, etc., jamais visitées par cette suite) et une demi-douzaine d'autres fonctions de route (`PipelineNewRoute`, `VisualQueryWizardNewRoute`, `ReportNewRoute`, `ReportsRoute`, `SitePublicRoute`, `PublicItemRoute`, `DatasetRoute`, `EmbedRoute`) qui n'ont **aucun rapport avec « Mes vues (signets) »**.

- [ ] **Step 1: Run coverage to confirm the current baseline (EditCollectionPanel)**

Run: `cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx --coverage --coverage.include='src/shell/EditCollectionPanel.tsx' --coverage.reportsDirectory=/tmp/cov-c12`
Expected: `Lines : 79.36%` (50/63), 11 tests passed.

- [ ] **Step 2: Add tests to `EditCollectionPanel.test.tsx`**

D'abord, ajouter `fireEvent` à l'import existant en tête de fichier :

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
```

Avant `describe("EditCollectionPanel — champs attachment (SP-40)", ...)`, ajouter :

```tsx
describe("EditCollectionPanel — onglet Général", () => {
  it("édite le titre, la description et bascule public/éditable", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Titre"), "!");
    await userEvent.type(screen.getByLabelText("Description"), "d");
    await userEvent.click(screen.getByLabelText("Public"));
    await userEvent.click(screen.getByLabelText("Éditable"));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Incidents!",
        description: "d",
        isPublic: true,
        editable: false,
      }),
    );
  });
});
```

Dans `describe("EditCollectionPanel — champs attachment (SP-40)", ...)`, après le test `"ajoute puis soumet un nouveau champ attachment"`, ajouter :

```tsx
  it("refuse d'ajouter un champ dont la clé existe déjà", async () => {
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, attachmentFields: [{ key: "photos", label: "Photos" }] }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Pièces jointes" }));
    await userEvent.type(screen.getByLabelText("Clé du champ"), "photos");
    await userEvent.type(screen.getByLabelText("Libellé du champ"), "Doublon");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un champ" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("supprime un champ attachment existant", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, attachmentFields: [{ key: "photos", label: "Photos" }] }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Pièces jointes" }));
    await userEvent.click(screen.getByRole("button", { name: "Retirer" }));
    expect(screen.queryByDisplayValue("photos")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ attachmentFields: [] }));
  });
```

Dans `describe("EditCollectionPanel — champs sensibles (GAP-22)", ...)`, après le test `"coche un champ puis soumet sensitiveFields"`, ajouter :

```tsx
  it("décoche un champ déjà sensible puis soumet sensitiveFields sans lui", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel
        collection={{ ...baseCollection, sensitiveFields: ["titre", "gravite"] }}
        onClose={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Champs sensibles" }));
    await userEvent.click(screen.getByLabelText("titre"));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ sensitiveFields: ["gravite"] }),
    );
  });
```

Dans `describe("EditCollectionPanel — métadonnées ouvertes (SP-41)", ...)`, après le dernier test (`"envoie null pour une emprise temporelle non renseignée"`), ajouter :

```tsx
  it("édite producteur, contact, généalogie, version, emprise temporelle et l'URI de licence Autre", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(
      <EditCollectionPanel collection={{ ...baseCollection, license: "other" }} onClose={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.type(screen.getByLabelText("URI de la licence"), "u");
    await userEvent.type(screen.getByLabelText("Producteur"), "p");
    await userEvent.type(screen.getByLabelText("Contact"), "c");
    await userEvent.type(screen.getByLabelText("Généalogie"), "g");
    await userEvent.type(screen.getByLabelText("Version"), "1");
    fireEvent.change(screen.getByLabelText("Début de l'emprise temporelle"), {
      target: { value: "2026-01-01" },
    });
    fireEvent.change(screen.getByLabelText("Fin de l'emprise temporelle"), {
      target: { value: "2026-01-02" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        licenseUri: "u",
        producer: "p",
        contact: "c",
        lineage: "g",
        version: "1",
        temporalStart: "2026-01-01",
        temporalEnd: "2026-01-02",
      }),
    );
  });
```

- [ ] **Step 3: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx --coverage --coverage.include='src/shell/EditCollectionPanel.tsx' --coverage.reportsDirectory=/tmp/cov-c12`
Expected (vérifié en session) : 16 tests passed, `Lines : 100%` (63/63), `Statements : 100%`, `Functions : 100%`, `Branches : 79.06%` (résiduel — ternaires de chargement/absence de données, non bloquant).

- [ ] **Step 4: Falsify one test**

Dans `shell/src/shell/EditCollectionPanel.tsx`, fonction `removeAttachmentField` (ligne ~109-111), remplacer temporairement le corps par `void key;`.

Run: `cd shell && npx vitest run src/shell/EditCollectionPanel.test.tsx -t "supprime un champ attachment"`
Expected: FAIL — `expect(element).not.toBeInTheDocument()` trouve toujours l'input `photos`.

Restaurer (`git checkout -- shell/src/shell/EditCollectionPanel.tsx`), relancer : PASS.

- [ ] **Step 5: Run coverage to confirm the current baseline (routes.tsx)**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx --coverage --coverage.include='src/shell/routes.tsx' --coverage.reportsDirectory=/tmp/cov-c12b`
Expected: `Lines : 61.29%` (76/124), 15 tests passed.

- [ ] **Step 6: Add mocks and 4 tests to `routes.test.tsx`**

Après le mock existant de `AdminExtensionsPage`, ajouter :

```tsx
vi.mock("../pages/PipelineBuilderPage", () => ({
  PipelineBuilderPage: ({ pk }: { pk: string | null }) => <div>pipeline-builder-{pk}</div>,
}));

vi.mock("../pages/ReportEditPage", () => ({
  ReportEditPage: ({ pk }: { pk: string | null }) => <div>report-edit-{pk}</div>,
}));
```

Avant le test `"a failed alert config fetch surfaces an error instead of silently doing nothing"`, ajouter :

```tsx
test("opening a pipeline navigates to its editor, not a generic app editor", async () => {
  server.use(
    http.get("https://core.test/v1/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "pl-1",
            resourceType: "pipeline",
            title: "Pipeline nocturne",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
  );
  wrap(<AppRoutes />);
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByText("pipeline-builder-pl-1")).toBeInTheDocument();
});

test("opening a report navigates to its editor, not a generic app editor", async () => {
  server.use(
    http.get("https://core.test/v1/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "rp-1",
            resourceType: "report",
            title: "Rapport mensuel",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
  );
  wrap(<AppRoutes />);
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByText("report-edit-rp-1")).toBeInTheDocument();
});

test.each(["tileset3d", "terrain3d"] as const)(
  "opening a %s item navigates to its item detail page, not a generic app editor",
  async (resourceType) => {
    server.use(
      http.get("https://core.test/v1/items", () =>
        HttpResponse.json({
          items: [
            {
              pk: "hosted-1",
              resourceType,
              title: "Contenu hébergé",
              abstract: "",
              owner: "alice",
              thumbnailUrl: null,
              date: "",
              configId: null,
              isPublished: false,
            },
          ],
          total: 1,
          page: 1,
          pageSize: 12,
        }),
      ),
    );
    wrap(<AppRoutes />);
    await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
    expect(await screen.findByText("item-detail-hosted-1")).toBeInTheDocument();
  },
);
```

- [ ] **Step 7: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx --coverage --coverage.include='src/shell/routes.tsx' --coverage.reportsDirectory=/tmp/cov-c12b`
Expected (vérifié en session) : 19 tests passed, `Lines : 70.96%` (88/124) — toutes les branches de `useOpenItem` (les 8 types d'item) sont désormais 100 % couvertes ; le résiduel non couvert (37 lignes) est exclusivement composé d'imports `lazy()` de pages sans rapport (Sites, SQL Lab, 6 pages Admin, etc.) et de fonctions de route sans rapport avec les signets.

- [ ] **Step 8: Falsify one test**

Dans `shell/src/shell/routes.tsx`, ligne ~125 (`` navigate(`/pipelines/${pk}/edit`); ``), remplacer temporairement par `` navigate(`/apps/${pk}/edit`); ``.

Run: `cd shell && npx vitest run src/shell/routes.test.tsx -t "opening a pipeline navigates"`
Expected: FAIL — timeout, `pipeline-builder-pl-1` jamais rendu.

Restaurer (`git checkout -- shell/src/shell/routes.tsx`), relancer : PASS.

- [ ] **Step 9: Constat honnête — `routes.tsx` ne peut pas atteindre 90 % dans ce périmètre**

**IMPORTANT, à répercuter dans la tâche de clôture (Volet D) et dans le tableau §1 de la spec** :
avec `atteignabilité`/`garde` non applicables (pas de surface REST/MCP pour « Mes vues ») et
`dette` à 100, la santé de cette fonctionnalité est `0.6 × tests + 40`. Pour dépasser 90, `tests`
(la couverture de lignes de **tout le fichier** `routes.tsx`) doit atteindre ≥ 83.3 % — or ce
fichier sert 20+ routes sans rapport avec les signets. Le porter à 83.3 % nécessiterait de couvrir
tout ou partie de : 15 imports `lazy()` de pages (Sites publics, SQL Lab, 6 pages Admin, Dataset,
Embed, VisualQueryWizard…) et 8 fonctions de route additionnelles (`PipelineNewRoute`,
`VisualQueryWizardNewRoute`/`EditRoute`, `ReportNewRoute`, `ReportsRoute`, `SitePublicRoute`,
`PublicItemRoute`, `DatasetRoute`, `EmbedRoute`) — aucun rattaché à « Mes vues (signets) ». Ce n'est
pas un travail proportionné à cette tâche ; le documenter ici plutôt que gonfler artificiellement le
périmètre (ou pire, écrire des tests qui ne visent qu'à toucher des lignes sans exercer un vrai
comportement). **Décision à prendre en Task 12 de ce plan** : soit un futur SP couvre
`routes.tsx` plus largement (bénéficierait à plusieurs fonctionnalités d'un coup, dont Mes vues),
soit cette fonctionnalité reste sous 90 et doit être documentée comme exception assumée (même
doctrine que `REV-176`) plutôt que comptée dans le plancher `plancher_priorite_moyenne`.

- [ ] **Step 10: Commit**

```bash
git add shell/src/shell/EditCollectionPanel.test.tsx shell/src/shell/routes.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre l'onglet Général/la suppression de pièce jointe/le
désélection de champ sensible d'EditCollectionPanel et les 4 branches
d'item non-bookmark de useOpenItem (routes.tsx)

EditCollectionPanel.tsx : 79,36% -> 100% (titre/description/public/
éditable jamais édités ; producteur/contact/généalogie/version/emprise
temporelle/URI Autre jamais édités ; suppression de pièce jointe et
désactivation d'un champ sensible jamais exercées ; garde anti-doublon
de clé jamais exercée). routes.tsx : 61,29% -> 70,96% (les 4 branches
pipeline/report/tileset3d/terrain3d de useOpenItem, partagée avec
bookmark, n'avaient aucun test — la logique propre aux signets était
déjà 100% couverte). Aucune ligne de production modifiée ; 2
falsifications (retrait temporaire d'un comportement réel, confirmation
d'échec, restauration).

Constat documenté (Step 9) : routes.tsx ne peut pas dépasser 90% de
santé pour la fonctionnalité "Mes vues" sans couvrir ~20 routes sans
rapport (Sites, SQL Lab, pages Admin...) — hors périmètre de cette
tâche, à trancher en clôture de plan (Volet D).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

## TROUVAILLE MAJEURE POUR LE PLAN GLOBAL

**« Mes vues (signets) » (`catalogue-mes-vues-signets`) ne peut PAS être portée à ≥90 dans ce plan.**
Meilleur atteignable mesuré : 70.96% de tests → santé ≈ 0.6×70.96+40 = 82.6. À traiter en Task
Volet D comme exception documentée assumée (ajouter au §6 « Hors périmètre » de la spec et au texte
de Volet D : le plancher `plancher_priorite_moyenne` doit être mesuré en excluant explicitement
cette fonctionnalité, avec une ligne dédiée dans le bilan/CLAUDE.md justifiant l'exception, plutôt
que de bloquer tout le plancher sous 83).

---

### Task 11: Couverture du rapport PDF planifié (mixte core+shell), compaction GeoParquet, et vérification QGIS Processing

**Files:**
- Modify: `core/tests/test_report_jobs.py`
- Create: `core/tests/test_cdc_jobs.py`
- Create: `shell/src/builder/report/ReportScheduleEditor.test.tsx`
- Modify: `shell/src/pages/ReportEditPage.test.tsx`

**Interfaces:**
- Consomme : `app.reports.jobs`, `app.cdc.jobs`, `ReportScheduleEditor`, `ReportEditPage` — tous inchangés, aucune ligne de production modifiée par cette tâche.
- Produit : rien de consommable par les autres tâches — tests purs, sauf pour la note de séquencement ci-dessous (dépendance de lecture sur Task 1).

**Context vérifié** (mesuré, pas deviné) :

- **`core/app/pipelines/ops/schemas.py`** (une des 2 preuves de « Transformer spatialement via QGIS Processing ») est déjà à **100 % de lignes** (`PYTHONPATH=. uv run pytest tests/test_pipeline_ops_schemas.py --cov=app.pipelines.ops.schemas --cov-report=term-missing` → `92/92`). L'autre preuve, `deploy/qgis-worker/server.py`, est fermée par Task 1 (repli littéral, `test_qgis_worker_server_handler.py` la cite déjà). **Aucun test à ajouter pour cette fonctionnalité** — régénérer le bilan une fois Task 1 fusionnée avant de conclure, mais elle devrait déjà atteindre 100 sans aucun travail supplémentaire.
- **`core/app/reports/jobs.py`** : baseline mesurée `86 %` (147 lignes, 21 manquantes) avec la seule suite existante (`test_report_jobs.py`, 18 tests, aucune DB Postgres requise — fixture SQLite en mémoire, `_make_session()`). Angles morts réels : dispatch du canal `email` (webhook seul était testé), filet TOCTOU config-supprimée-entre-listing-et-fetch (169-170), bookmark existant mais sans config `bookmark` (195-197, distinct du cas "accès refusé" déjà couvert), run de déclenchement échoué sans `export_job_id` (313-320), et le point d'entrée `sweep_report_schedules_task` lui-même — jamais appelé directement par aucun test existant, ni en mode lecture seule ni en mode normal.
- **`core/app/cdc/jobs.py`** (36 lignes) : **aucun fichier de test dédié** (seul `test_jobs.py` vérifie que la tâche est enregistrée, jamais qu'elle s'exécute). Le wrapper périodique (lecture des variables d'environnement, construction du client S3, appel à `compaction.run_compaction_cycle`, log du rapport) n'est jamais exercé — `compaction.py`/`storage.py` le sont séparément par leurs propres suites, mais pas ce fichier de câblage.
- **`shell/src/builder/report/ReportScheduleEditor.tsx`** : **aucun fichier de test** (`find` ne retrouve que le fichier de production). Mesuré en incident via `ReportEditPage.test.tsx` : 22 % de lignes.
- **`shell/src/pages/ReportEditPage.tsx`** : baseline mesurée `64.28 %` (via `ReportScheduleEditor.tsx` inclus dans la même mesure, cf. ci-dessus) — aucun des 7 tests existants ne clique jamais sur « Enregistrer » (`onSave`, lignes 87-103).
- **`core/app/configs/schemas.py` et `core/app/configs/routes.py`** (244 et 513 lignes) : **délibérément hors périmètre de cette tâche.** Ce sont des fichiers massivement partagés (pipelines, alertes, apps, bookmarks, rapports…), exactement le cas déjà documenté dans le docstring de `coverage_facts.py` (« un fichier partagé par cinq fonctionnalités leur donne à toutes le même chiffre »). Mesurer leur seul fichier de test dédié (`test_configs_schemas.py`, 5 tests → 70 %) sous-compte grossièrement leur couverture réelle, qui vient de dizaines d'autres suites à travers tout le dépôt. Écrire des tests ciblés sur la portion « rapport » de ces 2 fichiers dans le cadre d'une tâche censée fermer une seule fonctionnalité serait un travail dupliqué et disproportionné. **Action requise : après fusion de toutes les tâches de ce plan, régénérer `core/coverage.xml` par la suite complète et relire le vrai pourcentage agrégé de ces 2 fichiers avant de décider si un travail ciblé supplémentaire est nécessaire — ne jamais se fier à la mesure isolée ci-dessus.**

- [ ] **Step 1: Run coverage to confirm the `reports/jobs.py` baseline**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_report_jobs.py --cov=app.reports.jobs --cov-report=term-missing`
Expected: `18 passed`, `Cover 86%`, `Missing 50-51, 109-114, 170, 197, 318-320, 345, 385-386, 428-431, 452-457`.

- [ ] **Step 2: Add 8 tests to `core/tests/test_report_jobs.py`**

À la fin du fichier :

```python
def test_notify_sends_email_and_marks_notified(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard"
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report"
        ).id
        config = BuilderConfig.model_validate(
            {
                "kind": "report",
                "report": {
                    "bookmarkItemId": "bookmark-x",
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [
                        {"kind": "email", "to": "ops@example.test", "smtpSecretName": "smtp-1"}
                    ],
                },
            }
        )
        configs_repo.create_config(s, config, item_id=report_id, tenant_id=tenant.id)
        job = export_repo.create_job(
            s, tenant_id=tenant.id, item_id=app_item.id, user_id=owner.id, format="pdf"
        )
        export_repo.mark_done(s, job_id=job.id, result_key="renders/job-1.pdf")
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=job.id
        )
        s.commit()

    sent = []
    monkeypatch.setattr(
        report_jobs,
        "send_email",
        lambda session, *, tenant_id, channel, subject, body: sent.append((channel, subject, body)),
    )
    monkeypatch.setattr(
        report_jobs, "_presigned_url_for_job", lambda job: "https://s3.test/renders/job-1.pdf"
    )
    report_jobs._notify_pending_reports(Session)

    assert len(sent) == 1
    assert sent[0][0].to == "ops@example.test"
    assert "Weekly report" in sent[0][1]
    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None


def test_trigger_skips_a_report_whose_config_vanishes_between_listing_and_fetch(monkeypatch):
    """Filet TOCTOU (jobs.py:169-170) : list_due_reports() (repository.py)
    ne relit jamais la config au moment du déclenchement — un config
    supprimé/reconverti entre les deux doit être ignoré, pas planter le
    sweep pour les autres tenants."""
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        app_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="Dashboard"
        )
        bookmark_id = _seed_bookmark(s, tenant_id=tenant.id, owner_id=owner.id, app_id=app_item.id)
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=bookmark_id
        )
        s.commit()

    real_get_config_by_item = configs_repo.get_config_by_item

    def fake_get_config_by_item(session, item_id):
        if item_id == report_id:
            return None
        return real_get_config_by_item(session, item_id)

    monkeypatch.setattr(report_jobs.configs_repo, "get_config_by_item", fake_get_config_by_item)
    report_jobs._trigger_due_reports(Session)

    with Session() as s:
        assert reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id) is None


def test_trigger_fails_report_when_bookmark_config_is_missing(monkeypatch):
    """jobs.py:195-197 : le bookmark référencé est un item lisible (les
    access facts existent) mais n'a plus de config `bookmark` — distinct du
    cas "bookmark not readable" (access facts absents), déjà couvert."""
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        orphan_bookmark = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="bookmark", title="Orphan"
        )
        report_id = _seed_report(
            s, tenant_id=tenant.id, owner_id=owner.id, bookmark_item_id=orphan_bookmark.id
        )
        s.commit()

    report_jobs._trigger_due_reports(Session)

    with Session() as s:
        run = reports_repo.get_latest_run(s, tenant_id=tenant.id, report_item_id=report_id)
        assert run is not None
        assert run.export_job_id is None
        audit = s.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id, AuditLog.object_id == report_id
            )
        )
        assert audit.payload["error"] == "bookmark config not found"


def test_notify_pending_reports_closes_a_run_with_no_export_job(monkeypatch):
    """jobs.py:313-320 : filet de sécurité pour un run de déclenchement
    échoué (export_job_id=None) que _record_trigger_failure n'aurait, par
    hypothèse, pas déjà marqué notifié — rien à notifier, on le clôt."""
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        report_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="report", title="Weekly report"
        ).id
        run = reports_repo.create_run(
            s, tenant_id=tenant.id, report_item_id=report_id, export_job_id=None
        )
        s.commit()

    report_jobs._notify_pending_reports(Session)

    with Session() as s:
        fetched = reports_repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.notified_at is not None


def test_sweep_report_schedules_task_skips_everything_in_read_only_mode(monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    called = []
    monkeypatch.setattr(
        report_jobs, "_trigger_due_reports", lambda factory: called.append("trigger")
    )
    monkeypatch.setattr(
        report_jobs, "_notify_pending_reports", lambda factory: called.append("notify")
    )
    report_jobs.sweep_report_schedules_task(timestamp=0)
    assert called == []


def test_sweep_report_schedules_task_runs_trigger_then_notify_outside_read_only_mode(monkeypatch):
    monkeypatch.delenv("CORE_READ_ONLY_MODE", raising=False)
    called = []
    monkeypatch.setattr(
        report_jobs, "_trigger_due_reports", lambda factory: called.append(("trigger", factory))
    )
    monkeypatch.setattr(
        report_jobs, "_notify_pending_reports", lambda factory: called.append(("notify", factory))
    )
    report_jobs.sweep_report_schedules_task(timestamp=0)
    assert [c[0] for c in called] == ["trigger", "notify"]
    assert called[0][1] is called[1][1]
```

Note : le compte exact ajouté est de 6 tests de comportement (email, TOCTOU, bookmark sans config, run sans export_job_id) + 2 tests du sweep = 8 nouveaux tests au total.

- [ ] **Step 3: Run tests and verify coverage**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_report_jobs.py --cov=app.reports.jobs --cov-report=term-missing`
Expected (vérifié réellement en session) : `24 passed`, `Cover 95%`, `Missing 50-51, 109-114, 345, 428-431` (4 branches de double-échec résiduelles, profondes et rarement atteintes — jugées non prioritaires par rapport au gain 86%→95%, déjà largement au-dessus du seuil requis).

- [ ] **Step 4: Falsify one test**

Dans `core/app/reports/jobs.py`, ligne ~385 (`elif isinstance(channel, AlertChannelEmail):`), remplacer temporairement par `elif False:`.

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_report_jobs.py -k sends_email -v`
Expected: FAIL — `assert 0 == 1` (`send_email` n'est jamais appelé).

Restaurer : `git checkout -- core/app/reports/jobs.py`, relancer, `1 passed`.

- [ ] **Step 5: Create `core/tests/test_cdc_jobs.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Câblage de `run_compaction_cycle_task` — le wrapper périodique lui-même
n'était exercé par aucun test (compaction.py/storage.py le sont
séparément)."""

from app.cdc import jobs as cdc_jobs


def test_run_compaction_cycle_task_wires_env_and_report(monkeypatch, caplog):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_CDC_BUCKET", "custom-bucket")

    fake_client = object()
    make_s3_client_calls = []
    ensure_bucket_calls = []
    run_cycle_calls = []

    def fake_make_s3_client(*, endpoint_url, access_key, secret_key):
        make_s3_client_calls.append((endpoint_url, access_key, secret_key))
        return fake_client

    def fake_ensure_cdc_bucket(client, bucket):
        ensure_bucket_calls.append((client, bucket))

    def fake_run_compaction_cycle(client, *, bucket):
        run_cycle_calls.append((client, bucket))
        return cdc_jobs.compaction.CompactionReport(
            partitions_scanned=3, partitions_compacted=2, files_removed=5, partitions_failed=1
        )

    monkeypatch.setattr(cdc_jobs.storage, "make_s3_client", fake_make_s3_client)
    monkeypatch.setattr(cdc_jobs.storage, "ensure_cdc_bucket", fake_ensure_cdc_bucket)
    monkeypatch.setattr(cdc_jobs.compaction, "run_compaction_cycle", fake_run_compaction_cycle)

    with caplog.at_level("INFO"):
        cdc_jobs.run_compaction_cycle_task(timestamp=0)

    assert make_s3_client_calls == [("http://minio:9000", "ak", "sk")]
    assert ensure_bucket_calls == [(fake_client, "custom-bucket")]
    assert run_cycle_calls == [(fake_client, "custom-bucket")]
    assert "3 partitions scanned, 2 compacted, 5 files removed, 1 failed" in caplog.text


def test_run_compaction_cycle_task_defaults_bucket_when_unset(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.delenv("S3_CDC_BUCKET", raising=False)

    monkeypatch.setattr(cdc_jobs.storage, "make_s3_client", lambda **_: object())
    seen_bucket = {}
    monkeypatch.setattr(
        cdc_jobs.storage,
        "ensure_cdc_bucket",
        lambda client, bucket: seen_bucket.setdefault("b", bucket),
    )
    monkeypatch.setattr(
        cdc_jobs.compaction,
        "run_compaction_cycle",
        lambda client, *, bucket: cdc_jobs.compaction.CompactionReport(0, 0, 0, 0),
    )

    cdc_jobs.run_compaction_cycle_task(timestamp=0)
    assert seen_bucket["b"] == "geostudio-cdc"
```

- [ ] **Step 6: Run tests and verify (no DB needed)**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_cdc_jobs.py -v`
Expected (vérifié réellement en session): `2 passed`.

- [ ] **Step 7: Falsify one test**

Dans `core/app/cdc/jobs.py`, remplacer temporairement `os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")` par `os.environ.get("S3_CDC_BUCKET", "wrong-default")`.

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_cdc_jobs.py -k defaults_bucket -v`
Expected: FAIL — `assert 'wrong-default' == 'geostudio-cdc'`.

Restaurer : `git checkout -- core/app/cdc/jobs.py`, relancer, `1 passed`.

- [ ] **Step 8: Create `shell/src/builder/report/ReportScheduleEditor.test.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import type { ReportSchedulePayload } from "../../api/types";
import { ReportScheduleEditor } from "./ReportScheduleEditor";

const BASE: ReportSchedulePayload = {
  bookmarkItemId: "bm-1",
  refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
  channels: [{ kind: "webhook", url: "" }],
};

describe("ReportScheduleEditor", () => {
  test("shows the targeted view label", () => {
    render(<ReportScheduleEditor value={BASE} onChange={vi.fn()} bookmarkLabel="Weekly view" />);
    expect(screen.getByText("Weekly view")).toBeInTheDocument();
  });

  test("edits the webhook url when the channel is a webhook", async () => {
    const onChange = vi.fn();
    render(<ReportScheduleEditor value={BASE} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.type(screen.getByLabelText("URL du webhook"), "h");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "webhook", url: "h" }],
    });
  });

  test("switching the channel to email shows recipient and smtp secret fields", async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ReportScheduleEditor value={BASE} onChange={onChange} bookmarkLabel="v" />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Canal"), "email");
    expect(onChange).toHaveBeenLastCalledWith({
      ...BASE,
      channels: [{ kind: "email", to: "", smtpSecretName: "" }],
    });

    const emailValue: ReportSchedulePayload = {
      ...BASE,
      channels: [{ kind: "email", to: "", smtpSecretName: "" }],
    };
    rerender(<ReportScheduleEditor value={emailValue} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.type(screen.getByLabelText("Destinataire"), "a");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "email", to: "a", smtpSecretName: "" }],
    });

    await userEvent.type(screen.getByLabelText("Secret SMTP"), "s");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "email", to: "", smtpSecretName: "s" }],
    });
  });

  test("switching back to webhook resets the channel to an empty url", async () => {
    const onChange = vi.fn();
    const emailValue: ReportSchedulePayload = {
      ...BASE,
      channels: [{ kind: "email", to: "a", smtpSecretName: "s" }],
    };
    render(<ReportScheduleEditor value={emailValue} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.selectOptions(screen.getByLabelText("Canal"), "webhook");
    expect(onChange).toHaveBeenLastCalledWith({
      ...emailValue,
      channels: [{ kind: "webhook", url: "" }],
    });
  });

  test("forwards the refresh policy through the embedded PipelineScheduleEditor", async () => {
    const onChange = vi.fn();
    render(<ReportScheduleEditor value={BASE} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.click(screen.getByLabelText("Planification automatique"));
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      refreshPolicy: { enabled: false, cron: "0 8 * * MON" },
    });
  });
});
```

Note : le `?? { enabled: false, cron: "0 8 * * MON" }` de la ligne 91 (repli si `PipelineScheduleEditor` appelle `onChange(null)`) et le repli `channel?.kind ?? "webhook"` de la ligne 37 restent non couverts (branches à 80 %) — le type de `PipelineScheduleEditor.onChange` autorise `null`, mais son implémentation actuelle ne l'émet jamais dans aucun chemin d'UI réel ; forcer un test dessus exigerait de court-circuiter le composant enfant, jugé disproportionné pour 2 branches défensives. Documenté, pas corrigé.

- [ ] **Step 9: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/report/ReportScheduleEditor.test.tsx --coverage --coverage.include='src/builder/report/ReportScheduleEditor.tsx'`
Expected (vérifié réellement en session) : `5 passed`, `Lines 100%` (9/9), `Branches 80%` (8/10).

- [ ] **Step 10: Falsify one test**

Dans `shell/src/builder/report/ReportScheduleEditor.tsx`, ligne 39, remplacer temporairement `if (e.target.value === "webhook")` par `if (e.target.value === "webhookXX")`.

Run: `cd shell && npx vitest run src/builder/report/ReportScheduleEditor.test.tsx -t "resets the channel"`
Expected: FAIL.

Restaurer : `git checkout -- shell/src/builder/report/ReportScheduleEditor.tsx`, relancer, `1 passed`.

- [ ] **Step 11: Add 3 tests to `shell/src/pages/ReportEditPage.test.tsx`**

D'abord, ajouter l'import en tête de fichier (après la ligne `import { act, render, screen, waitFor } from "@testing-library/react";`) :

```tsx
import userEvent from "@testing-library/user-event";
```

Puis, à la fin du fichier :

```tsx
test("create mode: Enregistrer crée le rapport puis navigue vers sa page d'édition", async () => {
  const createReportScheduleItem = vi.fn().mockResolvedValue({ pk: "r-new" });
  renderPage(null, { createReportScheduleItem });
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(createReportScheduleItem).toHaveBeenCalledTimes(1));
  expect(createReportScheduleItem.mock.calls[0][0]).toMatchObject({
    owner: "alice",
    report: { bookmarkItemId: "bm-1" },
  });
});

test("persisted mode: Enregistrer sauvegarde le brouillon courant", async () => {
  const payload: ReportSchedulePayload = {
    bookmarkItemId: "bm-1",
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
  const saveReportScheduleConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("r-1", {
    getItem: vi.fn().mockResolvedValue(item),
    getReportScheduleConfig: () => Promise.resolve(payload),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
    saveReportScheduleConfig,
  });
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveReportScheduleConfig).toHaveBeenCalledWith("r-1", payload));
});

test("persisted mode: un échec de sauvegarde affiche le message d'erreur sans naviguer", async () => {
  const payload: ReportSchedulePayload = {
    bookmarkItemId: "bm-1",
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
  renderPage("r-1", {
    getItem: vi.fn().mockResolvedValue(item),
    getReportScheduleConfig: () => Promise.resolve(payload),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
    saveReportScheduleConfig: vi.fn().mockRejectedValue(new Error("network down")),
  });
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText("network down")).toBeInTheDocument();
});
```

Note : la ligne 154 (`onRestored={async () => setDraft(await client.getReportScheduleConfig(pk))}`, câblage à un clic « Restaurer » du `ConfigHistoryPanel`) reste non couverte — mécanisme générique déjà testé par ailleurs sur les pages jumelles (App/Map/Dataset/Pipeline), ce site précis n'est qu'un fil de câblage d'une ligne ; jugé disproportionné d'ajouter la fixture `listConfigRevisions`+bouton « Restaurer »+`window.confirm` pour cette seule ligne. Documenté, pas corrigé.

- [ ] **Step 12: Run tests and verify coverage**

Run: `cd shell && npx vitest run src/pages/ReportEditPage.test.tsx --coverage --coverage.include='src/pages/ReportEditPage.tsx'`
Expected (vérifié réellement en session) : `10 passed`, `Lines 96.42%` (27/28, seule la ligne 154 ci-dessus non couverte).

- [ ] **Step 13: Falsify one test**

Dans `shell/src/pages/ReportEditPage.tsx`, ligne 99, commenter temporairement `await saveReport.mutateAsync(draft);`.

Run: `cd shell && npx vitest run src/pages/ReportEditPage.test.tsx -t "Enregistrer sauvegarde le brouillon"`
Expected: FAIL (timeout, `saveReportScheduleConfig` jamais appelé).

Restaurer : `git checkout -- shell/src/pages/ReportEditPage.tsx`, relancer, `1 passed`.

- [ ] **Step 14: Full-suite sanity + commit**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_report_jobs.py tests/test_cdc_jobs.py -v` — `26 passed`.
Run: `cd shell && npx vitest run src/builder/report/ReportScheduleEditor.test.tsx src/pages/ReportEditPage.test.tsx` — `15 passed`.

```bash
git add core/tests/test_report_jobs.py core/tests/test_cdc_jobs.py \
  shell/src/builder/report/ReportScheduleEditor.test.tsx shell/src/pages/ReportEditPage.test.tsx
git commit -m "$(cat <<'EOF'
test: couvre le rapport PDF planifié (core+shell) et le câblage de compaction CDC

reports/jobs.py 86%->95% (dispatch email, filet TOCTOU config supprimée,
bookmark sans config, run sans export_job_id, sweep_report_schedules_task
lui-même en mode normal ET lecture seule — jamais appelé directement par
aucun test existant). cdc/jobs.py : nouveau fichier de test, le wrapper
périodique run_compaction_cycle_task n'était exercé par aucun test
(compaction.py/storage.py le sont séparément). ReportScheduleEditor.tsx :
nouveau fichier de test, 22%->100% de lignes (dispatch/édition webhook et
email, planification embarquée). ReportEditPage.tsx 64%->96% (création,
sauvegarde, échec de sauvegarde — aucun test existant ne cliquait
Enregistrer). pipelines/ops/schemas.py déjà à 100%, aucun travail requis.
configs/schemas.py/configs/routes.py délibérément hors périmètre (fichiers
massivement partagés, cf. note dans la tâche) — à revérifier sur la
couverture agrégée de la suite complète avant de conclure. Falsifié
(email/bucket par défaut/webhook reset/save — 4 comportements réels
temporairement cassés, échec confirmé, restauration). Aucune ligne de
production modifiée.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12 (dernière): généraliser le plancher CI à `priorite: "moyenne"` et clore le chantier

**Files:**
- Modify: `core/scripts/feature_health/scoring.py`
- Modify: `core/scripts/feature_health_cli.py`
- Modify: `core/scripts/feature_health_thresholds.json`
- Test: `core/tests/test_feature_health_scoring.py`
- Test: `core/tests/test_feature_health_cli.py`
- Modify: `docs/revue/bilan-fonctionnalites.html`, `docs/revue/bilan-fonctionnalites.md`,
  `docs/revue/historique-sante.jsonl` (régénérés, pas édités à la main)

**Interfaces:**
- Consomme : `Thresholds` (dataclass existante), `scoring.priority_rank`/`weighted_health`
  (inchangés), toutes les tâches précédentes de ce plan (elles doivent être fusionnées avant celle-ci
  — c'est la tâche de clôture).
- Produit : `Thresholds.floor_medium_priority: float` — consommé par `_check()`.

**Contexte vérifié** : `plancher_priorite_haute` est aujourd'hui la seule clé de seuil par priorité ;
`_check()` (`core/scripts/feature_health_cli.py:74-90`) filtre en dur sur
`row["feature"].priority == "haute"`. `_check()` lui-même n'a aucun test unitaire dédié à ce jour
(seul `--check-fresh` l'est, `test_feature_health_cli.py`) — vérifié par grep.

**IMPORTANT — cette tâche ne peut être exécutée qu'après TOUTES les tâches précédentes de ce plan**,
car son Step 4 lit la vraie valeur mesurée du plancher, qui dépend de leur effet cumulé.

- [ ] **Step 1: Write the failing tests**

Dans `core/tests/test_feature_health_scoring.py`, ajouter (à côté du test existant qui vérifie
`0 < thresholds.floor_high_priority <= 100`) :

```python
def test_thresholds_load_the_medium_priority_floor():
    thresholds = load_thresholds(REPO / "core/scripts/feature_health_thresholds.json")
    assert 0 < thresholds.floor_medium_priority <= thresholds.floor_high_priority
```

(vérifier l'import de `load_thresholds`/`REPO` déjà présents dans ce fichier — sinon les ajouter en
tête, `from scripts.feature_health.scoring import Thresholds, load_thresholds`.)

Dans `core/tests/test_feature_health_cli.py`, ajouter :

```python
def test_check_fails_a_medium_priority_feature_under_its_own_floor(capsys):
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="f1", health=85.0, priority="moyenne")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=96.0,
    )
    exit_code = feature_health_cli._check(rows, thresholds)
    assert exit_code == 1
    assert "f1 : santé 85.0 < plancher 90.0" in capsys.readouterr().err


def test_check_passes_a_medium_priority_feature_at_its_floor(capsys):
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="f1", health=90.0, priority="moyenne")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=40.0,
    )
    assert feature_health_cli._check(rows, thresholds) == 0


def test_check_exempts_a_named_medium_priority_exception(capsys):
    """`catalogue-mes-vues-signets` (spec §4.bis) reste durablement sous le
    plancher moyenne — sans cette exception nommée, --check échouerait pour
    toujours sur cette seule ligne, contrairement à l'intention documentée
    (exception assumée, pas une régression à corriger)."""
    from scripts.feature_health.scoring import Thresholds

    rows = [_row(identifier="catalogue-mes-vues-signets", health=82.6, priority="moyenne")]
    thresholds = Thresholds(
        weights={"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
        floor_high_priority=90.0,
        floor_medium_priority=90.0,
        floor_median=40.0,
        exceptions_medium_priority=frozenset({"catalogue-mes-vues-signets"}),
    )
    assert feature_health_cli._check(rows, thresholds) == 0
    assert capsys.readouterr().err == ""
```

(le `floor_median` du 2e et 3e test est mis à 40.0 pour isoler la propriété testée — une seule
ligne à 90.0/82.6 donnerait sinon une médiane hors d'un plancher réaliste ; garder ce raisonnement
en commentaire si un relecteur s'interroge.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_scoring.py -k medium_priority_floor tests/test_feature_health_cli.py -k medium_priority -v`
Expected: 4 FAILED — `TypeError: Thresholds.__init__() missing ... 'floor_medium_priority'` /
`load_thresholds()` lève `KeyError: 'plancher_priorite_moyenne'` / `TypeError:
Thresholds.__init__() got an unexpected keyword argument 'exceptions_medium_priority'`.

- [ ] **Step 3: Generalize `Thresholds` and `_check()`**

Dans `core/scripts/feature_health/scoring.py`, remplacer :

```python
@dataclasses.dataclass(frozen=True)
class Thresholds:
    weights: dict[str, float]
    floor_high_priority: float
    floor_median: float


def load_thresholds(path: pathlib.Path) -> Thresholds:
    document = json.loads(path.read_text(encoding="utf-8"))
    return Thresholds(
        weights=document["ponderations"],
        floor_high_priority=float(document["plancher_priorite_haute"]),
        floor_median=float(document["plancher_sante_mediane"]),
    )
```

par :

```python
@dataclasses.dataclass(frozen=True)
class Thresholds:
    weights: dict[str, float]
    floor_high_priority: float
    floor_median: float
    floor_medium_priority: float = 0.0
    exceptions_medium_priority: frozenset[str] = frozenset()


def load_thresholds(path: pathlib.Path) -> Thresholds:
    document = json.loads(path.read_text(encoding="utf-8"))
    return Thresholds(
        weights=document["ponderations"],
        floor_high_priority=float(document["plancher_priorite_haute"]),
        floor_median=float(document["plancher_sante_mediane"]),
        floor_medium_priority=float(document["plancher_priorite_moyenne"]),
        exceptions_medium_priority=frozenset(document.get("exceptions_priorite_moyenne", ())),
    )
```

(`floor_medium_priority`/`exceptions_medium_priority` gagnent un défaut sur le dataclass uniquement
pour ne pas casser un éventuel appelant positionnel existant — `load_thresholds`, seul appelant
réel du dépôt, les passe toujours explicitement.)

Dans `core/scripts/feature_health_cli.py`, remplacer :

```python
    failures = [
        f"{row['feature'].identifier} : santé {row['sante']:.1f} < plancher "
        f"{thresholds.floor_high_priority}"
        for row in rows
        if row["feature"].priority == "haute"
        and row["sante"] is not None
        and row["sante"] < thresholds.floor_high_priority
    ]
```

par :

```python
    floor_by_priority = {
        "haute": thresholds.floor_high_priority,
        "moyenne": thresholds.floor_medium_priority,
    }
    failures = [
        f"{row['feature'].identifier} : santé {row['sante']:.1f} < plancher {floor}"
        for row in rows
        if (floor := floor_by_priority.get(row["feature"].priority)) is not None
        and row["feature"].identifier not in thresholds.exceptions_medium_priority
        and row["sante"] is not None
        and row["sante"] < floor
    ]
```

- [ ] **Step 4: Merge every previous task, regenerate the bilan, read the real floor**

Une fois toutes les tâches précédentes de ce plan fusionnées sur la même branche :

Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write`

Lire `docs/revue/bilan-fonctionnalites.md`, section « Toutes les fonctionnalités » : filtrer les 33
lignes visées par ce plan (liste en §1 de la spec), confirmer qu'elles sont toutes ≥ 90.0
**sauf `catalogue-mes-vues-signets`** (exception documentée en spec §4.bis — Task 10 l'a
mesurée à 70.96 de tests, sous le seuil ~83.3 nécessaire ; c'est attendu, ne pas essayer de la
corriger ici). Si une AUTRE des 32 lignes n'est pas ≥ 90.0, ne PAS avancer ce plancher — retourner
à la tâche concernée. Une fois confirmé, calculer le minimum réel mesuré parmi TOUTES les
fonctionnalités `priorite: "moyenne"` **à l'exclusion de `catalogue-mes-vues-signets`** (pas
seulement les 33 visées — une fonctionnalité `moyenne` déjà ≥ 90 avant ce plan reste potentiellement
le nouveau plancher si elle est, par exemple, à 90.1).

Documenter dans `docs/revue/2026-09-04-backlog.md` (nouvelle entrée `REV-nnn`, numéro suivant
disponible) : « Mes vues (signets) » reste sous 90 (mesuré ~82-85 selon la valeur exacte lue),
exception assumée, non corrigée — même doctrine que `REV-176`.

- [ ] **Step 5: Set the measured floor**

Dans `core/scripts/feature_health_thresholds.json`, ajouter `"plancher_priorite_moyenne"` avec la
valeur réelle mesurée à l'étape précédente (jamais arrondie à la hausse — même doctrine que
`.coverage-threshold`), et `"exceptions_priorite_moyenne"` avec la seule exception nommée et
justifiée de ce plan :

```json
{
  "ponderations": {"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
  "plancher_priorite_haute": 90,
  "plancher_priorite_moyenne": <valeur mesurée, en excluant catalogue-mes-vues-signets>,
  "plancher_sante_mediane": 96,
  "exceptions_priorite_moyenne": ["catalogue-mes-vues-signets"]
}
```

- [ ] **Step 6: Run the full feature-health suite and the new tests**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_scoring.py tests/test_feature_health_cli.py -v`
Expected: tous les tests passent, y compris les 4 nouveaux (1 chargement + 3 sur `_check`, dont
l'exception nommée) avec des `Thresholds` construits explicitement (indépendants du fichier JSON
réel).

Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
Expected: code de sortie 0, aucun `ÉCHEC` affiché.

- [ ] **Step 7: Falsify the new gate**

Temporairement, remettre `plancher_priorite_moyenne` à une valeur supérieure à la santé mesurée
d'une des 33 fonctionnalités visées (par ex. `95` si l'une d'elles est mesurée à 92.0) :

Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
Expected: code de sortie 1, une ligne `ÉCHEC : <id> : santé 92.0 < plancher 95` sur stderr.

Restaurer la vraie valeur mesurée, relancer, code de sortie 0.

- [ ] **Step 8: Commit**

```bash
git add core/scripts/feature_health/scoring.py core/scripts/feature_health_cli.py \
  core/scripts/feature_health_thresholds.json core/tests/test_feature_health_scoring.py \
  core/tests/test_feature_health_cli.py docs/revue/bilan-fonctionnalites.html \
  docs/revue/bilan-fonctionnalites.md docs/revue/historique-sante.jsonl \
  docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
feat(core): généralise le plancher CI de santé à priorite: moyenne

32 des 33 fonctionnalités priorite: moyenne visées repassées au-dessus
de 90 par ce plan ; plancher_priorite_moyenne ajouté et fixé à la
valeur réellement mesurée (jamais arrondie à la hausse, exclusion de
catalogue-mes-vues-signets prise en compte) pour verrouiller le
résultat en CI, même doctrine que .coverage-threshold. Une exception
nommée (exceptions_priorite_moyenne) exempte catalogue-mes-vues-signets,
qui ne peut pas dépasser 90 sans couvrir des routes shell sans rapport
(spec §4.bis, nouvelle entrée backlog) — sans elle --check échouerait
indéfiniment sur cette seule ligne. Sans ce geste par ailleurs, --check
n'empêcherait aucune régression future de repasser une autre
fonctionnalité moyenne sous 90.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
