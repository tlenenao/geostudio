# SP-L0 « chiffres justes » : 12 défauts d'audit (AUD) — Plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE : utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher (`- [ ]`).

**Goal :** Corriger 12 défauts de l'audit du 2026-10-16 (`docs/revue/audit-2026-10-16/`) qui produisent des chiffres, des exports ou des accès faux sans erreur visible : une faille de sécurité Critical (AUD-151, terrain3d), des opérateurs de pipeline au résultat faux (AUD-005/006/007), la reprojection OGC Features hors 4326 (AUD-020), l'import de géométries invalides (AUD-129), des widgets qui présentent un échantillon comme complet (AUD-002), des exports PDF/PNG/zip faux ou impossibles (AUD-001/003/133), l'envoi S3 présigné et la photo de collecte (AUD-069), les items publiés ouvrables sans connexion (AUD-075).

**Architecture :** Douze correctifs indépendants, chacun au point unique où passent tous les appelants (piège n°14 : jumelles listées dans chaque tâche). Côté cœur : `core/app/{terrain3d,pipelines,features,ingestion,appexport,export}`. Côté shell : `shell/src/{builder/widgets,api/domains,pages,shell}`. Aucune migration. Régénération OpenAPI/TS requise par les tâches AUD-005, AUD-006 (diff possiblement vide) et AUD-133, centralisée dans la dernière tâche.

**Tech Stack :** Python 3.12 / FastAPI / SQLAlchemy / DuckDB / PostGIS / Playwright (export-worker) ; React + TypeScript + Vitest + Playwright E2E.

## Global Constraints

Tirées de `CLAUDE.md` :

- **TDD systématique** : test rouge d'abord, puis correctif, puis test vert. Un correctif de filet de test se vérifie par falsification (injecter le défaut, voir le test échouer, retirer).
- **Commits conventionnels** (`fix(core): …`, `fix(shell): …`), petits, un sujet ; un commit par tâche au minimum. Terminer chaque message par : `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- **Branche `dev` uniquement, en local.** Pas de branche `main` locale ; promotion par PR `origin/dev` → `origin/main`. Avant tout push : `git fetch` puis `git rev-list --left-right --count origin/dev...dev`.
- **Régénération OpenAPI + types TS** dès qu'une route, un modèle ou une description exposée change (voir Task 13 pour l'incantation exacte). Diff vide légitime si rien d'exposé ne change.
- **Inventaire des fonctionnalités** : aucune surface nouvelle (route REST, outil MCP, route shell) n'est prévue ; si une tâche en ajoute une, l'inscrire dans `docs/revue/inventaire-fonctionnalites.jsonl` (la CI refuse sinon).
- **Migrations** : aucune dans ce plan. Si l'une apparaît, la tester sur base non vide, dans les deux sens.
- **Tests PostGIS** : `CORE_TEST_DATABASE_URL` doit pointer un postgis-test réel (sinon ~185 tests skippent silencieusement). Sessions concurrentes sur la même base : rejouer en isolation avant de s'imputer une régression. Deux échecs intermittents connus : `test_features_rls.py::test_scope_preserves_original_sql_error`, `test_deployability.py::test_every_compose_substitution_is_documented`.
- **Portes qualité** : `cd core && uv run ruff check . && uv run ruff format --check .` ; `uv run lint-imports` ; `cd shell && npm run lint && npm run format:check`. Docs et messages utilisateur en français, code en anglais ; i18n : aucune chaîne française en dur dans le shell (clés de `shell/src/i18n/domains/`).
- **Revue par tâche ET revue finale de branche**, systématiquement (défauts de croisement entre tâches, piège n°4).
- **Suite E2E complète avant clôture** (`cd shell && npm run e2e`, doit être entièrement verte : tout rouge est réel).
- **Vérifier le code, pas le récit** (piège n°12) : chaque tâche cite des numéros de ligne relevés sur HEAD ; les relire avant d'éditer (ils dérivent après les tâches précédentes).

## Ordre d'exécution et fichiers partagés

1. **Task 1 (AUD-151)** d'abord : Critical sécurité, indépendante.
2. **Tasks 2, 3, 4 (AUD-005, AUD-006, AUD-007)** : toutes trois modifient `core/app/pipelines/compiler.py`, et 3/4 aussi `core/app/pipelines/ops/schemas.py` ; 2 et 3 partagent `core/tests/test_pipeline_compiler.py`. À exécuter **dans cet ordre, séquentiellement, jamais en parallèle** ; relire les numéros de ligne après chaque tâche.
3. **Tasks 5, 6 (AUD-020, AUD-129)** : toutes deux touchent le chemin d'import (`core/app/ingestion/importer.py` pour 020, `parsers.py` pour 129) ; séquentielles, 020 d'abord.
4. **Tasks 7, 8 (AUD-002, AUD-001)** : shell widgets ; indépendantes, mais 8 modifie `mapWidget.tsx` et `AppRuntimePage.tsx` (partagé avec Task 10).
5. **Tasks 9, 10 (AUD-003, AUD-133)** : export ; 9 touche `core/app/appexport/`, 10 `core/app/export/`, `docker-compose.yml`, `exportsIngestion.ts` et `AppRuntimePage.tsx` (déjà modifié par la Task 8 : relire).
6. **Tasks 11, 12 (AUD-069, AUD-075)** : 11 modifie `shell/src/api/domains/exportsIngestion.ts` (déjà modifié par la Task 10 : relire les lignes) ; 12 modifie `shell/src/api/domains/apps.ts` et `DatasetPage.tsx`.
7. **Task 13** : clôture.

## Task 1 (AUD-151) : terrain3d — contraindre la clé d'upload (copie + suppression d'un DEM tiers)

**Constat reconfirmé sur HEAD (piège 12).** `core/app/terrain3d/routes.py:105` n'a que `startswith(f"{tenant}/")` ; `jobs.py:109-118` reconvertit la clé source et crée item+config pour l'appelant, `jobs.py:148-155` supprime la source dans tous les cas. La jumelle raster (`raster/routes.py:129-133`) impose `fullmatch` + refus de `cog.tif`/`..` + `key_in_use`. Secondaire : `Terrain3DPresignRequest.filename` (`terrain3d/schemas.py:6`) n'a pas de `_safe_filename`, donc `../../x/y.tif` est accepté dans la clé présignée.

**Jumelles (piège 14).**
- `raster` : déjà durcie (rien à faire, sert de modèle).
- `tileset3d/routes.py` : clé générée côté serveur, le client n'en soumet pas -> non concernée (vérifié : aucun `startswith`/clé client).
- `ingestion/routes.py:104` et `:211` : même garde faible, mais bucket `uploads` ne contenant que des bruts transitoires ; pas de conversion en item d'une clé tierce. Exposition intra-tenant (lecture/suppression du brut d'un autre utilisateur du même tenant). **Hors périmètre de cette tâche, consigné** : à traiter avec le lot L2 (même `fullmatch` `{tenant}/{uuid32}-{nom}` + `key_in_use` sur `IngestionJob.source_key`) ; ajouter une ligne dans le backlog à la clôture.

**Files:**
- Modify: `core/app/terrain3d/schemas.py` (l.1-13 : validateur de nom ; `Terrain3DUploadCreate.filename` l.22 aussi)
- Modify: `core/app/terrain3d/repository.py` (ajout de `key_in_use` après `get_job`, ~l.38)
- Modify: `core/app/terrain3d/routes.py` (l.17 import `re`/`select`-free ; l.100-106 garde de clé)
- Test: `core/tests/test_terrain3d_routes.py` (étendre, fixture `env` existante)

**Interfaces:**
- Consumes: `Terrain3DJob.source_key`, `Terrain3DJob.converted_key`, `Terrain3DJob.tenant_id` (`app/terrain3d/models.py`).
- Produces: `repository.key_in_use(session: Session, *, tenant_id: str, key: str) -> bool` ; `schemas._safe_filename(v: str) -> str`.
- Aucune migration, aucun changement OpenAPI (pas de champ/route modifié, seules des validations 400/409/422 -> pas de régénération des types TS ; `422` sur `filename` déjà documenté par FastAPI).

- [ ] **Step 1: Tests qui échouent.** Ajouter à la fin de `core/tests/test_terrain3d_routes.py` :

```python
def test_create_upload_rejects_converted_cog_key_of_another_job(env):
    client, _, tenant, *_ = env
    key = f"{tenant.id}/{'a' * 32}/dem-cog.tif"
    r = client.post(
        "/v1/terrain3d/uploads", json={"key": key, "filename": "dem.tif", "title": "T"}
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "suffix",
    ["x/y.tif", "../../x/y.tif", "nouuid/dem.tif", f"{'a' * 32}/../dem.tif", f"{'a' * 32}/a/b.tif"],
)
def test_create_upload_rejects_malformed_key_shape(env, suffix):
    client, _, tenant, *_ = env
    r = client.post(
        "/v1/terrain3d/uploads",
        json={"key": f"{tenant.id}/{suffix}", "filename": "dem.tif", "title": "T"},
    )
    assert r.status_code == 400


def test_create_upload_refuses_a_key_already_used_by_a_job(env):
    client, *_ = env
    presigned = client.post("/v1/terrain3d/uploads/presign", json={"filename": "dem.tif"}).json()
    body = {"key": presigned["key"], "filename": "dem.tif", "title": "T"}
    assert client.post("/v1/terrain3d/uploads", json=body).status_code == 201
    assert client.post("/v1/terrain3d/uploads", json=body).status_code == 409


def test_create_upload_refuses_the_converted_key_of_an_existing_job(env):
    client, Session, tenant, _alice, *_ = env
    from app.terrain3d import repository as repo

    presigned = client.post("/v1/terrain3d/uploads/presign", json={"filename": "dem.tif"}).json()
    job_id = client.post(
        "/v1/terrain3d/uploads",
        json={"key": presigned["key"], "filename": "dem.tif", "title": "T"},
    ).json()["jobId"]
    converted = f"{tenant.id}/{job_id}/dem-cog.tif"
    with Session() as s:
        s.get(repo.Terrain3DJob, job_id).converted_key = converted
        s.commit()
        assert repo.key_in_use(s, tenant_id=tenant.id, key=converted) is True
        assert repo.key_in_use(s, tenant_id=tenant.id, key=f"{tenant.id}/{'b' * 32}/x.tif") is False


@pytest.mark.parametrize("name", ["../../x/y.tif", "a/b.tif", "a\\b.tif", "x..y.tif", "a\x00.tif"])
def test_presign_rejects_unsafe_filename(env, name):
    client, *_ = env
    r = client.post("/v1/terrain3d/uploads/presign", json={"filename": name})
    assert r.status_code == 422
```

- [ ] **Step 2: Constater l'échec.**
`cd /home/lenen/projets/geostudio/core && CORE_TEST_DATABASE_URL=sqlite+pysqlite:///:memory: uv run pytest tests/test_terrain3d_routes.py -q`
Attendu : FAIL sur les 4 nouveaux groupes (201 au lieu de 400/409/422 ; `AttributeError: key_in_use`). (SQLite en mémoire suffit, la fixture `env` l'utilise déjà ; aucune migration n'est en jeu.)

- [ ] **Step 3: Implémentation.** `core/app/terrain3d/schemas.py` :

```python
from pydantic import BaseModel, Field, field_validator


def _safe_filename(v: str) -> str:
    """Le nom entre dans la clé S3 : ni sous-chemin, ni `..`, ni caractère de contrôle
    (même règle que app.raster.schemas ; dupliquée car les domaines ne s'importent pas)."""
    if "/" in v or "\\" in v or ".." in v or any(ord(c) < 32 for c in v):
        raise ValueError("invalid filename")
    return v
```
et dans `Terrain3DPresignRequest` et `Terrain3DUploadCreate`, après le champ `filename` :
```python
    _check_filename = field_validator("filename")(_safe_filename)
```
`core/app/terrain3d/repository.py`, après `get_job` :

```python
def key_in_use(session: Session, *, tenant_id: str, key: str) -> bool:
    """La clé est déjà la source ou le COG converti d'un job : la ré-accepter
    ferait copier puis supprimer l'objet d'un autre (AUD-151)."""
    return (
        session.scalar(
            select(Terrain3DJob.id).where(
                Terrain3DJob.tenant_id == tenant_id,
                (Terrain3DJob.source_key == key) | (Terrain3DJob.converted_key == key),
            )
        )
        is not None
    )
```
`core/app/terrain3d/routes.py` : ajouter `import re` ; remplacer le bloc `if not body.key.startswith(...)` (l.105-106) par :

```python
    # Forme imposée `{tenant}/{uuid hex}/{nom}` (celle du presign). `dem-cog.tif` est le nom
    # des COG convertis : sinon un appelant ferait copier puis supprimer le DEM d'un tiers
    # (jobs.py purge la source dans tous les cas). Même patron que raster/routes.py.
    key_ok = re.fullmatch(rf"{re.escape(user.tenant_id)}/[0-9a-f]{{32}}/([^/]+)", body.key)
    if key_ok is None or key_ok.group(1) in ("dem-cog.tif", "..") or ".." in key_ok.group(1):
        raise HTTPException(status_code=400, detail="invalid upload key")
    if repo.key_in_use(session, tenant_id=user.tenant_id, key=body.key):
        raise HTTPException(status_code=409, detail="upload key already used")
```

- [ ] **Step 4: Vérifier.**
`cd /home/lenen/projets/geostudio/core && CORE_TEST_DATABASE_URL=sqlite+pysqlite:///:memory: uv run pytest tests/test_terrain3d_routes.py tests/test_terrain3d_jobs.py tests/test_terrain3d_repository.py tests/test_terrain3d_schema.py -q` -> tout vert.
Falsification : retirer temporairement le `key_in_use` de la route, confirmer que `test_create_upload_refuses_a_key_already_used_by_a_job` échoue, puis restaurer.
Puis `uv run ruff check app/terrain3d tests/test_terrain3d_routes.py && uv run ruff format --check app/terrain3d tests/test_terrain3d_routes.py && uv run lint-imports`.

- [ ] **Step 5: Checklist de clôture.** Régénération OpenAPI+TS : non. Migration : non. Inventaire des fonctionnalités : non (aucune surface nouvelle). E2E Playwright : non (aucun écran touché ; vérifier par grep que `shell/` n'envoie pas de nom de fichier contenant `/` au presign terrain3d : `grep -rn "terrain3d/uploads" shell/src`).

- [ ] **Step 6: Commit.**
```bash
git add core/app/terrain3d core/tests/test_terrain3d_routes.py
git commit -m "fix(core): terrain3d impose la forme de la clé d'upload et refuse une clé déjà utilisée (AUD-151)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

## Task 2 (AUD-005) : `transform.buffer` en mètres — projection azimutale équidistante locale au lieu d'EPSG:3857

**Constat relu sur HEAD (piège 12)** : confirmé. `core/app/pipelines/compiler.py:178-193` (`_compile_buffer`, `unit="meters"`) fait `ST_Transform(ST_Buffer(ST_Transform(geometry, src, 'EPSG:3857', true), d), 'EPSG:3857', src, true)`. L'unité de 3857 vaut 1/cos(lat) mètre réel : 100 m demandés donnent ~66 m à 49°N. Le test existant `test_compile_buffer_meters_unit_uses_correct_axis_order` ne mesure qu'un seuil à 500 m (point à 333 m dedans, à 111 km dehors) et ne détecte pas l'erreur de 30 %.

**Jumelles (piège 14)** : (a) `analysis.py:77-79` (`BufferArgs.unit`) promet « reprojection EPSG:3857 interne » : même op `transform.buffer` via `compile_transform_sql`, donc corrigé par le même changement, seule la description est à réécrire ; (b) `countWithin`, sorties collection et exports consomment ce tampon : rien à toucher ; (c) aucune autre op « en mètres » dans le compilateur (`grep meters` : seul `buffer` ; `simplify` est en unités du CRS, `tolerance` non typée « mètres ») ; (d) le chemin SRID 0 doit rester refusé (`test_srid_zero_refuses_reprojection_and_meter_buffer`, message `EPSG:0`) : le `ST_Transform` depuis `src` est conservé.

**Conception** : par ligne, centroïde WGS84 -> projection PROJ `+proj=aeqd` centrée dessus (vérifié sur DuckDB 1.5.5 : le CRS cible dynamique par ligne est accepté ; à 46°N et 60°N, 1000 m donnent ±1 m en latitude et en longitude). Valable pour tout SRID source, sans table de zones UTM. Limite assumée (commentaire `ponytail:`) : précision dégradée pour une géométrie de plusieurs centaines de km d'étendue (distorsion aeqd croissant avec la distance au centre) ; hors usage tampon courant.

**Files:**
- Modify: `core/app/pipelines/compiler.py:178-193` (`_compile_buffer`, branche `meters`)
- Modify: `core/app/pipelines/analysis.py:77-80` (description de `BufferArgs.unit`)
- Test: `core/tests/test_pipeline_compiler.py` (après `test_compile_buffer_meters_unit_uses_correct_axis_order`, l.184-203 ; fixture `conn_spatial` déjà présente)

**Interfaces:**
- Consumes: `compile_transform_sql(op, params, *, input_view, join_view=None, input_srid=None) -> str`, `_qi`, `TransformBufferParams(distance, unit)`.
- Produces: signature inchangée ; le SQL de `unit="meters"` expose une colonne interne `__gs_aeqd` exclue de la sortie.

- [ ] **Step 1 : écrire le test en échec.** Ajouter dans `core/tests/test_pipeline_compiler.py` :

```python
@pytest.mark.parametrize("lat", [46.0, 49.0, 60.0])
def test_compile_buffer_meters_is_metric_at_any_latitude(conn_spatial, lat):
    # AUD-005 : en EPSG:3857 le rayon réel valait d*cos(lat) (66 m pour 100 m à 49°N).
    conn_spatial.execute(
        f"CREATE TEMP TABLE pt AS SELECT 1 AS id, ST_Point(2.35, {lat}) AS geometry"
    )
    sql = compile_transform_sql(
        "transform.buffer",
        {"distance": 1000, "unit": "meters"},
        input_view="pt",
        input_srid=4326,
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out_buf AS {sql}")
    ymax, ymin, xmax = conn_spatial.execute(
        "SELECT ST_YMax(geometry), ST_YMin(geometry), ST_XMax(geometry) FROM out_buf"
    ).fetchone()
    import math

    north_m = (ymax - lat) * 111_195  # 1° de latitude ~ 111,195 km (sphère R=6 371 km)
    east_m = (xmax - 2.35) * 111_195 * math.cos(math.radians(lat))
    assert north_m == pytest.approx(1000, rel=0.01)
    assert east_m == pytest.approx(1000, rel=0.01)
    assert (lat - ymin) * 111_195 == pytest.approx(1000, rel=0.01)


def test_compile_buffer_meters_projected_source_and_extra_columns(conn_spatial):
    # Source projetée (Lambert-93) : 100 m doivent rester 100 m ; colonnes préservées,
    # colonne interne absente de la sortie.
    conn_spatial.execute(
        "CREATE TEMP TABLE pl AS SELECT 7 AS id, 'a' AS name, ST_Point(652000, 6862000) AS geometry"
    )
    sql = compile_transform_sql(
        "transform.buffer",
        {"distance": 100, "unit": "meters"},
        input_view="pl",
        input_srid=2154,
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out_pl AS {sql}")
    cols = [r[0] for r in conn_spatial.execute("DESCRIBE out_pl").fetchall()]
    assert sorted(cols) == ["geometry", "id", "name"]
    xmax, xmin = conn_spatial.execute(
        "SELECT ST_XMax(geometry), ST_XMin(geometry) FROM out_pl"
    ).fetchone()
    # Lambert-93 est quasi conforme : échelle locale ~1 à 1 % près en métropole.
    assert xmax - xmin == pytest.approx(200, rel=0.01)
```

- [ ] **Step 2 : constater l'échec.**

```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_pipeline_compiler.py -k "buffer_meters" -q
```
Attendu : `test_compile_buffer_meters_is_metric_at_any_latitude[46.0|49.0|60.0]` en échec (`east_m` ~ 695 / 656 / 500 au lieu de 1000, `assert ... == approx(1000 ± 10)`) ; le test source projetée échoue aussi (colonne `__gs_aeqd` absente OK, mais `DESCRIBE` / mesure faussée par 3857 : ~200 m * cos(lat) ~ 130 m).

- [ ] **Step 3 : implémenter.** Remplacer la fin de `_compile_buffer` (de `src = ...` à la fin de la fonction) dans `core/app/pipelines/compiler.py` :

```python
    src = f"'EPSG:{input_srid}'"
    # Tampon en mètres RÉELS (AUD-005) : EPSG:3857 dilate les distances de 1/cos(lat)
    # (100 m -> 66 m à 49°N). On projette chaque ligne en azimutal équidistant centré sur
    # le centroïde de sa géométrie (PROJ dynamique par ligne, exact au centre), on bufferise,
    # puis on revient au CRS source. always_xy=true : cf. plan Global Constraints.
    # ponytail: précision dégradée pour une géométrie de plusieurs centaines de km
    # d'étendue ; passer à un tampon géodésique par sommet si le besoin apparaît.
    aeqd = (
        "printf('+proj=aeqd +lat_0=%.9f +lon_0=%.9f +x_0=0 +y_0=0 +datum=WGS84 +units=m "
        "+no_defs', ST_Y(__gs_c), ST_X(__gs_c))"
    )
    return (
        f"SELECT * EXCLUDE (geometry, __gs_aeqd), "
        f"ST_Transform(ST_Buffer(ST_Transform(geometry, {src}, __gs_aeqd, true), "
        f"{p.distance}), __gs_aeqd, {src}, true) AS geometry "
        f"FROM (SELECT * EXCLUDE (__gs_c), {aeqd} AS __gs_aeqd FROM ("
        f"SELECT *, ST_Centroid(ST_Transform(geometry, {src}, 'EPSG:4326', true)) AS __gs_c "
        f"FROM {_qi(input_view)}))"
    )
```

Et dans `core/app/pipelines/analysis.py:79`, remplacer la description :

```python
        description="meters = en mètres réels (projection azimutale locale par entité) ; native = unité du CRS.",
```

- [ ] **Step 4 : vérifier.**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_pipeline_compiler.py tests/test_pipeline_ops_reliquats.py tests/test_pipeline_runtime.py tests/test_pipeline_ops_contracts.py tests/test_pipeline_ops_schemas.py -q -k "buffer or srid or analysis"
uv run pytest tests/ -q -k "analysis" 
uv run ruff check app tests && uv run ruff format --check app tests
```
Attendu : tout vert (les tests runtime « école 500 m » et `countWithin` restent verts : 500 m réels englobent au moins l'ancien rayon). Si un test d'`analysis` fige l'ancienne description ou une valeur numérique issue de 3857, l'ajuster à la valeur métrique correcte (vérifier au géodésique, pas à l'ancienne sortie). Ces tests DuckDB n'ont pas besoin de `CORE_TEST_DATABASE_URL` ; aucune migration en jeu.

- [ ] **Step 5 : falsification (piège 10).** Remettre temporairement `'EPSG:3857'` dans le SQL, constater que les 3 cas paramétrés échouent, puis rétablir.

- [ ] **Step 6 : commit.**

```bash
cd /home/lenen/projets/geostudio && git add core/app/pipelines/compiler.py core/app/pipelines/analysis.py core/tests/test_pipeline_compiler.py
git commit -m "fix(core): tampon en mètres réels par projection azimutale locale (AUD-005)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

**Checklist de clôture :** régénération OpenAPI + types TS : **oui** (la description de `BufferArgs.unit` apparaît dans `GET /v1/analysis/tools`, schéma exporté ; diff attendu limité à ce texte ; incantation `export_openapi.py` + `npm run gen:api-types` de CLAUDE.md). Migration Alembic : **non**. Inventaire des fonctionnalités : **non** (aucune surface nouvelle). E2E Playwright : **non** (pas de surface visible nouvelle). Mentionner dans `CHANGELOG.md` : « les tampons `unit=meters` déjà matérialisés étaient ~30 % trop courts ; à recalculer ».

## Task 3 (AUD-006) : `transform.snapToLayer` ne duplique plus les lignes (référence réduite à une géométrie)

**Constat reconfirmé sur HEAD (piège 12)** : `core/app/pipelines/compiler.py:761-774` émet `FROM <input> t, <join> o` sans `WHERE` ni agrégation ; N lignes x M références = N*M lignes. Un test existant (`test_compile_snap_to_layer_is_a_cross_join_with_every_reference_row`, `core/tests/test_pipeline_compiler.py:1055`) fige volontairement ce comportement : il doit être réécrit, pas contourné (son commentaire le dit). `tolerance: float` (`core/app/pipelines/ops/schemas.py:682`) n'a pas de contrainte. Aucun jumeau : c'est le seul compilateur à joindre par `FROM t, o` (grep `{_qi(input_view)} t, ` = 1 occurrence). Le `GROUP BY ALL` de `mergeChildren`/`countWithin` est AUD-I1, hors tâche.

**Choix** : la référence est réduite en CTE à une seule géométrie (`ST_Union_Agg`) ; cardinalité de sortie = cardinalité d'entrée, quel que soit M. Référence vide : `ST_Union_Agg` renvoie NULL, on conserve la géométrie d'origine (`COALESCE`) au lieu de perdre la géométrie. L'entrée secondaire n'a donc plus besoin d'être pré-agrégée (docstring mis à jour).

**Files:**
- Modify: `core/app/pipelines/compiler.py:761-774` (`_compile_snap_to_layer`)
- Modify: `core/app/pipelines/ops/schemas.py:674-683` (docstring + `tolerance: float = Field(gt=0, allow_inf_nan=False)`)
- Test: `core/tests/test_pipeline_compiler.py` (réécrire le test ligne 1055 ; ajouter 2 tests après)

**Interfaces:**
- Consumes: `compile_transform_sql(op, params, *, input_view, join_view, ...)`, fixture `conn_spatial` (tables `base` : ids 1 et 2).
- Produces: `_compile_snap_to_layer(params, *, input_view, join_view=None, input_srid=None) -> str` (signature inchangée) ; `TransformSnapToLayerParams.tolerance` strictement positive et finie.

- [ ] **Step 1 : tests d'abord.** Dans `core/tests/test_pipeline_compiler.py`, remplacer entièrement `test_compile_snap_to_layer_is_a_cross_join_with_every_reference_row` (lignes 1055-1077) par :

```python
def test_compile_snap_to_layer_preserves_input_cardinality(conn_spatial):
    # AUD-006 : N lignes d'entrée x M références doit rendre N lignes, pas N*M.
    conn_spatial.execute("CREATE TABLE ref2 (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO ref2 VALUES "
        "(1, ST_GeomFromText('POINT (3.0005 45.0005)')), "
        "(2, ST_GeomFromText('POINT (9 9)'))"
    )
    sql = compile_transform_sql(
        "transform.snapToLayer", {"tolerance": 0.01}, input_view="base", join_view="ref2"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    assert conn_spatial.execute("SELECT count(*) FROM out").fetchone() == (2,)
    assert conn_spatial.execute("SELECT id FROM out ORDER BY id").fetchall() == [(1,), (2,)]


def test_compile_snap_to_layer_empty_reference_keeps_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE ref_empty (id INTEGER, geometry GEOMETRY)")
    sql = compile_transform_sql(
        "transform.snapToLayer", {"tolerance": 0.01}, input_view="base", join_view="ref_empty"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    assert conn_spatial.execute("SELECT count(*) FROM out").fetchone() == (2,)
    assert conn_spatial.execute(
        "SELECT count(*) FROM out WHERE geometry IS NULL"
    ).fetchone() == (0,)


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan")])
def test_snap_to_layer_tolerance_must_be_positive_and_finite(bad):
    from pydantic import ValidationError

    from app.pipelines.ops.schemas import TransformSnapToLayerParams

    with pytest.raises(ValidationError):
        TransformSnapToLayerParams(tolerance=bad)
```

- [ ] **Step 2 : constater l'échec** (base jetable, aucune migration en jeu ; ces tests DuckDB n'utilisent pas Postgres) :

```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_pipeline_compiler.py -k "snap_to_layer" -q
```
Attendu : `preserves_input_cardinality` échoue (`assert (4,) == (2,)`), `empty_reference_keeps_geometry` échoue (0 ligne : `(0,) == (2,)`), les 4 cas `tolerance` échouent (`DID NOT RAISE`).

- [ ] **Step 3 : implémentation.** Dans `core/app/pipelines/compiler.py`, remplacer le `return` de `_compile_snap_to_layer` :

```python
    # AUD-006 : la référence est réduite à UNE géométrie (union) pour conserver la
    # cardinalité de l'entrée ; référence vide -> NULL -> on garde la géométrie d'origine.
    return (
        f"WITH ref AS (SELECT ST_Union_Agg(geometry) AS g FROM {_qi(join_view)}) "
        f"SELECT t.* EXCLUDE (geometry), "
        f"COALESCE(ST_Snap(t.geometry, ref.g, {p.tolerance}), t.geometry) AS geometry "
        f"FROM {_qi(input_view)} t CROSS JOIN ref"
    )
```
(`ref` a toujours exactement une ligne : agrégat sans `GROUP BY`.)

Dans `core/app/pipelines/ops/schemas.py`, remplacer le docstring et le champ de `TransformSnapToLayerParams` :

```python
    """Ajuste (« snap ») la géométrie sur l'union des géométries de l'entrée secondaire
    dans une tolérance donnée. L'entrée secondaire est réduite à une seule géométrie
    (`ST_Union_Agg`) : le nombre de lignes de sortie égale celui de l'entrée. Une entrée
    secondaire vide laisse les géométries inchangées."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    tolerance: float = Field(gt=0, allow_inf_nan=False)
```
Si pydantic refuse `allow_inf_nan` avec `gt` dans cette version, utiliser `Field(gt=0, lt=float("inf"))` (NaN échoue déjà `gt=0`).

- [ ] **Step 4 : vérification.**

```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_pipeline_compiler.py -q \
 && uv run pytest -q -k "snap or operation_contract or pipelines_ops" \
 && uv run ruff check app tests && uv run ruff format --check app tests && uv run lint-imports
```
Attendu : tout vert, y compris `test_compile_snap_to_layer` (snap de `POINT (3.0005 45.0005)` inchangé) et les tests `output_srid_snap_to_layer`.

- [ ] **Step 5 : portes annexes.**
  - OpenAPI + types TS : **oui** — `tolerance` gagne `exclusiveMinimum`/le docstring change dans le schéma de params exposé (si le diff est vide, c'est légitime). Lancer l'incantation du CLAUDE.md (`export_openapi.py openapi.json` puis `cd ../shell && npm run gen:api-types`) et committer le diff éventuel ; vérifier aussi qu'aucun schéma JSON de params copié dans `shell/` (grep `snapToLayer` dans `shell/src`) ne fige l'ancienne forme.
  - Migration Alembic : **non**. Inventaire des fonctionnalités : **non** (aucune surface nouvelle). E2E Playwright : **non** (pas de surface visible nouvelle).
  - Documenter le changement de comportement (jeu de données qui était gonflé N*M) dans `CHANGELOG.md` (ligne « Corrigé ») et fermer AUD-006 dans `docs/revue/audit-2026-10-16/99-synthese.md` si le dépôt tient un statut.

- [ ] **Step 6 : commit.**

```bash
git add core/app/pipelines/compiler.py core/app/pipelines/ops/schemas.py core/tests/test_pipeline_compiler.py CHANGELOG.md
git commit -m "fix(core): snapToLayer conserve la cardinalité de l'entrée (AUD-006)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

## Task 4 (AUD-007) : `transform.detectChanges` doit émettre les colonnes de données (upsert utilisable)

**Constat confirmé sur HEAD** (piège 12 : code relu) : `core/app/pipelines/compiler.py:684-715` (`_compile_detect_changes`) ne sélectionne que `key_select` + le statut. Le test `core/tests/test_pipeline_runtime.py:2982-2985` verrouille `set(rows[0].keys()) == {"id", "status"}`. Chaîne `detectChanges → writer.collection(mode=upsert, statusColumn=…)` : les lignes `inserted`/`updated` n'ont ni attributs ni géométrie. Défaut réel (D13-01, d10 I7).

**Sémantique retenue** : primaire `t` = état « avant », secondaire `o` = « après » (cohérent avec le test : id 3 présent seulement dans `t` → `deleted`). Sortie = **schéma « après »** (`join_columns`) ; valeur = `o.c` si la ligne existe côté après, sinon `t.c` si la colonne existe côté avant, sinon `NULL` (lignes `deleted`). Colonnes présentes seulement côté « avant » : non émises (la cible d'un upsert suit le schéma « après »). Une colonne sentinelle (`__gs_present`) remplace le test `t.<clé0> IS NULL`, ce qui corrige aussi la jumelle D13-02 sur les clés NULL/composites (une ligne « avant » à clé NULL devient `deleted`, plus `inserted`). Hors périmètre (noté, non traité) : fan-out sur clés dupliquées (`onDuplicateKey`), sorties séparées par statut.

**Jumelles examinées (piège 14)** : `_compile_merge_children`/`_compile_map_schema` ne partagent pas le défaut. Le consommateur `collection_writer.py` (l.387-446) lit `statusColumn` + colonnes de la cible : aucune modification nécessaire, mais le test d'intégration ci-dessous le prouve. Garde `test_pipeline_fme_review_guards.py:77` (`statusColumn` exempté) inchangée.

**Files:**
- Modify: `core/app/pipelines/compiler.py:684-715` (`_compile_detect_changes`)
- Modify: `core/app/pipelines/ops/schemas.py:617-625` (docstring `TransformDetectChangesParams`, et description l.85-89 inchangée)
- Test: `core/tests/test_pipeline_runtime.py:2884-2985` (étendre `test_preview_detect_changes_resolves_columns_after_upstream_rename`) + nouveau test unitaire du compilateur dans le même fichier

**Interfaces:**
- Consumes: `_qi(name: str) -> str`, `TransformDetectChangesParams(withCollectionId, keyColumns, statusColumn)`, `input_columns`/`join_columns` (résolus par `needs_columns`)
- Produces: `_compile_detect_changes(params, *, input_view, join_view, input_srid, input_columns, join_columns) -> str` — même signature, SQL émettant `join_columns` + `statusColumn`.

- [ ] **Step 1: Écrire les tests (échec attendu)**

Dans `core/tests/test_pipeline_runtime.py`, remplacer les 3 dernières lignes de l'assertion (l.2982-2985) par :

```python
    status_by_id = {r["id"]: r["status"] for r in rows}
    assert status_by_id == {1: "unchanged", 2: "updated", 3: "deleted", 4: "inserted"}
    by_id = {r["id"]: r for r in rows}
    # Schéma « après » émis : attributs et géométrie présents (AUD-007).
    assert {"id", "region", "pop", "geometry", "status"} <= set(rows[0].keys())
    assert by_id[4]["region"] == "X" and by_id[4]["geometry"] is not None  # inserted : valeurs « après »
    assert by_id[2]["region"] == "Ouest" and by_id[2]["pop"] == 99  # updated : valeurs « après »
    # deleted : repris du « avant » pour les colonnes communes, NULL sinon (region renommée en amont).
    assert by_id[3]["pop"] == 20 and by_id[3]["region"] is None
    assert by_id[3]["geometry"] is not None
```

Ajouter à la fin du fichier un test pur du SQL (clé NULL, D13-02) :

```python
def test_compile_detect_changes_emits_data_and_uses_presence_sentinel():
    from app.pipelines import compiler

    sql = compiler._compile_detect_changes(
        {"keyColumns": ["id"], "statusColumn": "st"},
        input_view="a",
        join_view="b",
        input_columns=["id", "pop"],
        join_columns=["id", "pop", "region"],
    )
    assert "__gs_present" in sql
    assert 'AS "region"' in sql and 'AS "pop"' in sql and 'AS "st"' in sql
    assert "t.\"id\" IS NULL" not in sql  # plus de test sur la clé elle-même
    # région absente côté « avant » : jamais t.region référencé
    assert 't."region"' not in sql
```

- [ ] **Step 2: Vérifier l'échec**

```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_pipeline_runtime.py -k "detect_changes" -x -q
```
Attendu : FAIL (`KeyError: 'region'` / `assert '__gs_present' in sql`).

- [ ] **Step 3: Implémenter** — remplacer le corps de `_compile_detect_changes` à partir de `common_cols = …` :

```python
    common_cols = [c for c in input_columns if c in join_columns and c not in p.keyColumns]
    key_join = " AND ".join(f"t.{_qi(k)} = o.{_qi(k)}" for k in p.keyColumns)
    if common_cols:
        diff_expr = " OR ".join(f"t.{_qi(c)} IS DISTINCT FROM o.{_qi(c)}" for c in common_cols)
    else:
        diff_expr = "FALSE"
    # Sentinelles de présence : tester la clé elle-même est faux (une clé NULL ne joint
    # jamais ; seule la 1re clé d'un jeu composite était testée — D13-02).
    status_expr = (
        "CASE "
        "WHEN t.__gs_present IS NULL THEN 'inserted' "
        "WHEN o.__gs_present IS NULL THEN 'deleted' "
        f"WHEN {diff_expr} THEN 'updated' "
        "ELSE 'unchanged' END"
    )
    # Schéma « après » : o.c si la ligne existe après, sinon t.c (deleted) quand la colonne
    # existe avant, sinon NULL. Sans ces colonnes l'upsert de writer.collection écrivait
    # des lignes vides (AUD-007).
    data_select = ", ".join(
        f"CASE WHEN o.__gs_present IS NULL THEN "
        f"{'t.' + _qi(c) if c in input_columns else 'NULL'} "
        f"ELSE o.{_qi(c)} END AS {_qi(c)}"
        for c in join_columns
    )
    return (
        f"SELECT {data_select}, ({status_expr}) AS {_qi(p.statusColumn)} "
        f"FROM (SELECT *, TRUE AS __gs_present FROM {_qi(input_view)}) t "
        f"FULL OUTER JOIN (SELECT *, TRUE AS __gs_present FROM {_qi(join_view)}) o ON {key_join}"
    )
```

Si `statusColumn` figure déjà dans `join_columns`, le validateur d'écriture existant n'en protège pas (D13-04, hors périmètre) ; ne pas l'ajouter ici.

Mettre à jour la docstring de `TransformDetectChangesParams` (`schemas.py:618-621`) : ajouter « La sortie reprend le schéma de l'état « après » (valeurs « avant » pour les lignes deleted) plus la colonne de statut. »

- [ ] **Step 4: Vérifier le vert + jumelles**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_pipeline_runtime.py tests/test_pipeline_ops_contracts.py tests/test_pipeline_fme_review_guards.py tests/test_pipeline_routes.py tests/test_collection_writer.py -q
uv run ruff check app/pipelines tests/test_pipeline_runtime.py && uv run ruff format --check app/pipelines tests/test_pipeline_runtime.py
```
Attendu : tout vert (aucune migration → pas de base dédiée ; `CORE_TEST_DATABASE_URL` habituel suffit pour `test_collection_writer.py`). Si l'on n'a pas de test écrivain de bout en bout `detectChanges→upsert`, en ajouter un dans `tests/test_collection_writer.py` sur le modèle des tests `statusColumn` existants (lignes `inserted` avec attributs → insérées avec valeurs).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/compiler.py core/app/pipelines/ops/schemas.py core/tests/test_pipeline_runtime.py
git commit -m "fix(core): detectChanges émet le schéma après + sentinelle de présence (AUD-007)"
```

**Livrables transverses :** régénération OpenAPI + types TS : **non** (seule une docstring de modèle change ; si le diff `openapi.json` n'est pas vide car la description du schéma d'op est exposée via `GET /v1/pipelines/ops`, lancer l'incantation de CLAUDE.md puis `npm run gen:api-types`). Migration Alembic : **non**. Inventaire des fonctionnalités : **non** (aucune surface nouvelle). E2E Playwright : **non** (comportement backend). Ajouter une ligne à `CHANGELOG.md` (changement de forme de sortie de `transform.detectChanges` : les pipelines qui lisaient seulement clé+statut voient des colonnes supplémentaires).

## Task 5 (AUD-020) : OGC Features, collection stockée hors 4326 (2154) : écriture GeoJSON reprojetée, lecture par défaut en lon/lat

**Constat vérifié sur HEAD (c0251b66)** : le défaut existe toujours. `core/app/features/repository.py:425` (`_geometry_sql`) fait `ST_SetSRID(ST_GeomFromGeoJSON(:__geom), :__srid)` avec `__srid = info.srid` : un lon/lat est estampillé 2154 sans `ST_Transform`. La lecture par défaut (`_select_list`, l.263-264) sort `ST_AsGeoJSON(geom)` brut (mètres Lambert) sans `Content-Crs` (`routes.py:403`, seulement si `crs` fourni). Les écritures passent toutes par `_geometry_sql` (insert l.449, insert_features l.490, replace l.565, `collection_writer._update_stmt` l.309) sauf le corps de `_straddle_gate` (l.507, SQL recopié à la main). `ingestion/importer.py:558` refuse l'ajout hors 4326 à cause de ce défaut.

**Jumelles traitées** (piège 14) : (1) `_straddle_gate` l.507 (corps comparé au clip stocké) ; (2) `collection_writer._snapshots` l.227 (instantané d'historique `ST_AsGeoJSON` brut, donc `entity_history` en mètres Lambert) ; (3) `get_feature` / `select_features` via `_select_list` ; (4) restriction d'ajout `importer.py:558` levée (insert_features est corrigé). Déjà corrects, vérifiés : `cql2.py:425` et `repository.py:252` (ST_Transform explicite) ; tuiles MVT (reprojetées en 3857).

**Files:**
- Modify: `core/app/features/repository.py` (`_select_list` l.258-267, `_geometry_sql` l.424-433, `_straddle_gate` l.507)
- Modify: `core/app/pipelines/collection_writer.py` (l.31 import, l.227)
- Modify: `core/app/ingestion/importer.py` (l.558-560, suppression du refus)
- Test: Create `core/tests/test_features_crs_storage_postgis.py` ; Modify `core/tests/test_ingestion_routes.py` ou tout test existant qui assert le message « seulement sur une collection en EPSG:4326 » (`grep -rn "EPSG:4326\"" core/tests | grep -i "ajout\|append\|supporté"` ; aucun trouvé au moment de la rédaction, donc probablement rien à changer)

**Interfaces:**
- Consumes : `TableInfo.srid: int | None`, `TableInfo.geometry_column`, `quote_ident`, `introspect_table`, `rls_scope`.
- Produces : `repository._geojson_out(session, info, out_srid=None) -> str` (expression SQL `ST_AsGeoJSON(...) AS __geo`-able) ; `repository._geom_from_geojson(info) -> str` (expression SQL GeoJSON lon/lat -> SRID de stockage, utilise `:__geom` et `:__srid`). Contrat inchangé : GeoJSON en entrée/sortie est TOUJOURS en lon/lat 4326 sauf `crs=` explicite en lecture.

- [ ] **Step 1 : test d'abord** : créer `core/tests/test_features_crs_storage_postgis.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-020 : collection stockée en EPSG:2154, GeoJSON toujours en lon/lat (RFC 7946)."""

import pytest
from sqlalchemy import text

from app.collections.introspection_pg import introspect_table
from app.features import repository as repo
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis

T = "t_aud020_l93"
PARIS = {"type": "Point", "coordinates": [2.3522, 48.8566]}


@pytest.fixture()
def table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {T}"))
        conn.execute(
            text(
                f"CREATE TABLE {T} (id serial PRIMARY KEY, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 2154))"
            )
        )
        conn.execute(text(f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                f"CREATE POLICY tenant_isolation ON {T} "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE ON {T} TO gis_rls"))
        conn.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {T}_id_seq TO gis_rls"))
    yield T
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {T}"))


def _stored_lonlat(pg_engine, fid):
    with pg_engine.begin() as conn:
        return conn.execute(
            text(f"SELECT ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326)) FROM {T} WHERE id = :i"),
            {"i": fid},
        ).one()


def test_insert_reprojects_lonlat_to_storage_srid(pg_engine, pg_session_factory, table):
    with pg_session_factory() as s:
        info = introspect_table(s, table)
        assert info.srid == 2154
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
        s.commit()
    x, y = _stored_lonlat(pg_engine, fid)
    assert (round(x, 4), round(y, 4)) == (2.3522, 48.8566)  # avant correctif : ~(0, 0) hors France


def test_insert_features_and_replace_reproject(pg_engine, pg_session_factory, table):
    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            repo.insert_features(s, info, [({}, PARIS)])
            fid = s.execute(text(f"SELECT max(id) FROM {T}")).scalar()
            repo.replace_feature(s, info, fid=str(fid), properties={}, geometry={"type": "Point", "coordinates": [5.0, 45.0]})
        s.commit()
    x, y = _stored_lonlat(pg_engine, fid)
    assert (round(x, 4), round(y, 4)) == (5.0, 45.0)


def test_default_read_is_lonlat_and_explicit_crs_is_storage(pg_session_factory, pg_engine, table):
    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
            default = repo.get_feature(s, info, fid=str(fid))
            l93 = repo.get_feature(s, info, fid=str(fid), out_srid=2154)
        s.commit()
    lon, lat = default["geometry"]["coordinates"]
    assert (round(lon, 4), round(lat, 4)) == (2.3522, 48.8566)  # avant : mètres Lambert
    assert l93["geometry"]["coordinates"][0] > 600000  # crs explicite = stockage, inchangé
```

- [ ] **Step 2 : constater l'échec** (base jetable, aucune migration en jeu mais on évite le postgis-test partagé)

```bash
cd /home/lenen/projets/geostudio/core
docker run -d --rm --name pg-aud020 -e POSTGRES_PASSWORD=x -p 55433:5432 postgis/postgis:16-3.4 >/dev/null
# attendre la base, puis appliquer le schéma de test comme le fait la CI (alembic upgrade head)
export CORE_TEST_DATABASE_URL=postgresql+psycopg://postgres:x@localhost:55433/postgres
PYTHONPATH=. uv run pytest tests/test_features_crs_storage_postgis.py -q
```
Attendu : 3 FAILED (`assert (2.0e-05, ...) == (2.3522, 48.8566)` pour l'insert ; lecture par défaut `assert 2.3522 == 651000...`). Si le rôle `gis_rls` ou l'environnement du conftest exige l'incantation de `tests/conftest.py` (l.57-70), la suivre à l'identique.

- [ ] **Step 3 : implémentation `repository.py`** : remplacer `_select_list` et `_geometry_sql` (l.258-267 et 424-433) et ajouter les deux helpers.

```python
def _geojson_out(session: Session, info: TableInfo, out_srid: int | None = None) -> str:
    """`ST_AsGeoJSON` de la géométrie : lon/lat 4326 par défaut (RFC 7946) quel que soit le SRID
    de stockage ; `out_srid` explicite (`?crs=`) = CRS demandé (Content-Crs posé par la route)."""
    g = quote_ident(session, info.geometry_column)
    target = out_srid if out_srid is not None else 4326
    if target == (info.srid or 4326):  # chemin historique : aucune reprojection
        return f"ST_AsGeoJSON({g})" if out_srid is None else f"ST_AsGeoJSON({g}, 9, 0)"
    return f"ST_AsGeoJSON(ST_Transform({g}, {int(target)}), 9, 0)"


def _select_list(session: Session, info: TableInfo, out_srid: int | None = None) -> str:
    cols = [quote_ident(session, info.pk_column)]
    cols += [quote_ident(session, c.name) for c in _property_columns(info)]
    if info.geometry_column:
        cols.append(f"{_geojson_out(session, info, out_srid)} AS __geo")
    return ", ".join(cols)


def _geom_from_geojson(info: TableInfo) -> str:
    """GeoJSON (lon/lat 4326 par contrat) -> SRID de stockage (`:__srid`). Les promotions
    Multi/simple (REV-352) s'appliquent APRÈS reprojection."""
    if (info.srid or 4326) == 4326:
        return "ST_SetSRID(ST_GeomFromGeoJSON(:__geom), :__srid)"
    return "ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:__geom), 4326), :__srid)"


def _geometry_sql(info: TableInfo) -> str:
    base = _geom_from_geojson(info)
    gt = info.geometry_type or ""
    if gt.startswith("Multi"):  # REV-352 : promotion X -> MultiX (idempotent sur Multi)
        return f"ST_Multi({base})"
    if gt in ("Point", "LineString", "Polygon"):  # MultiX à une partie -> X
        return (
            f"(CASE WHEN ST_NumGeometries({base}) = 1 THEN ST_GeometryN({base}, 1) ELSE {base} END)"
        )
    return base
```
Dans `_straddle_gate`, remplacer la ligne `body = ...` (l.507) par :
```python
    body = f"ST_SnapToGrid({_geom_from_geojson(info)}, 1e-6)"
```
Note : le chemin historique 4326 reste octet-pour-octet identique (`ST_AsGeoJSON(g)` sans options quand `crs` absent ; `ST_AsGeoJSON(g, 9, 0)` quand `crs` explicite, l'ancien SQL faisait `ST_Transform(g, 4326)` no-op, résultat identique).

- [ ] **Step 4 : jumelle `collection_writer.py`** : l.31 `from app.features.repository import _geojson_out, _geometry_sql, insert_features` ; l.227 :
```python
        sel.append(f"{_geojson_out(session, info)} AS __g")
```
(l'historique d'entités et `before`/`after` sont ainsi en lon/lat ; `_update_stmt` est déjà corrigé via `_geometry_sql`).

- [ ] **Step 5 : jumelle `importer.py`** : supprimer l.558-560 (le `if col.srid not in (None, 4326): raise …` et son commentaire `ponytail`). Les fichiers sont lus en WGS84 et `insert_features` reprojette désormais.

- [ ] **Step 6 : tests jumeaux** : ajouter à `core/tests/test_features_crs_storage_postgis.py`

```python
def test_collection_writer_snapshot_is_lonlat(pg_engine, pg_session_factory, table):
    from app.pipelines.collection_writer import _snapshots

    with pg_session_factory() as s:
        info = introspect_table(s, table)
        with rls_scope(s, "default"):
            fid = repo.insert_feature(s, info, properties={}, geometry=PARIS)
        s.commit()
        snap = _snapshots(s, info, "default", [fid])
    lon, lat = snap[fid]["geometry"]["coordinates"]
    assert (round(lon, 4), round(lat, 4)) == (2.3522, 48.8566)
```
Et un test d'ajout de fichier sur collection 2154 (étendre `test_ingestion_routes.py` : enregistrer la table 2154 comme collection éditable, `append_import` d'un CSV `lat,lon` à 1 ligne, attendre `inserted == 1`, relire `ST_Transform(geom,4326)` ≈ point d'entrée). Réutiliser le fixture d'append existant de ce fichier (`grep -n "append" core/tests/test_ingestion_routes.py`) en changeant seulement le SRID de la table. Un test de straddle sous limite géographique en 2154 est facultatif : la correction est couverte par le fait que `body` et `_geometry_sql` partagent `_geom_from_geojson`.

- [ ] **Step 7 : vérification**

```bash
cd /home/lenen/projets/geostudio/core
PYTHONPATH=. uv run pytest tests/test_features_crs_storage_postgis.py tests/test_features_geometry_promotion_postgis.py tests/test_features_repository.py tests/test_features_sortby_datetime_crs.py tests/test_features_rls.py tests/test_ingestion_routes.py tests/test_ingestion_tasks.py -q
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
docker rm -f pg-aud020
```
Attendu : tout vert (les 3+2 nouveaux tests passent ; les tests 4326 existants inchangés). Lancer ensuite `uv run pytest -q tests -k "collection_writer or writer_collection or features"` pour la jumelle pipeline.

- [ ] **Step 8 : commit**

```bash
git add core/app/features/repository.py core/app/pipelines/collection_writer.py core/app/ingestion/importer.py core/tests/test_features_crs_storage_postgis.py core/tests/test_ingestion_routes.py
git commit -m "fix(core): GeoJSON toujours en lon/lat sur une collection stockée en 2154 (AUD-020)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

**Récapitulatif**
- Régénération OpenAPI + types TS : **non** (aucune route ni modèle ne change ; contrat de réponse inchangé).
- Migration Alembic : **non**.
- Inventaire des fonctionnalités : **non** (aucune surface nouvelle) ; mettre à jour la ligne `AUD-020` du backlog/synthèse à « fermé » dans le même geste.
- E2E Playwright : **non** (pas de surface visible).
- Reste hors périmètre : CRS d'entrée explicite (`Content-Crs` en écriture, OGC Part 2) non ajouté (YAGNI : le contrat GeoJSON est lon/lat) ; WMS/OGC DOM/CC9 relèvent d'une autre entrée (d34 « Important »).

## Task 6 (AUD-129) : Import — réparer les géométries invalides au lieu de rejeter tout le fichier

**Constat revérifié sur HEAD `c0251b66`** : `core/app/ingestion/parsers.py:182-183` (GeoJSON) et `:490-491` (chemin GDAL, partagé par gpkg/shapefile/filegdb/dxf/dgn/kml/gml via `_read_layer`) font `if not geom.is_valid: raise IngestionParseError(...)` ; `tasks.py:208` marque alors le job entier en erreur. Aucun `make_valid` dans `app/ingestion`. Défaut confirmé.

**Décision (périmètre minimal)** : réparation systématique par `shapely.make_valid` (comportement `repair` du correctif suggéré), compteur journalisé. Le paramètre `invalidGeometry: repair|reject|skip` et le rapport par fid joint au job sont **différés** (surface API + migration du rapport de job, hors taille S) ; ajouter si un utilisateur demande `reject`/`skip`.

**Jumelles (piège 14)** :
- `run_append` passe par `_load_rows` -> mêmes parseurs : couvert sans code supplémentaire (test dédié ci-dessous).
- GeoParquet / CSV-WKT / XLSX-WKT : aucune vérification `is_valid` aujourd'hui (PostGIS accepte l'invalide), donc pas de rejet ; inchangé.
- `ST_Intersection` de `compiler.py:223` non protégé par `ST_MakeValid` : **hors tâche** (moteur DuckDB, disponibilité de `ST_MakeValid` dans la version spatial épinglée non vérifiée) -> à traiter dans la tâche AUD pipelines/overlay (AUD-021).

**Files:**
- Modify: `core/app/ingestion/parsers.py` (ajout helper après `IngestionParseError`, ~l.42-60 ; remplacement des blocs l.182-183 et l.490-491)
- Test: `core/tests/test_ingestion_parsers.py` (étendre) ; `core/tests/test_ingestion_gdal_formats.py` (cas GPKG)

**Interfaces:**
- Consumes: `shapely.make_valid`, `shapely.ops.unary_union`, `IngestionParseError`
- Produces: `_repair_geometry(geom: BaseGeometry, where: str) -> BaseGeometry` (module `app.ingestion.parsers`, privé) ; `parse_geojson`/`_read_layer` ne lèvent plus sur invalide réparable.

- [ ] **Step 1 : tests d'abord** — ajouter à `core/tests/test_ingestion_parsers.py` :

```python
BOWTIE = [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]  # nœud papillon, invalide


def _fc(*geoms):
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"n": i}, "geometry": g}
                for i, g in enumerate(geoms)
            ],
        }
    ).encode()


def test_geojson_invalid_polygon_is_repaired_not_rejected():
    ok = {"type": "Point", "coordinates": [1, 1]}
    bad = {"type": "Polygon", "coordinates": BOWTIE}
    rows = list(parse_geojson(_fc(ok, bad, ok)))
    assert len(rows) == 3
    geom = rows[1][0]
    assert geom.is_valid
    assert geom.geom_type in {"Polygon", "MultiPolygon"}
    assert geom.area == pytest.approx(2.0)  # deux triangles d'aire 1


def test_geojson_unrepairable_empty_still_rejected():
    # polygone dégénéré (aire nulle) : la réparation ne donne plus de polygone
    flat = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [2, 2], [0, 0]]]}
    with pytest.raises(IngestionParseError, match="feature 0 : géométrie invalide"):
        list(parse_geojson(_fc(flat)))
```

Et à `core/tests/test_ingestion_gdal_formats.py` (déjà `gpd`, `Polygon` importés ; adapter l'import de `parse_gpkg` si absent) :

```python
def test_gpkg_invalid_polygon_is_repaired(tmp_path):
    from app.ingestion.parsers import parse_gpkg

    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    path = tmp_path / "bad.gpkg"
    gpd.GeoDataFrame({"n": [1]}, geometry=[bowtie], crs="EPSG:4326").to_file(path, driver="GPKG")
    rows = list(parse_gpkg(path.read_bytes()))
    assert len(rows) == 1 and rows[0][0].is_valid
```

- [ ] **Step 2 : constater l'échec**

```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_ingestion_parsers.py tests/test_ingestion_gdal_formats.py -k "repaired or unrepairable" -q
```
Attendu : `test_geojson_invalid_polygon_is_repaired_not_rejected` et `test_gpkg_invalid_polygon_is_repaired` échouent avec `IngestionParseError: feature 1 : géométrie invalide` / `entité 0 : géométrie invalide` ; `unrepairable` passe déjà (garde de non-régression).

- [ ] **Step 3 : implémentation** — dans `parsers.py`, après la classe `IngestionParseError`, ajouter :

```python
def _repair_geometry(geom: BaseGeometry, where: str) -> BaseGeometry:
    """AUD-129 : une géométrie invalide (nœud papillon, auto-intersection) est réparée
    par make_valid au lieu de faire échouer tout le fichier. make_valid peut renvoyer une
    GeometryCollection mêlant dimensions : on ne garde que les parties de la dimension
    d'origine. Résultat vide/dégénéré -> rejet explicite (pas de perte silencieuse)."""
    if geom.is_valid:
        return geom
    dim = {"Polygon": 2, "MultiPolygon": 2, "LineString": 1, "MultiLineString": 1}.get(
        geom.geom_type, 0
    )
    fixed = shapely.make_valid(geom)
    if fixed.geom_type == "GeometryCollection":
        parts = [p for p in shapely.get_parts(fixed) if _DIM.get(p.geom_type, 0) == dim]
        fixed = unary_union(parts) if parts else fixed
    if fixed.is_empty or _DIM.get(fixed.geom_type, 0) != dim or not fixed.is_valid:
        raise IngestionParseError(f"{where} : géométrie invalide")
    return fixed


_DIM = {
    "Point": 0, "MultiPoint": 0, "LineString": 1, "MultiLineString": 1,
    "Polygon": 2, "MultiPolygon": 2,
}
```
(déplacer `_DIM` au-dessus de la fonction ; `from shapely.ops import transform as shapely_transform, unary_union` à la ligne d'import l.37.) Remplacer :

```python
        if not geom.is_valid:
            raise IngestionParseError(f"feature {i} : géométrie invalide")
```
par `geom = _repair_geometry(geom, f"feature {i}")`, et dans le chemin GDAL (après `shapely_transform`) :
```python
        if not geom.is_valid:
            raise IngestionParseError(f"entité {i} : géométrie invalide")
```
par `geom = _repair_geometry(geom, f"entité {i}")`. Mettre à jour la docstring de tête (l.5) : « les géométries invalides sont réparées (make_valid) ». Lancer `uv run ruff format app/ingestion/parsers.py` pour la mise en forme du dict.

- [ ] **Step 4 : vérifier**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_ingestion_parsers.py tests/test_ingestion_gdal_formats.py tests/test_ingestion_importer.py tests/test_ingestion_append.py -q
uv run ruff check app/ingestion && uv run ruff format --check app/ingestion
```
Attendu : tout vert. Les tests PostGIS d'importer/append exigent `CORE_TEST_DATABASE_URL` vers une base jetable (aucune migration ici, mais ne pas laisser skipper silencieusement : vérifier « 0 skipped »).

- [ ] **Step 5 : falsification** — retirer temporairement l'appel `_repair_geometry` dans `parse_geojson`, constater l'échec du test GeoJSON, puis restaurer.

- [ ] **Step 6 : commit**

```bash
git add core/app/ingestion/parsers.py core/tests/test_ingestion_parsers.py core/tests/test_ingestion_gdal_formats.py
git commit -m "fix(core): import — réparer les géométries invalides (make_valid) au lieu de rejeter le fichier (AUD-129)"
```

**Transverse :** régénération OpenAPI + types TS : non (aucune route/modèle). Migration Alembic : non. Inventaire des fonctionnalités : non (pas de surface nouvelle). E2E Playwright : non (aucune surface visible). Suivi à noter dans le backlog : paramètre `invalidGeometry` + rapport des entités réparées ; `ST_MakeValid` dans `_compile_intersection`/countWithin (AUD-021).

## Task 7 (AUD-002) : Indicateur/graphique/pivot sur source `features` : ne plus afficher un échantillon de 100 comme s'il était complet

**Constat relu sur HEAD (piège 12).** Confirmé, avec deux nuances par rapport à d05 :
- `buildFeaturesUrl` (`shell/src/api/domains/datasets.ts:103-107`) n'ajoute aucun `limit` ; le cœur applique `limit=Query(100)` et plafonne à `MAX_LIMIT = 1000` (`core/app/features/routes.py:104,320,347`). Un `limit` client ne peut donc **pas** rendre l'agrégat exact : le correctif doit être honnête, pas « plus gros ».
- Le tableau a déjà son avertissement (`data.tsx:377`, clé `widgetData.truncated`) et `DataSourceState.total` (= `numberMatched`) est déjà propagé par `DataContext.tsx:125`. Restent sans alerte : **indicateur** (`indicator.tsx:163-188`, `count` = `records.length`, `sum` sur l'échantillon), **graphique** (`chart.tsx:448`) et **pivot** (`pivot.tsx:91`) = les jumelles (piège 14).

**Correctif retenu (minimal, sans migration) :**
1. Indicateur `count` sur source `features` : utiliser `data.total` (exact, `numberMatched` respecte filtres/contexte) quand il est connu.
2. Composant partagé `SampleBadge` « Échantillon : N sur M » affiché par indicateur (sum/avg/min/max…), graphique et pivot quand `total > records.length` et que la source n'est pas `statistics`.
3. Hors périmètre, assumé : source par défaut `statistics` selon le widget et pagination/tri serveur du tableau (d05 correctif 2-3), à traiter dans une tâche produit séparée ; le badge rend le défaut visible dès maintenant.

**Files:**
- Create: `shell/src/builder/widgets/SampleBadge.tsx`
- Create (test): `shell/src/builder/widgets/SampleBadge.test.tsx`
- Modify: `shell/src/builder/widgets/indicator.tsx` (`resolveFlatValue` l.163-189 ; rendu l.374-385)
- Modify: `shell/src/builder/widgets/chart.tsx` (rendu l.456-470)
- Modify: `shell/src/builder/widgets/pivot.tsx` (rendu l.106-112)
- Modify: `shell/src/i18n/domains/widgets.ts` (près de l.149)
- Test: `shell/src/builder/widgets/indicator.test.tsx`, `chart.test.tsx`, `pivot.test.tsx` (étendre)

**Interfaces:**
- Consumes: `DataSourceState` (`api/types.ts:1549`, champs `records`, `total?`, `resolvedSource?`), `t()` de `i18n`.
- Produces: `export function isSampled(data: Pick<DataSourceState,"records"|"total"|"resolvedSource">): boolean` et `export function SampleBadge(props: { data: Pick<DataSourceState,"records"|"total"|"resolvedSource"> }): JSX.Element | null` ; clé i18n `widgetData.sampled` = `"Échantillon : {count} sur {total}"`.

- [ ] **Step 1 : tests du composant (rouges)** — `shell/src/builder/widgets/SampleBadge.test.tsx`

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { SampleBadge, isSampled } from "./SampleBadge";

const rec = (n: number) => Array.from({ length: n }, (_, i) => ({ id: i, properties: {} }));
const feat = { id: "s", type: "features" as const, service: "core", layer: "c", query: {} };

test("badge affiché quand total > records et source features", () => {
  render(<SampleBadge data={{ records: rec(100), total: 5000, resolvedSource: feat }} />);
  expect(screen.getByRole("status")).toHaveTextContent("Échantillon : 100 sur 5000");
});
test("rien si total inconnu, complet, ou source statistics", () => {
  expect(isSampled({ records: rec(100), total: null })).toBe(false);
  expect(isSampled({ records: rec(100), total: 100 })).toBe(false);
  expect(
    isSampled({ records: rec(1), total: 9, resolvedSource: { ...feat, type: "statistics" } }),
  ).toBe(false);
});
```

- [ ] **Step 2 : tests des widgets (rouges)** — ajouter à `indicator.test.tsx` (helpers `renderIndicator`/`state` existants) :

```tsx
test("count sur source features tronquée : affiche numberMatched, pas 100", () => {
  const records = Array.from({ length: 100 }, (_, i) => ({ id: i, properties: { v: 1 } }));
  renderIndicator(
    { agg: "count", dataSourceId: "s" },
    { data: state({ records, total: 5000, resolvedSource: { id: "s", type: "features", service: "core", layer: "c", query: {} } }) },
  );
  expect(screen.getByText("5 000")).toBeInTheDocument();
});
test("sum sur source features tronquée : badge échantillon visible", () => {
  const records = Array.from({ length: 100 }, (_, i) => ({ id: i, properties: { v: 1 } }));
  renderIndicator(
    { agg: "sum", field: "v", dataSourceId: "s" },
    { data: state({ records, total: 5000, resolvedSource: { id: "s", type: "features", service: "core", layer: "c", query: {} } }) },
  );
  expect(screen.getByRole("status")).toHaveTextContent("Échantillon : 100 sur 5000");
});
```
(Si `formatNumber` rend l'espace insécable, adapter la chaîne attendue d'après la sortie réelle du test ; ne pas assouplir l'assertion à `100`.)

Dans `chart.test.tsx` et `pivot.test.tsx`, reprendre le helper de rendu du fichier avec `data: { loading:false, error:false, records:<100 lignes valides>, total: 5000, resolvedSource:<features> }` et asserter `screen.getByRole("status")` contient « Échantillon : 100 sur 5000 » ; un second test avec `total: 100` asserte `queryByRole("status")` nul.

- [ ] **Step 3 : constater l'échec**

```bash
cd /home/lenen/projets/geostudio/shell && npx vitest run src/builder/widgets/SampleBadge.test.tsx src/builder/widgets/indicator.test.tsx src/builder/widgets/chart.test.tsx src/builder/widgets/pivot.test.tsx
```
Attendu : `SampleBadge.test.tsx` échoue (module introuvable) ; indicateur « count » affiche `100` au lieu de `5 000` ; chart/pivot : `Unable to find an accessible element with the role "status"`.

- [ ] **Step 4 : implémentation**

`shell/src/i18n/domains/widgets.ts`, après la ligne `"widgetData.truncated"` :
```ts
  "widgetData.sampled": "Échantillon : {count} sur {total}",
```

`shell/src/builder/widgets/SampleBadge.tsx` :
```tsx
// SPDX-License-Identifier: Apache-2.0
import { t } from "../../i18n";
import type { DataSourceState } from "../../api/types";

type SampleData = Pick<DataSourceState, "records" | "total" | "resolvedSource">;

// AUD-002 : une source `features` ne renvoie qu'une page (100 par défaut, 1000 au plus
// côté cœur). Tout calcul client sur ses lignes est un échantillon dès que
// numberMatched (`total`) le dépasse ; `statistics` est agrégée par le serveur.
export function isSampled(data: SampleData): boolean {
  return (
    data.resolvedSource?.type !== "statistics" &&
    data.total != null &&
    data.total > data.records.length
  );
}

export function SampleBadge({ data }: { data: SampleData }) {
  if (!isSampled(data)) return null;
  return (
    <p role="status" className="text-xs text-[var(--gs-color-muted)]">
      {t("widgetData.sampled", { count: data.records.length, total: data.total ?? 0 })}
    </p>
  );
}
```
(Vérifier le chemin d'import réel de `t` en tête de `indicator.tsx` et le reproduire.)

`indicator.tsx` — `resolveFlatValue` : changer le type du premier argument en `Pick<DataSourceState, "records" | "resolvedSource" | "total">`, et remplacer la fin par :
```ts
  if (agg === "sum") {
    return data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0);
  }
  // count : numberMatched du cœur est exact (filtres compris) ; la page ne l'est pas.
  return data.total ?? data.records.length;
```
Rendu : importer `SampleBadge` et, sous `{badge && …}`, ajouter `<SampleBadge data={data} />`. Pour `agg` autre que `count`/`sum` (avg/min/max retombent sur count, cf. d05 §« Autres »), le comportement existant est conservé : hors périmètre.

`chart.tsx` : dans le `return` final, après `<Suspense>…</Suspense>`, ajouter `<SampleBadge data={data} />`. `pivot.tsx` : juste après `<ExplorerMenu … />` du `return` final, ajouter `<SampleBadge data={data} />` (import identique).

- [ ] **Step 5 : vérifier (vert) + non-régression**

```bash
cd /home/lenen/projets/geostudio/shell && npx vitest run src/builder/widgets && npm run lint && npm run format:check && npm run build
```
Attendu : tout vert (le détecteur i18n et `hGuard` passent : aucune classe `h-8`, texte via `t()`). Falsification (piège 10) : retirer temporairement `<SampleBadge/>` du chart, constater l'échec du test chart, remettre.

- [ ] **Step 6 : commit**

```bash
git add shell/src/builder/widgets/SampleBadge.tsx shell/src/builder/widgets/SampleBadge.test.tsx shell/src/builder/widgets/{indicator,chart,pivot}.tsx shell/src/builder/widgets/{indicator,chart,pivot}.test.tsx shell/src/i18n/domains/widgets.ts
git commit -m "fix(shell): indicateur/graphique/pivot sur source features signalent l'échantillon (AUD-002)"
```

**Transverse :**
- Régénération OpenAPI + types TS : **non** (aucune route/modèle cœur touché).
- Migration Alembic : **non**.
- Inventaire des fonctionnalités / bilan : **non** (aucune surface nouvelle : ni route REST, ni outil MCP, ni route shell).
- E2E Playwright : optionnel ; si ajouté, étendre une spec d'app existante dont le mock `GET /collections/:id/items` renvoie `numberMatched: 5000` pour 100 features et asserter le texte « Échantillon : 100 sur 5000 » sur un indicateur `sum`. Lancer ensuite `npm run e2e` complet (piège 6).
- Suivi à consigner dans le backlog : source par défaut `statistics` et tableau paginé/trié serveur (d05 correctifs 2-3), non couverts ici.

## Task 8 (AUD-001) : L'export d'app/dashboard attend réellement ses widgets (requêtes + cartes) avant de lever `data-export-ready`

**Constat (D04-01, relu sur HEAD, confirmé).** `shell/src/pages/AppRuntimePage.tsx:79-83` appelle `markExportReady()` dans un `requestAnimationFrame` dès que `query.isSuccess && extensionsRegistered` : aucun widget n'est consulté. Le worker (`core/app/export/jobs.py:189-191`) attend ce seul sélecteur, donc PDF/PNG (et tout `ReportSchedule`, qui rend toujours une app, `core/app/reports/jobs.py:208-231`) capturent des spinners. Les widgets (`chart.tsx`, `indicator.tsx`, `data.tsx`, `sliderFilter.tsx`, `datasetCard.tsx`…) chargent tous via React Query ; seul le widget carte (`mapWidget.tsx:382`, `onReady`) a un signal propre.

**Jumelles examinées (piège 14).**
- `MapEditorPage.tsx:194` : lève déjà sur `idle` MapLibre (signal réel) — hors périmètre.
- `AtlasPages.tsx:37` : signal propre mais tronqué (D04-02, autre AUD) — hors périmètre.
- Les widgets carte dans une app sont la jumelle réelle : ils sont couverts ici via `trackExportTask()`.
- Pas de changement cœur : le worker n'a besoin que du même sélecteur. Le marquage « incomplet » est posé côté DOM (`data-export-incomplete`) ; sa remontée dans le job (statut/avertissement) est hors périmètre, à traiter avec AUD sur le jeton/budget (D04-05).

**Files:**
- Modify: `shell/src/shell/exportReady.ts` (ajout `trackExportTask`, `useExportReadiness`, constantes)
- Modify: `shell/src/pages/AppRuntimePage.tsx:79-83` (remplace le `useEffect` rAF) et l'import l.21
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (import + effet dans `Component`, ~l.247)
- Test: `shell/src/shell/exportReady.test.ts` (étendre), `shell/src/pages/AppRuntimePage.test.tsx` (test existant l.436 reste vert)

**Interfaces:**
- Consumes : `useIsFetching` de `@tanstack/react-query`, `useSyncExternalStore` de React.
- Produces :
  - `export const EXPORT_SETTLE_MS = 300;`
  - `export const EXPORT_TIMEOUT_MS = 90_000;`
  - `export function trackExportTask(): () => void` (incrémente un compteur global ; la fonction retournée le décrémente, idempotente)
  - `export function useExportReadiness(baseReady: boolean): void` (lève `markExportReady()` quand `baseReady`, 0 requête en cours, 0 tâche suivie, stable `EXPORT_SETTLE_MS` ; à `EXPORT_TIMEOUT_MS` lève quand même et pose `data-export-incomplete="true"`)

- [ ] **Step 1 : tests d'abord (échec attendu)**

Remplacer le contenu de `shell/src/shell/exportReady.test.ts` par (les 2 tests existants sont conservés en tête) :

```ts
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  EXPORT_SETTLE_MS,
  EXPORT_TIMEOUT_MS,
  markExportReady,
  trackExportTask,
  useExportReadiness,
} from "./exportReady";

afterEach(() => {
  delete document.body.dataset.exportReady;
  delete document.body.dataset.exportIncomplete;
  vi.useRealTimers();
});

describe("markExportReady", () => {
  it('sets data-export-ready="true" on document.body — the exact selector Task 6\'s worker waits for', () => {
    markExportReady();
    expect(document.body.getAttribute("data-export-ready")).toBe("true");
    expect(document.body.dataset.exportReady).toBe("true");
  });

  it("is idempotent: calling it twice does not throw and leaves the same attribute", () => {
    markExportReady();
    expect(() => markExportReady()).not.toThrow();
    expect(document.body.getAttribute("data-export-ready")).toBe("true");
  });
});

describe("useExportReadiness (AUD-001 / D04-01)", () => {
  let qc: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const ready = () => document.body.getAttribute("data-export-ready");

  beforeEach(() => {
    vi.useFakeTimers();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });

  it("ne lève rien tant que la base (config + extensions) n'est pas prête", () => {
    renderHook(() => useExportReadiness(false), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS * 3));
    expect(ready()).toBeNull();
  });

  it("lève après la fenêtre de stabilité quand rien n'est en cours", () => {
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS - 1));
    expect(ready()).toBeNull();
    act(() => void vi.advanceTimersByTime(2));
    expect(ready()).toBe("true");
    expect(document.body.dataset.exportIncomplete).toBeUndefined();
  });

  it("attend la fin d'une requête React Query en cours", async () => {
    let resolve!: (v: number) => void;
    const p = new Promise<number>((r) => (resolve = r));
    void qc.fetchQuery({ queryKey: ["slow"], queryFn: () => p });
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS * 5));
    expect(ready()).toBeNull();
    await act(async () => {
      resolve(1);
      await p;
    });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS + 1));
    expect(ready()).toBe("true");
  });

  it("attend une tâche suivie (widget carte) jusqu'à sa libération, libération idempotente", () => {
    const done = trackExportTask();
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS * 5));
    expect(ready()).toBeNull();
    act(() => {
      done();
      done();
    });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS + 1));
    expect(ready()).toBe("true");
  });

  it("à l'expiration, lève quand même et marque l'export incomplet", () => {
    const done = trackExportTask(); // ne se libère jamais (carte bloquée)
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_TIMEOUT_MS + 1));
    expect(ready()).toBe("true");
    expect(document.body.dataset.exportIncomplete).toBe("true");
    done();
  });
});
```

Le fichier passe en `.tsx` pour le JSX : `git mv shell/src/shell/exportReady.test.ts shell/src/shell/exportReady.test.tsx`.

- [ ] **Step 2 : constater l'échec**

```bash
cd /home/lenen/projets/geostudio/shell && git mv src/shell/exportReady.test.ts src/shell/exportReady.test.tsx
npx vitest run src/shell/exportReady.test.tsx
```
Attendu : échec (`trackExportTask`/`useExportReadiness`/`EXPORT_SETTLE_MS` non exportés → `is not a function` / `undefined`).

- [ ] **Step 3 : implémentation de `shell/src/shell/exportReady.ts`**

Conserver `markExportReady` et son commentaire tels quels, puis ajouter (imports en tête de fichier) :

```ts
import { useEffect, useSyncExternalStore } from "react";
import { useIsFetching } from "@tanstack/react-query";

// AUD-001 : fenêtre de stabilité avant de lever le signal (laisse les widgets
// montés par le rendu suivant démarrer leurs requêtes) et garde-fou de
// durée, inférieur au budget de rendu du worker (RENDER_TIMEOUT_MS = 120 s).
export const EXPORT_SETTLE_MS = 300;
export const EXPORT_TIMEOUT_MS = 90_000;

// Tâches de rendu hors React Query (ex. MapLibre « idle » d'un widget carte).
let pendingTasks = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function trackExportTask(): () => void {
  pendingTasks += 1;
  emit();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    pendingTasks -= 1;
    emit();
  };
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};
const getPending = () => pendingTasks;

// Lève `data-export-ready` quand l'app est chargée (`baseReady`), qu'aucune
// requête React Query n'est en vol et qu'aucune tâche suivie n'est ouverte,
// de façon stable pendant EXPORT_SETTLE_MS. Au-delà d'EXPORT_TIMEOUT_MS,
// capture quand même (mieux qu'un export qui expire) mais marque
// `data-export-incomplete="true"` au lieu de masquer le vide en silence.
export function useExportReadiness(baseReady: boolean): void {
  const fetching = useIsFetching();
  const tasks = useSyncExternalStore(subscribe, getPending, getPending);
  const settled = baseReady && fetching === 0 && tasks === 0;

  useEffect(() => {
    if (!settled) return;
    const id = setTimeout(markExportReady, EXPORT_SETTLE_MS);
    return () => clearTimeout(id);
  }, [settled]);

  useEffect(() => {
    const id = setTimeout(() => {
      document.body.dataset.exportIncomplete = "true";
      markExportReady();
    }, EXPORT_TIMEOUT_MS);
    return () => clearTimeout(id);
  }, []);
}
```

Appelé uniquement en mode export (voir Step 4), donc le timeout n'arme rien en usage normal.

- [ ] **Step 4 : câbler `AppRuntimePage.tsx`**

Import (l.21) : `import { markExportReady } from "../shell/exportReady";` → `import { useExportReadiness } from "../shell/exportReady";`

Remplacer le `useEffect` des l.79-83 par, et corriger le commentaire (supprimer la phrase « no per-widget … signal yet ») :

```tsx
  // AUD-001 : signal = config chargée + extensions + plus aucune requête en
  // vol ni carte en cours de chargement. Le hook ne s'arme qu'en mode export.
  useExportReadiness(
    isExportRender && !atlasMode && query.isSuccess && extensionsRegistered,
  );
```

Problème : le hook ne doit pas armer le timeout hors export. Ajuster la signature : `useExportReadiness(baseReady)` reste, mais le second `useEffect` du Step 3 devient conditionnel — remplacer son corps par `if (!baseReady) return;` avant `setTimeout` et ajouter `baseReady` aux dépendances (`[baseReady]`). Le timeout court alors depuis que la base est prête (≤ 90 s de rendu des widgets), jamais hors export ni en mode atlas (`baseReady` faux).

- [ ] **Step 5 : le widget carte suit son chargement (`mapWidget.tsx`)**

Import : `import { trackExportTask } from "../../shell/exportReady";`. Dans `Component`, juste après `const [mapReady, setMapReady] = useState(false);` :

```tsx
      // AUD-001 : un export attend le `idle` de chaque carte d'app.
      useEffect(() => {
        if (mapReady) return;
        return trackExportTask();
      }, [mapReady]);
```
(`useEffect` est déjà importé l.2.)

- [ ] **Step 6 : vérifier**

```bash
cd /home/lenen/projets/geostudio/shell
npx vitest run src/shell/exportReady.test.tsx src/pages/AppRuntimePage.test.tsx src/builder/widgets
npm run lint && npm run format:check && npm run build
```
Attendu : tout vert (le test AppRuntimePage l.436 passe : `waitFor` 1000 ms > 300 ms de stabilité). Falsification (piège 10) : retirer la condition `fetching === 0` → le test « attend la fin d'une requête » doit échouer ; la remettre.

- [ ] **Step 7 : Commit**

```bash
git add shell/src/shell/exportReady.ts shell/src/shell/exportReady.test.tsx shell/src/pages/AppRuntimePage.tsx shell/src/builder/widgets/mapWidget.tsx
git commit -m "fix(shell): l'export d'app attend requêtes et cartes des widgets avant de signaler « prêt » (AUD-001)"
```

**Drapeaux de clôture :**
- Régénération OpenAPI + types TS : non (aucune route/modèle).
- Migration Alembic : non.
- Inventaire des fonctionnalités : non (aucune surface nouvelle) ; mettre à jour la santé seulement si la porte CI le réclame.
- E2E Playwright : pas de nouvelle spec (surface non visible) ; lancer `npm run e2e -- export` pour confirmer que les specs d'export existantes restent vertes. Rejeu réel recommandé : `POST /v1/export` d'une app à graphique+tableau sur stack réelle.
- Ensuite : ligne `D04-01` fermée dans `docs/revue/2026-09-04-backlog.md` si référencée.

## Task 9 (AUD-003) : Export d'app — résoudre `datasetId` vers sa collection avant garde, gel et snapshot

**Constat revérifié sur HEAD (piège 12)** : `DataSourceSelect.tsx:35-40` crée `{type:"features", layer:"", datasetId: pk}`. `appexport/guard.py:138`, `freeze.py:40-44` et `snapshot.py:110` lisent `source.layer` sans jamais regarder `datasetId` (`grep -rn "\.layer\b" core/app/appexport` = ces 5 occurrences, aucune autre — pas de miniserver concerné). Résultat : « collection '' introuvable » dans les 3 modes (la garde est commune). Défaut confirmé.

**Décision** : un seul résolveur `resolve_dataset_sources` (config → config où chaque source `datasetId` d'un dataset `source == "collection"` devient `layer=<collectionId>, datasetId=None`, + raisons de refus pour les datasets arcgis/introuvables/hors tenant). Appelé par la garde (refus explicite) et par `jobs.py` (la config résolue alimente freeze/snapshot/bundle, y compris le mode connecté : le runtime exporté est anonyme et ne pourrait pas lire l'item dataset). Les datasets non-collection sont **refusés avec message explicite** (pas de matérialisation, hors périmètre ; seul `source` ∈ {collection, arcgis} existe dans `DatasetPayload`). Jumelles : `guard`, `freeze`, `snapshot` couvertes d'un coup puisqu'elles lisent toutes la config résolue ; `guest_access.resolve_guest_scope` fait déjà la même résolution (aucun changement).

**Files:**
- Create: `core/app/appexport/datasets.py`
- Modify: `core/app/appexport/guard.py` (import + début de `check_export_guard`, boucle `for source in config.dataSources` l.~120-150)
- Modify: `core/app/appexport/jobs.py` (`build_app_export_task`, bloc l.~141-150)
- Test: `core/tests/test_appexport_guard.py` (étendre), `core/tests/test_appexport_datasets.py` (Create), `core/tests/test_appexport_jobs.py` (étendre si un test de `_build_zip_bytes` existe ; sinon couvert par le test du résolveur)

**Interfaces:**
- Consumes : `configs_repo.get_config_by_item(session, item_id) -> ConfigRead | None`, `items_repo.get_access_facts(session, *, tenant_id, item_id)`, `BuilderConfig`, `DataSource`.
- Produces : `resolve_dataset_sources(session, *, tenant_id: str, config: BuilderConfig) -> tuple[BuilderConfig, list[str]]`.

- [ ] **Step 1 : tests du résolveur (échouent : module absent)**

`core/tests/test_appexport_datasets.py` :
```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport.datasets import resolve_dataset_sources
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, DataSource, Layout
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _owner(s):
    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice", email=None,
        first_name="", last_name="", bootstrap_admin=False,
    )
    return tenant, owner


def _dataset(s, tenant, owner, payload: dict) -> str:
    item = items_repo.create_item(
        s, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
    )
    cfg = BuilderConfig.model_validate({"kind": "dataset", "dataset": payload})
    configs_repo.create_config(s, cfg, item.id, tenant_id=tenant.id)
    s.commit()
    return item.id


def _app(dataset_id: str) -> BuilderConfig:
    return BuilderConfig(
        kind="app",
        dataSources=[
            DataSource(
                id="s1", type="features", service="core", layer="", datasetId=dataset_id, query={}
            )
        ],
        layout=Layout(type="grid", items=[]),
    )


def test_collection_dataset_is_resolved_to_its_layer():
    with _env()() as s:
        tenant, owner = _owner(s)
        ds = _dataset(s, tenant, owner, {"source": "collection", "collectionId": "col-1"})
        cfg, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=_app(ds))
    assert reasons == []
    assert cfg.dataSources[0].layer == "col-1"
    assert cfg.dataSources[0].datasetId is None


def test_arcgis_dataset_is_refused_with_explicit_reason():
    with _env()() as s:
        tenant, owner = _owner(s)
        ds = _dataset(s, tenant, owner, {"source": "arcgis", "arcgisItemId": "x"})
        _, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=_app(ds))
    assert len(reasons) == 1 and "s1" in reasons[0] and "collection" in reasons[0]


def test_unknown_or_other_tenant_dataset_is_refused():
    with _env()() as s:
        tenant, _ = _owner(s)
        _, reasons = resolve_dataset_sources(s, tenant_id=tenant.id, config=_app("nope"))
    assert len(reasons) == 1 and "introuvable" in reasons[0]
```

- [ ] **Step 2 : test de garde (échoue : « collection '' introuvable »)** — ajouter à `core/tests/test_appexport_guard.py` (réutilise `_public_collection`, `_app_config`) :
```python
def test_dataset_bound_source_on_public_collection_is_allowed_in_every_mode():
    from app.configs import repository as configs_repo
    from app.items import repository as items_repo

    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        from app.users.repository import get_or_create_user

        owner = get_or_create_user(
            s, tenant_id=tenant_id, oidc_sub="a", username="alice", email=None,
            first_name="", last_name="", bootstrap_admin=False,
        )
        item = items_repo.create_item(
            s, tenant_id=tenant_id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {"kind": "dataset", "dataset": {"source": "collection", "collectionId": col.id}}
            ),
            item.id,
            tenant_id=tenant_id,
        )
        s.commit()
        config = _app_config(
            data_sources=[
                DataSource(
                    id="s1", type="features", service="core", layer="",
                    datasetId=item.id, query={},
                )
            ]
        )
        for mode in ("static", "connected", "standalone"):
            result = check_export_guard(s, tenant_id=tenant_id, config=config, mode=mode)
            assert result.allowed is True, (mode, result.reasons)
```

Run : `cd core && CORE_TEST_DATABASE_URL=<base jetable> uv run pytest tests/test_appexport_datasets.py tests/test_appexport_guard.py -q` — attendu : ImportError sur `app.appexport.datasets`, et l'échec « collection '' introuvable ».

- [ ] **Step 3 : implémentation** — `core/app/appexport/datasets.py` :
```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-003 : une DataSource liée à un dataset (`datasetId`, `layer=""`) est
résolue vers la collection du dataset avant garde/gel/snapshot — jamais de
lecture de `source.layer` brut dans appexport. Même règle que
app.configs.guest_access.resolve_guest_scope (cloisonnement tenant via
get_access_facts). Idempotent."""

from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo


def resolve_dataset_sources(
    session: Session, *, tenant_id: str, config: BuilderConfig
) -> tuple[BuilderConfig, list[str]]:
    reasons: list[str] = []
    sources = []
    for source in config.dataSources:
        if source.type not in ("features", "statistics") or not source.datasetId:
            sources.append(source)
            continue
        facts = items_repo.get_access_facts(
            session, tenant_id=tenant_id, item_id=source.datasetId
        )
        ds = configs_repo.get_config_by_item(session, source.datasetId) if facts else None
        payload = ds.config.dataset if ds is not None and ds.kind == "dataset" else None
        if payload is None:
            reasons.append(f"source '{source.id}' : dataset '{source.datasetId}' introuvable")
            sources.append(source)
        elif payload.source != "collection" or not payload.collectionId:
            reasons.append(
                f"source '{source.id}' : l'export ne supporte que les datasets adossés "
                "à une collection (dataset SQL/pipeline/ArcGIS non exportable)"
            )
            sources.append(source)
        else:
            sources.append(
                source.model_copy(update={"layer": payload.collectionId, "datasetId": None})
            )
    return config.model_copy(update={"dataSources": sources}), reasons
```
`guard.py` : ajouter `from app.appexport.datasets import resolve_dataset_sources`, puis au début de `check_export_guard`, remplacer `reasons: list[str] = []` par :
```python
    config, reasons = resolve_dataset_sources(session, tenant_id=tenant_id, config=config)
```
et dans la boucle, après le test `source.type not in ("features","statistics")`, ajouter avant `collection_id = source.layer` :
```python
        if source.datasetId:  # non résolue : raison déjà posée par resolve_dataset_sources
            continue
```
`jobs.py` (`build_app_export_task`) : après le `if not guard_result.allowed: raise`, remplacer `config=config_read.config` dans `_build_zip_bytes` par la config résolue :
```python
            resolved, _ = resolve_dataset_sources(
                session, tenant_id=tenant_id, config=config_read.config
            )
            zip_bytes, export_warnings = _build_zip_bytes(
                session, tenant_id=tenant_id, mode=mode, config=resolved
            )
```
(+ `from app.appexport.datasets import resolve_dataset_sources`).

- [ ] **Step 4 : vérification**
```bash
cd core && CORE_TEST_DATABASE_URL=<base jetable> uv run pytest tests/test_appexport_datasets.py tests/test_appexport_guard.py tests/test_appexport_freeze.py tests/test_appexport_snapshot.py tests/test_appexport_jobs.py -q
uv run ruff check app/appexport tests && uv run ruff format --check app/appexport tests
uv run lint-imports
```
Attendu : tout vert (tests de freeze/snapshot inchangés : ils passent `layer` direct). Falsification : retirer l'appel dans `jobs.py` ne casse aucun test unitaire ; ajouter si possible un test PostGIS dans `test_appexport_jobs.py` appelant `_build_zip_bytes(mode="static")` avec une source dataset et vérifiant que le zip contient les enregistrements (sinon noter la limite en commit).

- [ ] **Step 5 : commit**
```
fix(core): export d'app — résoudre datasetId vers sa collection (AUD-003)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
```

**Régénération OpenAPI + types TS** : non (aucune route/modèle). **Migration Alembic** : non. **Inventaire des fonctionnalités** : non (aucune surface nouvelle ; corrige une surface existante). **E2E Playwright** : non (pas de changement visible ; le message de refus des datasets non-collection apparaît dans l'erreur de job existante). **Hors périmètre noté** : widgets référençant `collectionId`/`datasetId` dans leurs props (cf. d06, autre constat sur `resolve_guest_scope`).

## Task 10 (AUD-133) : Export PDF/PNG fonctionnel sur la configuration locale par défaut, message lisible, filtres transmis

Constat relu sur HEAD (piège 12) : **toujours présent**, en trois défauts distincts.

1. `core/app/export/jobs.py:271-272` : avec le compose par défaut (`VITE_CORE_URL=http://localhost:8200`, `docker-compose.yml:986`), le Chromium d'`export-worker` appelle `localhost:8200` = lui-même ; `core_unreachable_error` abandonne donc l'export à chaque fois (aucune valeur par défaut ne sert à la fois l'hôte et le worker, `.env.example:373-390`).
2. Même ligne : le message d'administrateur (`VITE_CORE_URL`, « export-worker ») est stocké tel quel dans `export_jobs.error`, affiché dans la barre et la cloche (`mark_error(error=str(exc))`, `_notify(error=str(exc))`).
3. `core/app/export/routes.py:35-39` : `CreateExportRequest` n'a ni `ctx` ni signet ; `shell/src/api/domains/exportsIngestion.ts:56-61` n'envoie que `itemId/format/entityId/atlas`. `ExportJob.ctx` existe déjà (modèle l.31, `create_job(ctx=)`, `jobs.py:264` le relaie à la page) mais seul `reports/jobs.py:222` le renseigne : le PDF d'un tableau de bord filtré montre la vue non filtrée.

Jumelles (piège 14) :
- `jobs.py:264` injecte `ctx` **non encodé** dans l'URL (`&ctx={ctx}`) : aujourd'hui sûr car produit par `encode_analytics_context` (base64url) ; dès que `ctx` vient d'un client, c'est une injection de paramètres (`&exportToken=…`). Corrigé ici : validation `^[A-Za-z0-9_-]*$` à la route **et** `quote()` au worker.
- Les rapports planifiés (`reports/jobs.py`) passent par le même worker et le même pont : couverts sans code supplémentaire.
- `app-exports` (Connecté/Autoporté) n'utilise pas Chromium : hors sujet.
- Hors périmètre (AUD-134/d15, consigné) : la fuite SSRF du Chromium d'export (`page.route` sans allowlist, d15 constat 1). Le pont ajouté ici ne route **que** l'URL publique du cœur ; il n'élargit pas l'accès.

**Files:**
- Modify: `core/app/export/jobs.py` (autour de `core_unreachable_error` l.132-155 : helper `_published_core_url`, `core_bridge_target`, `_core_bridge_handler` ; `_launch_and_navigate` l.158-210 : paramètre `core_bridge` ; `render_export_task` l.260-272 : quote `ctx`, pont, message utilisateur)
- Modify: `core/app/export/routes.py:35-39` (champ `ctx`), `:95-102` (transmission à `create_job`)
- Modify: `docker-compose.yml` (service `export-worker`, bloc `environment:` ~l.768) ; `.env.example` (~l.371-390)
- Modify: `shell/src/api/domains/exportsIngestion.ts:56-61`, `shell/src/api/types.ts:1129`, `shell/src/builder/print/ExportPanel.tsx:34-96`, `shell/src/pages/AppRuntimePage.tsx:231`
- Regénérés : `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`
- Test: `core/tests/test_export_jobs.py` (étendre, remplace l'assertion l.~588), `core/tests/test_export_routes.py` (étendre), `shell/src/builder/print/ExportPanel.test.tsx` (étendre)

**Interfaces:**
- Consumes : `export_repo.create_job(..., ctx: str | None)` (existe), `mint_export_token`, env `SHELL_BASE_URL`.
- Produces :
  - `jobs.core_bridge_target(shell_base_url: str) -> tuple[str, str] | None` : `(url publique du cœur, url interne)` quand le cœur publié est injoignable depuis le worker mais l'interne répond ; `None` sinon.
  - `jobs._core_bridge_handler(public: str, internal: str) -> Callable[[route], None]` (handler `page.route`).
  - `jobs._launch_and_navigate(url, viewport=None, core_bridge: tuple[str, str] | None = None)`.
  - `CreateExportRequest.ctx: str | None` (max 16000, `^[A-Za-z0-9_-]*$`).
  - TS : `createExport(itemId, format, scope?: { entityId?: string; atlas?: boolean; ctx?: string })` ; `<ExportPanel ctx?: string />`.
  - Env : `EXPORT_CORE_INTERNAL_URL` (défaut compose `http://core:8200`).

Pas de migration Alembic. Régénération OpenAPI + types TS : **oui** (champ `ctx` de `POST /v1/export`). Inventaire des fonctionnalités : **non** (aucune surface nouvelle : un champ sur une route déjà inventoriée). E2E Playwright : **non** ajouté (le bouton existe ; export réel exige le profil `export`, rejeu manuel au Step 12) ; test Vitest du panneau suffit.

- [ ] **Step 1 : tests rouges, cœur (jobs)** — ajouter à la fin de `core/tests/test_export_jobs.py` :

```python
class _FakeRoute:
    def __init__(self, method: str, url: str, headers: dict | None = None):
        self.request = type("R", (), {"method": method, "url": url, "headers": headers or {}})()
        self.fulfilled: dict | None = None
        self.fetched_url: str | None = None

    def fetch(self, *, url):
        self.fetched_url = url
        return type("Resp", (), {"headers": {"content-type": "application/json"}})()

    def fulfill(self, **kw):
        self.fulfilled = kw


def test_core_bridge_handler_answers_preflight_without_calling_core():
    handler = export_jobs._core_bridge_handler("http://localhost:8200", "http://core:8200")
    route = _FakeRoute(
        "OPTIONS", "http://localhost:8200/v1/me", {"origin": "http://shell:8300"}
    )
    handler(route)
    assert route.fetched_url is None
    assert route.fulfilled["status"] == 204
    h = route.fulfilled["headers"]
    assert h["access-control-allow-origin"] == "http://shell:8300"
    assert "authorization" in h["access-control-allow-headers"]


def test_core_bridge_handler_forwards_to_internal_core_with_cors():
    handler = export_jobs._core_bridge_handler("http://localhost:8200", "http://core:8200")
    route = _FakeRoute("GET", "http://localhost:8200/v1/items?x=1", {"origin": "http://shell:8300"})
    handler(route)
    assert route.fetched_url == "http://core:8200/v1/items?x=1"
    assert route.fulfilled["headers"]["access-control-allow-origin"] == "http://shell:8300"
    assert route.fulfilled["headers"]["content-type"] == "application/json"


def test_core_bridge_target_when_public_core_down_and_internal_up(tmp_path, monkeypatch):
    internal, internal_url = _serve_env_config(tmp_path, "unused")  # 404 sur /health : joignable
    public_url = f"http://127.0.0.1:{_free_port()}"
    shell, shell_url = _serve_env_config(tmp_path, public_url)
    monkeypatch.setenv("EXPORT_CORE_INTERNAL_URL", internal_url)
    try:
        assert export_jobs.core_bridge_target(shell_url) == (public_url, internal_url)
    finally:
        internal.shutdown()
        shell.shutdown()


def test_core_bridge_target_none_when_public_core_reachable(tmp_path, monkeypatch):
    core, core_url = _serve_env_config(tmp_path, "unused")
    shell, shell_url = _serve_env_config(tmp_path, core_url)
    monkeypatch.setenv("EXPORT_CORE_INTERNAL_URL", f"http://127.0.0.1:{_free_port()}")
    try:
        assert export_jobs.core_bridge_target(shell_url) is None
    finally:
        core.shutdown()
        shell.shutdown()


def test_unreachable_core_gives_user_message_not_ops_detail(db_session, monkeypatch, tmp_path):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    session.commit()
    server, shell_url = _serve_env_config(tmp_path, f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setenv("SHELL_BASE_URL", shell_url)
    monkeypatch.delenv("EXPORT_CORE_INTERNAL_URL", raising=False)
    try:
        export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    finally:
        server.shutdown()
    session.expire_all()
    error = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id).error
    assert "VITE_CORE_URL" not in error and "export-worker" not in error
    assert "administrateur" in error


def test_ctx_is_url_quoted_in_target(db_session, monkeypatch):
    session, tenant, user, item = db_session
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png",
        ctx="abc&exportToken=evil",
    )
    session.commit()
    monkeypatch.setenv("SHELL_BASE_URL", "http://shell.test")
    monkeypatch.setattr(export_jobs, "core_unreachable_error", lambda *_: None)
    monkeypatch.setattr(export_jobs, "core_bridge_target", lambda *_: None)
    seen = []
    monkeypatch.setattr(
        export_jobs, "_launch_and_navigate", lambda url, **kw: seen.append(url) or _FakePage()
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)
    assert seen and "&ctx=abc%26exportToken%3Devil" in seen[0]
    assert seen[0].count("exportToken=") == 1
```

Le test `test_render_export_task_fails_fast_when_core_unreachable` (~l.567-590) : remplacer sa dernière assertion `assert "pas joignable depuis export-worker" in refreshed.error` par `assert "administrateur" in refreshed.error` et ajouter `monkeypatch.delenv("EXPORT_CORE_INTERNAL_URL", raising=False)` avant l'appel.

- [ ] **Step 2 : tests rouges, cœur (route)** — ajouter à `core/tests/test_export_routes.py` :

```python
def test_post_export_stores_ctx_for_the_page(env):
    make_client, owner, _stranger, item_id, Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    r = client.post(
        "/v1/export", json={"itemId": item_id, "format": "pdf", "ctx": "eyJhIjoxfQ"}
    )
    assert r.status_code == 202
    with Session() as s:
        job = export_repo.get_job(s, tenant_id=owner.tenant_id, job_id=r.json()["jobId"])
        assert job.ctx == "eyJhIjoxfQ"


@pytest.mark.parametrize("bad", ["a&b=c", "a b", "é", "x" * 16001])
def test_post_export_rejects_malformed_ctx(env, bad):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    r = client.post("/v1/export", json={"itemId": item_id, "format": "png", "ctx": bad})
    assert r.status_code == 422
    assert calls == []
```

- [ ] **Step 3 : vérifier l'échec**

```bash
cd /home/lenen/projets/geostudio/core
CORE_TEST_DATABASE_URL=<base jetable> uv run pytest tests/test_export_jobs.py tests/test_export_routes.py -q -k "bridge or ctx or user_message or fails_fast"
```
Attendu : `AttributeError: module 'app.export.jobs' has no attribute '_core_bridge_handler'` / `core_bridge_target`, `ctx` ignoré (job.ctx None), 202 au lieu de 422, message contenant `VITE_CORE_URL`.

- [ ] **Step 4 : route** — `core/app/export/routes.py`, remplacer la classe `CreateExportRequest` :

```python
class CreateExportRequest(BaseModel):
    itemId: str
    format: str
    # ARC-26 / ARC-30 (PDF d'app seulement) : fiche d'une entité, ou atlas.
    entityId: str | None = Field(default=None, max_length=200)
    atlas: bool = False
    # AUD-133 : contexte analytique courant (période, emprise, cross-filter) tel
    # qu'encodé par le shell (`?ctx=`, base64url). Charset restreint : la valeur
    # est recopiée dans l'URL que le worker ouvre.
    ctx: str | None = Field(default=None, max_length=16000, pattern=r"^[A-Za-z0-9_-]+$")
```

et dans `create_export_route`, ajouter `ctx=body.ctx,` à l'appel `export_repo.create_job(...)` (après `format=body.format,`).

- [ ] **Step 5 : worker** — `core/app/export/jobs.py`. Remplacer `core_unreachable_error` (l.132-155) par :

```python
USER_EXPORT_UNAVAILABLE = (
    "L'export n'est pas disponible pour le moment (configuration du serveur). "
    "Contactez l'administrateur."
)


def _published_core_url(shell_base_url: str) -> str | None:
    """URL du cœur que la page rendue appellera (VITE_CORE_URL d'env-config.js)."""
    try:
        with urllib.request.urlopen(f"{shell_base_url}/env-config.js", timeout=5) as r:
            match = re.search(r'VITE_CORE_URL:\s*"([^"]+)"', r.read().decode())
    except (OSError, ValueError):
        return None
    return match.group(1).rstrip("/") if match else None


def _core_answers(core_url: str) -> bool | str:
    """True si le cœur répond (même 404), sinon le texte de l'erreur réseau."""
    try:
        urllib.request.urlopen(f"{core_url}/health", timeout=5).close()
    except urllib.error.HTTPError as exc:
        exc.close()
        return True
    except (OSError, ValueError) as exc:
        return str(exc)
    return True


def core_unreachable_error(shell_base_url: str) -> str | None:
    """Message technique (journaux) si le cœur que la page rendue appellera n'est
    pas joignable depuis ce conteneur (j05b-006). None = joignable, ou impossible
    à vérifier (le rendu tranchera)."""
    core_url = _published_core_url(shell_base_url)
    if core_url is None:
        return None
    result = _core_answers(core_url)
    if result is True:
        return None
    return (
        f"le cœur ({core_url}), que la page d'export appelle (VITE_CORE_URL du shell), "
        f"n'est pas joignable depuis export-worker : {result}. Définir VITE_CORE_URL sur une "
        "URL atteignable à la fois du navigateur et d'export-worker, ou EXPORT_CORE_INTERNAL_URL "
        "(cf. .env.example)."
    )


def core_bridge_target(shell_base_url: str) -> tuple[str, str] | None:
    """AUD-133 : (url publique, url interne) du cœur quand le cœur publié (ex.
    http://localhost:8200, le défaut du compose) est injoignable depuis le
    Chromium du worker mais que `EXPORT_CORE_INTERNAL_URL` répond — la
    navigation du worker est alors relayée vers le cœur interne. None = pas
    besoin de pont, ou pont impossible."""
    internal = os.environ.get("EXPORT_CORE_INTERNAL_URL", "").rstrip("/")
    public = _published_core_url(shell_base_url)
    if not internal or public is None or public == internal:
        return None
    if _core_answers(public) is True or _core_answers(internal) is not True:
        return None
    return public, internal


_BRIDGE_ALLOW_HEADERS = "authorization,content-type,if-match,x-share-link-token"


def _core_bridge_handler(public: str, internal: str):
    """Handler `page.route` : relaie les appels de la page vers le cœur interne et
    pose les en-têtes CORS (le shell, `shell:8300`, appelle un autre hôte).
    Ne couvre QUE l'origine publique du cœur — aucun accès réseau élargi."""

    def handler(route) -> None:
        request = route.request
        cors = {
            "access-control-allow-origin": request.headers.get("origin", "*"),
            "access-control-allow-headers": _BRIDGE_ALLOW_HEADERS,
            "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            "vary": "Origin",
        }
        if request.method == "OPTIONS":
            route.fulfill(status=204, headers=cors)
            return
        response = route.fetch(url=internal + request.url[len(public) :])
        route.fulfill(response=response, headers={**response.headers, **cors})

    return handler
```

`_launch_and_navigate` : nouvelle signature et pose du pont juste avant `page.goto` :

```python
def _launch_and_navigate(
    url: str,
    viewport: tuple[int, int] | None = None,
    core_bridge: tuple[str, str] | None = None,
) -> RenderPage:
```
```python
        if core_bridge is not None:
            public, internal = core_bridge
            page.route(f"{public}/**", _core_bridge_handler(public, internal))
        page.goto(url, wait_until="load", timeout=remaining_ms())
```

`render_export_task` : remplacer la construction `if ctx:` et le bloc de pré-vérification :

```python
        if ctx:
            target_url = f"{target_url}&ctx={quote(ctx, safe='')}"
```
```python
        shell_base_url = os.environ["SHELL_BASE_URL"]
        core_bridge = core_bridge_target(shell_base_url)
        if core_bridge is None and (reason := core_unreachable_error(shell_base_url)) is not None:
            # Détail d'exploitation dans les journaux ; l'utilisateur (barre,
            # cloche) ne reçoit qu'un message sans variable d'environnement.
            logger.error("export job %s : %s", job_id, reason)
            raise RuntimeError(USER_EXPORT_UNAVAILABLE)
```
et l'appel : `browser_page = _launch_and_navigate(target_url, viewport=page_pixels(print_layout), core_bridge=core_bridge)`.

Vérifier que les tests existants qui monkeypatchent `_launch_and_navigate` avec `lambda url, **kw` ou `(url, viewport=None)` acceptent `core_bridge` :
`grep -n "_launch_and_navigate" core/tests/*.py` ; adapter tout `lambda url, viewport=None:` en `lambda url, viewport=None, core_bridge=None:`. Dans ces tests, `core_bridge_target` interroge `SHELL_BASE_URL` : s'il n'est pas servi, `_published_core_url` renvoie None -> pas de pont, comportement inchangé.

- [ ] **Step 6 : compose + .env.example**

`docker-compose.yml`, service `export-worker`, après `SHELL_BASE_URL` :
```yaml
      # AUD-133 : cœur joignable DEPUIS ce conteneur. Si VITE_CORE_URL (publié par
      # le shell) ne l'est pas — défaut local http://localhost:8200 —, le Chromium
      # d'export relaie ses appels vers cette URL (core_bridge_target).
      EXPORT_CORE_INTERNAL_URL: ${EXPORT_CORE_INTERNAL_URL:-http://core:8200}
```
`.env.example`, après `SHELL_BASE_URL=http://shell:8300` (avant le bloc « CONTRAINTE ») :
```
# AUD-133 : URL du cœur joignable depuis export-worker (réseau docker). Quand
# VITE_CORE_URL n'est pas joignable depuis ce conteneur (défaut local
# http://localhost:8200), l'export relaie les appels de la page vers cette URL :
# plus besoin de VITE_CORE_URL joignable des deux côtés pour un poste local.
# Le défaut du compose (http://core:8200) suffit ; ne surcharger que si le
# service cœur porte un autre nom.
#EXPORT_CORE_INTERNAL_URL=http://core:8200
```
Mettre à jour la phrase « Cette variable ci-dessous est le vrai levier » : ajouter « (en local, le pont EXPORT_CORE_INTERNAL_URL rend ce réglage inutile) ».

- [ ] **Step 7 : shell, test rouge** — ajouter à `ExportPanel.test.tsx` (dans le `describe`, avec un rendu qui passe `ctx`) :

```tsx
  it("AUD-133 : transmet le contexte analytique courant à l'export", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    const getExportJob = vi
      .fn()
      .mockResolvedValue({ id: "job-1", status: "done", resultUrl: "https://m/x.pdf", error: null });
    const client = { createExport, getExportJob } as unknown as ItemClient;
    render(
      <ItemClientProvider client={client}>
        <ExportPanel itemId="item-1" ctx="eyJhIjoxfQ" />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));
    await waitFor(() =>
      expect(createExport).toHaveBeenCalledWith("item-1", "pdf", { ctx: "eyJhIjoxfQ" }),
    );
  });
```
Échec attendu : `toHaveBeenCalledWith("item-1","pdf",{ctx})` reçoit `("item-1","pdf")` :
`cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx`.

- [ ] **Step 8 : shell, implémentation**

`shell/src/api/types.ts:1129` et `exportsIngestion.ts:59` : `scope?: { entityId?: string; atlas?: boolean; ctx?: string }`.

`ExportPanel.tsx` : ajouter la prop `ctx?: string` (type et destructuration) et remplacer l'appel :

```tsx
      const scope = {
        ...(entityId !== undefined ? { entityId } : {}),
        ...(atlas ? { atlas } : {}),
        ...(ctx ? { ctx } : {}),
      };
      const { jobId } =
        Object.keys(scope).length > 0
          ? await client.createExport(itemId, format, scope)
          : await client.createExport(itemId, format);
```
(`pdfOnly` reste utilisé pour le sélecteur de format seulement.)

`AppRuntimePage.tsx` : avant le `return`, après `legendLayers` :

```tsx
  const exportCtx =
    currentAnalyticsContext.timeRange ||
    currentAnalyticsContext.extent ||
    Object.keys(currentAnalyticsContext.crossFilter).length > 0
      ? encodeAnalyticsContext(currentAnalyticsContext)
      : undefined;
```
et l.231 : `<ExportPanel itemId={pk} ctx={exportCtx} />` (l'atlas, par entité, garde son comportement).

- [ ] **Step 9 : régénérer OpenAPI + types**

```bash
cd /home/lenen/projets/geostudio/core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Attendu : diff limité à `CreateExportRequest.ctx` (si la route est derrière le flag éteint en CI, un diff vide est légitime : vérifier avec `CORE_EXPORT_ENABLED=true` dans la commande).

- [ ] **Step 10 : vérifications**

```bash
cd /home/lenen/projets/geostudio/core
CORE_TEST_DATABASE_URL=<base jetable> uv run pytest tests/test_export_jobs.py tests/test_export_routes.py tests/test_export_rendering.py tests/test_export_openapi.py tests/test_deployability.py tests/test_reports_jobs.py -q
uv run ruff check . && uv run ruff format --check . && uv run lint-imports
cd ../shell && npx vitest run src/builder/print src/pages/AppRuntimePage.test.tsx && npm run lint && npm run format:check && npm run build
```
Attendu : tout vert (`test_deployability` exige la variable documentée dans `.env.example` : Step 6). Pas de migration : `CORE_TEST_DATABASE_URL` sert seulement aux tests marqués postgis.

- [ ] **Step 11 : commit**

```bash
git add core/app/export core/tests/test_export_jobs.py core/tests/test_export_routes.py docker-compose.yml .env.example core/openapi.json shell/src
git commit -m "fix(core): export PDF/PNG opérant en local par défaut, message utilisateur, contexte analytique transmis (AUD-133)"
```
(terminer le message par la ligne `Co-Authored-By` fournie par l'environnement.)

- [ ] **Step 12 : rejeu manuel (stack réelle, non automatisable en CI)**

`docker compose --profile export up -d --build export-worker core shell`, sans toucher `VITE_CORE_URL`, `CORE_EXPORT_ENABLED=true` : ouvrir une app, filtrer une période, cliquer Exporter > PDF. Attendu : job `done`, PDF filtré ; `docker logs export-worker` sans erreur. Puis stopper `core` côté interne pour vérifier que l'erreur affichée est « Contactez l'administrateur » et que le détail est dans les logs. Consigner le résultat dans l'historique d'exécution ; fermer AUD-133 dans la synthèse.

## Task 11 (AUD-069) : Envoi S3 présigné (Content-Type vide) et photo de collecte perdue en silence

Constat confirmé sur HEAD (code relu, pas seulement le récit) :
- `shell/src/api/domains/exportsIngestion.ts:88-91` `uploadToPresignedUrl` fait `fetch(url, {method:"PUT", body:file})` sans `Content-Type`. Quand `file.type === ""` (`.gpkg`, `.gpx`, certains `.heic` sous Chromium/Linux) le navigateur n'envoie aucun en-tête, alors que `core/app/ingestion/storage.py:118-121` signe `ContentType` (le shell a présigné `application/octet-stream`) : 403 `SignatureDoesNotMatch`. Les appelants (`ImportFileButton.tsx:375-377`, `RasterUploadButton.tsx:96-98`, `Terrain3DUploadButton.tsx:96-98`) passent bien `file.type || "application/octet-stream"` au présignage : le correctif unique et racine est dans `uploadToPresignedUrl` (jumelles raster/terrain/import corrigées d'un coup).
- `shell/src/builder/widgets/form.tsx:306` : `uploadAttachment` envoie `"Content-Type": file.type` (vide) au lieu de la variable `contentType` calculée ligne 300, et ne teste pas `res.ok`.
- `form.tsx:766-776` : l'échec d'envoi fait `setGenericError(true)` puis `handleSubmit` (l.923) appelle `resetTo()` qui efface l'erreur (l.842) et `pendingFiles` : photo perdue en silence.
- Jumelle non concernée : `Tileset3DUploadButton.tsx:109` (URL de partie multipart, pas de `ContentType` signé, `res.ok` déjà testé).

**Files:**
- Modify: `shell/src/api/domains/exportsIngestion.ts:88-91`
- Modify: `shell/src/builder/widgets/form.tsx` (l.296-313 `uploadAttachment`, l.757-780 mutation `write`, l.703-712 états, l.835-850 `resetTo`, l.887-950 `handleSubmit`, l.1180-1184 rendu d'erreur)
- Modify: `shell/src/i18n/domains/widgets.ts` (après l.316, clé `widgetForm.attachmentRetry`)
- Test: `shell/src/api/domains/exportsIngestion.test.ts` (étendre), `shell/src/builder/widgets/form.collect.test.tsx` (étendre)

**Interfaces:**
- Consumes : `ItemClient.uploadToPresignedUrl(url: string, file: File): Promise<void>` (`api/types.ts:1098`), `presignAttachmentUpload`, `confirmAttachmentUpload`.
- Produces : signature inchangée ; `uploadToPresignedUrl` envoie toujours `Content-Type: file.type || "application/octet-stream"` ; `uploadAttachment` lève `Error("Upload failed: <status>")` si le PUT n'est pas `ok` ; la mutation `write` renvoie `{ fid: string | number; failed: Record<string, File> }`.

Pas de régénération OpenAPI/types TS, pas de migration Alembic, pas de mise à jour de l'inventaire (aucune surface nouvelle), pas de nouveau E2E (couvert par Vitest ; les mocks E2E de PUT S3 ignorent les en-têtes).

- [ ] **Step 1 : tests rouges, client d'envoi présigné**

Ajouter à la fin de `shell/src/api/domains/exportsIngestion.test.ts` (ajouter `vi` à l'import vitest : `import { expect, test, vi } from "vitest";`) :

```ts
test("uploadToPresignedUrl envoie application/octet-stream quand File.type est vide", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  try {
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
    await client.uploadToPresignedUrl("https://s3.test/u", new File(["x"], "a.gpkg", { type: "" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "https://s3.test/u",
      expect.objectContaining({
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream" },
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test("uploadToPresignedUrl conserve le type du fichier quand il est renseigné", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  try {
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
    await client.uploadToPresignedUrl(
      "https://s3.test/u",
      new File(["x"], "a.json", { type: "application/json" }),
    );
    expect(fetchMock.mock.calls[0]![1].headers).toEqual({ "Content-Type": "application/json" });
  } finally {
    vi.unstubAllGlobals();
  }
});
```

- [ ] **Step 2 : tests rouges, formulaire de collecte**

Ajouter à la fin de `shell/src/builder/widgets/form.collect.test.tsx` :

```tsx
test("la photo sans type MIME est envoyée avec le Content-Type signé", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3.test/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  renderCollect({ presignAttachmentUpload, confirmAttachmentUpload });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await userEvent.upload(input, new File(["x"], "p.heic", { type: "" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(confirmAttachmentUpload).toHaveBeenCalled());
  expect(fetchMock).toHaveBeenCalledWith(
    "https://s3.test/u",
    expect.objectContaining({ headers: { "Content-Type": "application/octet-stream" } }),
  );
});

test("un PUT S3 refusé garde la saisie en édition, la photo en file et affiche l'erreur", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 403 })
    .mockResolvedValueOnce({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const presignAttachmentUpload = vi
    .fn()
    .mockResolvedValue({ uploadUrl: "https://s3.test/u", key: "k" });
  const confirmAttachmentUpload = vi.fn().mockResolvedValue(undefined);
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  const c = renderCollect({ presignAttachmentUpload, confirmAttachmentUpload, updateFeature });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await userEvent.upload(input, new File(["x"], "p.jpg", { type: "image/jpeg" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("l'envoi de la photo a échoué");
  expect(confirmAttachmentUpload).not.toHaveBeenCalled();
  expect(screen.getByText("Photo prête : p.jpg")).toBeInTheDocument();
  // Réessayer : la saisie existe déjà (mise à jour, pas de doublon), la photo repart.
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(confirmAttachmentUpload).toHaveBeenCalledTimes(1));
  expect(c.createFeature).toHaveBeenCalledTimes(1);
  expect(updateFeature).toHaveBeenCalled();
});
```

- [ ] **Step 3 : constater l'échec**

```bash
cd /home/lenen/projets/geostudio/shell && npx vitest run src/api/domains/exportsIngestion.test.ts src/builder/widgets/form.collect.test.tsx
```
Attendu : 3-4 échecs (headers absents / `""` ; pas d'alerte « l'envoi de la photo a échoué » ; formulaire vidé donc `Photo prête : p.jpg` introuvable).

- [ ] **Step 4 : implémentation, client d'envoi**

`shell/src/api/domains/exportsIngestion.ts`, remplacer le corps de `uploadToPresignedUrl` :

```ts
    async uploadToPresignedUrl(url: string, file: File) {
      // Doit égaler le ContentType signé par le cœur (présignage : file.type || octet-stream) ;
      // sans en-tête explicite, un File.type vide n'envoie rien → 403 SignatureDoesNotMatch.
      const res = await fetch(url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    },
```

- [ ] **Step 5 : implémentation, formulaire**

a) `form.tsx` `uploadAttachment` (l.306) :

```ts
  const res = await fetch(uploadUrl, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": contentType },
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
```

b) Mutation `write` (l.757-780), remplacer le corps de `mutationFn` après la construction de `feature` :

```ts
      let fid: string | number;
      if (editingId !== null) {
        const args = [collectionId, String(editingId), feature] as const;
        if (etag) await client.updateFeature(...args, { ifMatch: etag });
        else await client.updateFeature(...args);
        fid = editingId;
      } else {
        fid = (await client.createFeature(collectionId, feature)).id;
      }
      // Photos mises en file : envoyées une fois la saisie identifiée (création ou reprise après
      // échec). Un échec ne fait pas échouer la saisie déjà enregistrée ; il est remonté
      // pour que le formulaire reste ouvert sur cette saisie avec les fichiers à renvoyer.
      const failed: Record<string, File> = {};
      for (const [key, file] of Object.entries(pendingFiles)) {
        if (!file) continue;
        try {
          await uploadAttachment(client, collectionId, String(fid), key, file);
        } catch {
          failed[key] = file;
        }
      }
      return { fid, failed };
```

Si `createFeature(...).id` n'a pas le type `string | number`, utiliser `as string | number` (le type d'`editingId` accepte les deux).

c) Ajouter l'état (après `genericError`, l.703) : `const [attachmentFailed, setAttachmentFailed] = useState(false);` ; dans `resetTo()` ajouter `setAttachmentFailed(false);`.

d) `handleSubmit` : avant `setGenericError(false)` (l.~903) ajouter `setAttachmentFailed(false);`, puis remplacer le bloc du `try` :

```ts
      const { fid, failed } = await write.mutateAsync({ properties, geometry });
      void queryClient.invalidateQueries({ queryKey: ["datasource"] });
      void queryClient.invalidateQueries({ queryKey: ["my-entries", collectionId] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties });
      if (Object.keys(failed).length > 0) {
        // Ne jamais vider le formulaire : saisie créée, photos à renvoyer par un nouvel envoi.
        setEditingId(fid);
        setPendingFiles(failed);
        setAttachmentFailed(true);
        return;
      }
      if (editingId === null) {
        resetTo();
      } else {
        void syncFromServer(editingId, false);
      }
```

e) Rendu (après le bloc `genericError`, l.1184) :

```tsx
      {attachmentFailed && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.attachmentRetry")}
        </p>
      )}
```

f) `i18n/domains/widgets.ts` après `widgetForm.saveFailed` :

```ts
  "widgetForm.attachmentRetry":
    "Saisie enregistrée, mais l'envoi de la photo a échoué. Cliquez sur Envoyer pour réessayer.",
```

- [ ] **Step 6 : vérification**

```bash
cd /home/lenen/projets/geostudio/shell && npx vitest run src/api/domains/exportsIngestion.test.ts src/builder/widgets src/shell/ImportFileButton.test.tsx src/map && npm run lint && npm run format:check && npm run build
```
Attendu : tout vert (l'ancien test « la photo choisie est envoyée… » mocke `fetch` en `{ok:true}` : toujours valable). Falsification (piège 10) : remettre temporairement `headers: {"Content-Type": file.type}` dans `uploadAttachment`, constater l'échec du test « Content-Type signé », restaurer.

- [ ] **Step 7 : commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/domains/exportsIngestion.ts shell/src/api/domains/exportsIngestion.test.ts shell/src/builder/widgets/form.tsx shell/src/builder/widgets/form.collect.test.tsx shell/src/i18n/domains/widgets.ts
git commit -m "fix(shell): PUT S3 avec Content-Type signé et photo de collecte conservée en cas d'échec (AUD-069)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

## Task 12 (AUD-075) : Items publiés `map` et `dataset` ouvrables sans connexion

**Constat vérifié sur HEAD (piège 12).** `PUBLIC_KINDS` (`core/app/items/repository.py:627`) contient `map` et `dataset` ; `GET /v1/public/configs/by-item/{id}` (`core/app/public/routes.py:266-276`) les sert correctement (`config.map` / `config.dataset`). Le défaut est 100 % shell : `getPublicAppConfig` (`shell/src/api/domains/apps.ts:70-93`) lève `config has no layout` pour ces kinds (seuls app/dashboard/site portent `layout`, `core/app/configs/schemas.py`), donc `PublicItemPage` affiche `PublicNotFound` + noindex alors que le sitemap et le social-preview annoncent l'URL. Correctif retenu (le plus court, une seule porte) : synthétiser un `AppConfig` en mémoire dans `getPublicAppConfig`, exactement comme `DatasetPage.previewConfig` (jamais persisté, un seul runtime `AppRenderer`, règle 3). Aucun changement cœur.

**Jumelles (piège 14).**
- `DatasetPage.previewConfig` (`shell/src/pages/DatasetPage.tsx:24-60`) = même synthèse : on l'extrait vers un module partagé pour ne pas avoir deux copies qui dérivent.
- `SitePublicPage` appelle aussi `getPublicAppConfig` : inchangé (kind `site` a un layout), couvert par un test de non-régression.
- `StaticItemClient`/`DesktopItemClient.getPublicAppConfig` : hors sujet (export/desktop, pas de route publique).
- Dataset `source: "arcgis"` : pas de collection locale, on garde l'erreur (introuvable) plutôt qu'une page vide ; documenté en test.
- Hors périmètre, déjà tracé par d09 §2 : la collection référencée peut ne pas être `is_public` (widgets sans données). Non corrigé ici.

**Files:**
- Create: `shell/src/api/domains/publicSynth.ts`
- Modify: `shell/src/api/domains/apps.ts:70-93` (`getPublicAppConfig`)
- Modify: `shell/src/pages/DatasetPage.tsx:1-60` (importer `datasetPreviewConfig`, supprimer `previewConfig` local, ligne ~131)
- Test: `shell/src/api/itemClient.test.ts` (après le test ligne ~3243), `shell/src/pages/DatasetPage.test.tsx` (non-régression, existant), `shell/e2e/public-catalog.spec.ts` (nouveau test)

**Interfaces:**
- Consumes: `AppConfig`, `MapLayer`, `MapTerrainConfig` (`shell/src/api/types.ts`) ; widgets `map` (props `layers`, `basemapStyle`, `center`, `zoom`, `terrain`, `dataSourceId`) et `table`.
- Produces:
  - `datasetPreviewConfig(collectionId: string, attachmentField?: string): AppConfig`
  - `mapRuntimeConfig(map: { basemap: BaseMap; view: MapViewport; layers: MapLayer[]; terrain?: MapTerrainConfig | null }): AppConfig`

- [ ] **Step 1: Écrire les tests en échec** dans `shell/src/api/itemClient.test.ts`, à la suite de `getPublicAppConfig throws when the config has no layout` :

```ts
test("getPublicAppConfig (AUD-075) synthétise un AppConfig carte pour un item map publié", async () => {
  server.use(
    http.get("https://core.test/v1/public/configs/by-item/m1", () =>
      HttpResponse.json({
        id: "cfg-m",
        itemId: "m1",
        kind: "map",
        version: 1,
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://style.test/s.json" },
            view: { center: [2.1, 48.8], zoom: 9 },
            layers: [
              { id: "l1", title: "Communes", visible: true, kind: "feature", url: "https://core.test/v1/x" },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getPublicAppConfig("m1");
  const w = cfg.layout.items[0];
  expect(w.widget).toBe("map");
  expect(w.props).toMatchObject({
    basemapStyle: "https://style.test/s.json",
    center: [2.1, 48.8],
    zoom: 9,
  });
  expect((w.props as { layers: unknown[] }).layers).toHaveLength(1);
});

test("getPublicAppConfig (AUD-075) synthétise carte+table pour un item dataset publié", async () => {
  server.use(
    http.get("https://core.test/v1/public/configs/by-item/d1", () =>
      HttpResponse.json({
        id: "cfg-d",
        itemId: "d1",
        kind: "dataset",
        version: 1,
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "col-9" } },
      }),
    ),
  );
  const cfg = await makeClient().getPublicAppConfig("d1");
  expect(cfg.dataSources[0]).toMatchObject({ type: "features", layer: "col-9" });
  expect(cfg.layout.items.map((i) => i.widget)).toEqual(["map", "table"]);
});

test("getPublicAppConfig (AUD-075) refuse un dataset arcgis (pas de collection locale)", async () => {
  server.use(
    http.get("https://core.test/v1/public/configs/by-item/d2", () =>
      HttpResponse.json({
        id: "cfg-d2",
        itemId: "d2",
        kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "x" } },
      }),
    ),
  );
  await expect(makeClient().getPublicAppConfig("d2")).rejects.toThrow();
});
```

- [ ] **Step 2: Constater l'échec.**

```bash
cd /home/lenen/projets/geostudio/shell && npx vitest run src/api/itemClient.test.ts -t "AUD-075"
```
Attendu : 2 échecs (`config has no layout`), le 3e passe déjà (throw préexistant — garde de non-régression).

- [ ] **Step 3: Créer `shell/src/api/domains/publicSynth.ts`** (déplacement du corps de `DatasetPage.previewConfig`, inchangé) :

```ts
// SPDX-License-Identifier: Apache-2.0
// AppConfig synthétisés en mémoire pour les items publiés sans `layout`
// (map, dataset) — jamais persistés : un seul runtime AppRenderer (règle 3).
import type { AppConfig, BaseMap, MapLayer, MapTerrainConfig, MapViewport } from "../types";

export function datasetPreviewConfig(
  collectionId: string,
  attachmentField?: string,
): AppConfig {
  const dataSourceId = "dataset-preview";
  return {
    kind: "app",
    theme: {},
    dataSources: [
      { id: dataSourceId, type: "features", service: "core", layer: collectionId, query: {} },
    ],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "dataset-preview-map",
          widget: "map",
          ordinal: 1,
          x: 0,
          y: 0,
          w: 6,
          h: 6,
          props: { dataSourceId, ...(attachmentField ? { popup: { attachmentField } } : {}) },
        },
        {
          id: "dataset-preview-table",
          widget: "table",
          ordinal: 1,
          x: 6,
          y: 0,
          w: 6,
          h: 6,
          props: { dataSourceId, columns: [], pageSize: 10 },
        },
      ],
    },
  };
}

export function mapRuntimeConfig(map: {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  terrain?: MapTerrainConfig | null;
}): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "public-map",
          widget: "map",
          ordinal: 1,
          x: 0,
          y: 0,
          w: 12,
          h: 12,
          props: {
            layers: map.layers,
            basemapStyle: map.basemap.style,
            center: map.view.center,
            zoom: map.view.zoom,
            cameraPitch: map.view.pitch ?? 0,
            cameraBearing: map.view.bearing ?? 0,
            terrain: map.terrain ?? null,
          },
        },
      ],
    },
  };
}
```
(Si `tsc` refuse `ordinal`/forme exacte d'un item, copier la forme de `DatasetPage.tsx:36-58` telle quelle : c'est la source.)

- [ ] **Step 4: Modifier `getPublicAppConfig`** (`apps.ts`). Ajouter l'import `import { datasetPreviewConfig, mapRuntimeConfig } from "./publicSynth";` et `BaseMap, MapLayer, MapTerrainConfig, MapViewport` au type import ; élargir le type de réponse et insérer avant le `if (!c?.layout)` :

```ts
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard" | "map" | "dataset";
          // ...champs existants inchangés...
          map?: { basemap: BaseMap; view: MapViewport; layers: MapLayer[]; terrain?: MapTerrainConfig | null };
          dataset?: { source?: string; collectionId?: string | null };
        };
      }>("GET", `/public/configs/by-item/${encodeURIComponent(pk)}`);
      const c = data.config;
      // AUD-075 : map/dataset n'ont pas de layout, on en synthétise un.
      if (c?.kind === "map" && c.map) return mapRuntimeConfig(c.map);
      if (c?.kind === "dataset" && c.dataset?.source === "collection" && c.dataset.collectionId)
        return datasetPreviewConfig(c.dataset.collectionId);
      if (!c?.layout) throw new Error("getPublicAppConfig: config has no layout");
```
(le champ `kind` du retour existant `c.kind ?? "app"` reste : après les deux `return`, `c.kind` ne peut plus être map/dataset utile ; le typer `"app" | "dashboard"` via `kind: c.kind === "dashboard" ? "dashboard" : "app"`.)

- [ ] **Step 5: Dédupliquer `DatasetPage.tsx`** : supprimer la fonction locale `previewConfig` (lignes 21-60 avec son commentaire), ajouter `import { datasetPreviewConfig } from "../api/domains/publicSynth";`, et remplacer l'appel ligne ~131 par `datasetPreviewConfig(collectionId, attachmentField)`. Retirer l'import `AppConfig` devenu inutile s'il l'est.

- [ ] **Step 6: Vérifier.**

```bash
cd /home/lenen/projets/geostudio/shell
npx vitest run src/api/itemClient.test.ts src/pages/DatasetPage.test.tsx src/pages/PublicItemPage.test.tsx src/pages/SitePublicPage.test.tsx
npm run lint && npm run build
```
Attendu : tout vert (les tests `DatasetPage` prouvent que l'extraction est neutre ; `SitePublicPage` que le kind `site` est intact). Falsification (piège 10) : retirer temporairement la ligne `if (c?.kind === "map" ...)`, constater l'échec du test map, la remettre.

- [ ] **Step 7: E2E** — ajouter à `shell/e2e/public-catalog.spec.ts` (surface visible, même helpers `mockCore`) :

```ts
test("AUD-075 : une carte publiée s'ouvre sans connexion (plus d'« introuvable »)", async ({ page }) => {
  await mockCore(page);
  const item = {
    pk: "m1", resourceType: "map", title: "Carte ouverte", abstract: "", owner: "alice",
    thumbnailUrl: null, date: "", configId: "cfg-m", isPublished: true, keywords: [],
    license: "", language: "fr",
    permissions: { read: true, write: false, delete: false, share: false },
  };
  await page.route("https://core.test/v1/public/items/m1", (r) => r.fulfill({ json: item }));
  await page.route("https://core.test/v1/public/configs/by-item/m1", (r) =>
    r.fulfill({
      json: {
        id: "cfg-m", itemId: "m1", kind: "map", version: 1,
        config: {
          kind: "map",
          map: { basemap: { style: "https://core.test/style.json" }, view: { center: [2.4, 46.6], zoom: 5 }, layers: [] },
        },
      },
    }),
  );
  await page.goto("/public/items/m1");
  await expect(page.getByRole("heading", { level: 1, name: "Carte ouverte" })).toBeAttached();
  await expect(page.getByText(/introuvable/i)).toHaveCount(0);
});
```
Si `getItem` public passe par une autre URL dans `mocks.ts`, aligner la route sur celle de `getItem` (vérifier `grep -n "public/items" shell/e2e/mocks.ts`). Lancer : `cd shell && npx playwright test e2e/public-catalog.spec.ts`.

- [ ] **Step 8: Régénérations / portes.** OpenAPI + types TS : **non** (aucune route ni modèle modifié). Migration Alembic : **non**. Inventaire des fonctionnalités : **non** (aucune surface nouvelle, correctif d'une route shell existante `/public/items/:pk` déjà inventoriée) ; mettre à jour la ligne AUD-075 / `REV` correspondante du backlog à « fermé » dans le même geste. Couverture : `npm run test` complet avant commit.

- [ ] **Step 9: Commit.**

```bash
git add shell/src/api/domains/publicSynth.ts shell/src/api/domains/apps.ts shell/src/pages/DatasetPage.tsx shell/src/api/itemClient.test.ts shell/e2e/public-catalog.spec.ts
git commit -m "fix(shell): items map/dataset publiés ouvrables sans connexion (AUD-075)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

## Task 13 : Clôture (OpenAPI/TS, bilan, documents de suivi, suites complètes)

**Files:**
- Modify : `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` (si diff)
- Modify : `docs/revue/bilan-fonctionnalites.{html,md}`, `docs/revue/historique-sante.jsonl` (régénérés)
- Modify : `docs/revue/2026-09-04-analyse-gaps.md`, `docs/revue/2026-09-04-backlog.md` (état des entrées AUD / GAP / REV concernées)
- Modify : `CLAUDE.md` (une ligne dans `### Livré`), `docs/superpowers/2026-08-27-historique-execution-continu.md` (entrée détaillée)

- [ ] **Step 1 : revue finale de branche** — relire le diff complet `git diff origin/dev...dev` ; lister les jumelles de garde par tâche (piège n°14) et vérifier que chacune est traitée ou consignée. Corriger sur place.

- [ ] **Step 2 : régénérer OpenAPI + types TS** (tâches 2, 3 et 10 l'exigent ; un diff vide est légitime pour 3) :

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 3 : inventaire + bilan de fonctionnalités** — aucune surface nouvelle attendue ; vérifier, puis :

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
```

- [ ] **Step 4 : documents de suivi** — dans `docs/revue/2026-09-04-analyse-gaps.md` et `docs/revue/2026-09-04-backlog.md`, passer à `fermé` (avec référence à SP-L0) les entrées correspondant aux AUD-151/005/006/007/020/129/002/001/003/133/069/075 ; y consigner les reliquats listés dans la section « Points à reporter » ci-dessous. Ajouter UNE ligne dans `CLAUDE.md` `### Livré` (« SP-L0 chiffres justes — 12 défauts AUD … ») et l'entrée détaillée (défauts trouvés en revue, déviations, reliquats) dans `docs/superpowers/2026-08-27-historique-execution-continu.md`. Puis `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold`.

Points à reporter (reliquats consignés par les tâches) : `ingestion/routes.py:104` et `:211` (même garde de clé faible que AUD-151, intra-tenant, pour L2) ; matérialisation des datasets arcgis/SQL/pipeline à l'export (AUD-003) ; paramètre `invalidGeometry` et rapport par fid, `ST_MakeValid` dans les compilateurs d'intersection (AUD-129) ; fan-out sur clés dupliquées de `detectChanges` (AUD-007) ; source par défaut `statistics` et tri/pagination serveur du tableau (AUD-002) ; SSRF du Chromium d'export (AUD-133) ; collection non `is_public` invisible dans un item publié (AUD-075) ; recalcul des tampons déjà matérialisés ~30 % trop courts (AUD-005).

- [ ] **Step 5 : suites complètes** (toutes vertes, sans « échec connu ») :

```bash
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
CORE_TEST_DATABASE_URL=<base postgis-test jetable> uv run pytest
cd ../shell && npm run lint && npm run format:check && npm run test && npm run build
npm run e2e
```

- [ ] **Step 6 : rejeu réel de l'export** (AUD-133 Step 12, AUD-001, AUD-003) sur stack avec le profil `export` : PDF d'un tableau de bord filtré, zip d'export d'une app à source `datasetId`. Consigner le résultat dans l'archive d'historique.

- [ ] **Step 7 : commit** : `docs: clôture SP-L0 chiffres justes` (+ trailer Co-Authored-By), puis `git fetch && git rev-list --left-right --count origin/dev...dev` avant tout push.
