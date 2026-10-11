# `transform.httpCall` (HTTPCaller) — appel HTTP par ligne, avec retry/pagination/multipart

**Date** : 2026-09-21
**Demande** : « lance une spec pour httpCaller », précisée en « fonctionnalités avancées retry, pagination,
multi-part etc. ».
**Référence** : `docs/revue/matrice-couverture-fme.md` ligne « HTTPCaller » (`Workflow / Logic`, statut
`planned_duckdb`, priorité `courant`) — explicitement exclu du périmètre de Vague 1
(`2026-09-17-vague1-transformers-duckdb-design.md` §3.2) et Vague 2
(`2026-09-20-vague2-transformers-duckdb-design.md` §2.2), classé dans la famille « appel externe par ligne »
(avec `PythonCaller`/`SQLExecutor`/`MCPCaller`/`Geocoder`) : `reader.connector.rest` ne lit qu'**une fois en
tête de DAG**, sous une garde d'egress SSRF vérifiée au démarrage ; un appel HTTP **par ligne**, au milieu du
pipeline, pose une garde structurellement différente (un budget/débit par ligne plutôt qu'un contrôle
unique sur l'URL de lecture) — ce document construit ce mécanisme.

## Révision 2026-10-11 (vérifiée contre le code)

Écarts entre la spec du 2026-09-21 et le dépôt actuel (piège CLAUDE.md n°3/n°12) ; les sections ci-dessous
sont corrigées en conséquence, ce bloc en liste les raisons.

1. **Mécanisme d'exécution.** `transform.qgis` n'existe plus. Le patron actuel est le champ
   `OperationContract.execute` (signature `(conn, *, input_view, view_name, params)`, dispatch générique
   `elif contract.execute is not None` dans `runtime.py::_execute_transform_chain`, exemples dans
   `ops/execute.py`) : `compile=None` + `execute=`, **aucune** branche spéciale `node.op == …`. Nouveau champ
   `needs_runtime_context: bool = False` sur `OperationContract` : quand il est vrai, `runtime.py` passe
   `secret_resolver=` **et** `preview=` à `execute`. `_execute_transform_chain` reçoit pour cela les kwargs
   `secret_resolver` et `preview`, construits par `preview_pipeline`/`run_pipeline`
   (`PostgresSecretResolver(session, tenant_id, user)`, `None` si `session is None`).
   **Mode aperçu** : seules les lignes GET des 20 premières (`rn < 20`) sont appelées ; les autres ont
   `httpStatus="skipped"` et `httpError="non exécuté en aperçu"`. `httpStatus` ∈ {`success`, `error`, `skipped`}.
   **Avec un secret lié** : les redirections ne sont PAS suivies (3xx = `error`, « redirection non suivie ») et
   l'URL de chaque ligne doit être dans le `baseUrl` du secret (REV-294, message fixe « URL hors de la portée du
   secret »). Un refus d'egress affiche la chaîne fixe « egress refusé » (jamais l'URL). Une pagination réussie
   rapporte le statut HTTP réel de la dernière page. Le plafond de taille de réponse s'applique aux octets
   décodés. Variables d'env : `CORE_PIPELINES_HTTP_CALL_MAX_ROWS` (10000) et
   `CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES` (5242880) et `CORE_PIPELINES_HTTP_CALL_MAX_TOTAL_BYTES` (268435456).
2. **Comptes.** Catalogue exposé 58 → 59 op, registre brut `OPERATIONS` 60 → 61 (test
   `test_operations_registry_has_60_entries` → 61 ; le compte exposé est à vérifier par comptage, pas supposé).
3. **Retry.** Abandon de l'extension `urllib3.Retry` de `egress.py` : le backoff d'urllib3 2.x ne dort pas
   avant le 1ᵉʳ retry (≠ « doublé à chaque tentative ») et `raise_on_status` est piégeux. À la place, une
   **boucle de retry maison** dans `http_call_runtime.py` autour de chaque appel de ligne ; la garde d'egress
   s'exécute donc à **chaque tentative** (plus fort que la spec d'origine) et `egress.py` n'est **pas modifié**.
   Limite assumée : en mode paginé, un retry rejoue toute la pagination depuis la page 1.
4. **Trou de sécurité de la spec d'origine : portée du secret (REV-294).** Un secret REST est LIÉ à
   `payload.baseUrl`. Pour `httpCall`, l'URL de **chaque ligne** doit être dans cette portée (helper partagé
   `_url_within_scope(scope, url)`, extrait de `_assert_url_within_secret_scope` de `connector_runtime.py`) ;
   un secret sans `baseUrl` fait échouer le nœud ; une URL hors portée = ligne en erreur **sans appel réseau**
   (le jeton n'est jamais envoyé hors portée).
5. **Bornes ajoutées** (un appel réseau par ligne est un vecteur d'amplification sur un cœur multi-tenant) :
   plafond de lignes `CORE_PIPELINES_HTTP_CALL_MAX_ROWS` (défaut 10000, échec du nœud au-delà), plafond de
   taille de réponse (5 Mo, ligne en erreur), bornes de schéma `maxRetries ≤ 10`, `maxConcurrency ≤ 16`,
   `timeoutSeconds ≤ 120`, `requestsPerSecond > 0`.
6. **Matérialisation.** Ne PAS relire les colonnes d'entrée en Python (la géométrie ne round-trippe pas) :
   table temp `node_x__stage` = `row_number() OVER () - 1 AS __rn, *, (urlExpr) AS __http_url, …`, résultats
   des appels (DataFrame enregistré) joints sur `__rn` ; `SELECT * EXCLUDE (…)` conserve géométrie et ordre. Une
   collision entre un nom de colonne de sortie et une colonne d'entrée = `PipelineRuntimeError` à
   l'exécution (le validateur de schéma ne connaît que l'unicité des 4 noms de sortie entre eux).
7. **Pas de nouveau flag** : l'op vit déjà sous `CORE_ETL_ENABLED` (pipelines) — décision consignée.
   `RESTClient(base_url="")` accepte une URL absolue en `path` (vérifié : `join_url` retourne `path` si
   `base_url == ""`).
8. **Tests.** `pytest-httpserver` est déjà une dépendance de test ; patron de
   `tests/test_pipeline_connector_runtime.py` (autouse `_no_ssrf_guard` qui monkeypatch
   `pipelines_egress.assert_egress_allowed`, `_REAL_ASSERT_EGRESS_ALLOWED` pour un test de garde réelle) ;
   tests runtime en `session=None` + `_FakeS3` (cf. `test_run_pipeline_transform_triangulate_end_to_end`).

## 0. Correction trouvée en explorant le dépôt (piège CLAUDE.md n°3, vérifié pas supposé)

`CLAUDE.md` (§ Décisions figées) dit « Expressions no-code : CEL ». C'est vrai **côté shell** (`cel-js`,
client, pour `visibleWhen`/`AppConfig`) mais **faux côté serveur pipelines** : le docstring de
`core/app/pipelines/expr_validation.py` corrige explicitement une affirmation historique fausse (design
SP-15a §5.1, « un moteur CEL tournait déjà côté serveur ») — `transform.filter`/`transform.derive`/
`transform.aggregate.metrics` évaluent en réalité une **expression SQL DuckDB bornée**
(`validate_bounded_expr`, même AST que `app.analytics.sql_sandbox`), jamais CEL. Ce chantier suit donc ce
mécanisme réel, pas celui supposé au brainstorm initial (décision validée par Tanguy après correction).

## 1. Ce que ce chantier construit, en une phrase

Une nouvelle op **`transform.httpCall`** (transform, `execution_model="in_process"`, `compile=None`, `execute=`
comme `transform.triangulate`, dispatch générique de `runtime.py`, jamais dans `compiler.py` qui reste pur) : un appel HTTP
**par ligne** d'entrée, URL/headers/corps construits par expression SQL DuckDB bornée précalculée en une
passe vectorisée, avec auth par secret (mêmes 4 `kind` que `reader.connector.rest`), pagination multi-page
agrégée en une ligne, corps `multipart/form-data` avec fichier depuis une colonne, retry à backoff
exponentiel respectant `Retry-After`, concurrence bornée + débit configurable, et un échec par ligne capturé
(jamais un échec de run entier).

## 2. Périmètre

### 2.1 Dans ce chantier

- 1 op `transform.httpCall`, 1 nouvelle classe `TransformHttpCallParams` (`ops/schemas.py`), 1 nouvelle
  entrée `OPERATIONS` (`ops/contracts.py`), 1 nouveau module `core/app/pipelines/http_call_runtime.py`
  (même rôle que `connector_runtime.py` : matérialisation, jamais dans `compiler.py`), branchée via
  `OperationContract.execute` + `needs_secrets=True` (dispatch générique de
  `runtime.py::_execute_transform_chain`, plus aucune branche spéciale par `node.op`).
- Réutilisation stricte, zéro duplication de logique déjà auditée :
  - Auth : `_build_auth`/`_REST_SECRET_KINDS`/`SecretResolver` de `connector_runtime.py`, appelés tels
    quels (import direct, pas de copie).
  - Pagination : `dlt.sources.helpers.rest_client.RESTClient` + les 4 paginateurs déjà utilisés par
    `materialize_rest_connector` (`_build_paginator`, réutilisé tel quel).
  - Portée du secret : helper `_url_within_scope(scope, url)` extrait de `_assert_url_within_secret_scope`
    (`connector_runtime.py`) et réutilisé par les deux appelants (§4).
  - Egress SSRF : `assert_egress_allowed`/`build_guarded_session` de `egress.py`, **inchangés** (§5).
- Retry, concurrence bornée, débit, capture d'erreur par ligne, `multipartFields` : code nouveau (§4-§6),
  rien d'équivalent n'existe ailleurs dans le dépôt pour un appel réseau répété par ligne.

### 2.2 Hors périmètre, assumé explicitement (documenté, pas silencieux)

- Pas de résolution de fichier depuis une URL/S3 pour `multipartFields` : la valeur d'un champ fichier vient
  toujours d'une colonne déjà matérialisée dans la ligne (BLOB ou texte), jamais d'une 2e requête réseau
  déclenchée pendant la construction du corps.
- Pas de mode `onError` configurable (`fail|continue`) : toujours capturé par ligne (§6) — un run qui doit
  échouer dur sur la première erreur se construit en aval avec `transform.filter` sur `statusColumn` +
  `writer.*`, pas une 2e sémantique à maintenir dans cette op.
- Pas de cache de réponse entre runs (chaque exécution refait tous les appels).
- Pas de 2e arête DAG pour la pagination : `paginator`/`paginatorConfig`/`recordsPath` sont des paramètres
  scalaires de l'op, comme pour `reader.connector.rest` — aucune extension de `PipelineCanvas` nécessaire.
- `PythonCaller`/`SQLExecutor`/`MCPCaller`/`Geocoder` (même famille FME « appel externe par ligne ») restent
  hors périmètre — chantiers séparés, non entamés par celui-ci malgré l'infrastructure partagée qu'il pose
  (pool borné + limiteur de débit potentiellement réutilisables plus tard, mais pas génériques par design
  ici : à revalider avant réutilisation, ne pas supposer).

## 3. Contrat de paramètres — `TransformHttpCallParams`

Templating entièrement en **expressions SQL DuckDB bornées** (§0), précalculées en une seule passe
vectorisée **avant** la boucle Python d'appels réseau — jamais évaluées ligne par ligne côté Python. Le
runtime construit une table intermédiaire (révision 2026-10-11 : une table numérotée, pas une vue relue) :

```sql
CREATE TEMP TABLE node_xxx__stage AS
SELECT row_number() OVER () - 1 AS __rn,
       *,
       ({urlExpr}) AS __http_url,
       ({headersExpr or 'NULL'}) AS __http_headers,
       ({bodyExpr or 'NULL'}) AS __http_body
       -- + une colonne __mp_{i} par MultipartField (valueExpr)
FROM {input_view}
```

puis lit **seulement** `__rn` + les colonnes `__http_*`/`__mp_*` (`fetchall()` + `description`) pour obtenir, par
ligne, des valeurs Python déjà résolues — le code Python de la boucle réseau ne voit plus jamais de SQL, ni les
colonnes d'entrée (la géométrie ne round-trippe pas par Python). Les résultats (`__rn` + 4 colonnes de sortie)
sont enregistrés en DataFrame et joints à `node_xxx__stage` sur `__rn` (§4.6).

Champs :

| Champ | Type | Défaut | Rôle |
|---|---|---|---|
| `urlExpr` | `str` | requis | expression SQL → URL complète |
| `method` | `Literal["GET","POST","PUT","PATCH","DELETE"]` | `"GET"` | méthode HTTP |
| `headersExpr` | `str \| None` | `None` | expression SQL produisant un objet JSON (`json_object(...)`), parsé en dict de headers |
| `bodyType` | `Literal["none","json","form","raw","multipart"]` | `"none"` | forme du corps |
| `bodyExpr` | `str \| None` | `None` | pour `json`/`form`/`raw` |
| `multipartFields` | `list[MultipartField]` | `[]` | pour `bodyType="multipart"` (§6) |
| `secretName` | `str \| None` | `None` | mêmes 4 `kind` que `reader.connector.rest` |
| `paginator` | `Literal["none","page_number","offset","cursor"]` | `"none"` | mêmes paginateurs dlt que `reader.connector.rest` |
| `paginatorConfig` | `dict` | `{}` | mêmes clés que `ReaderConnectorRestParams.paginatorConfig` |
| `recordsPath` | `str \| None` | `None` | sélecteur dlt (`data_selector`), utilisé seulement si `paginator != "none"` |
| `maxConcurrency` | `int` (1–16) | `1` | appels simultanés max (`ThreadPoolExecutor` borné) |
| `requestsPerSecond` | `float \| None` (> 0) | `None` | débit max, `None` = pas de limite au-delà de `maxConcurrency` |
| `maxRetries` | `int` (0–10) | `3` | tentatives de rejeu max sur ConnectionError/Timeout/429/5xx |
| `initialBackoffSeconds` | `float` | `1.0` | délai initial, doublé à chaque tentative (`× 2**n`) ; `Retry-After` prioritaire, plafonné à 60 s |
| `timeoutSeconds` | `float` (≤ 120) | `30.0` | timeout par tentative |
| `responseColumn` | `str` | `"responseBody"` | colonne de sortie : corps de réponse |
| `statusCodeColumn` | `str` | `"httpStatusCode"` | colonne de sortie : code HTTP (dernier essai) |
| `statusColumn` | `str` | `"httpStatus"` | colonne de sortie : `"success"` \| `"error"` |
| `errorColumn` | `str` | `"httpError"` | colonne de sortie : message d'erreur, `NULL` si succès |

`MultipartField` : `{name: str, valueExpr: str, isFile: bool = False, filename: str | None = None,
contentType: str | None = None}`.

`OperationContract` : `kind="transform"`, `engine="python"`, `engine_license="Apache-2.0 (requests) +
Apache-2.0 (dlt, utilisé seulement si paginator≠none)"`, `is_copyleft=False`, `execution_model="in_process"`,
`compile=None`, `execute=_execute_http_call` (même mécanisme que `transform.triangulate`, jamais dans
`compiler.py`), `needs_secrets=True` (nouveau champ de `OperationContract`, défaut `False` : `runtime.py`
passe alors `secret_resolver=` à `execute`), `needs_columns=False` (les colonnes requises sont résolues par
la table `__stage`, pas par introspection `DESCRIBE`).

`model_validator` : `bodyExpr` requis si `bodyType` ∈ {`json`,`form`,`raw`} ; `multipartFields` non vide si
`bodyType="multipart"` ; les 4 noms de colonnes de sortie (`responseColumn`/`statusCodeColumn`/
`statusColumn`/`errorColumn`) doivent être distincts entre eux. Leur collision avec une colonne **d'entrée**
n'est détectable qu'à l'exécution (le schéma ne connaît pas les colonnes) : `PipelineRuntimeError` explicite
plutôt qu'un écrasement silencieux d'une colonne de données de l'utilisateur.

Docstring française courte sur `TransformHttpCallParams` (devient le tooltip de palette, même mécanisme que
les op existantes — vérifié en Vague 1/2, `PipelinePalette.tsx` reste générique-depuis-catalogue, aucun
changement front nécessaire).

## 4. Exécution — `http_call_runtime.py`

Nouvelle fonction `execute_http_call_transform(conn, *, input_view, view_name, params, secret_resolver)`,
référencée par `OperationContract.execute` (avec `needs_secrets=True`) et appelée par le dispatch générique
de `runtime.py::_execute_transform_chain` (`contract.execute(conn, input_view=…, view_name=…, params=…,
secret_resolver=…)`) — aucune branche `node.op == …`. Les expressions sont validées en amont par
`_validate_node_exprs` (étendu à `transform.httpCall`).

1. Valider les expressions bornées (`urlExpr`/`headersExpr`/`bodyExpr`/chaque `valueExpr` de
   `multipartFields`) avec `validate_bounded_expr`, comme le fait déjà `_validate_node_exprs` pour
   `transform.filter`/`derive` — réutilisation, pas une 2e implémentation de validation.
2. Compter les lignes d'entrée : au-delà de `CORE_PIPELINES_HTTP_CALL_MAX_ROWS` (défaut 10000) → échec du
   nœud (`PipelineRuntimeError`), avant toute requête. Vérifier l'absence de collision entre les 4 noms de
   colonnes de sortie et les colonnes d'entrée (`DESCRIBE`). Créer la table `__stage` (§3) et en lire
   `__rn` + `__http_*`/`__mp_*` en mémoire Python — **limite assumée** : pas de streaming/batching. Les
   entrées sont bornées par le plafond de lignes ; les réponses (jusqu'à `MAX_RESPONSE_BYTES` chacune) le sont
   par un budget cumulé par nœud `CORE_PIPELINES_HTTP_CALL_MAX_TOTAL_BYTES` (défaut 256 Mio) : au-delà, la
   ligne devient une erreur « budget de réponse dépassé » (corps non conservé, le nœud n'échoue pas). En aperçu :
   pas de retry et échéance globale `CORE_PIPELINES_PREVIEW_TIMEOUT_S` (lignes restantes ignorées).
3. Résoudre l'auth une fois (`_resolve_secret` + `_build_auth` de `connector_runtime.py`, réutilisés) — jamais
   par ligne, un seul secret par nœud. Si le secret n'a pas de `baseUrl` → `ConnectorRuntimeError` (échec du
   nœud, REV-294). Par ligne, l'URL doit satisfaire `_url_within_scope(payload.baseUrl, url)` (helper partagé
   extrait de `_assert_url_within_secret_scope`) ; sinon la ligne passe en `error` **sans appel réseau**.
4. Traiter les lignes via un `ThreadPoolExecutor(max_workers=maxConcurrency)` ; un limiteur à jetons partagé
   (implémentation minimale maison, aucun équivalent existant dans le dépôt pour un débit sortant) applique
   `requestsPerSecond` si renseigné.
5. Par ligne (fonction exécutée dans le pool) :
   - Si `paginator == "none"` : un appel direct via `build_guarded_session()` (inchangé), dans la boucle de
     retry maison (§5) — `requests.Session`, pas `httpx` (cohérence avec `egress.py`, qui garde `requests` —
     noté dans son propre docstring que copier le transport `httpx` de `app.harvest.egress` ne garderait
     rien en pratique ici non plus). Réponse lue en `stream=True` avec un plafond de 5 Mo (au-delà : ligne en
     erreur). `responseBody` = texte brut exact de la réponse, sans aucun parsing.
   - Si `paginator != "none"` : `RESTClient(base_url="", session=build_guarded_session(), …).paginate(url,
     method=, params=, json=)` (même client que `materialize_rest_connector` ; `base_url=""` accepte une URL
     absolue en `path`, vérifié), pages concaténées en une liste, `responseBody` =
     `json.dumps(all_records)` — **parsing JSON interne nécessaire** pour suivre le curseur/offset entre
     pages (§ pagination, décision assumée : pas de contradiction avec « responseBody brut », qui ne
     s'applique qu'au cas `paginator="none"`, le cas courant).
   - Succès : `httpStatusCode` = code de la dernière tentative, `httpStatus="success"`, `httpError=NULL`.
   - Échec définitif (après `maxRetries`) : `httpStatusCode` = code de la dernière tentative (ou `NULL` si
     timeout/erreur de connexion sans réponse), `httpStatus="error"`, `httpError` = message borné (jamais
     l'URL complète ni un secret — même discipline que `ConnectorRuntimeError` dans `connector_runtime.py`).
6. Écrire les résultats collectés (dans l'ordre d'entrée, pas l'ordre de complétion — un `ThreadPoolExecutor`
   avec `executor.map` préserve cet ordre nativement) en DataFrame `(__rn, <4 colonnes de sortie>)`
   enregistré sur la connexion, puis matérialiser :
   `CREATE TEMP TABLE {view_name} AS SELECT s.* EXCLUDE (__rn, __http_url, __http_headers, __http_body,
   __mp_*), r.* EXCLUDE (__rn) FROM node_xxx__stage s JOIN results r USING (__rn) ORDER BY s.__rn`.
   Les colonnes d'entrée (géométrie comprise) ne transitent jamais par Python.

## 5. Retry — boucle maison, `egress.py` inchangé

Révision 2026-10-11 : l'extension `urllib3.Retry` prévue à l'origine est abandonnée (backoff urllib3 2.x :
0 s avant le 1ᵉʳ retry, pas de « doublé à chaque tentative » ; `raise_on_status` piégeux ; retries invisibles
de la garde d'egress). `http_call_runtime.py` porte une boucle explicite autour de chaque appel de ligne
(appel direct, ou pagination complète) :

- tentatives = `1 + maxRetries` ; rejeu sur `requests.ConnectionError`/`Timeout`, statuts
  `{429, 500, 502, 503, 504}` (appel direct) ou `requests.HTTPError` portant l'un de ces statuts (mode paginé,
  dlt appelle `raise_for_status`) ; **toutes les méthodes** sont rejouées (HTTPCaller FME ne distingue pas les
  idempotentes, le contrat n'a pas d'a priori sur le sens métier de l'appel de l'auteur du pipeline) ;
- délai avant le rejeu n = `Retry-After` (secondes, plafonné à 60 s) s'il est présent, sinon
  `initialBackoffSeconds * 2**n` ;
- la garde d'egress (`assert_egress_allowed` dans `_GuardedHTTPAdapter.send()`) s'exécute à **chaque
  tentative**, puisque chaque tentative est un `session.request` complet (plus fort que la spec d'origine) ;
  `egress.py` n'est pas modifié ;
- limite assumée (`ponytail:`) : en mode paginé, un rejeu repart de la page 1.

## 6. Pagination et multipart — reformulation précise des choix validés

- **Pagination = agrégation multi-page en 1 ligne** (pas une explosion en plusieurs lignes) : cohérent avec
  la garantie de cardinalité 1:1 de la majorité du catalogue transform ; qui veut 1 ligne par page compose
  ensuite avec `transform.explodeList` sur le tableau JSON de `responseBody`.
- **Multipart = corps `multipart/form-data` avec fichier depuis une colonne** : `requests` accepte nativement
  `files={name: (filename, content, content_type)}` — chaque `MultipartField` avec `isFile=True` alimente ce
  dict, les autres deviennent le paramètre `data=` classique de `requests.request(...)`.

## 7. Tests (falsifiés avant clôture, piège CLAUDE.md n°10)

- Un test par branche `bodyType` (`none`/`json`/`form`/`raw`/`multipart`) contre un serveur HTTP de test
  local (`pytest-httpserver`, déjà dépendance de test — fixture `httpserver`). Patron de
  `tests/test_pipeline_connector_runtime.py` : autouse `_no_ssrf_guard` (monkeypatch
  `pipelines_egress.assert_egress_allowed`, le serveur écoute sur 127.0.0.1) ; tests runtime de bout en bout
  en `session=None` + `_FakeS3` (cf. `test_run_pipeline_transform_triangulate_end_to_end`).
- Test de retry : serveur de test renvoyant `503` puis `200`, assertion sur le nombre réel de tentatives et
  le délai observé (pas une assertion de durée seule — mesurer l'intervalle entre tentatives, piège CLAUDE.md
  n°7) ; un 2e test avec en-tête `Retry-After` explicite, assertion que le délai réel respecte cette valeur
  plutôt que le backoff calculé.
- Test pagination : serveur de test à 3 pages (`page_number`), assertion que `responseBody` contient bien la
  concaténation des 3 pages, pas seulement la première.
- Test d'erreur par ligne : un jeu de lignes où une URL pointe vers un hôte qui renvoie systématiquement
  `500` (au-delà de `maxRetries`) — assertion que **seule** cette ligne a `httpStatus="error"`, les autres
  `"success"`, et que le run se termine sans exception.
- Test de la garde d'egress : une `urlExpr` qui résout vers une IP interne (`127.0.0.1`/`10.x`) — assertion
  de rejet avant toute tentative réseau, comme pour `reader.connector.rest` (test isolé qui réactive la vraie
  garde via `_REAL_ASSERT_EGRESS_ALLOWED`) ; la garde s'applique à **chaque tentative de retry** (un 2ᵉ appel
  de la garde est observé après un `503`).
- Test de portée du secret (REV-294) : secret `bearer_token` avec `baseUrl` → une ligne dans la portée reçoit
  l'en-tête `Authorization`, une ligne hors portée est en `error` **sans aucune requête reçue** par le
  serveur de test ; secret sans `baseUrl` → échec du nœud.
- Bornes : plafond de lignes (`CORE_PIPELINES_HTTP_CALL_MAX_ROWS=2`, 3 lignes → échec avant toute requête) ;
  réponse > 5 Mo → ligne en erreur ; collision de nom de colonne de sortie avec une colonne d'entrée →
  `PipelineRuntimeError` ; géométrie et ordre d'entrée conservés dans la sortie.
- Test de concurrence : falsification explicite du budget — avec `maxConcurrency=2` et un serveur de test qui
  enregistre les intervalles de requêtes reçues, vérifier qu'au plus 2 requêtes sont in-flight simultanément
  (mesurer le recouvrement des intervalles, pas une durée totale — même piège CLAUDE.md n°7).
- Test de non-régression sur le compte d'op : `test_operations_registry_has_60_entries` passe à 61 (60
  aujourd'hui, + `transform.httpCall`) ; compte du catalogue exposé 58 → 59, à vérifier par comptage.
- `test_every_registered_transform_has_exactly_one_of_compile_or_execute` reste vert (`execute=` seul) ;
  `needs_secrets` : une op à `needs_secrets=True` reçoit bien `secret_resolver` (test runtime).
- `test_pipeline_routes.py` : `GET /pipelines/ops` contient `transform.httpCall` avec son `paramsSchema`.
- Test de sécurité des messages d'erreur : un `secretName` avec un jeton bearer réel, forcer un échec, vérifier
  que le jeton n'apparaît nulle part dans `errorColumn` ni dans les logs.

## 8. Portes de qualité et surfaces à régénérer avant clôture

- `ruff check`/`ruff format --check`/`mypy --strict` (si `app.pipelines` est dans le périmètre strict —
  vérifier `core/pyproject.toml`) ; `lint-imports` ; suite complète `core`.
- Régénérer `openapi.json` + `core-schema.d.ts` (piège CLAUDE.md n°1) — diff non vide attendu (1 nouveau
  schéma de params).
- `docs/revue/matrice-couverture-fme.jsonl` : ligne `HTTPCaller` `planned_duckdb` → `implemented`,
  `geostudio_equivalent` renseigné, puis `python3 core/scripts/fme_coverage_cli.py --write` puis `--check`.
- `docs/revue/inventaire-fonctionnalites.jsonl` : `GET /pipelines/ops` existe déjà, aucune nouvelle route —
  à vérifier plutôt que supposer.
- Aucun fichier `shell/` à modifier : `PipelinePalette.tsx`/`PipelineNodeInspector.tsx` restent
  générique-depuis-catalogue ; le formulaire de secret n'a pas besoin de nouveau `kind` (les 4 réutilisés
  existent déjà côté `SecretsAdminPage` pour `reader.connector.rest`) — **à revérifier contre le code réel**
  avant de clore, ne pas présumer par analogie (piège CLAUDE.md n°12).
- `CLAUDE.md` à la clôture : une ligne dans `### Livré` (« `transform.httpCall` (HTTPCaller) — appel HTTP par
  ligne avec retry exponentiel/Retry-After, pagination agrégée, multipart, concurrence+débit bornés, erreurs
  capturées par ligne ; catalogue exposé à 59 op, brut à 61 »).
- Pas de flag dédié : l'op vit déjà sous `CORE_ETL_ENABLED` (pipelines) ; les bornes du §« Révision »
  (lignes, taille de réponse, concurrence) tiennent lieu de garde-fou d'amplification.
- Si `runtime.py` ou `OperationContract` changent (`needs_secrets`, kwarg `secret_resolver`) : vérifier que
  `preview_pipeline` **et** `run_pipeline` passent le resolver (jumelles, piège CLAUDE.md n°14).
