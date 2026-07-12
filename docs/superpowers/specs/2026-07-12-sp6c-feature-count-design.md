# SP-6c — Nombre d'entités par collection : design

**Date** : 2026-07-12
**Statut** : validé (brainstorm), prêt pour plan d'implémentation

## Contexte

SP-6 (feuille de route, `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
§SP-6) prévoit des « métadonnées extraites (emprise, nombre d'entités,
champs) stockées sur la collection — champs alignés STAC selon A7 ». SP-6a et
SP-6b ont livré les critères d'acceptation de SP-6 (M4, erreur lisible sans
job zombie) sans couvrir ce point précisément. Vérification du code actuel
(2026-07-12) :

- **Emprise (bbox)** : déjà servie, calculée à la volée sur chaque
  `GET /collections/{id}` (`extent_provider`, depuis SP-3b) — pas stockée,
  et c'est très bien ainsi (toujours à jour). **Hors périmètre de SP-6c.**
- **Champs** : déjà servis par `GET /collections/{id}/schema`
  (introspection live). **Hors périmètre de SP-6c.**
- **Nombre d'entités (feature_count)** : absent partout — ni stocké, ni
  calculé, ni exposé. **C'est l'unique périmètre de SP-6c.**

## Objectif

Stocker `feature_count` sur `Collection`, le tenir à jour à chaque écriture
OGC API Features (create/delete), l'exposer sur l'API (`GET /collections`,
`GET /collections/{id}`) et l'afficher dans le sélecteur de source de couche
du builder (`LayerPicker`), pour aider à juger la taille d'une source avant
de l'ajouter à une carte.

## Hors périmètre

- Emprise et schéma des champs (déjà servis, voir Contexte).
- Toute notion de catalogue STAC complet (A7 tranche explicitement contre
  ça pour SP-6).
- Affichage du compteur ailleurs que `LayerPicker` (pas de badge sur
  `ItemCard` — un item carte peut référencer 0..N collections via ses
  couches, pas de relation 1:1 exploitable côté catalogue).

## Architecture — Cœur

### Modèle

`core/app/collections/models.py` — `Collection.feature_count: int | None`,
colonne nullable (même style que `layer_name` en SP-6b), migration
`0011_collections_feature_count.py`.

### Initialisation

- **Ingestion** (`core/app/ingestion/importer.py`, `run_import`) :
  `feature_count=len(rows)` — gratuit, la liste est déjà entièrement
  matérialisée en mémoire avant l'insertion PostGIS.
- **Enregistrement admin** (`core/app/collections/routes.py`,
  `register_collection`) : un `SELECT count(*) FROM public.<table>` unique
  au moment de l'enregistrement (action rare, coût négligeable).
- **Backfill des collections existantes** : la migration `0011` recalcule
  `feature_count` pour chaque ligne déjà présente dans `collections`, via
  une boucle Python dans la migration (`UPDATE collections SET
  feature_count = (SELECT count(*) FROM public.<table>)` par collection,
  nom de table protégé par le même `quote_ident` que `app/collections/ddl.py`).
  Si une table backing a disparu entre-temps (cas limite), l'erreur est
  capturée et loggée pour cette collection seule (elle reste `NULL`), la
  migration continue pour les autres — jamais d'échec total de migration
  pour une table orpheline.

Après backfill, toute collection a un `feature_count` non-`NULL` en usage
normal ; les routes d'écriture ci-dessous n'ont donc pas besoin de gérer un
cas `NULL` particulier (elles fonctionnent aussi bien si un `NULL` résiduel
existe : `NULL + 1`/`NULL - 1` restent `NULL` en SQL, dégradation silencieuse
acceptable pour ce cas limite non bloquant).

### Maintien à jour

`core/app/features/routes.py` (OGC API Features Part 4, écritures) :

- `create_feature` (`POST /collections/{id}/items`) : après l'insertion
  réussie, `UPDATE collections SET feature_count = feature_count + 1 WHERE
  id = :id`, **dans la même transaction/session** que l'insertion — un
  `UPDATE` SQL atomique, jamais un cycle lire-l'attribut-ORM-puis-réécrire
  (qui perdrait des incréments sous écritures concurrentes sur la même
  collection).
- `remove_feature` (`DELETE /collections/{id}/items/{fid}`) : même patron,
  `- 1`, exécuté seulement après confirmation que la suppression a
  effectivement supprimé une ligne (`ok` vrai, cf. code existant).
- `put_feature` (`PUT .../items/{fid}`, remplacement) : aucun changement de
  compte — pas touché par SP-6c.

Le compteur est protégé par la même transaction que l'écriture qu'il
accompagne : si celle-ci échoue et provoque un rollback, l'`UPDATE` du
compteur est annulé avec elle — jamais de dérive silencieuse.

### API

Le JSON de sérialisation des collections (`_collection_json`, consommé par
`GET /collections` et `GET /collections/{id}`) gagne un champ
`featureCount: number | null`. Régénération OpenAPI (`core/openapi.json`) +
types shell (`shell/src/api/generated/core-schema.d.ts`), patron déjà établi
en SP-6b Task 4.

## Architecture — Shell

### Types

`shell/src/api/types.ts` — `LayerSource.featureCount?: number | null`,
pertinent seulement pour les sources `service: "core"` (les sources
`martin`, tuiles vectorielles pré-rendues, n'ont pas ce concept — le champ
reste absent pour elles).

### `itemClient.ts`

`fetchCoreCollections()` mappe `c.featureCount` de la réponse `/collections`
vers `LayerSource.featureCount`.

### `LayerPicker.tsx`

Badge texte discret (`N entités`) affiché à côté du `kind` existant,
uniquement quand `featureCount` est un nombre (pas de badge pour les sources
`martin`, pas de badge trompeur type « 0 entités » si la valeur est
`null`/absente).

## Tests

**Cœur** :
- `test_collections_repository.py` : `create_collection` accepte
  `feature_count`, défaut `None`.
- `test_ingestion_importer.py` : `run_import` fixe `feature_count ==
  len(rows)` (test PostGIS réel, comme les tests GPKG/Shapefile de SP-6b).
- `test_collections_routes.py` (ou équivalent) : `register_collection`
  fixe `feature_count` via `COUNT(*)` sur une table pré-existante.
- Migration : backfill vérifié sur une collection existante avant/après
  upgrade (test PostGIS réel).
- `test_features_routes.py`/`test_features_integration.py` : `create_feature`
  incrémente, `remove_feature` décrémente, `put_feature` ne change rien.
  L'atomicité est une propriété de la forme de la requête SQL
  (`UPDATE ... SET feature_count = feature_count + 1`, jamais un
  lire-l'attribut-ORM-puis-réécrire) — garantie par revue de code du plan
  d'implémentation, pas par un test de concurrence (pas de patron existant
  dans ce dépôt pour simuler des écritures concurrentes en test, et en
  ajouter un serait hors périmètre de SP-6c).

**Shell** :
- `itemClient.test.ts` (ou fichier équivalent existant) : `featureCount`
  correctement mappé depuis `/collections`.
- `LayerPicker.test.tsx` : badge affiché pour une source `core` avec un
  compte, absent pour une source `martin`.

Pas de nouvelle spec E2E dédiée prévue — à confirmer en écrivant le plan si
un scénario E2E existant (ex. `ingestion.spec.ts`) peut absorber une
assertion supplémentaire à coût quasi nul ; sinon, la couverture unitaire
ci-dessus suffit (le patron SP-6b n'a pas non plus ajouté d'E2E pour des
changements purement additifs sur l'API de lecture).

## Points validés en session (ne pas rediscuter)

- Le compteur est un **snapshot maintenu par delta atomique**, pas un
  `COUNT(*)` recalculé à la demande (contrairement à l'emprise, qui reste
  volontairement live).
- Le badge shell va dans **`LayerPicker`**, pas `ItemCard` (correction
  d'une proposition initiale erronée — `ItemCard` affiche des items, pas
  des collections, et la relation carte↔collections n'est pas 1:1).
- Backfill des collections existantes inclus dans la migration (pas de
  script séparé, pas de `NULL` permanent pour les collections
  pré-SP-6c).
