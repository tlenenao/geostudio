# SP-61 — Bilan déterministe de qualité des fonctionnalités — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec :** `docs/superpowers/specs/2026-09-06-bilan-qualite-deterministe-design.md`
(lire en entier avant la Tâche 1 — ce plan ne la recopie pas).

**Goal :** remplacer la matrice de fonctionnalités écrite à la main par une
commande rejouable qui calcule une **santé** (0-100) par fonctionnalité, la
croise avec une **priorité déclarée**, rend un bilan HTML + Markdown, et fait
**échouer la CI** dès qu'une surface livrée n'est pas inventoriée.

**Architecture :** un package Python sans dépendance nouvelle
(`core/scripts/feature_health/`) qui ne lit que des **fichiers** du dépôt —
jamais `app` importé, jamais de base de données : `core/openapi.json`,
l'AST de `core/app/**/routes.py` et `core/app/mcp/tools/*.py`,
`shell/src/shell/routes.tsx`, `core/coverage.xml`,
`shell/coverage/coverage-summary.json`, les deux documents de dette de
`docs/revue/`. Un inventaire déclaratif
(`docs/revue/inventaire-fonctionnalites.jsonl`) porte les fonctionnalités ; les
surfaces dérivées du code servent à **prouver qu'il est complet**, pas à le
construire.

**Tech Stack :** Python 3.12 (stdlib seule : `ast`, `json`, `re`, `pathlib`,
`xml.etree.ElementTree`, `dataclasses`), pytest, HTML/CSS/JS statique sans build.

## Global Constraints

- **Worktree dédié obligatoire** (spec §11) : ce plan ne s'exécute jamais dans
  `/home/lenen/projets/geostudio` directement. Créer le worktree via la skill
  `superpowers:using-git-worktrees` avant la Tâche 1 ; retour sur `dev` par
  fusion explicite après la revue finale de branche.
- **Aucune dépendance nouvelle.** `core/pyproject.toml` n'est pas modifié pour
  ajouter un paquet. Stdlib seule. Vérifiable : `git diff dev -- core/pyproject.toml`
  ne montre aucune ligne ajoutée dans `dependencies`.
- **Aucune surface produit ajoutée** : zéro route REST, zéro outil MCP, zéro
  route shell. Le diff de `core/openapi.json` et de
  `shell/src/api/generated/core-schema.d.ts` doit être **vide** à la fin du plan
  (piège n°1 de `CLAUDE.md` : diff vide *attendu* ici, et c'est ce qu'on vérifie).
- **Le générateur n'importe jamais `app`.** Il doit tourner sans `.env`, sans
  `CORE_SECRETS_MASTER_KEY`, sans Postgres. C'est ce qui le rend utilisable en CI
  dans un job qui n'a pas de base.
- **SPDX** : tout nouveau fichier `.py` commence par
  `# SPDX-License-Identifier: Apache-2.0`.
- **Langue** : identifiants et noms de fichiers en anglais ; docstrings,
  commentaires, clés du JSONL et sortie rendue en français (`CLAUDE.md`).
- `ruff` : `line-length = 100`, cible `py312`. Toutes les commandes de
  vérification se lancent depuis `core/` :
  `uv run ruff check . && uv run ruff format --check .`
- **Docstring de limites obligatoire** sur chaque résolveur AST ou heuristique
  textuelle, sur le patron de `core/tests/test_deployability.py::core_env_vars`
  (« Limites assumées, pas couvertes : … »). Un futur lecteur ne doit jamais
  sur-interpréter un résultat vert.
- **Falsification obligatoire** (piège n°10) : chaque filet ajouté est vérifié en
  injectant délibérément le défaut qu'il vise, en confirmant l'échec, puis en
  retirant l'injection. Les étapes « Run test to verify it fails » ci-dessous ne
  sont pas décoratives.

## Écarts vérifiés vis-à-vis de la spec (mesurés le 2026-09-06 à `1516a3a1`)

Quatre points ont été vérifiés dans le code pendant la rédaction de ce plan et
**corrigent ou complètent la spec**. Ils sont intégrés aux tâches ci-dessous ;
ils sont listés ici pour qu'aucun exécutant ne « rétablisse » le texte de la spec.

1. **`core/openapi.json` ne contient PAS toutes les routes REST.** Les 7 routeurs
   derrière un flag de capacité y sont **absents** — mesuré :
   `/v1/pipelines` 0 chemin, `/v1/exports` 0, `/v1/appexports` 0, `/v1/tileset3d` 0,
   `/v1/terrain3d` 0, `/v1/copilot` 0, `/v1/admin/tools` 0, parce que
   `scripts/export_openapi.py` appelle `create_app()` avec les flags à leur valeur
   par défaut (éteinte) et que `core/app/main.py:301-314` monte ces routeurs sous
   `if is_*_enabled():`. La spec §3.2 dit « route REST : présente dans
   `openapi.json` — y figurer *est* la preuve du montage » : c'est vrai pour les
   26 routeurs inconditionnels, faux pour les 7 autres. **L'index de routes est
   donc dérivé de l'AST** (Tâche 2), et `openapi.json` devient un **contre-témoin** :
   tout chemin d'`openapi.json` (sauf `/health`) doit exister dans l'index AST,
   sinon le résolveur est faux et le test échoue.
2. **Les gardes se résolvent en profondeur 2, pas 1.** Outre les appels directs
   dans le corps de la route (déjà acté par la spec §3.3), des routes délèguent à
   un helper du **même module** qui porte la garde :
   `core/app/collections/routes.py:181 get_readable_collection` appelle `can(...)`
   à la ligne 202. Une résolution en profondeur 1 noterait ces routes « sans
   garde » — un faux positif exactement du type que le piège n°11 décrit. La
   récursion s'arrête au même module (un helper importé d'un autre module n'est
   pas suivi) : limite à écrire dans la docstring.
3. **L'ancrage d'amorçage remesuré à `1516a3a1`** avec le parseur exact spécifié
   en Tâche 5 : **294 lignes sur 304** ont tous leurs chemins de preuve existants,
   **8** ont un chemin mort (7 × `core/app/mcp/tools.py`, découpé par SP-43 ;
   1 × `shell/src/pages/TasksComingSoonPage.tsx`, remplacé par `UsagePage` en
   SP-47), **2** n'ont aucun chemin parsable. La spec annonçait « une trentaine
   de lignes à reprendre » : le compte réel de lignes *cassées* est 10 ; le reste
   du travail manuel est le **rattachement des surfaces** (Tâche 5, Step 6).
4. **`docs/revue/2026-09-04-matrice-fonctionnalites.html` est déjà rapatrié et
   commité** (550 949 octets, commit `7aad5234`). La tâche de rapatriement
   annoncée par la spec §7.0 est **faite** — il n'y a rien à télécharger. C'est la
   référence de design de la Tâche 7, lisible dans le dépôt.

## File Structure

| Fichier | Responsabilité |
|---|---|
| `core/scripts/feature_health/__init__.py` | package vide (marqueur) |
| `core/scripts/feature_health/model.py` | `SubScore`, `Feature`, `load_inventory` |
| `core/scripts/feature_health/reachability.py` | sous-score *atteignabilité* (Tâche 1) |
| `core/scripts/feature_health/rest_surface.py` | index AST des routes REST + gardes → sous-score *garde* (Tâche 2) |
| `core/scripts/feature_health/mcp_surface.py` | index AST des outils MCP (Tâche 2) |
| `core/scripts/feature_health/coverage_facts.py` | sous-score *tests* (Tâche 3) |
| `core/scripts/feature_health/debt.py` | sous-score *dette ouverte* (Tâche 4) |
| `core/scripts/feature_health/quality.py` | reprise §5, sans note (Tâche 6) |
| `core/scripts/feature_health/scoring.py` | pondérations, santé, tri de priorisation (Tâche 6) |
| `core/scripts/feature_health/history.py` | journal append-only (Tâche 6) |
| `core/scripts/feature_health/render_md.py` | rendu Markdown (Tâche 7) |
| `core/scripts/feature_health/render_html.py` | rendu HTML (Tâche 7) |
| `core/scripts/feature_health/assets/bilan.css` | CSS repris **verbatim** de l'artefact SP-42 (Tâche 7) |
| `core/scripts/feature_health/assets/bilan-body.html` | squelette de corps, repris de l'artefact (Tâche 7) |
| `core/scripts/feature_health/assets/bilan.js` | JS du bilan (Tâche 7) |
| `core/scripts/feature_health_cli.py` | CLI `--check` / `--write` (Tâche 6) |
| `core/scripts/feature_health_thresholds.json` | pondérations + planchers (Tâche 6) |
| `core/scripts/bootstrap_feature_inventory.py` | migration ponctuelle SP-42 → inventaire (Tâche 5) |
| `docs/revue/inventaire-fonctionnalites.jsonl` | **source déclarative** (Tâche 5) |
| `docs/revue/historique-sante.jsonl` | journal append-only (Tâche 6) |
| `docs/revue/bilan-fonctionnalites.{html,md}` | rendus regénérés (Tâche 7) |
| `core/tests/test_feature_health_*.py` | tests unitaires par module (Tâches 1-4, 6-7) |
| `core/tests/test_feature_inventory.py` | **garde-fou CI** §6.1 + §6.2 (Tâches 5 et 6) |

---

### Task 1 : socle + sous-score `atteignabilité`

C'est le sous-score qui a déjà prouvé sa valeur avant d'exister (spec §3.2,
`/bookmarks`). Il se pose en premier, avec ses deux ancres de falsification
réelles, mesurées à `1516a3a1` par le prototype de rédaction de ce plan.

**Files:**
- Create: `core/scripts/feature_health/__init__.py`
- Create: `core/scripts/feature_health/model.py`
- Create: `core/scripts/feature_health/reachability.py`
- Test: `core/tests/test_feature_health_reachability.py`

**Interfaces:**
- Consumes: rien (première tâche).
- Produces :
  - `model.SubScore(value: float | None, evidence: dict[str, object])` —
    `value is None` = **non applicable** (aucune surface du type mesuré) ;
  - `model.Feature` (dataclass gelée) et
    `model.load_inventory(path: pathlib.Path) -> tuple[Feature, ...]` ;
  - `reachability.declared_shell_routes(repo: pathlib.Path) -> tuple[str, ...]` ;
  - `reachability.route_prefix(route_path: str) -> str` ;
  - `reachability.collect_shell_inbound(repo, routes) -> dict[str, tuple[str, ...]]` ;
  - `reachability.ReachabilityFacts(shell_routes, shell_inbound, rest_paths, mcp_tools)` ;
  - `reachability.collect_reachability_facts(repo, *, rest_paths: frozenset[str], mcp_tools: frozenset[str]) -> ReachabilityFacts` ;
  - `reachability.score_reachability(feature: Feature, facts: ReachabilityFacts) -> SubScore`.
  - **Convention d'identifiant de surface REST, valable dans tout le plan :**
    `"<MÉTHODE> <chemin openapi>"`, ex. `"GET /v1/collections/{collection_id}"`.
    Un outil MCP est identifié par son nom de fonction nu, ex. `"query_features"`.
    Une route shell par son littéral de `routes.tsx`, ex. `"/apps/:pk/edit"`.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `core/tests/test_feature_health_reachability.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Sous-score « atteignabilité » (SP-61, spec §3.2).

Ces tests s'exécutent contre le **dépôt réel**, comme
`core/tests/test_deployability.py` : c'est la seule façon de vérifier qu'un
calcul d'atteignabilité dit la vérité sur ce dépôt-ci. Deux ancres de
falsification sont des faits mesurés, pas des fixtures — si l'une d'elles
change, c'est le dépôt qui a bougé et il faut relire, pas le test qu'il faut
assouplir."""

import json
import pathlib

import pytest

from scripts.feature_health.model import Feature, load_inventory
from scripts.feature_health.reachability import (
    ReachabilityFacts,
    collect_reachability_facts,
    collect_shell_inbound,
    declared_shell_routes,
    route_prefix,
    score_reachability,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1",
        domain="Test",
        name="fonctionnalité de test",
        proofs=("shell/src/pages/CatalogPage.tsx",),
        rest=(),
        mcp=(),
        shell=(),
        public=(),
        priority="moyenne",
        priority_source="amorcage-sp42",
        raw={},
    )
    base.update(overrides)
    return Feature(**base)


def test_declared_shell_routes_lists_every_route_of_routes_tsx():
    routes = declared_shell_routes(REPO)
    assert len(routes) == 28
    assert "/bookmarks" in routes
    assert "/public/datasets/:collectionId" in routes


@pytest.mark.parametrize(
    "route,expected",
    [
        ("/apps/:pk/edit", "/apps"),
        ("/reports/new", "/reports/new"),
        ("/apps/:pk/:pageId?", "/apps"),
        ("/", "/"),
    ],
)
def test_route_prefix_cuts_at_the_first_parameter(route, expected):
    assert route_prefix(route) == expected


def test_bookmarks_has_no_inbound_link():
    """GAP-80. Un utilisateur peut créer un signet (`useCreateBookmark`,
    `pages/AppRuntimePage.tsx`) et n'a ensuite aucun moyen de le retrouver."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert inbound["/bookmarks"] == ()


def test_sql_lab_has_no_inbound_link():
    """Même classe que GAP-80, trouvée en écrivant ce plan : la barre de
    domaines pointe `analytics` vers `/?type=bookmark`
    (`shell/src/shell/chrome/domainRoutes.ts:21`) et plus vers `/analytics/sql`.
    Les seules occurrences du littéral sont un commentaire, des tests, et
    l'URL REST `${coreUrl}/analytics/sql` — jamais un lien."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert inbound["/analytics/sql"] == ()


def test_admin_collections_has_an_inbound_link():
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert "shell/src/pages/AdminExtensionsPage.tsx" in inbound["/admin/collections"]


def test_rest_url_built_by_interpolation_is_not_counted_as_an_inbound_link():
    """`fetch(`${coreUrl}/analytics/sql`)` (api/domains/exportsIngestion.ts)
    est une URL d'API, pas un lien de navigation : le littéral n'est pas
    précédé d'un guillemet ouvrant, donc la règle ne le compte pas."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    assert "shell/src/api/domains/exportsIngestion.ts" not in inbound["/analytics/sql"]


def test_i18n_catalog_is_never_an_inbound_link():
    """Le catalogue i18n contient des libellés, pas des liens."""
    inbound = collect_shell_inbound(REPO, declared_shell_routes(REPO))
    for files in inbound.values():
        assert not any(f.startswith("shell/src/i18n/") for f in files)


def test_score_is_zero_for_a_shell_surface_without_inbound_link():
    facts = collect_reachability_facts(REPO, rest_paths=frozenset(), mcp_tools=frozenset())
    score = score_reachability(_feature(shell=("/bookmarks",)), facts)
    assert score.value == 0.0
    assert score.evidence["/bookmarks"] == "aucun lien entrant"


def test_score_is_hundred_for_a_shell_surface_with_an_inbound_link():
    facts = collect_reachability_facts(REPO, rest_paths=frozenset(), mcp_tools=frozenset())
    assert score_reachability(_feature(shell=("/admin/collections",)), facts).value == 100.0


def test_score_averages_every_declared_surface():
    facts = ReachabilityFacts(
        shell_routes=("/a", "/b"),
        shell_inbound={"/a": ("x.tsx",), "/b": ()},
        rest_paths=frozenset({"GET /v1/items"}),
        mcp_tools=frozenset({"query_features"}),
    )
    score = score_reachability(
        _feature(shell=("/a", "/b"), rest=("GET /v1/items",), mcp=("query_features",)),
        facts,
    )
    assert score.value == pytest.approx(75.0)


def test_score_is_not_applicable_without_any_technical_surface():
    """Undo/redo du builder, symbologie catégorielle : aucune route, aucun
    outil. Non applicable ≠ zéro — un 0 ici serait un mensonge pondéré."""
    facts = collect_reachability_facts(REPO, rest_paths=frozenset(), mcp_tools=frozenset())
    score = score_reachability(_feature(), facts)
    assert score.value is None


def test_load_inventory_rejects_a_duplicated_identifier(tmp_path):
    row = {
        "id": "dup",
        "domaine": "D",
        "fonctionnalite": "F",
        "preuve": ["core/app/items/routes.py"],
        "surfaces": {},
        "priorite": "basse",
    }
    path = tmp_path / "inv.jsonl"
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="identifiants dupliqués : dup"):
        load_inventory(path)


def test_load_inventory_rejects_a_missing_required_key(tmp_path):
    path = tmp_path / "inv.jsonl"
    path.write_text(json.dumps({"id": "x", "domaine": "D"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clés manquantes"):
        load_inventory(path)
```

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

Run (depuis `core/`) : `uv run pytest tests/test_feature_health_reachability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.feature_health'`

- [ ] **Step 3 : écrire `model.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Types partagés par les quatre sous-scores du bilan (SP-61, spec §3)."""

from __future__ import annotations

import dataclasses
import json
import pathlib


@dataclasses.dataclass(frozen=True)
class SubScore:
    """Un sous-score et la donnée qui l'a produit.

    `value is None` signifie **non applicable** — la fonctionnalité n'a aucune
    surface du type mesuré. La moyenne pondérée (scoring.py) renormalise sur
    les seuls sous-scores applicables : un widget builtin sans route REST ne
    doit pas être puni d'un 0 de « garde » qui n'a aucun sens pour lui.

    `evidence` est rendu tel quel dans le détail dépliable du bilan HTML : un
    score dont on ne peut pas voir la source est un score qu'on ne croit pas
    (spec §7.1)."""

    value: float | None
    evidence: dict[str, object]


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


REQUIRED_KEYS = ("id", "domaine", "fonctionnalite", "preuve", "surfaces", "priorite")
PRIORITIES = ("haute", "moyenne", "basse")


def load_inventory(path: pathlib.Path) -> tuple[Feature, ...]:
    features: list[Feature] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        missing = [key for key in REQUIRED_KEYS if key not in row]
        if missing:
            raise ValueError(f"{path}:{number} — clés manquantes : {', '.join(missing)}")
        if row["priorite"] not in PRIORITIES:
            raise ValueError(f"{path}:{number} — priorité inconnue : {row['priorite']!r}")
        surfaces = row["surfaces"] or {}
        features.append(
            Feature(
                identifier=row["id"],
                domain=row["domaine"],
                name=row["fonctionnalite"],
                proofs=tuple(row["preuve"]),
                rest=tuple(surfaces.get("rest", ())),
                mcp=tuple(surfaces.get("mcp", ())),
                shell=tuple(surfaces.get("shell", ())),
                public=tuple(row.get("publiques", ())),
                priority=row["priorite"],
                priority_source=row.get("priorite_source", "declaree"),
                raw=row,
            )
        )
    identifiers = [feature.identifier for feature in features]
    duplicates = sorted({i for i in identifiers if identifiers.count(i) > 1})
    if duplicates:
        raise ValueError(f"{path} — identifiants dupliqués : {', '.join(duplicates)}")
    return tuple(features)
```

- [ ] **Step 4 : écrire `reachability.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Sous-score « atteignabilité » (SP-61, spec §3.2).

Une surface montée mais qu'aucun lien n'atteint est morte pour l'utilisateur.
C'est ce calcul, fait à la main une fois par huit agents en SP-42, qui a
produit les 13 lignes `inerte` — et, refait mécaniquement, `/bookmarks`
(GAP-80) puis `/analytics/sql` qu'ils avaient tous deux manqués.

Règle : un lien entrant est une occurrence du **littéral de chemin précédée
d'un guillemet ouvrant** (`"`, `'` ou backtick) dans un fichier de
`shell/src`, hors `routes.tsx` (sa propre déclaration), hors fichiers de test,
hors `shell/src/i18n/` (des libellés, pas des liens). Exiger le guillemet
ouvrant est ce qui distingue un lien de navigation d'une URL d'API
interpolée (`fetch(`${coreUrl}/analytics/sql`)`) — vérifié sur les 28 chemins
réels.

Limites assumées, pas couvertes — un futur lecteur ne doit pas sur-interpréter
un vert :
- un lien construit par concaténation à partir d'un préfixe variable
  (``navigate(`${base}/bookmarks`)``) n'est pas vu : la règle exige le
  guillemet ouvrant immédiatement avant le chemin ;
- un lien présent mais rendu inatteignable par une garde de privilège n'est
  pas distingué d'un lien réellement offert ;
- inversement, une occurrence du littéral dans un commentaire ou une chaîne
  qui n'est pas un lien compte comme un lien entrant (faux négatif de
  détection d'inertie) ;
- la réciproque côté REST/MCP n'est pas mesurée ici : « montée » veut dire
  présente dans l'index de surfaces, pas « appelée par le shell »."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature, SubScore

ROUTES_TSX = "shell/src/shell/routes.tsx"
_ROUTE_PATH_RE = re.compile(r'path="([^"]+)"')
_EXCLUDED_INBOUND_PREFIXES = ("shell/src/i18n/",)
_TEST_MARKERS = (".test.", ".spec.", "__tests__/")


def declared_shell_routes(repo: pathlib.Path) -> tuple[str, ...]:
    """Les chemins déclarés par `routes.tsx`, dans l'ordre du fichier."""
    source = (repo / ROUTES_TSX).read_text(encoding="utf-8")
    return tuple(dict.fromkeys(_ROUTE_PATH_RE.findall(source)))


def route_prefix(route_path: str) -> str:
    """`/apps/:pk/edit` → `/apps` : la partie littérale, avant tout paramètre."""
    segments: list[str] = []
    for segment in route_path.split("/"):
        if segment.startswith(":") or segment.startswith("*"):
            break
        segments.append(segment)
    return "/".join(segments) or "/"


def _searchable_files(repo: pathlib.Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for path in sorted((repo / "shell/src").rglob("*.ts*")):
        relative = path.relative_to(repo).as_posix()
        if relative == ROUTES_TSX:
            continue
        if any(marker in relative for marker in _TEST_MARKERS):
            continue
        if any(relative.startswith(prefix) for prefix in _EXCLUDED_INBOUND_PREFIXES):
            continue
        files.append((relative, path.read_text(encoding="utf-8")))
    return files


def collect_shell_inbound(
    repo: pathlib.Path, routes: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    files = _searchable_files(repo)
    inbound: dict[str, tuple[str, ...]] = {}
    for route in routes:
        prefix = route_prefix(route)
        if prefix == "/":
            inbound[route] = ("<racine, atteignable par construction>",)
            continue
        needles = (f'"{prefix}', f"'{prefix}", f"`{prefix}")
        inbound[route] = tuple(
            relative
            for relative, blob in files
            if any(needle in blob for needle in needles)
        )
    return inbound


@dataclasses.dataclass(frozen=True)
class ReachabilityFacts:
    shell_routes: tuple[str, ...]
    shell_inbound: dict[str, tuple[str, ...]]
    rest_paths: frozenset[str]
    mcp_tools: frozenset[str]


def collect_reachability_facts(
    repo: pathlib.Path, *, rest_paths: frozenset[str], mcp_tools: frozenset[str]
) -> ReachabilityFacts:
    routes = declared_shell_routes(repo)
    return ReachabilityFacts(
        shell_routes=routes,
        shell_inbound=collect_shell_inbound(repo, routes),
        rest_paths=rest_paths,
        mcp_tools=mcp_tools,
    )


def score_reachability(feature: Feature, facts: ReachabilityFacts) -> SubScore:
    scores: list[float] = []
    evidence: dict[str, object] = {}
    for route in feature.shell:
        hits = facts.shell_inbound.get(route, ())
        scores.append(100.0 if hits else 0.0)
        evidence[route] = list(hits) if hits else "aucun lien entrant"
    for surface in feature.rest:
        mounted = surface in facts.rest_paths
        scores.append(100.0 if mounted else 0.0)
        evidence[surface] = "montée" if mounted else "absente de l'index des routes"
    for tool in feature.mcp:
        declared = tool in facts.mcp_tools
        scores.append(100.0 if declared else 0.0)
        evidence[tool] = "déclaré" if declared else "absent de l'index des outils MCP"
    if not scores:
        return SubScore(None, {"raison": "aucune surface technique déclarée"})
    return SubScore(sum(scores) / len(scores), evidence)
```

Créer aussi `core/scripts/feature_health/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
```

- [ ] **Step 5 : lancer les tests, vérifier qu'ils passent**

Run : `uv run pytest tests/test_feature_health_reachability.py -v`
Expected: PASS (13 tests).

- [ ] **Step 6 : falsifier la règle d'exclusion i18n**

Ajouter temporairement `shell/src/i18n/` à la liste des répertoires scannés (retirer
`_EXCLUDED_INBOUND_PREFIXES` de `_searchable_files`), relancer :
`uv run pytest tests/test_feature_health_reachability.py::test_i18n_catalog_is_never_an_inbound_link -v`
Expected: FAIL (`shell/src/i18n/catalog.fr.ts` remonte sur `/internal/kit-gallery`).
Restaurer l'exclusion, reconfirmer PASS. **Ne pas commiter l'injection.**

- [ ] **Step 7 : portes de qualité + commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . && cd ..
git add core/scripts/feature_health core/tests/test_feature_health_reachability.py
git commit -m "feat(revue): sous-score d'atteignabilite des surfaces (SP-61)"
```

---

### Task 2 : index AST des surfaces REST et MCP + sous-score `garde`

Le cœur technique du plan. Tout est mesuré : 33 modules définissent un
`APIRouter`, ils déclarent **147 routes**, dont **121** figurent dans
`openapi.json` (122 opérations moins `/health`) et **26** sont derrière un flag
de capacité. Résolution des gardes en profondeur 2 : **86 routes gardées**
(dont 31 uniquement grâce à la profondeur 2), 36 authentifiées sans garde
d'autorisation, 8 en authentification optionnelle, **17 sans rien** — et ces 17
sont exactement les routes publiques par conception.

**Files:**
- Create: `core/scripts/feature_health/rest_surface.py`
- Create: `core/scripts/feature_health/mcp_surface.py`
- Test: `core/tests/test_feature_health_rest_surface.py`
- Test: `core/tests/test_feature_health_mcp_surface.py`

**Interfaces:**
- Consumes: `model.SubScore`, `model.Feature` (Tâche 1).
- Produces :
  - `rest_surface.RouteFact(method, path, module, function, guards: frozenset[str], auth: str, flag: str | None)`
    où `auth ∈ {"required", "optional", "none"}` ;
  - `rest_surface.index_rest_routes(repo) -> tuple[RouteFact, ...]` ;
  - `rest_surface.surface_id(fact) -> str` (`"GET /v1/items"`) ;
  - `rest_surface.rest_surface_ids(routes) -> frozenset[str]` (consommé par
    `collect_reachability_facts(rest_paths=…)` de la Tâche 1) ;
  - `rest_surface.score_guard(feature, routes) -> SubScore` ;
  - `mcp_surface.index_mcp_tools(repo) -> tuple[str, ...]` (27 noms).

- [ ] **Step 1 : écrire les tests d'index REST qui échouent**

Créer `core/tests/test_feature_health_rest_surface.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Index AST des routes REST et sous-score « garde » (SP-61, spec §3.3).

Le contre-témoin `openapi.json` est la propriété centrale de ce fichier : si le
résolveur compose mal un chemin, un chemin d'`openapi.json` cesse d'être
retrouvé et le test échoue bruyamment. C'est ce qui rend croyable un index
dérivé de l'AST plutôt que du framework lui-même."""

import json
import pathlib

from scripts.feature_health.model import Feature
from scripts.feature_health.rest_surface import (
    RouteFact,
    index_rest_routes,
    rest_surface_ids,
    score_guard,
    surface_id,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _openapi_operations() -> set[tuple[str, str]]:
    document = json.loads((REPO / "core/openapi.json").read_text(encoding="utf-8"))
    return {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    }


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1",
        domain="Test",
        name="fonctionnalité de test",
        proofs=(),
        rest=(),
        mcp=(),
        shell=(),
        public=(),
        priority="moyenne",
        priority_source="declaree",
        raw={},
    )
    base.update(overrides)
    return Feature(**base)


def test_index_finds_every_declared_route():
    assert len(index_rest_routes(REPO)) == 147


def test_every_openapi_operation_is_resolved_by_the_index():
    """Contre-témoin. `/health` est déclaré par `@app.get` dans `main.py`,
    hors routeur et hors versionnement (SP-57b) : seule exception admise."""
    indexed = {(fact.method, fact.path) for fact in index_rest_routes(REPO)}
    unresolved = sorted(
        operation for operation in _openapi_operations()
        if operation not in indexed and operation[1] != "/health"
    )
    assert unresolved == []


def test_flagged_routes_are_indexed_although_absent_from_openapi():
    """`scripts/export_openapi.py` appelle `create_app()` flags éteints : les 7
    routeurs conditionnels de `main.py` ne figurent pas dans `openapi.json`.
    Un inventaire qui n'aurait dérivé ses surfaces que d'`openapi.json`
    ignorerait 26 routes réelles — dont tout le domaine Automatisation."""
    indexed = {(fact.method, fact.path) for fact in index_rest_routes(REPO)}
    flagged = sorted(indexed - _openapi_operations())
    assert len(flagged) == 26
    assert ("GET", "/v1/pipelines/{item_id}/runs") in flagged


def test_router_prefix_is_composed_with_the_v1_prefix():
    facts = {fact.path for fact in index_rest_routes(REPO)}
    assert "/v1/dcat/catalog" in facts
    assert "/v1/compliance/purges/{purge_id}" in facts


def test_capability_flag_is_resolved_from_main():
    by_module = {fact.module: fact.flag for fact in index_rest_routes(REPO)}
    assert by_module["app/pipelines/routes.py"] == "is_etl_enabled"
    assert by_module["app/collections/routes.py"] is None


def test_guard_called_directly_in_the_route_body_is_found():
    fact = next(
        f for f in index_rest_routes(REPO)
        if (f.method, f.path) == ("POST", "/v1/collections")
    )
    assert "require_privilege" in fact.guards


def test_guard_reached_through_a_same_module_helper_is_found():
    """`GET /v1/configs/{config_id}` → `get_config` → `_require_access`
    (`configs/routes.py:57`) → `can()`. Une résolution en profondeur 1
    classerait cette route « sans garde » — faux positif du type que le piège
    n°11 de CLAUDE.md décrit."""
    fact = next(
        f for f in index_rest_routes(REPO)
        if (f.method, f.path) == ("GET", "/v1/configs/{config_id}")
    )
    assert "can" in fact.guards


def test_public_by_design_routes_carry_no_guard():
    unguarded = {
        f.function for f in index_rest_routes(REPO) if not f.guards and f.auth == "none"
    }
    assert {"public_sitemap", "public_robots", "get_public_item", "conformance"} <= unguarded
    assert len(unguarded) == 17


def test_surface_id_is_method_space_path():
    fact = RouteFact(
        method="GET", path="/v1/items", module="app/items/routes.py",
        function="list_items", guards=frozenset(), auth="required", flag=None,
    )
    assert surface_id(fact) == "GET /v1/items"


def test_rest_surface_ids_feeds_the_reachability_facts():
    ids = rest_surface_ids(index_rest_routes(REPO))
    assert "GET /v1/items" in ids
    assert len(ids) == 147


def _fact(function, guards, auth):
    return RouteFact(
        method="GET", path=f"/v1/{function}", module="app/x/routes.py",
        function=function, guards=frozenset(guards), auth=auth, flag=None,
    )


def test_guard_score_is_hundred_with_an_authorization_guard():
    routes = (_fact("guarded", {"require_privilege"}, "required"),)
    assert score_guard(_feature(rest=("GET /v1/guarded",)), routes).value == 100.0


def test_guard_score_is_fifty_with_authentication_but_no_authorization():
    routes = (_fact("authed", set(), "required"),)
    assert score_guard(_feature(rest=("GET /v1/authed",)), routes).value == 50.0


def test_guard_score_is_zero_when_nothing_guards_an_undeclared_route():
    routes = (_fact("open", set(), "none"),)
    assert score_guard(_feature(rest=("GET /v1/open",)), routes).value == 0.0


def test_a_route_declared_public_by_design_is_not_penalised():
    routes = (_fact("open", set(), "none"),)
    feature = _feature(rest=("GET /v1/open",), public=("GET /v1/open",))
    score = score_guard(feature, routes)
    assert score.value == 100.0
    assert score.evidence["GET /v1/open"] == "publique par conception (déclarée)"


def test_guard_score_is_not_applicable_without_rest_surface():
    assert score_guard(_feature(shell=("/bookmarks",)), ()).value is None
```

- [ ] **Step 2 : lancer, vérifier l'échec**

Run : `uv run pytest tests/test_feature_health_rest_surface.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.feature_health.rest_surface'`

- [ ] **Step 3 : écrire `rest_surface.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Index AST des routes REST du cœur, et sous-score « garde » (SP-61, spec §3.3).

Pourquoi l'AST plutôt qu'`openapi.json` : (1) `openapi.json` est produit par
`create_app()` avec les flags de capacité **éteints**, donc les 7 routeurs
conditionnels de `main.py` (pipelines, export, appexport, tileset3d, terrain3d,
copilot, admin_tools) n'y figurent pas — 26 routes réelles, tout le domaine
Automatisation compris ; (2) les gardes d'autorisation de ce dépôt ne sont pas
des dépendances FastAPI, elles sont appelées dans le **corps** de la fonction de
route, donc invisibles de toute lecture de signature.

`openapi.json` reste le **contre-témoin** : tout chemin qu'il déclare (sauf
`/health`) doit être retrouvé par cet index, sinon la composition de préfixes
est fausse (test dédié).

Limites assumées, pas couvertes — un futur lecteur ne doit pas sur-interpréter
un vert :
- la résolution de garde s'arrête au **même module** : un helper importé d'un
  autre module et qui porterait la garde n'est pas suivi (aucun cas réel à
  `1516a3a1`, mais rien ne l'empêche d'apparaître) ;
- profondeur 2 exactement : route → helper → garde. Une chaîne plus longue
  n'est pas suivie ;
- une garde présente mais inopérante (mauvais privilège, condition toujours
  vraie) compte comme une garde : ce sous-score mesure la **présence** d'un
  point de contrôle, jamais sa justesse ;
- un chemin construit dynamiquement (`@router.get(SOME_CONSTANT)`) n'est pas
  vu ; le contre-témoin `openapi.json` le ferait échouer si le cas apparaissait
  sur un routeur non flaggé."""

from __future__ import annotations

import ast
import dataclasses
import pathlib

from scripts.feature_health.model import Feature, SubScore

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
V1_PREFIX = "/v1"
GUARD_NAMES = frozenset(
    {
        "require_privilege",
        "require_any_privilege",
        "has_privilege",
        "can",
        "rls_scope",
        "assert_egress_allowed",
    }
)
AUTH_REQUIRED = "get_current_user"
AUTH_OPTIONAL = "get_current_user_optional"


@dataclasses.dataclass(frozen=True)
class RouteFact:
    method: str
    path: str
    module: str
    function: str
    guards: frozenset[str]
    auth: str  # "required" | "optional" | "none"
    flag: str | None


def surface_id(fact: RouteFact) -> str:
    return f"{fact.method} {fact.path}"


def rest_surface_ids(routes: tuple[RouteFact, ...]) -> frozenset[str]:
    return frozenset(surface_id(fact) for fact in routes)


def _router_modules(repo: pathlib.Path) -> list[pathlib.Path]:
    """Tout module de `core/app` qui construit un `APIRouter`, sauf `main.py`.

    Un glob sur `routes.py` en manquerait deux, mesurés : `app/features/tiles.py`
    (la route `.mvt`) et `app/schemas_routes.py`."""
    modules = []
    for path in sorted((repo / "core/app").rglob("*.py")):
        if path.name == "main.py":
            continue
        if "APIRouter(" in path.read_text(encoding="utf-8"):
            modules.append(path)
    return modules


def _router_prefix(tree: ast.Module) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "router":
            continue
        if isinstance(node.value, ast.Call):
            for keyword in node.value.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                    return str(keyword.value.value)
    return ""


def _route_decorators(node: ast.AST) -> list[ast.Call]:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return []
    found = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "router"
            and func.attr in HTTP_METHODS
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            found.append(decorator)
    return found


def _called_names(node: ast.AST) -> set[str]:
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _depends_names(node: ast.AST) -> set[str]:
    """Les fonctions passées à `Depends(...)` — elles ne sont pas *appelées*
    dans le corps, seules `Depends` l'est."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id != "Depends":
                continue
            for argument in child.args:
                if isinstance(argument, ast.Name):
                    names.add(argument.id)
                elif isinstance(argument, ast.Attribute):
                    names.add(argument.attr)
    return names


def _capability_flags(repo: pathlib.Path) -> dict[str, str]:
    """`{"pipelines_routes": "is_etl_enabled", …}` depuis les `if is_*_enabled():`
    de `create_app()`, plus la table d'alias d'import
    (`from app.pipelines import routes as pipelines_routes`) pour retomber sur
    un chemin de module."""
    main = repo / "core/app/main.py"
    tree = ast.parse(main.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for name in node.names:
                if name.asname:
                    aliases[name.asname] = f"{node.module}.{name.name}".replace(".", "/") + ".py"
    flags: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Call):
            continue
        test = node.test.func
        flag = test.id if isinstance(test, ast.Name) else getattr(test, "attr", None)
        if not flag:
            continue
        for called in ast.walk(node):
            if not isinstance(called, ast.Call):
                continue
            func = called.func
            if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
                continue
            for argument in called.args:
                if isinstance(argument, ast.Attribute) and isinstance(argument.value, ast.Name):
                    module = aliases.get(argument.value.id)
                    if module:
                        flags[module] = flag
    return flags


def index_rest_routes(repo: pathlib.Path) -> tuple[RouteFact, ...]:
    flags = _capability_flags(repo)
    facts: list[RouteFact] = []
    for path in _router_modules(repo):
        module = path.relative_to(repo / "core").as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = _router_prefix(tree)
        local_functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for node in ast.walk(tree):
            for decorator in _route_decorators(node):
                called = _called_names(node)
                dependencies = _depends_names(node)
                guards = called & GUARD_NAMES
                for name in called | dependencies:
                    helper = local_functions.get(name)
                    if helper is not None and helper is not node:
                        guards |= _called_names(helper) & GUARD_NAMES
                if AUTH_REQUIRED in dependencies:
                    auth = "required"
                elif AUTH_OPTIONAL in dependencies:
                    auth = "optional"
                else:
                    auth = "none"
                facts.append(
                    RouteFact(
                        method=decorator.func.attr.upper(),
                        path=V1_PREFIX + prefix + decorator.args[0].value,
                        module=module,
                        function=node.name,
                        guards=frozenset(guards),
                        auth=auth,
                        flag=flags.get(module),
                    )
                )
    return tuple(facts)


def score_guard(feature: Feature, routes: tuple[RouteFact, ...]) -> SubScore:
    by_id = {surface_id(fact): fact for fact in routes}
    scores: list[float] = []
    evidence: dict[str, object] = {}
    for surface in feature.rest:
        if surface in feature.public:
            scores.append(100.0)
            evidence[surface] = "publique par conception (déclarée)"
            continue
        fact = by_id.get(surface)
        if fact is None:
            scores.append(0.0)
            evidence[surface] = "route introuvable dans l'index"
        elif fact.guards:
            scores.append(100.0)
            evidence[surface] = sorted(fact.guards)
        elif fact.auth in ("required", "optional"):
            scores.append(50.0)
            evidence[surface] = "authentification seule, aucune garde d'autorisation"
        else:
            scores.append(0.0)
            evidence[surface] = "ni authentification ni garde, non déclarée publique"
    if not scores:
        return SubScore(None, {"raison": "aucune surface REST déclarée"})
    return SubScore(sum(scores) / len(scores), evidence)
```

- [ ] **Step 4 : lancer, vérifier que tout passe**

Run : `uv run pytest tests/test_feature_health_rest_surface.py -v`
Expected: PASS (16 tests).

- [ ] **Step 5 : falsifier la résolution en profondeur 2**

Remplacer temporairement, dans `index_rest_routes`, la boucle de résolution des
helpers par `pass` (garder seulement `guards = called & GUARD_NAMES`), relancer :
`uv run pytest tests/test_feature_health_rest_surface.py -v`
Expected: FAIL sur `test_guard_reached_through_a_same_module_helper_is_found`
et sur `test_public_by_design_routes_carry_no_guard` (les routes non gardées
passent de 17 à 48). Restaurer, reconfirmer PASS.

- [ ] **Step 6 : écrire le test d'index MCP qui échoue**

Créer `core/tests/test_feature_health_mcp_surface.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Index AST des outils MCP (SP-61, spec §3.2)."""

import pathlib

from scripts.feature_health.mcp_surface import index_mcp_tools

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_index_finds_every_declared_tool():
    tools = index_mcp_tools(REPO)
    assert len(tools) == 27
    assert "query_features" in tools
    assert "search_collections" in tools  # SP-54


def test_index_is_sorted_and_free_of_duplicates():
    tools = index_mcp_tools(REPO)
    assert list(tools) == sorted(set(tools))


def test_index_ignores_the_schema_resource():
    """`@server.resource("schema://app-config")` (mcp/tools/__init__.py) n'est
    pas un outil : la ressource est inventoriée comme surface `autre`."""
    assert "app_config_schema" not in index_mcp_tools(REPO)
```

- [ ] **Step 7 : lancer, vérifier l'échec, écrire `mcp_surface.py`, revérifier**

Run : `uv run pytest tests/test_feature_health_mcp_surface.py -v` → FAIL (import).

```python
# SPDX-License-Identifier: Apache-2.0
"""Index AST des outils MCP (SP-61, spec §3.2).

Les 27 outils sont déclarés par `@server.tool()` sur une fonction imbriquée
dans la fonction d'enregistrement de chaque module de `core/app/mcp/tools/`.
`@server.resource(...)` (1 occurrence) n'est pas un outil et n'est pas indexé.

Limite assumée : un outil enregistré autrement qu'avec ce décorateur (appel
programmatique à `server.add_tool`) ne serait pas vu — aucun cas à `1516a3a1`."""

from __future__ import annotations

import ast
import pathlib


def index_mcp_tools(repo: pathlib.Path) -> tuple[str, ...]:
    names: set[str] = set()
    for path in sorted((repo / "core/app/mcp").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "tool"
                ):
                    names.add(node.name)
    return tuple(sorted(names))
```

Run : `uv run pytest tests/test_feature_health_mcp_surface.py -v` → PASS (3 tests).

- [ ] **Step 8 : portes de qualité + commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . && cd ..
git add core/scripts/feature_health core/tests/test_feature_health_rest_surface.py \
        core/tests/test_feature_health_mcp_surface.py
git commit -m "feat(revue): index AST des surfaces REST/MCP et sous-score de garde (SP-61)"
```

---

### Task 3 : sous-score `tests`

Trois familles de preuve, trois sources — mesurées : `core/coverage.xml` porte
**274** entrées de fichier dont les `filename` sont relatifs à **`core/app/`**
(pas à `core/` : piège vérifié, spec §3.1) ; `shell/coverage/coverage-summary.json`
porte **290** clés en chemins **absolus** (donc à relativiser sur le segment
`shell/`, jamais sur la racine du dépôt courant — le fichier peut avoir été
produit dans un autre worktree) ; les lignes d'infrastructure n'ont pas de
couverture et sont mesurées par les règles de `core/tests/test_deployability.py`
(46 tests, 10 constantes de chemin).

**Files:**
- Create: `core/scripts/feature_health/coverage_facts.py`
- Test: `core/tests/test_feature_health_coverage.py`

**Interfaces:**
- Consumes: `model.SubScore`, `model.Feature`.
- Produces :
  - `coverage_facts.CoverageFacts(core_rates, shell_rates, e2e_specs, deployability_rules)` ;
  - `coverage_facts.collect_coverage_facts(repo) -> CoverageFacts` (lève
    `FileNotFoundError` si un artefact de couverture manque — jamais de
    dégradation silencieuse à 0) ;
  - `coverage_facts.score_tests(feature, facts) -> SubScore`.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `core/tests/test_feature_health_coverage.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Sous-score « tests » (SP-61, spec §3.1)."""

import pathlib

import pytest

from scripts.feature_health.coverage_facts import (
    CoverageFacts,
    collect_coverage_facts,
    core_line_rates,
    deployability_rules,
    score_tests,
    shell_line_rates,
)
from scripts.feature_health.model import Feature

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1", domain="Test", name="f", proofs=(), rest=(), mcp=(),
        shell=(), public=(), priority="moyenne", priority_source="declaree", raw={},
    )
    base.update(overrides)
    return Feature(**base)


def test_core_rates_are_keyed_on_repo_relative_paths():
    """Piège de la spec §3.1 : `filename` est relatif à `core/app/`. Avec le
    mauvais préfixe, le rattachement tombe à 165/304 au lieu de 256/304."""
    rates = core_line_rates(REPO)
    assert "core/app/collections/routes.py" in rates
    assert 0.0 <= rates["core/app/collections/routes.py"] <= 100.0


def test_shell_rates_are_relativised_on_the_shell_segment():
    """Les clés du JSON sont des chemins absolus produits par une autre
    machine (ou un autre worktree) : on relativise sur le segment `shell/`,
    jamais en comparant à la racine du dépôt courant."""
    rates = shell_line_rates(REPO)
    assert "shell/src/pages/CatalogPage.tsx" in rates
    assert "total" not in rates


def test_deployability_rules_map_infra_paths_to_test_functions():
    rules = deployability_rules(REPO)
    assert len(rules["docker-compose.yml"]) >= 10
    assert "deploy/backup/restore.sh" in rules


def test_score_uses_the_line_rate_of_each_proof_file():
    facts = CoverageFacts(
        core_rates={"core/app/items/routes.py": 94.2},
        shell_rates={},
        e2e_specs={},
        deployability_rules={},
    )
    score = score_tests(_feature(proofs=("core/app/items/routes.py",)), facts)
    assert score.value == pytest.approx(94.2)


def test_score_of_an_infra_proof_is_binary_on_deployability_rules():
    facts = CoverageFacts(
        core_rates={}, shell_rates={}, e2e_specs={},
        deployability_rules={"docker-compose.yml": ("test_a", "test_b")},
    )
    covered = score_tests(_feature(proofs=("docker-compose.yml",)), facts)
    uncovered = score_tests(_feature(proofs=("deploy/postgis/Dockerfile",)), facts)
    assert covered.value == 100.0
    assert uncovered.value == 0.0


def test_a_shell_surface_adds_an_e2e_component_to_the_average():
    """Une fonctionnalité visible sans spec E2E ne peut pas obtenir 100 :
    « chaque feature visible a sa spec E2E Playwright » (CLAUDE.md)."""
    facts = CoverageFacts(
        core_rates={}, shell_rates={"shell/src/pages/BookmarksPage.tsx": 100.0},
        e2e_specs={"/bookmarks": ()}, deployability_rules={},
    )
    score = score_tests(
        _feature(proofs=("shell/src/pages/BookmarksPage.tsx",), shell=("/bookmarks",)),
        facts,
    )
    assert score.value == pytest.approx(50.0)
    assert score.evidence["e2e"] == "aucune spec E2E ne cite /bookmarks"


def test_score_is_not_applicable_without_any_attachable_proof():
    facts = CoverageFacts({}, {}, {}, {})
    assert score_tests(_feature(proofs=("docs/vision/quelque-chose.md",)), facts).value is None


def test_collect_refuses_to_degrade_silently_when_an_artefact_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="coverage.xml"):
        collect_coverage_facts(tmp_path)
```

- [ ] **Step 2 : lancer, vérifier l'échec**

Run : `uv run pytest tests/test_feature_health_coverage.py -v` → FAIL (import).

- [ ] **Step 3 : écrire `coverage_facts.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Sous-score « tests » (SP-61, spec §3.1).

Trois familles de preuve, trois sources :
- `core/app/**` → `core/coverage.xml`. Ses `filename` sont relatifs à
  `core/app/` (`<sources><source>…/core/app</source></sources>`), pas à
  `core/` : le mauvais préfixe fait chuter le rattachement de 256/304 à
  165/304 (mesuré, spec §3.1).
- `shell/src/**` → `shell/coverage/coverage-summary.json`, dont les clés sont
  des chemins **absolus** de la machine qui a produit le fichier. On
  relativise sur le segment `shell/`, jamais par rapport à la racine du dépôt
  courant : le worktree d'exécution n'est presque jamais celui de la mesure.
- infrastructure (`docker-compose*.yml`, `deploy/`, `.github/`, `scripts/`) →
  aucune couverture possible ; le signal naturel est l'existence d'une règle de
  `core/tests/test_deployability.py` qui touche ce fichier.

Limites assumées, pas couvertes :
- la couverture de ligne d'un fichier n'est pas la couverture d'une
  fonctionnalité : un fichier partagé par cinq fonctionnalités leur donne à
  toutes le même chiffre ;
- le rattachement d'une règle de déployabilité passe par les **constantes de
  module** (`BASE = REPO / "docker-compose.yml"`) référencées nommément dans
  le corps d'un `test_*` ; une règle qui reçoit son chemin par un helper
  (`services(path)`) n'est comptée que si la constante apparaît malgré tout
  dans le test — le compte est donc un plancher, pas un total ;
- « une spec E2E cite ce chemin de route » ne prouve pas qu'elle exerce la
  fonctionnalité, seulement qu'elle y navigue."""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import xml.etree.ElementTree as ET

from scripts.feature_health.model import Feature, SubScore

_INFRA_PREFIXES = ("docker-compose", "deploy/", ".github/", "scripts/", ".env")


def core_line_rates(repo: pathlib.Path) -> dict[str, float]:
    path = repo / "core/coverage.xml"
    if not path.exists():
        raise FileNotFoundError(f"{path} — lancer `uv run pytest --cov=app --cov-report=xml`")
    root = ET.parse(path).getroot()
    return {
        "core/app/" + element.attrib["filename"]: float(element.attrib["line-rate"]) * 100
        for element in root.findall(".//class")
    }


def shell_line_rates(repo: pathlib.Path) -> dict[str, float]:
    path = repo / "shell/coverage/coverage-summary.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} — lancer `npm run test -- --coverage` dans shell/")
    document = json.loads(path.read_text(encoding="utf-8"))
    rates: dict[str, float] = {}
    for key, summary in document.items():
        if key == "total" or "/shell/" not in key:
            continue
        relative = "shell/" + key.split("/shell/", 1)[1]
        rates[relative] = float(summary["lines"]["pct"])
    return rates


def e2e_specs(repo: pathlib.Path) -> dict[str, tuple[str, ...]]:
    """Route shell → specs E2E qui citent son littéral de chemin."""
    from scripts.feature_health.reachability import declared_shell_routes, route_prefix

    specs = [
        (path.relative_to(repo).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted((repo / "shell/e2e").glob("*.spec.ts"))
    ]
    found: dict[str, tuple[str, ...]] = {}
    for route in declared_shell_routes(repo):
        prefix = route_prefix(route)
        needles = (f'"{prefix}', f"'{prefix}", f"`{prefix}")
        found[route] = tuple(
            name for name, blob in specs if any(needle in blob for needle in needles)
        )
    return found


def deployability_rules(repo: pathlib.Path) -> dict[str, tuple[str, ...]]:
    path = repo / "core/tests/test_deployability.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.BinOp):
            continue
        if (
            isinstance(value.op, ast.Div)
            and isinstance(value.left, ast.Name)
            and value.left.id == "REPO"
            and isinstance(value.right, ast.Constant)
        ):
            candidate = str(value.right.value)
            if (repo / candidate).is_file():
                constants[target.id] = candidate
    rules: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
        for constant, file_path in constants.items():
            if constant in names:
                rules.setdefault(file_path, []).append(node.name)
    return {key: tuple(value) for key, value in rules.items()}


@dataclasses.dataclass(frozen=True)
class CoverageFacts:
    core_rates: dict[str, float]
    shell_rates: dict[str, float]
    e2e_specs: dict[str, tuple[str, ...]]
    deployability_rules: dict[str, tuple[str, ...]]


def collect_coverage_facts(repo: pathlib.Path) -> CoverageFacts:
    return CoverageFacts(
        core_rates=core_line_rates(repo),
        shell_rates=shell_line_rates(repo),
        e2e_specs=e2e_specs(repo),
        deployability_rules=deployability_rules(repo),
    )


def score_tests(feature: Feature, facts: CoverageFacts) -> SubScore:
    scores: list[float] = []
    evidence: dict[str, object] = {}
    for proof in feature.proofs:
        if proof in facts.core_rates:
            rate = facts.core_rates[proof]
        elif proof in facts.shell_rates:
            rate = facts.shell_rates[proof]
        elif proof.startswith(_INFRA_PREFIXES):
            covering = facts.deployability_rules.get(proof, ())
            rate = 100.0 if covering else 0.0
            evidence[proof] = list(covering) or "aucune règle de test_deployability.py"
            scores.append(rate)
            continue
        else:
            evidence[proof] = "hors périmètre de mesure (ni couverture ni règle)"
            continue
        evidence[proof] = f"{rate:.1f} % de lignes couvertes"
        scores.append(rate)
    if feature.shell:
        citing = tuple(
            spec for route in feature.shell for spec in facts.e2e_specs.get(route, ())
        )
        scores.append(100.0 if citing else 0.0)
        evidence["e2e"] = (
            sorted(set(citing))
            if citing
            else "aucune spec E2E ne cite " + ", ".join(feature.shell)
        )
    if not scores:
        return SubScore(None, {"raison": "aucune preuve mesurable", **evidence})
    return SubScore(sum(scores) / len(scores), evidence)
```

- [ ] **Step 4 : lancer, vérifier que tout passe**

Run : `uv run pytest tests/test_feature_health_coverage.py -v`
Expected: PASS (8 tests). Prérequis : `core/coverage.xml` et
`shell/coverage/coverage-summary.json` présents dans le worktree — les copier
depuis le checkout principal si besoin, ou lancer les deux suites une fois.

- [ ] **Step 5 : falsifier le préfixe de `coverage.xml`**

Remplacer `"core/app/" + element.attrib["filename"]` par
`"core/" + element.attrib["filename"]`, relancer :
Expected: FAIL sur `test_core_rates_are_keyed_on_repo_relative_paths`.
Restaurer, reconfirmer PASS.

- [ ] **Step 6 : portes de qualité + commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . && cd ..
git add core/scripts/feature_health/coverage_facts.py core/tests/test_feature_health_coverage.py
git commit -m "feat(revue): sous-score de tests depuis les artefacts de couverture (SP-61)"
```

---

### Task 4 : sous-score `dette ouverte`

Consomme les deux documents déjà tenus à jour à chaque clôture de SP
(obligation `CLAUDE.md` du 2026-09-06) sans les dupliquer : le tableau d'état
des `GAP-nn` de `docs/revue/2026-09-04-analyse-gaps.md` et les 178 sections
`### REV-nnn` de `docs/revue/2026-09-04-backlog.md` (dont **81 + 73 + 5 = 159
ouvertes**, mesuré sur la ligne `- **État :**`).

**Files:**
- Create: `core/scripts/feature_health/debt.py`
- Test: `core/tests/test_feature_health_debt.py`

**Interfaces:**
- Consumes: `model.SubScore`, `model.Feature`.
- Produces :
  - `debt.DebtItem(identifier, severity, paths: tuple[str, ...])` ;
  - `debt.open_gaps(repo) -> tuple[DebtItem, ...]` ;
  - `debt.open_revs(repo) -> tuple[DebtItem, ...]` ;
  - `debt.collect_debt_facts(repo) -> tuple[DebtItem, ...]` ;
  - `debt.score_debt(feature, items) -> SubScore`.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `core/tests/test_feature_health_debt.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Sous-score « dette ouverte » (SP-61, spec §3.4)."""

import pathlib

import pytest

from scripts.feature_health.debt import (
    DebtItem,
    collect_debt_facts,
    open_gaps,
    open_revs,
    score_debt,
)
from scripts.feature_health.model import Feature

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1", domain="Test", name="f", proofs=(), rest=(), mcp=(),
        shell=(), public=(), priority="moyenne", priority_source="declaree", raw={},
    )
    base.update(overrides)
    return Feature(**base)


def test_open_gaps_excludes_closed_ones():
    identifiers = {item.identifier for item in open_gaps(REPO)}
    assert "GAP-08" in identifiers      # « Géocodage BAN non traité »
    assert "GAP-05" not in identifiers  # fermé par SP-55
    assert "GAP-44" not in identifiers  # fermé par SP-53


def test_open_gaps_expands_a_range_row():
    """`| GAP-16 à GAP-23 | Ouvert | … |` compte pour huit entrées."""
    identifiers = {item.identifier for item in open_gaps(REPO)}
    assert {"GAP-16", "GAP-20", "GAP-23"} <= identifiers


def test_open_revs_reads_the_etat_line():
    items = {item.identifier: item for item in open_revs(REPO)}
    assert "REV-001" in items
    assert items["REV-001"].severity == "critical"
    assert "REV-165" not in items or items["REV-165"].severity in {
        "critical", "important", "minor", "observation", "inconnu"
    }


def test_open_revs_carries_the_proof_paths():
    items = {item.identifier: item for item in open_revs(REPO)}
    assert "core/app/pipelines/jobs.py" in items["REV-001"].paths


def test_score_is_hundred_without_any_open_item():
    assert score_debt(_feature(proofs=("core/app/items/routes.py",)), ()).value == 100.0


def test_score_drops_by_severity():
    items = (
        DebtItem("REV-900", "critical", ("core/app/x.py",)),
        DebtItem("REV-901", "minor", ("core/app/x.py",)),
    )
    score = score_debt(_feature(proofs=("core/app/x.py",)), items)
    assert score.value == pytest.approx(50.0)  # 100 - 40 - 10
    assert score.evidence["REV-900"] == "critical"


def test_score_never_goes_below_zero():
    items = tuple(DebtItem(f"REV-{n}", "critical", ("core/app/x.py",)) for n in range(5))
    assert score_debt(_feature(proofs=("core/app/x.py",)), items).value == 0.0


def test_an_item_that_cites_another_file_does_not_count():
    items = (DebtItem("REV-900", "critical", ("core/app/other.py",)),)
    assert score_debt(_feature(proofs=("core/app/x.py",)), items).value == 100.0


def test_collect_returns_both_families():
    identifiers = {item.identifier for item in collect_debt_facts(REPO)}
    assert any(i.startswith("GAP-") for i in identifiers)
    assert any(i.startswith("REV-") for i in identifiers)
```

- [ ] **Step 2 : lancer, vérifier l'échec**

Run : `uv run pytest tests/test_feature_health_debt.py -v` → FAIL (import).

- [ ] **Step 3 : écrire `debt.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Sous-score « dette ouverte » (SP-61, spec §3.4).

Consomme les deux documents que `CLAUDE.md` oblige à mettre à jour à chaque
clôture de SP, sans les dupliquer :
- `docs/revue/2026-09-04-analyse-gaps.md` — le tableau d'état, dont chaque
  ligne est `| GAP-nn | Ouvert \\| **Fermé** \\| **Partiel** | commentaire |`.
  Une ligne peut couvrir une plage (`| GAP-16 à GAP-23 | Ouvert | … |`), qui est
  dépliée. `**Partiel**` compte comme ouvert.
- `docs/revue/2026-09-04-backlog.md` — une section `### REV-nnn — <sévérité> — …`
  par entrée, avec une ligne `- **État :** ouvert…` et une ligne
  `- **Preuve :** `chemin:lignes ; chemin:lignes``.

Pondération volontairement grossière (spec §6.2, « grossier, robuste ») :
critical −40, important −20, minor/observation −10, inconnu −10, plancher 0.
Les `GAP` n'exposent pas leur impact dans le tableau d'état (il vit dans les
tableaux de détail, à un autre format par référentiel) : ils comptent tous
pour −20. Simplification assumée plutôt qu'un parseur fragile de trois
tableaux différents.

Limites assumées : le rattachement se fait par **chemin de fichier cité dans
la preuve** ; une entrée dont la preuve ne nomme aucun fichier ne pénalise
aucune fonctionnalité, et une entrée qui cite un fichier partagé pénalise
toutes les fonctionnalités qui le citent."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature, SubScore

GAPS_DOC = "docs/revue/2026-09-04-analyse-gaps.md"
BACKLOG_DOC = "docs/revue/2026-09-04-backlog.md"

_GAP_ROW_RE = re.compile(
    r"^\|\s*GAP-(\d+)(?:\s*à\s*GAP-(\d+))?\s*\|\s*([^|]+?)\s*\|", re.MULTILINE
)
_REV_HEADING_RE = re.compile(r"^### (REV-\d+)\s*—\s*([^—\n]*)", re.MULTILINE)
_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}")
_SEVERITIES = ("critical", "important", "minor", "observation")
_PENALTY = {"critical": 40.0, "important": 20.0, "minor": 10.0, "observation": 10.0}
_DEFAULT_PENALTY = 20.0


@dataclasses.dataclass(frozen=True)
class DebtItem:
    identifier: str
    severity: str
    paths: tuple[str, ...]


def open_gaps(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    text = (repo / GAPS_DOC).read_text(encoding="utf-8")
    items: dict[str, DebtItem] = {}
    for match in _GAP_ROW_RE.finditer(text):
        status = match.group(3).lower()
        if "fermé" in status and "partiel" not in status:
            continue
        if "ouvert" not in status and "partiel" not in status:
            continue
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        line_end = text.find("\n", match.end())
        row = text[match.end() : line_end if line_end != -1 else None]
        paths = tuple(dict.fromkeys(_PATH_RE.findall(row)))
        for number in range(first, last + 1):
            identifier = f"GAP-{number:02d}"
            items.setdefault(identifier, DebtItem(identifier, "gap", paths))
    return tuple(items.values())


def open_revs(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    text = (repo / BACKLOG_DOC).read_text(encoding="utf-8")
    headings = list(_REV_HEADING_RE.finditer(text))
    items: list[DebtItem] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[match.end() : end]
        state = re.search(r"^- \*\*État :\*\*\s*(.+)$", body, re.MULTILINE)
        if state is None or not state.group(1).lower().startswith(("ouvert", "partiel")):
            continue
        label = match.group(2).strip().lower()
        severity = next((s for s in _SEVERITIES if s in label), "inconnu")
        proof = re.search(r"^- \*\*Preuve :\*\*\s*(.+)$", body, re.MULTILINE)
        paths = tuple(dict.fromkeys(_PATH_RE.findall(proof.group(1)))) if proof else ()
        items.append(DebtItem(match.group(1), severity, paths))
    return tuple(items)


def collect_debt_facts(repo: pathlib.Path) -> tuple[DebtItem, ...]:
    return open_gaps(repo) + open_revs(repo)


def score_debt(feature: Feature, items: tuple[DebtItem, ...]) -> SubScore:
    proofs = set(feature.proofs)
    value = 100.0
    evidence: dict[str, object] = {}
    for item in items:
        if not proofs.intersection(item.paths):
            continue
        value -= _PENALTY.get(item.severity, _DEFAULT_PENALTY)
        evidence[item.identifier] = item.severity
    if not evidence:
        evidence["raison"] = "aucune entrée GAP/REV ouverte ne cite ces fichiers"
    return SubScore(max(0.0, value), evidence)
```

- [ ] **Step 4 : lancer, vérifier que tout passe**

Run : `uv run pytest tests/test_feature_health_debt.py -v` → PASS (9 tests).

Si `test_open_gaps_excludes_closed_ones` échoue, **ne pas assouplir le test** :
le tableau d'état a changé de forme, ce qui est exactement ce que ce filet doit
signaler. Relire le tableau, ajuster le parseur, revérifier.

- [ ] **Step 5 : falsification**

Ajouter temporairement, à la fin du tableau d'état de
`docs/revue/2026-09-04-analyse-gaps.md`, la ligne
`| GAP-99 | Ouvert | ligne d'injection, à retirer | core/app/items/routes.py |`
puis relancer `test_open_gaps_excludes_closed_ones` avec un `assert "GAP-99" in identifiers`
temporaire. Expected: PASS, prouvant que le parseur lit bien ce tableau.
Retirer la ligne **et** l'assertion temporaire.

- [ ] **Step 6 : portes de qualité + commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . && cd ..
git add core/scripts/feature_health/debt.py core/tests/test_feature_health_debt.py
git commit -m "feat(revue): sous-score de dette ouverte depuis GAP/REV (SP-61)"
```

---

### Task 5 : inventaire amorcé + réconciliation + garde-fou §6.1

L'inventaire est **migré**, pas collecté : 304 lignes de
`.superpowers/sdd/sp42-matrice-notee.jsonl`. Mesures faites en rédigeant ce plan,
à `1516a3a1` — elles disent exactement combien de travail manuel reste :

| Mesure | Compte |
|---|---|
| lignes dont tous les chemins de preuve existent encore | **294 / 304** |
| lignes avec un chemin mort | **8** (7 × `core/app/mcp/tools.py`, découpé par SP-43 ; 1 × `shell/src/pages/TasksComingSoonPage.tsx`, remplacé par `UsagePage` en SP-47) |
| lignes sans chemin parsable | **2** |
| routes REST rattachées automatiquement (fichier de preuve = module de la route) | **141 / 147** |
| routes REST orphelines à rattacher à la main | **6** (compliance 3, usage 2, quotas 1 — domaines créés par SP-47/SP-58, postérieurs à la matrice) |
| outils MCP rattachés par mention nominative | **19 / 27** |
| outils MCP orphelins | **8** (`add_group_member`, `create_bookmark`, `create_dataset`, `create_group`, `get_app_config`, `list_groups`, `run_alert_rule`, `search_collections`) |

**Files:**
- Create: `core/scripts/bootstrap_feature_inventory.py`
- Create: `docs/revue/inventaire-fonctionnalites.jsonl` (produit, puis corrigé à la main)
- Create: `core/tests/test_feature_inventory.py`
- Test: `core/tests/test_bootstrap_feature_inventory.py`

**Interfaces:**
- Consumes: `model.load_inventory`, `rest_surface.index_rest_routes`/`surface_id`,
  `mcp_surface.index_mcp_tools`, `reachability.declared_shell_routes`.
- Produces : le fichier `docs/revue/inventaire-fonctionnalites.jsonl`, une ligne
  JSON par fonctionnalité, aux clés françaises :

```json
{"id": "administration-console-minio",
 "domaine": "Administration",
 "fonctionnalite": "Accéder à la console MinIO depuis la page d'infrastructure admin",
 "description": "Lien direct non gardé par le gate cookie",
 "preuve": ["shell/src/pages/AdminInfrastructurePage.tsx", "docker-compose.yml"],
 "surfaces": {"rest": [], "mcp": [], "shell": ["/admin/infrastructure"], "autre": []},
 "publiques": [],
 "priorite": "basse",
 "priorite_source": "amorcage-sp42",
 "note_sp42": "limite technique assumée : …",
 "note_sp42_date": "2026-09-04"}
```

- [ ] **Step 1 : écrire le test du script d'amorçage**

Créer `core/tests/test_bootstrap_feature_inventory.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Migration ponctuelle SP-42 → inventaire (SP-61, spec §8)."""

import json

import pytest

from scripts.bootstrap_feature_inventory import (
    bootstrap_priority,
    proof_paths,
    slug_for,
)


@pytest.mark.parametrize(
    "utility,expected",
    [(9, "haute"), (8, "haute"), (7, "moyenne"), (5, "moyenne"), (4, "basse"), (1, "basse")],
)
def test_bootstrap_priority_maps_the_sp42_utility_note(utility, expected):
    assert bootstrap_priority(utility) == expected


def test_proof_paths_keeps_the_path_and_drops_the_line_numbers():
    """L'ancrage par `chemin:ligne` ne tient pas deux jours (spec §8)."""
    raw = "shell/src/pages/AdminInfrastructurePage.tsx:70-79 ; docker-compose.yml:88-90"
    assert proof_paths(raw) == (
        "shell/src/pages/AdminInfrastructurePage.tsx",
        "docker-compose.yml",
    )


def test_slug_is_stable_and_ascii():
    assert slug_for("Administration", "Accéder à la console MinIO") == (
        "administration-acceder-a-la-console-minio"
    )


def test_slugs_are_deduplicated_by_suffix():
    from scripts.bootstrap_feature_inventory import unique_slugs

    assert unique_slugs(["a", "a", "b"]) == ["a", "a-2", "b"]


def test_generated_rows_load_back_through_the_inventory_loader(tmp_path):
    from scripts.bootstrap_feature_inventory import build_rows
    from scripts.feature_health.model import load_inventory

    source = tmp_path / "src.jsonl"
    source.write_text(
        json.dumps(
            {
                "domaine": "Catalogue",
                "fonctionnalite": "Lister les items",
                "description": "",
                "preuve": "core/app/items/routes.py:10-20",
                "note": "",
                "notes": {"utilite": 9},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "inv.jsonl"
    target.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in build_rows(source)) + "\n",
        encoding="utf-8",
    )
    features = load_inventory(target)
    assert features[0].identifier == "catalogue-lister-les-items"
    assert features[0].priority == "haute"
    assert features[0].priority_source == "amorcage-sp42"
```

- [ ] **Step 2 : lancer, vérifier l'échec, écrire le script, revérifier**

Run : `uv run pytest tests/test_bootstrap_feature_inventory.py -v` → FAIL (import).

Créer `core/scripts/bootstrap_feature_inventory.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Migration **ponctuelle** de la matrice SP-42 vers l'inventaire vivant
(SP-61, spec §8). Commité pour documenter la provenance des 304 lignes ; il
n'est pas rejoué en CI et ne doit plus jamais être relancé sur un inventaire
déjà corrigé à la main — il écraserait les corrections.

Ce qu'il migre : domaine, libellé, description, chemins de preuve (chemin nu,
sans `:ligne`), note qualitative datée, et la priorité **amorcée** depuis
`notes.utilite` (≥8 haute, 5-7 moyenne, ≤4 basse), marquée
`priorite_source: "amorcage-sp42"` — un point de départ, jamais une vérité.

Ce qu'il ne migre PAS : les états `livre`/`partiel`/`inerte`/`absent` du
2026-09-04, périmés par SP-43→SP-60. Ils sont **recalculés** par le générateur.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import unicodedata

_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
SOURCE = ".superpowers/sdd/sp42-matrice-notee.jsonl"
TARGET = "docs/revue/inventaire-fonctionnalites.jsonl"
SP42_DATE = "2026-09-04"


def proof_paths(raw: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_PATH_RE.findall(raw or "")))


def bootstrap_priority(utility: int | None) -> str:
    if utility is None:
        return "moyenne"
    if utility >= 8:
        return "haute"
    if utility >= 5:
        return "moyenne"
    return "basse"


def slug_for(domain: str, name: str) -> str:
    text = f"{domain} {name}"
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _SLUG_STRIP_RE.sub("-", ascii_text.lower()).strip("-")[:80]


def unique_slugs(slugs: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    output = []
    for slug in slugs:
        seen[slug] = seen.get(slug, 0) + 1
        output.append(slug if seen[slug] == 1 else f"{slug}-{seen[slug]}")
    return output


def build_rows(source: pathlib.Path) -> list[dict]:
    raw_rows = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    slugs = unique_slugs([slug_for(row["domaine"], row["fonctionnalite"]) for row in raw_rows])
    rows = []
    for slug, row in zip(slugs, raw_rows, strict=True):
        rows.append(
            {
                "id": slug,
                "domaine": row["domaine"],
                "fonctionnalite": row["fonctionnalite"],
                "description": row.get("description", ""),
                "preuve": list(proof_paths(row.get("preuve"))),
                "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []},
                "publiques": [],
                "priorite": bootstrap_priority((row.get("notes") or {}).get("utilite")),
                "priorite_source": "amorcage-sp42",
                "note_sp42": row.get("note", ""),
                "note_sp42_date": SP42_DATE,
            }
        )
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--force", action="store_true", help="écrase un inventaire existant")
    arguments = parser.parse_args(argv)
    target = arguments.repo / TARGET
    if target.exists() and not arguments.force:
        print(f"{target} existe déjà — refus d'écraser (utiliser --force).", file=sys.stderr)
        return 1
    rows = build_rows(arguments.repo / SOURCE)
    target.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} lignes écrites dans {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Run : `uv run pytest tests/test_bootstrap_feature_inventory.py -v` → PASS (8 tests).

- [ ] **Step 3 : générer l'inventaire**

```bash
cd core && uv run python scripts/bootstrap_feature_inventory.py --repo .. && cd ..
wc -l docs/revue/inventaire-fonctionnalites.jsonl   # attendu : 304
```

- [ ] **Step 4 : écrire le garde-fou §6.1 (il DOIT échouer à ce stade)**

Créer `core/tests/test_feature_inventory.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde-fou d'inventaire (SP-61, spec §6.1).

Le geste qu'on veut rendre impossible : livrer une surface sans la déclarer.
Sans ce test, l'inventaire repérit exactement comme la matrice SP-42 l'a fait —
17 SP pendant lesquels rien ne signalait sa péremption (piège n°12).

Ce fichier teste le **dépôt**, pas `core/app/` : même entorse assumée que
`core/tests/test_deployability.py`, et pour la même raison — `core/` est le
seul répertoire du dépôt qui possède un runner Python dans la CI."""

import pathlib

from scripts.feature_health.mcp_surface import index_mcp_tools
from scripts.feature_health.model import load_inventory
from scripts.feature_health.reachability import declared_shell_routes
from scripts.feature_health.rest_surface import index_rest_routes, surface_id

REPO = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = REPO / "docs/revue/inventaire-fonctionnalites.jsonl"


def _declared():
    features = load_inventory(INVENTORY)
    return (
        {surface for feature in features for surface in feature.rest},
        {tool for feature in features for tool in feature.mcp},
        {route for feature in features for route in feature.shell},
    )


def test_every_rest_route_is_claimed_by_an_inventory_entry():
    declared_rest, _, _ = _declared()
    missing = sorted(
        surface_id(fact) for fact in index_rest_routes(REPO)
        if surface_id(fact) not in declared_rest
    )
    assert missing == [], (
        "Routes REST non inventoriées — ajouter chacune à la ligne de "
        f"docs/revue/inventaire-fonctionnalites.jsonl qui la porte : {missing}"
    )


def test_every_mcp_tool_is_claimed_by_an_inventory_entry():
    _, declared_mcp, _ = _declared()
    missing = sorted(tool for tool in index_mcp_tools(REPO) if tool not in declared_mcp)
    assert missing == [], f"Outils MCP non inventoriés : {missing}"


def test_every_shell_route_is_claimed_by_an_inventory_entry():
    _, _, declared_shell = _declared()
    missing = sorted(
        route for route in declared_shell_routes(REPO) if route not in declared_shell
    )
    assert missing == [], f"Routes shell non inventoriées : {missing}"


def test_no_inventory_entry_claims_an_unknown_surface():
    """Le sens inverse : une surface déclarée mais retirée du code (route
    supprimée, outil renommé) doit être nettoyée, pas laissée à pourrir."""
    declared_rest, declared_mcp, declared_shell = _declared()
    known_rest = {surface_id(fact) for fact in index_rest_routes(REPO)}
    known_mcp = set(index_mcp_tools(REPO))
    known_shell = set(declared_shell_routes(REPO))
    unknown = sorted(
        (declared_rest - known_rest) | (declared_mcp - known_mcp) | (declared_shell - known_shell)
    )
    assert unknown == [], f"Surfaces déclarées mais absentes du code : {unknown}"


def test_every_proof_path_still_exists():
    """L'ancrage par chemin de fichier tient (294/304 mesuré à l'amorçage) —
    il ne tient que si on le vérifie."""
    dead = sorted(
        f"{feature.identifier} → {proof}"
        for feature in load_inventory(INVENTORY)
        for proof in feature.proofs
        if not (REPO / proof).exists()
    )
    assert dead == [], f"Chemins de preuve morts : {dead}"


def test_every_entry_has_at_least_one_proof():
    empty = sorted(
        feature.identifier for feature in load_inventory(INVENTORY) if not feature.proofs
    )
    assert empty == [], f"Entrées sans aucune preuve : {empty}"
```

Run : `uv run pytest tests/test_feature_inventory.py -v`
Expected: **FAIL** sur les 5 premiers tests — c'est l'état attendu : l'inventaire
vient d'être amorcé, aucune surface n'y est encore rattachée. Ce rouge est la
mesure exacte du travail du Step 5.

- [ ] **Step 5 : rattacher les surfaces automatiquement**

Ajouter au script d'amorçage une passe `--attach`, qui ré-écrit **seulement** le
champ `surfaces` de l'inventaire existant (donc rejouable après les corrections
manuelles sans les écraser) :

```python
_LAZY_RE = re.compile(r'const (\w+) = lazy\(\(\) =>\s*import\("([^"]+)"\)')
_ROUTE_ELEMENT_RE = re.compile(r'path="([^"]+)"[^>]*element=\{<(\w+)', re.DOTALL)


def _route_pages(repo: pathlib.Path) -> dict[str, str]:
    """Route shell -> fichier de page.

    `routes.tsx` déclare 23 pages en `lazy(() => import("../pages/X"))`
    (SP-60) et rend soit la page elle-même, soit un composant enveloppe défini
    dans le même fichier ; on résout les deux en cherchant, dans le corps de
    l'enveloppe, un nom de composant paresseux."""
    source = (repo / "shell/src/shell/routes.tsx").read_text(encoding="utf-8")
    lazy = dict(_LAZY_RE.findall(source))
    pages: dict[str, str] = {}
    for route, element in _ROUTE_ELEMENT_RE.findall(source):
        target = lazy.get(element)
        if target is None:
            parts = source.split(f"function {element}", 1)
            if len(parts) == 2:
                target = next((lazy[name] for name in lazy if name in parts[1][:400]), None)
        if target:
            pages[route] = "shell/src/" + target.removeprefix("../") + ".tsx"
    return pages


def attach_surfaces(repo: pathlib.Path, rows: list[dict]) -> dict[str, list[str]]:
    """Rattache chaque surface dérivée aux entrées qui citent déjà sa preuve.

    Sur-rattacher est volontaire : une route citée par cinq entrées est
    attachée aux cinq. Le garde-fou (§6.1) exige **au moins un** revendicateur ;
    l'affinage se fait à la main, entrée par entrée, au fil des SP. La valeur de
    retour est la liste des orphelines — la seule liste de travail manuel."""
    from scripts.feature_health.mcp_surface import index_mcp_tools
    from scripts.feature_health.reachability import declared_shell_routes
    from scripts.feature_health.rest_surface import index_rest_routes, surface_id

    text_of = {
        row["id"]: " ".join(
            [
                " ".join(row["preuve"]),
                row["fonctionnalite"],
                row["description"],
                row.get("note_sp42", ""),
            ]
        )
        for row in rows
    }
    for row in rows:
        row["surfaces"] = {"rest": [], "mcp": [], "shell": [], "autre": []}
    by_id = {row["id"]: row for row in rows}
    orphans: dict[str, list[str]] = {"rest": [], "mcp": [], "shell": []}

    for fact in index_rest_routes(repo):
        module = "core/" + fact.module
        claimants = [row for row in rows if module in row["preuve"]]
        if not claimants:
            orphans["rest"].append(surface_id(fact))
        for row in claimants:
            row["surfaces"]["rest"].append(surface_id(fact))

    for tool in index_mcp_tools(repo):
        claimants = [identifier for identifier, text in text_of.items() if tool in text]
        if not claimants:
            orphans["mcp"].append(tool)
        for identifier in claimants:
            by_id[identifier]["surfaces"]["mcp"].append(tool)

    pages = _route_pages(repo)
    for route in declared_shell_routes(repo):
        page = pages.get(route)
        claimants = [row for row in rows if page and page in row["preuve"]]
        if not claimants:
            orphans["shell"].append(route)
        for row in claimants:
            row["surfaces"]["shell"].append(route)

    for row in rows:
        for key in ("rest", "mcp", "shell"):
            row["surfaces"][key] = sorted(set(row["surfaces"][key]))
    return orphans
```

`main()` gagne `--attach` : recharge l'inventaire existant ligne à ligne (en
conservant l'ordre et tous les autres champs), appelle `attach_surfaces`,
réécrit le fichier, puis imprime les orphelines.

Comptes attendus (mesurés à `1516a3a1`) : **6** orphelines REST (compliance 3,
usage 2, quotas 1), **8** orphelins MCP, quelques routes shell. Le script sort
en code 0 même avec des orphelines : c'est un outil de préparation, pas un
garde-fou — le garde-fou, c'est le test.

```bash
cd core && uv run python scripts/bootstrap_feature_inventory.py --repo .. --attach && cd ..
uv run pytest tests/test_feature_inventory.py -v   # depuis core/
```

- [ ] **Step 6 : rattacher les orphelines à la main, jusqu'au vert**

Éditer `docs/revue/inventaire-fonctionnalites.jsonl` :

1. les **6 routes REST orphelines** (compliance/usage/quotas) : créer les
   entrées manquantes si aucune ligne SP-42 ne les décrit — ces domaines sont
   nés après la matrice (SP-47, SP-58) ;
2. les **8 outils MCP orphelins** : les rattacher à l'entrée de la
   fonctionnalité qu'ils exposent (`search_collections` → l'entrée « recherche
   de collections », etc.) ;
3. les **routes shell** restées orphelines après la passe automatique ;
4. les **10 lignes à chemin mort ou sans chemin** : `core/app/mcp/tools.py` →
   le module de `core/app/mcp/tools/` qui porte l'outil (SP-43) ;
   `TasksComingSoonPage.tsx` → `shell/src/pages/UsagePage.tsx` (SP-47) ;
5. déclarer dans `publiques` les surfaces publiques par conception. Les **17
   routes sans garde** mesurées en Tâche 2 sont la liste de départ ; deux
   d'entre elles ne sont pas « publiques » mais portent leur propre
   authentification hors vocabulaire de gardes —
   `trigger_pipeline_webhook_route` (jeton haché, SP-53) et
   `bootstrap_admin_tool_session` (jeton HMAC, SP-32) : les déclarer dans
   `publiques` avec le commentaire correspondant dans `description`, plutôt que
   de les laisser noter 0.

Reboucler jusqu'à `uv run pytest tests/test_feature_inventory.py -v` **vert**.

- [ ] **Step 7 : falsifier le garde-fou**

Retirer une surface d'une ligne de l'inventaire (par ex. `"GET /v1/items"`),
relancer : Expected FAIL avec le message qui nomme la route. Restaurer,
reconfirmer PASS. Puis ajouter une surface bidon (`"GET /v1/inexistante"`) :
Expected FAIL sur `test_no_inventory_entry_claims_an_unknown_surface`. Retirer.

- [ ] **Step 8 : commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . && cd ..
git add core/scripts/bootstrap_feature_inventory.py core/tests/test_bootstrap_feature_inventory.py \
        core/tests/test_feature_inventory.py docs/revue/inventaire-fonctionnalites.jsonl
git commit -m "feat(revue): inventaire de fonctionnalites amorce + garde-fou de reconciliation (SP-61)"
```

---

### Task 6 : santé, priorité, reprise qualité, journal, CLI, plancher §6.2

**Contrainte d'environnement à connaître avant de coder cette tâche** (vérifiée
dans `.github/workflows/ci.yml`) : le job `core` produit `coverage.xml` **à la
fin** de son propre `pytest`, et `shell/coverage/coverage-summary.json` est
produit par un **autre job, sur une autre machine**. Un test pytest ne peut donc
pas calculer la santé en CI. Conséquence, assumée et documentée :

- le garde-fou §6.1 (réconciliation, Tâche 5) vit dans **pytest** — il ne lit
  aucun artefact de couverture ;
- le plancher §6.2 vit dans le **CLI**, exécuté par un job dédié qui récupère
  les deux artefacts (Tâche 8) ;
- le test pytest du plancher existe quand même, mais **se skippe** proprement
  quand les artefacts manquent, avec une raison lisible. Un skip silencieux qui
  ferait croire à un vert est exactement le piège que ce plan combat.

**Files:**
- Create: `core/scripts/feature_health/quality.py`
- Create: `core/scripts/feature_health/scoring.py`
- Create: `core/scripts/feature_health/history.py`
- Create: `core/scripts/feature_health_thresholds.json`
- Create: `core/scripts/feature_health_cli.py`
- Modify: `core/tests/test_feature_inventory.py` (ajout du plancher §6.2)
- Test: `core/tests/test_feature_health_scoring.py`

**Interfaces:**
- Consumes: les quatre sous-scores (Tâches 1-4), `model.Feature`.
- Produces :
  - `quality.QualityFacts(mypy_strict_modules, layer_exemptions, eslint_disabled, typing_escapes)` ;
  - `quality.collect_quality_facts(repo) -> QualityFacts` ;
  - `quality.quality_for(feature, facts) -> dict[str, object]` (**des faits, jamais une note**) ;
  - `scoring.Thresholds(weights: dict[str, float], floor_high_priority: float, floor_median: float)` ;
  - `scoring.load_thresholds(path) -> Thresholds` ;
  - `scoring.weighted_health(subscores: dict[str, SubScore], weights) -> float | None` ;
  - `scoring.priority_rank(feature, health: float | None) -> float` ;
  - `feature_health_cli.compute(repo) -> tuple[list[dict], Thresholds]` — le seul
    point qui assemble les six modules ; chaque ligne est un `dict`
    `{"feature", "sante", "sous_scores", "qualite", "rang"}` (forme consommée
    telle quelle par les deux rendus de la Tâche 7 et par le plancher §6.2) ;
  - `history.append_snapshot(path, healths, *, commit, date)` et
    `history.last_snapshot(path) -> dict[str, float]`.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `core/tests/test_feature_health_scoring.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Santé pondérée, priorité, reprise qualité, journal (SP-61, spec §3-§5, §7.2)."""

import json
import pathlib

import pytest

from scripts.feature_health.history import append_snapshot, last_snapshot
from scripts.feature_health.model import Feature, SubScore
from scripts.feature_health.quality import collect_quality_facts, quality_for
from scripts.feature_health.scoring import (
    Thresholds,
    load_thresholds,
    priority_rank,
    weighted_health,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


def _feature(**overrides) -> Feature:
    base = dict(
        identifier="f1", domain="Test", name="f",
        proofs=("core/app/auth/routes.py",), rest=(), mcp=(), shell=(), public=(),
        priority="moyenne", priority_source="declaree", raw={},
    )
    base.update(overrides)
    return Feature(**base)


WEIGHTS = {"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20}


def test_weighted_health_is_the_weighted_mean_of_applicable_subscores():
    subscores = {
        "tests": SubScore(80.0, {}),
        "atteignabilite": SubScore(100.0, {}),
        "garde": SubScore(50.0, {}),
        "dette": SubScore(100.0, {}),
    }
    assert weighted_health(subscores, WEIGHTS) == pytest.approx(82.5)


def test_a_non_applicable_subscore_is_excluded_and_the_weights_renormalise():
    """Un widget builtin n'a ni route ni outil : lui coller 0 de « garde »
    serait un mensonge pondéré (spec §3)."""
    subscores = {
        "tests": SubScore(80.0, {}),
        "atteignabilite": SubScore(None, {}),
        "garde": SubScore(None, {}),
        "dette": SubScore(100.0, {}),
    }
    assert weighted_health(subscores, WEIGHTS) == pytest.approx(88.0)


def test_health_is_none_when_no_subscore_is_applicable():
    subscores = {name: SubScore(None, {}) for name in WEIGHTS}
    assert weighted_health(subscores, WEIGHTS) is None


def test_priority_rank_sorts_what_matters_most_and_goes_worst():
    """`priorité × (100 − santé)` — aucune moyenne des deux axes n'est
    jamais calculée (spec §4)."""
    assert priority_rank(_feature(priority="haute"), 40.0) == pytest.approx(180.0)
    assert priority_rank(_feature(priority="basse"), 40.0) == pytest.approx(60.0)
    assert priority_rank(_feature(priority="haute"), 100.0) == 0.0


def test_thresholds_are_loaded_from_the_versioned_json():
    thresholds = load_thresholds(REPO / "core/scripts/feature_health_thresholds.json")
    assert set(thresholds.weights) == {"tests", "atteignabilite", "garde", "dette"}
    assert sum(thresholds.weights.values()) == pytest.approx(1.0)
    assert 0 < thresholds.floor_high_priority <= 100
    assert 0 < thresholds.floor_median <= 100


def test_quality_facts_read_the_real_repository():
    facts = collect_quality_facts(REPO)
    assert "app/auth" in facts.mypy_strict_modules
    assert len(facts.mypy_strict_modules) == 6
    assert any("->" in exemption for exemption in facts.layer_exemptions)
    assert len(facts.eslint_disabled) == 10
    assert len(facts.typing_escapes) == 7


def test_quality_for_reports_facts_without_any_note():
    facts = collect_quality_facts(REPO)
    reported = quality_for(_feature(proofs=("core/app/auth/routes.py",)), facts)
    assert reported["typage_strict"] is True
    assert "note" not in reported
    assert "score" not in reported


def test_quality_is_never_part_of_the_health_score():
    """Sinon ajouter une exemption `ignore_imports` légitime et documentée
    ferait échouer la build — cela punirait le geste honnête (spec §5)."""
    from scripts.feature_health import scoring

    source = pathlib.Path(scoring.__file__).read_text(encoding="utf-8")
    assert "quality" not in source.split("def weighted_health")[1].split("def ")[0]


def test_snapshot_is_appended_never_rewritten(tmp_path):
    journal = tmp_path / "historique-sante.jsonl"
    append_snapshot(journal, [("f1", 50.0, {})], commit="aaa", date="2026-09-07")
    append_snapshot(journal, [("f1", 62.0, {})], commit="bbb", date="2026-09-08")
    lines = journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["commit"] == "aaa"
    assert last_snapshot(journal) == {"f1": 62.0}


def test_last_snapshot_of_an_absent_journal_is_empty(tmp_path):
    assert last_snapshot(tmp_path / "absent.jsonl") == {}
```

- [ ] **Step 2 : lancer, vérifier l'échec**

Run : `uv run pytest tests/test_feature_health_scoring.py -v` → FAIL (imports).

- [ ] **Step 3 : écrire `quality.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Reprise des portes de qualité existantes (SP-61, spec §5).

**Aucun calcul neuf, aucune note.** Le bilan affiche des faits déjà écrits
ailleurs, gratuits à lire, et discriminants par module ou par fichier :
- `mypy --strict` ne couvre que 6 modules sur 42 (`.github/workflows/ci.yml`) ;
- chaque exemption `ignore_imports` de `core/pyproject.toml` nomme une arête
  précise, avec sa justification ;
- 10 fichiers de `shell/src` portent un `eslint-disable` ;
- 7 portent un `@ts-expect-error` ou un `: any`.

Ces reprises **n'entrent pas dans la santé** : sinon ajouter une exemption
légitime et documentée ferait échouer la build, ce qui punirait exactement le
geste honnête qu'on veut encourager (spec §5)."""

from __future__ import annotations

import dataclasses
import pathlib
import re

from scripts.feature_health.model import Feature

_MYPY_RE = re.compile(r"mypy --strict ((?:app/\S+\s*)+)")
_IGNORE_BLOCK_RE = re.compile(r"ignore_imports = \[(.*?)\]", re.DOTALL)
_EXEMPTION_RE = re.compile(r'"([^"]+->[^"]+)"')


@dataclasses.dataclass(frozen=True)
class QualityFacts:
    mypy_strict_modules: tuple[str, ...]
    layer_exemptions: tuple[str, ...]
    eslint_disabled: frozenset[str]
    typing_escapes: frozenset[str]


def collect_quality_facts(repo: pathlib.Path) -> QualityFacts:
    ci = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = _MYPY_RE.search(ci)
    modules = tuple(match.group(1).split()) if match else ()
    pyproject = (repo / "core/pyproject.toml").read_text(encoding="utf-8")
    block = _IGNORE_BLOCK_RE.search(pyproject)
    exemptions = tuple(_EXEMPTION_RE.findall(block.group(1))) if block else ()
    eslint, typing = set(), set()
    for path in sorted((repo / "shell/src").rglob("*.ts*")):
        blob = path.read_text(encoding="utf-8")
        relative = path.relative_to(repo).as_posix()
        if "eslint-disable" in blob:
            eslint.add(relative)
        if "@ts-expect-error" in blob or ": any" in blob:
            typing.add(relative)
    return QualityFacts(modules, exemptions, frozenset(eslint), frozenset(typing))


def quality_for(feature: Feature, facts: QualityFacts) -> dict[str, object]:
    core_proofs = [proof for proof in feature.proofs if proof.startswith("core/app/")]
    strict = bool(core_proofs) and all(
        any(proof.startswith(f"core/{module}/") for module in facts.mypy_strict_modules)
        for proof in core_proofs
    )
    modules = {
        "app." + proof[len("core/app/") :].split("/", 1)[0] for proof in core_proofs
    }
    return {
        "typage_strict": strict if core_proofs else None,
        "exemptions_de_couches": [
            exemption
            for exemption in facts.layer_exemptions
            if any(exemption.startswith(module) for module in modules)
        ],
        "eslint_disable": sorted(set(feature.proofs) & facts.eslint_disabled),
        "echappatoires_de_typage": sorted(set(feature.proofs) & facts.typing_escapes),
    }
```

- [ ] **Step 4 : écrire `scoring.py`, `history.py` et `feature_health_thresholds.json`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Agrégation des quatre sous-scores en une santé 0-100 (SP-61, spec §3, §4).

Deux grandeurs, jamais moyennées ensemble : la **santé** (calculée ici) et la
**priorité** (déclarée dans l'inventaire). Le tri de priorisation est
`priorité × (100 − santé)` : ce qui compte le plus et qui va le moins bien.

Un sous-score `None` est **non applicable** : il sort du calcul et les
pondérations se renormalisent sur les sous-scores restants."""

from __future__ import annotations

import dataclasses
import json
import pathlib

from scripts.feature_health.model import Feature, SubScore

PRIORITY_WEIGHT = {"haute": 3.0, "moyenne": 2.0, "basse": 1.0}


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


def weighted_health(subscores: dict[str, SubScore], weights: dict[str, float]) -> float | None:
    applicable = {
        name: score.value
        for name, score in subscores.items()
        if score.value is not None and name in weights
    }
    if not applicable:
        return None
    total = sum(weights[name] for name in applicable)
    return sum(value * weights[name] for name, value in applicable.items()) / total


def priority_rank(feature: Feature, health: float | None) -> float:
    if health is None:
        return 0.0
    return PRIORITY_WEIGHT.get(feature.priority, 1.0) * (100.0 - health)
```

```python
# SPDX-License-Identifier: Apache-2.0
"""Journal de santé append-only (SP-61, spec §7.2).

Append-only et non « fichier réécrit » pour trois raisons tenues : le diff git
d'une régénération ne montre que des ajouts ; deux sessions concurrentes ne
s'écrasent pas ; un bug du générateur ne peut pas perdre l'historique.

Le journal n'est **jamais** rétro-calculé : les six notes d'agents de SP-42
sont des jugements, pas des mesures, et les convertir en santé rétroactive
produirait une courbe fausse à son origine."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable


def append_snapshot(
    path: pathlib.Path,
    healths: Iterable[tuple[str, float | None, dict[str, float | None]]],
    *,
    commit: str,
    date: str,
) -> None:
    lines = [
        json.dumps(
            {
                "date": date,
                "commit": commit,
                "id": identifier,
                "sante": value,
                "sous_scores": subscores,
            },
            ensure_ascii=False,
        )
        for identifier, value, subscores in healths
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def last_snapshot(path: pathlib.Path) -> dict[str, float]:
    """La santé de chaque fonctionnalité au dernier instantané écrit."""
    if not path.exists():
        return {}
    latest_commit = None
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["commit"] != latest_commit:
            latest_commit = row["commit"]
            values = {}
        if row["sante"] is not None:
            values[row["id"]] = float(row["sante"])
    return values
```

`core/scripts/feature_health_thresholds.json` — **valeurs provisoires** ;
elles sont remplacées au Step 6 par les valeurs mesurées :

```json
{
  "ponderations": {"tests": 0.30, "atteignabilite": 0.25, "garde": 0.25, "dette": 0.20},
  "plancher_priorite_haute": 1,
  "plancher_sante_mediane": 1
}
```

- [ ] **Step 5 : écrire le CLI**

`core/scripts/feature_health_cli.py` : `--repo`, `--check` (plancher §6.2,
sortie non nulle si franchi), `--write` (regénère les deux rendus et **ajoute**
un instantané au journal). Le CLI est le seul point qui assemble les six
modules ; il ne contient aucune règle de calcul.

```python
# SPDX-License-Identifier: Apache-2.0
"""Bilan de santé des fonctionnalités — calcul, garde-fou et rendu (SP-61).

    uv run python scripts/feature_health_cli.py --repo .. --check
    uv run python scripts/feature_health_cli.py --repo .. --write

`--check` n'écrit rien : il calcule et applique les deux planchers de
`feature_health_thresholds.json`. `--write` regénère
`docs/revue/bilan-fonctionnalites.{html,md}` et ajoute un instantané à
`docs/revue/historique-sante.jsonl`."""

from __future__ import annotations

import argparse
import datetime
import pathlib
import statistics
import subprocess
import sys

from scripts.feature_health import history, quality, scoring
from scripts.feature_health.coverage_facts import collect_coverage_facts, score_tests
from scripts.feature_health.debt import collect_debt_facts, score_debt
from scripts.feature_health.mcp_surface import index_mcp_tools
from scripts.feature_health.model import load_inventory
from scripts.feature_health.reachability import collect_reachability_facts, score_reachability
from scripts.feature_health.rest_surface import index_rest_routes, rest_surface_ids, score_guard

INVENTORY = "docs/revue/inventaire-fonctionnalites.jsonl"
JOURNAL = "docs/revue/historique-sante.jsonl"
THRESHOLDS = "core/scripts/feature_health_thresholds.json"


def compute(repo: pathlib.Path):
    features = load_inventory(repo / INVENTORY)
    routes = index_rest_routes(repo)
    reach = collect_reachability_facts(
        repo, rest_paths=rest_surface_ids(routes), mcp_tools=frozenset(index_mcp_tools(repo))
    )
    coverage = collect_coverage_facts(repo)
    debt_items = collect_debt_facts(repo)
    quality_facts = quality.collect_quality_facts(repo)
    thresholds = scoring.load_thresholds(repo / THRESHOLDS)
    rows = []
    for feature in features:
        subscores = {
            "tests": score_tests(feature, coverage),
            "atteignabilite": score_reachability(feature, reach),
            "garde": score_guard(feature, routes),
            "dette": score_debt(feature, debt_items),
        }
        value = scoring.weighted_health(subscores, thresholds.weights)
        rows.append(
            {
                "feature": feature,
                "sante": value,
                "sous_scores": subscores,
                "qualite": quality.quality_for(feature, quality_facts),
                "rang": scoring.priority_rank(feature, value),
            }
        )
    return rows, thresholds


def _check(rows, thresholds) -> int:
    measured = [row["sante"] for row in rows if row["sante"] is not None]
    median = statistics.median(measured) if measured else 0.0
    failures = [
        f"{row['feature'].identifier} : santé {row['sante']:.1f} < plancher "
        f"{thresholds.floor_high_priority}"
        for row in rows
        if row["feature"].priority == "haute"
        and row["sante"] is not None
        and row["sante"] < thresholds.floor_high_priority
    ]
    print(f"Santé médiane : {median:.1f} (plancher {thresholds.floor_median})")
    if median < thresholds.floor_median:
        failures.append(f"santé médiane {median:.1f} < plancher {thresholds.floor_median}")
    for failure in failures:
        print(f"ÉCHEC : {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args(argv)
    repo = arguments.repo.resolve()
    rows, thresholds = compute(repo)
    if arguments.write:
        # Import tardif : les deux rendus arrivent en Tâche 7, alors que `--check`
        # doit déjà fonctionner en Tâche 6. Un import de module manquant en tête
        # de fichier casserait `--check` pour une raison sans rapport avec lui.
        from scripts.feature_health import render_html, render_md

        commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        date = datetime.date.today().isoformat()
        previous = history.last_snapshot(repo / JOURNAL)
        (repo / "docs/revue/bilan-fonctionnalites.md").write_text(
            render_md.render(rows, previous=previous, date=date), encoding="utf-8"
        )
        (repo / "docs/revue/bilan-fonctionnalites.html").write_text(
            render_html.render(rows, previous=previous, date=date, commit=commit),
            encoding="utf-8",
        )
        history.append_snapshot(
            repo / JOURNAL,
            [
                (
                    row["feature"].identifier,
                    row["sante"],
                    {name: score.value for name, score in row["sous_scores"].items()},
                )
                for row in rows
            ],
            commit=commit,
            date=date,
        )
        print(f"{len(rows)} fonctionnalités — bilan et journal écrits.")
    return _check(rows, thresholds) if arguments.check else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 6 : mesurer, puis fixer les planchers**

```bash
cd core && uv run python scripts/feature_health_cli.py --repo .. --check
```

Relever la santé médiane affichée et la santé minimale des fonctionnalités de
priorité `haute`. Écrire dans `feature_health_thresholds.json` **la valeur
mesurée arrondie à l'entier inférieur**, sans marge inventée — c'est la
doctrine de `.coverage-threshold` (85 pour 94 % mesuré) et
`.bundle-size-threshold` (630 pour 624 Ko) : un plancher est un cliquet, il se
relève par un commit explicite. Consigner les deux valeurs mesurées dans le
message de commit.

- [ ] **Step 7 : ajouter le plancher §6.2 à `core/tests/test_feature_inventory.py`**

Compléter l'en-tête d'imports du fichier créé en Tâche 5 (`import pathlib` y est
déjà) avec `import statistics` et `import pytest`, puis ajouter :

```python
COVERAGE_ARTEFACTS = (
    REPO / "core/coverage.xml",
    REPO / "shell/coverage/coverage-summary.json",
)


@pytest.mark.skipif(
    not all(path.exists() for path in COVERAGE_ARTEFACTS),
    reason=(
        "artefacts de couverture absents — le plancher de santé est vérifié en CI "
        "par le job `feature-health`, qui les récupère des jobs `core` et `shell`"
    ),
)
def test_health_floors_hold():
    """Plancher §6.2. Ce test ne peut pas tourner dans le job `core` de la CI :
    `coverage.xml` y est écrit à la fin du pytest qui l'exécuterait, et la
    couverture shell est produite sur une autre machine. Il tourne en local
    (où les deux artefacts existent) et dans le job dédié."""
    from scripts.feature_health_cli import compute

    rows, thresholds = compute(REPO)
    measured = [row["sante"] for row in rows if row["sante"] is not None]
    low = sorted(
        (row["feature"].identifier, row["sante"])
        for row in rows
        if row["feature"].priority == "haute"
        and row["sante"] is not None
        and row["sante"] < thresholds.floor_high_priority
    )
    assert low == [], f"fonctionnalités de priorité haute sous le plancher : {low}"
    assert statistics.median(measured) >= thresholds.floor_median
```

- [ ] **Step 8 : falsifier le plancher**

Porter temporairement `plancher_sante_mediane` à `99`, relancer
`uv run python scripts/feature_health_cli.py --repo .. --check` : Expected
sortie **1** avec le message `ÉCHEC : santé médiane …`. Restaurer la valeur
mesurée, reconfirmer sortie 0.

- [ ] **Step 9 : portes de qualité + commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run pytest tests/test_feature_health_scoring.py tests/test_feature_inventory.py -v && cd ..
git add core/scripts/feature_health core/scripts/feature_health_cli.py \
        core/scripts/feature_health_thresholds.json core/tests/test_feature_health_scoring.py \
        core/tests/test_feature_inventory.py
git commit -m "feat(revue): sante ponderee, priorite declaree, journal et plancher CI (SP-61)"
```

---

### Task 7 : rendus Markdown et HTML

Le rendu vient **en dernier parce que c'est la partie qui n'apprend rien**
(spec §10). Le design n'est pas réinventé : `docs/revue/2026-09-04-matrice-fonctionnalites.html`
(déjà dans le dépôt, commit `7aad5234`) est la référence — un seul fichier, sans
build, données en `<script type="application/json">`, CSS et JS inline, thème
clair/sombre via `prefers-color-scheme` **plus** `[data-theme]` explicite, une
seule dépendance externe (Google Fonts) avec pile de repli réelle. Mesuré dans
ce fichier : bloc CSS de 22 576 caractères, bloc JS de 29 378, trois blocs de
données JSON.

**Files:**
- Create: `core/scripts/feature_health/assets/bilan.css` (extrait **verbatim** de l'artefact)
- Create: `core/scripts/feature_health/assets/bilan-body.html`
- Create: `core/scripts/feature_health/assets/bilan.js`
- Create: `core/scripts/feature_health/render_md.py`
- Create: `core/scripts/feature_health/render_html.py`
- Create: `docs/revue/bilan-fonctionnalites.md`, `docs/revue/bilan-fonctionnalites.html` (produits)
- Test: `core/tests/test_feature_health_render.py`

**Interfaces:**
- Consumes: les lignes produites par `feature_health_cli.compute()`
  (`{"feature", "sante", "sous_scores", "qualite", "rang"}`) et
  `history.last_snapshot()`.
- Produces :
  - `render_md.render(rows, *, previous: dict[str, float], date: str) -> str` ;
  - `render_html.render(rows, *, previous, date, commit) -> str`.

**Ce qui change par rapport à l'artefact repris** (conséquence directe du modèle,
spec §7.1) :
1. la colonne « Note » (moyenne de six critères) devient **deux colonnes
   distinctes** — *santé* calculée et *priorité* déclarée, jamais moyennées ;
2. le détail dépliable montre les **quatre sous-scores** et, pour chacun, la
   donnée qui l'a produit (`SubScore.evidence`, déjà porté depuis la Tâche 1) ;
3. un bloc **qualité reprise** (typage strict, exemptions de couches,
   `eslint-disable`, `@ts-expect-error`) — des faits, sans note ;
4. le tri par défaut est `priorité × (100 − santé)` ;
5. une **vue d'évolution** : delta par fonctionnalité depuis l'instantané
   précédent (`↑ +12`, `=`, `↓ −7`), liste « amélioré / dégradé », et santé
   médiane par instantané.

- [ ] **Step 1 : extraire le CSS de l'artefact, verbatim**

```bash
cd core && uv run python - <<'PY'
import pathlib, re
source = pathlib.Path("../docs/revue/2026-09-04-matrice-fonctionnalites.html").read_text(encoding="utf-8")
blocks = re.findall(r"<style>(.*?)</style>", source, re.S)
target = pathlib.Path("scripts/feature_health/assets/bilan.css")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(blocks[1], encoding="utf-8")   # bloc 0 = reset de 213 car., bloc 1 = le design
print(len(blocks[1]), "caractères extraits")
PY
cd ..
```
Expected: `22576 caractères extraits`.

- [ ] **Step 2 : écrire les tests de rendu qui échouent**

Créer `core/tests/test_feature_health_render.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Rendus Markdown et HTML du bilan (SP-61, spec §7.1).

Propriété centrale : les deux sorties viennent de la **même source dans le même
passage** — elles ne peuvent pas se contredire parce qu'aucune n'est écrite à
la main."""

import json
import pathlib
import re

from scripts.feature_health import render_html, render_md
from scripts.feature_health.model import Feature, SubScore

REPO = pathlib.Path(__file__).resolve().parents[2]


def _row(identifier="f1", health=60.0, priority="haute"):
    feature = Feature(
        identifier=identifier, domain="Catalogue", name="Lister les items",
        proofs=("core/app/items/routes.py",), rest=("GET /v1/items",), mcp=(), shell=(),
        public=(), priority=priority, priority_source="amorcage-sp42", raw={},
    )
    return {
        "feature": feature,
        "sante": health,
        "sous_scores": {
            "tests": SubScore(94.2, {"core/app/items/routes.py": "94.2 % de lignes couvertes"}),
            "atteignabilite": SubScore(100.0, {"GET /v1/items": "montée"}),
            "garde": SubScore(50.0, {"GET /v1/items": "authentification seule"}),
            "dette": SubScore(80.0, {"REV-042": "important"}),
        },
        "qualite": {"typage_strict": False, "exemptions_de_couches": [],
                    "eslint_disable": [], "echappatoires_de_typage": []},
        "rang": 120.0,
    }


def test_markdown_carries_one_row_per_feature():
    output = render_md.render([_row("a"), _row("b")], previous={}, date="2026-09-07")
    assert output.count("| Catalogue |") == 2


def test_markdown_shows_health_and_priority_in_separate_columns():
    output = render_md.render([_row()], previous={}, date="2026-09-07")
    header = next(line for line in output.splitlines() if line.startswith("| Domaine"))
    assert "Santé" in header and "Priorité" in header
    assert "note globale" not in output.lower()


def test_markdown_shows_the_delta_against_the_previous_snapshot():
    output = render_md.render([_row(health=60.0)], previous={"f1": 48.0}, date="2026-09-07")
    assert "+12" in output


def test_html_embeds_its_data_as_json():
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc123")
    payload = re.search(
        r'<script type="application/json" id="bilan-data">(.*?)</script>', output, re.S
    )
    assert payload is not None
    data = json.loads(payload.group(1))
    assert data["fonctionnalites"][0]["id"] == "f1"
    assert data["fonctionnalites"][0]["sous_scores"]["garde"]["valeur"] == 50.0
    assert data["commit"] == "abc123"


def test_html_has_no_external_dependency_but_the_font_stylesheet():
    """Contrainte de forme héritée de l'artefact : un seul fichier, aucune
    étape de compilation, aucun CDN de librairie (spec §7.1)."""
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc")
    assert "<script src=" not in output
    external = re.findall(r'<link[^>]+href="(https?://[^"]+)"', output)
    assert external == ["https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,"
                        "400;9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;"
                        "600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"]


def test_html_keeps_the_dark_theme_of_the_reference_artefact():
    output = render_html.render([_row()], previous={}, date="2026-09-07", commit="abc")
    assert "@media (prefers-color-scheme: dark)" in output
    assert '[data-theme="dark"]' in output


def test_html_and_markdown_never_diverge():
    rows = [_row("a", health=60.0), _row("b", health=90.0)]
    markdown = render_md.render(rows, previous={}, date="2026-09-07")
    html = render_html.render(rows, previous={}, date="2026-09-07", commit="abc")
    data = json.loads(
        re.search(r'id="bilan-data">(.*?)</script>', html, re.S).group(1)
    )
    from_html = {item["id"]: item["sante"] for item in data["fonctionnalites"]}
    from_md = {
        match.group(1): float(match.group(2))
        for match in re.finditer(r"\| `([a-z0-9-]+)` \| ([0-9.]+) \|", markdown)
    }
    assert from_html == from_md


def test_the_committed_html_is_a_single_self_contained_file():
    """Le produit livré, pas seulement la fonction de rendu."""
    output = (REPO / "docs/revue/bilan-fonctionnalites.html").read_text(encoding="utf-8")
    assert "<style>" in output and 'id="bilan-data"' in output
    assert "node_modules" not in output
```

- [ ] **Step 3 : lancer, vérifier l'échec, écrire les deux rendus, revérifier**

Run : `uv run pytest tests/test_feature_health_render.py -v` → FAIL (imports).

`core/scripts/feature_health/render_md.py` — la forme greppable et diffable.
**L'ordre des colonnes est contractuel** : le test de non-divergence lit
`| \`id\` | santé |` dans cet ordre, et la table de synthèse par domaine met le
domaine en gras (`| **Catalogue** |`) pour ne pas être confondue avec les lignes
de fonctionnalités.

```python
# SPDX-License-Identifier: Apache-2.0
"""Rendu Markdown du bilan (SP-61, spec §7.1).

Le Markdown n'est pas le produit central — le HTML l'est. Il existe pour ce que
le HTML fait mal : être lu dans un diff de commit, et être grepé. Les deux
sorties viennent du même passage du même script sur la même source : aucune
divergence n'est possible."""

from __future__ import annotations

import statistics
from collections.abc import Iterable

_COLUMNS = (
    "Domaine", "Fonctionnalité", "id", "Santé", "Δ", "Priorité",
    "tests", "atteignabilité", "garde", "dette",
)


def _cell(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _delta(identifier: str, health: float | None, previous: dict[str, float]) -> str:
    if health is None or identifier not in previous:
        return "—"
    difference = health - previous[identifier]
    if abs(difference) < 0.05:
        return "="
    return f"{difference:+.1f}"


def render(rows: Iterable[dict], *, previous: dict[str, float], date: str) -> str:
    rows = sorted(rows, key=lambda row: row["rang"], reverse=True)
    measured = [row["sante"] for row in rows if row["sante"] is not None]
    lines = [
        "# Bilan de fonctionnalités — GeoStudio",
        "",
        f"**Généré le {date}** par "
        "`uv run python scripts/feature_health_cli.py --repo .. --write`. "
        "**Ne pas éditer à la main** : ce fichier est regénéré à chaque clôture de SP.",
        "",
        f"{len(rows)} fonctionnalités — santé médiane "
        f"{statistics.median(measured):.1f} sur {len(measured)} mesurables.",
        "",
        "La **santé** est calculée (quatre sous-scores, spec §3) ; la **priorité** est "
        "déclarée (spec §4). Les deux ne sont jamais moyennées. Le tri est "
        "`priorité × (100 − santé)`.",
        "",
        "## Par domaine",
        "",
        "| Domaine | Fonctionnalités | Santé médiane |",
        "|---|---|---|",
    ]
    domains: dict[str, list[float]] = {}
    for row in rows:
        if row["sante"] is not None:
            domains.setdefault(row["feature"].domain, []).append(row["sante"])
    for domain in sorted(domains):
        values = domains[domain]
        lines.append(f"| **{domain}** | {len(values)} | {statistics.median(values):.1f} |")
    lines += [
        "",
        "## Toutes les fonctionnalités",
        "",
        "| " + " | ".join(_COLUMNS) + " |",
        "|" + "---|" * len(_COLUMNS),
    ]
    for row in rows:
        feature = row["feature"]
        subscores = row["sous_scores"]
        lines.append(
            "| {domain} | {name} | `{identifier}` | {health} | {delta} | {priority} "
            "| {tests} | {reach} | {guard} | {debt} |".format(
                domain=feature.domain,
                name=feature.name.replace("|", "/"),
                identifier=feature.identifier,
                health=_cell(row["sante"]),
                delta=_delta(feature.identifier, row["sante"], previous),
                priority=feature.priority,
                tests=_cell(subscores["tests"].value),
                reach=_cell(subscores["atteignabilite"].value),
                guard=_cell(subscores["garde"].value),
                debt=_cell(subscores["dette"].value),
            )
        )
    return "\n".join(lines) + "\n"
```

`core/scripts/feature_health/render_html.py` — un seul fichier, sans build. Le
squelette de corps est **repris de l'artefact** (`docs/revue/2026-09-04-matrice-fonctionnalites.html`) :
bandeau, tuiles de synthèse, barre empilée, grille par famille, contrôles
collants, tableau à colonnes triables, lignes dépliables. Le CSS est le fichier
extrait au Step 1, inchangé.

```python
# SPDX-License-Identifier: Apache-2.0
"""Rendu HTML du bilan — le produit de suivi central (SP-61, spec §7.1).

Contraintes de forme héritées de l'artefact SP-42, à conserver : un seul
fichier, aucune étape de compilation, données embarquées en
`<script type="application/json">`, CSS et JS inline, une seule dépendance
externe (Google Fonts, avec pile de repli réelle), thème clair/sombre par
`prefers-color-scheme` **et** `[data-theme]` explicite. Pas de CDN de
librairie, pas de graphique tiers."""

from __future__ import annotations

import json
import pathlib
import statistics
from collections.abc import Iterable

ASSETS = pathlib.Path(__file__).parent / "assets"
FONTS = (
    "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,"
    "400;9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;"
    "600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
)


def _payload(rows, previous, date, commit) -> dict:
    features = []
    for row in rows:
        feature = row["feature"]
        health = row["sante"]
        features.append(
            {
                "id": feature.identifier,
                "domaine": feature.domain,
                "fonctionnalite": feature.name,
                "sante": health,
                "delta": (
                    None
                    if health is None or feature.identifier not in previous
                    else round(health - previous[feature.identifier], 1)
                ),
                "priorite": feature.priority,
                "priorite_source": feature.priority_source,
                "sous_scores": {
                    name: {"valeur": score.value, "preuve": score.evidence}
                    for name, score in row["sous_scores"].items()
                },
                "qualite": row["qualite"],
                "rang": row["rang"],
                "preuve": list(feature.proofs),
                "surfaces": {
                    "rest": list(feature.rest),
                    "mcp": list(feature.mcp),
                    "shell": list(feature.shell),
                },
            }
        )
    measured = [item["sante"] for item in features if item["sante"] is not None]
    return {
        "date": date,
        "commit": commit,
        "sante_mediane": statistics.median(measured) if measured else None,
        "fonctionnalites": sorted(features, key=lambda item: item["rang"], reverse=True),
    }


def render(rows: Iterable[dict], *, previous: dict[str, float], date: str, commit: str) -> str:
    payload = _payload(list(rows), previous, date, commit)
    css = (ASSETS / "bilan.css").read_text(encoding="utf-8")
    script = (ASSETS / "bilan.js").read_text(encoding="utf-8")
    body = (ASSETS / "bilan-body.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset=utf8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>Bilan GeoStudio</title>"
        f'<link rel="stylesheet" href="{FONTS}">'
        f"<style>{css}</style></head><body>\n"
        f"{body}\n"
        f'<script type="application/json" id="bilan-data">{data}</script>\n'
        f"<script>{script}</script>\n"
        "</body></html>\n"
    )
```

`core/scripts/feature_health/assets/bilan-body.html` : le squelette statique,
copié depuis l'artefact (lignes 419-522 : bandeau, `#tiles`, `#stackBar`,
`#famGrid`, `#searchInput`, groupes de chips, `<tbody id="tbody">`) et adapté —
la colonne « Note » y devient deux colonnes `Santé` et `Priorité`, plus une
colonne `Δ`, et un onglet « Évolution » s'ajoute à côté de l'onglet « Bilan ».

`core/scripts/feature_health/assets/bilan.js` : nouveau (les colonnes ont
changé), mais de même facture que le JS de l'artefact. Il fait exactement six
choses, dans cet ordre :

1. lit `JSON.parse(document.getElementById("bilan-data").textContent)` ;
2. rend les tuiles de synthèse (nombre de fonctionnalités, santé médiane,
   répartition par tranche de santé, nombre de priorités hautes sous le
   plancher) et la barre empilée ;
3. rend la grille par domaine (clic = filtre) ;
4. rend le tableau, trié par `rang` décroissant par défaut, avec tri par clic
   d'en-tête sur chaque colonne, recherche plein texte, et chips de filtre
   (domaine, priorité, tranche de santé) ;
5. déplie une ligne au clic : les quatre sous-scores avec, sous chacun, sa
   `preuve` telle quelle (pourcentage de couverture, lien entrant trouvé ou son
   absence, garde détectée, `GAP`/`REV` ouverts), puis le bloc **qualité
   reprise** — typage strict, exemptions de couches, `eslint-disable`,
   échappatoires de typage — présenté comme des faits, sans note ;
6. rend l'onglet **Évolution** : les fonctionnalités améliorées et dégradées
   depuis l'instantané précédent (`delta`), et la santé médiane courante.

Run : `uv run pytest tests/test_feature_health_render.py -v` → PASS, sauf
`test_the_committed_html_is_a_single_self_contained_file` tant que le Step 4
n'est pas fait.

- [ ] **Step 4 : générer les deux rendus**

```bash
cd core && uv run python scripts/feature_health_cli.py --repo .. --write && cd ..
ls -la docs/revue/bilan-fonctionnalites.html docs/revue/bilan-fonctionnalites.md
wc -l docs/revue/historique-sante.jsonl    # attendu : 304 (premier instantané)
```

Ouvrir `docs/revue/bilan-fonctionnalites.html` dans un navigateur (`file://`) et
vérifier à l'œil : le tri par défaut est bien le tri de priorisation, un
dépliage montre les quatre sous-scores **avec leur donnée source**, le thème
sombre fonctionne, aucune erreur en console.

- [ ] **Step 5 : vérifier la propriété de non-divergence sur les données réelles**

```bash
cd core && uv run pytest tests/test_feature_health_render.py -v && cd ..
```

- [ ] **Step 6 : commit**

```bash
cd core && uv run ruff check . && uv run ruff format --check . && cd ..
git add core/scripts/feature_health/assets core/scripts/feature_health/render_md.py \
        core/scripts/feature_health/render_html.py core/tests/test_feature_health_render.py \
        docs/revue/bilan-fonctionnalites.html docs/revue/bilan-fonctionnalites.md \
        docs/revue/historique-sante.jsonl
git commit -m "feat(revue): rendus HTML et Markdown du bilan depuis une source unique (SP-61)"
```

---

### Task 8 : câblage CI et bascule documentaire

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `CLAUDE.md`
- Modify: `docs/revue/2026-09-04-matrice-fonctionnalites.md` (encadré de gel)
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (GAP-81, `/analytics/sql`)
- Test: `core/tests/test_deployability.py` (une règle de plus)

- [ ] **Step 1 : écrire la règle de déployabilité qui échoue**

Ajouter à `core/tests/test_deployability.py` (fichier exempté de `ruff`, cf.
`core/pyproject.toml` — ne pas le reformater) :

```python
def test_feature_health_gate_runs_in_ci():
    """SP-61 : un garde-fou qui n'est pas câblé dans la CI ne garde rien —
    piège n°2 de CLAUDE.md, « livré + testé + mergé ≠ câblé »."""
    ci = CI.read_text()
    assert "feature_health_cli.py" in ci
    assert "--check" in ci
```

Run : `uv run pytest tests/test_deployability.py::test_feature_health_gate_runs_in_ci -v`
Expected: FAIL.

- [ ] **Step 2 : câbler le job `feature-health`**

Ajouter à `.github/workflows/ci.yml` : dans le job `core`, après
`check_coverage.py`, un `actions/upload-artifact@v4` de `core/coverage.xml` ; dans
le job `shell`, après `check-coverage.mjs`, un upload de
`shell/coverage/coverage-summary.json` ; puis un job dédié :

```yaml
  feature-health:
    runs-on: ubuntu-latest
    needs: [core, shell]
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - uses: actions/download-artifact@v4
        with: {name: core-coverage, path: core}
      - uses: actions/download-artifact@v4
        with: {name: shell-coverage, path: shell/coverage}
      - run: uv sync
        working-directory: core
      - run: uv run python scripts/feature_health_cli.py --repo .. --check
        working-directory: core
```

Vérifier **par valeur**, pas de mémoire (piège n°2) :

```bash
python3 -c "import yaml;d=yaml.safe_load(open('.github/workflows/ci.yml'));\
print(list(d['jobs']));print(d['jobs']['feature-health']['needs'])"
cd core && uv run pytest tests/test_deployability.py -v && cd ..
```

- [ ] **Step 3 : geler le couple daté**

En tête de `docs/revue/2026-09-04-matrice-fonctionnalites.md`, sous le titre,
ajouter :

```markdown
> **Document historique, gelé le 2026-09-06 (SP-61).** Cette matrice est une
> photo du 2026-09-04, produite une fois par huit agents ; elle a servi de
> matière première à `analyse-gaps.md` et au backlog et le reste telle quelle.
> Le document vivant qui la remplace est **`docs/revue/bilan-fonctionnalites.html`**
> (rendu Markdown : `bilan-fonctionnalites.md`), regénéré par
> `uv run python scripts/feature_health_cli.py --repo .. --write` depuis
> `docs/revue/inventaire-fonctionnalites.jsonl`. Ne plus éditer ce fichier-ci.
```

Le lien `**Version consultable :** <https://claude.ai/code/artifact/…>` (ligne 7)
devient un lien vers le fichier local `2026-09-04-matrice-fonctionnalites.html`,
rapatrié depuis (commit `7aad5234`) : plus de dépendance externe pour un
livrable du dépôt.

- [ ] **Step 4 : basculer le pointeur de `CLAUDE.md`**

Dans `## Comment on travaille`, la clause « **À la clôture d'un SP** » nomme
aujourd'hui `docs/revue/2026-09-04-matrice-fonctionnalites.md` comme document à
mettre à jour à la main. Remplacer par : mettre à jour l'état des `GAP-nn` dans
`analyse-gaps.md` (inchangé), **et régénérer le bilan** :

```markdown
  et **régénérer le bilan de fonctionnalités** —
  `cd core && uv run python scripts/feature_health_cli.py --repo .. --write` —
  après avoir ajouté à `docs/revue/inventaire-fonctionnalites.jsonl` toute
  surface nouvellement livrée (route REST, outil MCP, route shell). La CI
  refuse une surface non inventoriée (`core/tests/test_feature_inventory.py`) :
  ce n'est plus une discipline, c'est une porte. La matrice datée
  `2026-09-04-matrice-fonctionnalites.md` est **gelée** et ne se met plus à jour.
```

Ajouter la commande à `## Commandes`, section cœur.

- [ ] **Step 5 : consigner la trouvaille `/analytics/sql`**

Ajouter à `docs/revue/2026-09-04-analyse-gaps.md`, à la suite de GAP-80 et sur
le même modèle, une entrée **GAP-81 — `/analytics/sql` inatteignable** : la
route existe (`routes.tsx:330`, gardée par `RequirePrivilege
analytics.sql_lab.access`), mais `shell/src/shell/chrome/domainRoutes.ts:21`
route le domaine Analytique vers `/?type=bookmark` et **aucun lien du shell ne
pointe vers `/analytics/sql`** — un analyste porteur du privilège ne peut
atteindre le SQL Lab qu'en tapant l'URL. Même classe que GAP-30/32/39/67/80.
Ajouter la ligne correspondante au tableau d'état (`| GAP-81 | Ouvert | … |`) —
ce qui la fait entrer automatiquement dans le sous-score `dette` de la
fonctionnalité SQL Lab, à la prochaine régénération.

- [ ] **Step 6 : régénérer et vérifier l'ensemble**

```bash
cd core
uv run ruff check . && uv run ruff format --check . && uv run lint-imports
uv run pytest tests/test_feature_health_*.py tests/test_feature_inventory.py \
              tests/test_bootstrap_feature_inventory.py tests/test_deployability.py -v
uv run python scripts/feature_health_cli.py --repo .. --write
cd ..
git diff --stat docs/revue/
```

Le diff de `bilan-fonctionnalites.{html,md}` doit refléter GAP-81 (santé du SQL
Lab en baisse) et rien d'autre d'inattendu ; `historique-sante.jsonl` gagne 304
lignes, aucune modifiée.

- [ ] **Step 7 : commit**

```bash
git add .github/workflows/ci.yml CLAUDE.md core/tests/test_deployability.py \
        docs/revue/
git commit -m "feat(ci): cable le garde-fou de bilan et gele la matrice datee (SP-61)"
```

---

## Revue finale de branche (obligatoire — piège n°4)

Une revue **par tâche** ne voit pas les défauts de croisement. Avant toute
fusion vers `dev`, vérifier explicitement, dans cet ordre :

1. **Suite complète du cœur** : `cd core && uv run pytest` avec
   `CORE_TEST_DATABASE_URL` positionné sur un conteneur `postgis-test` **dédié à
   cette session** (piège n°9 : sessions concurrentes sur un conteneur partagé →
   `UniqueViolation`/`DuplicateTable` sans rapport). Compte de référence avant ce
   plan : 2589 passed / 5 skipped (qgis) / 0 failed.
2. **Diff `openapi.json` et `core-schema.d.ts` vides** — attendu et à *vérifier*,
   pas à supposer (piège n°1) :
   `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types && git diff --exit-code`
3. **`uv run lint-imports`** : le package `core/scripts/` n'est pas dans le
   contrat de couches (`app.*` seulement) — confirmer qu'aucune exemption n'a
   été nécessaire, et qu'aucun import de `app.*` ne s'est glissé dans
   `feature_health/` (contrainte globale : le générateur n'importe jamais `app`).
   `grep -rn "^from app\|^import app" core/scripts/feature_health/` doit être vide.
4. **Le garde-fou échoue vraiment** : retirer une route de l'inventaire, lancer
   `uv run pytest tests/test_feature_inventory.py`, confirmer le rouge, restaurer.
5. **Le plancher échoue vraiment** : `plancher_sante_mediane` à 99 →
   `--check` sort 1. Restaurer la valeur mesurée.
6. **Cohérence des comptes entre tâches** : les nombres cités dans les tests
   (147 routes, 27 outils, 28 routes shell, 17 routes sans garde, 6 modules
   `mypy --strict`, 10 `eslint-disable`, 7 échappatoires de typage) sont des
   **mesures**, pas des constantes de confort. Si l'un a bougé pendant le plan,
   c'est le dépôt qui a bougé : relire ce qui a changé avant d'ajuster le
   chiffre, et le consigner.
7. **Suite shell inchangée** : ce plan ne touche aucun fichier de `shell/src`.
   `git diff --stat dev -- shell/` doit être vide.

Puis la skill `superpowers:finishing-a-development-branch` pour la fusion.
