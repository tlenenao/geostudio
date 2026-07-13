# Task 3 (SP-8c) — rapport d'implémentation

Core — validation du scope de permissions à l'enregistrement d'une config.

## Statut

**DONE** — implémentation conforme au brief, tous les tests locaux passent
(380 passed, 62 skipped, aucune régression), `lint-imports` PASS.

## Ce qui a été implémenté

- `core/app/configs/extension_permissions.py` (nouveau) : `ExtensionPermissionError`
  et `validate_extension_permissions(session, config, *, tenant_id)`. Parcourt tous
  les `LayoutItem` d'un `BuilderConfig` (layout racine + `pages[].layout`), résout
  les widgets dont le type correspond à un `id` d'`Extension` du tenant, et pour
  chaque prop `dataSource` déclarée par cette extension dont la valeur pointe vers
  un `DataSource` du config, vérifie que `DataSource.layer` est dans
  `extension.permissions["collections"]` (ou que ce scope vaut `"all"`). Ne lève
  rien pour : widgets non-extension, extensions à scope `"all"`, props `dataSource`
  non renseignées, ou valeurs de prop qui ne référencent aucun `DataSource` connu.
  Code strictement identique à celui du brief.
- `core/app/configs/routes.py` : import de
  `ExtensionPermissionError, validate_extension_permissions` (juste après l'import
  de `BuilderConfig`), helper `_validate_extension_scope` (traduit l'exception en
  `HTTPException(400, detail=str(err))`), et un appel dans les 3 routes d'écriture :
  - `create_config` : première ligne du corps, avant `items_repo.create_item` — un
    rejet ne crée ni item ni config.
  - `update_config` : juste après `_require_access`, avant `repo.update_config`.
  - `update_config_by_item` : juste après la résolution de `existing`
    (`repo.get_config_by_item`), avant `repo.update_config`.
  `rollback_config` n'est **pas** modifié — hors périmètre volontaire (spec §Hors
  périmètre), vérifié par un test dédié.
- `core/pyproject.toml` : `app.extensions` ajouté au contrat `layers`
  d'import-linter, juste sous `app.configs` (qui l'importe désormais pour la
  première fois) et au-dessus de tout ce que `app.extensions` importe lui-même
  (`app.tenants`, `app.auth`, `app.audit`, `app.users`) — conforme à l'insertion
  demandée par le brief.
  - **Ajout non prévu par le brief, nécessaire pour que `lint-imports` passe** :
    `app.db -> app.extensions.models` manquait dans `ignore_imports`. `app/db.py`
    importe paresseusement `app.extensions.models` exactement comme il le fait déjà
    pour `app.configs.models`, `app.items.models`, etc. (pattern d'enregistrement
    des tables SQLAlchemy sur `Base.metadata`). Tant que `app.extensions` était
    absent de `layers`, import-linter ne vérifiait pas du tout ce module (trou
    pré-existant depuis SP-8b, déjà signalé dans le brief comme motivant l'ajout à
    `layers`). Dès que je l'ai ajouté à `layers`, `lint-imports` a échoué sur 6
    fausses violations transitives (`app.audit`/`app.items`/`app.tenants`/
    `app.sharing`/`app.users`/`app.auth` "important" `app.extensions` via
    `app.db`). Fixé en ajoutant `"app.db -> app.extensions.models"` à
    `ignore_imports`, miroir exact des 7 entrées déjà présentes pour les autres
    modules de modèles. Sans ce deuxième ajout, le contrat restait cassé après le
    seul changement demandé littéralement par le brief.
- `core/tests/test_configs_extension_permissions.py` (nouveau, code exact du
  brief) : 6 tests.

## TDD — RED

```
cd core && uv run pytest tests/test_configs_extension_permissions.py -v
```
Résultat (avant l'implémentation de `extension_permissions.py`/le câblage des routes) :
```
tests/test_configs_extension_permissions.py::test_create_config_rejects_extension_prop_outside_scope FAILED
tests/test_configs_extension_permissions.py::test_create_config_accepts_extension_prop_inside_scope PASSED
tests/test_configs_extension_permissions.py::test_create_config_ignores_non_extension_widgets PASSED
tests/test_configs_extension_permissions.py::test_update_config_rejects_extension_prop_outside_scope FAILED
tests/test_configs_extension_permissions.py::test_rejected_create_does_not_leave_an_orphan_item FAILED
tests/test_configs_extension_permissions.py::test_rollback_restores_a_revision_even_if_it_would_now_violate_a_narrowed_scope FAILED
========================= 4 failed, 2 passed in 1.31s ==========================
```
Conforme à l'attendu du brief (les 2 tests qui n'exercent pas la validation
passent déjà — comportement pré-existant sans changement de code — et les 4
qui l'exercent échouent pour la raison attendue : pas de 400, item orphelin
créé, rollback jamais atteint sur un 200 attendu). Le traceback
`procrastinate.exceptions.AppNotOpen` visible dans les logs de test est le
comportement fail-open pré-existant de l'enqueue d'embedding (SP-7), sans
rapport avec cette tâche.

## TDD — GREEN

```
cd core && uv run pytest tests/test_configs_extension_permissions.py -v
```
```
tests/test_configs_extension_permissions.py::test_create_config_rejects_extension_prop_outside_scope PASSED
tests/test_configs_extension_permissions.py::test_create_config_accepts_extension_prop_inside_scope PASSED
tests/test_configs_extension_permissions.py::test_create_config_ignores_non_extension_widgets PASSED
tests/test_configs_extension_permissions.py::test_update_config_rejects_extension_prop_outside_scope PASSED
tests/test_configs_extension_permissions.py::test_rejected_create_does_not_leave_an_orphan_item PASSED
tests/test_configs_extension_permissions.py::test_rollback_restores_a_revision_even_if_it_would_now_violate_a_narrowed_scope PASSED
============================== 6 passed in 1.23s ===============================
```

```
cd core && uv run lint-imports
```
```
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

Suite complète :
```
cd core && uv run pytest -q
```
```
380 passed, 62 skipped in 19.14s
```
Baseline réelle avant cette tâche (fournie par le donneur d'ordre) : 374
passed/62 skipped (après Tasks 1+2 sur cette branche). 374 + 6 nouveaux = 380
passed/62 skipped — aucune régression, delta exact attendu (le brief lui-même
annonçait 373+6=379 par erreur, arithmétique corrigée par la consigne de la
tâche à utiliser 374 comme vraie baseline).

## Fichiers modifiés

- `core/app/configs/extension_permissions.py` (nouveau)
- `core/app/configs/routes.py` (import + helper + 3 call sites)
- `core/pyproject.toml` (layers + ignore_imports)
- `core/tests/test_configs_extension_permissions.py` (nouveau)

## Self-review

- **Complétude** : tous les points du brief traités (Steps 1 à 7). Un point non
  prévu par le brief mais nécessaire a été ajouté (`ignore_imports` pour
  `app.db -> app.extensions.models`, cf. ci-dessus) — sans lui, `lint-imports`
  restait cassé après le changement de `layers` demandé explicitement par
  l'étape 5 du brief.
- **Qualité** : `extension_permissions.py` et le câblage des routes reproduisent
  le code exact du brief, sans écart. Le seul choix éditorial fait (ordre des
  deux imports `app.configs.schemas`/`app.configs.extension_permissions` dans
  `routes.py`) suit littéralement l'instruction du brief ("ajouter l'import
  après `from app.configs.schemas import BuilderConfig`").
- **Discipline** : aucun changement hors du périmètre du brief à l'exception du
  fix `ignore_imports` documenté et justifié ci-dessus (nécessaire pour
  satisfaire l'attendu explicite du brief "uv run lint-imports : pas d'erreur").
  `rollback_config` n'a pas été touché — confirmé volontaire par le test dédié,
  qui passe en l'état.
- **Tests** : les 6 tests couvrent effectivement le comportement voulu —
  rejet hors scope (create + update), acceptation dans le scope, widgets
  non-extension ignorés, absence d'item orphelin sur un create rejeté (vérifié
  en plaçant l'appel de validation en toute première ligne du handler, avant
  toute écriture), et non-régression volontaire du rollback face à un scope
  resserré après coup. Sortie pristine (aucune erreur/warning inattendue en
  dehors du log fail-open habituel de l'enqueue d'embedding, pré-existant et
  sans rapport).
- Placement de la validation vérifié ligne par ligne dans les 3 routes :
  `create_config` (avant `items_repo.create_item`), `update_config` (après
  `_require_access`, avant `repo.update_config`), `update_config_by_item`
  (après résolution de `existing`, avant `repo.update_config`) — aucune
  mutation ne peut précéder un rejet.

## Concerns

Aucun. Le seul écart par rapport au brief (ajout de l'entrée `ignore_imports`)
est mineur, cohérent avec le pattern existant (miroir exact des 7 entrées déjà
présentes pour les autres modules de modèles), documenté ci-dessus, et
strictement nécessaire pour que l'étape 6 du brief ("uv run lint-imports :
pas d'erreur") soit satisfaite — sans lui le contrat de couches restait cassé
juste après avoir appliqué l'étape 5 du brief telle quelle.

## Commit

`a7396a1` — `feat(core): rejette une config qui route une collection hors du
scope d'une extension`

## Fix: pages[] traversal test coverage

Finding (Important, revue de tâche) : `_all_layout_items`
(`core/app/configs/extension_permissions.py:37-43`) parcourt explicitement
`config.layout.items` **et** `config.pages[*].layout.items` (apps
multi-pages), mais aucun des 6 tests existants ne construit une config avec
le champ `pages` — les 6 n'utilisent que le `layout` racine à plat. La
branche de parcours `pages[]` n'était donc jamais exercée : une régression
future sur cette frontière de sécurité (ex. un refactor qui oublierait la
boucle `for page in config.pages`) aurait pu rouvrir le contournement de
scope que cette tâche ferme, sans que rien dans la CI ne le détecte.

### Ce qui a été ajouté

Dans `core/tests/test_configs_extension_permissions.py` :

- `_config_body_with_pages(data_source_layer)` : même forme que
  `_config_body`, mais place le widget `acme.gauge` **uniquement** dans
  `pages[0].layout.items` — le `layout` racine est présent (requis par le
  validateur `BuilderConfig._require_kind_payload` pour `kind="app"`, qui
  lève si `layout is None`) mais avec `items: []`. `Page` (vu dans
  `core/app/configs/schemas.py`) requiert `id: str`, `name: str` (pas
  `title`), `layout: Layout` — tous fournis.
- `test_create_config_rejects_extension_prop_outside_scope_in_pages` : POST
  `/configs` avec cette config (`layer="incidents"`, hors du scope
  `["communes"]` de `acme.gauge`) et vérifie `response.status_code == 400`
  + `"acme.gauge"` dans le detail — même style d'assertion que
  `test_create_config_rejects_extension_prop_outside_scope`.

### Preuve que le test exerce bien la branche `pages[]` (RED/GREEN)

Comme `_all_layout_items` traite déjà correctement `pages` (constat de la
revue), il n'y avait pas de bug produit à corriger — seulement une lacune de
test à combler. Preuve demandée par le brief : commenter temporairement la
boucle `pages` dans `_all_layout_items` et vérifier que le nouveau test
échoue pour la bonne raison, puis restaurer.

1. **RED (boucle `pages` désactivée)** — dans
   `core/app/configs/extension_permissions.py`, remplacé temporairement
   ```python
   for page in config.pages:
       items.extend(page.layout.items)
   ```
   par une ligne en commentaire (no-op). Lancé
   `uv run pytest tests/test_configs_extension_permissions.py -q` :
   ```
   FAILED tests/test_configs_extension_permissions.py::test_create_config_rejects_extension_prop_outside_scope_in_pages
   assert response.status_code == 400
   E       assert 201 == 400
   E        +  where 201 = <Response [201 Created]>.status_code
   1 failed, 6 passed in 0.94s
   ```
   Le layout racine ayant `items: []`, sans la boucle `pages` la validation
   ne voit aucun item, donc aucune extension à vérifier : la config est
   créée (`201`) au lieu d'être rejetée (`400`). Ceci prouve que le test ne
   passerait pas « par accident » via le layout racine — il dépend
   strictement du parcours `pages[*].layout.items`. (Le traceback
   `procrastinate.exceptions.AppNotOpen` visible dans les logs de test est
   le comportement fail-open pré-existant de l'enqueue d'embedding, SP-7,
   sans rapport avec ce test.)
2. **GREEN (boucle restaurée)** — restauré la boucle `for page in
   config.pages: items.extend(page.layout.items)` telle quelle (diff nul
   sur `extension_permissions.py` confirmé par `git diff --stat`).
   Relancé :
   ```
   7 passed in 1.31s
   ```

### Suite complète

```
cd core && uv run pytest -q
```
```
381 passed, 62 skipped in 18.81s
```
Baseline entrant dans ce fix : 380 passed/62 skipped (374 avant Task 3 + 6
tests de Task 3). +1 nouveau test = 381 passed/62 skipped — exactement le
delta attendu, aucune régression.

### Fichiers modifiés

- `core/tests/test_configs_extension_permissions.py` (1 nouveau helper +
  1 nouveau test)

### Concerns

Aucun.

### Commit

`test(core): couvre la traversée pages[] dans validate_extension_permissions`
