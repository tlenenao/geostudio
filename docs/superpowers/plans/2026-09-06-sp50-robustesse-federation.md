# SP-50 — Robustesse des surfaces publiques de fédération : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer 4 gaps « Sérieux » de la revue SP-42 sur le module de
fédération (STAC/DCAT/moissonnage, livré SP-12) et sur trois surfaces
voisines : GAP-60 (liens STAC « items »/DCAT « STAC item-search » cassés
pour un rôle porteur d'`admin.collections.manage`), GAP-62 (une collection
cassée fait échouer 500 tout le catalogue STAC/DCAT au lieu de dégrader),
GAP-57 (absence de pagination sur `GET /collections`, `GET /stac/collections`,
`GET /dcat/catalog`, `GET /pipelines/{id}/runs`, `GET /reports/{id}/runs`,
`GET /alerts/{id}/evaluations`), GAP-59 (egress du moissonnage sans plafond
de taille de réponse, document racine illisible rapporté comme moissonnage
réussi). Aucune nouvelle fonctionnalité — robustesse et fiabilité de
surfaces déjà livrées.

**Architecture:** 9 tâches, dans l'ordre du moins au plus risqué (§5 de la
spec) : GAP-60 (Tâche 1) → GAP-62 STAC puis DCAT (Tâches 2-3) → GAP-57
familles collections (Tâches 4-6) puis historiques (Tâche 7) → GAP-59
plafond de taille (Tâche 8) puis signalement d'échec racine sur les 8
connecteurs (Tâche 9).

**Tech Stack:** Python/FastAPI + SQLAlchemy + httpx + pytest.

**Document source :**
`docs/superpowers/specs/2026-09-06-sp50-robustesse-federation-design.md`
(sections citées : §0 état vérifié, §1 GAP-60, §2 GAP-62, §3 GAP-57, §4
GAP-59, §5 ordre, §6 hors périmètre, §7 risques).

## Global Constraints

- **TDD / filet-avant-code** : chaque tâche pose ou vérifie son filet de
  test **avant** de toucher le code de production qu'elle protège.
- Commits **conventional**, un sujet par commit, français dans les messages
  (`fix(core): ...`, `test(core): ...`).
- **Suite complète rejouée avant de clore chaque tâche** — jamais un
  sous-ensemble (piège CLAUDE.md n°6) : `cd core && uv run pytest`.
- **Tout filet de test ajouté doit être vérifié par falsification** (piège
  CLAUDE.md n°10) : injecter délibérément le défaut visé, confirmer que le
  test échoue, puis retirer l'injection, avant d'écrire le correctif final.
- **Régénérer la spec OpenAPI + types TS dès qu'une route ou un modèle de
  réponse HTTP change** (piège CLAUDE.md n°1) — attendu : diff **non vide**
  pour les Tâches 4, 5, 6, 7 (nouveaux paramètres de requête et/ou nouveaux
  champs de réponse), diff **vide** pour les Tâches 1, 2, 3, 8, 9 (aucun
  changement de contrat HTTP).
- **Ne jamais deviner une interface tierce** (piège CLAUDE.md n°3) : la
  Tâche 8 s'appuie sur une API interne d'httpx (`BaseTransport.handle_request`,
  attribut `response.stream`) — vérifier son comportement exact contre la
  version verrouillée (`core/uv.lock`) avant d'écrire le correctif final, pas
  contre la documentation générale d'httpx. La Tâche 9 vérifie individuellement
  la structure de chacun des 8 connecteurs avant de choisir où insérer le
  `raise` — ne pas supposer qu'ils partagent tous la structure de
  `stac.py`.
- **Chemin de lecture / cohérence de patron (piège CLAUDE.md n°5/n°11)** :
  toute nouvelle forme de réponse (Tâches 4-7) doit être vérifiée contre les
  consommateurs shell existants (`shell/src/api/domains/collectionsAdmin.ts`,
  `pipelines.ts`, `reports.ts`, `alerts.ts`) — aucun de ces fichiers n'est
  modifié par ce plan (périmètre strictement core), mais chaque tâche
  concernée documente explicitement l'effet observable côté shell inchangé
  ou dégradé.
- **Hors périmètre explicite** (spec §6), à ne pas toucher dans ce plan :
  pagination shell (curseur, « charger plus »), `GET /dcat/datasets/{id}`
  pour la dégradation GAP-62 (sauf décision explicite en Tâche 3 si le coût
  est trivial), pagination de `GET /harvest/layers`/`/feature-layers` (déjà
  traitée ailleurs par un plafond dur), pin IP/DNS-rebinding sur l'egress.

---

## Task 1 (GAP-60) : liens STAC « items »/DCAT « STAC item-search » cassés

Corrige le seul défaut d'autorisation-lecture de ce plan : un rôle porteur
du privilège `admin.collections.manage` qui vient de lire
`GET /stac/collections/{id}` avec succès obtient un 404 en suivant le lien
« items » vers `GET /stac/collections/{id}/items` (et
`GET /stac/collections/{id}/items/{feature_id}`), alors que le patron
correct existe déjà 3 lignes plus haut dans le même fichier
(`get_collection`, `core/app/stac/routes.py:137-144`).

**Files:**
- Modify: `core/app/stac/routes.py` (`list_items` ligne 177-216, `get_item`
  ligne 219-241)
- Modify: `core/tests/test_stac_routes.py`

**Interfaces:**
- Consumes : `app.roles.guards.has_privilege`, `app.roles.privileges.Privilege.ADMIN_COLLECTIONS_MANAGE`
  (déjà importés en tête de `stac/routes.py`, lignes 21-22 — aucun nouvel
  import nécessaire), `get_readable_collection(..., can_manage_collections=...)`
  (`app/collections/routes.py:178-209`, paramètre déjà supporté, seul
  l'appel change).
- Produces : aucun changement de forme de réponse HTTP — vérifier après
  coup (diff OpenAPI attendu vide).

- [ ] **Step 1 : lire le test précédent qui a fermé le même défaut sur
  `get_collection`, comme patron direct**

```bash
sed -n '170,210p' core/tests/test_stac_routes.py
```

C'est `test_custom_role_with_collections_manage_reaches_collection_detail` —
même fixture `env`/`env_repo`, même construction de rôle sur mesure
(`create_role`, `set_user_role`, `Privilege.ADMIN_COLLECTIONS_MANAGE`).

- [ ] **Step 2 : écrire le test qui reproduit le défaut AVANT de corriger
  (falsification, piège CLAUDE.md n°10)**

Dans `core/tests/test_stac_routes.py`, nouveau test utilisant la fixture
`env_repo` (elle inclut déjà `env`, qui fournit `admin`/`regular`/`Session`,
plus le repo de features factice) :

```python
def test_custom_role_with_collections_manage_reaches_items(env_repo):
    # Round 3 : GET /stac/collections/{id} et /schema (déjà corrigés)
    # laissaient encore /stac/collections/{id}/items et /items/{feature_id}
    # sur l'ancien get_readable_collection() sans can_manage_collections.
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, admin, repo = env_repo
    _register(app, client, admin, public=False)

    with Session() as s:  # Session importé du module comme dans le test miroir
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s, tenant_id=tenant.id, name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(s, tenant_id=tenant.id, user_id=regular.id, role_id=custom.id, role_slug=custom.slug)
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User
        custom_user = s.get(User, regular_id)
        _as(app, custom_user)
        assert client.get("/stac/collections/incidents/items").status_code == 200
        assert client.get("/stac/collections/incidents/items/1").status_code == 200
```

**Adapter les noms de variables exacts** (`Session`, `regular` viennent de
la fixture `env` sous-jacente à `env_repo` — vérifier leur exposition
exacte via `env_repo` avant d'écrire le test final, `env_repo` ne renvoie
que `app, client, admin, repo` d'après sa définition ligne 233-238 : il
faudra soit étendre légèrement l'accès à `Session`/`regular` (déjà présents
dans la fixture `env` sous-jacente, récupérables via une variante locale de
la fixture ou un appel direct à `env.__wrapped__`), soit dupliquer
l'enregistrement de rôle avec un accès direct à `env` plutôt qu'`env_repo`
et overrider `get_features_repo` manuellement dans le corps du test — choisir
l'option la plus proche du style existant du fichier, ne pas deviner sans
lire `env_repo` à nouveau juste avant d'écrire ce test.

Confirmer que ce test **échoue** (404) avant la Step 3.

- [ ] **Step 3 : corriger `list_items` et `get_item`**

```python
# core/app/stac/routes.py, list_items (ligne ~190) et get_item (ligne ~230)
col = get_readable_collection(
    session,
    user,
    collection_id,
    can_manage_collections=bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    ),
)
```

- [ ] **Step 4 : rejouer le test de la Step 2, vérifier qu'il passe
  désormais**

- [ ] **Step 5 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 6 : commit**

`fix(core): les liens STAC items restent accessibles à un rôle admin.collections.manage`

---

## Task 2 (GAP-62 STAC) : une collection cassée ne fait plus échouer tout `GET /stac/collections`

**Files:**
- Modify: `core/app/stac/routes.py` (`list_collections`, ligne 79-124 —
  ajout d'imports `logging`, `sqlalchemy.exc.DBAPIError`,
  `app.collections.introspection.{TableNotFound,UnsupportedTable}`)
- Modify: `core/tests/test_stac_routes.py`

**Interfaces:**
- Consumes : même patron que `app/collections/routes.py::get_collection`
  (ligne 428-436) — tuple d'exceptions **étroit**, jamais `except Exception`.
- Produces : aucun changement de forme de réponse pour le cas nominal ; le
  cas dégradé ajoute une collection avec un `bbox`/emprise absent au lieu de
  faire échouer toute la requête en 500.

- [ ] **Step 1 : lire le patron de dégradation existant et son test miroir**

```bash
sed -n '1,60p' core/tests/test_ogc_discovery.py | grep -n "import\|def env"
sed -n '141,166p' core/tests/test_ogc_discovery.py
```

Noter la différence d'arité du `bbox_provider` (§0.1 de la spec) :
`stac_routes.get_bbox_provider` produit une fonction à **2** arguments
`(session, info)`, pas 3 — ne pas copier l'override `broken_provider(session, info, tenant_id)`
tel quel.

- [ ] **Step 2 : lire le corps de `stac.serializers.collection` pour
  vérifier qu'il accepte `bbox=None` sans lever**

```bash
grep -n "^def collection" -A 30 core/app/stac/serializers.py
```

Si le serializer suppose `bbox` non-`None` (ex. déstructuration directe),
adapter en conséquence dans la Step 4 — ne pas supposer qu'il se comporte
comme `_collection_json` (`app/collections/routes.py`), qui construit
`extent` en dehors du serializer.

- [ ] **Step 3 : écrire le test AVANT de corriger (falsification)**

Dans `core/tests/test_stac_routes.py`, deux collections enregistrées, un
override de `stac_routes.get_bbox_provider` qui lève `TableNotFound` pour
l'une des deux seulement (`incidents2` par exemple) :

```python
def test_broken_collection_degrades_instead_of_failing_whole_catalog(env, caplog):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)
    client.post("/collections", json={"tableName": "incidents2", "isPublic": True})

    def flaky_bbox_provider(session, info):
        if info.table_name == "incidents2":
            raise TableNotFound("gone")
        return [1.0, 44.0, 2.0, 45.0]

    app.dependency_overrides[stac_routes.get_bbox_provider] = lambda: flaky_bbox_provider
    resp = client.get("/stac/collections")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["collections"]]
    assert set(ids) == {"incidents", "incidents2"}
    assert "extent lookup failed" in caplog.text  # ou message équivalent choisi en Step 4


def test_broken_collection_code_bug_is_not_swallowed(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)

    def buggy_provider(session, info):
        raise TypeError("bug")

    app.dependency_overrides[stac_routes.get_bbox_provider] = lambda: buggy_provider
    with pytest.raises(TypeError):
        client.get("/stac/collections")
```

**`fake_introspector` de ce fichier lève déjà `TableNotFound` pour tout
`table_name != "incidents"`** (ligne 29-32) — vérifier si `incidents2`
provoque un conflit avec cette fixture avant d'écrire le test final (peut
nécessiter d'étendre `fake_introspector` pour accepter `incidents2` aussi,
avec une `TableInfo` distincte, ou choisir un scénario de test qui ne
dépend pas d'enregistrer une seconde collection réelle — par exemple faire
lever le `bbox_provider` conditionnellement sur `col.id` plutôt que sur
`info.table_name`, en inspectant l'ordre d'appel réel de `list_collections`).
Confirmer que les deux tests échouent avant la Step 4 (le premier en 500,
le second parce que rien ne lève encore `TypeError` de façon visible avant
correctif — à formuler précisément selon le comportement actuel observé).

- [ ] **Step 4 : corriger `list_collections`**

```python
import logging
from sqlalchemy.exc import DBAPIError
from app.collections.introspection import TableNotFound, UnsupportedTable

logger = logging.getLogger(__name__)

...
for col in _visible_collections(session, user):
    info = introspect(session, col.table_name)  # peut déjà lever avant le bloc rls
    try:
        with rls(session, col.tenant_id):
            bbox = bbox_provider(session, info)
    except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
        logger.warning("stac catalog: extent lookup failed for collection %s: %s", col.id, exc)
        bbox = None
    docs.append(serializers.collection(..., bbox=bbox, ...))
```

**Vérifier si `introspect(session, col.table_name)` lui-même doit être dans
le `try`** (il peut lever `TableNotFound`/`UnsupportedTable` avant même
d'atteindre `bbox_provider` — cf. `get_collection` de
`app/collections/routes.py` qui enveloppe les deux appels ensemble, pas
seulement le second) — reproduire cette portée exacte, ne pas rétrécir le
`try` au seul appel `bbox_provider`.

- [ ] **Step 5 : rejouer les tests de la Step 3, vérifier qu'ils passent
  désormais (le premier) et lèvent toujours (le second)**

- [ ] **Step 6 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 7 : commit**

`fix(core): GET /stac/collections dégrade une collection cassée au lieu de faire échouer tout le catalogue`

---

## Task 3 (GAP-62 DCAT) : une collection cassée ne fait plus échouer tout `GET /dcat/catalog`

Même défaut, même correctif, fichier et tests distincts — revue plus
propre en tâche séparée (spec §5).

**Files:**
- Modify: `core/app/dcat/routes.py` (`_dataset_doc` ligne 63-87, `get_catalog`
  ligne 90-115)
- Modify: `core/tests/test_dcat_routes.py`

**Interfaces:**
- Consumes : même patron que Task 2. `dcat_routes.get_bbox_provider` a la
  même signature à 2 arguments que `stac_routes.get_bbox_provider` (§0.1 de
  la spec) — vérifié, code identique dans les deux fichiers.
- Produces : aucun changement de forme de réponse pour le cas nominal.

- [ ] **Step 1 : décider où déplacer le calcul de `bbox`**

Spec §2.2 recommande de sortir le calcul de `bbox` de `_dataset_doc` vers
l'appelant (`get_catalog`), pour appliquer la même dégradation aux deux
sans dupliquer la logique dans deux fonctions. Vérifier l'usage de
`_dataset_doc` : appelé par `get_catalog` (boucle) **et** par `get_dataset`
(détail par id, ligne 118-148, hors périmètre de ce défaut précis — spec
§6). Si `bbox` sort de la signature de `_dataset_doc` vers un paramètre
explicite, `get_dataset` doit continuer à fonctionner sans dégradation
(comportement actuel conservé pour le détail par id, décision explicite de
scope) — calculer `bbox` normalement (sans try/except) dans `get_dataset`,
avec dégradation uniquement dans `get_catalog`.

- [ ] **Step 2 : écrire les deux tests AVANT de corriger (même patron que
  Task 2 Step 3, transposé à `/dcat/catalog`)**

```python
def test_broken_collection_degrades_instead_of_failing_whole_catalog(env, caplog):
    ...
    resp = client.get("/dcat/catalog")
    assert resp.status_code == 200
    ids = [d["dct:identifier"] for d in resp.json()["dcat:dataset"]]
    assert set(ids) == {"incidents", "incidents2"}


def test_broken_collection_code_bug_is_not_swallowed(env):
    ...
    with pytest.raises(TypeError):
        client.get("/dcat/catalog")
```

Vérifier la clé exacte du dataset dans le JSON-LD produit (`dct:identifier`
confirmé par `app/dcat/serializers.py:114`) avant d'écrire l'assertion.
Confirmer l'échec des deux tests avant la Step 3.

- [ ] **Step 3 : corriger `_dataset_doc`/`get_catalog`**

```python
def _dataset_doc(*, base, col, bbox, publisher_name):  # bbox désormais un paramètre
    ...  # corps inchangé, retire le calcul introspect+bbox_provider+rls interne


def _resolve_bbox(session, col, *, introspect, bbox_provider, rls) -> list[float] | None:
    try:
        info = introspect(session, col.table_name)
        with rls(session, col.tenant_id):
            return bbox_provider(session, info)
    except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
        logger.warning("dcat catalog: extent lookup failed for collection %s: %s", col.id, exc)
        return None


@router.get("/catalog")
def get_catalog(...):
    ...
    datasets = [
        _dataset_doc(
            base=base, col=col,
            bbox=_resolve_bbox(session, col, introspect=introspect, bbox_provider=bbox_provider, rls=rls),
            publisher_name=tenant.name,
        )
        for col in cols
    ]
    ...


@router.get("/datasets/{collection_id}")
def get_dataset(...):
    ...  # get_readable_collection inchangé, 404 propre déjà en place
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        bbox = bbox_provider(session, info)  # PAS de try/except ici, décision de scope §6
    doc = _dataset_doc(base=base, col=col, bbox=bbox, publisher_name=tenant.name)
```

Adapter les imports (`logging`, `DBAPIError`, `TableNotFound`,
`UnsupportedTable`) en tête de `app/dcat/routes.py`.

- [ ] **Step 4 : rejouer les tests de la Step 2**

- [ ] **Step 5 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 6 : commit**

`fix(core): GET /dcat/catalog dégrade une collection cassée au lieu de faire échouer tout le catalogue`

---

## Task 4 (GAP-57 Famille A.1) : pagination de `GET /collections`

**Files:**
- Modify: `core/app/collections/routes.py` (`list_collections`, ligne
  316-354)
- Modify: `core/tests/test_collections_routes.py`

**Interfaces:**
- Consumes : `repo.list_visible_collections` (signature **inchangée** —
  slicing appliqué en Python après l'appel, spec §3.1/§3.2, pas en SQL).
- Produces : nouveaux champs `numberMatched`/`numberReturned` dans la
  réponse JSON, nouveaux paramètres de requête `limit`/`offset` — diff
  OpenAPI attendu **non vide**.
- **Effet shell documenté (non corrigé ici)** : `shell/src/api/domains/collectionsAdmin.ts:30`
  appelle `GET /collections${qs}` sans `limit` ; avec le défaut `limit=100`,
  un tenant à >100 collections verrait sa liste d'administration tronquée
  à 100 sans pagination UI pour voir la suite (spec §3.2, §7 — risque
  assumé, hors périmètre shell de ce plan).

- [ ] **Step 1 : écrire le test AVANT de corriger**

```python
def test_list_collections_is_paginated(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    for i in range(150):
        client.post("/collections/empty", json={"tableName": f"t{i}", "geometryType": "Point", "srid": 4326})
    body = client.get("/collections").json()
    assert len(body["collections"]) == 100  # DEFAULT_LIMIT, pas 150
    assert body["numberMatched"] == 150
    assert body["numberReturned"] == 100
    body2 = client.get("/collections?limit=100&offset=100").json()
    assert len(body2["collections"]) == 50
```

**Vérifier la route exacte de création rapide de collections dans ce
fichier de test avant d'écrire la boucle** (`POST /collections/empty` avec
quel corps exact — grep `def test_.*empty` dans le même fichier plutôt que
deviner le schéma `EmptyCollectionCreate`). Confirmer l'échec (150 items
renvoyés, pas de clé `numberMatched`) avant la Step 2.

- [ ] **Step 2 : corriger `list_collections`**

```python
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

@router.get("/collections")
def list_collections(
    q: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    ...
    cols = repo.list_visible_collections(session, tenant_id=tenant_id, user_id=..., can_see_all=..., q=q)
    limit = min(limit, MAX_LIMIT)
    total = len(cols)
    cols_page = cols[offset : offset + limit]
    owner_ids = {c.owner_id for c in cols_page}
    owners = (...)
    permissions_by_id = repo.collection_permissions_by_id(..., collections=cols_page)
    return {
        "collections": [_collection_json(c, permissions_by_id[c.id], owner=owners.get(c.owner_id)) for c in cols_page],
        "numberMatched": total,
        "numberReturned": len(cols_page),
    }
```

Ajouter `Query` à l'import `fastapi` en tête du fichier si absent (vérifier —
`from fastapi import APIRouter, Depends, HTTPException, Request` actuel, pas
de `Query`).

- [ ] **Step 3 : rejouer le test de la Step 1**

- [ ] **Step 4 : suite complète + régénération OpenAPI/TS**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts  # attendu : non vide
```

- [ ] **Step 5 : commit**

`feat(core): GET /collections accepte limit/offset et plafonne la liste renvoyée`

---

## Task 5 (GAP-57 Famille A.2) : pagination de `GET /stac/collections`

**Files:**
- Modify: `core/app/stac/routes.py` (`list_collections`, ligne 79-124 —
  déjà retouché par la Task 2, vérifier qu'aucun conflit de merge)
- Modify: `core/tests/test_stac_routes.py`

**Interfaces:**
- Consumes : `MAX_LIMIT`/`DEFAULT_LIMIT` déjà déclarés en tête de fichier
  (ligne 28-29) — réutiliser tels quels, ne pas en redéclarer.
- Produces : nouveaux paramètres `limit`/`offset`, nouveau lien `rel=next`
  conditionnel dans `links` — diff OpenAPI attendu **non vide**.

- [ ] **Step 1 : écrire le test AVANT de corriger**

```python
def test_stac_collections_list_is_paginated(env):
    app, client, admin, _regular, _Session = env
    for i in range(3):
        client.post("/collections", json={"tableName": f"t{i}", "isPublic": True})
    _as(app, admin)
    body = client.get("/stac/collections?limit=2&offset=0").json()
    assert len(body["collections"]) == 2
    rels = {link["rel"]: link["href"] for link in body["links"]}
    assert "offset=2" in rels["next"]
    body2 = client.get("/stac/collections?limit=2&offset=2").json()
    assert len(body2["collections"]) == 1
    assert "next" not in {link["rel"] for link in body2["links"]}
```

Confirmer l'échec (paramètre `limit` actuellement ignoré, pas de `rel=next`)
avant la Step 2.

- [ ] **Step 2 : corriger `list_collections`**

```python
@router.get("/collections")
def list_collections(
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    ...
):
    limit = min(limit, MAX_LIMIT)
    cols = _visible_collections(session, user)
    total = len(cols)
    cols_page = cols[offset : offset + limit]
    docs = [... for col in cols_page]  # boucle existante avec dégradation Task 2
    base = _base(request)
    links = [
        {"rel": "self", "type": "application/json", "href": f"{base}/stac/collections"},
        {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
    ]
    if offset + len(cols_page) < total:
        links.append({
            "rel": "next", "type": "application/json",
            "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
        })
    return {"collections": docs, "links": links}
```

- [ ] **Step 3 : rejouer le test de la Step 1**

- [ ] **Step 4 : suite complète + régénération OpenAPI/TS**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 5 : commit**

`feat(core): GET /stac/collections accepte limit/offset et expose un lien next`

---

## Task 6 (GAP-57 Famille A.3) : pagination de `GET /dcat/catalog`

**Files:**
- Modify: `core/app/dcat/routes.py` (`get_catalog`, retouché par la Task 3
  — vérifier l'absence de conflit)
- Modify: `core/tests/test_dcat_routes.py`

**Interfaces:**
- Consumes : aucune constante `MAX_LIMIT`/`DEFAULT_LIMIT` existante dans ce
  fichier — à ajouter (mêmes valeurs que STAC, 1000/100).
- Produces : nouveaux paramètres `limit`/`offset`, nouveau champ `"links"`
  non-RDF (extension pragmatique documentée en commentaire, spec §3.4) —
  diff OpenAPI attendu **non vide**.

- [ ] **Step 1 : écrire le test AVANT de corriger**

```python
def test_dcat_catalog_is_paginated(env):
    app, client, admin, _regular, _Session = env
    for i in range(3):
        client.post("/collections", json={"tableName": f"t{i}", "isPublic": True})
    _as(app, admin)
    body = client.get("/dcat/catalog?limit=2&offset=0").json()
    assert len(body["dcat:dataset"]) == 2
    rels = {link["rel"]: link["href"] for link in body.get("links", [])}
    assert "offset=2" in rels["next"]
```

Confirmer l'échec avant la Step 2.

- [ ] **Step 2 : corriger `get_catalog`**

```python
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

@router.get("/catalog")
def get_catalog(
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    ...
):
    limit = min(limit, MAX_LIMIT)
    cols = _visible_collections(session, user, tenant)
    total = len(cols)
    cols_page = cols[offset : offset + limit]
    datasets = [... for col in cols_page]  # boucle existante avec dégradation Task 3
    doc = serializers.catalog(base=base, tenant_name=tenant.name, datasets=datasets)
    if offset + len(cols_page) < total:
        doc["links"] = [{
            "rel": "next",
            "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
        }]
    return JSONResponse(content=doc, media_type=MEDIA_TYPE)
```

Ajouter `Query` à l'import `fastapi` en tête du fichier si absent (vérifier
l'import actuel : `from fastapi import APIRouter, Depends, Request`).

- [ ] **Step 3 : rejouer le test de la Step 1**

- [ ] **Step 4 : suite complète + régénération OpenAPI/TS**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 5 : commit**

`feat(core): GET /dcat/catalog accepte limit/offset et expose un lien de pagination`

---

## Task 7 (GAP-57 Famille B) : pagination des historiques pipelines/rapports/alertes

Un seul patron répété 3 fois (précédent direct : Task 3 de
`docs/superpowers/plans/2026-09-05-sp49-fiabilite-jobs.md`, batching des 3
mêmes familles pour un autre défaut) — traité en une tâche.

**Files:**
- Modify: `core/app/pipelines/repository.py` (`list_runs`, ligne 39-51),
  `core/app/pipelines/routes.py` (`list_pipeline_runs`, ligne 83-102)
- Modify: `core/app/reports/repository.py` (`list_runs`, ligne 55-65),
  `core/app/reports/routes.py` (`get_report_runs_route`, ligne 51-...)
- Modify: `core/app/alerts/repository.py` (`list_evaluations`, ligne
  113-131), `core/app/alerts/routes.py` (`get_alert_evaluations`, ligne
  68-88)
- Modify: `core/tests/test_pipeline_repository.py`,
  `core/tests/test_report_repository.py`, `core/tests/test_alert_repository.py`,
  `core/tests/test_pipeline_routes.py`, `core/tests/test_report_routes.py`,
  `core/tests/test_alert_routes.py`

**Interfaces:**
- Consumes : aucune dépendance nouvelle.
- Produces : `response_model` inchangé (`list[RunStatus]`/
  `list[ReportRunStatus]`/`list[EvaluationStatus]`, bare list) — nouveaux
  paramètres de requête `limit`/`offset` uniquement. Diff OpenAPI attendu
  **non vide** (nouveaux paramètres de requête) mais forme de réponse
  identique.
- **Effet shell documenté (non corrigé ici)** : `pipelines.ts:86`,
  `reports.ts:65`, `alerts.ts:75` n'envoient aujourd'hui aucun `limit`/
  `offset` — recevront par défaut les 100 lignes les plus récentes
  (`created_at.desc()`, ordre déjà existant) au lieu de la totalité. Risque
  de régression fonctionnelle jugé faible (spec §3.5) : aucune UI existante
  n'affiche « toutes » les lignes simultanément.

- [ ] **Step 1 : écrire les 3 tests repository AVANT de corriger**

```python
# test_pipeline_repository.py
def test_list_runs_respects_limit_and_offset():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        for _ in range(5):
            repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        page = repo.list_runs(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id, limit=2, offset=0)
        assert len(page) == 2
        page2 = repo.list_runs(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id, limit=2, offset=4)
        assert len(page2) == 1
```

Transposer à l'identique pour `test_report_repository.py`
(`report_item_id`) et `test_alert_repository.py`
(`alert_rule_item_id`/`create_evaluation`). Confirmer que les 3 échouent
(TypeError, paramètres inexistants) avant la Step 2.

- [ ] **Step 2 : ajouter `limit`/`offset` aux 3 fonctions repository**

```python
# app/pipelines/repository.py
def list_runs(
    session: Session, *, tenant_id: str, pipeline_item_id: str,
    limit: int = 100, offset: int = 0,
) -> list[PipelineRun]:
    rows = (
        session.execute(
            select(PipelineRun)
            .where(PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id)
            .order_by(PipelineRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows)
```

Symétrique pour `app/reports/repository.py::list_runs` et
`app/alerts/repository.py::list_evaluations`.

- [ ] **Step 3 : rejouer les 3 tests de la Step 1**

- [ ] **Step 4 : écrire les 3 tests routes AVANT de corriger**

```python
# test_pipeline_routes.py
def test_list_pipeline_runs_accepts_limit_and_offset(...):
    ...
    resp = client.get(f"/pipelines/{item_id}/runs?limit=2&offset=0")
    assert len(resp.json()) == 2
```

Transposer pour `test_report_routes.py`/`test_alert_routes.py`. Confirmer
l'échec (paramètre ignoré, toutes les lignes renvoyées) avant la Step 5.

- [ ] **Step 5 : ajouter `limit`/`offset` aux 3 routes**

```python
# app/pipelines/routes.py
MAX_LIMIT = 1000

@router.get("/pipelines/{item_id}/runs", response_model=list[RunStatus])
def list_pipeline_runs(
    item_id: str,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunStatus]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    require_pipeline_config(session, item_id)
    limit = min(limit, MAX_LIMIT)
    runs = pipelines_repo.list_runs(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id, limit=limit, offset=offset
    )
    return [...]
```

Symétrique pour `app/reports/routes.py::get_report_runs_route` et
`app/alerts/routes.py::get_alert_evaluations`. **Ajouter `Query` à l'import
`fastapi`** dans `reports/routes.py` et `alerts/routes.py` (absent
aujourd'hui — vérifié, seul `pipelines/routes.py` l'importe déjà).

- [ ] **Step 6 : rejouer les 3 tests de la Step 4**

- [ ] **Step 7 : suite complète + régénération OpenAPI/TS**

```bash
cd core && uv run pytest
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 8 : commit**

`feat(core): historiques pipelines/rapports/alertes acceptent limit/offset et sont plafonnés par défaut`

---

## Task 8 (GAP-59.1) : plafond de taille de réponse sur l'egress de moissonnage

**Files:**
- Modify: `core/app/harvest/egress.py` (`_GuardedTransport.handle_request`,
  ligne 73-79)
- Modify: `core/tests/test_harvest_egress.py`

**Interfaces:**
- Consumes : `httpx.BaseTransport`/`httpx.MockTransport` (test uniquement).
- Produces : nouvelle exception publique `ResponseTooLargeError`, nouvelle
  variable d'environnement `CORE_HARVEST_MAX_RESPONSE_BYTES` (à documenter
  dans `.env.example` si le dépôt le fait systématiquement pour toute
  nouvelle variable — vérifier la convention avant de clore la tâche).

- [ ] **Step 1 : vérifier l'API `httpx.BaseTransport`/`response.stream`
  contre la version verrouillée (piège CLAUDE.md n°3, ne pas deviner)**

```bash
cd core && uv run python -c "import httpx; print(httpx.__version__)"
uv run python -c "
import httpx
def handler(request):
    return httpx.Response(200, content=b'x' * 100)
transport = httpx.MockTransport(handler)
with httpx.Client(transport=transport) as c:
    # inspecter transport.handle_request directement, sans passer par .get(),
    # pour confirmer la forme de la réponse brute (attribut .stream, .read())
    req = httpx.Request('GET', 'http://test/')
    resp = transport.handle_request(req)
    print(type(resp.stream), list(resp.stream))
"
```

Ajuster l'implémentation de la Step 3 selon ce que cette vérification
révèle réellement (ne pas supposer que `response.stream` est directement
itérable de la façon décrite dans la spec §4.1 sans l'avoir confirmé).

- [ ] **Step 2 : écrire le test AVANT de corriger (falsification)**

```python
def test_guarded_transport_rejects_oversized_response(monkeypatch):
    from app.harvest.egress import _GuardedTransport, ResponseTooLargeError

    monkeypatch.setenv("CORE_HARVEST_MAX_RESPONSE_BYTES", "10")

    def handler(request):
        return httpx.Response(200, content=b"x" * 1000)

    inner = httpx.MockTransport(handler)
    # Contourne assert_egress_allowed (bloquerait un hôte de test interne) :
    # construire le client directement avec _GuardedTransport(inner), sans
    # passer par build_guarded_client() qui compose HTTPTransport() en dur.
    monkeypatch.setattr("app.harvest.egress.assert_egress_allowed", lambda url: None)
    client = httpx.Client(transport=_GuardedTransport(inner))
    with pytest.raises(ResponseTooLargeError):
        client.get("http://test/")


def test_guarded_transport_allows_response_within_limit(monkeypatch):
    from app.harvest.egress import _GuardedTransport

    monkeypatch.setenv("CORE_HARVEST_MAX_RESPONSE_BYTES", "10000")
    monkeypatch.setattr("app.harvest.egress.assert_egress_allowed", lambda url: None)

    def handler(request):
        return httpx.Response(200, content=b"ok", headers={"content-type": "application/json"})

    client = httpx.Client(transport=_GuardedTransport(httpx.MockTransport(handler)))
    resp = client.get("http://test/")
    assert resp.status_code == 200
    assert resp.content == b"ok"
```

Confirmer que les deux tests échouent (import error sur
`ResponseTooLargeError`, `_GuardedTransport` ne prend qu'un paramètre)
avant la Step 3.

- [ ] **Step 3 : implémenter le plafond dans `_GuardedTransport`**

Reprendre le corps de la spec §4.1, ajusté selon la Step 1. Ne pas oublier
de fermer la réponse originale (`response.close()`) dans tous les cas
(succès et dépassement) pour ne pas fuir une connexion.

- [ ] **Step 4 : rejouer les tests de la Step 2 et la suite existante de
  `test_harvest_egress.py` (non-régression sur les tests déjà présents,
  notamment `test_guarded_client_transport_blocks_before_connection`)**

- [ ] **Step 5 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 6 : commit**

`fix(core): l'egress de moissonnage plafonne la taille des réponses distantes`

---

## Task 9 (GAP-59.2) : document racine illisible n'est plus rapporté comme moissonnage réussi

**Files:**
- Modify: `core/app/harvest/connectors/base.py` (nouvelle exception
  `HarvestFetchError`)
- Modify: `core/app/harvest/connectors/stac.py`, `arcgis.py`, `ckan.py`,
  `csw.py`, `ogc_records.py`, `wfs.py`, `wms.py`, `wmts.py` (un seul point
  de changement par fichier, portée exacte à vérifier individuellement —
  spec §4.2)
- Modify: `core/tests/test_harvest_stac_connector.py`,
  `test_harvest_arcgis_connector.py`, `test_harvest_ckan_connector.py`,
  `test_harvest_csw_connector.py`, `test_harvest_ogc_records_connector.py`,
  `test_harvest_wfs_connector.py`, `test_harvest_wms_connector.py`,
  `test_harvest_wmts_connector.py`
- Modify (vérification, pas de code attendu) : `core/tests/test_harvest_service.py`
  — `harvest_source` ne change pas, mais un test de bout en bout confirmant
  qu'une `HarvestFetchError` levée par le connecteur produit bien
  `source.last_status == "error"` referme la boucle.

**Interfaces:**
- Consumes : rien de nouveau — `harvest_source` (`app/harvest/service.py:66-74`)
  capture déjà `Exception` largement, aucune modification de ce fichier
  n'est nécessaire (à confirmer explicitement en Step 5, pas juste supposé).
- Produces : `HarvestFetchError`, exportée depuis
  `app/harvest/connectors/base.py` aux côtés de `HarvestedRecord`/
  `HarvestConnector`/`HttpGet`.

- [ ] **Step 1 : ajouter `HarvestFetchError` dans `connectors/base.py`**

```python
class HarvestFetchError(Exception):
    """Le document racine d'une source de moissonnage est injoignable ou
    illisible (réseau, HTTP, JSON/XML malformé) — distinct d'un document
    enfant tolérable (lien cassé plus profond dans l'arborescence, cf.
    docstring de chaque connecteur). Levée uniquement pour le tout premier
    accès réseau d'un fetch(), jamais pour un enfant découvert en cours de
    parcours. Propagée telle quelle par harvest_source (déjà un except
    Exception large, app/harvest/service.py:66-74) — source.last_status
    passe "error" au lieu d'"ok" avec zéro enregistrement (SP-50, GAP-59)."""
```

- [ ] **Step 2 : `stac.py` — cas le plus documenté, traiter en premier
  comme patron de référence**

Test AVANT correction (falsification) dans
`test_harvest_stac_connector.py` :

```python
def test_root_document_unreachable_raises_harvest_fetch_error(monkeypatch):
    from app.harvest.connectors.base import HarvestFetchError
    from app.harvest.connectors.stac import StacConnector

    def broken_get(url, timeout=None):
        raise httpx.ConnectError("boom")

    client = SimpleNamespace(get=broken_get, close=lambda: None)
    connector = StacConnector(client=client)
    with pytest.raises(HarvestFetchError):
        list(connector.fetch("https://example.com/stac"))


def test_child_document_unreachable_still_tolerated(monkeypatch):
    # Un lien "child" cassé PLUS PROFOND dans l'arborescence reste toléré
    # (comportement existant, ne doit pas régresser) — construire un
    # document racine valide de type Catalog avec un lien child vers une
    # URL qui échoue, vérifier que fetch() ne lève pas et renvoie les
    # collections des AUTRES liens valides.
    ...
```

Confirmer que le premier test échoue (aujourd'hui `fetch()` renvoie `[]`
silencieusement) et que le second passe déjà (comportement existant
préservé, sert de garde non-régression) avant la Step 3.

Corriger `_walk` (ligne 49-59) : au seul appel où `depth == 0`, remplacer
`return` par `raise HarvestFetchError(f"document racine STAC injoignable ou illisible : {url} ({exc})") from exc`
dans le bloc `except (httpx.HTTPError, ValueError)`. Les appels à
`depth > 0` gardent le `return` (log + tolérance) inchangé.

- [ ] **Step 3 : `csw.py`, `wfs.py`, `wms.py`, `wmts.py` — cas à appel
  racine unique**

Pour chacun, un seul point d'échec (`_first_page`/`client.get(caps_url)`) :
lever `HarvestFetchError` au lieu de `return []`/`return None`. Même
discipline TDD (test de falsification par fichier, un par connecteur,
avant la correction de ce fichier précis). Vérifier pour `csw.py`
spécifiquement que `_first_page` (qui tente ISO puis DC en repli, ligne
46-55) ne doit lever que si **les deux tentatives** échouent — pas après
la première (le repli DC est un comportement voulu, pas une racine
injoignable au sens de ce défaut).

- [ ] **Step 4 : `arcgis.py`, `ckan.py`, `ogc_records.py` — cas avec
  pagination/sous-requêtes internes, vérifier individuellement avant de
  coder**

Pour chacun, lire le corps complet de `_fetch` avant de décider où insérer
le `raise` (spec §4.2 — ne pas supposer une structure identique à
`stac.py`) :
- `arcgis.py` : le tout premier `_get_json(client, f"{service_url}?f=json")`
  est la racine ; les appels suivants (par couche, dans la boucle) — à
  vérifier s'ils lèvent déjà `HTTPError` de façon non capturée ou s'ils ont
  leur propre tolérance à préserver.
- `ckan.py` : le premier passage de la boucle `while True` (page 1 de
  `package_search`) est la racine ; les pages suivantes peuvent rester
  tolérantes (troncature déjà existante via `_MAX_CKAN_PAGES`).
- `ogc_records.py` : déterminer si l'appel racine est dans
  `_list_collections` ou son premier appel interne — lire le corps complet
  de la fonction (non lu en intégralité pendant cette recherche) avant de
  coder.

Même discipline TDD par fichier.

- [ ] **Step 5 : vérifier `harvest_source` sans le modifier**

```bash
grep -n "except Exception" core/app/harvest/service.py
```

Confirmer que le `except Exception` de la ligne 66-74 capture bien
`HarvestFetchError` sans changement de code (c'est une sous-classe
d'`Exception`, donc oui par construction — mais vérifier qu'aucun test
existant sur `harvest_source` ne mocke un connecteur d'une façon qui
contournerait ce chemin). Ajouter un test de bout en bout dans
`test_harvest_service.py` si un tel cas n'existe pas déjà :

```python
def test_harvest_source_marks_error_when_root_document_unreachable(monkeypatch):
    ...
    # connecteur factice dont fetch() lève HarvestFetchError
    harvest_source(session, source, http_get=guarded_get)
    assert source.last_status == "error"
    assert "..." in source.last_error
```

- [ ] **Step 6 : suite complète**

```bash
cd core && uv run pytest
```

- [ ] **Step 7 : commit**

`fix(core): un document racine de moissonnage illisible est rapporté en erreur au lieu d'un succès silencieux à zéro enregistrement`

---

## Vérification finale de branche (toutes tâches closes)

- [ ] `cd core && uv run pytest` — suite complète, 0 échec.
- [ ] `cd core && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd core && uv run lint-imports`
- [ ] `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types` —
  diff final cohérent avec les Tâches 4-7 (nouveaux paramètres/champs), rien
  d'inattendu venu des Tâches 1-3/8-9.
- [ ] `cd shell && npm run build` — les types générés compilent toujours
  (aucun consommateur shell n'est censé casser, mais un changement de forme
  de réponse peut révéler un usage non anticipé).
- [ ] Revue finale de branche distincte de la revue par tâche (piège
  CLAUDE.md n°4) — vérifier en particulier :
  - que la Task 1 (GAP-60) et les Tasks 2/5 (GAP-62/pagination STAC) ne se
    marchent pas dessus sur le même bloc de code (`list_items`/`get_item`
    vs `list_collections`, fichiers distincts mais même module) ;
  - que le tuple d'exceptions capturé dans les Tasks 2/3 reste **identique**
    à celui de `app/collections/routes.py::get_collection`
    (`TableNotFound, UnsupportedTable, DBAPIError`) — pas un sur-ensemble
    ni un sous-ensemble ;
  - que les défauts assumés et documentés (§3.2, §3.5 de la spec —
    troncature shell de `/collections` à 100, historiques par défaut aux
    100 plus récents) sont bien mentionnés dans le message de PR/la
    communication à Tanguy, pas seulement dans la spec.
- [ ] Relire `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`
  (ou son successeur courant) — ajouter l'entrée SP-50 à `CLAUDE.md`
  §Livré, avec mention explicite : GAP-57/59/60/62 clos ; ce qui reste
  ouvert (pagination shell non câblée pour `/collections` et les 3
  historiques, `GET /dcat/datasets/{id}` non aligné sur la dégradation
  GAP-62 sauf décision contraire prise en Task 3).
