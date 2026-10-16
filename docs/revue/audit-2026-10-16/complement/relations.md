# Audit complémentaire : `core/app/relations/` (ARC-21)

Méthode : lecture du code, puis repro sur une base jetable `relaudit` créée dans le conteneur
postgis-test (supprimée ensuite), en réutilisant la fixture `env` de
`core/tests/test_relations_postgis.py`. Script : `relations-repro-test.py.txt`.
Aucun fichier source modifié. Les points suivants sont déjà couverts par les tests existants et
n'ont pas été retrouvés défaillants : masquage de colonne sensible sur la collection liée,
limite géographique de la collection liée (non-PK), 404 d'une collection liée illisible,
isolation de tenant (`get_relation` filtre sur `tenant_id`).

## R1 (Important) numberMatched fuit le nombre d'enregistrements cachés (M2M / clé PK)
`service.py:219-221` : sur la voie « clé = PK », `total = len(values)` compte les valeurs liées,
pas les lignes visibles sous RLS/limite géographique (le commentaire `ponytail` l'assume).
Repro (exécuté) : relation many_to_many parcelles/propriétaires via `rel_liens`, 3 propriétaires
liés (1 dans la limite SQUARE du groupe du lecteur, 2 dehors).
Résultat : `features=['in']`, `numberReturned=1`, `numberMatched=3`.
Le lecteur limité apprend le cardinal total, hors de sa zone, alors que les voies non-PK
utilisent `count_mode="exact"` sous RLS (`service.py:222-230`). Même défaut pour toute ligne masquée par RLS.
Correctif : compter les lignes effectivement lues, ou un `COUNT` sous `rls`.

## R2 (Important) 500 non géré quand la clé de relation devient sensible après la déclaration
`_check_key` (`service.py:95-96`) refuse une clé sensible uniquement à la création. Un
`PATCH /collections/rel_proprios {"sensitiveFields":["parcelle_id"]}` ultérieur (200) laisse la
relation intacte. Ensuite, pour un lecteur sans privilège sensible,
`GET /collections/rel_parcelles/items/{pid}/related/{rid}` (direction children) :
`_read_ctx` masque `parcelle_id` de `info` (`service.py:196-202`), puis `_matching` filtre
dessus (`service.py:225-227`). Résultat exécuté : `FilterError: unknown filter property
'parcelle_id'` non rattrapée (`repository.py:195`), donc HTTP 500. La direction parents répond
200 vide. Idem `check_write` (`service.py:356`) pour une clé parent sensible.
`GET /collections/rel_proprios/relations` continue d'exposer `childKey` (nom de la colonne
sensible) à ce lecteur (`routes.py:59-77`).
Correctif : à l'écriture de `sensitiveFields`, refuser (409) ou mettre en quarantaine les relations
qui utilisent la colonne ; à la lecture, traduire `FilterError` en 4xx/liste vide et omettre la relation.

## R3 (Important) La clé étrangère logique n'est vérifiée que sur 2 des chemins d'écriture
`check_write` n'est appelé que depuis `features/routes.py:919` (POST) et `:1034` (`_replace` :
PUT/PATCH/restore). Aucun appel dans :
- `public_submit/routes.py:360` (`approve_submission`, `insert_feature` direct) ;
- `ingestion/importer.py:528-614` (`run_append`, `insert_features`) ;
- `pipelines/collection_writer.py:470` et `:543` (`writer.collection` insert/upsert/update).
Une valeur `child_key` inexistante ou un 2e enfant 1-1 y passe sans 422/409 (jumelle de garde
oubliée, piège 14). Constaté par lecture de code et `grep` de `check_write`/`RelationHooks` : seuls
`features/routes.py` et `main.py:493` l'utilisent. Non exécuté (nécessite S3/worker).
Correctif : porter la vérification dans une couche partagée (repository/rang `insert_features`)
ou l'appeler dans ces trois chemins.

## R4 (Important) Modifier la clé du parent orpheline les enfants sans garde ; `restrict` ne couvre que la suppression
Repro exécuté : relation 1-N avec `parentKey="ref"`, enfant `parcelle_id=7`, parent `ref="7"`.
`PUT /items/{pid}` avec `ref="8"` : 204. `related` renvoie ensuite `numberMatched=0` ; le
parent est ensuite supprimable (204) malgré l'enfant, qui n'est plus lié à rien.
`check_write` ne contrôle que le côté enfant (`service.py:350`) ; rien n'agit quand la
valeur `parent_key` d'un parent change. L'ADR 0021 promet la politique `restrict` sur « supprimer » seulement ;
l'intégrité référentielle annoncée par « clé étrangère logique » est donc contournable par simple mise à jour.
Correctif : appliquer la logique de `before_delete` quand la valeur de `parent_key` change.

## R5 (Important) Suppression d'une collection parent : la relation disparaît en silence, enfants orphelins
Repro exécuté : `DELETE /v1/collections/rel_parcelles` (admin) : 204 alors que la relation
`proprietaires` a un enfant. La FK `ondelete=CASCADE` (`models.py`) supprime la ligne
`collection_relations`, la liste des relations devient `[]`. `unregister_collection`
(`collections/routes.py:969-1010`) ne contrôle que les configs référentes
(`find_referencing_config_kinds`), pas les relations, et la `on_delete="restrict"` n'est pas
honorée. Aucune entrée d'audit `relation.delete`. Correctif : refuser (409) ou auditer.

## R6 (Mineur) Oracle d'existence au rang propriétaire (1-1, restrict)
`check_write` 1-1 (`service.py:370-378`, `_owner_values`) et `before_delete`
(`service.py:409-424`) comptent sans RLS ni limite géographique. Repro exécuté : lecteur éditeur
limité à SQUARE, un enfant lié hors zone ; `POST` d'un 2e enfant : 409 « parent already linked »
(au lieu de 201). Il apprend l'existence d'un enregistrement invisible. Documenté comme
voulu (docstring du module) ; consigné car en tension avec la règle « un enfant illisible
n'existe pas pour lui » (`service.py:251-253`). Idem le 409 `restrict` qui nomme la relation.

## R7 (Mineur) Lecture M2M : liens non ordonnés, plafonnés à 1000 sans signal
`service.py:292-304` lit `rel_liens` avec `limit=MAX_LINKED`, sans ordre ni indicateur de
troncature ; au-delà de 1000 liens, `values` est tronqué arbitrairement, la pagination
(`values[offset:offset+limit]`, `:215`) n'est pas stable. `numberMatched` serait faux (cf. R1).

## R8 (Mineur) `restricting_relation` trop large pour le mode `delete`
`service.py:504-509` : bloque tout `writer.collection mode=delete` dès qu'une ligne enfant avec clé
non nulle existe n'importe où, sans relier aux lignes réellement supprimées. Sur-blocage (pas une fuite).
Le mode `update` qui change la clé du parent n'est pas gardé (cf. R4).

## Non retenu
`_read_ctx(…, rls)` : paramètre `rls` inutilisé (`service.py:196`), sans effet. Les limites
géographiques passent bien par `get_rls_scope` (`routes.py:93`) pour chaque `rls(...)` ; la limite
de la collection LIÉE est appliquée (test exécuté : `['in']` seul renvoyé).
