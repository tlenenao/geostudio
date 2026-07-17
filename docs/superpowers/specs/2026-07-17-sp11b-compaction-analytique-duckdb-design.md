# SP-11b — Compaction GeoParquet + module analytique DuckDB

Date : 2026-07-17
Statut : validé (brainstorm), en attente de plan

## Contexte

SP-11a (`docs/superpowers/specs/2026-07-17-sp11a-spike-cdc-geoparquet-design.md`)
livre le socle CDC : un worker dédié réplique PostGIS (chaud) vers un
change-log GeoParquet append-only sur MinIO (froid), partitionné
`tenant_id=<t>/collection_id=<c>/dt=<date>/part-<uuid>.parquet`, colonnes
métier + `_op`/`_lsn`/`_ts`. Le lecteur reconstitue l'état courant par
réduction `(pk, max(_lsn))`, les tombstones (`_op="delete"`) portant
uniquement la clé primaire. Cette sous-partie était en cours d'exécution
(tâches 1–6 sur 11 livrées) au moment d'écrire cette spec — sans incidence
sur son contenu, qui ne touche à rien de ce que SP-11a a déjà posé.

SP-11 (feuille de route, arbitrages A17–A19) prévoit ensuite, dans cet
ordre logique : le job de compaction (complète A17), le module analytique
DuckDB + API d'agrégation structurée (A18/A19, remplace l'agrégation
client actuelle de `queryDataSource`), puis l'endpoint SQL sandbox réservé
au rôle analyste (deuxième moitié d'A19). **SP-11b** couvre les deux
premiers morceaux ensemble plutôt que successivement : le CDC flush
toutes les ~30s ou N changements (SP-11a) accumule vite, sur une
collection à forte écriture, des centaines de petits fichiers Parquet par
jour ; sans réduction de ce nombre de fichiers, l'API d'agrégation lirait
via `httpfs` un fichier par `GET` MinIO et son critère de performance
(~1 M lignes < 2 s) ne serait vérifiable que sur un scénario artificiel
(un seul gros backfill, jamais un flux CDC prolongé réaliste). La
compaction est donc traitée comme un prérequis de cette sous-partie, pas
une sous-partie séparée.

Aujourd'hui, `core/pyproject.toml` ne dépend pas de `duckdb` et aucun
module analytique n'existe. Le client (`shell/src/api/itemClient.ts`)
agrège déjà les statistiques **côté client** : `queryDataSource` fetch les
features brutes d'une collection (`GET /collections/{id}/items`) puis, si
`DataSource.type === "statistics"`, les réduit en mémoire via
`aggregateRecords` (group-by/measures/pivot `split`, agrégats
`count`/`sum`/`avg`/`min`/`max`) — consommé par les widgets Graphique
(`chart.tsx`) et Indicateur (`indicator.tsx`) via `DataContext.tsx`. C'est
ce chemin que SP-11b déplace côté serveur.

## Objectif de SP-11b

Un widget Graphique ou Indicateur agrège les données d'une collection via
une nouvelle API du cœur — DuckDB in-process interrogeant le GeoParquet
CDC — au lieu de fetcher les features brutes et d'agréger côté client :
~1 M lignes agrégées en < 2 s, fraîcheur ≤ 5 min (SLO CDC inchangé,
aucune nouvelle notion de fraîcheur introduite). Une collection à fort
volume d'écriture reste performante grâce à un job de compaction qui
réduit périodiquement le nombre de fichiers Parquet par partition, sans
jamais changer la sémantique de change-log ni risquer de perte de données.

**Hors périmètre** (sous-parties ultérieures de SP-11) : endpoint SQL
read-only sandboxé réservé au rôle analyste (deuxième moitié d'A19, qui
n'existe pas encore comme rôle distinct dans `core/app/users`) ;
dashboard/alerte Grafana dédiés (patron SP-10b, sur une métrique de
performance/fraîcheur de l'agrégation si elle s'avère utile) ; outil MCP
d'agrégation (REST-only pour cette sous-partie — pas de besoin agent
identifié, à réévaluer si un besoin concret émerge) ; DuckDB-WASM
navigateur (A18, différé explicitement par la feuille de route, deuxième
étage après stabilisation du serveur) ; toute forme d'analytique
temporelle/historique (l'API n'expose que l'état courant, pas de
requête « point-in-time » sur le change-log — hors scope produit à ce
stade) ; politique de rétention/archivage du change-log (le GeoParquet
CDC grossit indéfiniment, cf. §Risques).

## Architecture

### Job de compaction (`app/cdc/compaction.py`, nouveau)

Tâche planifiée `procrastinate` (périodique, ex. toutes les ~10–15 min
par collection suivie par le CDC — fréquence exacte à affiner en plan
selon le coût mesuré) qui réduit le nombre de fichiers Parquet d'une
partition `tenant_id=/collection_id=/dt=` **sans changer la sémantique du
change-log** : mêmes colonnes `_op`/`_lsn`/`_ts`, toujours append-only,
aucune déduplication ni suppression de tombstone à l'écriture — la
réduction à l'état courant reste entièrement à la charge du lecteur (le
module analytique, cf. ci-dessous), pas de la compaction. C'est le choix
retenu (« approche A », fusion pure) plutôt qu'un snapshot d'état courant
matérialisé (« approche B ») : une seule notion de fraîcheur (le SLO CDC
existant), pas de nouvelle surface à faire vieillir ni de second SLO à
définir.

**Algorithme** : pour chaque partition avec plus d'un fichier éligible,
lire tous les fichiers éligibles avec geopandas, les concaténer, écrire
un unique fichier fusionné (nouveau `part-<uuid>.parquet`), puis supprimer
les fichiers d'entrée. **Seuil de taille** : seuls les fichiers en dessous
d'un seuil (ex. 32 Mo, paramétrable) sont éligibles à la fusion — un
fichier déjà volumineux (issu d'un backfill ou d'une fusion précédente)
n'est jamais re-fusionné. Sans ce seuil, chaque cycle relirait et
réécrirait l'intégralité de l'historique du jour, un coût qui grossirait
au fil de la journée ; avec le seuil, le coût par cycle reste borné aux
seuls petits fichiers accumulés depuis le dernier passage.

**Sûreté à l'interruption** (même style de raisonnement que la reprise sur
panne du consumer en SP-11a) : le fichier fusionné est **toujours écrit
avant** la suppression des fichiers d'entrée, jamais l'inverse. Un crash
entre l'écriture et la suppression laisse des données dupliquées (fusion
+ originaux) sur le disque — inoffensif, car le lecteur réduit par
`(pk, max(_lsn))` : des lignes dupliquées ne changent pas le résultat,
elles ne font que ralentir légèrement la lecture jusqu'au prochain cycle
de compaction qui les nettoiera. Un crash qui laisse une suppression
partielle (certains fichiers d'entrée supprimés, d'autres non) est
similairement inoffensif pour la même raison. Aucun verrou ni coordination
avec le worker CDC n'est nécessaire : de nouveaux fichiers peuvent
apparaître pendant un cycle de compaction, ils seront simplement traités
au cycle suivant.

### Module analytique (`core/app/analytics/`, nouveau)

Nouvelle dépendance `duckdb` (`core/pyproject.toml` + `core/Dockerfile` +
`uv.lock`, même discipline que `pyogrio`/`pyarrow` en SP-6b/SP-11a).
Connexion DuckDB **in-process, éphémère par requête** (ouverte, extensions
`httpfs`+`spatial` chargées — installées une fois sur le disque de
l'image, `LOAD` rapide à chaque requête —, credentials S3/MinIO réutilisés
tels quels depuis la config déjà utilisée par `app.ingestion.storage`/
`app.cdc.storage`, fermée en fin de requête). Pas de pool ni de connexion
partagée entre requêtes concurrentes dans cette sous-partie — simplicité
d'abord, le coût de chargement des extensions (dizaines de ms) est
négligeable face au budget de 2 s ; à revisiter seulement si le
profilage en plan montre que c'est un goulot réel.

**Requête** : `read_parquet(glob, hive_partitioning=true)` scopé
strictement à `tenant_id=<tenant courant>/collection_id=<id demandé>`
(jamais un glob plus large — l'isolation tenant est portée par le chemin,
pas par une RLS Postgres qui n'existe pas côté fichiers). Réduction à
l'état courant par fenêtre SQL :
`QUALIFY row_number() OVER (PARTITION BY <pk> ORDER BY _lsn DESC) = 1`,
puis exclusion des lignes `_op = 'delete'`. Puis, dans cet ordre : filtres
attributaires (égalité, mêmes clés que les query params déjà acceptés par
`GET /items`), filtre spatial bbox simple (`ST_Intersects` sur la colonne
géométrie WKB via l'extension `spatial`), puis `GROUP BY`/mesures
(`count`/`sum`/`avg`/`min`/`max`, plusieurs mesures ou un pivot `split` —
même vocabulaire que `DataSource.query` côté shell aujourd'hui).

### Endpoint `POST /collections/{collection_id}/aggregate`

**POST** (pas GET) car le corps porte une structure plus riche qu'une
liste de query params : `groupBy`, `split` optionnel, `measures` (liste
`{field?, agg, label?}`) ou `{agg, field}` unique, filtres attributaires
(objet clé/valeur), `bbox` optionnel. Même porte d'autorisation que
`GET /collections/{id}/items` — `can(user, "read", collection)`, aucun
nouveau modèle de permission, réponses 403/404 cohérentes avec le reste de
l'API Features. Réponse : tableau de lignes larges (une par catégorie de
`groupBy`, une colonne par série) — **exactement la forme que produit
`aggregateRecords` aujourd'hui côté client**, pour que la migration shell
soit un simple changement de source de données, pas un changement de
contrat.

### Migration shell

`queryDataSource` (`shell/src/api/itemClient.ts`) : pour
`DataSource.type === "statistics"`, appelle le nouvel endpoint au lieu de
fetcher `/items` puis d'agréger en mémoire. `aggregateRecords` et
`reduceValues`/`measureLabel` (code mort après migration, `itemClient.ts:
84-165`) sont supprimés. `chart.tsx`/`indicator.tsx`/`DataSourcePanel.tsx`
inchangés : même forme de `DataSource.query` côté auteur, même forme de
résultat `DataRecord[]` côté widget. `DataContext.tsx` (câblage React
Query) change seulement l'appel réseau sous-jacent, pas sa forme
publique.

## Tests

- **Compaction** (`core/tests/test_cdc_compaction.py`, marqueur non
  nécessairement `postgis` — pas de dépendance Postgres directe, juste
  S3/MinIO) : fusion de plusieurs petits fichiers en un seul (contenu
  identique après réduction `max(_lsn)`), fichier déjà volumineux non
  re-fusionné (seuil respecté), tolérance à une interruption simulée
  (fichiers dupliqués laissés en place → résultat de lecture inchangé).
- **Module analytique** (marqueur `postgis` pour la partie autorisation
  qui touche `can()`/la DB ; fixtures Parquet écrites directement sur un
  MinIO de test, même patron que les tests `app.cdc`) : réduction état
  courant correcte (dernière version gagne, tombstone exclue), filtre
  attributaire, filtre bbox, group-by simple et avec `split`/mesures
  multiples, comportement sur collection vide/absente.
- **Empirique de bout en bout** : script de mesure de performance (même
  esprit que `core/scripts/measure_cdc_consumer_throughput.py` déjà
  présent pour SP-11a) générant ~1 M lignes réparties sur plusieurs
  fichiers réalistes (backfill + petits flushes incrémentaux, pas un seul
  gros fichier artificiel), validant le critère < 2 s avant **et** après
  un cycle de compaction — la performance ne doit pas dépendre d'un
  scénario favorable non représentatif.
- **E2E shell** : les specs existantes sur les widgets Graphique/Indicateur
  continuent de passer contre un mock de `POST /collections/{id}/
  aggregate` au lieu du mock `/items` + agrégation — pas de nouvelle spec
  dédiée attendue si la forme de résultat est bien préservée (à confirmer
  en plan).

## Critères d'acceptation

1. Un job de compaction réduit le nombre de fichiers Parquet d'une
   partition à forte écriture, sans perte ni incohérence du résultat lu
   (identique avant/après compaction).
2. Un widget Graphique ou Indicateur agrège ~1 M lignes en < 2 s via
   `POST /collections/{id}/aggregate`, mesuré sur un scénario de données
   réparti sur plusieurs fichiers (backfill + flux incrémental), pas sur
   un unique fichier artificiellement compact.
3. Une collection non autorisée pour l'utilisateur courant est refusée
   par le nouvel endpoint, cohérent avec `GET /items`.
4. `aggregateRecords` (agrégation client) est supprimé ; `queryDataSource`
   migré ; aucune régression sur les specs E2E des widgets Graphique/
   Indicateur.
5. La fraîcheur des résultats agrégés reste bornée par le seul SLO CDC
   existant (≤ 5 min) — aucune nouvelle notion de fraîcheur introduite par
   la compaction.

## Risques

- **Compatibilité DuckDB spatial ↔ GeoParquet écrit par geopandas** :
  non vérifiée à ce stade (geopandas/pyarrow d'un côté, extension
  `spatial` de DuckDB de l'autre — deux implémentations indépendantes de
  la spec GeoParquet). Recommandé : une validation empirique courte en
  tâche d'ouverture du plan (lire un fichier réel produit par SP-11a
  depuis DuckDB, vérifier que `ST_Intersects` fonctionne sur la colonne
  WKB), avant d'investir dans le module complet — même logique de spike
  que SP-11a, mais plus légère (un point technique isolé, pas tout le
  mécanisme CDC).
- **CRS non normalisé pour les collections enregistrées manuellement**
  (limite héritée de SP-11a, non résolue) : un filtre bbox suppose WGS84 ;
  une collection avec un CRS source différent produirait un filtrage
  spatial incorrect. Non traité par cette sous-partie.
- **Croissance non bornée du change-log** : la compaction réduit le nombre
  de fichiers, pas le volume total de données (aucune purge/rétention).
  Le critère de performance (~1 M lignes) est un ordre de grandeur actuel,
  pas une garantie à toute échelle de déploiement — une politique de
  rétention/archivage reste à définir si le volume dépasse ce qui est
  raisonnable pour un scan DuckDB, hors périmètre ici.
- **Connexion DuckDB éphémère par requête** : simplicité assumée au prix
  d'un coût de chargement d'extensions à chaque appel ; à mesurer en plan,
  et à ne remplacer par un pool/connexion partagée que si le profilage le
  justifie réellement (YAGNI).
- **Absence de coordination entre compaction et écriture concurrente** :
  assumée sûre par construction (cf. §Architecture, sûreté à
  l'interruption) — mais dépend strictement de l'ordre écriture-puis-
  suppression ; toute évolution future de la compaction doit préserver cet
  ordre.
