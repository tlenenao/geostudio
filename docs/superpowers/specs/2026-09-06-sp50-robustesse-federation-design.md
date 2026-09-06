# SP-50 — Robustesse des surfaces publiques de fédération

**Date** : 2026-09-06
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (feuille de route révisée, suite SP-42)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-57, GAP-59,
GAP-60, GAP-62), `docs/revue/2026-09-04-backlog.md` (REV-151, REV-153,
REV-154, REV-156 — mêmes trouvailles), `CLAUDE.md` §« Pièges récurrents »
(n°1, n°3, n°5, n°10, n°11, n°12).

**Portée de ce document** : fermer 4 gaps « Sérieux » de la revue SP-42 sur
le module de fédération (STAC natif, export DCAT-AP, moissonnage — livré
SP-12) et sur trois surfaces internes voisines exposées au même défaut
d'absence de pagination (registre de collections, historiques
pipelines/rapports/alertes). Indépendant de SP-43 et de tout autre chantier
en cours — aucune nouvelle fonctionnalité, uniquement robustesse (pagination,
egress, cohérence des liens, dégradation propre) de surfaces déjà livrées.

---

## 0. État réel vérifié en session (piège CLAUDE.md n°3/n°12 : ne pas se fier au texte des GAP sans relire le code)

Les quatre GAP ont été vérifiés par lecture directe du code sur `dev`, pas
seulement sur le texte de `analyse-gaps.md`. Résumé des écarts trouvés entre
le texte du GAP et le code réel :

- **GAP-57** : le texte est exact. `core/app/collections/routes.py::list_collections`
  (`GET /collections`, ligne 316), `core/app/stac/routes.py::list_collections`
  (`GET /stac/collections`, ligne 79), `core/app/dcat/routes.py::get_catalog`
  (`GET /dcat/catalog`, ligne 90) n'acceptent aucun `limit`/`offset` et
  renvoient la totalité des collections visibles. `list_runs`
  (`app/pipelines/repository.py:39`, `app/reports/repository.py:55`) et
  `list_evaluations` (`app/alerts/repository.py:113`) n'ont ni `LIMIT` ni
  paramètre de pagination — confirmé par lecture directe des trois fonctions
  et de leurs routes (`app/pipelines/routes.py:83`,
  `app/reports/routes.py:51`, `app/alerts/routes.py:68`).
- **GAP-59** : confirmé, et **plus large que ce que suggère le texte du
  GAP** une fois vérifié : « un connecteur bufferise » est en réalité un
  patron **partagé par les 8 connecteurs** (`stac.py`, `arcgis.py`, `ckan.py`,
  `csw.py`, `ogc_records.py`, `wfs.py`, `wms.py`, `wmts.py`) — chacun appelle
  `client.get(url)` directement (pas `guarded_get`), sans aucune limite de
  taille de réponse. Et le second défaut (« document racine illisible rapporté
  comme réussi ») est également présent **identiquement dans les 8
  connecteurs** : chacun capture `(httpx.HTTPError, ValueError)` sur son tout
  premier appel HTTP et retourne `[]` (ou équivalent) au lieu de laisser
  l'exception remonter — `app/harvest/service.py::harvest_source` (ligne
  66-74) ne voit donc jamais d'exception à ce point et écrit
  `source.last_status = "ok"` (ligne 134) avec zéro enregistrement traité.
- **GAP-60** : confirmé précisément. `core/app/stac/routes.py::list_items`
  (ligne 190) et `get_item` (ligne 230) appellent
  `get_readable_collection(session, user, collection_id)` **sans**
  `can_manage_collections=...`, alors que `get_collection` (ligne 137-144,
  même fichier) et `app/dcat/routes.py::get_dataset` (ligne 128-135) le font
  déjà. Le patron correct existe déjà dans le même fichier — non appliqué à
  ces deux routes précises. Un test de régression exact existe déjà pour le
  cas voisin déjà corrigé :
  `core/tests/test_stac_routes.py::test_custom_role_with_collections_manage_reaches_collection_detail`
  (ligne 170) — sert de patron direct pour le nouveau test de cette tâche.
- **GAP-62** : confirmé. `core/app/collections/routes.py::get_collection`
  (ligne 394-437) enveloppe `introspect()` + `extent_provider()` dans un
  `try/except (TableNotFound, UnsupportedTable, DBAPIError)` qui dégrade
  `body["extent"]` à `None` en journalisant un avertissement plutôt que de
  laisser l'exception remonter (patron testé par
  `core/tests/test_ogc_discovery.py::test_extent_failure_degrades_to_none` et
  son test miroir `test_extent_code_bug_is_not_swallowed`, qui vérifie que ce
  n'est *pas* un `except Exception` large). `app/stac/routes.py::list_collections`
  (ligne 79-124) et `app/dcat/routes.py::get_catalog`/`_dataset_doc` (ligne
  63-115) n'ont **aucun** `try/except` autour de l'appel équivalent
  (`introspect` + `bbox_provider`, dans une boucle sur toutes les collections
  visibles) : une seule collection dont la table backing est absente
  (`TableNotFound`), mutée (`UnsupportedTable`) ou dont le scan géométrique
  échoue en base (`DBAPIError`, via `app/stac/extent.py::estimated_bbox_4326`
  qui exécute un `ST_Extent` réel sous RLS, pas une lecture de statistiques)
  fait remonter l'exception non attrapée jusqu'à FastAPI → 500 sur
  **l'ensemble** du catalogue, pas seulement la collection en cause.

### 0.1 Différence de signature entre les deux `bbox_provider`

`app/collections/routes.py::get_extent_provider` produit une fonction de
signature `(session, info, tenant_id)` (RLS appliqué à l'intérieur du
provider lui-même). `app/stac/routes.py::get_bbox_provider` et
`app/dcat/routes.py::get_bbox_provider` produisent tous deux
`estimated_bbox_4326(session, info)` (2 arguments — RLS appliqué par
l'appelant via `with rls(session, col.tenant_id):`, à l'extérieur de l'appel).
**Ne pas copier le test de dégradation de `test_ogc_discovery.py` avec la
mauvaise arité** — les nouveaux tests STAC/DCAT overrident
`stac_routes.get_bbox_provider`/`dcat_routes.get_bbox_provider` avec une
fonction à 2 paramètres, pas 3.

### 0.2 Ordre déjà déterministe des deux listes concernées par la pagination Python-side

- `app/stac/routes.py::_visible_collections` / `app/dcat/routes.py::_visible_collections`
  trient déjà `sorted(cols, key=lambda c: c.id)` avant de servir.
- `app/collections/repository.py::list_visible_collections` trie par
  `Collection.title` en l'absence de recherche (`q`), ou par le rang RRF
  hybride sinon (ligne 147 et 127-141) — dans les deux cas, un ordre
  reproductible entre deux appels consécutifs à paramètres identiques.

Ces deux propriétés permettent un découpage par tranche (slice) **après**
matérialisation Python de la liste complète, sans introduire de risque de
doublon/omission entre deux pages consécutives — à condition qu'aucune
écriture concurrente ne réordonne la liste entre deux requêtes (risque
déjà présent aujourd'hui pour toute pagination par offset, pas spécifique
à ce correctif).

---

## 1. GAP-60 — Liens STAC « items » cassés pour un rôle porteur d'`admin.collections.manage`

### 1.1 Défaut exact

Un utilisateur porteur du privilège `admin.collections.manage` (rôle sur
mesure, pas `is_admin`) qui vient de lire avec succès :

- `GET /stac/collections/{id}` (passe par `get_collection`, qui calcule
  correctement `can_manage_collections`) — la réponse contient
  `links: [{"rel": "items", "href": ".../stac/collections/{id}/items"}]`
  (implicitement, via le contrat STAC standard — la collection STAC ellemême
  n'émet pas ce lien explicitement dans ce serializer, mais tout client STAC
  standard construit cette URL, et `GET /dcat/datasets/{id}` l'émet
  explicitement dans `dcat:distribution` sous le titre « STAC item-search »,
  `app/dcat/serializers.py:149-153`) ;

… obtient un `404 {"detail": "collection not found"}` en suivant ce lien vers
`GET /stac/collections/{id}/items`, alors que la même collection privée
vient d'être lue avec succès une ligne plus haut. Le rôle voit la collection
« exister » puis « disparaître » selon l'endpoint appelé — incohérence pure
d'implémentation (le patron correct existe déjà à trois lignes de distance
dans le même fichier), pas une question d'autorisation voulue.

### 1.2 Correctif

Dans `core/app/stac/routes.py`, `list_items` (ligne 177-216) et `get_item`
(ligne 219-241) : remplacer

```python
col = get_readable_collection(session, user, collection_id)
```

par le même calcul que `get_collection` (ligne 137-144) :

```python
col = get_readable_collection(
    session,
    user,
    collection_id,
    can_manage_collections=bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    ),
)
```

Aucune autre route STAC/DCAT n'est concernée : `get_collection` et
`get_dataset` (DCAT) le font déjà correctement — c'est le seul angle mort.
`POST /stac/search`/`GET /stac/search` passent par `_visible_collections`
(déjà correct, `can_see_all` calculé de façon équivalente) donc ne sont pas
concernés par ce défaut précis (ils ne filtrent jamais par
`get_readable_collection`).

---

## 2. GAP-62 — Une collection cassée fait échouer tout le catalogue STAC/DCAT

### 2.1 Correctif STAC (`app/stac/routes.py::list_collections`)

Envelopper l'appel `introspect` + `bbox_provider` (boucle ligne 88-113) du
même `try/except` que `app/collections/routes.py::get_collection`
(ligne 428-436), par collection, en continuant la boucle pour les autres :

```python
from sqlalchemy.exc import DBAPIError
from app.collections.introspection import TableNotFound, UnsupportedTable
import logging

logger = logging.getLogger(__name__)

...
for col in _visible_collections(session, user):
    try:
        info = introspect(session, col.table_name)
        with rls(session, col.tenant_id):
            bbox = bbox_provider(session, info)
    except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
        logger.warning("stac catalog: extent lookup failed for collection %s: %s", col.id, exc)
        bbox = None
    docs.append(serializers.collection(..., bbox=bbox, ...))
```

Le serializer `stac.serializers.collection` doit déjà accepter `bbox=None`
sans lever (vérifier — `get_collection`, ligne 148-162, lui passe déjà
potentiellement un `bbox` calculé, jamais `None` explicitement testé côté
STAC list ; vérifier le corps de `serializers.collection` avant de coder,
ne pas supposer qu'il gère `None` de la même façon que
`app/collections/routes.py::_collection_json` qui, lui, construit
`body["extent"]` conditionnellement en dehors du serializer).

### 2.2 Correctif DCAT (`app/dcat/routes.py::_dataset_doc`, appelé par `get_catalog`)

Même enveloppe, à l'intérieur de `_dataset_doc` (ligne 63-87) puisque
`get_catalog` (ligne 90-115) l'appelle une fois par collection dans une
liste en compréhension — la dégradation doit se faire **au niveau de
l'appel**, pas en modifiant la signature de `_dataset_doc` pour renvoyer un
optionnel (plus simple : capturer l'exception dans `get_catalog` autour de
l'appel à `_dataset_doc`, ou passer un `bbox` déjà résolu en amont —
choisir l'option qui déplace le moins de code ; recommandé : sortir le
calcul de `bbox` de `_dataset_doc` vers l'appelant, comme le fait déjà STAC,
pour appliquer le même patron aux deux endpoints sans dupliquer la logique
de dégradation dans deux fonctions différentes). `GET /dcat/datasets/{id}`
(`get_dataset`, ligne 118-148) reste hors périmètre de ce point précis — il
sert déjà une 404 propre en amont via `get_readable_collection` pour une
collection absente, et une collection *présente* mais dont la table est
cassée y est un cas différent (actuellement non couvert par un test, à
vérifier s'il faut l'aligner aussi — cf. §6 risques : décision à prendre en
tâche, la question n'est pas résolue par cette recherche seule car
`get_dataset` n'est pas listé explicitement dans GAP-62, qui ne cite que
« catalogues » au pluriel, donc les endpoints de liste, pas le détail par
id).

### 2.3 Tests

Reproduire exactement le patron de `core/tests/test_ogc_discovery.py`
(lignes 141-166) : un test `..._degrades_to_none` (le catalogue reste 200,
la collection cassée apparaît avec un bbox de repli ou absent selon le
serializer, les autres collections restent intactes) et un test
`..._code_bug_is_not_swallowed` (un `TypeError` du provider remonte bien,
`pytest.raises`, pour vérifier que le tuple d'exceptions capturé reste
**étroit** et ne masque pas un bug de code — piège CLAUDE.md n°10 déjà
matérialisé une fois dans ce dépôt pour ce précis mécanisme).

---

## 3. GAP-57 — Absence de pagination sur 5 surfaces

### 3.1 Deux familles de correctif, pas une seule

Les 5 surfaces ne partagent pas le même profil de risque ni le même point
d'application optimal du correctif :

**Famille A — listes de collections (`GET /collections`,
`GET /stac/collections`, `GET /dcat/catalog`)** : le nombre de collections
enregistrées est borné par une action administrative (`POST /collections`),
pas par un tiers non authentifié — la liste elle-même n'est jamais la
ressource qui explose. Le coût réel et non borné est le **traitement par
collection** qui suit (owners + permissions batchées pour `/collections` ;
introspection + `ST_Extent` réel par collection, potentiellement coûteux sur
une grosse table, pour STAC/DCAT). **Correctif retenu : découper (slice)
la liste déjà matérialisée en Python *avant* ce traitement coûteux**, pas
repousser `LIMIT`/`OFFSET` dans `list_visible_collections` — cette fonction
est partagée par de nombreux appelants (recherche sémantique `q`, MCP,
sharing) dont la modification de signature élargirait inutilement le risque
de régression pour un gain marginal (la requête de visibilité elle-même
n'est pas le goulot). Reprend le patron d'en-tête pagination de
`GET /collections/{id}/items` (`limit`/`offset` en `Query`, plafond
`MAX_LIMIT`) mais applique le slicing après coup plutôt qu'en SQL.

**Famille B — historiques (`GET /pipelines/{id}/runs`,
`GET /reports/{id}/runs`, `GET /alerts/{id}/evaluations`)** : chaque ligne
est produite par un cron toutes les 5 minutes, sans fin de vie — ces tables
grossissent réellement sans borne sur la durée de vie d'un pipeline/d'une
alerte/d'un rapport. **Correctif retenu : `LIMIT`/`OFFSET` poussés dans la
requête SQL** (`list_runs`/`list_evaluations`), pas un slicing Python après
un `SELECT` sans limite — ici le slicing après coup ne protégerait rien
(la ligne coûteuse — charger toute la table en mémoire — resterait exécutée
avant le découpage).

### 3.2 `GET /collections` (`app/collections/routes.py::list_collections`)

Ajouter `limit: int = Query(100, ge=1)` et `offset: int = Query(0, ge=0)`
(mêmes bornes que `GET /items`, `MAX_LIMIT = 1000` nouvelle constante locale
au module, absente aujourd'hui de ce fichier — vérifié par grep, seul
`app/features/routes.py` et `app/stac/routes.py` en ont une). Trancher
`cols` **avant** le calcul des `owners`/`permissions_by_id` (actuellement
calculés pour la totalité) :

```python
total = len(cols)
cols_page = cols[offset : offset + limit]
owner_ids = {c.owner_id for c in cols_page}
...
permissions_by_id = repo.collection_permissions_by_id(..., collections=cols_page)
return {
    "collections": [...for c in cols_page],
    "numberMatched": total,
    "numberReturned": len(cols_page),
}
```

Pas de champ `links` ici — ce n'est pas une surface OGC/STAC, et aucun
consommateur (shell `collectionsAdmin.ts`) n'en a besoin aujourd'hui ;
`numberMatched`/`numberReturned` suffisent pour qu'un futur client shell
sache qu'il existe plus de résultats, en réutilisant le vocabulaire déjà
établi par `GET /items` plutôt qu'en inventant une convention.

**Risque explicite (à trancher en tâche, cf. §6)** : le shell
(`shell/src/api/domains/collectionsAdmin.ts:30`) appelle aujourd'hui
`GET /collections${qs}` sans `limit` et lit uniquement `data.collections` —
avec le défaut `limit=100`, un tenant possédant plus de 100 collections
verrait sa liste d'administration silencieusement tronquée à 100 sans
qu'aucune pagination UI n'existe pour voir la suite. C'est un changement de
comportement observable pour ce cas précis, pas seulement un
durcissement invisible. Aucune tâche de ce plan ne touche le shell
(périmètre strictement core) — documenté explicitement comme risque
assumé, pas un oubli.

### 3.3 `GET /stac/collections` (`app/stac/routes.py::list_collections`)

Même bornes (`limit`/`offset`, réutilise le `MAX_LIMIT`/`DEFAULT_LIMIT`
déjà déclarés en tête de fichier, ligne 28-29). Trancher **avant** la boucle
d'introspection/bbox (elle-même retouchée par la Tâche GAP-62) :

```python
cols = _visible_collections(session, user)
total = len(cols)
cols_page = cols[offset : offset + limit]
docs = [... for col in cols_page]  # boucle existante, dégradation §2 incluse
return {
    "collections": docs,
    "links": [
        {"rel": "self", ...},
        {"rel": "root", ...},
        *([{"rel": "next", "href": f"{base}/stac/collections?limit={limit}&offset={offset+limit}"}]
          if offset + len(cols_page) < total else []),
    ],
}
```

Pas de `numberMatched` ici (surface STAC/OGC API Common — la convention
suivie par ce module ailleurs, cf. `serializers.item_collection`, se limite
à `links` pour la pagination des items ; rester cohérent avec le
vocabulaire spec plutôt qu'en ajouter un champ hors-spec sur l'endpoint
`/collections`).

### 3.4 `GET /dcat/catalog` (`app/dcat/routes.py::get_catalog`)

Même bornes (nouvelles constantes locales, ce fichier n'en a aucune
aujourd'hui). Trancher la liste de collections visibles avant la boucle de
construction des `dataset()` (elle-même coûteuse par la même
`bbox_provider`). Ajouter un champ `"links"` non normatif — DCAT-AP ne fixe
pas de vocabulaire de pagination standard pour un `dcat:Catalog` unique
(Hydra `PartialCollectionView` existe dans l'écosystème DCAT mais serait
disproportionné à introduire ici pour un besoin v0) : réutiliser par
pragmatisme la même forme `{"rel": "next", "href": ...}` que STAC, en dehors
du bloc JSON-LD sémantique (`@context`/`dct:*`/`dcat:*`), documentée en
commentaire comme extension non-RDF de ce dépôt.

### 3.5 Historiques (`GET /pipelines/{id}/runs`, `GET /reports/{id}/runs`, `GET /alerts/{id}/evaluations`)

`limit`/`offset` en SQL, mêmes bornes (`DEFAULT_LIMIT=100`, `MAX_LIMIT=1000`,
constantes à ajouter à chacun des trois fichiers routes — `pipelines/routes.py`
importe déjà `Query`, `reports/routes.py` et `alerts/routes.py` ne
l'importent pas encore, à ajouter). Le `response_model` reste un `list[...]`
brut (`RunStatus`/`ReportRunStatus`/`EvaluationStatus`) — **pas de
changement de forme de réponse**, uniquement une troncature contrôlée par
défaut au lieu d'un chargement complet :

```python
# app/pipelines/repository.py::list_runs
def list_runs(
    session, *, tenant_id, pipeline_item_id, limit: int = 100, offset: int = 0
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
`app/alerts/repository.py::list_evaluations`. Les trois routes
(`list_pipeline_runs`, `get_report_runs_route`, `get_alert_evaluations`)
gagnent `limit: int = Query(100, ge=1)`/`offset: int = Query(0, ge=0)` et
les transmettent tels quels, plafonnés à `MAX_LIMIT` avant l'appel repo
(`limit = min(limit, MAX_LIMIT)`). Aucun consommateur shell
(`pipelines.ts:86`, `reports.ts:65`, `alerts.ts:75`) ne passe aujourd'hui de
`limit`/`offset` — ils recevront par défaut les 100 lignes les plus
récentes au lieu de la totalité, ce qui est le comportement voulu par le
GAP (troncature contrôlée, la plus récente en premier — déjà l'ordre
`created_at.desc()` existant, donc les 100 lignes retenues par défaut sont
déjà celles qu'un panneau d'historique afficherait en premier) : risque de
régression fonctionnelle nettement plus faible qu'en Famille A, car aucune
UI existante n'affiche « toutes » les lignes simultanément — un panneau
d'historique paginé/scrollable montre déjà les plus récentes en premier.

---

## 4. GAP-59 — Egress du moissonnage sans garde-fou de volumétrie

### 4.1 Absence de limite de taille de réponse

Confirmé §0 : les 8 connecteurs appellent `client.get(url, ...)` (client
construit via `build_guarded_client()`, `app/harvest/egress.py:82-83`), qui
lit systématiquement le corps entier en mémoire avant de renvoyer la
réponse — aucune limite de taille, `Content-Length` ou non (en-tête
absent/mensonger n'est pas une garantie, et un flux `chunked` n'a pas de
`Content-Length` du tout). **Point d'application retenu : le transport
partagé** (`_GuardedTransport.handle_request`, `app/harvest/egress.py:73-79`)
— c'est le seul chokepoint traversé par les 8 connecteurs **et** par
`guarded_get` (utilisé en mode copie, `app/harvest/service.py:19`), donc un
correctif unique protège toute la surface sans toucher aux 8 fichiers de
connecteurs individuellement.

```python
_MAX_RESPONSE_BYTES_ENV = "CORE_HARVEST_MAX_RESPONSE_BYTES"
_DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 Mio


class ResponseTooLargeError(Exception):
    """Réponse distante dépassant CORE_HARVEST_MAX_RESPONSE_BYTES."""


def _max_response_bytes() -> int:
    raw = os.environ.get(_MAX_RESPONSE_BYTES_ENV, "")
    return int(raw) if raw.strip() else _DEFAULT_MAX_RESPONSE_BYTES


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        response = self._inner.handle_request(request)
        cap = _max_response_bytes()
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.stream:
                total += len(chunk)
                if total > cap:
                    raise ResponseTooLargeError(
                        f"réponse distante > {cap} octets pour {request.url}"
                    )
                chunks.append(chunk)
        finally:
            response.close()
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=b"".join(chunks),
            request=request,
        )
```

**À vérifier explicitement en tâche avant d'écrire l'implémentation finale
(piège CLAUDE.md n°3)** : la forme exacte de `httpx.BaseTransport.handle_request`
et de l'itération sur `response.stream` (attribut public `SyncByteStream`
côté transport bas niveau, distinct de `response.iter_bytes()` côté client
haut niveau) contre la version d'httpx réellement verrouillée
(`core/uv.lock`) — ne pas supposer l'API stable entre versions mineures.
`ResponseTooLargeError` doit se comporter, côté appelants, comme
`EgressBlockedError` aujourd'hui : **non catturée par les connecteurs**
(remonte jusqu'à `harvest_source`, qui la traite déjà comme n'importe quelle
autre exception de `connector.fetch()`, ligne 66-74) — cohérent avec le
commentaire déjà présent dans `connectors/base.py:33-37` sur
`EgressBlockedError`.

### 4.2 Document racine illisible rapporté comme moissonnage réussi

Confirmé §0 : identique dans les 8 connecteurs. Chacun capture
`(httpx.HTTPError, ValueError)` (ou juste `httpx.HTTPError` pour
wfs/wms/wmts) sur le tout premier appel réseau du `fetch()`, journalise un
avertissement, et retourne une liste vide — indistinguable, côté
`harvest_source`, d'un catalogue distant réellement vide et valide.

**Décision de conception** : introduire une exception dédiée
`HarvestFetchError` dans `app/harvest/connectors/base.py` (à côté de
`HarvestedRecord`/`HarvestConnector`), levée **uniquement** quand le
**document racine** (le tout premier fetch de l'URL passée à `fetch()`, pas
un lien enfant découvert en cours de parcours) échoue — la tolérance
existante pour les documents **enfants** malformés/inaccessibles (déjà
documentée et voulue : « un catalogue distant malformé/cyclique/hostile ne
doit jamais faire tomber tout un moissonnage », `connectors/stac.py:3-4`)
n'est **pas** remise en cause : seul le premier accès change de
comportement. `harvest_source` (`app/harvest/service.py:66-74`) n'a besoin
d'aucune modification — il capture déjà tout `Exception` sorti de
`connector.fetch()` et écrit `source.last_status = "error"` ;
`HarvestFetchError` s'y engouffre sans changement de code, seulement un
changement de comportement (l'exception remonte au lieu d'être avalée).

Par connecteur (patron identique, un seul point de changement par fichier) :

- **`stac.py`** (`_walk`, ligne 49-59) : le premier appel (`depth == 0`) lève
  `HarvestFetchError` au lieu de `return` sur `(httpx.HTTPError, ValueError)` ;
  les appels à `depth > 0` (liens `child` découverts en cours de parcours)
  gardent le `return` tolérant actuel, inchangé.
- **`arcgis.py`** (`_fetch`, premier `_get_json(client, f"{service_url}?f=json")`,
  ligne 55) : lève si ce premier appel échoue ; les appels suivants (par
  couche, dans la boucle `for entry in layers[:_MAX_LAYERS]`) restent
  tolérants s'ils le sont déjà (à vérifier au cas par cas en tâche — ne pas
  supposer une structure identique à `stac.py`).
- **`ckan.py`** (`_fetch`, premier appel de la boucle `while True` à
  `pages == 1`) : lève seulement sur l'échec de la **première** page ; un
  échec sur une page suivante (pagination CKAN) peut rester tolérant
  (tronquer la liste, comme déjà fait pour `_MAX_CKAN_PAGES`) — à confirmer
  contre le corps réel de la fonction en tâche.
- **`csw.py`**, **`wfs.py`**, **`wms.py`**, **`wmts.py`** : un seul appel
  racine chacun (`_first_page`/`client.get(caps_url, ...)`) — cas le plus
  simple, le `return []` actuel sur l'unique point d'échec devient
  `raise HarvestFetchError(...)`.
- **`ogc_records.py`** (`_get_json`, appelé par `_list_collections` en
  premier) : même distinction racine/enfant qu'`arcgis.py` — à vérifier
  contre le corps réel de `_list_collections`/`_collect_collection` avant de
  coder (ne pas deviner laquelle des deux fonctions porte l'appel racine).

**Message d'erreur** : inclure l'URL et la cause d'origine
(`str(exc)`/`exc.__class__.__name__`) — `source.last_error` est tronqué à
500 caractères par `harvest_source` (ligne 72), donc pas de contrainte
particulière de longueur côté connecteur.

---

## 5. Ordre de traitement proposé, du moins au plus risqué

1. **GAP-60** (Tâche 1) — 2 lignes, isolé, patron déjà éprouvé 3 lignes plus
   haut dans le même fichier, test de régression quasi identique à copier.
2. **GAP-62 STAC** (Tâche 2) puis **GAP-62 DCAT** (Tâche 3) — patron déjà
   éprouvé et testé ailleurs dans le dépôt (`test_ogc_discovery.py`), risque
   bas, deux fichiers distincts donc deux tâches pour un diff propre par
   revue.
3. **GAP-57 Famille A** (Tâches 4-6, une par surface : `/collections`,
   `/stac/collections`, `/dcat/catalog`) — surface plus large, change une
   forme de réponse JSON (nouveaux champs), donc régénération OpenAPI/TS
   requise et risque de troncature silencieuse du shell (`/collections`,
   §3.2) à documenter, pas à corriger dans ce plan.
4. **GAP-57 Famille B** (Tâche 7, les trois historiques ensemble — patron
   strictement identique répété 3 fois, comme le précédent direct du Task 3
   de SP-49 pour les balayages cron) — risque plus bas que la Famille A
   (pas de changement de forme de réponse, juste un plafond par défaut).
5. **GAP-59** (Tâches 8-9) — le plus invasif : Tâche 8 (plafond de taille au
   niveau du transport partagé, un seul fichier mais dépendance à l'API
   interne d'httpx à vérifier) puis Tâche 9 (signalement d'échec racine,
   8 fichiers connecteurs à modifier un par un avec vérification
   individuelle de leur structure).

## 6. Hors périmètre explicite

- **Pagination shell** (colonne « charger plus »/curseur dans
  `collectionsAdmin.ts`, `PipelineRunPanel`, `AlertRuleEditor`,
  `ReportSchedule` UI équivalente) — ce document est strictement core ; le
  risque de troncature silencieuse de l'admin des collections (§3.2) est
  documenté, pas corrigé ici.
- **`GET /dcat/datasets/{id}`** (détail par id) pour la dégradation GAP-62 —
  le GAP cite « catalogues » (les listes), pas le détail par id ; à trancher
  en Tâche 3 si l'alignement est jugé trivial à ajouter au passage (coût
  marginal), sinon noté comme suivi séparé.
- **Pagination de `GET /harvest/layers`/`/feature-layers`** — déjà traité
  par un plafond dur (sans curseur) dans un chantier antérieur
  (SP-49 §2.2) ; non repris ici, ces deux routes ne font pas partie des 5
  surfaces assignées à GAP-57.
- **Pin IP / protection DNS-rebinding TOCTOU** sur l'egress — résiduel déjà
  documenté et assumé dans `app/harvest/egress.py:8-11`, sans rapport avec
  GAP-59 tel qu'assigné (volumétrie et faux positif de succès, pas
  résolution DNS).
- **Migration vers l'API heartbeat pure de procrastinate, montée de version
  future d'httpx** — aucun impact direct connu sur ce périmètre, mais toute
  dépendance à une API interne d'httpx (§4.1) devra être revérifiée si
  `core/uv.lock` change de version majeure d'httpx dans le futur.

## 7. Risques

- **§3.2 (`GET /collections`)** : troncature silencieuse de l'admin des
  collections pour un tenant à >100 collections — assumé, documenté,
  non corrigé côté shell dans ce plan (cf. §6).
- **§3.3/3.4 (STAC/DCAT collections)** : un moissonneur tiers qui ne
  supporte pas la pagination `links.next` verrait son catalogue tronqué à
  100 entrées sans avertissement applicatif — comportement conforme aux
  spécifications STAC/DCAT-AP (qui prévoient justement ce mécanisme de
  liens), mais à surveiller si un connecteur de moissonnage *interne* à ce
  dépôt (`app/harvest/connectors/stac.py`) consomme un jour sa propre API —
  vérifié : `harvest_source`/`StacConnector` moissonnent des catalogues
  STAC **externes**, jamais l'API STAC de ce cœur lui-même en boucle, donc
  aucun risque de régression croisée identifié.
- **§4.1 (plafond de taille)** : un seuil trop bas casserait un moissonnage
  légitime contre un vrai service STAC/CSW/CKAN volumineux (nombreuses
  collections dans un seul document racine) — 10 Mio est un ordre de
  grandeur pour un document JSON/XML de métadonnées (jamais des données
  binaires ou des tuiles), à confirmer par un test contre un cas réel
  proche de la limite si possible, sinon documenté comme valeur par défaut
  raisonnable mais arbitraire, paramétrable par variable d'environnement.
- **§4.2 (signalement d'échec racine)** : le point de bascule
  racine/enfant diffère par connecteur (§4.2, `arcgis.py`/`ckan.py`/
  `ogc_records.py` ont une structure de pagination interne qui n'est pas
  aussi simple qu'un unique appel comme `csw.py`/`wfs.py`/`wms.py`/`wmts.py`)
  — un mauvais choix romprait la tolérance voulue pour les échecs
  profonds (répertoriée comme fonctionnalité, pas comme bug) ; chaque
  connecteur doit être vérifié individuellement contre son propre code
  avant de choisir où insérter le `raise`, pas par analogie automatique
  avec `stac.py`.
- **Falsification des filets de test (piège CLAUDE.md n°10)** : chaque
  correctif de ce document change un comportement observable seulement dans
  un cas précis (limite dépassée, racine injoignable, rôle porteur d'un
  privilège précis, collection cassée) — chaque test ajouté doit être
  vérifié en échouant AVANT le correctif, pas seulement en passant après.
