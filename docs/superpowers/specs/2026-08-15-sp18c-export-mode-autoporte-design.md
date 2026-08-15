# Export d'apps : mode Autoporté (SP-18c)

> Spec issue du brainstorm du 2026-08-15. Troisième et dernier mode de SP-18
> (`docs/superpowers/specs/2026-08-05-export-apps-standalone-design.md`,
> jalon **M15 apps portables**) — après SP-18a (mécanisme commun + mode
> Statique) et SP-18b (mode Connecté), tous deux livrés. Clôt M15.

## 1. Contexte & objectif

Un auteur exporte une app publiée depuis le builder sous forme d'un
**conteneur Docker autonome** : un mini-serveur read-only (sous-ensemble
d'OGC API Features Part 1 + `/aggregate`) qui sert un **instantané figé** des
collections référencées par l'app, dans le même conteneur que le bundle
statique du shell. Zéro dépendance à Postgres, Keycloak ou MinIO dans
l'artefact exporté — seule dépendance externe : Docker, sur la machine de
l'utilisateur.

Ce mode complète Statique (données JSON embarquées dans le bundle, aucun
serveur) et Connecté (le bundle continue d'appeler le cœur GeoStudio
d'origine, données vivantes) : Autoporté offre un instantané figé mais
interrogeable dynamiquement côté serveur (filtres, bbox, agrégats), sans
dépendre de l'instance GeoStudio d'origine ni d'un hébergement statique.

## 2. Pourquoi c'est faisable sans reconstruire le moteur analytique

`app.analytics.aggregate.run_collection_aggregate` et
`app.analytics.duckdb_conn` n'ont **aujourd'hui déjà aucune dépendance
SQLAlchemy/Postgres** : ce sont des fonctions pures sur une connexion DuckDB
et une forme `table_info` à duck-typing (`.pk_column`, `.geometry_column`,
`.columns[].name`). Et `app.cdc.parquet_writer.write_geoparquet`/`ChangeRow`
sait déjà écrire une partition GeoParquet au format CDC. Un instantané est
exactement *« un lot CDC de rien que des insertions, un seul `_lsn`, sur
toutes les lignes actuelles »* — le job d'export peut donc produire une
disposition Parquet locale compatible partition
(`tenant_id=X/collection_id=Y/dt=snapshot/data.parquet`) avec ce même writer,
et l'endpoint `/aggregate` du mini-serveur réutilise
`run_collection_aggregate` **sans aucune modification**, simplement pointé
sur un chemin local (`file://…`) au lieu d'`s3://`.

## 3. Mécanisme

### 3.1 Production de l'instantané

Dans `build_app_export_task`, branché sur `mode="standalone"` (même patron
que SP-18b pour `mode="connected"`) : pour chaque `DataSource` de type
`"features"` ou `"statistics"`, récupère les lignes exactement comme
`freeze.py` le fait déjà (`introspect_table` + `select_features` in-process,
sous `rls_scope`), mais au lieu d'embarquer des enregistrements JSON,
enveloppe chaque ligne en `ChangeRow(op="insert", lsn=0, …)` et appelle
`write_geoparquet` vers un répertoire d'instantané local. Même plafond que
SP-18a : `max_records_per_source=50_000`, réutilisé tel quel (une collection
plus grande produit un instantané tronqué à 50k lignes — comportement déjà
documenté et accepté pour Statique, pas de raison de le durcir ici).

### 3.2 Mini-serveur (`core/app/appexport/miniserver/`, nouveau sous-module)

Une petite app FastAPI qui sert :
- Le sous-ensemble déjà énuméré par l'allowlist CORS de SP-18b :
  `GET /collections`, `GET /collections/{id}`, `GET /collections/{id}/schema`,
  `GET /collections/{id}/items`, `GET /collections/{id}/items/{fid}`,
  `POST /collections/{id}/aggregate`.
- Le bundle statique du shell (mêmes fichiers prébâtis que Statique/Connecté,
  `StaticFiles` sur le même processus) — **un seul conteneur, un seul port**,
  au sens littéral de la spec ombrelle (« un conteneur autonome »).

`/collections/{id}/items` est une implémentation nouvelle (lecture directe
du snapshot local via DuckDB — `app.features.repository.select_features` est
Postgres-only, inutilisable ici). `/aggregate` importe
`run_collection_aggregate` directement.

Le seul couplage SQLAlchemy accidentel de ce chemin — `TableInfo`
(`app.collections.introspection`) référence `Session` uniquement pour un
alias de type `Introspector` non utilisé ici — passe derrière
`TYPE_CHECKING` pour que ce sous-module n'ait jamais besoin de
SQLAlchemy/psycopg installés à l'exécution. Dépendances de l'image du
mini-serveur : `duckdb`, `fastapi`, `uvicorn`, `pydantic`. Rien d'autre.

### 3.3 Garde d'export

`check_export_guard` gagne `mode="standalone"` :
- Sources `"features"` et `"statistics"` : même garde `is_public` que
  `mode="connected"` (l'agrégat est pleinement supporté, contrairement à
  Statique qui le refuse faute de pouvoir le figer).
- Widgets : **même allowlist builtin que `mode="static"`** — décision prise
  en session (2026-08-15) : la spec ombrelle d'origine évoquait un
  « bundling » des widgets tiers pour Autoporté, mais ce bundling n'a jamais
  été construit, même pour Statique (SP-18a se contente d'interdire tout
  widget hors des 22 builtin). Autoporté suit ce même précédent réellement
  livré plutôt que la formulation d'origine, non implémentée, de la spec
  ombrelle — pas de nouvelle machinerie de bundling ES module dans ce SP.

### 3.4 Distribution de l'image

Un 4ᵉ artefact `geostudio-appexport-standalone` rejoint la matrice existante
de `.github/workflows/release.yml` (`build-and-push`), publié sur ghcr.io au
même titre que `geostudio-core`/`geostudio-shell`/`geostudio-postgis`
aujourd'hui. Le `docker-compose.yml` généré à l'export référence
`image: ghcr.io/tlenenao/geostudio-appexport-standalone:<tag>`, `<tag>` =
version du cœur qui a produit l'export (`core/pyproject.toml`'s `version`),
repli `latest` si absente/dev.

**Écart documenté, non corrigé par ce SP** (même nature que le suivi non
bloquant SP-15d/qgis) : aucun tag `v*.*.*` n'a jamais été poussé sur ce dépôt
— le pipeline `release.yml` n'a donc jamais réellement publié quoi que ce
soit sur ghcr.io à ce jour. Un `docker pull` réel contre l'image générée par
ce SP reste donc non vérifié tant que Tanguy n'a pas coupé une release. Le
test E2E de ce SP contourne ça en **construisant l'image localement** plutôt
qu'en la tirant du registre — même astuce que `test-gate` utilise déjà pour
l'image Postgis CI.

### 3.5 Artefact d'export

Même mécanisme zip que les deux autres modes
(`POST /app-exports?mode=standalone` → job procrastinate → upload S3 → lien
de téléchargement dans `AppExportPanel`), mais le zip contient cette fois :
le bundle statique prébâti (identique aux deux autres modes), les fichiers
d'instantané GeoParquet, un `docker-compose.yml` généré, un court README
(`docker compose up`, port exposé, aucune donnée écrite nulle part).

## 4. Hors périmètre v1 (hérité de la spec ombrelle)

- Écriture (mini-serveur strictement read-only — pas de widget Formulaire
  fonctionnel dans ce mode).
- Rafraîchissement automatique post-export (ré-export manuel uniquement,
  comme les deux autres modes).
- SQL Lab (`/analytics/sql`), `Tile3DLayer`, widgets d'impression — hors
  périmètre analytique, cf. spec ombrelle §4.
- Bundling de widgets tiers SP-8 (cf. §3.3 — décision prise en session).
- Publication garantie sur ghcr.io (cf. §3.4 — dépend d'un premier tag réel,
  hors périmètre de ce SP).

## 5. Validation & tests

Un test E2E réellement en conditions (pas asséré), dans l'esprit des deux
modes précédents : construit l'image du mini-serveur localement (pas de
`docker pull`), démarre le conteneur à froid (image + volumes vierges),
vérifie que l'app se charge, que `GET /collections/{id}/items` répond depuis
l'instantané GeoParquet, que `POST /collections/{id}/aggregate` répond, et
qu'aucun Postgres/Keycloak/MinIO n'apparaît dans le compose généré. Plus :
export refusé avec message explicite si une source non publique est
référencée (même garde que Connecté, test unitaire côté `check_export_guard`
comme SP-18a/b).

Non-régression : suites cœur/shell/E2E existantes restent vertes (mécanisme
additif, ne touche ni `AppRenderer` ni les `ItemClient` existants côté
instance GeoStudio normale).

## 6. Décisions prises en session (2026-08-15)

- **Distribution d'image** : publication ghcr.io (extension de la matrice
  `release.yml` existante) plutôt qu'un tar `docker save` embarqué dans le
  zip ou un `Dockerfile`+source à builder par l'utilisateur — cohérent avec
  le mécanisme de publication déjà en place pour les 3 autres images, écart
  documenté ci-dessus (§3.4) plutôt que bloquant.
- **Widgets tiers** : aucune tentative de bundling offline pour Autoporté —
  même restriction déjà réellement livrée pour Statique (§3.3), au lieu de
  la formulation plus ambitieuse mais jamais construite de la spec ombrelle
  d'origine.
