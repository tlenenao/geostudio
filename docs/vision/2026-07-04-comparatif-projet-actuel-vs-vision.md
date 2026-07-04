# Comparatif — Projet actuel vs « Plateforme WebGIS nouvelle génération »

> Analyse comparative entre l'état réel du dépôt `gis-project` (branche `dev`, ~200 commits,
> 2026-07-04) et le document d'exploration
> [`2026-07-04-plateforme-webgis-nouvelle-generation.md`](./2026-07-04-plateforme-webgis-nouvelle-generation.md)
> (ci-après « la Vision »).
>
> Objectif : mesurer les convergences et les écarts, puis **orienter la suite** —
> adaptation du projet actuel ou construction d'un nouveau projet.
> Statut : document d'aide à la décision. Se termine par les questions à trancher.

---

## Sommaire

1. [Les deux objets comparés](#1-les-deux-objets-comparés)
2. [Synthèse en un tableau](#2-synthèse-en-un-tableau)
3. [Comparaison détaillée par domaine](#3-comparaison-détaillée-par-domaine)
4. [Les quatre briques différenciantes (addendum §13)](#4-les-quatre-briques-différenciantes)
5. [Bilan : actifs réutilisables, actifs en tension, absents](#5-bilan--actifs-réutilisables-actifs-en-tension-absents)
6. [**Orientation : adapter ou reconstruire**](#6-orientation--adapter-ou-reconstruire)
7. [Recommandation](#7-recommandation)
8. [Questions pour orienter le projet](#8-questions-pour-orienter-le-projet)

---

## 1. Les deux objets comparés

### 1.1 Le projet actuel — trois couches d'âge différent

Le dépôt n'est pas un objet homogène ; il superpose trois générations de travail :

**Couche 1 — le corpus d'études (« stack FOSS4G »).**
`synthese.md`, `stacks-comparatif.md`, `stacks-production.md`, `stack3-modern-web-gis.md`,
`IMPLEMENTATION_PLAN.md` (8 phases, prérequis 16 vCPU / 32 Go RAM) : démonstration qu'un
**assemblage** de briques open source (GeoServer, GeoNode, Superset, Airflow…) peut
égaler ArcGIS Enterprise. Logique de *catalogue de composants*.

**Couche 2 — l'étude produit OGE (`plateforme-modulaire.md`).**
Passage du catalogue à *un produit* : noyau `GeoCore` + modules enfichables. Première
prise de conscience que « un assemblage de briques n'est pas un produit ». Restée à
l'état d'étude — rien du noyau GeoCore n'est implémenté.

**Couche 3 — le produit en développement réel : GeoStudio.**
C'est là que vivent les ~180 commits de développement effectif :

| Composant | État réel |
|---|---|
| `shell/` — front React 19 + Vite + TS | 72 fichiers source, 56 fichiers de tests unitaires (Vitest), 13 specs E2E Playwright |
| Pages | Catalogue, détail d'item, éditeur de carte, builder d'apps, runtime d'app publié |
| Moteur builder | Grille responsive drag-drop, registre de widgets + SDK, data sources déclaratives, bus d'actions, variables, multi-pages + navigation, thèmes (CSS variables), templates de départ, publication/partage, miniatures |
| Widgets | Carte (MapLibre + deck.gl), Texte, Image, Bouton, Liste/Table, Indicateur, Filtre, Graphiques (ECharts : barres, lignes, jauge, boxplot…), Navigation, widget d'exemple SDK-only (Compteur) |
| `builder-service/` — FastAPI + SQLAlchemy | CRUD de configs JSON **versionnées avec révisions et rollback**, validation de schéma, adaptateur d'items GeoNode (HTTP réel ou stub) |
| Infra (`docker-compose.yml`) | 13 services : PostGIS 16/3.4, PgBouncer, Redis, MinIO, Martin, TiTiler, pg_featureserv, Superset, **GeoNode 4.2**, Keycloak 24, Traefik, builder-service, shell |
| Données | `sql/init.sql` : tables de démo (communes, POI, incidents) + vues matérialisées MVT ; script `generate-pmtiles.sh` |

Le modèle de contenu (items, métadonnées, partage privé/groupe/public, identité) est
**délégué à GeoNode** ; Keycloak porte l'OIDC ; le shell consomme GeoNode API v2,
Martin, pg_featureserv et le builder-service.

### 1.2 La Vision — une plateforme « feuille blanche 2026 »

Résumé en une phrase : **la couche géospatiale de la data platform moderne**, construite
comme un *monolithe modulaire* unique (catalogue STAC, identité/politiques, OGC API,
builder, partage, MCP) + workers de jobs + streaming optionnel, sur exactement deux
systèmes d'état (PostGIS + S3), formats cloud-native (GeoParquet, COG, PMTiles),
architecture AI-native (MCP, tout déclaratif), temps réel progressif, quatre profils de
déploiement dont un **Solo : `docker compose up` < 5 min sur 4 vCPU / 8 Go**, sécurité
OIDC + multi-tenant + ReBAC + RLS spatiale, exploitation GitOps + OpenTelemetry. Quatre
briques différenciantes en addendum : workflows durables, versionnement de données façon
Git, agent runtime, app builder niveau Retool.

### 1.3 Le constat de fond

Le projet actuel et la Vision ne divergent pas sur la *destination* (alternative ouverte
à ArcGIS, builder unifié, formats ouverts) mais sur la **stratégie de construction** :

- Le projet actuel = **assembler des produits tiers existants** et bâtir la couche
  création (GeoStudio) par-dessus. GeoNode y joue le rôle de portail/catalogue.
- La Vision = **bâtir un cœur maison minimal** et n'utiliser des tiers que comme
  bibliothèques ou services satellites (Martin, QGIS Server print, Keycloak). GeoNode,
  Superset, GeoServer y sont précisément ce qu'on **supprime** (fédération de
  quasi-produits, rite de publication, empreinte).

Fait remarquable : la partie la plus développée du projet actuel (le builder
config-driven à runtime unique, configs JSON versionnées) est **exactement** la colonne
vertébrale du §5 de la Vision. Le projet a, sans le formuler ainsi, déjà construit une
bonne part de « l'an 2 » de la trajectoire de la Vision — tout en reposant sur une
fondation (couches 1–2) que la Vision invalide.

---

## 2. Synthèse en un tableau

Légende : ✅ conforme à la Vision · 🟡 partiel / en tension · ❌ absent · ⛔ contradiction structurelle

| Domaine (§ Vision) | Vision | Projet actuel | Verdict |
|---|---|---|---|
| Vision produit (§1) | Couche géospatiale de la data platform, consommateur métier d'abord | « Alternative à ArcGIS » par assemblage ; personas non hiérarchisés | 🟡 |
| Architecture (§2) | Monolithe modulaire + workers ; 2 systèmes d'état ; test « VM 8 Go » | 13 conteneurs hétérogènes (Django, Java-like, Python, Node…) ; 16–32 Go requis ; pas de workers/jobs | ⛔ |
| Données chaudes (§3) | PostGIS, OGC API Features, CDC | PostGIS ✅, pg_featureserv (OGC API Features lecture) 🟡, pas de CDC | 🟡 |
| Données froides / lakehouse (§3) | GeoParquet/Iceberg, COG, PMTiles sur S3, DuckDB, FlatGeobuf | MinIO présent, TiTiler (COG) présent, un script PMTiles ; **aucun** GeoParquet/DuckDB/Iceberg | ❌ |
| Catalogue (§3) | STAC + DCAT, « référencer ≠ copier » | Catalogue GeoNode (ResourceBase, rite de publication) | ⛔ |
| Recherche sémantique (§3/§6) | pgvector, hybride BM25+vecteur+spatial | Absente | ❌ |
| Cartographie (§4) | MapLibre + style spec + Martin/PMTiles + deck.gl + 3D Tiles | MapLibre ✅ Martin ✅ deck.gl ✅ ; styles non traités comme artefacts ; pas de 3D Tiles ; PMTiles non servi | ✅/🟡 |
| Builder & runtime unique (§5) | Un `AppConfig` déclaratif, un `AppRenderer`, modes édition/aperçu/exécution | **Implémenté** : moteur maison, configs versionnées + rollback, templates, publication | ✅ |
| SDK & plugins (§5) | Web Components, plugins ES sandboxés + manifeste permissions, marketplace | SDK React in-app (registre runtime), pas de chargement dynamique externe, pas de sandbox ni marketplace | 🟡 |
| IA (§6) | MCP natif, copilotes, gouvernance agents, modèles enfichables | Rien | ❌ |
| Temps réel (§7) | SSE natif → NATS activable ; alertes transversales | Rien (Redis présent mais inutilisé pour ça) | ❌ |
| Déploiement (§8) | 4 profils, Solo < 5 min / 8 Go, edge sync, offline-first | Un seul profil, lourd ; GeoNode+Superset rendent Solo impossible | ⛔ |
| Sécurité (§9) | OIDC/Keycloak, multi-tenant natif, ReBAC (OpenFGA), RLS spatiale | Keycloak ✅ ; permissions = modèle GeoNode ; pas de tenant_id, pas de ReBAC, pas de RLS | 🟡/❌ |
| Exploitation (§10) | Tout déclaratif, GitOps, OpenTelemetry, SLO packagés | AppConfigs déclaratives ✅ ; config plateforme non exportable ; pas d'OTel/SLO | ❌ |
| Workflows (§13.1) | Durable execution sur Postgres, OGC API Processes | Rien | ❌ |
| Versioning données (§13.2) | Time-travel + branches/merge (Kart) | Rien côté données ; révisions/rollback des **configs** ✅ (embryon du même réflexe) | ❌/🟡 |
| Agent runtime (§13.3) | Agents = objets de plateforme, plan→approbation | Rien | ❌ |
| App builder Retool (§13.4) | Formulaires/CRUD, CEL, actions composables, génération IA | Lecture + filtres + variables + actions ✅ ; pas de formulaires/écriture, pas de CEL | 🟡 |

**Lecture d'ensemble** : le projet actuel est *en avance* sur l'axe applicatif (§5, une
partie de §13.4 — la Vision le place en an 2) et *à zéro ou en contradiction* sur les
fondations que la Vision place en an 1 (cœur, catalogue STAC, lakehouse, profil Solo).
La trajectoire du dépôt a construit la maison en commençant par le premier étage.

---

## 3. Comparaison détaillée par domaine

### 3.1 Vision produit

- **Convergence** : même ennemi (coût/complexité ArcGIS Enterprise), même conviction
  formats ouverts, même cible collectivités/organisations moyennes (explicite dans les
  études de la couche 1).
- **Écart** : le projet actuel se définit *par rapport à ArcGIS* (« équivalent à »,
  matrice de parité 11.4) là où la Vision refuse ce match (« on ne joue pas la largeur
  du catalogue ») et se positionne *par rapport à la data platform*. Concrètement :
  aucun pont vers dbt/notebooks/DuckDB dans le projet actuel, alors que c'est le persona
  n° 2 de la Vision.
- **Écart** : la Vision hiérarchise 5 personas (consommateur métier d'abord) ; le projet
  actuel cible implicitement le géomaticien/l'admin SIG (GeoNode) et l'auteur no-code
  (GeoStudio), sans hiérarchie explicite.

### 3.2 Architecture générale — le point de rupture principal

La Vision recommande un **monolithe modulaire + 2 systèmes d'état** avec un test
d'acceptation brutal : *tout démarre sur une VM 4 vCPU / 8 Go*. Le projet actuel est
l'exact contre-modèle, hérité de la couche 1 :

- **13 services**, dont trois plateformes lourdes à part entière : GeoNode (Django +
  ses propres dépendances internes), Superset (BI complète), Keycloak. Prérequis
  affichés du README : **16 Go RAM minimum, 32 recommandés** — soit 2 à 4× le budget
  total du profil Solo de la Vision.
- **Systèmes d'état multiples** : PostgreSQL, Redis, MinIO, volumes Keycloak, état
  interne GeoNode/Superset — contre « PostGIS + S3, point » dans la Vision.
- **Pas de couche jobs/workers** : pas de file, pas d'import/ETL asynchrone, pas de
  génération de tuiles pilotée (le script PMTiles est manuel).
- Le cœur au sens de la Vision (catalogue + identité + politiques + OGC API + builder +
  partage dans UN artefact) n'existe pas : ces responsabilités sont éclatées entre
  GeoNode (catalogue, partage), Keycloak (identité), pg_featureserv (OGC API),
  builder-service (configs), shell (builder).

À noter : la fédération GeoNode↔Keycloak↔builder-service↔shell reproduit en miniature la
fédération Portal/Server que la Vision identifie comme la source n° 1 d'incidents
d'ArcGIS Enterprise.

### 3.3 Données

- **Chaud** : PostGIS est là (✅, même version d'esprit), exposé en OGC API Features
  par pg_featureserv (lecture seule — la Vision veut lecture/écriture). Pas de CDC,
  donc pas de chemin vers un lakehouse ni vers des couches live.
- **Froid** : c'est le grand absent. Aucun GeoParquet, aucun DuckDB (serveur ou WASM),
  pas d'Iceberg, pas de FlatGeobuf. MinIO existe mais sert de stockage brut. TiTiler
  donne le COG (✅ partiel). PMTiles : un script de génération, aucun chemin de service
  HTTP Range documenté/câblé.
- **Catalogue** : GeoNode incarne le modèle que la Vision supprime — la donnée doit être
  *enregistrée puis publiée* pour exister. Pas de STAC, pas de DCAT natif. Le principe
  « le catalogue référence les assets là où ils sont » est structurellement étranger à
  GeoNode.
- **Sémantique** : pas de pgvector, pas d'embeddings.
- **Règle d'or de la Vision** (« aucun octet dans un format que QGIS/DuckDB/curl ne lit
  pas ») : respectée par les données elles-mêmes (PostGIS), pas par le modèle de
  contenu (items GeoNode, configs en base du builder-service — ces dernières étant du
  JSON propre, l'écart est faible).

### 3.4 Cartographie — le domaine le plus aligné

MapLibre GL + deck.gl + Martin : le trio recommandé est en place et fonctionne, avec
basemaps, panneau de couches, légende, éditeur de carte. Écarts restants :

- Le **style MapLibre comme artefact de première classe** (versionné, diffable,
  générable par IA) n'est pas traité — les styles vivent dans le code/les configs.
- Pas de 3D (3D Tiles/quantized-mesh), pas de CesiumJS optionnel — non critique, la
  Vision le met tard.
- Pas de chemin PMTiles-depuis-CDN/S3 (le cœur resterait hors du chemin des tuiles
  statiques) ; aujourd'hui tout le vecteur dynamique passe par Martin (✅ pour le chaud).
- Pas d'impression (QGIS Server headless prévu par la Vision ; GeoServer des études de
  couche 1 n'est même plus dans le compose — bon signe de minimalisme).

### 3.5 Développement applicatif — l'avance réelle du projet

Le §5 de la Vision décrit : *un seul modèle, tout est une config déclarative rendue par
un runtime unique ; la config est du JSON versionnable ; SDK ; plugins*. Le projet
actuel a implémenté l'essentiel du premier tiers :

- ✅ `AppConfig` unique pour apps et dashboards, `AppRenderer` avec modes
  édition/runtime, grille responsive, data sources déclaratives, bus d'actions,
  variables, multi-pages, thèmes, templates, publication.
- ✅ Configs **versionnées avec révisions et rollback** côté builder-service — c'est
  littéralement « la config est l'actif stratégique » de la Vision.
- 🟡 SDK : contrat de widget propre (registre + manifeste, preuve par le widget
  Compteur « sdk-only »), mais **couplé React et compilé dans le bundle**. Pas de
  Web Components, pas de chargement dynamique de modules ES tiers, pas de manifeste de
  permissions, pas de sandbox, pas de marketplace.
- ❌ Pas d'*eject* vers un projet code.
- La fragmentation que la Vision reproche à Esri (N builders) est correctement évitée :
  apps et dashboards sont bien deux presets du même moteur.

### 3.6 IA — écart total

Rien dans le projet actuel : pas de serveur MCP, pas de recherche sémantique, pas de
copilote, pas de journalisation d'actions d'agents. En revanche, le prérequis
architectural de la Vision (« tout déclaratif, tout schématisé ») est *partiellement
acquis* côté builder : un copilote « génère-moi un dashboard » aurait déjà un format
cible propre (l'AppConfig). C'est un écart d'implémentation, pas de conception — sauf
pour le catalogue (GeoNode n'expose rien de MCP-able proprement).

### 3.7 Temps réel — écart total

Aucune ingestion MQTT/HTTP, aucun SSE/WebSocket, aucune couche live, aucun moteur
d'alertes. Redis est dans le compose sans rôle temps réel. Le palier 0 de la Vision
(ingestion simple → PostGIS → SSE) serait un chantier nouveau mais modeste.

### 3.8 Déploiement — contradiction structurelle

- La Vision : 4 profils, un artefact, **Solo < 5 min / < 8 Go** comme *exigence produit
  de niveau 1*, edge sync, offline terrain.
- Le projet actuel : un seul profil, démarrage ordonné manuel en 6 étapes documentées,
  16–32 Go, aucune version allégée possible tant que GeoNode et Superset sont dans le
  chemin critique. Pas d'offline (ni client GeoPackage, ni synchro différée).
- Point positif : tout est déjà OCI/compose, Traefik en ingress, `.env` centralisé —
  la *mécanique* est là, c'est le *contenu* du compose qui est trop lourd.

### 3.9 Sécurité

- ✅ OIDC via Keycloak, tokens propagés dans le shell (`react-oidc-context`), routes
  runtime publiques gérées via la publication GeoNode.
- ❌ Multi-tenant : aucun `tenant_id` nulle part — la Vision insiste : quasi impossible
  à rétrofitter, quasi gratuit à anticiper. Tout ce qui sera construit d'ici la
  décision aggrave ce rétrofit.
- ❌ Autorisation : le modèle de partage *en surface* (privé/groupe/public, hérité de
  GeoNode) correspond au modèle mental que la Vision veut garder — mais le *moteur*
  dessous est celui de GeoNode (ad hoc), pas un ReBAC/ABAC requêtable, et rien ne
  descend en RLS PostGIS (pg_featureserv voit tout).
- ❌ Pas d'audit unifié.

### 3.10 Exploitation

- ❌ Pas d'OpenTelemetry, pas de SLO, pas de GitOps (la config *plateforme* — realm
  Keycloak, réglages GeoNode/Superset — n'est ni exportable ni applicable) ;
  l'observabilité des études de couche 1 (Prometheus/Grafana) n'a pas été câblée.
- ✅ En germe : les AppConfigs sont exportables/versionnables par nature ; les
  révisions du builder-service sont un embryon d'auditabilité.

---

## 4. Les quatre briques différenciantes

| Brique (§13) | Projet actuel | Distance |
|---|---|---|
| **Workflow Engine** (13.1) | Rien. Pas de file de jobs (prérequis an 2 : « jobs + déclencheurs ») | Chantier entier, mais indépendant — greffable |
| **Data Versioning** (13.2) | Étage 1 (time-travel/audit) absent — pas de CDC ni lakehouse. Mais le réflexe « tout objet a des révisions + rollback » existe déjà pour les configs | L'étage 1 dépend du chantier données |
| **Agent Runtime** (13.3) | Rien (dépend de la surface MCP, absente) | Dépend du cœur/MCP |
| **App Builder Retool** (13.4) | Le plus proche : runtime unique ✅, actions ✅, variables ✅, multi-pages ✅. Manquent : formulaires/CRUD (écriture !), expressions CEL, actions→workflows, génération IA | ~1 cran sur 4 franchi, le suivant (formulaires/CRUD) est faisable sur l'existant |

Le séquencement consolidé de la Vision (tableau §13) place le projet actuel à peu près
sur la colonne « An 1–2 » de la ligne App builder, et à la colonne « — » des trois
autres lignes.

---

## 5. Bilan : actifs réutilisables, actifs en tension, absents

### 5.1 Actifs conformes à la Vision (à conserver quoi qu'il arrive)

1. **Le moteur builder du shell** (grille, registre/SDK, data sources, actions,
   variables, pages, thèmes, templates, publication) + ses **56 fichiers de tests et
   13 specs E2E**. C'est l'actif le plus coûteux à reconstruire et il implémente le §5.
2. **Le principe « configs JSON versionnées + rollback »** du builder-service (le
   *principe* et le schéma, sinon le service lui-même).
3. **Le trio carto MapLibre + deck.gl + Martin** et l'éditeur de carte.
4. **Keycloak/OIDC** et le câblage auth du shell.
5. **PostGIS + PgBouncer + MinIO + Traefik** : les fondations d'infra neutres.
6. Le **modèle mental de partage** (privé/groupe/public) exposé dans l'UI.
7. Le **corpus d'études** comme documentation de veille (valeur documentaire).

### 5.2 Actifs en tension frontale avec la Vision

1. **GeoNode** — la contradiction centrale. Il fournit aujourd'hui catalogue, items,
   métadonnées, partage, publication… c'est-à-dire ~la moitié du futur cœur. Mais il
   incarne les trois postulats que la Vision renverse : rite de publication, plateforme-
   silo, empreinte lourde. Tout investissement nouveau autour de GeoNode creuse l'écart.
2. **Superset** — doublon direct des widgets charts/dashboards du builder maison ;
   contraire au « un seul runtime ».
3. **Redis** — système d'état surnuméraire sans rôle clair (la Vision : deux états).
4. **L'IMPLEMENTATION_PLAN 8 phases** (couche 1) — décrit la construction d'une stack
   d'assemblage, obsolète par rapport aux couches 2–3 et à la Vision.
5. **builder-service en Python/FastAPI séparé** — pas contradictoire en soi, mais la
   Vision veut UN cœur (Go ou TS) englobant builder + catalogue + politiques ; un
   service Python isolé en est le germe possible ou l'orphelin futur, selon la décision.

### 5.3 Absents purs (chantiers nouveaux dans tous les scénarios)

Lakehouse (GeoParquet/DuckDB/Iceberg), STAC/DCAT, pgvector/recherche sémantique, MCP et
copilotes, SSE/alertes/streaming, profils de déploiement + offline, multi-tenant,
ReBAC/OpenFGA + RLS, OTel/GitOps/SLO, workflows, versioning de données, agent runtime,
formulaires/CRUD + CEL. **Ces chantiers coûtent le même prix dans les deux scénarios**
(adapter ou reconstruire) — ils ne discriminent donc pas la décision, sauf quand GeoNode
est sur leur chemin (STAC, MCP, multi-tenant, ReBAC : il l'est).

---

## 6. Orientation : adapter ou reconstruire

### 6.1 Reformuler la question

« Adapter ou reconstruire » est trompeur si on traite le projet comme un bloc. Les trois
couches n'appellent pas la même réponse :

- La **couche 1** (stack d'assemblage) est déjà invalidée par la Vision — et
  partiellement abandonnée de fait (GeoServer, Airflow, Sedona ne sont plus dans le
  compose).
- La **couche 3** (GeoStudio : shell + builder) est *conforme* à la Vision — la
  question ne se pose pas, on la garde.
- La vraie question porte sur **le centre de gravité** : qui est le cœur de la
  plateforme ? GeoNode (état actuel) ou un cœur maison (Vision) ? Et : dans quel dépôt,
  quel langage, quelle continuité ?

Trois options réalistes en découlent.

### 6.2 Option A — Adaptation continue du projet actuel (GeoNode reste le centre)

On garde l'architecture actuelle et on greffe les éléments de la Vision autour :
STAC via pygeoapi/stac-fastapi à côté de GeoNode, MCP devant l'API GeoNode, PMTiles
servis de MinIO, DuckDB dans un service à part, etc.

| Pour | Contre |
|---|---|
| Aucune rupture ; le produit reste démontrable en continu | **Chaque brique de la Vision devra contourner GeoNode** (catalogue en double, permissions en double, publication en double) |
| Catalogue/partage/métadonnées « gratuits » aujourd'hui | Le profil Solo (< 8 Go) reste inatteignable — l'arme d'adoption n° 1 de la Vision est sacrifiée |
| Zéro coût de migration immédiat | La dette de fédération (GeoNode↔Keycloak↔builder↔shell) croît avec chaque feature |
| | Multi-tenant, ReBAC, RLS : quasi impossibles à travers GeoNode |
| | On devient mainteneur de l'intégration GeoNode (upgrades Django, breaking changes API v2) sans en contrôler la roadmap |

**Verdict : c'est l'option par défaut si on ne décide rien — et la plus chère à 3 ans.**
Elle transforme la Vision en liste de vœux inapplicables. À ne retenir que si l'objectif
réel du projet est *déployer un portail SIG fonctionnel rapidement pour un besoin
concret immédiat* (auquel cas GeoNode est un choix honnête) — pas si l'objectif est de
construire la plateforme décrite par la Vision.

### 6.3 Option B — Nouveau projet feuille blanche

Nouveau dépôt, cœur monolithe modulaire (Go ou TypeScript) conforme au §12, en
réécrivant aussi le front « proprement » (Web Components d'entrée, etc.).

| Pour | Contre |
|---|---|
| Architecture exacte de la Vision dès le jour 1 (tenant_id, frontières de modules, STAC natif) | **On jette l'actif le plus cher** : ~180 commits, un builder testé (56 + 13 fichiers de tests) qui est précisément la partie la plus longue à refaire |
| Pas de dette d'intégration GeoNode à porter ni à défaire | Tunnel de 9–18 mois sans produit démontrable — mortel pour la motivation d'un side project |
| Liberté totale sur le langage du cœur | L'historique du dépôt montre déjà deux pivots (stack → OGE → GeoStudio) ; un troisième « on recommence » est le pattern d'échec classique |
| | Le shell actuel n'est PAS en tension avec la Vision — le réécrire est une perte sèche |
| | Le risque « second system effect » : sur-architecturer le cœur avant d'avoir un usage |

**Verdict : à écarter sous cette forme totale.** La feuille blanche ne se justifie que
pour la partie qui n'existe pas encore (le cœur) — pas pour celle qui existe et
converge (le builder).

### 6.4 Option C — Refonte par étranglement : garder GeoStudio, remplacer le centre (recommandée)

Principe : **le shell + moteur builder sont le produit ; GeoNode est un backend
provisoire qu'on remplace par le cœur de la Vision, module par module.** Le pattern
strangler appliqué à son propre projet.

Trajectoire concrète (ordre proposé, chaque étape laissant le produit fonctionnel) :

1. **Décision fondatrice** : langage et forme du cœur (voir Q5). Deux voies :
   - *C-continuité* : promouvoir `builder-service` (FastAPI) en cœur — il gagne
     catalogue/items/partage et devient le monolithe modulaire, en Python ;
   - *C-vision* : nouveau service cœur en Go ou TypeScript ; `builder-service` y est
     absorbé (ses schémas et sa logique de révisions sont portés, ses tests traduits).
2. **Module items/catalogue dans le cœur** : items (id, type, titre, owner, sharing,
   thumbnail) + métadonnées STAC + partage privé/groupe/public. Le shell bascule son
   `itemClient` de GeoNode vers le cœur (la façade `itemClient` existante rend ce swap
   peu invasif — c'est déjà une interface). **GeoNode sort du compose.** Gain
   immédiat : ~la moitié de l'empreinte mémoire.
3. **Sortir Superset** (les widgets charts le couvrent pour le no-code ; l'analytique
   lourde attendra DuckDB). Redis sort s'il n'a pas trouvé de rôle. → Le compose vise
   le **profil Solo** : cœur + PostGIS + MinIO + Martin + Keycloak + Traefik.
4. **Chemin de publication de la Vision** : dépôt de fichier → worker (file de jobs
   `SKIP LOCKED` dans Postgres) → GeoParquet + PMTiles + métadonnées STAC → servable.
   Premier morceau du lakehouse et suppression du rite de publication.
5. **Surface AI-ready** : serveur MCP sur le cœur (catalogue, requêtes, configs) +
   pgvector pour la recherche. Faible coût une fois le cœur en place, différenciation
   maximale.
6. Ensuite, au choix selon les réponses aux questions : formulaires/CRUD (§13.4, sur
   l'existant builder), SSE/alertes (palier 0), multi-tenant + RLS, profils de
   déploiement formalisés.

| Pour | Contre / risques |
|---|---|
| Conserve 100 % de l'actif conforme (builder + tests + carto) | Période de double maintenance pendant le remplacement de GeoNode (mitigée par la façade `itemClient`) |
| Produit démontrable en continu, jamais de tunnel | Réécrire items/partage/miniatures que GeoNode donnait « gratuitement » (mais périmètre réellement utilisé : modeste — CRUD items + sharing + is_published + thumbnails) |
| Le profil Solo devient atteignable (l'argument d'adoption n° 1) | Exige la décision de langage du cœur maintenant — c'est LA décision irréversible |
| Débloque STAC, MCP, multi-tenant, ReBAC (plus de GeoNode sur le chemin) | Discipline de frontières de modules à outiller dès le début (lint d'archi), sinon le cœur pourrit |
| Chaque étape a une valeur autonome | Le multi-tenant (`tenant_id`) doit entrer au schéma du cœur dès l'étape 2, même inutilisé |

**Coût estimé de l'étape critique (2–3)** : le périmètre GeoNode réellement consommé par
le shell est étroit et déjà abstrait derrière `itemClient` + le stub in-memory du
builder-service (qui prouve que le contrat est cernable). C'est des semaines, pas des
mois — sans commune mesure avec une réécriture du builder.

### 6.5 Matrice de décision

| Critère | A — Adapter autour de GeoNode | B — Feuille blanche totale | C — Étranglement |
|---|---|---|---|
| Réutilisation de l'existant | Totale | ~Nulle (front refait) | Totale sur l'actif conforme |
| Conformité Vision à 2 ans | Faible (plafonnée par GeoNode) | Maximale (si le tunnel est survécu) | Élevée |
| Risque d'abandon du projet | Moyen (frustration croissante) | **Élevé** (tunnel sans démo) | Faible |
| Profil Solo « < 5 min / 8 Go » | Inatteignable | Atteignable | Atteignable dès l'étape 3 |
| Time-to-valeur des nouveautés (MCP, STAC…) | Lent (contournements) | Très lent (fondations d'abord) | Rapide après l'étape 2 |
| Coût de la décision si on se trompe | Dette d'intégration | Perte sèche du travail | Réversible étape par étape |

---

## 7. Recommandation

**Option C — refonte par étranglement**, avec trois principes :

1. **Le builder/shell est déclaré « produit » ; GeoNode est déclaré « échafaudage ».**
   Plus aucun investissement nouveau ne cible GeoNode ; tout investissement contenu
   (items, partage) cible le futur cœur.
2. **La décision de langage du cœur se prend maintenant** (question 5 ci-dessous) —
   c'est la seule décision quasi irréversible du scénario. Tout le reste est
   séquençable et réversible.
3. **Le test d'acceptation de la Vision devient le garde-fou du dépôt** : à partir de
   l'étape 3, *la plateforme complète doit démarrer via `docker compose up` sur 8 Go* —
   et une CI peut le vérifier.

Le projet actuel n'est ni à jeter ni à continuer tel quel : il contient déjà l'an 2 de
la Vision (builder) posé sur un an 1 qui la contredit (GeoNode/assemblage). L'option C
remet les étages dans l'ordre sans démolir le premier étage construit.

---

## 8. Questions pour orienter le projet

Les réponses à ces questions déterminent l'ordre des chantiers de l'option C (et
pourraient, pour certaines, la remettre en cause). Les questions 1–5 sont
structurantes ; les suivantes séquencent.

**Q1 — Finalité du projet.** Est-ce (a) un produit destiné à être diffusé/commercialisé
(open core, la marketplace et le multi-tenant deviennent réels), (b) une plateforme pour
un besoin interne/professionnel précis, ou (c) un terrain d'apprentissage/portfolio ?
→ *Change la priorité de : marketplace, multi-tenant, licence, doc publique.*

**Q2 — Premiers utilisateurs réels.** Qui sont les 1 à 3 premiers
utilisateurs/déploiements visés à 12 mois (une collectivité identifiée ? une équipe
data ? vous seul ?) et quel est LE cas d'usage qu'ils doivent réussir ?
→ *Sans réponse, la Vision reste un document ; avec une réponse, elle devient une roadmap.*

**Q3 — Cas d'usage n° 1.** Parmi les cinq cas prioritaires de la Vision — (a) publier
une donnée → carte partageable en minutes, (b) dashboard/app métier no-code, (c)
interrogation en langage naturel, (d) collecte terrain offline, (e) alertes
spatiales — lequel est le critère de succès des 6 prochains mois ?
→ *(a) pousse le cœur+workers ; (b) pousse formulaires/CRUD ; (c) pousse MCP/pgvector ;
(d) et (e) sont des chantiers neufs entiers.*

**Q4 — Sort de GeoNode.** Confirmez-vous son remplacement par un cœur maison (option C,
étape 2), ou GeoNode doit-il rester 12 mois de plus (parce qu'un déploiement réel en
dépend, parce que son catalogue riche est requis…) ?
→ *C'est le pivot de toute l'orientation. « Oui mais plus tard » = option A de fait.*

**Q5 — Langage et forme du cœur.** (a) Go (perf, binaire unique, mais nouvelle
compétence à bord ?), (b) TypeScript/Node (continuité avec le shell, un seul langage
front+back), (c) Python/FastAPI en promouvant builder-service (continuité avec
l'existant, mais à contre-courant du « binaire unique » de la Vision) ?
→ *Question à trancher en fonction de VOS compétences et de qui maintiendra ce code.*

**Q6 — Capacité de développement.** Le projet est-il développé en solo (avec agents IA),
à temps partiel ? Combien d'heures/semaine de façon réaliste ?
→ *Dimensionne tout : la Vision est une trajectoire à 5 ans pour une équipe ; en solo,
chaque « an » de la Vision en vaut probablement 2–3.*

**Q7 — Contrainte scale-down.** Le test « `docker compose up` < 5 min sur une VM 8 Go »
devient-il une exigence de niveau 1 dès maintenant (CI qui le vérifie, refus de tout
service qui le casse) ou un objectif différé ?
→ *Si oui : Superset et Redis sortent vite, et GeoNode a une date de fin.*

**Q8 — Place de l'IA.** La surface MCP + recherche sémantique est-elle un chantier de
l'année 1 (différenciateur immédiat, cohérent avec vos outils de travail actuels) ou
attend-elle que la boucle publier→cartographier→partager soit refaite sur le cœur ?
→ *La Vision la met en an 1–2 ; l'option C la place à l'étape 5, avançable si c'est votre
critère d'enthousiasme.*

**Q9 — Multi-tenant.** Y a-t-il un scénario réel multi-organisations à horizon visible
(hébergement mutualisé pour plusieurs collectivités, SaaS) ? Ou mono-tenant assumé ?
→ *Même mono-tenant, la Vision recommande `tenant_id` jour 1 dans le schéma du cœur —
coût quasi nul à l'étape 2 de l'option C, prohibitif après.*

**Q10 — Temps réel et alertes.** Avez-vous un besoin concret identifié (flotte,
capteurs, crues…) ou est-ce spéculatif ? Si concret : volumes (nombre d'objets mobiles,
fréquence) ?
→ *Concret → palier 0 (SSE natif) monte dans la pile ; spéculatif → il attend.*

**Q11 — Terrain / offline.** La collecte terrain hors connexion (GeoPackage local,
synchro différée) est-elle dans le périmètre des 2 prochaines années ?
→ *C'est le chantier le plus structurant côté client (service workers, synchro,
conflits) — il vaut mieux le savoir avant de figer le SDK.*

**Q12 — Superset et l'analytique.** Confirmez-vous que les widgets charts du builder
remplacent Superset pour le no-code, l'analytique lourde étant renvoyée à DuckDB/
GeoParquet plus tard ? Ou Superset a-t-il des utilisateurs/usages actuels à préserver ?

**Q13 — SDK et plugins.** Pour la v1 du SDK public : (a) assumer un SDK React (simple,
continuité de l'existant) en réservant les Web Components à une v2, ou (b) migrer le
contrat de widget vers Web Components avant d'ouvrir le SDK à des tiers ?
→ *(b) est la cible Vision mais retarde l'ouverture ; (a) crée des widgets tiers à
migrer plus tard.*

**Q14 — LA brique différenciante.** Des quatre briques de l'addendum — workflows
durables, versionnement de données « pull request pour vos données », agent runtime,
app builder niveau Retool — laquelle voulez-vous comme signature du produit ? (Une
seule ; le document lui-même prévient que ces briques sont le risque de scope creep
maximal.)
→ *L'existant favorise « app builder » (déjà 1 cran franchi) ; votre contexte outillage
IA favorise « agent runtime » ; le secteur public favorise « versionnement ».*

**Q15 — Identité du projet.** OGE, GeoCore, GeoStudio coexistent dans le dépôt. Un seul
produit = un seul nom : lequel survit, et le dépôt/les docs sont-ils restructurés en
conséquence (archivage des couches 1–2 dans `docs/archive/`) ?

---

## 9. Réponses et orientation retenue (2026-07-04)

Réponses apportées le 2026-07-04 (12 des 15 questions ; Q2 — premiers utilisateurs
réels, Q10 — temps réel, Q11 — offline restent ouvertes) :

| Question | Décision |
|---|---|
| Q1 Finalité | **Produit open-source public** |
| Q3 Cas d'usage n° 1 (6 mois) | **Dashboards / apps métier no-code** |
| Q4 GeoNode | **Remplacé par un cœur maison** (option C confirmée) |
| Q5 Langage du cœur | **Python — `builder-service` promu en cœur** |
| Q6 Capacité | **Solo, 10–25 h/semaine (+ agents IA)** |
| Q7 Contrainte Solo 8 Go | **Pas prioritaire** (pas de CI bloquante) |
| Q8 IA / MCP | **Tôt : dès que le cœur v0 existe** |
| Q9 Multi-tenant | **Pas de besoin immédiat, mais `tenant_id` dès le jour 1** |
| Q12 Superset | **Sort du produit** (le builder le remplace) |
| Q13 SDK widgets | **Web Components avant toute ouverture aux tiers** |
| Q14 Brique signature | **App builder niveau Retool** |
| Q15 Nom | **GeoStudio** |

### Ce que ces réponses changent au séquencement de l'option C

1. **L'axe produit est le builder, pas l'ingestion.** Cas d'usage n° 1 + brique
   signature convergent : après le remplacement de GeoNode (étape 2), la priorité
   est le cran suivant du §13.4 — **formulaires/CRUD** (écriture via le cœur, avec
   permissions), puis expressions, actions composées. Le chemin de publication
   lakehouse (étape 4 : workers, GeoParquet, STAC complet) passe *après* ou en
   parallèle lent.
2. **Le cœur v0 est en Python** : `builder-service` gagne les modules items,
   catalogue, partage, publication — schéma avec `tenant_id` partout et audit des
   écritures dès la première migration. Le shell bascule via la façade `itemClient`.
3. **MCP monte dans la pile** : dès le cœur v0 stabilisé, serveur MCP (items,
   AppConfigs, requêtes) — cohérent avec « produit public » (surface agentique =
   argument d'adoption) et avec le mode de développement (solo + agents).
4. **Superset sort à l'étape 3** comme prévu ; en revanche, **pas de garde-fou CI
   « 8 Go »** — écart assumé avec la vision (§8). À noter : la sortie de
   GeoNode + Superset allège de fait l'empreinte ; l'exigence pourra être réévaluée
   quand le profil Solo deviendra un argument commercial du produit public.
5. **SDK : le registre React reste interne.** Aucune ouverture publique du SDK avant
   la migration du contrat de widget vers Web Components — ce chantier se planifie
   *avant* la marketplace, pas après.
6. **Nom : GeoStudio** — consolidation documentaire à faire (README réécrit autour du
   produit, couches 1–2 archivées, OGE/GeoCore retirés ou renommés).

**Prochain jalon suggéré** (dans l'esprit des SP-0x existants) : *SP-1 — cœur v0* :
module items/partage/publication dans `builder-service` (schéma `tenant_id` + audit),
bascule `itemClient`, sortie de GeoNode du compose. Puis *SP-2 — formulaires/CRUD*
dans le builder.

---

## Annexe — Correspondance service par service (compose actuel → architecture cible §12)

| Service actuel | Rôle dans l'architecture cible de la Vision | Devenir (option C) |
|---|---|---|
| postgis (16/3.4) | PostgreSQL/PostGIS + pgvector (état chaud, RLS) | **Conservé** ; ajouter pgvector, RLS, CDC |
| pgbouncer | Non mentionné (détail d'implémentation) | Conservé si utile |
| redis | Absent (« deux systèmes d'état ») | Cache optionnel toléré, jamais un état durable ; candidat sortie (étape 3) |
| minio | Object storage S3 | **Conservé** |
| martin | Tuiles dynamiques (MVT depuis PostGIS) | **Conservé** |
| titiler | COG servis du S3 (+ rendus dynamiques) | Conservé court terme ; recouvrement partiel avec le « HTTP Range direct » de la Vision, à réévaluer |
| pg-featureserv | OGC API Features du cœur | Solution d'attente ; absorbé par le cœur (lecture/écriture) à terme |
| superset | Absent (dashboards = runtime config-driven) | **Candidat sortie** (étape 3, cf. Q12) |
| geonode | Cœur : catalogue STAC, items, partage, publication | **Remplacé par le cœur** (étape 2, cf. Q4) — la charnière est la façade `itemClient` |
| keycloak | Identité OIDC (IdP embarqué par défaut) | **Conservé** ; passer de `start-dev` à un realm provisionné/exporté |
| traefik | Reverse proxy / CDN | **Conservé** |
| builder-service | Module « builder & AppConfigs » du cœur | **Conservé — embryon du cœur** (destin selon Q5 : promu ou absorbé) |
| shell | Client web (MapLibre/deck.gl) + builder | **Conservé — actif principal** |
| — (absents) | Workers de jobs, STAC, DuckDB, MCP, SSE/alertes, moteur de politiques (OpenFGA/embarqué), OTel | À construire (séquencement selon Q3, Q7–Q10) |

---

*Document généré le 2026-07-04 sur l'état de la branche `dev` (commit `b8eb71f`).*
