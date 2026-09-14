# Faire passer les 7 fonctionnalités « priorité haute » sous 90 au-dessus de 90 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire passer les 7 fonctionnalités `priorite: "haute"` du bilan SP-61 actuellement
sous 90 de santé au-dessus de 90, et verrouiller ce résultat en CI.

**Architecture:** Deux volets. (A) Corriger deux faux négatifs vérifiés de l'analyseur de garde
AST (`core/scripts/feature_health/rest_surface.py`) — un nom de fonction-garde manquant à
`GUARD_NAMES`, et une résolution de garde qui s'arrête au même module alors que l'architecture
réelle du dépôt (SP-43) place désormais la garde dans une couche de service importée. (B)
Corriger deux preuves d'inventaire périmées et combler deux vrais trous de test
(`scripts/install.sh`, couverture de `DataSourcePanel.tsx`). Fermeture : régénérer le bilan et
relever le plancher CI (`plancher_priorite_haute`) à la valeur réellement mesurée.

**Tech Stack:** Python 3.14 / pytest / AST stdlib (cœur), TypeScript / React / Vitest / Testing
Library (shell), Bash (scripts d'exploitation).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-14-priorite-haute-sante-90-design.md`.
- Aucune nouvelle route REST/MCP/route shell n'est créée par ce plan — `docs/revue/
  inventaire-fonctionnalites.jsonl` ne gagne aucune nouvelle ligne, seules 2 lignes existantes
  voient leur `preuve`/`description`/`note_sp42` corrigées (Tâches 3 et 4).
- Toute modification de `core/scripts/feature_health/rest_surface.py` doit rester un
  élargissement **générique** de la résolution déjà en place (jamais un nom de fonction ajouté
  sans avoir vérifié par lecture directe qu'il enforce réellement une autorisation).
- Chaque nouveau test doit exercer un comportement réel, falsifiable (retirer l'assertion/le
  correctif, confirmer que le test casse, remettre) — jamais un test qui passerait aussi bien
  sur une implémentation vide.
- Docs et commentaires de code en français, identifiants en anglais (convention du dépôt).
- Commits conventionnels, un sujet par commit (`fix(core): …`, `test(core): …`,
  `docs(revue): …`).

---

## File Structure

- **Modify** `core/scripts/feature_health/rest_surface.py` — `GUARD_NAMES` élargi (Tâche 1),
  nouvelle résolution cross-module à un saut (Tâche 2).
- **Modify** `core/tests/test_feature_health_rest_surface.py` — 5 nouveaux tests (Tâches 1-2).
- **Modify** `docs/revue/inventaire-fonctionnalites.jsonl` — 2 lignes corrigées (Tâches 3-4).
- **Create** `core/tests/test_install_script.py` — double `docker`/`jq` + 4 scénarios réels
  (Tâche 6). Aucune modification de `scripts/install.sh` : le script porte déjà toutes les
  échappatoires non-interactives nécessaires (`INSTALL_YES`, `INSTALL_PROFILES`,
  `INSTALL_SEED_DEMO`, `GEOSTUDIO_PUBLIC_HOST`, `BACKUP_S3_ENDPOINT`, `INSTALL_ADMIN_EMAIL`) —
  découverte faite en vérifiant le script en détail, qui simplifie le volet C.1 de la spec
  (la spec anticipait 3 échappatoires manquantes ; il n'y en a en réalité aucune).
- **Modify** `shell/src/builder/DataSourcePanel.test.tsx` — 7 nouveaux tests (Tâche 5).
- **Modify** `core/scripts/feature_health_thresholds.json` — `plancher_priorite_haute` relevé
  (Tâche 7).
- **Modify** `docs/revue/bilan-fonctionnalites.{html,md}`,
  `docs/revue/historique-sante.jsonl` — régénérés (Tâche 7).

---

### Task 1: `GUARD_NAMES` — reconnaître deux gardes réels appelés directement

**Files:**
- Modify: `core/scripts/feature_health/rest_surface.py:40-49`
- Test: `core/tests/test_feature_health_rest_surface.py`

**Interfaces:**
- Consomme : `GUARD_NAMES` (frozenset existant), `index_rest_routes(repo)` (inchangé de
  signature).
- Produit : `GUARD_NAMES` élargi de 6 à 8 entrées — consommé tel quel par `score_guard` (Tâche
  2 et Tâche 7 s'appuient dessus sans rien changer d'autre).

**Contexte vérifié** (lecture directe du code, pas supposé) :
- `core/app/features/tiles.py::get_collection_tile` appelle
  `get_readable_collection(session, user, collection_id, guest=guest)` **directement dans son
  corps** — importé de `core/app/collections/routes.py`. Cette fonction recoupe avec
  `can(...)` en interne (docstring de `get_readable_collection`, ligne ~218 : « recoupée avec
  can(..., user_id=guest.created_by, ...) »). C'est le chokepoint documenté par CLAUDE.md pour
  toute lecture de collection (GAP-19/22/50/60).
- `core/app/pipelines/routes.py::list_pipeline_runs`, `preview_pipeline_route` et
  `list_webhook_tokens_route` appellent `require_pipeline_access(session, user=user,
  item_id=item_id, action=...)` **directement dans leur corps** — importé de
  `core/app/pipelines/service.py`. Cette fonction (lignes 33-38 de ce fichier) appelle
  `can(session, user_id=user.id, action=..., item=facts)` et lève 404/403 selon le verdict —
  un vrai garde, pas un simple accesseur.
- Aucun des deux noms n'est dans `GUARD_NAMES` aujourd'hui — uniquement parce qu'ils n'y ont
  jamais été ajoutés, pas parce que la résolution AST échoue à les voir (`_called_names` les
  capture déjà, ils sont appelés par leur nom littéral dans le corps de la route).

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_feature_health_rest_surface.py` :

```python
def test_a_directly_called_collection_read_gate_is_recognised_as_a_guard():
    """`get_collection_tile` (`app/features/tiles.py`) appelle
    `get_readable_collection(...)` en corps de route — chokepoint d'autorisation
    des collections (GAP-19/22/50/60), qui recoupe avec `can()` en interne
    (`app/collections/routes.py`, vérifié). Absent de `GUARD_NAMES` jusqu'ici
    uniquement par omission — l'appel est déjà visible de `_called_names`."""
    fact = next(
        f
        for f in index_rest_routes(REPO)
        if (f.method, f.path) == ("GET", "/v1/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")
    )
    assert "get_readable_collection" in fact.guards


def test_a_directly_called_pipeline_access_gate_is_recognised_as_a_guard():
    """`require_pipeline_access` (`app/pipelines/service.py`) appelle `can()` et
    lève 404/403 — vérifié par lecture directe. Trois routes l'appellent
    directement en corps (pas via une fonction de service intermédiaire, cf.
    Tâche 2 pour les trois autres)."""
    guarded_directly = {
        "GET /v1/pipelines/{item_id}/runs",
        "POST /v1/pipelines/{item_id}/preview",
        "GET /v1/pipelines/{item_id}/webhook-tokens",
    }
    by_id = {f"{f.method} {f.path}": f for f in index_rest_routes(REPO)}
    for surface in guarded_directly:
        assert "require_pipeline_access" in by_id[surface].guards, surface
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -k "directly_called" -v`
Expected: 2 FAILED — `assert "get_readable_collection" in frozenset({...})` et
`assert "require_pipeline_access" in frozenset({...})` échouent (les noms sont absents des
`guards` actuels).

- [ ] **Step 3: Add the two guard names**

Dans `core/scripts/feature_health/rest_surface.py`, remplacer :

```python
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
```

par :

```python
GUARD_NAMES = frozenset(
    {
        "require_privilege",
        "require_any_privilege",
        "has_privilege",
        "can",
        "rls_scope",
        "assert_egress_allowed",
        # SP-61 volet A.1 (spec 2026-09-14) : wrappers de garde vérifiés par
        # lecture directe de leur corps — chacun recoupe avec `can()`/lève
        # 404-403 selon le verdict, jamais un simple accesseur.
        "get_readable_collection",
        "require_pipeline_access",
    }
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -v`
Expected: 17 passed (15 existants + 2 nouveaux), 0 failed.

- [ ] **Step 5: Run the full feature_health test suite to check for unintended regressions**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py tests/test_feature_health_scoring.py tests/test_feature_inventory.py -v`
Expected: tous verts (le test `test_publiques_declaration_matches_the_ast_unguarded_set` de
`test_feature_inventory.py` recoupe l'ensemble des routes sans garde — l'ajout de deux gardes
ne peut que rétrécir cet ensemble, jamais l'élargir, donc ne peut pas faire échouer ce test).

- [ ] **Step 6: Commit**

```bash
git add core/scripts/feature_health/rest_surface.py core/tests/test_feature_health_rest_surface.py
git commit -m "$(cat <<'EOF'
fix(core): reconnaître get_readable_collection/require_pipeline_access comme des gardes

Les deux fonctions sont déjà appelées directement dans le corps des
routes REST concernées et recoupent avec can() en interne (vérifié par
lecture directe) — elles n'étaient simplement jamais entrées dans
GUARD_NAMES, faisant sous-compter le sous-score « garde » du bilan SP-61
pour la tuile MVT et 3 des 9 routes de pipeline.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

### Task 2: Résolution de garde cross-module (un saut à travers les imports)

**Files:**
- Modify: `core/scripts/feature_health/rest_surface.py` (docstring du module + `index_rest_routes`)
- Test: `core/tests/test_feature_health_rest_surface.py`

**Interfaces:**
- Consomme : `GUARD_NAMES` (Tâche 1), `_called_names(node)` (existant, inchangé).
- Produit : deux nouvelles fonctions module-privées, `_import_targets(tree, repo) ->
  dict[str, pathlib.Path]` et `_guards_in_imported_function(name, path) -> frozenset[str]`,
  utilisées uniquement à l'intérieur d'`index_rest_routes` — aucun autre module de
  `feature_health` ne les importe.

**Contexte vérifié** : `run_pipeline_route`, `create_webhook_token_route` et
`delete_webhook_token_route` (`core/app/pipelines/routes.py`) n'appellent PAS
`require_pipeline_access` directement — ils appellent respectivement
`run_pipeline_service(...)`, `create_webhook_token_service(...)`,
`revoke_webhook_token_service(...)`, trois fonctions importées de
`core/app/pipelines/service.py`. Chacune de ces trois fonctions de service appelle
`require_pipeline_access(...)` **dans son propre corps** (`service.py:90`, `service.py:128`,
`service.py:155`, lu directement) — patron introduit par SP-43 pour partager la garde entre
REST et MCP. La résolution actuelle de `index_rest_routes` ne suit que les fonctions locales au
**même fichier** que la route ; ces trois-là vivent dans un autre fichier, donc invisibles.

- [ ] **Step 1: Write the failing test**

Ajouter à `core/tests/test_feature_health_rest_surface.py` :

```python
def test_guard_reached_through_an_imported_service_function_is_found():
    """POST /v1/pipelines/{item_id}/run → run_pipeline_route → run_pipeline_service
    (importé d'app.pipelines.service) → require_pipeline_access(...) → can(). Avant
    ce volet, cette route ressortait « authentification seule » alors que la
    garde est réelle — vérifié par lecture directe de service.py:78-93."""
    by_id = {f"{f.method} {f.path}": f for f in index_rest_routes(REPO)}
    guarded_via_service = {
        "POST /v1/pipelines/{item_id}/run": "run_pipeline_service",
        "POST /v1/pipelines/{item_id}/webhook-tokens": "create_webhook_token_service",
        "DELETE /v1/pipelines/{item_id}/webhook-tokens/{token_id}": "revoke_webhook_token_service",
    }
    for surface in guarded_via_service:
        assert "require_pipeline_access" in by_id[surface].guards, surface


def test_import_resolution_does_not_invent_guards_on_an_unguarded_helper():
    """Non-régression : une fonction importée dont le corps n'appelle réellement
    aucun nom de GUARD_NAMES doit rester sans garde détecté — la résolution ne
    doit jamais sur-détecter."""
    fact = next(
        f for f in index_rest_routes(REPO) if (f.method, f.path) == ("GET", "/v1/pipelines/ops")
    )
    # /v1/pipelines/ops est déclarée publique par conception (feature.public) —
    # ce test vérifie l'index brut, pas score_guard : la fonction de route
    # elle-même n'appelle aucune garde, cross-module ou non.
    assert fact.guards == frozenset()
```

- [ ] **Step 2: Run tests to verify the first one fails**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -k "imported_service or invent_guards" -v`
Expected: `test_guard_reached_through_an_imported_service_function_is_found` FAILED (les 3
routes n'ont pas encore `require_pipeline_access` dans `guards`) ;
`test_import_resolution_does_not_invent_guards_on_an_unguarded_helper` PASSED (déjà vrai
avant le changement — c'est le filet de non-régression, il doit rester vert avant ET après).

- [ ] **Step 3: Implement the cross-module resolution**

Dans `core/scripts/feature_health/rest_surface.py`, remplacer le bloc de bullets de limites du
docstring de module (lignes 16-28) :

```python
Limites assumées, pas couvertes — un futur lecteur ne doit pas sur-interpréter
un vert :
- la résolution de garde s'arrête au **même module** : un helper importé d'un
  autre module et qui porterait la garde n'est pas suivi (aucun cas réel à
  `1516a3a1`, mais rien ne l'empêche d'apparaître) ;
- profondeur 2 exactement : route → helper → garde. Une chaîne plus longue
  n'est pas suivie ;
```

par :

```python
Limites assumées, pas couvertes — un futur lecteur ne doit pas sur-interpréter
un vert :
- la résolution de garde suit un import cross-module sur **un seul saut**
  (route → fonction importée d'un autre module de `core/app` → garde appelée
  dans son corps) — patron réel depuis SP-43 (couche de service partagée
  REST↔MCP), vérifié sur `run_pipeline_service`/`create_webhook_token_service`/
  `revoke_webhook_token_service` (`app/pipelines/service.py`, spec
  2026-09-14). Une fabrique `Depends(get_x)` qui **retourne** un garde sans
  l'appeler (`return rls_scope`), invoqué ensuite via le paramètre local qui
  reçoit la dépendance, n'est PAS suivie — seul un appel direct compte ;
- profondeur 2 exactement, que le helper soit local ou importé : route →
  helper → garde. Une chaîne plus longue (route → service → sous-helper →
  garde) n'est pas suivie ;
```

Puis, juste avant `def index_rest_routes(repo: pathlib.Path) -> tuple[RouteFact, ...]:`,
ajouter :

```python
def _import_targets(tree: ast.Module, repo: pathlib.Path) -> dict[str, pathlib.Path]:
    """`{nom_local: chemin_absolu_du_module_source}` pour chaque `from app.x.y
    import a, b as c` résoluble vers un fichier réel de `core/app` — ce dépôt
    n'a pas d'imports relatifs (vérifié), donc `node.module` est toujours un
    chemin absolu en pointillés."""
    targets: dict[str, pathlib.Path] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        candidate = repo / "core" / (node.module.replace(".", "/") + ".py")
        if not candidate.is_file():
            continue
        for alias in node.names:
            targets[alias.asname or alias.name] = candidate
    return targets


_IMPORTED_MODULE_CACHE: dict[pathlib.Path, ast.Module] = {}


def _guards_in_imported_function(name: str, path: pathlib.Path) -> frozenset[str]:
    """Les noms de `GUARD_NAMES` appelés dans le corps de la fonction `name`
    définie dans le module `path` — un seul saut, jamais récursif plus loin.
    Suffisant pour le patron de couche de service introduit par SP-43 (route →
    fonction de service importée → garde), vérifié sur
    `run_pipeline_service`/`create_webhook_token_service`/
    `revoke_webhook_token_service` (`app/pipelines/service.py`), qui appellent
    chacune `require_pipeline_access(...)` — jamais suivi avant ce volet
    puisque ni la route ni la fonction de service ne vivent dans le même
    fichier que l'appel visible."""
    tree = _IMPORTED_MODULE_CACHE.get(path)
    if tree is None:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        _IMPORTED_MODULE_CACHE[path] = tree
    function = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name
        ),
        None,
    )
    if function is None:
        return frozenset()
    return _called_names(function) & GUARD_NAMES
```

Puis, dans `index_rest_routes`, remplacer :

```python
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
```

par :

```python
        local_functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        imports = _import_targets(tree, repo)
        for node in ast.walk(tree):
            for decorator in _route_decorators(node):
                called = _called_names(node)
                dependencies = _depends_names(node)
                guards = called & GUARD_NAMES
                for name in called | dependencies:
                    helper = local_functions.get(name)
                    if helper is not None and helper is not node:
                        guards |= _called_names(helper) & GUARD_NAMES
                        continue
                    source = imports.get(name)
                    if source is not None:
                        guards |= _guards_in_imported_function(name, source)
                if AUTH_REQUIRED in dependencies:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py -v`
Expected: 19 passed, 0 failed.

- [ ] **Step 5: Confirm both target features now score ≥ 90 at the sub-score level**

Run:
```bash
cd core && PYTHONPATH=. python3 - <<'EOF'
import pathlib
from scripts.feature_health.model import load_inventory
from scripts.feature_health.rest_surface import index_rest_routes, score_guard

repo = pathlib.Path("..").resolve()
routes = index_rest_routes(repo)
features = load_inventory(repo / "docs/revue/inventaire-fonctionnalites.jsonl")
ids = {
    "features-ogc-api-tuiles-vectorielles-mvt-servies-par-le-cur-avec-rls",
    "automatisation-lancer-l-execution-d-un-pipeline-a-la-demande",
}
for f in features:
    if f.identifier in ids:
        print(f.identifier, score_guard(f, routes).value)
EOF
```
Expected: les deux lignes affichent `100.0`.

- [ ] **Step 6: Run the full feature_health test suite**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_health_rest_surface.py tests/test_feature_health_scoring.py tests/test_feature_inventory.py -v`
Expected: tous verts.

- [ ] **Step 7: Commit**

```bash
git add core/scripts/feature_health/rest_surface.py core/tests/test_feature_health_rest_surface.py
git commit -m "$(cat <<'EOF'
fix(core): résoudre les gardes à travers un import cross-module (un saut)

run_pipeline_service/create_webhook_token_service/revoke_webhook_token_service
(app/pipelines/service.py) appellent require_pipeline_access() dans leur
propre corps, mais routes.py ne les résolvait pas — la garde vit
désormais souvent dans une couche de service importée (SP-43), pas
seulement dans un helper du même fichier. Généralise la résolution déjà
en place plutôt que d'ajouter des cas particuliers.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

### Task 3: Corriger la preuve d'inventaire de « Restaurer une sauvegarde »

**Files:**
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl:288`

**Interfaces:**
- Consomme : rien de nouveau — `deploy/backup/restore.sh` (SP-59) et la règle de test
  `test_restore_recreates_every_bucket_backup_mirrors` déjà présente dans
  `core/tests/test_deployability.py`.
- Produit : la ligne d'inventaire `sauvegarde-restaurer-une-sauvegarde` avec une `preuve`
  vérifiable par `core/tests/test_feature_inventory.py::test_every_proof_path_still_exists`.

**Contexte vérifié** : `deploy/backup/restore.sh` existe et est réel (SP-59, 2026-09-06),
couvert par `core/tests/test_deployability.py::test_restore_recreates_every_bucket_backup_mirrors`
(constante `RESTORE_SH = REPO / "deploy/backup/restore.sh"`, ligne 72) et par
`core/tests/test_restore_script.py` (suite dédiée, doubles `pg_restore`/`mc`). La ligne
d'inventaire actuelle pointe encore vers `deploy/backup/entrypoint.sh` et affirme qu'« aucun
script de restauration n'existe » — vrai avant SP-59, faux depuis.

- [ ] **Step 1: Confirm the current (stale) proof scores zero**

Run:
```bash
cd core && PYTHONPATH=. python3 -c "
import pathlib
from scripts.feature_health.coverage_facts import deployability_rules
repo = pathlib.Path('..').resolve()
rules = deployability_rules(repo)
print('entrypoint.sh rule:', rules.get('deploy/backup/entrypoint.sh'))
print('restore.sh rule:', rules.get('deploy/backup/restore.sh'))
"
```
Expected: `entrypoint.sh rule: None` (aucune règle — c'est pourquoi le sous-score `tests` de
cette fonctionnalité vaut 0.0 aujourd'hui) ; `restore.sh rule:
('test_restore_recreates_every_bucket_backup_mirrors',)` (la règle existe déjà, seule la
preuve d'inventaire ne pointe pas encore dessus).

- [ ] **Step 2: Edit the inventory line**

Dans `docs/revue/inventaire-fonctionnalites.jsonl`, la ligne 288 commence par
`{"id": "sauvegarde-restaurer-une-sauvegarde", ...}`. Remplacer les champs `"description"`,
`"preuve"` et `"note_sp42"` (garder `"note_sp42_date": "2026-09-04"` inchangé — c'est la date de
l'audit SP-42 d'origine, pas une date de dernière modification) :

Ancien fragment :
```json
"description": "Aucun script de restauration n'existe dans deploy/backup/ (seuls backup.sh, entrypoint.sh, retention.py, test_retention.py et le Dockerfile y figurent) — la restauration n'est ni scriptée ni automatisée dans cette tranche.", "preuve": ["deploy/backup/entrypoint.sh"], "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []}, "publiques": [], "priorite": "haute", "priorite_source": "amorcage-sp42", "note_sp42": "Le mécanisme de création de sauvegardes est complet et chiffré, mais rien dans ce dépôt ne restaure automatiquement une archive .tar.gz.age : le succès d'une restauration n'est jamais vérifié mécaniquement. Preuve corrigée en Tâche 3 : l'ancienne référence était un listing de répertoire. entrypoint.sh:12 est l'unique invocation du conteneur de sauvegarde (`/usr/local/bin/backup.sh` dans la boucle quotidienne) — aucun chemin symétrique de restauration n'existe, et `grep -rin restaur` sur deploy/, scripts/, docs/*.md et README.md ne renvoie que deux commentaires de backup.sh:29,31 qui parlent d'une restauration future, jamais du code qui la ferait."
```

Nouveau fragment :
```json
"description": "deploy/backup/restore.sh (SP-59, GAP-70) restaure Postgres (pg_restore --clean --if-exists --no-owner) et MinIO (mc mirror, un bucket par bucket sauvegardé) à partir d'une archive .tar.gz.age déchiffrée — un test de parité (test_restore_recreates_every_bucket_backup_mirrors) garantit qu'il recrée les 7 buckets que backup.sh sauvegarde.", "preuve": ["deploy/backup/restore.sh"], "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []}, "publiques": [], "priorite": "haute", "priorite_source": "amorcage-sp42", "note_sp42": "Preuve corrigée le 2026-09-14 (spec 2026-09-14-priorite-haute-sante-90-design.md) : ce texte affirmait qu'aucun script de restauration n'existait et pointait vers entrypoint.sh — obsolète depuis SP-59 (2026-09-06), qui a livré deploy/backup/restore.sh et son test de parité, jamais répercuté dans cet inventaire (piège CLAUDE.md n°12). Note historique conservée : le mécanisme de création de sauvegardes était déjà complet et chiffré avant SP-59 ; c'était la restauration elle-même qui manquait."
```

- [ ] **Step 3: Verify the JSON line is still valid and the proof path resolves**

Run:
```bash
cd core && PYTHONPATH=. python3 -c "
import pathlib
from scripts.feature_health.model import load_inventory
repo = pathlib.Path('..').resolve()
features = load_inventory(repo / 'docs/revue/inventaire-fonctionnalites.jsonl')
f = next(x for x in features if x.identifier == 'sauvegarde-restaurer-une-sauvegarde')
print(f.proofs)
assert (repo / f.proofs[0]).exists()
print('OK')
"
```
Expected: `('deploy/backup/restore.sh',)` puis `OK`.

- [ ] **Step 4: Run the inventory guard-rail test**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_inventory.py -v`
Expected: tous verts, en particulier `test_every_proof_path_still_exists`.

- [ ] **Step 5: Commit**

```bash
git add docs/revue/inventaire-fonctionnalites.jsonl
git commit -m "$(cat <<'EOF'
docs(revue): corrige la preuve périmée de « Restaurer une sauvegarde »

deploy/backup/restore.sh existe et est testé depuis SP-59 (2026-09-06) ;
la ligne d'inventaire pointait toujours vers l'ancien entrypoint.sh et
affirmait qu'aucun script de restauration n'existait — jamais mis à
jour depuis, classe de dérive documentée par CLAUDE.md (piège n°12).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

### Task 4: Élargir la preuve d'inventaire du worker CDC et mesurer sa vraie couverture

**Files:**
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl:253`
- Possibly modify: `core/tests/test_cdc_consumer.py` ou `core/tests/test_cdc_backfill.py` (si
  la mesure du Step 4 reste sous 90 en moyenne)

**Interfaces:**
- Consomme : `core/app/cdc/consumer.py`, `storage.py`, `parquet_writer.py`, `buffer.py`
  (fichiers existants, inchangés par ce plan sauf éventuellement des tests supplémentaires).
- Produit : la ligne d'inventaire `federation-des-donnees-fraicheur-quasi-temps-reel...` avec
  une `preuve` élargie, vérifiée par une mesure réelle de couverture (pas supposée).

**Contexte vérifié, sans postgis (cette session n'a pas de conteneur `postgis-test`
disponible)** — `PYTHONPATH=. uv run pytest tests/test_cdc_consumer.py tests/test_cdc_storage.py
tests/test_cdc_parquet_writer.py tests/test_cdc_buffer.py tests/test_cdc_compaction.py
tests/test_cdc_backfill.py tests/test_cdc_shutdown.py tests/test_cdc_main.py -m "not postgis"
--basetemp=/tmp/gs-cdc-verify --cov=app/cdc --cov-report=term-missing` (43 passed, 0 error, une
fois `--basetemp` pointé sur un répertoire possédé par l'utilisateur courant — le `/tmp/
pytest-of-<user>` par défaut peut être root-owned par un conteneur d'une session antérieure,
piège CLAUDE.md déjà documenté) donne :

| Fichier | Couverture sans postgis |
|---|---|
| `buffer.py` | 100 % |
| `parquet_writer.py` | 100 % |
| `storage.py` | 97 % |
| `compaction.py` | 98 % |
| `backfill.py` | 64 % |
| `consumer.py` | 45 % |
| `main.py` | 44 % |

Les lignes non couvertes de `consumer.py` (121-137, 205-223, 251-276) sont exactement
`ensure_replication_slot`/`_start_replication_with_retry`/`stream_changes` — la réplication
logique Postgres réelle, gérée par `core/tests/test_cdc_consumer_postgis.py`
(`pytest.mark.postgis`, exclu de la mesure ci-dessus faute de conteneur). `main.py` n'est **pas**
inclus dans la `preuve` élargie ci-dessous (reste point d'entrée/câblage, peu de logique propre —
conforme à la spec §3, B.2) : la preuve élargie se limite aux 4 fichiers qui portent
effectivement le comportement décrit par la fonctionnalité.

- [ ] **Step 1: Edit the inventory line**

Dans `docs/revue/inventaire-fonctionnalites.jsonl`, ligne 253
(`"id": "federation-des-donnees-fraicheur-quasi-temps-reel-des-donnees-pour-l-analytique-"`),
remplacer le champ `"preuve"` et ajouter une note :

Ancien fragment :
```json
"preuve": ["core/app/cdc/main.py"], "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []}, "publiques": [], "priorite": "haute", "priorite_source": "amorcage-sp42", "note_sp42": "Fonctionnalité invisible en tant que telle pour l'utilisateur : c'est le mécanisme qui rend correctes les deux fonctionnalités analytiques ci-dessus. Pas de surface directe, donc ui/api/mcp à false par construction."
```

Nouveau fragment :
```json
"preuve": ["core/app/cdc/consumer.py", "core/app/cdc/storage.py", "core/app/cdc/parquet_writer.py", "core/app/cdc/buffer.py"], "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []}, "publiques": [], "priorite": "haute", "priorite_source": "amorcage-sp42", "note_sp42": "Fonctionnalité invisible en tant que telle pour l'utilisateur : c'est le mécanisme qui rend correctes les deux fonctionnalités analytiques ci-dessus. Pas de surface directe, donc ui/api/mcp à false par construction. Preuve élargie le 2026-09-14 (spec 2026-09-14-priorite-haute-sante-90-design.md) : ne citait que main.py (point d'entrée, peu de logique propre) alors que le comportement décrit ci-dessus (consommation du flux logique, écriture GeoParquet, déduplication par _lsn) vit dans consumer.py/storage.py/parquet_writer.py/buffer.py, chacun couvert par un fichier de test dédié — main.py reste hors preuve, toujours peu de logique propre."
```

- [ ] **Step 2: Start a local postgis-test container with logical replication enabled**

Run:
```bash
docker build -t geostudio-postgis-ci:latest deploy/postgis
docker run -d --name gs-plan-postgis \
  -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis_test \
  -p 5433:5432 geostudio-postgis-ci:latest \
  -c wal_level=logical -c output_plugin_libraries=wal2json,pgoutput,test_decoding
for i in $(seq 1 30); do docker exec gs-plan-postgis pg_isready -U gis && break; sleep 2; done
```
Expected: `gs-plan-postgis:5433 - accepting connections` dans les 60 secondes.

- [ ] **Step 3: Measure real coverage including postgis-marked tests**

Run:
```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5433/gis_test" \
  PYTHONPATH=. uv run pytest tests/test_cdc_consumer.py tests/test_cdc_consumer_postgis.py \
  tests/test_cdc_storage.py tests/test_cdc_parquet_writer.py tests/test_cdc_buffer.py \
  --basetemp=/tmp/gs-cdc-verify --cov=app/cdc/consumer --cov=app/cdc/storage \
  --cov=app/cdc/parquet_writer --cov=app/cdc/buffer --cov-report=term-missing -v
```
Expected: tous les tests passent (y compris ceux marqués `postgis`, plus skippés). Noter le
pourcentage de couverture affiché pour chacun des 4 fichiers.

- [ ] **Step 4: Decide — proof widening alone, or additional tests needed**

Calculer la moyenne simple des 4 pourcentages relevés au Step 3.

- **Si la moyenne ≥ 90** : la correction de preuve seule suffit, passer au Step 5 sans
  modifier aucun fichier de test.
- **Si la moyenne < 90** : identifier le(s) fichier(s) le(s) moins couvert(s) (`consumer.py`
  est le candidat le plus probable au vu de la mesure sans-postgis, en particulier les lignes
  restées hors `test_cdc_consumer_postgis.py` — comparer les lignes `Missing` du rapport du
  Step 3 à celles listées au Step 0 de ce Step, 121-137/205-223/251-276, pour voir lesquelles
  restent réellement non couvertes une fois postgis inclus). Ajouter, dans
  `core/tests/test_cdc_consumer.py` (fichier existant, patron déjà en place dans ce fichier :
  tests unitaires avec des doubles `psycopg2`/curseur factices, pas de vraie connexion), un cas
  de test par ligne critique non couverte restante (ex. le chemin `ObjectInUse` avec succès à
  la dernière tentative de `ensure_replication_slot`, ou le chemin `extra` message de
  `stream_changes`) — ne jamais réduire le périmètre de la `preuve` pour gonfler la moyenne à
  la place. Documenter dans le message de commit les lignes exactes couvertes par les tests
  ajoutés.

- [ ] **Step 5: Clean up the local container**

Run: `docker rm -f gs-plan-postgis`

- [ ] **Step 6: Verify the inventory JSON is still valid**

Run:
```bash
cd core && PYTHONPATH=. python3 -c "
import pathlib
from scripts.feature_health.model import load_inventory
repo = pathlib.Path('..').resolve()
features = load_inventory(repo / 'docs/revue/inventaire-fonctionnalites.jsonl')
f = next(x for x in features if x.identifier == 'federation-des-donnees-fraicheur-quasi-temps-reel-des-donnees-pour-l-analytique-')
print(f.proofs)
for p in f.proofs:
    assert (repo / p).exists(), p
print('OK')
"
```
Expected: 4 chemins affichés, puis `OK`.

- [ ] **Step 7: Run the inventory guard-rail test**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_inventory.py -v`
Expected: tous verts.

- [ ] **Step 8: Commit**

```bash
git add docs/revue/inventaire-fonctionnalites.jsonl
# + core/tests/test_cdc_consumer.py si le Step 4 a ajouté des tests
git commit -m "$(cat <<'EOF'
docs(revue): élargit la preuve du worker CDC aux fichiers qui portent le comportement

La preuve ne citait que core/app/cdc/main.py (point d'entrée, peu de
logique propre) — le comportement décrit (consommation du flux
logique, écriture GeoParquet, déduplication par _lsn) vit dans
consumer.py/storage.py/parquet_writer.py/buffer.py, chacun couvert par
un fichier de test dédié, mesuré avec un conteneur postgis réel
(wal_level=logical) pour inclure les tests marqués postgis.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

### Task 5: Couverture de `DataSourcePanel.tsx` — 7 tests ciblés

**Files:**
- Modify: `shell/src/builder/DataSourcePanel.test.tsx`

**Interfaces:**
- Consomme : `DataSourcePanel` (`shell/src/builder/DataSourcePanel.tsx`, inchangé — aucune
  ligne de production n'est modifiée par cette tâche), les clés i18n `dataSourcePanel.fieldAria`
  = « Champ agrégé (source {id}) », `measureFieldAria` = « Champ mesure {n} (source {id}) »,
  `measureAggAria` = « Agrégation mesure {n} (source {id}) », `measurePercentileLabel` =
  « Centile mesure {n} (source {id}) », `removeMeasureAria` = « Retirer la mesure {n} de {id} »,
  `promoteAria` = « Promouvoir en dataset partagé {id} », `promotingLabel` = « Promotion… »,
  `emptySources` = « Aucune source. » (`shell/src/i18n/catalog.fr.ts`, vérifiées, inchangées).

**Contexte vérifié** : la note d'inventaire `note_sp42` de
`builder-donnees-panneau-des-sources-de-donnees-features-statistics-static` (« aucun champ
n'apparaît pour saisir les enregistrements [statiques] ») est déjà obsolète — `StaticRecordRow`
existe et 3 tests le couvrent déjà (SP-52). Le score 89.7 vient de la couverture de lignes
mesurée de `DataSourcePanel.tsx` (82.75 %, confirmé par `npx vitest run
src/builder/DataSourcePanel.test.tsx --coverage --coverage.include='src/builder/
DataSourcePanel.tsx'`). Les 7 tests ci-dessous ont été **vérifiés en session** (ajoutés
temporairement, exécutés, retirés avant ce commit) : ils font passer la couverture de lignes à
98.27 % (61/62 statements, 47/48 fonctions).

- [ ] **Step 1: Run coverage to confirm the current baseline**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx --coverage --coverage.include='src/builder/DataSourcePanel.tsx'`
Expected: `Lines : 82.75%` (58 lignes, 48 couvertes), 22 tests passed.

- [ ] **Step 2: Add the 7 tests**

À la fin de `shell/src/builder/DataSourcePanel.test.tsx` (après le dernier test existant,
`"removing a record drops it from query.records"`), ajouter :

```tsx
test("edits the default aggregated field of a statistics source", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Champ agrégé (source s1)"), "p");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.field).toBe("p");
});

test("edits a measure's field", async () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "count", measures: [{ agg: "sum", field: "" }] },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Champ mesure 1 (source s1)"), "p");
  const last = (onChange.mock.calls.at(-1)![0] as DataSource[])[0];
  expect(last.query.measures).toEqual([{ agg: "sum", field: "p" }]);
});

test("switching a measure's aggregation to percentile seeds a default centile", async () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "count", measures: [{ agg: "sum", field: "pop" }] },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);
  await userEvent.selectOptions(
    screen.getByLabelText("Agrégation mesure 1 (source s1)"),
    "percentile",
  );
  const last = (onChange.mock.calls.at(-1)![0] as DataSource[])[0];
  expect(last.query.measures).toEqual([{ agg: "percentile", field: "pop", p: 50 }]);
});

test("commits a measure's percentile via its dedicated input", () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: {
      groupBy: "region",
      agg: "count",
      measures: [{ agg: "percentile", field: "pop", p: 75 }],
    },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Centile mesure 1 (source s1)"), {
    target: { value: "95" },
  });
  const last = (onChange.mock.calls.at(-1)![0] as DataSource[])[0];
  expect(last.query.measures).toEqual([{ agg: "percentile", field: "pop", p: 95 }]);
});

test("removes a measure from a statistics source", async () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "count", measures: [{ agg: "sum", field: "pop" }] },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer la mesure 1 de s1" }));
  const last = (onChange.mock.calls.at(-1)![0] as DataSource[])[0];
  expect(last.query.measures).toEqual([]);
});

test("shows an empty state when there are no sources", () => {
  render(<DataSourcePanel sources={[]} onChange={vi.fn()} />);
  expect(screen.getByText("Aucune source.")).toBeInTheDocument();
});

test("shows a promoting label and disables the button while a promotion is in flight", () => {
  const sources: DataSource[] = [
    { id: "s1", type: "features", service: "core", layer: "parcs", query: {} },
  ];
  render(
    <DataSourcePanel sources={sources} onChange={vi.fn()} onPromote={vi.fn()} promotingId="s1" />,
  );
  const button = screen.getByRole("button", { name: "Promouvoir en dataset partagé s1" });
  expect(button).toBeDisabled();
  expect(button).toHaveTextContent("Promotion…");
});
```

- [ ] **Step 3: Run the tests and verify coverage**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx --coverage --coverage.include='src/builder/DataSourcePanel.tsx'`
Expected: 29 tests passed, `Lines : 98.27%` (57/58).

- [ ] **Step 4: Falsify one of the new tests to prove it exercises real behaviour**

Temporairement, dans `shell/src/builder/DataSourcePanel.tsx`, changer la ligne
`onClick={() => setMeasures(s, [...measuresOf(s), { agg: "sum", field: "" }])}`'s voisine de
suppression — plus simple : commenter temporairement le bloc `onClick` du bouton de suppression
de mesure (ligne ~340-345, `onClick={() => setMeasures(s, measuresOf(s).filter((_, i) => i !==
mi))}` → remplacer par `onClick={() => {}}`), relancer le test ciblé :

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx -t "removes a measure"`
Expected: FAIL (`expect(last.query.measures).toEqual([])` reçoit toujours la mesure).

Restaurer la ligne d'origine (`git checkout -- shell/src/builder/DataSourcePanel.tsx`), relancer :

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx -t "removes a measure"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/DataSourcePanel.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): couvre les mesures/champ agrégé/état vide de DataSourcePanel

7 interactions non couvertes (champ agrégé par défaut, champ/agrégation/
centile/suppression d'une mesure, état vide, libellé "Promotion…") —
82.75 % → 98.27 % de couverture de lignes, mesuré. Aucune ligne de
production touchée ; falsifié (retrait temporaire du handler de
suppression de mesure, confirmation d'échec, restauration).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

### Task 6: `scripts/install.sh` — double `docker`/`jq` + 4 scénarios de test

**Files:**
- Create: `core/tests/test_install_script.py`

**Interfaces:**
- Consomme : `scripts/install.sh` (inchangé — les échappatoires non-interactives existent
  déjà : `INSTALL_YES`, `INSTALL_PROFILES`, `INSTALL_SEED_DEMO`, `GEOSTUDIO_PUBLIC_HOST`,
  `TS_AUTHKEY`, `BACKUP_S3_ENDPOINT`, `INSTALL_ADMIN_EMAIL`), `.env.example` (gabarit copié
  tel quel comme `.env` de test — toutes les clés `set_env_var` cibles y existent déjà,
  vérifié).
- Produit : rien consommé par une autre tâche — suite de test autonome.

**Contexte vérifié en session (exécution réelle, pas supposée)** : les 4 scénarios ci-dessous
ont chacun été exécutés avec succès contre le vrai `scripts/install.sh` (copié dans un
répertoire de travail isolé, jamais le `.env`/dépôt réel) avant d'écrire ce fichier de plan —
create-admin (exit 0, `CORE_ADMIN_SUBS` écrit), idempotent-rerun (exit 0, aucun `create users`
appelé), Keycloak-timeout (exit 1 après ~60s, message d'erreur exact), sélection de profils
(`docker compose ... --profile observability up -d` bien émis). La spec anticipait 3
échappatoires manquantes à ajouter au script — **elles existent déjà toutes** (vérifié en
lisant le script en entier) ; ce volet se limite donc à écrire les tests, sans toucher
`scripts/install.sh`.

- [ ] **Step 1: Write the test file**

Créer `core/tests/test_install_script.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Comportement de scripts/install.sh (spec 2026-09-14, volet C.1).

Même patron que test_restore_script.py (SP-59) : pas de framework de test
shell dans ce dépôt, donc double de test — un exécutable `docker` et un
exécutable `jq` factices sur un PATH de test, qui journalisent leurs
arguments et renvoient des réponses canned plutôt que de toucher un vrai
Docker/Keycloak. install.sh porte déjà toutes les échappatoires
non-interactives nécessaires (INSTALL_YES, INSTALL_PROFILES/
INSTALL_SEED_DEMO, GEOSTUDIO_PUBLIC_HOST, BACKUP_S3_ENDPOINT,
INSTALL_ADMIN_EMAIL) — posées pour un usage de test jamais écrit avant ce
fichier (le commentaire de confirm() le dit littéralement) ; aucune
modification du script de production n'a été nécessaire (vérifié en
lisant le script en entier avant d'écrire ces tests)."""

import json
import os
import pathlib
import shutil
import stat
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
INSTALL_SH = REPO / "scripts/install.sh"
ENV_EXAMPLE = REPO / ".env.example"

_FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_BIN_LOG"
if [ "$1" = "compose" ]; then
  shift
  while [ "$1" = "-f" ] || [ "$1" = "--profile" ]; do shift; shift; done
  case "$1" in
    config)
      echo "${FAKE_COMPOSE_PROFILES:-}"
      exit 0
      ;;
    up)
      exit 0
      ;;
    exec)
      shift
      shift
      service="$1"
      shift
      if [ "$service" = "keycloak" ]; then
        sub="$2"
        case "$sub" in
          config)
            [ "${FAKE_KC_AUTH_FAILS:-0}" = "1" ] && exit 1
            exit 0
            ;;
          get)
            if grep -q "kcadm.sh create users" "$FAKE_BIN_LOG" 2>/dev/null; then
              echo "[{\"id\":\"created-fake-id\"}]"
            elif [ -n "${FAKE_KC_EXISTING_USER_ID:-}" ]; then
              echo "[{\"id\":\"${FAKE_KC_EXISTING_USER_ID}\"}]"
            else
              echo "[]"
            fi
            exit 0
            ;;
          create)
            exit 0
            ;;
          *)
            exit 0
            ;;
        esac
      elif [ "$service" = "core" ]; then
        if printf '%s' "$*" | grep -q "scripts.seed_demo"; then
          exit 0
        fi
        echo 401
        exit 0
      else
        exit 0
      fi
      ;;
    *)
      exit 0
      ;;
  esac
fi
exit 0
"""

_FAKE_JQ = '''#!/usr/bin/env python3
import sys, json

args = sys.argv[1:]
if args == ["--version"]:
    print("fake-jq-1.0")
    sys.exit(0)
filt = args[-1]
data = json.load(sys.stdin)


def first_id(d):
    return d[0]["id"] if d else None


if filt == ".[0].id // empty":
    value = first_id(data)
    print(value if value is not None else "")
elif filt == ".[0].id":
    print(first_id(data))
else:
    sys.exit(f"fake jq: unsupported filter {filt!r}")
'''


@pytest.fixture()
def install_workdir(tmp_path):
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    shutil.copy(INSTALL_SH, work / "scripts/install.sh")
    shutil.copy(ENV_EXAMPLE, work / ".env")
    return work


@pytest.fixture()
def fake_bin_path(tmp_path):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log_file = tmp_path / "fake-bin.log"
    log_file.write_text("")

    docker = bin_dir / "docker"
    docker.write_text(_FAKE_DOCKER)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)

    jq = bin_dir / "jq"
    jq.write_text(_FAKE_JQ)
    jq.chmod(jq.stat().st_mode | stat.S_IEXEC)

    return bin_dir, log_file


def _run_install(install_workdir, fake_bin_path, *, extra_env=None, timeout=30):
    bin_dir, log_file = fake_bin_path
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_BIN_LOG"] = str(log_file)
    env["INSTALL_YES"] = "1"
    env["INSTALL_PROFILES"] = ""
    env["INSTALL_SEED_DEMO"] = "0"
    env["GEOSTUDIO_PUBLIC_HOST"] = "geostudio-test.example"
    env["TS_AUTHKEY"] = "tskey-test-fake"
    env["BACKUP_S3_ENDPOINT"] = ""
    env["INSTALL_ADMIN_EMAIL"] = "admin@test.example"
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["bash", str(install_workdir / "scripts/install.sh")],
        cwd=install_workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result, log_file.read_text()


def test_install_creates_an_admin_account_and_writes_core_admin_subs(
    install_workdir, fake_bin_path
):
    result, log = _run_install(install_workdir, fake_bin_path)

    assert result.returncode == 0, result.stderr
    assert "kcadm.sh create users" in log
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ADMIN_SUBS=created-fake-id" in env_lines


def test_install_reuses_an_existing_admin_account_idempotently(install_workdir, fake_bin_path):
    result, log = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"FAKE_KC_EXISTING_USER_ID": "existing-user-42"},
    )

    assert result.returncode == 0, result.stderr
    assert "kcadm.sh create users" not in log
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ADMIN_SUBS=existing-user-42" in env_lines


def test_install_fails_cleanly_when_keycloak_never_authenticates(install_workdir, fake_bin_path):
    # La boucle de retry réelle du script (30 tentatives × 2s) s'exécute en
    # entier — ~60s, volontairement non raccourcie (pas de knob dédié dans
    # install.sh, et en ajouter un romprait le patron déjà en place pour ne
    # pas modifier le script de production dans ce volet).
    result, _ = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={"FAKE_KC_AUTH_FAILS": "1"},
        timeout=90,
    )

    assert result.returncode == 1
    assert "Échec d'authentification" in result.stdout
    env_lines = (install_workdir / ".env").read_text().splitlines()
    assert "CORE_ADMIN_SUBS=" in env_lines  # jamais écrit


def test_install_selects_profiles_and_launches_the_stack_with_them(
    install_workdir, fake_bin_path
):
    result, log = _run_install(
        install_workdir,
        fake_bin_path,
        extra_env={
            "INSTALL_PROFILES": "observability",
            "FAKE_COMPOSE_PROFILES": "observability\netl",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "--profile observability up -d" in log
```

- [ ] **Step 2: Run the new tests**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_install_script.py -v`
Expected: 4 passed (le troisième, `..._keycloak_never_authenticates`, prend ~60s — attendu et
documenté en commentaire).

- [ ] **Step 3: Falsify one test to confirm it exercises real behaviour**

Temporairement, dans le fake `docker` du fichier de test, changer
`elif [ -n "${FAKE_KC_EXISTING_USER_ID:-}" ]; then echo "[{\"id\":\"${FAKE_KC_EXISTING_USER_ID}\"}]"`
en supprimant la branche `elif` (pour forcer un `[]` même en scénario idempotent), relancer :

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_install_script.py -k idempotently -v`
Expected: FAIL (`kcadm.sh create users` apparaît alors dans le log, contredisant l'assertion
`assert "kcadm.sh create users" not in log`).

Restaurer la branche `elif` d'origine, relancer :

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_install_script.py -k idempotently -v`
Expected: PASS.

- [ ] **Step 4: Confirm no production file was touched**

Run: `git status --short scripts/install.sh`
Expected: aucune sortie (fichier inchangé).

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_install_script.py
git commit -m "$(cat <<'EOF'
test(core): couvre install.sh avec un double docker/jq (création admin, idempotence, échec, profils)

install.sh n'avait aucun test automatisé malgré des échappatoires
non-interactives déjà posées pour cet usage précis (INSTALL_YES/
INSTALL_PROFILES/INSTALL_SEED_DEMO/GEOSTUDIO_PUBLIC_HOST/
INSTALL_ADMIN_EMAIL) — même patron que test_restore_script.py (SP-59) :
double docker/jq journalisant ses arguments, jamais de vrai Docker/
Keycloak touché. Aucune modification du script de production.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

### Task 7: Régénérer le bilan et relever le plancher CI

**Files:**
- Modify: `docs/revue/bilan-fonctionnalites.html`, `docs/revue/bilan-fonctionnalites.md`,
  `docs/revue/historique-sante.jsonl`
- Modify: `core/scripts/feature_health_thresholds.json`

**Interfaces:**
- Consomme : toutes les tâches précédentes (1-6) doivent être committées.
- Produit : bilan à jour + plancher CI relevé — dernier geste du plan, rien n'en dépend.

- [ ] **Step 1: Start a local postgis-test container (logical replication, as Task 4)**

Run:
```bash
docker run -d --name gs-plan-postgis-final \
  -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis_test \
  -p 5433:5432 geostudio-postgis-ci:latest \
  -c wal_level=logical -c output_plugin_libraries=wal2json,pgoutput,test_decoding
for i in $(seq 1 30); do docker exec gs-plan-postgis-final pg_isready -U gis && break; sleep 2; done
```

- [ ] **Step 2: Run the full core test suite with coverage**

Run:
```bash
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5433/gis_test" \
  PYTHONPATH=. uv run pytest --cov=app --cov-report=xml:coverage.xml --basetemp=/tmp/gs-plan-final -q
```
Expected : 0 failed (les 5 `qgis`-marked skippent, sans sidecar — attendu, cf. CLAUDE.md).
`coverage.xml` produit.

- [ ] **Step 3: Run the full shell test suite with coverage**

Run: `cd shell && rm -rf dist dist-export && npm run test -- --coverage`
Expected: 0 failed. `shell/coverage/coverage-summary.json` produit.

- [ ] **Step 4: Run the CI floor gate directly**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_inventory.py::test_health_floors_hold -v`
Expected: PASSED — les deux planchers (`plancher_priorite_haute` actuel 40,
`plancher_sante_mediane` 96) tiennent toujours (large marge, ce test ne peut que passer plus
facilement après ce plan).

- [ ] **Step 5: Regenerate the bilan**

Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write`

- [ ] **Step 6: Verify the 7 target lines are all ≥ 90**

Run:
```bash
awk -F'|' 'NR>82 && $7 ~ /haute/ { gsub(/^ +| +$/,"",$5); if ($5+0 < 90) print }' \
  ../docs/revue/bilan-fonctionnalites.md
```
Expected: aucune sortie (0 ligne priorité haute sous 90).

- [ ] **Step 7: Read the new measured floor for high-priority features**

Run:
```bash
awk -F'|' 'NR>82 && $7 ~ /haute/ { gsub(/^ +| +$/,"",$5); print $5 }' \
  ../docs/revue/bilan-fonctionnalites.md | sort -n | head -1
```
Note la valeur affichée — c'est le nouveau plancher mesuré.

- [ ] **Step 8: Raise the CI threshold to the measured value (never rounded up)**

Ouvrir `core/scripts/feature_health_thresholds.json`. Remplacer `"plancher_priorite_haute": 40`
par la valeur lue au Step 7, tronquée à l'entier inférieur (jamais arrondie à la hausse — même
doctrine que `.coverage-threshold`/`.bundle-size-threshold`). Exemple si la valeur mesurée est
`93.94` : `"plancher_priorite_haute": 93`.

- [ ] **Step 9: Re-run the floor gate to confirm it still passes at the new threshold**

Run: `cd core && PYTHONPATH=. uv run pytest tests/test_feature_inventory.py::test_health_floors_hold -v`
Expected: PASSED.

- [ ] **Step 10: Review the full bilan diff, not just the 7 targeted lines**

Run: `git diff --stat docs/revue/bilan-fonctionnalites.md docs/revue/bilan-fonctionnalites.html`

Lire le diff complet de `docs/revue/bilan-fonctionnalites.md` (pas seulement `--stat`) :
confirmer qu'aucune autre fonctionnalité priorité haute n'a régressé (les volets A.1/A.2 ne
peuvent que faire monter des scores de garde, jamais les faire baisser — vérifier que c'est
bien ce qu'on observe).

- [ ] **Step 11: Clean up the local container**

Run: `docker rm -f gs-plan-postgis-final`

- [ ] **Step 12: Commit**

```bash
git add core/scripts/feature_health_thresholds.json docs/revue/bilan-fonctionnalites.html \
  docs/revue/bilan-fonctionnalites.md docs/revue/historique-sante.jsonl
git commit -m "$(cat <<'EOF'
docs(revue): régénère le bilan, relève le plancher priorité haute à <VALEUR>

Les 7 fonctionnalités priorité haute sous 90 (installeur/premier admin/
restauration/CDC/tuiles MVT/panneau Statique/lancement de pipeline)
sont maintenant toutes ≥ 90. plancher_priorite_haute (40 → <VALEUR>)
verrouille le résultat en CI plutôt que de le laisser dériver
silencieusement (piège CLAUDE.md n°12).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TgDwCsaYnqwLygg5322Tei
EOF
)"
```

---

## Self-Review

**Spec coverage** : Volet A.1 → Tâche 1. Volet A.2 (renommé « cross-module », le mécanisme
« fabrique `Depends` qui retourne un garde » s'est révélé inutile une fois `get_readable_
collection` ajouté à `GUARD_NAMES` — vérifié en session, `get_readable_collection` est déjà
appelé directement dans le corps de route, aucune résolution de fabrique n'était nécessaire) →
Tâche 2. Volet B.1 → Tâche 3. Volet B.2 → Tâche 4. Volet C.1 → Tâche 6 (simplifié : aucune
échappatoire à ajouter, toutes existaient déjà — vérifié en lisant `scripts/install.sh` en
entier). Volet C.2 → Tâche 5. Volet D → Tâche 7.

**Écart au texte de la spec, documenté ici plutôt que suivi à la lettre** : la spec (§4,
« C.1 ») anticipait l'ajout de 3 échappatoires (`INSTALL_PUBLIC_HOST`/`INSTALL_FUNNEL`/
`INSTALL_BACKUP_TARGET`) à `scripts/install.sh`. En lisant le script en entier avant d'écrire
ce plan, les 3 fonctions concernées (`prompt_public_host`, `activate_funnel`,
`prompt_backup_target`) se sont révélées déjà entièrement pilotables sans prompt via
`GEOSTUDIO_PUBLIC_HOST`/`TS_AUTHKEY`/`BACKUP_S3_ENDPOINT` — vérifié par une exécution réelle de
bout en bout (voir Tâche 6, 4 scénarios exécutés en session avant d'écrire le plan). Aucune
modification de `scripts/install.sh` n'est donc nécessaire.

**Placeholder scan** : aucun « TBD »/« add tests for X sans le code » — la seule branche
conditionnelle du plan (Tâche 4, Step 4 : « si la moyenne < 90, ajouter des tests ») donne un
fichier cible concret, des lignes concrètes déjà identifiées (121-137/205-223/251-276 de
`consumer.py`) et un patron de test déjà en place à suivre — dépend d'une mesure qui ne peut
être faite qu'avec un vrai conteneur postgis, indisponible pendant l'écriture de ce plan.

**Type consistency** : `GUARD_NAMES`, `score_guard`, `index_rest_routes` gardent leurs
signatures exactes à travers les Tâches 1-2 ; `_import_targets`/`_guards_in_imported_function`
introduites en Tâche 2, consommées uniquement par `index_rest_routes` dans le même fichier.

---

**Plan complete and saved to `docs/superpowers/plans/2026-09-14-priorite-haute-sante-90.md`.**
Two execution options:

**1. Subagent-Driven (recommended)** — je dispatche un subagent frais par tâche, revue entre
chaque tâche, itération rapide.

**2. Inline Execution** — j'exécute les tâches dans cette session avec `executing-plans`,
exécution par lots avec points de contrôle.

Which approach?
