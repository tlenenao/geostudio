# Fix — final whole-branch review, SP-15h : `list_configs_by_kind` tolère une config non validable

## Constat (finding Important)

`core/app/configs/repository.py::list_configs_by_kind(session, kind)` balaie les
configs de tous les tenants pour un `kind` donné et appelle
`BuilderConfig.model_validate(revision.data)` sans filet sur chaque ligne. Une
seule config `kind="pipeline"` corrompue (édition manuelle en base, ou
durcissement futur du schéma `BuilderConfig`) fait remonter une
`pydantic.ValidationError` non rattrapée à travers `pipelines_repo.
list_due_pipelines` jusqu'à `run_pipeline_sweep_task` (job périodique toutes
les 5 min, tous tenants confondus) — plantant tout le balayage pour **tous**
les tenants, silencieusement (seule trace : log worker).

Analogue `harvest.list_due_sources` : pas de mode de panne équivalent, car il
itère des lignes ORM typées sans re-valider du JSON stocké.

## Fix implémenté

Dans `list_configs_by_kind`, le seul appel `BuilderConfig.model_validate(...)`
est enveloppé dans un `try/except ValidationError` : sur échec, un
`logger.warning(...)` (message français, identifiant `item_id`/`tenant_id`/
`kind`) est émis et la boucle `continue` au record suivant au lieu de
propager. Signature et type de retour inchangés. Aucune autre fonction
touchée (notamment pas `list_due_pipelines`) — le fix est posé à la source
commune, bénéficiant à tout consommateur présent/futur de ce helper
cross-tenant.

**Choix `ValidationError` plutôt que `Exception` large** : le seul chemin de
panne documenté et reproductible pour `BuilderConfig.model_validate` sur un
JSON déjà désérialisé (colonne `JSON` SQLAlchemy) est une `ValidationError`
pydantic (mismatch de type/forme/contrainte). Un `except Exception` masquerait
aussi des bugs de programmation réels (ex. `AttributeError` dans un futur
validator custom) sous un simple "config ignorée", ce qui serait pire pour le
diagnostic. Champ ouvert : si `BuilderConfig` gagnait un jour un validator
levant une exception non-pydantic, il faudrait élargir le `except` — non
observé aujourd'hui (aucun validator du schéma ne lève autre chose que
`ValueError`, que pydantic re-enveloppe en `ValidationError`).

## Fichiers modifiés

- `core/app/configs/repository.py` — import `logging`, `ValidationError`,
  déclaration du logger de module, `try/except` autour du seul appel
  `model_validate` dans `list_configs_by_kind`.
- `core/tests/test_repository.py` — nouveau test
  `test_list_configs_by_kind_skips_one_unvalidatable_config`.

## Preuve RED/GREEN

**RED** (avant fix, test seul) :
```
E           pydantic_core._pydantic_core.ValidationError: 1 validation error for BuilderConfig
E           pipeline
E             Input should be a valid dictionary or instance of PipelinePayload [type=model_type, input_value='not-a-valid-shape', input_type=str]
app/configs/repository.py:101: ValidationError
FAILED tests/test_repository.py::test_list_configs_by_kind_skips_one_unvalidatable_config
```

**GREEN** (après fix) :
```
cd core && uv run pytest tests/test_repository.py tests/test_pipeline_repository.py tests/test_pipeline_sweep.py -v
...
37 passed in 1.51s
```
Le nouveau test vérifie : (1) la config `item-bad` corrompue (donnée
directement patchée sur `ConfigRevision.data` via l'ORM, car `create_config`
n'écrit que du JSON valide) est absente du résultat ; (2) la config
`item-good` valide est bien retournée ; (3) aucune exception ne remonte ;
(4) un warning contenant `item-bad` est bien loggé (`caplog.at_level
("WARNING")`).

## Auto-revue

- Portée strictement respectée : un seul `try/except` autour du seul appel
  visé, pas de retry, pas de dead-letter, signature/type de retour intacts.
- `list_due_pipelines` (`core/app/pipelines/repository.py`) non touché — testé
  transitivement par `tests/test_pipeline_repository.py` et
  `tests/test_pipeline_sweep.py`, tous verts.
- Message de log en français, conforme à la convention déjà en place dans
  `app/harvest/service.py` (`logger.warning("...", args)` %-style, pas
  d'f-string).
- Pas de régression sur les 3 tests `list_configs_by_kind` préexistants ni sur
  le reste de la suite ciblée (37/37 passed).

## Préoccupations

- Aucune préoccupation bloquante. Point mineur déjà documenté ci-dessus : le
  `except ValidationError` ciblé ne couvrirait pas une future exception
  non-pydantic levée depuis un validator custom de `BuilderConfig` — à
  élargir si un tel cas apparaît un jour (aucun aujourd'hui).
