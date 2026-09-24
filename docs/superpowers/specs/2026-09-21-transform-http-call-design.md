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

## 0. Correction trouvée en explorant le dépôt (piège CLAUDE.md n°3, vérifié pas supposé)

`CLAUDE.md` (§ Décisions figées) dit « Expressions no-code : CEL ». C'est vrai **côté shell** (`cel-js`,
client, pour `visibleWhen`/`AppConfig`) mais **faux côté serveur pipelines** : le docstring de
`core/app/pipelines/expr_validation.py` corrige explicitement une affirmation historique fausse (design
SP-15a §5.1, « un moteur CEL tournait déjà côté serveur ») — `transform.filter`/`transform.derive`/
`transform.aggregate.metrics` évaluent en réalité une **expression SQL DuckDB bornée**
(`validate_bounded_expr`, même AST que `app.analytics.sql_sandbox`), jamais CEL. Ce chantier suit donc ce
mécanisme réel, pas celui supposé au brainstorm initial (décision validée par Tanguy après correction).

## 1. Ce que ce chantier construit, en une phrase

Une nouvelle op **`transform.httpCall`** (transform, `execution_model="in_process"`, `compile=None` — comme
`transform.qgis`, spécial-casée dans `runtime.py`, jamais dans `compiler.py` qui reste pur) : un appel HTTP
**par ligne** d'entrée, URL/headers/corps construits par expression SQL DuckDB bornée précalculée en une
passe vectorisée, avec auth par secret (mêmes 4 `kind` que `reader.connector.rest`), pagination multi-page
agrégée en une ligne, corps `multipart/form-data` avec fichier depuis une colonne, retry à backoff
exponentiel respectant `Retry-After`, concurrence bornée + débit configurable, et un échec par ligne capturé
(jamais un échec de run entier).

## 2. Périmètre

### 2.1 Dans ce chantier

- 1 op `transform.httpCall`, 1 nouvelle classe `TransformHttpCallParams` (`ops/schemas.py`), 1 nouvelle
  entrée `OPERATIONS` (`ops/contracts.py`), 1 nouveau module `core/app/pipelines/http_call_runtime.py`
  (même rôle que `connector_runtime.py` : matérialisation, jamais dans `compiler.py`), 1 branche spéciale
  dans `runtime.py::_execute_transform_chain` (même patron que `node.op == "transform.qgis"`).
- Réutilisation stricte, zéro duplication de logique déjà auditée :
  - Auth : `_build_auth`/`_REST_SECRET_KINDS`/`SecretResolver` de `connector_runtime.py`, appelés tels
    quels (import direct, pas de copie).
  - Pagination : `dlt.sources.helpers.rest_client.RESTClient` + les 4 paginateurs déjà utilisés par
    `materialize_rest_connector` (`_build_paginator`, réutilisé tel quel).
  - Egress SSRF : `assert_egress_allowed`/`build_guarded_session` de `egress.py`, **étendu** (pas dupliqué)
    pour accepter une politique de retry (§5).
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
runtime construit une vue intermédiaire :

```sql
CREATE TEMP VIEW node_xxx__templated AS
SELECT *,
       ({urlExpr}) AS __http_url,
       ({headersExpr or 'NULL'}) AS __http_headers,
       ({bodyExpr or 'NULL'}) AS __http_body
FROM {input_view}
```

puis lit cette vue avec DuckDB (`fetchall()` + `description` pour les noms de colonnes) pour obtenir, par
ligne, des valeurs Python déjà résolues — le code Python de la boucle réseau ne voit plus jamais de SQL.

Champs :

| Champ | Type | Défaut | Rôle |
|---|---|---|---|
| `urlExpr` | `str` | requis | expression SQL → URL complète |
| `method` | `Literal["GET","POST","PUT","PATCH","DELETE"]` | `"GET"` | méthode HTTP |
| `headersExpr` | `str \| None` | `None` | expression SQL produisant un objet JSON (`json_object(...)`), parsé en dict de headers |
| `bodyType` | `Literal["none","json","form","raw","multipart"]` | `"none"` | forme du corps |
| `bodyExpr` | `str \| None` | `None` | pour `json`/`form`/`raw` |
| `multipartFields` | `list[MultipartField]` | `[]` | pour `bodyType="multipart"` (§5) |
| `secretName` | `str \| None` | `None` | mêmes 4 `kind` que `reader.connector.rest` |
| `paginator` | `Literal["none","page_number","offset","cursor"]` | `"none"` | mêmes paginateurs dlt que `reader.connector.rest` |
| `paginatorConfig` | `dict` | `{}` | mêmes clés que `ReaderConnectorRestParams.paginatorConfig` |
| `recordsPath` | `str \| None` | `None` | sélecteur dlt (`data_selector`), utilisé seulement si `paginator != "none"` |
| `maxConcurrency` | `int` | `1` | appels simultanés max (`ThreadPoolExecutor` borné) |
| `requestsPerSecond` | `float \| None` | `None` | débit max, `None` = pas de limite au-delà de `maxConcurrency` |
| `maxRetries` | `int` | `3` | tentatives max sur timeout/5xx/429 |
| `initialBackoffSeconds` | `float` | `1.0` | délai initial, doublé à chaque tentative |
| `timeoutSeconds` | `float` | `30.0` | timeout par tentative |
| `responseColumn` | `str` | `"responseBody"` | colonne de sortie : corps de réponse |
| `statusCodeColumn` | `str` | `"httpStatusCode"` | colonne de sortie : code HTTP (dernier essai) |
| `statusColumn` | `str` | `"httpStatus"` | colonne de sortie : `"success"` \| `"error"` |
| `errorColumn` | `str` | `"httpError"` | colonne de sortie : message d'erreur, `NULL` si succès |

`MultipartField` : `{name: str, valueExpr: str, isFile: bool = False, filename: str | None = None,
contentType: str | None = None}`.

`OperationContract` : `kind="transform"`, `engine="python"`, `engine_license="Apache-2.0 (requests) +
Apache-2.0 (dlt, utilisé seulement si paginator≠none)"`, `is_copyleft=False`, `execution_model="in_process"`,
`compile=None` (comme `transform.qgis`, jamais dans `compiler.py`), `needs_columns=False` (les colonnes
requises sont résolues par la vue templée, pas par introspection `DESCRIBE`).

`model_validator` : `bodyExpr` requis si `bodyType` ∈ {`json`,`form`,`raw`} ; `multipartFields` non vide si
`bodyType="multipart"` ; les 4 noms de colonnes de sortie (`responseColumn`/`statusCodeColumn`/
`statusColumn`/`errorColumn`) doivent être distincts entre eux (une collision silencieuse écraserait une
colonne de données de l'utilisateur).

Docstring française courte sur `TransformHttpCallParams` (devient le tooltip de palette, même mécanisme que
les 47 op existantes — vérifié en Vague 1/2, `PipelinePalette.tsx` reste générique-depuis-catalogue, aucun
changement front nécessaire).

## 4. Exécution — `http_call_runtime.py`

Nouvelle fonction `execute_http_call_transform(conn, node, *, secret_resolver, input_view, view_name)`,
appelée depuis `runtime.py::_execute_transform_chain` dans une branche `elif node.op ==
"transform.httpCall":` symétrique à celle de `transform.qgis`.

1. Valider les expressions bornées (`urlExpr`/`headersExpr`/`bodyExpr`/chaque `valueExpr` de
   `multipartFields`) avec `validate_bounded_expr`, comme le fait déjà `_validate_node_exprs` pour
   `transform.filter`/`derive` — réutilisation, pas une 2e implémentation de validation.
2. Créer la vue templée (§3), la lire intégralement en mémoire Python (liste de dicts) — **limite assumée** :
   pas de streaming/batching, cohérent avec le fait qu'un appel réseau par ligne est de toute façon l'axe
   dominant de lenteur bien avant la taille mémoire d'une ligne (à documenter comme limite connue, pas un
   oubli — un jeu de plusieurs millions de lignes n'est pas un cas d'usage visé par cette op).
3. Résoudre l'auth une fois (`_build_auth` de `connector_runtime.py`, réutilisé) — jamais par ligne, un seul
   secret par nœud.
4. Traiter les lignes via un `ThreadPoolExecutor(max_workers=maxConcurrency)` ; un limiteur à jetons partagé
   (implémentation minimale maison, aucun équivalent existant dans le dépôt pour un débit sortant) applique
   `requestsPerSecond` si renseigné.
5. Par ligne (fonction exécutée dans le pool) :
   - Si `paginator == "none"` : un appel direct via une session gardée à retry (§5) — `requests.Session`,
     pas `httpx` (cohérence avec `egress.py`, qui garde `requests` — noté dans son propre docstring que
     copier le transport `httpx` de `app.harvest.egress` ne garderait rien en pratique ici non plus).
     `responseBody` = texte brut exact de la réponse, sans aucun parsing.
   - Si `paginator != "none"` : `RESTClient(...).paginate(url, method=, params=, json=)` (même client que
     `materialize_rest_connector`), pages concaténées en une liste, `responseBody` =
     `json.dumps(all_records)` — **parsing JSON interne nécessaire** pour suivre le curseur/offset entre
     pages (§ pagination, décision assumée : pas de contradiction avec « responseBody brut », qui ne
     s'applique qu'au cas `paginator="none"`, le cas courant).
   - Succès : `httpStatusCode` = code de la dernière tentative, `httpStatus="success"`, `httpError=NULL`.
   - Échec définitif (après `maxRetries`) : `httpStatusCode` = code de la dernière tentative (ou `NULL` si
     timeout/erreur de connexion sans réponse), `httpStatus="error"`, `httpError` = message borné (jamais
     l'URL complète ni un secret — même discipline que `ConnectorRuntimeError` dans `connector_runtime.py`).
6. Écrire les résultats collectés (dans l'ordre d'entrée, pas l'ordre de complétion — un `ThreadPoolExecutor`
   avec `executor.map` préserve cet ordre nativement) dans une `CREATE TEMP TABLE` combinant les colonnes
   d'entrée + les 4 colonnes de sortie.

## 5. Retry — extension de `egress.py`, pas une 2e garde

`build_guarded_session()` prend un nouveau paramètre optionnel `retry: urllib3.util.Retry | None = None`,
monté sur `_GuardedHTTPAdapter(max_retries=retry)`. `http_call_runtime.py` construit :

```python
Retry(
    total=params.maxRetries,
    backoff_factor=params.initialBackoffSeconds,
    status_forcelist=[429, 500, 502, 503, 504],
    respect_retry_after_header=True,
    allowed_methods=None,  # retry sur toutes les méthodes, pas seulement les idempotentes — HTTPCaller FME
                           # ne fait pas cette distinction, et le contrat n'a pas d'a priori sur le sens
                           # métier de l'appel de l'auteur du pipeline
)
```

Point vérifié (pas supposé) à confirmer par test avant clôture : les retries d'`urllib3` se produisent
**dans** `HTTPAdapter.send()` (au niveau `HTTPConnectionPool.urlopen`), donc `_GuardedHTTPAdapter.send()`
n'est appelé **qu'une fois par requête logique** — la garde d'egress s'exécute avant la 1ʳᵉ tentative, pas
avant chaque retry individuellement. Ce n'est pas une régression de sécurité : un retry cible le **même**
hôte déjà validé (aucune redirection n'est concernée par ce mécanisme, `requests` la traite séparément en
rappelant `send()` à chaque redirection, donc déjà re-gardée). À vérifier explicitement en test (§7) plutôt
que supposé — piège CLAUDE.md n°3.

## 6. Pagination et multipart — reformulation précise des choix validés

- **Pagination = agrégation multi-page en 1 ligne** (pas une explosion en plusieurs lignes) : cohérent avec
  la garantie de cardinalité 1:1 de la majorité du catalogue transform ; qui veut 1 ligne par page compose
  ensuite avec `transform.explodeList` sur le tableau JSON de `responseBody`.
- **Multipart = corps `multipart/form-data` avec fichier depuis une colonne** : `requests` accepte nativement
  `files={name: (filename, content, content_type)}` — chaque `MultipartField` avec `isFile=True` alimente ce
  dict, les autres deviennent le paramètre `data=` classique de `requests.request(...)`.

## 7. Tests (falsifiés avant clôture, piège CLAUDE.md n°10)

- Un test par branche `bodyType` (`none`/`json`/`form`/`raw`/`multipart`) contre un serveur HTTP de test
  local (`httpserver`/`responses`, à choisir contre ce qui est déjà une dépendance de test du dépôt —
  vérifier avant d'en ajouter une nouvelle).
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
  de rejet avant toute tentative réseau, comme pour `reader.connector.rest`.
- Test de concurrence : falsification explicite du budget — avec `maxConcurrency=2` et un serveur de test qui
  enregistre les intervalles de requêtes reçues, vérifier qu'au plus 2 requêtes sont in-flight simultanément
  (mesurer le recouvrement des intervalles, pas une durée totale — même piège CLAUDE.md n°7).
- Test de non-régression sur le compte d'op (`len(OPERATIONS) == 48` — 47 aujourd'hui, vérifié par
  comptage direct dans `ops/contracts.py`, + `transform.httpCall`).
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
  capturées par ligne ; catalogue à 48 op »).
