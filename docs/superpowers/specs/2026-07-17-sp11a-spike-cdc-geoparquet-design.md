# SP-11a — Spike CDC + réplication PostgreSQL → GeoParquet

Date : 2026-07-17
Statut : validé (brainstorm), en attente de plan

## Contexte

SP-11 (« Lakehouse & CDC », cf. `docs/vision/2026-07-04-feuille-de-route-
geostudio.md` §SP-11, arbitrages A16–A19) fait rejoindre le SIG à la data
platform : PostGIS (chaud) répliqué en continu vers GeoParquet sur MinIO
(froid), interrogé plus tard par DuckDB. C'est un chantier large — CDC vers
GeoParquet, layout + compaction, module analytique DuckDB + API d'agrégation,
endpoint SQL sandbox analyste — que la feuille de route elle-même identifie
comme portant le risque le plus élevé de toute la feuille de route (« le
morceau le plus délicat »), et pour lequel elle recommande explicitement un
**spike de validation en ouverture de phase**.

Comme SP-6, SP-8, SP-9 et SP-10, SP-11 est donc découpé en sous-parties
livrables indépendamment, chacune avec sa spec puis son plan. **SP-11a**
couvre le socle le plus risqué et bloquant pour tout le reste : le mécanisme
CDC lui-même (A16, réplication logique + worker maison) et l'écriture
GeoParquet (A17, format plat + partitionnement). Sans ce socle, ni le module
DuckDB (A18/A19) ni le SQL sandbox analyste n'ont de données froides
fiables à interroger.

Aujourd'hui, aucune brique de ce chantier n'existe : pas de service CDC, pas
de publication PostgreSQL, aucune dépendance GeoParquet/geopandas dans
`core/pyproject.toml`, `docker-compose.yml` ne connaît que `core`/`worker`
comme process applicatifs (PgBouncer en mode `transaction`, incompatible
avec le protocole de réplication logique).

## Objectif de SP-11a

Une écriture PostGIS (via l'API OGC Features du cœur, y compris depuis le
widget Formulaire de SP-4) devient visible en GeoParquet sur MinIO en moins
de 5 minutes, suppressions comprises, avec reprise sur panne sans perte ni
gap — validé d'abord par un **spike de go/no-go**, puis livré comme worker
CDC dédié.

**Hors périmètre** (sous-parties ultérieures de SP-11) : job de compaction
planifié, module analytique DuckDB + API d'agrégation structurée (remplace
l'agrégation client de `queryDataSource`), endpoint SQL read-only sandboxé
réservé au rôle analyste, dashboard/alerte Grafana dédiés au lag CDC
(la donnée existe dès SP-11a via une métrique OTel, cf. §Observabilité, mais
son exploitation dans Grafana suit le patron SP-10b dans une sous-partie
ultérieure).

## Architecture

### Nouveau service `cdc-worker`

Process long-lived dédié dans `docker-compose.yml`, aux côtés de
`core`/`worker` (pas derrière un profil optionnel — au même titre que
`core`/`worker`, c'est un service métier essentiel dès que SP-11 est livré,
pas un outil d'exploitation optionnel comme le profil `observability` de
SP-10b). Isole le risque : un crash du CDC ne touche pas le worker
procrastinate d'ingestion existant.

**Connexion directe à `postgis:5432`**, en contournant PgBouncer. PgBouncer
est configuré en `POOL_MODE: transaction` (`docker-compose.yml`), qui ne
supporte pas le protocole de réplication logique — `cdc-worker` est donc le
seul service à parler directement à `postgis`, tous les autres continuant de
passer par `pgbouncer:6432` (inchangé).

### Extension `wal2json`

Ajoutée à l'image PostGIS custom (`deploy/postgis/Dockerfile`, déjà
personnalisée pour pgvector depuis SP-7 — même style d'incrément de risque
déjà traversé une fois). Émet les changements en JSON (colonnes, valeurs,
type d'opération) — décodage trivial côté worker Python, pas de protocole
binaire (`pgoutput`) à implémenter. Choisi plutôt que `pgoutput` natif car
il n'existe pas de bibliothèque Python cliente mature pour ce protocole hors
libpq ; le coût d'ajouter une extension à une image déjà personnalisée est
jugé inférieur au risque d'écrire un décodeur binaire.

### Publication et slot

- **Une publication unique** `geostudio_cdc`, tenue à jour dynamiquement :
  l'enregistrement d'une collection (admin, SP-3a, ou automatique via
  l'ingestion SP-6a/6b) ajoute sa table via `ALTER PUBLICATION geostudio_cdc
  ADD TABLE <schema>.<table>` ; le désenregistrement d'une collection (SP-9)
  la retire (`DROP TABLE` de la publication — la table PostGIS elle-même
  survit, comportement inchangé, seule la réplication s'arrête).
- **Un seul slot de réplication logique**, créé de façon idempotente au
  démarrage du worker s'il n'existe pas déjà (plugin `wal2json`).
- Toutes les collections enregistrées rejoignent automatiquement la
  publication (pas d'opt-in par collection) — cohérent avec le critère
  d'acceptation SP-11 (« une écriture PostGIS ») qui ne mentionne aucune
  activation manuelle, et évite un oubli qui laisserait une écriture
  invisible côté froid.

## Flux de données

### Backfill initial (par collection)

- **Démarrage à froid du worker** (création du slot) : PostgreSQL permet
  d'exporter un snapshot cohérent au moment exact de la création du slot
  (`CREATE_REPLICATION_SLOT ... EXPORT_SNAPSHOT`). Le backfill lit ce
  snapshot pour toutes les collections déjà enregistrées à cet instant, puis
  le flux continu prend le relais sans gap ni chevauchement.
- **Collection enregistrée après coup** (slot déjà existant) :
  `ALTER PUBLICATION ADD TABLE` ne fait entrer la table dans le flux qu'à
  partir de maintenant — aucun historique. Un backfill dédié de cette table
  est donc déclenché juste après l'ADD TABLE, avec la même exigence de
  cohérence (bornage par une transaction/LSN connu, pour ne dupliquer ni
  rater les lignes autour de la bascule).

### Flux continu

Le worker consomme les messages `wal2json` (insert/update/delete),
bufferise en mémoire, et flush vers MinIO **toutes les ~30s ou tous les N
changements** (le premier seuil atteint) — borne la fraîcheur bien sous les
5 min de la SLO et limite le nombre de petits fichiers (la compaction de ces
petits fichiers reste hors périmètre, cf. §Objectif).

### Reprise sur panne — idempotence plutôt qu'exactly-once

Le worker n'envoie son feedback de position (`confirmed_flush_lsn`,
mécanisme natif du protocole de réplication logique, **persisté par
PostgreSQL lui-même** — pas de table de checkpoint applicative séparée)
qu'**après** l'écriture réussie du flush sur MinIO. Un crash entre écriture
et feedback rejoue donc certains changements au redémarrage (*at-least-once*,
jamais de perte). Chaque ligne écrite porte son LSN d'origine (`_lsn`) ; les
lecteurs (DuckDB, sous-partie ultérieure) réduisent par `(pk, max(_lsn))`
pour obtenir l'état courant — les doublons de replay sont donc inoffensifs
sans nécessiter de déduplication à l'écriture.

Un `ALTER TABLE` sur une collection suivie déclenche un re-backfill complet
de cette collection (assumé par la feuille de route — pas d'évolution de
schéma incrémentale en v1).

## Format de sortie

### Layout / partitionnement (convention A17)

```
s3://<bucket>/cdc/tenant_id=<tenant>/collection_id=<collection>/dt=<YYYY-MM-DD>/part-<uuid>.parquet
```

Chaque fichier est un lot de changements — **append-only change log**, pas
un état déjà fusionné. Colonnes : les colonnes métier de la table source +
`_op` (`insert`/`update`/`delete`), `_lsn`, `_ts` (horloge murale d'écriture
du flush). Une ligne `delete` est une **tombstone** : clé primaire +
`_op="delete"` uniquement, pas les autres colonnes — suffisant car
`REPLICA IDENTITY` par défaut n'expose que la PK sur delete (pas besoin de
`REPLICA IDENTITY FULL`).

### Géométrie

Écrite en GeoParquet 1.0 conforme (métadonnées `geo` standard, colonne WKB)
via **geopandas** (nouvelle dépendance `core/pyproject.toml` —
`GeoDataFrame.to_parquet` gère nativement les métadonnées GeoParquet ;
s'appuie sur `shapely`, déjà présent). Pas de reprojection forcée : le CRS
de la colonne source est préservé tel quel et documenté dans les métadonnées
GeoParquet. Limite assumée : les collections issues de l'ingestion SP-6a/6b
sont déjà normalisées en WGS84, mais ce n'est pas garanti pour une
collection enregistrée manuellement (SP-3a) — non traité par cette
sous-partie.

## Observabilité

`ObservableGauge` `geostudio.cdc.lag_seconds` (même patron que
`geostudio.jobs.backlog` de SP-10b), attribut `collection_id` — écart entre
l'horloge murale et `_ts` du dernier changement flushé. Export OTLP
inconditionnel comme `core`/`worker` (SP-10a/SP-10b : silencieux si aucun
collecteur n'écoute). Aucun dashboard ni règle d'alerte Grafana dans cette
sous-partie — la donnée est exportée, son exploitation suit dans une
sous-partie ultérieure de SP-11 alignée sur le patron SP-10b.

## Tests

- **Spike (go/no-go, tâche d'ouverture du plan)** : script empirique
  (`scripts/spike_cdc_replication.py`, même patron que
  `spike_pgbouncer_rls.py` de SP-3b) contre un PostGIS jetable réel — pas en
  isolation. Valide : création du slot avec `wal2json` ; insert/update/delete
  décodés correctement sur une table avec colonne géométrie ;
  `ALTER PUBLICATION ADD TABLE` dynamique pendant que le slot existe déjà ;
  un cycle crash-simulé/redémarrage confirmant le rejeu idempotent sans gap.
  Si un de ces points échoue durement, le plan s'arrête avant d'investir dans
  le worker complet (cf. §Risques).
- **Automatisé (core, marqueur `postgis`)** : gestion de la publication
  (ajout/retrait de table au register/unregister d'une collection), lecture
  du gauge de lag via `InMemoryMetricReader` (même patron que SP-10a/b),
  écriture GeoParquet (schéma, colonnes `_op`/`_lsn`/`_ts`, tombstone
  correcte) contre un backend de test.
- **Empirique de bout en bout** : écrire une feature via l'API OGC Features
  → la retrouver en GeoParquet sur MinIO en < 5 min, y compris pour une
  suppression (tombstone présente, pas de ligne fantôme dans une réduction
  `max(_lsn)`).

## Critères d'acceptation

1. Une écriture PostGIS (formulaire SP-4 ou API Features) est visible en
   GeoParquet en < 5 min, suppressions comprises.
2. Une collection enregistrée après le démarrage du worker est backfillée
   puis suivie en continu, sans intervention manuelle.
3. Un redémarrage du worker après un arrêt brutal reprend sans perte (au pire
   quelques doublons inoffensifs pour un lecteur qui réduit par
   `max(_lsn)`).
4. `geostudio.cdc.lag_seconds` est exporté par collection.
5. `docker compose up` (par défaut, sans flag) démarre `cdc-worker` comme les
   autres services métier — aucune régression sur `core`/`worker`/le reste de
   la stack.

## Risques

- Le CDC est explicitement « le morceau le plus délicat de la feuille de
  route » — mitigé par le spike de go/no-go en ouverture de plan, avant tout
  investissement dans le worker complet.
- `wal2json` ajoute une extension à l'image PostGIS custom : à vérifier
  qu'elle compile proprement dans `deploy/postgis/Dockerfile` (même style de
  risque que pgvector en SP-7, déjà traversé une fois).
- Slot de réplication qui gonfle le WAL si le worker s'arrête longtemps sans
  consommer — la seule garde en place dans cette sous-partie est le gauge de
  lag ; pas d'auto-drop de slot ni d'alerte dédiée en v1 (assumé, une
  intervention manuelle reste possible ; l'alerte suit dans une sous-partie
  ultérieure avec le dashboard).
- CRS non normalisé pour les collections enregistrées manuellement (cf.
  §Format de sortie) — limite documentée, non traitée par ce spike.
- `cdc-worker` actif par défaut dès `docker compose up` introduit un nouveau
  mode de panne possible (slot qui gonfle) sur tout déploiement, y compris
  ceux qui n'utilisent pas encore l'étage analytique — compromis assumé
  (cohérence avec `core`/`worker` comme services métier non-optionnels)
  plutôt qu'une activation par profil.
