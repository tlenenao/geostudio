# SP-15f — `reader.connector` dlt (REST + Postgres) (design)

> **Date : 2026-08-06 · Statut : validé (brainstorm tenu en session)**
> Sixième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39**), consommant le coffre de secrets
> livré en
> [`2026-08-06-sp15e-connector-secrets-store-design.md`](2026-08-06-sp15e-connector-secrets-store-design.md)
> (§1/§7 : `reader.connector` y était nommément le premier consommateur
> anticipé, non construit dans ce sous-plan). Étude de faisabilité amont :
> [`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> §2.2 (choix de `dlt`, Apache-2.0, embarquable), §5 phase 3 (« `reader.connector`
> dlt (REST + Postgres) »), D5 (« périmètre initial : REST générique + Postgres ;
> élargir sur demande »), cas d'usage #4/#8.
>
> Références de code vérifiées en session : `core/app/pipelines/runtime.py`
> (mécanisme de matérialisation en deux passes, scratch `transform.qgis`),
> `core/app/pipelines/ops/schemas.py` (catalogue `OP_KINDS`/`OP_PARAMS`),
> `core/app/pipelines/config_validation.py` (validation forme-seule à la
> sauvegarde), `core/app/harvest/egress.py` (garde SSRF SP-12d),
> `core/app/analytics/sql_sandbox.py` (`parse_ast`/`validate_select_only`,
> déjà réutilisé par `app.pipelines.expr_validation`),
> `core/pyproject.toml:74-93` (contrat `layers` import-linter — `app.harvest`
> **au-dessus** de `app.pipelines`, `app.secrets` en dessous des deux).

## 1. Objectif & non-buts

**Objectif.** Deux nouvelles op **reader** dans le catalogue Pipeline
(`core/app/pipelines/ops/schemas.py`) : `reader.connector.rest` (API REST
paginée, générique) et `reader.connector.postgres` (requête SQL sur une base
Postgres distante), toutes deux authentifiables via un secret du coffre
SP-15e référencé **par son nom**, jamais par sa valeur. Chacune matérialise
son résultat en `TEMP TABLE` dans la même passe que `reader.collection`
(design SP-15a), pour que le reste du graphe (transforms/writers) ne
distingue pas une lecture externe d'une lecture de collection.

**Non-buts explicites** (v0, « élargir sur demande » — D5) :
- **Extraction incrémentale / `write_disposition="merge"`** — chaque run
  ré-extrait tout (`replace`), aucun état dlt n'est conservé entre deux runs
  (le fichier DuckDB scratch produit par dlt est supprimé en fin de run,
  même sort que le GPKG scratch de `transform.qgis`).
- **Tables enfants dlt** — une réponse REST dont un champ est un tableau
  imbriqué serait normalement éclatée par dlt en plusieurs tables liées ; v0
  ne sélectionne que la table racine (`records`), les colonnes de type
  tableau/objet imbriqué restent telles quelles (JSON brut) dans la colonne.
- **Détection automatique de géométrie** — contrairement à `reader.collection`
  et `transform.qgis`, qui renomment leur colonne géométrie détectée par
  type DuckDB en `"geometry"`, les deux nouvelles op v0 sont **purement
  tabulaires** : aucune détection, aucun renommage. Un auteur qui a besoin
  d'une géométrie issue d'un champ JSON (REST) ou WKB/hex (Postgres/PostGIS)
  la promeut lui-même en aval via `transform.derive`.
- **Planification/déclenchement** — `Pipeline.refreshPolicy` n'est pas
  touché ; ces deux op s'exécutent comme toute autre op, via `run_pipeline`
  existant (manuel ou MCP).
- **Canvas / palette** — authoring **MCP/REST uniquement**, même posture que
  `transform.qgis` (SP-15d) : pas de sélecteur de secret dans le builder
  (SP-15e n'a livré aucune UI de gestion des secrets), donc pas d'entrée de
  palette pour l'instant.
- **Exposition MCP des noms de secrets** — différée (SP-15e §7 l'anticipe
  explicitement pour un futur incrément de SP-15f, pas celui-ci) ; un agent
  doit connaître un `secretName` par un autre canal (indication humaine),
  exactement comme il doit déjà connaître un `collectionId`.
- **Écriture vers Postgres distant** — ces deux op sont des *readers* ; pas
  de `writer.connector`, aucune opération DML n'est jamais envoyée (cf. §5
  garde `SELECT`-only).
- **Enrichissement ligne à ligne** — le cas d'usage #8 de l'étude de
  faisabilité (« géocodage inverse, météo ») est couvert comme *lecture d'une
  table de référence à joindre* (`reader.connector.rest` + `transform.join`),
  pas comme un appel REST par ligne scannée.

## 2. Modélisation des op (décision de brainstorm)

Deux op séparées plutôt qu'une op unique à discriminant (comme `SecretPayload`
ou `transform.qgis.algorithmId`) : REST et Postgres ont des formes de params
sans recouvrement utile (pagination/`recordsPath` d'un côté, `query` SQL de
l'autre) — même granularité que les 5 op spatiales de SP-15c (une op = un
comportement), plutôt qu'une op fourre-tout. Le catalogue `OP_KINDS`/
`OP_PARAMS` (table clé→modèle) accueille simplement deux entrées de plus,
aucun changement de mécanisme.

```python
class ReaderConnectorRestParams(BaseModel):
    baseUrl: str = Field(..., pattern=r"^https?://")
    path: str = ""
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)   # statiques, non secrets — l'en-tête d'auth vient du secret (location="header")
    recordsPath: str | None = None    # chemin pointé vers le tableau d'enregistrements dans le corps de réponse ; None = le corps EST le tableau
    paginator: Literal["none", "page_number", "cursor", "offset"] = "none"
    paginatorConfig: dict[str, Any] = Field(default_factory=dict)  # forme dépendante de `paginator`, passée telle quelle au paginateur dlt
    secretName: str | None = None     # référence un secret api_key/bearer_token/basic_auth/oauth2_client_credentials ; None = endpoint public non authentifié


class ReaderConnectorPostgresParams(BaseModel):
    secretName: str                    # référence un secret postgres_dsn — toujours requis, pas de notion de DSN non authentifié
    query: str                          # texte SQL libre, validé SELECT-only à l'EXÉCUTION (§5), jamais à la sauvegarde
```

Ajouts à `OP_KINDS`/`OP_PARAMS` :

```python
OP_KINDS["reader.connector.rest"] = "reader"
OP_KINDS["reader.connector.postgres"] = "reader"
OP_PARAMS["reader.connector.rest"] = ReaderConnectorRestParams
OP_PARAMS["reader.connector.postgres"] = ReaderConnectorPostgresParams
```

`ops_catalog()` (déjà générique sur `OP_PARAMS`) les publie automatiquement
en JSON Schema via `GET /pipelines/ops`, sans changement de mécanisme.

## 3. Runtime d'exécution

### 3.1 Profondeur d'intégration dlt (décision de brainstorm)

Le runtime actuel matérialise chaque reader en `TEMP TABLE` DuckDB éphémère,
**sans aucun état persisté entre les runs** (design SP-15a). dlt, lui, est
conçu autour d'un pipeline complet avec sa propre destination et ses tables
de catalogue (`_dlt_loads`, `_dlt_version`…).

**Retenu : dlt complet → DuckDB scratch éphémère → `ATTACH`.** Chaque run
exécute un vrai pipeline dlt (extraction, normalisation, inférence de
schéma, pagination — tout géré par dlt) vers un fichier DuckDB scratch dédié
au nœud ; le runtime l'`ATTACH` en lecture seule dans sa connexion,
sélectionne la table racine en `TEMP TABLE`, puis supprime le fichier
scratch. Alternative écartée (dlt en extraction pure, sans jamais appeler
`pipeline.run()`) : plus léger, mais réimplémente à la main l'inférence de
schéma/normalisation JSON imbriquée que dlt offre gratuitement en mode
pipeline complet — perd l'essentiel de la raison pour laquelle dlt a été
retenu dans l'étude de faisabilité (§2.2, ligne « time-to-value »).

Contrairement au sidecar `qgis-worker` (SP-15d), **aucun nouveau service
compose** : dlt est une bibliothèque Python in-process dans le `worker`
existant, sans besoin d'isolation (elle porte déjà les identifiants du
tenant, résolus depuis le secret qu'on lui donne — pas de frontière de
confiance à faire respecter comme pour QGIS). Le fichier scratch vit dans un
répertoire temporaire ordinaire (`tempfile`), pas dans le volume `/scratch`
partagé avec le sidecar QGIS (celui-ci existe spécifiquement pour la
frontière d'isolation du sidecar — sans objet ici).

### 3.2 Séquence de matérialisation (`_prepare`, passe 1)

Ajout au bloc de matérialisation des readers de `_prepare()` (avant
`_lock_down`), à côté de `reader.collection` :

```python
def _materialize_connector_rest(conn, node, *, session, tenant_id, view_name, run_id) -> None:
    p = ReaderConnectorRestParams.model_validate(node.params)
    payload = _resolve_secret(session, tenant_id, p.secretName)  # None si secretName est None
    scratch_path = _dlt_scratch_path(run_id, node.id)
    _run_dlt_rest_pipeline(p, payload, destination_path=scratch_path)  # dlt.sources.rest_api + session à adaptateur SSRF (§5.2)
    _attach_and_select(conn, scratch_path, view_name=view_name)
    _cleanup_scratch(scratch_path)  # finally, best-effort


def _materialize_connector_postgres(conn, node, *, session, tenant_id, view_name, run_id) -> None:
    p = ReaderConnectorPostgresParams.model_validate(node.params)
    payload = _resolve_secret(session, tenant_id, p.secretName)
    if payload is None:
        raise PipelineRuntimeError(f"secret '{p.secretName}' not found")
    validate_select_only(parse_ast(conn, p.query))   # §5.3, garde-fou à l'exécution seulement
    scratch_path = _dlt_scratch_path(run_id, node.id)
    _run_dlt_sql_pipeline(p, payload, destination_path=scratch_path)  # dlt.sources.sql_database
    _attach_and_select(conn, scratch_path, view_name=view_name)
    _cleanup_scratch(scratch_path)
```

`_attach_and_select` :

```python
def _attach_and_select(conn, scratch_path: str, *, view_name: str) -> None:
    conn.execute(f"ATTACH '{scratch_path}' AS dlt_extract (READ_ONLY)")
    try:
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM dlt_extract.pipeline_dataset.records LIMIT 0"
        ).description if d[0] not in {"_dlt_id", "_dlt_load_id"}]
        select_list = ", ".join(_qi(c) for c in cols)
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            f"SELECT {select_list} FROM dlt_extract.pipeline_dataset.records"
        )
    finally:
        conn.execute("DETACH dlt_extract")
```

La ressource dlt est nommée **de façon déterministe** (`"records"`, dataset
`"pipeline_dataset"`) côté appel `dlt.pipeline(...).run(resource, ...)` —
le runtime n'a jamais besoin d'introspecter le schéma dlt pour savoir quelle
table sélectionner. Colonnes de plomberie dlt (`_dlt_id`, `_dlt_load_id`)
exclues de la sélection, même logique que `_materialize_reader` qui exclut
les colonnes de plomberie CDC (`_op`/`_lsn`/`_ts`).

En cas d'échec (connexion, authentification, timeout, erreur dlt) :
`PipelineRuntimeError` avec message clair — même contrat que
`_execute_qgis_transform` pour ses erreurs `httpx`.

## 4. Résolution du secret

```python
def _resolve_secret(session: Session, tenant_id: str, secret_name: str | None) -> SecretPayload | None:
    if secret_name is None:
        return None
    payload = secrets_repo.get_secret_payload(session, tenant_id=tenant_id, name=secret_name)
    if payload is None:
        raise PipelineRuntimeError(f"secret '{secret_name}' not found")
    return payload
```

Appelé **uniquement à l'exécution** (jamais à la sauvegarde du pipeline —
§6). `app.pipelines` est positionné **au-dessus** de `app.secrets` dans le
contrat de couches (`app.harvest`, `app.pipelines`, `app.secrets`,
`app.ingestion`…, `core/pyproject.toml:74-93`), donc cet import est déjà
autorisé sans modification du contrat (c'est exactement la position que
SP-15e avait anticipée pour ce module).

`_resolve_secret` retourne un `SecretPayload` générique (l'union discriminée
des 5 kinds, SP-15e §4) — **c'est `_run_dlt_rest_pipeline`/
`_run_dlt_sql_pipeline` (§3.2), pas `_resolve_secret`, qui vérifie que
`payload.kind` correspond à ce que le connecteur attend** :
`reader.connector.rest` accepte `api_key`/`bearer_token`/`basic_auth`/
`oauth2_client_credentials` (rejette `postgres_dsn` avec une
`PipelineRuntimeError` claire) ; `reader.connector.postgres` n'accepte que
`postgres_dsn` (rejette les 4 autres). Un `secretName` du mauvais type
référencé par erreur échoue donc à l'exécution avec un message explicite,
jamais silencieusement.

## 5. Sécurité

### 5.1 Garde-fou SSRF — duplication dans `app.pipelines`

`app.harvest.egress.assert_egress_allowed` n'est **pas importable** depuis
`app.pipelines` : `app.harvest` est listé au-dessus de `app.pipelines` dans
le contrat `layers`, et une couche ne peut importer que ce qui est **en
dessous** d'elle (`app.pipelines` ne peut donc pas importer `app.harvest`,
même contrainte que celle documentée par SP-15e §3.1 pour `app.secrets`).

**Retenu : dupliquer** `assert_egress_allowed`/`_is_internal` (~70 lignes,
aucune dépendance interne — seulement `ipaddress`/`socket`/`urllib.parse`)
dans un nouveau `core/app/pipelines/egress.py`. Même posture que les
duplications déjà assumées dans ce module (`_qi()` dupliqué 3× selon le
commentaire de `compiler.py`, `_require_admin()` dupliqué par module selon
SP-15e plan Global Constraints) plutôt que de rouvrir la frontière de
`app.harvest` (module d'un autre sous-plan, hors périmètre ici) ou de
déplacer la garde vers un module plus bas.

**Point d'application — attention au client HTTP.** La garde existante
s'applique via un **transport `httpx`** personnalisé
(`_GuardedTransport(httpx.BaseTransport)`). Mais `dlt.sources.rest_api`
utilise **`requests`** en interne, pas `httpx` — copier tel quel le garde-fou
httpx ne protégerait **rien** en pratique (faux sentiment de sécurité, à ne
pas manquer en implémentation). La duplication doit prendre la forme d'un
`requests.adapters.HTTPAdapter` dont `send()` appelle
`assert_egress_allowed(request.url)` avant de déléguer, monté sur la
`requests.Session` passée explicitement à
`dlt.sources.rest_api.rest_api_source(..., session=guarded_session)`.
Résiduel documenté identique à SP-12d : DNS-rebinding TOCTOU (la garde
valide l'IP résolue avant la requête, `requests` re-résout à la connexion) —
même risque accepté, pas de pinning-IP.

`reader.connector.postgres` n'émet aucune requête HTTP (connexion SQL
directe via le DSN du secret) — la garde SSRF ne s'y applique pas ; le DSN
lui-même est la frontière de confiance (posé par un admin qui a créé le
secret).

### 5.2 Garde-fou `SELECT`-only sur `reader.connector.postgres.query`

Réutilise **tel quel** `app.analytics.sql_sandbox.parse_ast` +
`validate_select_only` — le même mécanisme que
`app.pipelines.expr_validation.validate_bounded_expr` utilise déjà pour les
expressions bornées. Ici appliqué à un texte SQL **complet** (pas une
expression bornée dans un `SELECT (...)` sans `FROM`), pour rejeter tout ce
qui n'est pas un `SELECT`/`WITH` avant de l'envoyer à la base Postgres
distante. Défense en profondeur heuristique, pas une garantie : le texte est
parsé avec le dialecte SQL de **DuckDB**, pas celui de Postgres — un texte
syntaxiquement valide pour DuckDB mais rejeté/différent en Postgres échoue
côté Postgres avec une erreur claire (comportement accepté, documenté).
Vérifié **à l'exécution uniquement** (§6), jamais à la sauvegarde — même
règle que tout SQL borné de ce module.

`app.pipelines` peut déjà importer `app.analytics` : ce module n'apparaît
pas dans la liste `layers` du contrat import-linter (confirmé en lisant
`core/pyproject.toml:74-93` en session), donc hors du périmètre du contrat —
`runtime.py`/`expr_validation.py` l'importent déjà sans dérogation.

### 5.3 Permissions

Aucune nouvelle porte. Reprend la posture déjà tranchée par SP-15e §6 :
n'importe quel auteur de pipeline ayant les droits d'écriture sur l'item
Pipeline peut référencer un secret existant **par son nom** (un admin l'a
créé) ; la valeur en clair du secret n'apparaît **jamais** dans le JSON du
Pipeline, une réponse MCP, une sortie de preview, des statistiques de run ou
une entrée d'audit — uniquement `secretName`.

## 6. Validation à la sauvegarde vs à l'exécution

`app.pipelines.config_validation` ne gagne **aucune entrée** dans
`_COLLECTION_PARAM_FIELD` pour ces deux op : à la sauvegarde, seule la
**forme** des params (Pydantic) est vérifiée — pas l'existence du secret, pas
la validité du SQL. C'est exactement le comportement anticipé par SP-15e
§6 : *« Une future `reader.connector` (SP-15f) qui référence un secret
supprimé échoue à l'**exécution** avec un message clair — jamais un blocage
à la sauvegarde du pipeline, même philosophie que les expressions CEL et
`transform.qgis`. »* Un `secretName`/`query` invalide sauvegardable, qui
échoue proprement au run, est le comportement voulu, pas un bug.

## 7. Déploiement

- `dlt` (Apache-2.0) ajouté à `core/pyproject.toml` et à l'image `worker`
  (feasibility study §3.6 : « `worker` : `+dlt` dans `pyproject.toml`/
  `Dockerfile` » — confirmé ici, aucune divergence).
- **Aucun nouveau service compose** — contrairement au sidecar
  `qgis-worker` de SP-15d, dlt est in-process, sans frontière d'isolation à
  matérialiser en conteneur séparé.
- `CORE_ETL_ENABLED` (capacité instance-wide existante, SP-15a) couvre ces
  deux op comme toutes les autres — aucune nouvelle capacité.

## 8. Exposition MCP

Aucun nouvel outil. `explain_pipeline` (existant) expose les deux nouvelles
op gratuitement via `ops_catalog()` (déjà générique sur `OP_PARAMS`).
Conformément à SP-15e §7, la liste des **noms** de secrets (métadonnées
seules, jamais de valeur) pour guider un agent auteur vers un `secretName`
existant est **différée** à un futur incrément de SP-15f, pas construite
ici — un agent doit connaître un `secretName` par un canal humain, comme il
doit déjà connaître un `collectionId`.

## 9. Tests (`core/tests/`)

- **Schémas** : round-trip forme des deux nouveaux modèles de params (y
  compris `secretName=None` sur REST, requis sur Postgres).
- **Runtime REST** : contre un serveur HTTP local factice (`pytest-httpserver`
  ou équivalent, pas de réseau réel) — injection de l'en-tête/param d'auth
  depuis un secret factice (les 4 kinds `api_key`/`bearer_token`/
  `basic_auth`/`oauth2_client_credentials` pertinents pour REST), pagination
  (les 3 modes), extraction `recordsPath`, cible interne bloquée par la garde
  SSRF (assertion sur l'adaptateur `requests`, pas seulement sur la fonction
  `assert_egress_allowed` isolée — pour couvrir le point d'application §5.1).
- **Runtime Postgres** : fixture Postgres réelle existante (patron
  `pg_engine`/tests marqués comme les autres tests DB-dépendants du dépôt) —
  round-trip requête → lignes ; texte non-`SELECT` rejeté (`INSERT`/`UPDATE`/
  `DELETE`/DDL), testable sans DB réelle (le rejet est un échec de parsing/
  validation avant toute connexion).
- **Secret manquant/supprimé** → `PipelineRuntimeError` propre à
  l'**exécution**, jamais un blocage à la sauvegarde (test explicite des deux
  moments).
- **Non-fuite** : aucune valeur de secret dans la sortie de preview, les
  statistiques de run, ou une entrée `audit_log` (même style d'assertion que
  les tests routes de SP-15e — scan du corps de réponse/payload).
- **Frontière de couches** : `lint-imports` confirme que `app.pipelines`
  reste incapable d'importer `app.harvest` (la duplication §5.1, pas un
  import, ne doit jamais en introduire un) et peut importer `app.secrets`
  (déjà vrai, non modifié par ce sous-plan).
- Suites existantes (`core` pytest, `shell` vitest/e2e) restent vertes —
  extension additive pure (2 entrées de catalogue, aucune route/comportement
  existant modifié).

## 10. Compatibilité & risques

Aucune migration Alembic (aucune nouvelle table). Aucun nouveau service
compose. Nouvelle dépendance Python directe (`dlt`) sur `core`/`worker`.
Extension pure du catalogue d'op (`OP_KINDS`/`OP_PARAMS`) et de
`runtime.py` — aucune route/comportement existant modifié.

| Risque | Mitigation |
|---|---|
| La garde SSRF dupliquée est branchée sur le mauvais client HTTP (httpx au lieu de l'adaptateur `requests` que dlt utilise réellement) | Signalé explicitement en §5.1 comme point d'attention d'implémentation ; test dédié qui exerce l'adaptateur `requests`, pas seulement la fonction de garde isolée |
| Un `secretName` de type `postgres_dsn` référencé par erreur dans `reader.connector.rest` (ou l'inverse) | Le discriminant `kind` du payload déchiffré (SP-15e §4) ne correspond pas à la forme attendue par le connecteur → erreur claire à l'exécution, pas un comportement silencieusement dégradé (à vérifier explicitement en implémentation : chaque connecteur valide le `kind` du payload résolu avant de l'utiliser) |
| Garde `SELECT`-only contournable par une syntaxe valide en Postgres mais non reconnue par le parseur DuckDB (faux négatif) | Documenté comme défense en profondeur heuristique, pas une garantie (§5.2) — le DSN lui-même (privilèges accordés par l'admin qui l'a créé) reste la frontière de sécurité réelle |
| Fichier DuckDB scratch dlt non nettoyé après un crash worker | Risque opérationnel mineur identique au scratch GPKG de `transform.qgis` (accepté en design SP-15d), pas traité différemment ici |
| Poids/complexité de `dlt` comme dépendance (surface transitive) | Déjà arbitré dans l'étude de faisabilité (§2.2) — Apache-2.0, embarquable, retenu contre 6 alternatives ; pas rediscuté ici |
