# SP-11c — Endpoint SQL analyste read-only sandboxé

Date : 2026-07-18
Statut : validé (brainstorm), en attente de plan

## Contexte

SP-11 (« Lakehouse & CDC », feuille de route §SP-11, arbitrages A16–A19) fait
rejoindre le SIG à la data platform. Ses deux premières sous-parties sont
closes :

- **SP-11a** (`2026-07-17-sp11a-spike-cdc-geoparquet-design.md`) : socle CDC —
  worker dédié répliquant PostGIS (chaud) vers un change-log GeoParquet
  append-only sur MinIO (froid), partitionné
  `tenant_id=<t>/collection_id=<c>/dt=<date>/part-<uuid>.parquet`, colonnes
  métier + `_op`/`_lsn`/`_ts`, reprise sur panne idempotente.
- **SP-11b** (`2026-07-17-sp11b-compaction-analytique-duckdb-design.md`) : job de
  compaction + module analytique DuckDB in-process
  (`app/analytics/duckdb_conn.py`, `app/analytics/aggregate.py`) et endpoint
  `POST /collections/{id}/aggregate` (group-by/mesures/filtres attributaires et
  spatiaux simples) qui remplace l'agrégation client de `queryDataSource`. La
  réduction à l'état courant (`QUALIFY row_number() OVER (PARTITION BY <pk>
  ORDER BY _lsn DESC) = 1`, tombstones exclues) et la connexion DuckDB éphémère
  par requête (extensions `httpfs`+`spatial` embarquées dans l'image) sont déjà
  en place et éprouvées.

Il reste **la deuxième moitié d'A19** : l'endpoint SQL read-only sandboxé
réservé au rôle *analyste* (feuille de route §SP-11 : « vues autorisées par les
permissions, quotas, timeout » ; critère d'acceptation SP-11 : « un analyste
exécute du SQL read-only sur ses vues autorisées, un non-analyste reçoit 403 »).
C'est la dernière sous-partie de SP-11 — sa livraison **clôt SP-11**.

Aujourd'hui, aucun rôle *analyste* distinct n'existe (`core/app/users` ne connaît
que le booléen `is_admin`, bootstrappé par `CORE_ADMIN_SUBS`, réglable par
`PATCH /users`, exposé sur `GET /me`), et aucune surface SQL n'est exposée.

## Objectif de SP-11c

Un utilisateur porteur du rôle *analyste* exécute du SQL read-only, via une
nouvelle API du cœur, sur les collections qu'il a le droit de lire — chacune
exposée comme une vue DuckDB déjà réduite à l'état courant sur le GeoParquet
CDC. Un non-analyste reçoit 403. Le SQL est confiné par construction aux seules
vues autorisées (jamais d'accès à un autre tenant, à une autre collection, à un
fichier arbitraire, ni à une écriture), borné par un timeout, un plafond de
lignes et une limite mémoire, et chaque exécution est auditée.

**Hors périmètre :**

- **SQL Lab (UI)** : la feuille de route (§SP-14, « SQL Lab : l'UI de l'endpoint
  SQL read-only du rôle analyste ») rattache explicitement l'interface à SP-14.
  SP-11c ne livre que l'endpoint backend. Aucune spec E2E shell attendue.
- **Outil MCP d'exécution SQL** : REST-only pour cette sous-partie (même
  arbitrage que `POST /aggregate` en SP-11b — aucun besoin agent identifié, et
  offrir une surface SQL brute à un agent est un risque distinct qui mérite sa
  propre décision). À réévaluer si un besoin concret émerge.
- **Analytique temporelle / point-in-time** : les vues n'exposent que l'état
  courant (comme SP-11b), pas de requête historique sur le change-log.
- **DuckDB-WASM navigateur** (A18, différé par la feuille de route).
- **Dashboard/alerte Grafana** dédié aux requêtes SQL (patron SP-10b, dans une
  sous-partie ultérieure si une métrique s'avère utile) — la donnée est
  exportée dès ici (cf. §Observabilité), pas son exploitation Grafana.
- **Datasets sauvegardés** (« un analyste sauve une requête SQL comme dataset »,
  feuille de route §SP-14/A28) — hors périmètre, relève de SP-14.
- **Politique de rétention/archivage du change-log** : limite héritée de SP-11b,
  non traitée (cf. §Risques).

## Architecture

### Rôle analyste (`core/app/users`)

Nouveau booléen `users.is_analyst` (`NOT NULL default false`, migration Alembic),
**miroir exact du pattern `is_admin`** :

- bootstrap depuis une nouvelle variable `CORE_ANALYST_SUBS` (même logique que
  `CORE_ADMIN_SUBS` dans `app/auth/dependency.py` / `app/users/repository.py` :
  un sub retiré de la variable ne destitue pas silencieusement) ;
- réglable par un admin via `PATCH /users` (champ `isAnalyst`, à côté de
  `isAdmin`) ;
- exposé sur `GET /me` (`isAnalyst`).

**`is_admin` n'implique PAS `is_analyst`** — ce sont deux capacités distinctes,
conformes à la séparation de personas de la vision. La conséquence de test est
assumée : le cas 403 s'appuie sur un utilisateur ordinaire (ni admin ni
analyste), et un admin non-analyste reçoit lui aussi 403.

Côté shell : le type `Me` gagne `isAnalyst` (régénéré depuis l'OpenAPI, comme
`isAdmin`). Aucune UI consommatrice dans cette sous-partie (SQL Lab = SP-14) —
le champ est exposé pour cohérence de contrat et pour SP-14.

### Endpoint `POST /analytics/sql`

- **POST**, corps `{ "sql": "<texte>" }`.
- **Autorisation** : `is_analyst` requis (403 sinon, **avant tout travail
  DuckDB**). Le périmètre des données lisibles reste porté par la porte existante
  `can(user, "read", collection)` — aucun nouveau modèle de permission.
- **Réponse** : forme tabulaire alignée sur ce que renvoie déjà
  `app/analytics/aggregate.py` (colonnes + lignes), à figer en plan par lecture
  du code existant plutôt que réinventée.
- **Exemption du mode démo/read-only** : c'est un `POST` mais une lecture. Le
  middleware ASGI read-only de SP-9 (« démo lecture seule ») 403 tout
  `POST/PUT/PATCH/DELETE` hors `/mcp`. `POST /aggregate` avait dû être exempté au
  même titre (commit SP-11b « endpoint POST /collections/{id}/aggregate, exempté
  du mode démo ») ; `POST /analytics/sql` l'est **exactement de la même façon**,
  sans quoi tout déploiement démo 403-erait chaque requête analyste.
- **Erreurs** : SQL invalide / vue inconnue → 400 avec message ; dépassement de
  timeout → 400 (ou 408, à trancher en plan) ; non-analyste → 403.

### Isolation — le cœur délicat (spike go/no-go d'ouverture)

Par requête, une connexion DuckDB **éphémère** (réutilise strictement le patron
`app/analytics/duckdb_conn.py` de SP-11b : extensions `httpfs`+`spatial`
embarquées et `LOAD`-ées, credentials S3/MinIO issus de la config déjà utilisée
par `app.cdc.storage`, connexion fermée en fin de requête).

Pour **chaque collection que l'analyste a le droit de lire**
(`can(user, "read", collection)` dans son tenant — même surface de permission
que `GET /items` et `POST /aggregate`), on **pré-enregistre une vue** (nom =
identifiant de collection) construite à partir de la **réduction état-courant de
SP-11b** : `read_parquet` scopé à
`tenant_id=<tenant courant>/collection_id=<id>/` (jamais un glob plus large —
l'isolation tenant est portée par le chemin, il n'existe pas de RLS Postgres côté
fichiers), `QUALIFY row_number() OVER (PARTITION BY <pk> ORDER BY _lsn DESC) = 1`,
exclusion des `_op = 'delete'`, colonne géométrie exposée. Le builder de vue /
CTE de `app/analytics/aggregate.py` est réutilisé, pas dupliqué.

Le SQL de l'analyste s'exécute ensuite contre une connexion **durcie de sorte
que DuckDB lui-même interdit tout accès externe au-delà de ces vues** : pas de
`read_parquet`/`read_csv`/`glob`/`parquet_scan` fournis par l'analyste, pas
d'`ATTACH`, pas de `COPY`/écriture, pas de `LOAD`/`INSTALL`, pas de lecture de
fichier local, pas de chemin cross-tenant. **La frontière de sécurité est
DuckDB, pas un parseur maison** (l'approche « parser/allowlist comme seule
frontière » a été explicitement écartée en brainstorm comme trop fragile).

Parce que c'est la frontière de sécurité et « le morceau délicat », l'incantation
exacte de durcissement est **verrouillée par un spike go/no-go en tâche
d'ouverture du plan** — patron déjà suivi par SP-11a et SP-11b, précisément
parce que ce chantier porte le risque le plus élevé de la feuille de route.
Mécanismes candidats :

- **(A) — recommandé** : matérialiser les vues scopées référencées en tables
  temporaires (`CREATE TEMP TABLE … AS SELECT …`), puis
  `SET enable_external_access = false; SET lock_configuration = true`, puis
  exécuter le SQL de l'analyste — DuckDB refuse alors physiquement tout accès
  fichier/S3/`ATTACH`/`LOAD` au moment du bind/exécution. Isolation **imposée par
  DuckDB**. Coût : matérialisation en mémoire (à borner ; cf. §Risques). La
  découverte des vues réellement référencées, si nécessaire pour ne matérialiser
  que le strict utile, peut s'appuyer sur le parseur **natif** de DuckDB
  (`json_serialize_sql`) — utilisé comme optimisation et pour un 400 clair « vue
  inconnue », **pas** comme frontière de sécurité (qui reste `enable_external_
  access = false`, défense en profondeur).
- **(B)** : vues paresseuses + denylist **native DuckDB** des fonctions
  fichier/`ATTACH`/config appliquée au SQL. Plus léger, mais la frontière repose
  sur une denylist.

Le spike doit **empiriquement mettre en échec**, contre un MinIO réel et un
fichier GeoParquet réel : lecture d'un chemin cross-tenant, `read_parquet`/
`read_csv` arbitraire fourni par l'analyste, `ATTACH`, `COPY TO` (tentative
d'écriture), `INSTALL`/`LOAD`, lecture de fichier local — tout en retournant un
résultat correct depuis les vues scopées sous les limites de timeout/lignes/
mémoire. Si un de ces points ne peut être bloqué proprement, le plan s'arrête
avant d'investir dans l'endpoint complet.

### Quotas

Sur la connexion éphémère, avant l'exécution du SQL analyste :
`SET statement_timeout` (~10 s), plafond de lignes **appliqué** (~10 000, par
`LIMIT` imposé ou troncature côté serveur — à trancher en plan),
`SET memory_limit` (~512 Mo), nombre de threads plafonné. Toutes ces valeurs
sont réglables et à affiner en plan selon le profilage. Elles bornent l'abus/DoS
sans infrastructure de jobs (l'exécution reste synchrone — requête/réponse — ce
qui suffit à du SQL analytique read-only sous timeout).

### Observabilité & audit

- **`audit_log`** : une entrée par exécution SQL (acteur, tenant, texte de
  requête tronqué) — le SQL analyste est une surface sensible qui mérite d'être
  tracée, cohérent avec l'audit déjà en place sur les mutations.
- **OTel** : compteur `geostudio.analytics.sql_queries` (patron SP-10a, export
  OTLP inconditionnel, silencieux si aucun collecteur n'écoute). Aucun dashboard
  ni règle d'alerte Grafana dans cette sous-partie.

## Tests

- **Spike (go/no-go, tâche d'ouverture du plan)** :
  `scripts/spike_duckdb_sql_sandbox.py` (même patron que
  `spike_duckdb_geoparquet.py` de SP-11b et `spike_cdc_replication.py` de
  SP-11a), contre un MinIO réel + un GeoParquet réel. Valide la lecture correcte
  d'une vue scopée **et** le rejet de chacun des cas d'abus listés en
  §Architecture. Verrouille le mécanisme de durcissement (A vs B) avant le reste
  du plan.
- **Cœur (marqueur `postgis` pour ce qui touche `can()`/la DB ; fixtures Parquet
  écrites sur un MinIO de test, même patron que `app.analytics`/`app.cdc`)** :
  bootstrap `CORE_ANALYST_SUBS` et `PATCH /users` (`is_analyst`) ; 403 pour un
  non-analyste **et** pour un admin non-analyste ; l'ensemble des vues
  enregistrées correspond exactement aux collections lisibles par l'analyste
  (ni plus — pas de collection non autorisée, ni d'un autre tenant — ni moins) ;
  une requête analytique correcte (réduction état courant, tombstone exclue) ;
  chaque cas d'abus d'isolation rejeté ; timeout / plafond de lignes / limite
  mémoire effectivement appliqués ; entrée `audit_log` écrite ; compteur OTel
  incrémenté (`InMemoryMetricReader`, patron SP-10a/b).
- **Empirique de bout en bout** : une requête analyste sur ~1 M lignes CDC
  (réparties sur plusieurs fichiers, backfill + flux incrémental — pas un unique
  fichier artificiel) retourne un résultat correct sous les limites.
- **E2E shell** : aucune nouvelle spec attendue (pas d'UI). Le changement de
  forme de `GET /me` (ajout `isAnalyst`) ne doit régresser aucune spec existante
  (mocks re-câblés si nécessaire).

## Critères d'acceptation

1. Un analyste exécute du SQL read-only sur ses vues autorisées et obtient des
   résultats corrects (état courant réduit, tombstones exclues), pour les seules
   collections qu'il a le droit de lire.
2. Un non-analyste — y compris un admin non-analyste — reçoit 403, avant tout
   travail DuckDB.
3. Chacun des cas d'abus d'isolation (lecture cross-tenant, `read_parquet`/
   `read_csv` arbitraire, `ATTACH`, écriture `COPY TO`, `INSTALL`/`LOAD`, lecture
   de fichier local) est rejeté — **imposé par DuckDB**, validé par le spike.
4. Chaque exécution est bornée par un timeout, un plafond de lignes et une limite
   mémoire, et tracée dans `audit_log` ; le compteur `geostudio.analytics.
   sql_queries` est exporté.
5. Aucune régression : `docker compose up` inchangé, suites cœur/shell/E2E
   vertes. **SP-11 est intégralement clos.**

## Risques

- **Frontière de sécurité DuckDB non triviale** : garder « SQL read-only » de
  devenir « lire n'importe quel objet MinIO via `httpfs` » est le point délicat
  de cette sous-partie. Mitigation : spike go/no-go d'ouverture (comme SP-11a/b),
  frontière imposée par DuckDB (`enable_external_access = false`) et non par un
  parseur maison, cas d'abus explicitement testés.
- **Coût de matérialisation (mécanisme A)** : matérialiser en mémoire les vues
  autorisées par requête peut coûter cher si l'analyste peut lire beaucoup de
  grosses collections. À borner en plan — matérialiser seulement les vues
  référencées (découverte via le parseur natif DuckDB), et/ou profiler pour
  décider si (B) est un meilleur compromis. Décision finale au spike.
- **CRS non normalisé pour les collections enregistrées manuellement** (limite
  héritée de SP-11a/b, non résolue) : une vue expose la géométrie telle quelle ;
  une opération spatiale de l'analyste suppose WGS84 et serait incorrecte sur une
  collection à CRS source différent. Documenté, non traité ici.
- **Croissance non bornée du change-log** (héritée de SP-11b) : le scan SQL porte
  sur l'intégralité de l'historique CDC ; le critère ~1 M lignes est un ordre de
  grandeur actuel, pas une garantie à toute échelle. Politique de rétention hors
  périmètre.
- **Connexion DuckDB éphémère par requête** (héritée de SP-11b) : simplicité
  assumée ; à ne remplacer par un pool que si le profilage le justifie (YAGNI).
- **Séparation admin/analyste** : un admin n'étant pas analyste par défaut, un
  déploiement doit penser à peupler `CORE_ANALYST_SUBS` (ou `PATCH /users`) pour
  qu'un humain puisse utiliser la fonctionnalité — compromis assumé au profit de
  la séparation de personas, à documenter dans le README au moment de la
  livraison.
