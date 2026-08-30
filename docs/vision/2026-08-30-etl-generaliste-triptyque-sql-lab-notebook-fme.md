# ETL généraliste et triptyque analytique — SQL Lab / Notebook / FME-like

**Date** : 2026-08-30
**Statut** : proposition de repositionnement conscient, à valider avant tout chantier d'implémentation
**Déclenché par** : l'étude d'intégration du projet finance (`/home/lenen/projets/finance`) comme cas d'usage réel non-géospatial

## 1. Ce que ce document révise

`2026-07-09-brainstorm-geostudio-analytics-platform.md` (vision validée) pousse GeoStudio vers une plateforme complète de Data Viz/Analytics/Decision Support, mais pose explicitement un garde-fou dans sa table des risques (§9) :

> *"Reconstruire Superset en pire (générateur de charts générique sans âme) — ★★ — Le fil rouge est le différenciateur spatial : chaque feature doit servir « voir/comprendre/agir sur un territoire » ; sinon backlog."*
> *"Le mot « Analytics Platform » brouille le positionnement v0.1 — le README v0.1 reste « geospatial app builder » ; l'analytics arrive comme chapitre 2 du récit, pas comme promesse initiale."*

Ce document propose de **rouvrir consciemment ce garde-fou** : accepter que GeoStudio devienne une plateforme de data-analyse généraliste où la cartographie est une capacité parmi d'autres (largement la plus mature aujourd'hui), pas nécessairement le fil rouge de chaque fonctionnalité future. Le risque de dispersion nommé dans le document du 07-09 est réel et reste valable — ce document propose une architecture (§3) conçue spécifiquement pour le contenir plutôt que pour l'ignorer.

Le déclencheur concret de cette reformulation : un projet réel non-géospatial (analyse financière historique personnelle, ~3 000 transactions, ingestion de relevés PDF/OFX bancaires) a servi de cas d'étude pour tester si l'architecture actuelle de GeoStudio pouvait héberger un domaine métier qui n'a rien de spatial. Les sections suivantes en tirent les enseignements.

## 2. État des lieux — ce qui est déjà générique, et ce qui ne l'est pas

Investigation en lecture seule de `core/app/collections/`, `core/app/pipelines/`, `core/app/analytics/`, `core/app/appexport/`, `shell/src/builder/` :

- **Le modèle de collection est déjà geometry-optional en pratique**, pas seulement en théorie : `geometry_column` nullable, cas `None` déjà géré et testé dans l'introspection, l'extent, le DDL, le CRUD (`features/repository.py`), et surtout dans le writer générique du moteur ETL (`pipelines/runtime.py::_write_collection`, `has_geometry` déjà calculé). Une collection purement tabulaire fonctionne aujourd'hui sans changement de cœur, via `register_collection` ou `writer.collection`.
- **Le builder de dashboard et SQL Lab sont déjà agnostiques du domaine.** SQL Lab (`core/app/analytics/sql_sandbox.py`) est en réalité le composant le plus rigoureusement sécurisé du dépôt (§3.1) et n'a aucune dépendance à la géométrie.
- **Le moteur ETL déclaratif (`pipelines/`, l'équivalent FME de SP-15) reste, lui, structurellement fermé et borné** : registre de 17 opérations en dur (`OP_KINDS`/`OP_PARAMS`), aucun mécanisme de code personnalisé (recherche exhaustive de `script`/`udf`/`exec`/`eval` : zéro résultat), aucun reader "fichier déposé" (les trois readers actuels sont tous des connecteurs *pull* contre une source adressable en continu — collection interne, REST, Postgres), déclenchement uniquement par cron (`procrastinate`, balayage périodique des pipelines dus), et un modèle d'audit qui ne descend jamais en dessous du run complet (`PipelineRun`, stats agrégées par nœud).
- **Le SDK de widgets frontend est le seul précédent réel d'extensibilité ouverte** — mais il s'exécute côté navigateur, dans l'onglet d'un seul utilisateur, isolé par error boundary (résilience, pas sécurité). Il ne se transpose pas tel quel à un registre de nœuds exécutés côté serveur, en contexte multi-tenant, avec accès à la session DB — classe de risque différente (fuite cross-tenant possible), pas seulement "plus risqué".

## 3. Architecture proposée — trois espaces complémentaires

### 3.1 SQL Lab (déjà livré, rien à construire)

Exposé en `POST /analytics/sql`, modèle de sécurité en quatre couches indépendantes :

1. Gate AST (`SELECT`/`UNION` uniquement) — filtre précoce, pas la vraie frontière.
2. Scope de tables limité à ce que `can(user, action, object)` autorise (`list_visible_collections`) — seules ces tables sont matérialisées en `TEMP TABLE`.
3. **Verrouillage moteur DuckDB après matérialisation** (`enable_external_access=false`, `lock_configuration=true`) — la vraie frontière, même patron deux-passes que le pipeline.
4. Bornes de ressources : 512 Mo, 2 threads, timeout 10s, 10 000 lignes max.

L'analyste ne touche jamais la table Postgres de production : la requête lit un instantané CDC dédupliqué en GeoParquet, découplé du pool OLTP. Chaque requête est auditée (`write_audit`). Gate de rôle explicite (`user.is_analyst`).

### 3.2 Notebook (à construire — le seul vrai chantier neuf)

N'existe pas aujourd'hui (recherche exhaustive : zéro trace de Jupyter/kernel/papermill). La différence structurante avec SQL Lab n'est pas la sécurité, c'est le **cycle de vie** : SQL Lab est sans état (connexion éphémère par requête) ; un notebook exige une session vivante persistante (état conservé entre cellules, potentiellement des heures) — une catégorie d'infrastructure différente.

Le modèle de menace change favorablement par rapport à un registre de plugins ouvert : un notebook est utilisé par un **analyste authentifié de l'instance**, pas un plugin tiers anonyme. Ça déplace le curseur de "suffisant" vers le bas sur l'isolation syscall : un **conteneur éphémère par session avec de vraies limites cgroups (CPU/mémoire/temps)**, sans gVisor/Kata, devient proportionné — alors que ça aurait été jugé insuffisant pour héberger du code de plugin tiers.

Recommandation : **intégrer un kernel gateway Jupyter existant** plutôt que reconstruire un runtime interactif maison — ce problème précis (session de kernel isolée, adressable, avec état) est déjà résolu par l'écosystème Jupyter, contrairement au reste du moteur ETL qui est volontairement maison. Accès aux données : jamais un DSN Postgres brut — un client Python de première partie pré-importé dans l'environnement du notebook, qui réutilise `list_visible_collections` (lecture) et `features/repository` (écriture, déjà geometry-optional), même discipline que SQL Lab.

### 3.3 FME-like (existant, volontairement gardé borné)

Le registre reste fermé et déclaratif — SQL DuckDB borné + transforms géo/tabulaires + sidecar QGIS allowlisté. **Ne pas** l'ouvrir à du code arbitraire : le sidecar QGIS prouve déjà que le pipeline sait déléguer une étape à un service externe isolé sans exécuter lui-même le code (canal HTTP + volume partagé, avant verrouillage réseau) — un futur nœud "notebook packagé comme job reproductible" suivrait ce même patron, pointé vers le service Notebook plutôt que `qgis-worker`. Pas de nouveau précédent architectural, une réutilisation.

Dans l'autre sens (notebook → pipeline), le pont existe déjà structurellement : un notebook qui écrit dans une collection produit une source immédiatement consommable par n'importe quel `reader.collection` en aval.

**Le principe organisateur** : le risque d'exécution de code générique reste concentré dans un seul composant délibérément conçu pour ça (Notebook, sessions isolées, quotas, reaping), plutôt que dispersé dans le registre de pipeline — qui garde la rigueur qui fait sa valeur actuelle (déclaratif, borné, revu comme du code cœur). C'est la réponse concrète au risque de dispersion nommé en §9 du document du 07-09 : la généricité arrive par un composant dédié et contenu, pas par la dilution du moteur existant.

## 4. Gains à faible risque, indépendants de la décision de positionnement

Identifiés lors de l'investigation, réalisables sans attendre une décision sur le Notebook :

- **Audit par ligne opt-in** sur `writer.collection` (`auditPerRow: bool`) — l'infra `audit_log` est déjà générique et réutilisée partout, ajout purement additif.
- **`reader.storage.object`** pour les formats que DuckDB lit déjà nativement via l'extension `httpfs` (déjà chargée) : CSV/JSON/Parquet depuis MinIO/S3, sans code personnalisé.
- **Extension `fts`** (recherche plein texte DuckDB) — jamais installée, ajout à faible risque pour un usage "texte/documents" léger.
- Agrégats stats et grains temporels — déjà livrés (SP-23), aucun gap.

## 5. Où se situe un service métier non-géospatial (ex. finance) dans cette architecture

SQL Lab et Notebook sont des outils **exploratoires, pilotés par un humain authentifié**, à session bornée. Un besoin d'ingestion de production — parsing récurrent de documents, réconciliation multi-source, moteur de règles versionné avec audit par transaction, tournant **sans surveillance, sur planification, indéfiniment** — ne trouve sa place dans aucun des trois espaces : c'est l'inverse de la forme d'un notebook (session humaine bornée), et SQL Lab est structurellement en lecture seule.

Le patron recommandé pour ce type de besoin reste : **un service Python de première partie, externe au DAG**, qui réutilise ce que la plateforme offre déjà de générique (scheduling `procrastinate`, coffre de secrets, `register_collection` comme unique point de couplage), et dont la production devient une collection comme une autre — consommable ensuite par les trois espaces de ce document pour l'exploration et le dashboard, sans qu'aucun d'eux ne sache comment elle a été produite. Ce patron n'est pas spécifique à la finance : c'est la réponse générale pour tout domaine dont le cœur métier a des exigences (audit fin, exécution non-supervisée) qui dépassent ce qu'un espace analytique interactif est censé offrir.

## 6. Roadmap phasée

```
Déjà acquis         SQL Lab (livré), pont collection → SQL Lab/pipeline (de facto)
Faible risque        audit par ligne opt-in, reader.storage.object (formats httpfs), extension fts
Chantier principal   Notebook : intégration kernel gateway + conteneur éphémère/session + cgroups
                      + client Python de première partie (list_visible_collections / features/repository)
Après stabilisation   pont pipeline → notebook (job reproductible), réplique le patron sidecar QGIS
Hors de ce chantier   tout service métier de production (ex. finance) — avance en parallèle, indépendant,
                      devient utile au triptyque seulement une fois sa collection existe
```

## 7. Risque produit — assumé, pas ignoré

Le risque de dispersion nommé dans le document du 07-09 reste réel : ajouter un Notebook et des readers de fichiers élargit mécaniquement la surface du produit au-delà du géospatial. La réponse de ce document n'est pas de nier ce risque mais de le canaliser : le moteur ETL géospatial existant (FME-like) ne change pas de nature, SQL Lab ne change pas de nature, seul un nouveau composant borné (Notebook) porte l'ouverture vers le générique — avec ses propres garde-fous (sessions, quotas, reaping) plutôt que par affaiblissement des garanties déjà en place ailleurs. La décision de poursuivre reste néanmoins un choix de positionnement produit conscient, pas une conséquence technique automatique de ce qui est faisable.
