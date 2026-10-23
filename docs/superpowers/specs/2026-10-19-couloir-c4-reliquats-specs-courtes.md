# Couloir C (4e mission) — specs courtes des reliquats non exécutés

Date : 2026-10-19. Complète `docs/revue/audit-2026-10-16/101-reliquats-L-cadrage.md`. Chaque
section dit ce qui est livré (relu dans le code, piège n°12), ce qui reste, et le modèle retenu.

## AUD-014 — lecture en flux (livré, décision d'atomicité maintenue)

Relecture : `_open_rows` parcourait déjà le fichier en deux passes en flux et insérait par lots
(CSV, JSONL, GeoJSON, Parquet tabulaire). Restaient trois lecteurs qui matérialisaient tout :
OGR (`pyogrio.raw.read` de la couche entière), GeoParquet (`gpd.read_parquet` + `iterrows`),
XML générique (DOM complet). Livré : fenêtres de `_BATCH_ROWS` (10 000) pour OGR et GeoParquet,
`iterparse` + deux passages pour le XML (le premier trouve le parent répété avec la règle BFS de
l'ancien code, le second émet les enregistrements et retire du parent tout ce qui est fermé).

Décision : l'import reste **atomique** (une transaction, rien de partiel). L'import par lots
reprenables exigerait un état de reprise (curseur par job) et une table de transit ; hors lot.
Reste : `content: bytes` est encore l'objet lu en entier depuis S3 (le pic ne dépend plus du
nombre d'entités mais de la taille du fichier compressé) ; passer le téléchargement S3 en
`SpooledTemporaryFile` + parseurs prenant un chemin est la suite naturelle (M, risque modéré :
`_temp_file` valide signature et suffixe sur des octets).

## AUD-099 — pré-agrégation, cache, backfill, index

Relecture : le cache d'agrégat existait (`_result_cache`, clé = fichiers du lac + requête +
champs masqués) et le `statement_timeout` de `rls_scope` aussi (`CORE_DB_STATEMENT_TIMEOUT_MS`).
Livré : backfill CDC en flux (curseur serveur `stream_results`, segments de 50 000 lignes),
créneaux d'agrégat par tenant (4 par processus, attente 10 s, puis 429 + `Retry-After`).
Cache de tuiles : non fait (la clé doit inclure le rôle effectif et les limites géographiques,
sinon fuite entre `rls_scope` ; à concevoir avec un invalidateur de compaction).

**Index d'attribut déclaratifs (non fait, spec)** : table `collection_indexes`
`(id, tenant_id, collection_id, field, kind btree|trgm, status pending|ready|failed, error)`,
migration 0181 ; `POST/DELETE /v1/collections/{id}/indexes` sous `admin.collections.manage` ;
job procrastinate qui exécute `CREATE INDEX CONCURRENTLY` hors transaction (connexion
`autocommit`), nom dérivé du champ validé contre le schéma, plafond de 8 index par collection,
audit `collection.index_create`. Surfaces à inventorier : 2 routes REST, 1 route shell
(onglet de la collection). Risque : `CONCURRENTLY` laisse un index invalide en cas d'échec
(le job le supprime et passe `failed`).

## AUD-029 — arrêt d'un code Python bloquant en cours de nœud (non fait)

Python ne sait pas interrompre GEOS/GDAL dans un fil. La seule solution fiable est d'exécuter
chaque nœud non DuckDB dans un **sous-processus** (`multiprocessing` spawn, échange par IPC
Arrow du seam `pipelines/exchange.py`) tué à l'annulation ou à la durée maximale. Coût : le
démarrage (~150 ms par nœud, à amortir par nœud « lourd » seulement via un indicateur
`isolated` sur `OperationContract`), la mémoire doublée sur le passage de données, les secrets
(le sous-processus ne reçoit que le contexte résolu). Effort L ; à lancer comme SP à part.

## AUD-059 — cross-filter multi-entrées

Livré dans ce couloir : la comparaison de périodes (indicateur, graphique) garde les filtres
propres de la source d'origine (avant : requête synthétique à `query: {}`). Les autres points
de l'AUD (pivot, fenêtre chevauchante, widget Période) étaient déjà livrés.

**Modèle retenu pour le cross-filter multi-entrées (non fait)** : aujourd'hui
`crossFilter: Record<datasetId, CrossFilterEntry>` — une entrée par dataset, la dernière
sélection écrase la précédente. Cible : `Record<datasetId, Record<originSourceId,
CrossFilterEntry>>`, donc une entrée par widget émetteur ; `derivePatch` applique toutes les
entrées dont l'origine diffère de la source lue, ET entre champs distincts, OU intra-champ
(valeurs d'un même widget). Changements : `AnalyticsContext` (`setCrossFilter` clé
`(datasetId, originSourceId)`), `derivePatch` (boucle sur les entrées), `Bookmark.crossFilter`
côté cœur (`dict[str, BookmarkCrossFilterEntry]` devient `dict[str, dict[str,
BookmarkCrossFilterEntry]]`, lecture tolérante de l'ancienne forme, migration de lecture sans
SQL), `CrossFilterLinkEditor` inchangé. Risque : collision de deux entrées sur le même champ
(la plus récente gagne, documenté) ; contrat `Bookmark` à versionner.

## AUD-115 c — DCAT multilingue, RTL

XLSForm : livré (`labels`/`hints` par langue `fr`/`en` conservés dans les champs de formulaire,
affichés selon la langue active ; langues hors fr/en toujours « ignorées » au rapport). DCAT
`dct:title@en` : dépend de D8 (contenu utilisateur traduisible, décision de Tanguy) ; RTL :
décision requise (chantier CSS propre), non entrepris.
