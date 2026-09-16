# OperationContract — contrat unique par op de pipeline (core-only)

**Date** : 2026-09-16
**Demande** : « est-ce qu'il y a des modifications de fond à faire sur le moteur ETL avant de se
lancer dans la construction de transformers ? » → « go » (brainstorming du chantier envisagé par
`CLAUDE.md` : « un `OperationContract` (schéma/compilateur/exécuteur/capacités/licence/moteur) au-dessus
de plusieurs moteurs »).
**Référence** : matrice de couverture FME→GeoStudio (`docs/revue/matrice-couverture-fme.jsonl`, mergée
le 2026-09-16, PR #134) — 289 lignes, dont 166 (`planned_duckdb` 90 + `planned_gdal` 55 + `planned_pdal`
16 + `planned_otb` 3 + `planned_rust` 2) exigent un moteur qui n'est câblé nulle part dans le runtime de
pipeline aujourd'hui.

## 1. Constat de départ (vérifié dans le code, pas supposé)

Le moteur de pipeline (`core/app/pipelines/`) ne connaît aujourd'hui qu'un seul moteur d'exécution :
DuckDB. `compile_transform_sql()` (`compiler.py`) est un unique `if/elif` de 11 branches qui produit
directement du SQL DuckDB (`ST_Buffer`, `ST_Transform`, `h3_latlng_to_cell`…) — l'op et le moteur sont
fusionnés dans le même bloc de code, sans point d'extension.

Le seul précédent de moteur externe est `transform.qgis` : il écrit la vue DuckDB courante dans un
GeoPackage sur un volume scratch partagé, appelle le sidecar `qgis-worker` en HTTP (allowlist de 50 ids
d'algorithme), puis rematérialise le GPKG produit en table DuckDB. Décision SP-15d déjà actée et
préservée par SP-43 : cette exécution reste **inline** dans `runtime.py`, jamais déplacée dans un
registre — c'est le seul transform avec un effet de bord (I/O + réseau).

Au moins **5 structures parallèles indexées par nom d'op**, à tenir synchrones à la main pour chaque
op, existent déjà, réparties sur 2 fichiers :
- `ops/schemas.py` : `OP_PARAMS`, `OP_KINDS`, `BINARY_OPS` ;
- `compiler.py` : `compile_transform_sql()` et `transform_output_srid()` (deux `if/elif` séparés sur les
  mêmes op, sans garde qui vérifie qu'ajouter une op met bien à jour les deux).

## 2. Périmètre

**Dans ce chantier :**
- Un type `OperationContract` unique par op (schéma/moteur/licence/modèle d'exécution/compilateur/règle
  de SRID de sortie), remplaçant les 5 structures parallèles ci-dessus pour les **19 ops déjà livrées**.
- Migration des **11 op de transformation DuckDB déjà existantes** (`filter`, `select`, `derive`,
  `aggregate`, `join`, `buffer`, `reproject`, `intersection`, `countWithin`, `h3Aggregate`, `merge`) dans
  ce contrat — mêmes fonctions, juste réorganisées, aucun changement de comportement observable.
- Entrée de métadonnées pour `transform.qgis` (moteur, licence, modèle d'exécution) — preuve que le type
  du contrat couvre un moteur externe, sans toucher à son exécution.
- Une règle formalisée et testée : **licence copyleft ⇒ modèle d'exécution `sidecar` obligatoire**,
  jamais de bindings in-process (généralisation de la décision SP-15d déjà en vigueur pour QGIS).

**Hors périmètre, explicitement (à ne pas réinterpréter en cours d'exécution) :**
- **Aucun nouveau moteur réellement câblé** (GDAL/PDAL/OTB/Rust) — zéro exécution au-delà de DuckDB+QGIS
  déjà existants. Câbler un premier moteur externe réel est un chantier séparé, ultérieur, qui
  consommera ce contrat une fois posé.
- **Aucune nouvelle op ni transformer** des 90 lignes `planned_duckdb` de la matrice — ce chantier
  prépare le terrain, ne le construit pas. Chantier séparé, ultérieur.
- **Aucun changement d'API publique.** `GET /pipelines/ops` (consommée par
  `shell/src/builder/pipeline/PipelinePalette.tsx`) garde exactement la même réponse JSON — les nouveaux
  champs (`engine`, `engine_license`, `execution_model`, `is_copyleft`) restent internes au cœur, jamais
  sérialisés par `ops_catalog()`. Diff `openapi.json`/`core-schema.d.ts` vide attendu, à vérifier plutôt
  que supposer (piège CLAUDE.md n°1). Zéro fichier `shell/` touché.
- **Licence des 7 ops readers/writers (connecteurs)** : `reader.collection`, `reader.connector.rest`,
  `reader.connector.postgres`, `reader.connector.snowflake`, `writer.collection`, `writer.export`,
  `writer.dataset` entrent dans le contrat pour `kind`/`params_schema`/`accepts_secondary_input`
  uniquement — leurs champs `engine`/`engine_license`/`compile`/`output_srid` restent à leurs valeurs par
  défaut (`engine=None`, non classé). Leurs licences composites réelles (DuckDB + dlt + SDK source par
  connecteur, déjà documentées de façon hétérogène dans la matrice FME) sont un vrai sujet, mais un
  chantier à part — `engine=None` ne déclenche jamais la règle copyleft⇒sidecar (qui ne s'applique que si
  `is_copyleft=True`, faux par défaut). Leur exécution reste entièrement dans `registries.py`
  (`READERS`/`WRITERS`), jamais touchée par ce chantier.
- **Le trou `FieldType` sans variante liste/array** (`app/collections/introspection.py`) — investigué en
  détail pendant ce brainstorming, tracé séparément comme **`GAP-83`**/**`REV-191`**
  (`docs/revue/2026-09-04-analyse-gaps.md`, `docs/revue/2026-09-04-backlog.md`). Résumé de
  l'investigation (vérifiée dans le code, pas supposée) : `transform.derive`/`transform.aggregate.metrics`
  peuvent **déjà** produire une colonne DuckDB de type LIST aujourd'hui (`expr_validation.py` ne filtre
  aucun nom de fonction), mais `writer.collection` la rejette **proprement**
  (`validate_feature()` → `unknown_property`/`invalid_type`, jamais de crash) puisqu'aucune collection ne
  peut déclarer de colonne liste. `writer.export`/`writer.dataset` ne sont pas affectés (JSON/CSV/Parquet
  tolèrent déjà les listes). Ce n'est ni un risque à mitiger dans ce chantier, ni un sujet du contrat
  d'op lui-même (aucune des 12 op DuckDB/qgis existantes n'est concernée) : le blast radius réel (DDL de
  collection, schéma JSON de formulaire, encodage MVT, export OGC Features) dépasse largement le module
  `pipelines`.

## 3. Design — structure du contrat

Nouveau fichier `core/app/pipelines/ops/contracts.py` (à côté de `schemas.py`, `qgis_algorithms.py`) :

```python
@dataclass(frozen=True)
class OperationContract:
    op: str                              # "transform.filter"
    kind: Literal["reader", "transform", "writer"]
    params_schema: type[BaseModel]       # classe déjà existante dans schemas.py
    accepts_secondary_input: bool = False
    engine: str | None = None            # "duckdb" | "qgis" | None (non classé — readers/writers)
    engine_license: str | None = None    # texte informatif, jamais parsé automatiquement
    is_copyleft: bool = False            # déclaré explicitement par l'auteur, jamais déduit
                                          # d'un parsing de engine_license (piège CLAUDE.md n°3)
    execution_model: Literal["in_process", "sidecar"] = "in_process"
    compile: Callable[..., str] | None = None       # None = exécution hors de ce contrat
    output_srid: Callable[..., int] | None = None   # None = passthrough (comportement déjà
                                                      # existant par défaut)

    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(f"'{self.op}': moteur copyleft ({self.engine}) exige execution_model='sidecar'")

OPERATIONS: dict[str, OperationContract] = {...}  # 19 entrées, une par op existante
```

- Les callables `compile`/`output_srid` référencent des fonctions qui **restent définies dans
  `compiler.py`** (même patron déjà documenté par `registries.py` pour `READERS`/`WRITERS` : agréger des
  références, jamais dupliquer un corps de fonction).
- La règle copyleft⇒sidecar est vérifiée **à la construction du dict** (donc à chaque import du module,
  pas seulement par un test dédié).
- `OP_PARAMS`/`OP_KINDS`/`BINARY_OPS` (`ops/schemas.py`) deviennent des vues dérivées de `OPERATIONS`
  (comprehensions) — conservées telles quelles pour ne casser aucun de leurs appelants existants
  (`parse_op_params()`, etc.).

## 4. Convention d'appel uniforme

Pour que `contract.compile`/`contract.output_srid` soient appelables génériquement quel que soit l'op :

- `compile(params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None) -> str`
- `output_srid(params: dict, *, input_srid: int, join_srid: int | None = None) -> int`

Les 11 branches de `compile_transform_sql` deviennent 11 fonctions privées (`_compile_filter`,
`_compile_select`, …, `_compile_merge`) — même corps qu'aujourd'hui, juste extraites de l'`if/elif`.
`transform.intersection`/`transform.countWithin`/`transform.merge` partagent déjà, dans le code réel, la
même logique de réconciliation SRID (même branche `if op in (...)` dans `transform_output_srid`) : une
seule fonction `_output_srid_reconcile_join` référencée par les trois entrées, pas de triplication.

`compile_transform_sql`/`transform_output_srid` (signatures publiques inchangées, donc `runtime.py` et
toute la suite `tests/test_pipeline_compiler.py` ne bougent pas) deviennent de fins wrappers :

```python
def compile_transform_sql(op, params, *, input_view, join_view=None, input_srid=None):
    contract = OPERATIONS.get(op)
    if contract is None or contract.compile is None:
        raise ValueError(f"'{op}' is not a transform op")
    return contract.compile(params, input_view=input_view, join_view=join_view, input_srid=input_srid)

def transform_output_srid(op, params, *, input_srid, join_srid=None):
    contract = OPERATIONS.get(op)
    if contract is None or contract.output_srid is None:
        return input_srid  # passthrough — comportement déjà existant, vérifié dans le code réel :
                            # transform_output_srid n'a AUCUNE branche d'erreur pour un op inconnu,
                            # contrairement à compile_transform_sql
    return contract.output_srid(params, input_srid=input_srid, join_srid=join_srid)
```

Comportement externe vérifié identique sur les deux cas limites déjà couverts par
`test_pipeline_compiler.py` :
- `compile_transform_sql("reader.collection", ...)` continue à lever `ValueError`.
- `transform_output_srid("transform.filter", ..., input_srid=4326)` continue à faire un passthrough
  silencieux (pas de `raise`).

## 5. `transform.qgis` — métadonnées seulement

`OPERATIONS["transform.qgis"]` :
- `compile=None` (exécution intacte dans `runtime.py`, décision SP-43 préservée) ;
- `output_srid=<fonction extraite des 3 lignes qgis de l'actuel `transform_output_srid`>` (même
  comportement : `int(p.outputSrid.rsplit(":", 1)[1])` si `outputSrid` fourni, sinon passthrough) ;
- `engine="qgis"`, `is_copyleft=True`, `execution_model="sidecar"` — la seule entrée où `__post_init__` a
  effectivement quelque chose à vérifier.
- `engine_license` : à vérifier contre la source réelle au moment d'implémenter (piège CLAUDE.md n°3 —
  ne pas deviner la chaîne, QGIS est GPL v2+ mais le libellé exact doit être confirmé, par exemple contre
  la même source déjà utilisée pour peupler `engine_license` dans la matrice FME).

## 6. Tests

**Filet existant, inchangé** : `test_pipeline_compiler.py` (boîte noire, indexé par nom d'op littéral)
doit rester vert sans aucune modification — preuve que le refactor ne change aucun comportement
observable. `test_pipeline_routes.py::test_get_pipelines_ops_returns_all_nineteen` (GAP-16) reste le
filet côté API — la réponse JSON de `ops_catalog()` ne doit pas bouger d'un octet.

**Nouveaux tests, falsifiés avant clôture** (casser exprès, confirmer l'échec, corriger — piège
CLAUDE.md n°10) :
1. La règle `is_copyleft ⇒ execution_model == "sidecar"` : un faux contrat
   `is_copyleft=True, execution_model="in_process"` doit lever `ValueError` à la construction.
2. `OPERATIONS` contient exactement les 19 clés déjà connues (mêmes 19 que `ops_catalog()` aujourd'hui,
   listées dans la ledger `.superpowers/sdd/matrice-fme-progress.md`) — garde-fou pour qu'aucune op ne
   soit silencieusement perdue pendant l'extraction des fonctions.
3. `OPERATIONS["transform.qgis"]` : `engine="qgis"`, `is_copyleft=True`, `execution_model="sidecar"`,
   `compile is None`.

## 7. Portes de qualité à repasser avant clôture

`ruff check`/`ruff format --check`/`mypy --strict` (si `app.pipelines` est dans le périmètre strict —
vérifier `core/pyproject.toml` plutôt que supposer) ; `lint-imports` (le nouveau `contracts.py` importe
`compiler.py`, pas l'inverse — vérifier l'absence de cycle) ; suite complète `core` (aucune régression
attendue, aucun fichier `shell/` touché) ; diff `openapi.json`/`core-schema.d.ts` vide.
