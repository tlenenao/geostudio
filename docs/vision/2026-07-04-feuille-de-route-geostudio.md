# GeoStudio — Feuille de route Option C (spécification et phasage)

> Déclinaison opérationnelle de l'option C (« refonte par étranglement ») retenue dans
> [`2026-07-04-comparatif-projet-actuel-vs-vision.md`](./2026-07-04-comparatif-projet-actuel-vs-vision.md)
> (§9), elle-même issue de la vision
> [`2026-07-04-plateforme-webgis-nouvelle-generation.md`](./2026-07-04-plateforme-webgis-nouvelle-generation.md).
>
> Date : 2026-07-04 · Statut : feuille de route — les arbitrages techniques (§7) sont
> tranchés en §8. Chaque phase donnera lieu à sa spec + son plan détaillé
> (`docs/superpowers/`) au moment de la lancer, selon le workflow SP-0x existant.
> Étendue le 2026-07-05 (SP-10→13, A16–A27) puis le **2026-07-09** (SP-14/SP-15,
> A28–A30, amendements A22/A27, jalons M11/M12 — issus du
> [brainstorm Analytics Platform](./2026-07-09-brainstorm-geostudio-analytics-platform.md),
> validé Q-A1→Q-A5), puis le **2026-07-14** (SP-16 « Portails & Sites », quick
> win Storytelling, arbitrages A31/A33–A38, jalon M13 — issus du
> [gap analysis dataviz/analytics/BI/portails](./geostudio-dataviz-analytics-gap-analysis.md),
> arbitrages tranchés par Tanguy).

---

## Sommaire

1. [Décisions déjà actées (rappel)](#1-décisions-déjà-actées)
2. [Principes d'exécution](#2-principes-dexécution)
3. [Architecture cible de fin de feuille de route](#3-architecture-cible)
4. [Le périmètre exact du remplacement de GeoNode](#4-périmètre-du-remplacement-de-geonode)
5. [Modèle de données du cœur v0](#5-modèle-de-données-du-cœur-v0)
6. [Phasage SP-1 → SP-13](#6-phasage)
7. [Points d'arbitrage technique (A1–A27)](#7-points-darbitrage-technique)
8. [Décisions d'arbitrage](#8-décisions-darbitrage)
9. [Ce qui est explicitement différé](#9-différé)
10. [Risques transverses](#10-risques-transverses)
11. [Jalons et indicateurs de succès](#11-jalons-et-indicateurs)

---

## 1. Décisions déjà actées

| Sujet | Décision (comparatif §9) |
|---|---|
| Stratégie | Option C — le shell/builder est le produit, GeoNode est remplacé par un cœur maison |
| Finalité | Produit **open-source public**, nommé **GeoStudio** |
| Cœur | **Python** — `builder-service` promu en cœur (monolithe modulaire) |
| Capacité | Solo, **10–25 h/semaine** (+ agents IA) |
| Cas d'usage n° 1 | **Dashboards / apps métier no-code** → cap sur le niveau Retool (formulaires/CRUD) |
| IA | **MCP tôt**, dès le cœur v0 |
| Multi-tenant | Pas d'activation immédiate, mais **`tenant_id` partout dès le jour 1** |
| Superset | **Sort du produit** |
| SDK | **Web Components avant toute ouverture aux tiers** |
| Contrainte « Solo 8 Go » | Non prioritaire (pas de CI bloquante) |
| Questions restées ouvertes | Q2 (premiers utilisateurs), Q10 (temps réel), Q11 (offline) |

---

## 2. Principes d'exécution

1. **Jamais de tunnel.** Chaque SP livre un produit fonctionnel et démontrable ; les
   13 specs E2E Playwright existantes restent vertes en permanence (elles sont le
   filet de la migration).
2. **Workflow inchangé** : brainstorm → spec (`docs/superpowers/specs/`) → plan
   (`docs/superpowers/plans/`) → TDD → E2E → commit. Cette feuille de route fixe le
   *quoi* et l'*ordre* ; chaque SP garde son plan détaillé.
3. **La façade `ItemClient` est le sas de migration.** Le shell ne voit jamais deux
   backends : on implémente `CoreItemClient` derrière l'interface existante, on
   bascule, on supprime `GeoNodeItemClient`.
4. **`tenant_id` + `audit_log` dès la première migration** du cœur — même inutilisés
   fonctionnellement, ils sont dans chaque table et chaque écriture.
5. **Tout objet du cœur est un document déclaratif schématisé** (items, configs,
   partages, collections, formulaires) : c'est ce qui rend le MCP (SP-2) et la
   génération par IA quasi gratuits ensuite.
6. **Frontières de modules outillées** dès SP-1 (lint d'imports croisés) — le
   monolithe modulaire ne survit pas sans ça (vision §2).
7. **Estimations honnêtes** : données en heures d'effort ; à 10–25 h/semaine,
   convertir en calendrier avec un facteur 1,5–2× (imprévus, maintenance, vie).

---

## 3. Architecture cible

État visé à la fin de cette feuille de route (≈ v0.1 publique) :

```
                    ┌────────────────────────────────────────────┐
   Clients          │  Shell React (catalogue·carto·builder·run) │
                    │  Agents IA (MCP) · QGIS/curl (OGC, JSON)   │
                    └───────────────┬────────────────────────────┘
                                    │ HTTPS
                    ┌───────────────▼───────────────┐
                    │           TRAEFIK             │
                    └──┬──────────┬──────────┬──────┘
                       │          │          │
        ┌──────────────▼───┐  ┌───▼────┐  ┌──▼──────────┐
        │  CŒUR GeoStudio  │  │ MARTIN │  │  KEYCLOAK   │
        │  (Python/FastAPI,│  │ (MVT)  │  │  (OIDC)     │
        │  monolithe       │  └───┬────┘  └─────────────┘
        │  modulaire)      │      │
        │ · items+partage  │  ┌───▼───────────────┐   ┌───────────┐
        │ · configs+rev.   │  │ POSTGRES/POSTGIS  │   │ MINIO(S3) │
        │ · collections+   │  │ + pgvector        │   │ vignettes │
        │   CRUD features  │  │ (cœur + données   │   │ uploads   │
        │ · ingestion(jobs)│  │  métier, audit)   │   │ PMTiles   │
        │ · recherche      │  └───────────────────┘   └───────────┘
        │ · serveur MCP    │      ▲
        └────────┬─────────┘      │
                 └── workers ─────┘   (TiTiler conservé pour le raster/COG)
```

Sortent du compose au fil de la route : **GeoNode** (SP-1), **Superset** (SP-1),
**pg_featureserv** (SP-3, absorbé), **Redis** (SP-1 sauf rôle avéré). Restent :
PostGIS, PgBouncer, MinIO, Martin, TiTiler, Keycloak, Traefik, cœur, shell.

---

## 4. Périmètre du remplacement de GeoNode

Le contrat à honorer est **exactement** l'interface `ItemClient`
(`shell/src/api/types.ts`) — 18 méthodes, dont 4 ne touchent pas GeoNode :

| Méthode(s) | Backend actuel | Module du cœur v0 |
|---|---|---|
| `listItems, getItem, createConfigItem, createMapItem, updateItem, deleteItem` | GeoNode API v2 | **items** (CRUD, scopes all/mine/shared/public, pagination, recherche q/type) |
| `uploadThumbnail` | GeoNode | **assets** (arbitrage A6) |
| `getMe` | GeoNode | **identity** (depuis le token OIDC) |
| `listGroups, getSharing, setSharing` | GeoNode | **sharing** (public + groupes×rôle viewer/editor ; arbitrages A1–A2) |
| publication (`isPublished` dans `updateItem` + accès runtime anonyme) | GeoNode `is_published` | **items** + politique d'accès anonyme |
| `getAppConfig, saveAppConfig, getMapConfig, saveMapConfig` | builder-service (déjà cœur) | **configs** (existant : révisions + rollback) |
| `queryDataSource, featuresUrl` | pg_featureserv | inchangé en SP-1 ; absorbé en SP-3 |
| `listLayerSources` | config statique | **collections** (registre, enrichi en SP-3) |

Côté builder-service, l'adaptateur `geonode.py` (`ItemClient`/`StubItemClient`
Python) disparaît : les items deviennent des lignes de la même base — l'intégrité
config↔item redevient transactionnelle (le commentaire de `routes.py:delete_config`
sur la fenêtre distribuée GeoNode devient sans objet).

**Ce que l'on ne réimplémente pas** (périmètre GeoNode non consommé par le shell) :
métadonnées ISO/INSPIRE riches, moissonnage CSW, gestion de styles SLD, upload de
couches via GeoNode, notifications, ratings… — rien de tout cela n'est appelé.

---

## 5. Modèle de données du cœur v0

Schéma cible de SP-1 (PostgreSQL, migrations Alembic, `tenant_id` sur chaque table) :

```
tenants(id, name, created_at)
users(id, tenant_id, sub_oidc UNIQUE, username, first_name, last_name, seen_at)
groups(id, tenant_id, title)                      -- arbitrage A2
group_members(group_id, user_id, added_at)
items(id, tenant_id, type app|dashboard|map, title, abstract, keywords[],
      owner_id, is_published, thumbnail_key, created_at, updated_at)
item_shares(item_id, group_id, role viewer|editor)         -- + public bool sur items
configs(id, tenant_id, kind, item_id FK→items, current_version, …)   -- existant, rattaché
config_revisions(…)                                                   -- existant
collections(id, tenant_id, source martin|featureserv|core, layer, title, …)  -- SP-3 l'enrichit
audit_log(id, tenant_id, at, actor_id, actor_kind user|agent, action,
          object_type, object_id, payload jsonb)   -- append-only
```

Notes :
- `users` est un **miroir paresseux** de Keycloak (créé/rafraîchi au premier token
  vu) — le cœur ne stocke jamais de credentials (vision §9).
- Le JSON des configs ne bouge pas : `AppConfig`/`MapConfig` restent le contrat, on
  ajoute seulement le lien transactionnel à `items`.
- Toute écriture passe par une fonction unique qui journalise dans `audit_log`
  (l'`actor_kind agent` anticipe le MCP de SP-2).

---

## 6. Phasage

Vue d'ensemble (effort en heures ; calendrier ≈ effort ÷ capacité × 1,5–2) :

| SP | Titre | Effort | Dépend de | Jalon |
|---|---|---|---|---|
| SP-1 | Cœur v0 : items, partage, publication — sortie de GeoNode | 60–100 h | — | **M1 GeoNode-free** |
| SP-2 | Serveur MCP v0 | 15–30 h | SP-1 | **M2 AI-operable** |
| SP-3 | Collections & CRUD features (écriture de données) | 50–90 h | SP-1 | — |
| SP-4 | Formulaires dans le builder | 60–110 h | SP-3 | **M3 les apps écrivent** |
| SP-5 | Expressions & actions composées | 40–70 h | SP-4 | — |
| SP-6 | Ingestion v1 (upload → PostGIS → carte) | 50–90 h | SP-3 | **M4 donnée→carte en minutes** |
| SP-7 | Recherche (pgvector) + MCP v1 | 25–45 h | SP-2, SP-6 | — |
| SP-8 | SDK Web Components v1 | 60–110 h | SP-5 | **M5 SDK ouvrable** |
| SP-9 | Durcissement produit public (v0.1) | 30–50 h + continu | tous | **M6 v0.1 publique** |
| SP-10 | Observabilité & SLO (OpenTelemetry) | 25–45 h | SP-9 | **M7 exploitable** |
| SP-11 | Lakehouse & CDC (GeoParquet, DuckDB) | 70–120 h | SP-6, SP-10 | **M8 data platform** |
| SP-12 | Catalogue interopérable (STAC, DCAT, moissonnage) | 60–100 h | SP-6 | **M9 catalogue ouvert** |
| SP-13 | 3D & impression | 50–90 h | SP-1 | **M10 3D & print** |
| SP-14 | Analytics UX : datasets, requête visuelle, contexte global | 60–100 h | SP-11 | **M11 BI géospatiale** |
| SP-15 | Alertes & reporting : exports, rapports planifiés | 50–80 h | SP-13, SP-14 | **M12 la plateforme prévient** |
| SP-16 | Portails & Sites : portails publics de marque, découverte éditorialisée | 60–100 h | SP-11 | **M13 portails ouverts** |
| SP-17 | ETL no-code « équivalent FME » : document `Pipeline`, canvas, runtime deux étages | 150–260 h | SP-11 | **M14 ETL no-code** |
| | **Total** | **≈ 915–1 590 h** | | ≈ 20–40 mois à 10–25 h/sem |

L'ordre SP-3→SP-6 est inversable (ingestion avant formulaires) si un utilisateur
réel l'exige (question Q2 du comparatif, toujours ouverte). SP-2 est
volontairement minuscule et placé tôt : démo forte, coût faible, et il force la
propreté de l'API du cœur.

Les **SP-10 à SP-13** ont été ajoutés le 2026-07-05 (extension de périmètre :
sortie du « différé ») ; leur position — *après* v0.1 — et leur ordre relatif
sont fixés par l'arbitrage A27. SP-13 (3D & impression) ne dépend que du socle et
peut s'intercaler plus tôt si un besoin utilisateur réel l'exige ; SP-12 peut
précéder SP-11 si l'interop catalogue devient un argument commercial urgent.

Les **SP-14 et SP-15** ont été ajoutés le 2026-07-09 (brainstorm Analytics
Platform, validé) : ils suivent SP-11 (l'API analytique est leur socle), mais
leur ordre relatif vis-à-vis de SP-12/SP-13 **reste à arbitrer** avant le
lancement du premier d'entre eux (décision Q-A3 ; A27 amendé). Seule contrainte
structurelle : SP-15 dépend du worker d'export de SP-13 pour ses rapports PDF.
Les quick wins de la « vague 0 » du brainstorm (auto-refresh par source, types
ECharts additionnels, KPI enrichie) restent opportunistes au fil de SP-4/SP-5,
hors périmètre formel.

**Le SP-16 a été ajouté le 2026-07-14** (gap analysis dataviz/analytics/BI/
portails, arbitrages A31/A33–A38 tranchés par Tanguy) : chantier **Portails &
Sites**, qui dote GeoStudio d'un objet de plateforme absent jusqu'ici — la
façade publique multi-app éditorialisée (face à ArcGIS Hub/CKAN/data.gouv.fr
thématiques). Il ne dépend techniquement d'aucun autre chantier (un portail
v1 fonctionne déjà avec les seuls items publiés existants) mais s'exécute
**juste après SP-11, avant SP-12/SP-13** (A34/A35 tranchés — SP-11 conditionne
la maturité produit générale avant d'ouvrir un nouveau front public). Son
ordre relatif à SP-14 reste libre : les deux chantiers sont mutuellement
indépendants, le premier prêt peut démarrer. **Le storytelling, lui,
n'attend aucun SP** : livré en quick win indépendant (A36/A37), il s'appuie
uniquement sur des briques déjà acquises (`PageManager`, bindings CEL,
`ActionBus`/`map.flyTo`) et peut être fait dès maintenant, en parallèle de
SP-9 — voir
[la spec dédiée](../superpowers/specs/2026-07-14-storytelling-pagemanager-design.md).

**Le SP-17 a été ajouté le 2026-07-22** (étude de faisabilité ETL no-code,
arbitrage A39 tranché par Tanguy — Go cœur-first) : chantier **ETL no-code
« équivalent FME »**, qui dote GeoStudio de la brique manquante du cycle de vie
de la donnée (transformer/nettoyer/enrichir/recombiner entre la source et la
publication, **données tabulaires pures autant que géospatiales**), sans code.
Il **subsume la partie « pipeline de transformations déclaratif » de SP-14/A28**
(SP-14 conserve l'UX analytique — requête visuelle, contexte global,
cross-filter, SQL Lab ; le moteur de transformation et son canvas visuel
migrent ici). Approche **cœur-first** : document déclaratif `Pipeline`
(MCP-opérable, `can()`/audit/tenant), **runtime de transformers à deux étages**
(étage 1 in-process DuckDB+CEL+pandas+dlt pour les données pures et le spatial
courant ; étage 2 **sidecar `qgis_process`** GPL, opt-in via profil compose
`etl`, pour la longue traîne géo profonde — ~1000+ algorithmes sans en écrire
un), formats GDAL, connecteurs **dlt**, orchestration **procrastinate + OTel**.
**n8n / Kestra / Apache Hop restent des cartes de repli nommées, jamais le
centre.** Dépend de SP-11 (runtime DuckDB) ; s'exécute en 4 phases livrables
(socle headless → canvas → spatial+sidecar → automatisation). Le poste de risque
n°1 est le canvas de graphe ; le runtime réutilise massivement l'existant
(SP-6/SP-11). Voir
[l'étude de faisabilité](../superpowers/specs/2026-07-22-etude-faisabilite-etl-fme-nocode-design.md).

---

### SP-1 — Cœur v0 : items, partage, publication (sortie de GeoNode)

**Objectif.** Le shell fonctionne intégralement sans GeoNode ; toutes les E2E
passent ; Superset et Redis sortent du compose par la même occasion.

Découpage en sous-phases *toutes livrables* (GeoNode reste en place jusqu'à 1d) :

- **SP-1a — Socle du cœur** (12–20 h)
  Restructuration de `builder-service` selon A14 ; Alembic ; middleware
  d'authentification **JWT OIDC** (validation JWKS Keycloak, mode `mock` pour
  tests/e2e comme côté shell) ; tables `tenants/users/audit_log` ; lint de
  frontières de modules ; `GET /me`.
- **SP-1b — Module items** (20–30 h)
  Tables `items` (+ lien `configs.item_id` FK réel) ; endpoints CRUD + listing
  (scopes, q, type, pagination) alignés sur `ListItemsParams` ; vignettes selon A6 ;
  suppression transactionnelle config+item.
- **SP-1c — Partage & publication** (15–25 h)
  `groups`/`group_members`/`item_shares` selon A1–A2 ; enforcement des scopes en
  lecture ET en écriture ; `is_published` + accès anonyme au runtime (route
  publique = item publié uniquement) ; tout écrit dans `audit_log`.
- **SP-1d — Bascule et démolition** (13–25 h)
  `CoreItemClient` dans le shell (mêmes types TS, arbitrage A11) ; variables d'env
  (`VITE_CORE_URL` remplace `VITE_GEONODE_URL`) ; migration des données selon A15 ;
  **retrait de GeoNode, Superset, Redis du compose** ; realm Keycloak exporté et
  provisionné au démarrage (fin du `start-dev` nu) ; mise à jour README/docs.

**Critères d'acceptation.**
- Les 13 specs E2E passent sur le compose sans GeoNode/Superset/Redis.
- Un item partagé à un groupe est visible par ses membres et invisible aux autres
  (testé E2E) ; un item publié est accessible anonymement en runtime, un non publié
  renvoie 404.
- Chaque création/modification/suppression/partage apparaît dans `audit_log`.
- `docker compose up` : shell + cœur + PostGIS + MinIO + Martin + TiTiler +
  Keycloak + Traefik + PgBouncer, et rien d'autre.

**Risques.** Le plus gros SP « invisible » de la route — mitigé par les 4
sous-phases livrables et le filet E2E. L'enforcement du partage est le morceau à
tester le plus durement (c'est de la sécurité, et le produit sera public).

---

### SP-2 — Serveur MCP v0

**Objectif.** GeoStudio est opérable par un agent : la démo « ouvre Claude, dis
*crée-moi un dashboard de suivi des incidents par commune*, obtiens une app dans le
catalogue » fonctionne.

**Contenu.**
- Serveur MCP intégré au cœur (arbitrage A13) exposant en v0 : `list_items`,
  `get_item`, `get_app_config`, `save_app_config` (avec révision), `create_item`,
  `get_sharing/set_sharing` — c'est-à-dire strictement l'API existante, ni plus ni
  moins de droits (authentification = token de l'utilisateur).
- Les schémas JSON d'`AppConfig`/`MapConfig` publiés (JSON Schema) — ils servent au
  MCP, à la validation serveur, et plus tard à la génération par IA.
- `actor_kind = agent` dans `audit_log` pour toute action MCP.

**Critères d'acceptation.** Un client MCP standard liste les items, lit une config,
crée un dashboard valide (validé par schéma) qui s'ouvre dans le builder ; l'action
est auditée avec son origine agent.

**Risques.** Faibles ; le danger est le scope creep (« et si l'agent pouvait
aussi… ») — v0 = miroir de l'API, point.

---

### SP-3 — Collections & CRUD features (écriture de données)

**Objectif.** Le cœur sait *écrire des données métier* dans PostGIS avec
permissions — le prérequis absolu des formulaires (SP-4). C'est ici que le produit
cesse d'être en lecture seule.

**Contenu.**
- Module `collections` : registre des couches éditables (table PostGIS, schéma
  introspecté : champs, types, contraintes, géométrie) ; `listLayerSources`
  branché dessus.
- Introspection de schéma exposée (`GET /collections/{id}/schema`) — alimentera la
  génération de formulaires.
- CRUD features selon A4 (create/update/delete, validation par schéma, géométrie
  optionnelle), permissions par collection (réutilise groupes×rôles de SP-1c),
  RLS selon A3.
- La lecture reste sur pg_featureserv tant que la parité n'est pas atteinte ;
  bascule de `queryDataSource/featuresUrl` vers le cœur en fin de SP, puis retrait
  de pg_featureserv du compose.
- Tables de démo (`incidents`, `points_interet`) déclarées comme collections
  éditables.

**Critères d'acceptation.** Un `editor` crée/modifie/supprime une entité via l'API
(géométrie comprise) ; un `viewer` reçoit 403 ; les écritures sont auditées ;
Martin voit les modifications immédiatement (tuiles) ; pg_featureserv n'est plus
dans le compose.

**Risques.** La généricité du CRUD (types PostGIS variés) peut enfler — v1 limitée
aux types courants (text, num, bool, date, enum/domaine, point/ligne/polygone).

---

### SP-4 — Formulaires dans le builder (le cran Retool n° 1)

**Objectif.** Le cas d'usage n° 1 décidé : une app métier qui *écrit* — créée sans
code.

**Contenu.**
- Widget **Formulaire** : généré depuis le schéma d'une collection (A9), champs
  typés (texte, nombre, date, booléen, liste de valeurs, géométrie via clic carte),
  labels/ordre/masquage configurables, validation déclarative (requis, min/max,
  motif) exécutée client **et** serveur.
- Nouvelles actions du bus : `feature.create`, `feature.update`, `feature.delete`,
  `form.submit`, `form.reset` — câblées comme les actions existantes
  (triggers→actions), avec états succès/erreur.
- Sélection → édition : une Table ou une Carte peut envoyer « l'entité
  sélectionnée » vers un Formulaire (réutilise le bus et les variables).
- Rafraîchissement des data sources après écriture (invalidation TanStack Query).
- Template « Application de saisie » dans la galerie.

**Critères d'acceptation (E2E).** Créer dans le builder une app « déclarer un
incident » (formulaire + carte + table) sans code ; en runtime : créer une entité,
la voir apparaître sur la carte et dans la table, la modifier depuis la sélection
table→formulaire, la supprimer. Un viewer ne voit pas les boutons d'écriture et le
serveur refuse ses écritures.

**Risques.** Le plus gros SP front. L'UX de liaison formulaire↔sélection est le
morceau dur — prototyper tôt dans la sous-phase 1.

---

### SP-5 — Expressions & actions composées

**Objectif.** La logique légère sans code : visibilité conditionnelle, champs
calculés, filtres dynamiques — l'équivalent ouvert du rôle d'Arcade chez Esri.

**Contenu.**
- Langage d'expressions selon A8, évaluable **côté client** (réactivité) et **côté
  serveur** (validation/MCP), avec le même vocabulaire : accès aux variables
  (`vars.x`), au record courant (`record.champ`), à l'utilisateur (`user.name`),
  fonctions de base (math, texte, date, logique).
- Points d'accroche dans les configs : `visibleWhen` (widgets), champs calculés
  (Texte, Indicateur, colonnes de Table), valeurs par défaut de formulaire,
  filtres de data sources paramétrés par expression — en remplacement/extension
  des bindings `{{champ}}`/`{{var:nom}}` actuels (compatibilité assurée).
- Actions composées : une action peut en déclencher plusieurs, avec condition
  (expression) — sans devenir un moteur de workflow (l'ETL déclaratif dédié est
  SP-17, A39 ; les actions composées restent un mécanisme d'app, pas un ETL).
- **Extension de périmètre 2026-07-09** (brainstorm Analytics, acté) :
  **bindings CEL généralisés** — toute prop de tout widget accepte une
  expression (`{ $expr: … }`) évaluée dans `WidgetHost` — et **variables
  typées** (string|number|bool|date|record|list) en remplacement des variables
  string actuelles ; `visibleWhen` et les champs calculés en deviennent des cas
  particuliers.

**Critères d'acceptation.** Un dashboard où un Filtre pilote par expression la
visibilité d'un widget et une colonne calculée, créé sans code, E2E vert ; une
expression invalide est signalée à l'édition (pas à l'exécution).

---

### SP-6 — Ingestion v1 : d'un fichier à une carte

**Objectif.** Le 2ᵉ cas d'usage de la vision (« publier une donnée → carte
partageable en minutes ») — et la première brique workers.

**Contenu.**
- File de jobs selon A5 + un worker conteneurisé (même image que le cœur).
- `POST /uploads` (GeoPackage, GeoJSON, CSV+lat/lon, Shapefile zippé) → job :
  validation (CRS, géométries), import PostGIS (pyogrio/GDAL), création de la
  collection + d'un item carte avec style par défaut raisonnable.
- Métadonnées extraites (emprise, nombre d'entités, champs) stockées sur la
  collection — champs alignés STAC selon A7 (sans prétendre à un catalogue STAC
  complet à ce stade).
- Suivi du job dans l'UI (états pending/running/done/error) ; génération PMTiles
  optionnelle pour les grosses couches (tippecanoe dans le worker).

**Critères d'acceptation.** Déposer un GPKG de 50 k entités → carte stylée visible
et partageable en < 5 min sans intervention ; l'échec d'un fichier corrompu produit
une erreur lisible, pas un job zombie.

---

### SP-7 — Recherche sémantique + MCP v1

**Objectif.** Le catalogue se cherche en langage naturel ; l'agent requête les
données.

**Contenu.**
- pgvector ; embeddings des métadonnées d'items/collections (titre, résumé,
  mots-clés, champs) calculés en job à chaque écriture ; **fournisseur
  d'embeddings enfichable** (API compatible OpenAI/Voyage ou modèle local) — la
  clé est l'interface, pas le choix initial.
- Recherche hybride du catalogue : trigram/BM25 + vecteur (+ filtre type/scope),
  branchée sur la barre de recherche existante du shell.
- MCP v1 : outils `search_catalog`, `query_features` (lecture, paginée, mêmes
  permissions), `create_form_app` s'appuyant sur les schémas de SP-3/SP-4.

**Critères d'acceptation.** « incidents voirie 2026 » trouve le bon dashboard même
sans mot exact ; un agent MCP compose une app formulaire fonctionnelle sur une
collection existante.

---

### SP-8 — SDK Web Components v1

**Objectif.** Le contrat de widget devient ouvrable à des tiers (décision Q13 :
Web Components d'abord) — sans réécrire les widgets internes.

**Contenu.**
- Contrat de widget **Web Component** (custom element + manifeste JSON : nom,
  props typées, events, taille par défaut) selon A10 ; le `WidgetHost` React sait
  monter un custom element et lui passer props/contexte (données, thème via CSS
  variables — déjà en place, actions via events).
- Chargement dynamique de modules ES (URL → import()) avec registre
  d'« extensions » côté cœur (item de type extension, activable par l'admin) ;
  **pas de sandbox dure en v1** : extensions *trusted* + permissions déclaratives
  (vision §5, compromis assumé).
- Le widget d'exemple `Compteur` porté en WC de référence ; guide « écrire un
  widget » ; le SDK React interne reste pour les widgets cœur.

**Critères d'acceptation.** Un widget WC développé hors du repo, servi comme module
ES, se charge dans le builder, reçoit des données, émet des actions, respecte le
thème — E2E incluse ; sa désactivation ne casse pas les apps qui l'utilisaient
(placeholder propre).

**Risques.** Frontière React↔WC (synchronisation props/events, SSR sans objet ici) ;
prototyper le pont sur le Compteur avant de figer le manifeste.

---

### SP-9 — Durcissement produit public (v0.1)

**Objectif.** Le dépôt devient un produit qu'un inconnu peut installer, évaluer et
contribuer.

**Contenu.**
- Licence selon A12 ; en-têtes, `CONTRIBUTING.md`, code of conduct.
- **Consolidation documentaire** (décidée au comparatif) : README réécrit autour de
  GeoStudio, couches G1/G2 archivées dans `docs/archive/`, `IMPLEMENTATION_PLAN.md`
  retiré (remplacé par cette feuille de route).
- CI publique : tests + E2E + build d'images versionnées (GHCR), semver, CHANGELOG.
- Install : `docker compose up` documenté avec seed de démo ; realm Keycloak
  provisionné ; mots de passe générés, plus de valeurs par défaut faibles.
- Sécurité minimale d'un produit exposé : revue authz (tests dédiés partage/
  publication/anonyme), en-têtes Traefik, rate limiting basique, dépendances
  auditées.
- Démo publique hébergée (mode lecture seule) — l'argument d'adoption n° 1 à
  défaut du profil 8 Go.

---

### SP-10 — Observabilité & SLO (OpenTelemetry)

**Objectif.** La plateforme s'exploite : traces, métriques et logs standards,
SLO packagés — en place au moment où la démo publique (SP-9) commence à recevoir
du trafic réel.

**Contenu.**
- **OTel SDK** dans le cœur et les workers : auto-instrumentation FastAPI /
  SQLAlchemy / httpx, spans sur les jobs procrastinate, logs structurés corrélés
  au `trace_id`. Export **OTLP** configurable par env — aucun backend imposé.
- **Profil compose optionnel** `--profile observability` : conteneur unique
  `grafana/otel-lgtm` (Grafana + Loki + Tempo + Mimir) — la référence (A26) ;
  OTLP standard pour brancher autre chose en production.
- **Dashboards packagés** : santé du cœur (latence API P95, taux d'erreur),
  tuiles Martin (ses métriques Prometheus existantes), jobs (backlog, échecs,
  durée), PostgreSQL de base.
- **SLO définis + alertes préconfigurées** : latence API Features P95 < 200 ms,
  latence tuiles P95 < 50 ms, backlog de jobs sous seuil, taux 5xx < 1 %.
  (La fraîcheur CDC s'y ajoute en SP-11.)
- Quelques métriques métier : items créés, apps publiées, exécutions runtime.

**Critères d'acceptation.** `docker compose --profile observability up` →
dashboards alimentés sans configuration ; une requête lente est traçable de bout
en bout (shell → cœur → SQL) ; les 4 SLO sont visibles et une alerte de test se
déclenche.

**Risques.** En faire trop : c'est une *référence d'exploitation* packagée, pas
une plateforme d'observabilité. Le périmètre est celui des dashboards/SLO listés,
point.

---

### SP-11 — Lakehouse & CDC (GeoParquet, DuckDB)

**Objectif.** L'étage analytique de la vision : PostGIS (chaud) répliqué en
continu vers GeoParquet sur MinIO (froid), interrogé par DuckDB dans le cœur.
Le SIG rejoint la data platform.

**Contenu.**
- **Worker CDC** (A16) : slot de réplication logique PostgreSQL (pgoutput),
  décodage des changements, écriture **GeoParquet partitionné** (collection +
  temps), tombstones pour les suppressions, checkpointing et reprise sur panne ;
  **backfill initial** par snapshot de table. Spike de validation en ouverture
  de phase.
- **Layout lakehouse** (A17) : GeoParquet plat + convention de partitionnement
  documentée ; job de **compaction** planifié (procrastinate). Iceberg différé
  (réévalué quand le versioning de données §13.2 montera).
- **Module analytique du cœur** : DuckDB in-process (extension spatiale + httpfs
  vers MinIO) ; **API d'agrégation structurée** (A19) — group-by, mesures,
  filtres attributaires et spatiaux simples — consommée par les widgets
  stats/charts (remplace l'agrégation client actuelle de `queryDataSource`).
- **Endpoint SQL read-only sandboxé** réservé au rôle *analyste* (A19) : vues
  autorisées par les permissions, quotas, timeout.
- **SLO de fraîcheur CDC** (branché sur SP-10) : lag chaud→froid < 5 min.
- DuckDB-**WASM** navigateur explicitement différé (A18) — deuxième étage, après
  stabilisation du serveur.

**Critères d'acceptation.** Une écriture PostGIS (formulaire SP-4) est visible
dans le GeoParquet en < 5 min, suppressions comprises ; un widget Graphique
agrège ~1 M de lignes en < 2 s via l'API analytique ; un analyste exécute du SQL
read-only sur ses vues autorisées, un non-analyste reçoit 403 ; le lag CDC est
visible dans les dashboards SP-10.

**Risques.** Le CDC est le morceau le plus délicat de toute la feuille de route
(slots qui gonflent le WAL, redémarrages, évolutions de schéma). Mitigation :
spike d'ouverture, monitoring du lag dès le premier jour, procédure de
re-backfill documentée ; en v1, un `ALTER TABLE` déclenche un re-backfill de la
collection (pas de schema evolution incrémentale).

---

### SP-12 — Catalogue interopérable : STAC, DCAT, moissonnage

**Objectif.** Le catalogue GeoStudio se lit avec les standards (STAC, DCAT) et
lit les autres catalogues (moissonnage) — « le catalogue référence les assets là
où ils sont ».

**Contenu.**
- **API STAC native dans le cœur** (A20) : classes de conformité progressives
  (core → collections → item-search) sur les tables items/collections
  existantes, mapping documenté ; conformité vérifiée par `stac-api-validator`
  en CI ; la visibilité suit les permissions (le STAC anonyme n'expose que le
  publié).
- **Export DCAT-AP** JSON-LD moissonnable (A21), validé contre le validateur
  data.gouv.fr — l'obligation open-data des collectivités couverte à peu de
  frais.
- **Moteur de moissonnage** : sources déclaratives (`harvest_sources` : type,
  URL, planification, mode) exécutées en jobs procrastinate ; **référencement
  pur par défaut, copie opt-in** par source (A23) qui route vers le pipeline
  d'ingestion SP-6. Items moissonnés typés « référence externe » (source, lien,
  fraîcheur, re-moissonnage).
- **Connecteurs** (A22 — les quatre retenus), *chacun livrable séparément et
  dans cet ordre* : ① catalogues STAC externes ; ② WMS/WFS GetCapabilities
  (référencer un GeoServer existant en secondes) ; ③ CSW/ISO 19139
  (GeoNetwork/geOrchestra — parser tolérant, champs minimaux) ; ④ CKAN/
  data.gouv.fr.
- UI : administration des sources, badge « externe » sur les items, ajout d'une
  couche moissonnée (WMS/WFS) à une carte sans copie.

**Critères d'acceptation.** QGIS (plugin STAC) navigue le catalogue ; l'export
DCAT-AP passe le validateur data.gouv.fr ; une source GeoNetwork et un GeoServer
sont moissonnés, cherchables, et une couche WMS moissonnée s'affiche dans une
carte ; le re-moissonnage met à jour sans dupliquer.

**Risques.** L'hétérogénéité ISO 19139 (profils, encodages) — parser tolérant et
périmètre de champs minimal assumé. Quatre connecteurs = risque d'étalement :
chaque connecteur est un incrément autonome, on peut s'arrêter entre deux.

---

### SP-13 — 3D & impression

**Objectif.** Des maquettes 3D (3D Tiles) et du terrain dans les cartes ; des
exports PNG/PDF mis en page depuis n'importe quelle carte ou app.

**Contenu 3D** (A24) :
- Type de couche `tiles3d` dans `MapConfig` ; rendu **deck.gl `Tile3DLayer`**
  (loaders.gl) dans le MapView existant — pas de deuxième moteur carto ;
  contrôles caméra (pitch/bearing) dans l'éditeur.
- **Terrain** : source raster-dem MapLibre alimentée par un DEM COG servi par
  TiTiler (déjà dans la stack) ; interrupteur terrain dans l'éditeur de carte.
- Hébergement de tilesets 3D Tiles *existants* : upload (zip) → S3 → item ;
  la **conversion** (py3dtiles, nuages de points…) est différée.

**Contenu impression** (A25) :
- **Worker d'export** : Playwright headless rend la vraie page runtime
  (carte ou app) → PNG haute résolution / PDF — WYSIWYG exact des styles
  MapLibre. Écart assumé avec la vision (QGIS Server), documenté : le print
  « pro » (CMJN, très hautes résolutions) attendra une demande réelle.
- **`PrintLayout` déclaratif** (encore une config) : format A4/A3
  portrait/paysage, titre, légende, barre d'échelle, flèche nord, cartouche.
- Bouton « Exporter » (visionneuse et runtime) → job asynchrone → lien de
  téléchargement (S3 présigné).

**Critères d'acceptation.** Un tileset 3D Tiles public s'affiche, terrain
activé, navigable à > 30 fps sur un poste moyen ; export PDF A3 d'une carte avec
légende et échelle correctes ; export d'un dashboard multi-widgets fidèle au
rendu écran.

**Risques.** Réglage du screen-space error de `Tile3DLayer` selon les tilesets ;
Playwright alourdit l'image du worker (image worker dédiée à l'export).

---

### SP-14 — Analytics UX : datasets, requête visuelle, contexte global

> Ajouté le 2026-07-09 (brainstorm
> [Analytics Platform](./2026-07-09-brainstorm-geostudio-analytics-platform.md)
> §7, vague 1). Position relative à SP-12/SP-13 : à arbitrer avant lancement
> (A27 amendé).

**Objectif.** La BI géospatiale sans code : un agent non technicien répond à une
question spatiale (« combien d'incidents à moins de 500 m d'une école, par
commune, ce trimestre ? ») sans SQL, sur l'API analytique de SP-11.

> **Amendement 2026-07-22 (A39) :** la partie **« pipeline de transformations
> déclaratif »** ci-dessous **migre vers SP-17** (ETL no-code) — le document
> `Pipeline` de SP-17 EST ce pipeline, avec un `writer.dataset`. SP-14 conserve
> l'UX analytique (requête visuelle, contexte global, cross-filter, SQL Lab) et
> consomme les datasets produits par le moteur de SP-17. Pas deux moteurs de
> transformation (règle d'archi #3).

**Contenu.**
- **Datasets partagés** (A28) : nouveau type d'item (catalogué, partageable via
  `can()`, versionné, audité) = source + pipeline de transformations déclaratif
  (filter attributaire/spatial/CEL, aggregate, join, derive, pivot, opérations
  spatiales packagées : buffer, countWithin, intersection, agrégation H3) +
  métriques nommées CEL + libellés métier + `refreshPolicy` (à la demande /
  intervalle / matérialisation planifiée). **Le moteur de ce pipeline est
  livré par SP-17 (A39)** ; SP-14 en est le premier consommateur. Datasets
  inline conservés dans les apps ; « promouvoir en dataset partagé » depuis le
  builder. Le type `statistics` actuel (agrégation client) migre vers le
  pipeline serveur.
- **Requête visuelle** (Filtrer → Joindre → Résumer → Trier) compilant vers
  l'API analytique structurée (A19) — jamais de SQL fabriqué côté client ;
  suggestions de visualisation depuis le schéma introspecté (SP-3).
- **Contexte analytique global** : temps × emprise × filtres × sélection ;
  cross-filter par défaut sur les nouvelles apps (`interactions: "auto"`,
  `manual` pour les configs migrées) ; réactivité à l'emprise **opt-in par
  dataset** avec refetch au déplacement activable en config (A29) ; état
  sérialisable dans l'URL + bookmarks (« situations » partageables).
- **Widgets analytiques** : KPI card riche (delta vs référence, sparkline,
  seuils CEL), tableau croisé/pivot (agrégation serveur), nouveaux types
  ECharts (sankey, treemap, sunburst, funnel, histogramme binné serveur),
  séries temporelles avec comparaison de périodes, filtres typés
  (select/date-range/slider alimentés par dataset), carte analytique
  (MapConfig complet + symbologie pilotée par dataset via les mêmes
  `encodings` que les charts), conteneurs (onglets/modale/tiroir).
- **SQL Lab** : l'UI de l'endpoint SQL read-only du rôle analyste (A19) —
  éditeur, historique, « enregistrer comme dataset ».
- **Source `arcgis`** : référencement d'un Feature Service comme source de
  dataset (la partie moissonnage/copie reste en SP-12, A22 amendé).
- MCP : outils `create_dataset`, `run_analytics_query`, `explain_dataset`.

**Critères d'acceptation (E2E).** La question spatiale type ci-dessus est
résolue sans code (requête visuelle → dataset → widgets) ; un clic sur une
barre filtre le dashboard entier ; « voir les entités » ouvre les lignes
sous-jacentes (table + carte) ; un dataset partagé alimente deux apps
distinctes ; un analyste sauve une requête SQL comme dataset consommé ensuite
par un non-analyste ; les configs v1 existantes s'ouvrent sans régression
(migration automatique, E2E existantes vertes).

**Risques.** L'API analytique qui enfle en ORM (garde-fou : périmètre fermé par
version ; la soupape est le SQL analyste) ; le cross-filter qui surprend
(garde-fou : `manual` par défaut sur l'existant) ; le SP le plus large de la
route — sous-phases livrables obligatoires à la rédaction du plan.

---

### SP-15 — Alertes & reporting : la plateforme prévient

> Ajouté le 2026-07-09 (brainstorm §7, vague 2). Dépend de SP-14 (datasets, API
> analytique) et du worker d'export de SP-13.

**Objectif.** Le decision support qui sort de l'écran : rapports planifiés
diffusés, alertes de seuil, exports — sur les droits du propriétaire, audité.

**Contenu.**
- **`AlertRule`** (objet déclaratif) : dataset + condition CEL (+ prédicats
  spatiaux — géofencing léger : entité dans zone, sortie de périmètre) +
  fréquence + canaux email/webhook avec gabarit de message ; évaluée en jobs
  procrastinate ; états ok/firing, historique, tout dans `audit_log` ; droits
  du propriétaire, quotas par tenant.
- **`ReportSchedule`** : cible app/page + état analytique figé (bookmark) +
  format + cron + destinataires → worker Playwright (SP-13) → S3 présigné →
  email/webhook. PDF de dashboards paginés (en-tête/pied, sauts de page par
  section).
- **Exports secs** (A30) : CSV/XLSX côté serveur (DuckDB `COPY TO`), par widget
  ou par dataset, permissions `can()` ; menu « explorer » des widgets (export
  CSV/PNG du widget). Classeurs mis en forme (gabarits) différés (§9).

**Critères d'acceptation (E2E).** Un rapport hebdomadaire PDF arrive par email
avec l'état analytique attendu ; une alerte de seuil se déclenche en < 5 min et
se journalise ; un export XLSX d'un dataset de 100 k lignes respecte les
permissions ; un utilisateur sans droit sur le dataset ne reçoit rien.

**Risques.** Surface d'abus (spam, exfiltration) — quotas, canaux validés,
audit systématique ; scope creep du reporting (gabarits, CMJN, éditeur de mise
en page) — différé explicite, la demande réelle décidera.

---

### Quick win — Storytelling (hors SP, livrable immédiatement)

> Ajouté le 2026-07-14 (arbitrages A36/A37, tranchés par Tanguy). Ne dépend
> d'aucun SP ; peut être livré dès maintenant, en parallèle de SP-9. Spec
> détaillée :
> [`2026-07-14-storytelling-pagemanager-design.md`](../superpowers/specs/2026-07-14-storytelling-pagemanager-design.md).

**Objectif.** Un auteur active un mode narratif sur une app existante, sans
code : les pages deviennent des chapitres séquencés (barre de progression,
navigation précédent/suivant), chacun pouvant piloter la carte vers une
emprise cible à l'entrée (réutilise `map.flyTo`, déjà câblé depuis SP-0d3).

**Contenu.** `AppConfig.navigationMode?: "tabs" | "story"` (défaut `tabs`,
rétrocompatible) ; mode de layout sur `PageManager` existant (**A36** : pas de
nouveau widget conteneur) ; `PageConfig.onEnter?: ActionMessage[]` qui réutilise
`ActionBus.emit` et la validation de conditions déjà en place (SP-5b) ; gabarit
de galerie « Story cartographique ».

**Critères d'acceptation.** Une story cartographique de 3 chapitres, créée
sans code, où la carte vole d'une emprise à l'autre à chaque chapitre ; les
apps existantes (sans `navigationMode`) restent inchangées.

**Risques.** Quasi nuls — réutilisation stricte de briques déjà testées
(`ActionBus`, `ActionsPanel`, validation d'expressions) ; aucune nouvelle
brique cœur.

---

### SP-16 — Portails & Sites

> Ajouté le 2026-07-14 (arbitrages A31/A33–A35/A38, tranchés par Tanguy —
> gap analysis dataviz/analytics/BI/portails). Chantier dédié (**A35**),
> exécuté après SP-11, avant SP-12/SP-13 (**A34**). Spec détaillée :
> [`2026-07-14-sp16-portails-sites-design.md`](../superpowers/specs/2026-07-14-sp16-portails-sites-design.md).

**Objectif.** GeoStudio dote son catalogue d'une façade publique de marque —
le manque structurel face à ArcGIS Hub/CKAN/data.gouv.fr thématiques
(argument commercial direct pour la cible collectivités, persona n° 8). Un
admin construit, sans code, un portail : page d'accueil éditoriale, galerie
de découverte filtrable des items publiés, fiches de jeux de données
téléchargeables.

**Contenu.**
- Nouveau type d'item **`site`** (à côté d'app/dashboard/map) — même table
  `items`, même `can()`, même `audit_log`, mêmes révisions de config ; aucun
  nouveau module cœur, extension du module `items` existant.
- `items.slug` (unique par tenant), route publique `GET /public/sites/{slug}`
  (miroir exact de `GET /public/items/{id}`, même politique d'accès anonyme,
  404 si non publié — jamais 403).
- Nouveaux widgets de contenu, disponibles pour tout type d'item : `Hero`,
  `RichSection` (markdown simple), `Gallery` (découverte filtrable par
  tag/type), `DatasetCard`/`DatasetPage` (fiche + téléchargement).
- Téléchargement v1 volontairement limité : GeoJSON (OGC API Features déjà
  exposée, SP-3) + CSV client-side sous un seuil de volumétrie explicite —
  export DCAT-AP/STAC (SP-12) et export serveur gros volumes (SP-15) upgradent
  ce module plus tard, sans le bloquer aujourd'hui.
- **Domaine personnalisé et fonctions communautaires (commentaires, follow,
  discussions) explicitement différés** (A33/A38) — accès v1 via
  `/sites/{slug}`, portail catalogue+éditorial seulement.

**Critères d'acceptation.** Un admin publie un portail (accueil + galerie +
au moins une fiche dataset téléchargeable) sur une URL stable ; un visiteur
anonyme le parcourt et télécharge un jeu de données sans jamais voir un item
non publié ; aucun chemin ne contourne `can()`/la politique de publication
existante (vérifié en revue finale de branche, comme chaque SP touchant à la
sécurité depuis SP-1c).

**Risques.** Confusion de tenant par résolution de slug (mitigé par un test
d'isolation tenant×slug dédié, symétrique aux matrices rôle×action déjà
exigées) ; dérive vers un CMS complet (périmètre `RichSection` fermé
explicitement à un bloc markdown simple) ; étalement du chantier (sous-phases
livrables obligatoires à la rédaction du plan, sur le modèle SP-4/SP-8).

---

## 7. Points d'arbitrage technique

Chaque point : options, avantages/inconvénients, recommandation. Les décisions
sont consignées en §8.

### A1 — Moteur d'autorisation v0 (SP-1c)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Tables maison + moteur in-process** (item_shares, rôles ; une fonction `can(user, action, object)` unique) | Simple, transactionnel, zéro composant d'état en plus ; suffisant pour le modèle privé/groupe/public actuel ; testable unitairement | À remplacer si le partage devient hiérarchique (héritage dossiers/espaces) ; discipline requise pour que `can()` reste l'unique porte |
| (b) OpenFGA dès v0 | Modèle ReBAC cible de la vision, héritages gratuits | Un service d'état de plus à opérer, réseau dans le chemin de chaque check, surdimensionné pour 3 types d'objets ; contraire au minimalisme v0 |
| (c) Tout dans Postgres RLS | Enforcement au plus près de la donnée | RLS sur les tables *du cœur* complexifie chaque requête/migration pour un bénéfice faible (le cœur est l'unique client de sa base) ; RLS pertinente pour les *données métier* (voir A3) |

**Recommandation : (a)**, avec `can()` comme unique point d'entrée pour pouvoir
brancher OpenFGA plus tard sans toucher les routes.

### A2 — Source de vérité des groupes (SP-1c)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Groupes gérés par le cœur** (tables + UI d'admin minimale) | Indépendant de l'IdP (un déployeur peut fédérer son AD sans que ses groupes SIG en dépendent) ; pas d'appel admin Keycloak ; modèle simple | Deux notions de groupe coexistent (IdP vs produit) ; une UI d'admin à faire (minimale) |
| (b) Groupes Keycloak (claims du token + admin API) | Zéro duplication ; l'admin gère tout dans Keycloak | Couplage fort à l'IdP (contraire à « identité déléguée, autorisation maison ») ; l'admin API Keycloak est pénible ; les partages cassent si on change d'IdP ; claims à synchroniser |

**Recommandation : (a)** — c'est aussi le modèle GeoNode actuel, donc le moindre
mouvement pour l'UX existante (`ShareDialog`).

### A3 — Row-Level Security PostGIS : quand ? (SP-1 vs SP-3)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Pas de RLS en SP-1 ; RLS sur les données métier en SP-3** (politiques générées par collection au moment où l'écriture arrive) | Vélocité SP-1 ; la RLS arrive là où elle paie (données métier requêtables par d'autres clients : Martin, DuckDB demain) | Fenêtre où l'enforcement est purement applicatif ; double logique à terme (can() + RLS) à garder cohérente |
| (b) RLS partout dès SP-1 | Un seul modèle dès le début ; défense en profondeur immédiate | Coût notable sur chaque migration/test du cœur ; Martin/pg_featureserv se connectent en rôle applicatif unique aujourd'hui — le bénéfice réel n'arrive qu'avec des rôles par requête (travail en plus) |

**Recommandation : (a)** — en notant que Martin devra à terme passer par des vues
ou un rôle par tenant pour que la RLS serve aussi les tuiles.

### A4 — Forme de l'API d'écriture des features (SP-3)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) OGC API Features Part 1+4 dans le cœur** | Standard (QGIS et l'écosystème parlent nativement) ; remplace pg_featureserv (un service de moins) ; cohérent avec la vision (« OGC comme surface ») | Spécification à respecter sérieusement (CRS, ETags, collections) — plus de travail qu'un REST maison ; Part 4 encore peu implémentée côté clients (mais c'est nous le serveur) |
| (b) REST maison (`/collections/{id}/features` non conforme) | Le plus rapide ; taillé pour le builder | Dette : une 2ᵉ API à faire le jour où l'interop QGIS/tiers compte ; à contre-courant de la vision |
| (c) Intégrer pygeoapi | OGC clef en main (Features, bientôt Processes) | 3ᵉ application Python à héberger/configurer ; auth/permissions à câbler dedans (plugins) ; perte du contrôle transactionnel fin avec `can()`/audit |

**Recommandation : (a)** — en implémentant le sous-ensemble utile d'abord (GeoJSON,
CRS84 + déclaration des CRS courants), conformité progressive.

### A5 — File de jobs / workers (SP-6, anticipé si besoin en SP-3)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) procrastinate** (file Postgres native, async, Python) | Zéro broker (Postgres = la file, aligné vision « pas de dépendance de plus ») ; lib maintenue, retries/planification inclus | Moins d'écosystème que Celery ; débit plafonné par Postgres (sans objet à notre échelle) |
| (b) Celery + Redis | Standard de fait, docs infinies | Réintroduit Redis comme infra *critique* (qu'on vient de sortir) ; ergonomie async datée |
| (c) File maison SKIP LOCKED | Contrôle total, ~200 lignes | Réinventer retries, visibilité, planification, instrumentation — du code à maintenir sans valeur produit |

**Recommandation : (a).**

### A6 — Vignettes et fichiers (SP-1b, SP-6)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) MinIO/S3 avec URLs présignées** (upload et lecture directs) | Le cœur hors du chemin des octets ; scalable ; pattern standard | Les vignettes d'items *privés* deviennent lisibles par quiconque a l'URL pendant sa validité (acceptable pour des vignettes) ; CORS/config MinIO à soigner |
| (b) Proxy via le cœur | Contrôle d'accès exact par requête ; plus simple à configurer en dev | Chaque image transite par Python ; à proscrire pour les uploads de données (SP-6) |

**Recommandation : (a)** pour les uploads de données ; au choix pour les vignettes
(petits volumes — le proxy est défendable en v0 pour sa simplicité).

### A7 — Métadonnées : minimal d'abord ou STAC-first (SP-1, SP-6)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Modèle items minimal v0, champs alignés STAC à l'ingestion (SP-6), catalogue STAC complet différé** | SP-1 reste petit ; on n'expose pas un STAC à moitié vide ; les champs (bbox, datetime, assets) restent compatibles | L'interop catalogue (STAC browser, QGIS STAC) attend ; risque de « on le fera jamais » |
| (b) STAC-first dès v0 (stac-fastapi ou modèle STAC natif) | Interop immédiate ; le modèle item est « déjà juste » | Alourdit SP-1 (le SP le plus risqué) ; STAC modélise mal apps/dashboards (nos items majoritaires aujourd'hui) — il faudrait deux modèles quand même |

**Recommandation : (a)** — STAC est le bon habit pour les *données* (SP-6+), pas
pour les configs d'apps.

### A8 — Langage d'expressions (SP-5)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) CEL** (cel-python côté serveur, cel-js côté client) | Recommandé par la vision ; sandboxable par construction, analysable, bien généré par les LLM ; même sémantique client/serveur | Deux implémentations (Python/JS) à garder alignées ; cel-js moins mûr que l'implémentation Go de référence — à valider par un spike |
| (b) JSONLogic | Trivial à embarquer des deux côtés ; AST JSON (facile à générer/valider) | Expressivité vite limitée (pas de vraies fonctions texte/date sans extensions maison) ; illisible à la main dès que ça grossit |
| (c) JS sandboxé (QuickJS-wasm / SES) | Puissance maximale, familiarité | Sandboxing sérieux difficile (le compromis que la vision refuse) ; non analysable ; évaluation côté serveur lourde |

**Recommandation : (a)** avec un spike de validation de cel-js en ouverture de
SP-5 ; repli (b) si le spike échoue, en gardant la syntaxe CEL comme cible.

### A9 — Génération des formulaires (SP-4)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Schema-driven** : formulaire généré depuis le schéma de la collection (SP-3), personnalisation par overrides dans la config | Aligné vision §13.4 ; le formulaire suit les évolutions du schéma ; validation serveur gratuite (même source) | Exige l'introspection propre (SP-3) ; les cas exotiques passent par overrides (à borner) |
| (b) Formulaires configurés champ par champ à la main | Contrôle total de l'auteur ; plus simple à implémenter au début | Dérive schéma↔formulaire silencieuse ; deux fois plus de config à écrire ; la génération par IA y perd sa source de vérité |

**Recommandation : (a)** — les overrides couvrant labels, ordre, masquage, widgets
de saisie.

### A10 — Technique Web Components (SP-8)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Contrat WC natif (Lit ou vanilla) pour les tiers ; widgets internes restent React derrière un pont WidgetHost↔WC** | Le contrat public est propre (zéro React exposé) ; pas de réécriture interne ; Lit = 5 Ko, standard | Un pont à écrire et tester (props/events/slots) ; deux façons d'écrire un widget coexistent en interne |
| (b) Wrapper automatique React→WC (@r2wc) pour tout | Très rapide ; un seul modèle interne | Le contrat public embarque React en douce (bundle, versions) ; fuites d'abstraction (events synthétiques) ; exactement le défaut « framework figé » reproché à Experience Builder |
| (c) Réécrire tous les widgets en WC | Un seul modèle, pur standard | Coût énorme sans valeur utilisateur ; risque de régression sur l'acquis testé |

**Recommandation : (a).**

### A11 — Client API TypeScript du shell (SP-1d)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Types générés depuis l'OpenAPI du cœur** (openapi-typescript), `CoreItemClient` écrit à la main par-dessus | Dérive front/back détectée à la compilation ; l'OpenAPI devient un contrat de premier ordre (aussi pour le MCP et les tiers) | Une étape de génération dans la CI ; l'interface `ItemClient` reste à mapper à la main (souhaitable : c'est la façade) |
| (b) Client manuel (statu quo) | Zéro outillage | La dérive ne se voit qu'à l'exécution ; le contrat vit dans deux têtes |

**Recommandation : (a).**

### A12 — Licence (SP-9, mais à afficher dès que le repo devient public)

| Option | Avantages | Inconvénients |
|---|---|---|
| (a) Apache-2.0 | Adoption maximale (entreprises, intégrateurs) ; clause brevets ; standard de l'écosystème cloud-native | Un tiers peut vendre un SaaS fermé de GeoStudio sans contribuer |
| **(b) AGPL-3.0** | Défensif : le SaaS d'un tiers doit republier ses modifications ; compatible modèle open-core futur (vous restez libre de vendre des exceptions) ; précédents SIG (QGIS/GeoServer sont GPL) | Certaines entreprises l'interdisent (frein d'adoption) ; demande une gestion propre des CLA si open-core un jour |
| (c) MIT | Simplicité maximale | Ni clause brevets ni défense SaaS |

**Recommandation : (b) AGPL-3.0** pour un produit-plateforme public dont le risque
n° 1 est la captation SaaS — avec les SDK/clients (types TS, futur SDK widgets)
sous **Apache-2.0/MIT** pour ne pas contaminer les apps des utilisateurs.

### A13 — Forme du serveur MCP (SP-2)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Module du cœur** (même process, SDK MCP Python, transport HTTP/streamable) | Mêmes permissions/audit sans plomberie ; pas de service en plus ; accès direct aux schémas | Couple le cycle de release du MCP à celui du cœur (acceptable : même produit) |
| (b) Service séparé consommant l'API publique | Découplage ; dogfooding de l'API | Un déploiement de plus ; latence ; duplication de l'authz si mal fait |

**Recommandation : (a)** — d'autant que (a) *force* l'API interne à rester propre.

### A14 — Structure du dépôt (SP-1a)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Monorepo, `builder-service/` renommé `core/`** (+ `shell/` inchangé) | Le nom dit ce que c'est ; un PR = front+back cohérents ; CI unique | Renommage à propager (compose, CI, docs) — une heure de grep |
| (b) Monorepo, noms inchangés | Zéro friction immédiate | « builder-service » devient un mensonge dès SP-1b (il gère les items) |
| (c) Repos séparés core/shell | Releases indépendantes | Overhead permanent (versions croisées, 2 CI) injustifié en solo |

**Recommandation : (a).**

### A15 — Données GeoNode existantes (SP-1d)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Repartir propre** (re-seed de démo ; pas de migration) | SP-1d plus court ; aucun déploiement de prod identifié à ce jour | Perte des items de test créés ; si un usage réel existe quelque part, il faut le savoir *maintenant* |
| (b) Script de migration GeoNode→cœur | Rien n'est perdu | Effort pour des données de dev ; le script vit une seule fois |

**Recommandation : (a)** — sauf si Q2 (premiers utilisateurs) révèle un déploiement
réel.

### A16 — Mécanisme de CDC (SP-11)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Réplication logique + worker maison** (slot pgoutput/wal2json lu par un worker qui écrit le GeoParquet) | Aucun composant en plus ; aligné vision (« CDC par logical replication ») ; contrôle total du format de sortie | Plomberie à écrire et durcir : gestion des slots, reprises, backpressure, WAL qui gonfle si le worker s'arrête |
| (b) Debezium Server | Éprouvé, gère slots/offsets/reprises | Une JVM de plus, configuration lourde, pensé pour Kafka (sinks limités sans lui) — à contre-courant du scale-down |
| (c) Synchro périodique (`updated_at`/exports) | Trivial | Pas du vrai CDC : suppressions ratées sans tombstones, fraîcheur en heures, double logique |

**Recommandation : (a)**, avec spike de validation en ouverture de SP-11 et
monitoring du lag dès le premier jour.

### A17 — Format des tables froides (SP-11)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) GeoParquet plat + partitionnement par convention, Iceberg plus tard** | Simple ; lisible partout (DuckDB, QGIS, pandas) ; zéro catalogue de tables à opérer ; l'option « simple » de la vision §3 | Pas de time-travel ni schema evolution — l'étage 1 du versioning de données (§13.2) attendra Iceberg ; compaction maison |
| (b) Iceberg dès le début (+ catalogue REST type Lakekeeper) | Time-travel jour 1, schema evolution, snapshots | Un service catalogue de plus ; écosystème Python encore mouvant ; complexité d'exploitation notable |

**Recommandation : (a)** — Iceberg est réévalué quand la brique versioning montera.

### A18 — Ordre d'exposition de l'analytique DuckDB (SP-11)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Serveur d'abord, WASM ensuite** | L'endpoint analytique du cœur profite immédiatement aux widgets stats/charts (remplace l'agrégation client), permissions contrôlées | Charge sur le cœur (mitigée : DuckDB in-process lit S3, cache) |
| (b) DuckDB-WASM navigateur d'abord | Zéro charge serveur ; exploration locale spectaculaire (démonstrateur de la vision) | Les parquet descendent au client (permission = fichier entier) ; sert l'analyste, pas les widgets |
| (c) Les deux dans la même phase | Cohérence | Double chantier — phase énorme, risque d'enlisement |

**Recommandation : (a).**

### A19 — Surface de requête analytique (SP-11)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) API structurée pour les widgets + SQL read-only sandboxé réservé au rôle analyste** | Widgets sûrs et générables par IA ; l'analyste (persona n° 2 de la vision) est servi ; périmètre contrôlé (vues autorisées, quotas, timeout) | Deux surfaces à maintenir |
| (b) SQL read-only pour tous | Puissance partout | Surface d'abus/DoS ; permissions à répliquer dans les vues ; UX non-analyste faible |
| (c) API structurée seulement | Minimal et sûr | Le pont vers la data platform perd son intérêt |

**Recommandation : (a).**

### A20 — Implémentation de l'API STAC (SP-12)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Routes STAC natives dans le cœur** (sur les tables items/collections existantes) | Une seule source de vérité ; permissions/audit natifs ; conformité progressive (core → collections → item-search) | La conformité est à notre charge (stac-api-validator en CI) |
| (b) pgstac + stac-fastapi monté dans le cœur | Éprouvé, item-search très performant | Deuxième modèle de données (schéma pgstac) à synchroniser : duplication, migrations doubles, permissions à rebrancher |
| (c) Service stac-fastapi séparé | Isolation | Contredit le monolithe modulaire ; même duplication + un déploiement de plus |

**Recommandation : (a).**

### A21 — Ambition DCAT (SP-12)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Export DCAT-AP moissonnable** (JSON-LD/RDF généré du catalogue) | Suffit à data.gouv.fr et aux portails open-data ; peu de code ; couvre l'obligation open-data des collectivités | Pas d'API DCAT complète ni SPARQL |
| (b) API DCAT complète | Interop maximale | Gros chantier pour très peu d'usage réel |
| (c) Différer | Focus | Argument commercial collectivités raté |

**Recommandation : (a).**

### A22 — Connecteurs de moissonnage v1 (SP-12)

Candidats : catalogues STAC externes · CSW/ISO 19139 (GeoNetwork) · WMS/WFS
GetCapabilities · CKAN/data.gouv.fr. Arbitrage sur *lesquels* et dans quel ordre —
chaque connecteur doit être un incrément livrable séparément (risque d'étalement).

**Recommandation : STAC d'abord** (modèle natif), puis GetCapabilities (valeur
immédiate pour les organisations équipées), CSW ensuite (valeur forte, parsing
pénible), CKAN en dernier (métadonnées géo pauvres).

> **Amendement 2026-07-09 (Q-A4, brainstorm Analytics)** : un **5ᵉ connecteur
> ArcGIS Feature Services** (référencement + copie via l'ingestion SP-6) entre
> dans A22, inséré en **2ᵉ position** — ordre final : STAC → **ArcGIS FS** →
> GetCapabilities → CSW/ISO → CKAN. Argument : la donnée existante des
> collectivités équipées Esri, le pont de sortie. Le *référencement* d'un
> Feature Service comme source de dataset arrive dès SP-14.

### A23 — Mode de moissonnage (SP-12)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Référencement pur + copie opt-in par source** | « Enregistrer ≠ copier » (vision) ; léger, frais ; la copie opt-in route vers l'ingestion SP-6 quand perfs/dispo l'exigent | Dépendance à la disponibilité des sources non copiées |
| (b) Copie systématique | Performances et disponibilité garanties | Contredit la vision ; stockage et resynchronisation permanents ; licences des données copiées |

**Recommandation : (a).**

### A24 — Moteur 3D (SP-13)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) deck.gl `Tile3DLayer` + terrain raster-dem MapLibre** | Réutilise l'overlay deck.gl déjà intégré ; 3D Tiles OGC via loaders.gl ; terrain depuis un DEM COG servi par TiTiler (déjà en stack) ; pas de 2ᵉ moteur | Pas de vrai globe ; photogrammétrie très lourde à la limite |
| (b) Viewer CesiumJS séparé | Globe complet, écosystème 3D le plus riche | Deuxième moteur à intégrer au builder (couches, styles, interactions dupliquées) — coût permanent |
| (c) Attendre la 3D native MapLibre | Zéro travail | Calendrier hors de notre contrôle |

**Recommandation : (a)**, CesiumJS réévalué si un besoin globe/photogrammétrie
réel apparaît.

### A25 — Voie d'impression/export (SP-13)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Rendu navigateur headless en worker** (Playwright rend la vraie carte → PNG/PDF, layouts déclaratifs) | WYSIWYG exact des styles MapLibre ; réutilise la stack ; les mises en page sont des configs | Print « pro » limité (CMJN, très hautes résolutions) — **écart assumé avec la vision (QGIS Server)**, documenté |
| (b) QGIS Server headless | Qualité cartographique professionnelle | Traduction permanente des styles MapLibre en projets QGIS — chantier de conversion sans fin ; conteneur lourd |
| (c) Navigateur d'abord, QGIS Server plus tard | Progressif, la demande décide | Deux systèmes à terme si le besoin pro se confirme |

**Recommandation : (a)** — bascule vers (c) uniquement sur demande réelle de
print professionnel.

### A26 — Stack d'observabilité de référence (SP-10)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) OTel SDK + profil compose `grafana/otel-lgtm`** | Instrumentation OTLP native ; un seul conteneur optionnel pour tout voir (aligné scale-down) ; dashboards/SLO packagés démontrables | L'image lgtm vise le dev/petite échelle (assumé : OTLP permet de brancher autre chose en prod) |
| (b) Stack Grafana complète séparée | Prod-grade d'entrée | 4–5 conteneurs à opérer et documenter — disproportionné comme référence |
| (c) Export OTLP seul, pas de backend fourni | Minimal | « SLO packagés » indémontrables ; l'exploitant débutant livré à lui-même |

**Recommandation : (a).**

### A27 — Séquencement des quatre chantiers (SP-10 → SP-13)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Après v0.1 : OTel → Lakehouse → STAC → 3D/print** | v0.1 sort tôt ; l'observabilité protège la démo publique ; puis data platform, catalogue, 3D | La différenciation data attend v0.1 |
| (b) Après v0.1 : Lakehouse d'abord, OTel par tranches | La valeur data arrive plus vite | Démo publique exploitée à l'aveugle au début |
| (c) Intercaler le lakehouse avant le SDK (SP-8) | Différenciation data plus tôt | Retarde v0.1 de plusieurs mois — contraire à « démontrable en continu » |

**Recommandation : (a).**

> **Amendement 2026-07-09 (Q-A3)** : SP-14 et SP-15 s'ajoutent après SP-11
> (leur socle). L'ordre relatif SP-12/SP-13/SP-14/SP-15 **reste à arbitrer**
> avant le lancement du premier d'entre eux ; seule contrainte : SP-15 requiert
> le worker d'export de SP-13.

### A28 — Datasets : objet de plateforme ou config privée aux apps (SP-14)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Dataset = objet de plateforme** (nouveau type d'item : catalogué, partagé via `can()`, versionné, audité) + datasets inline conservés dans les apps | Couche sémantique : métriques définies une fois, réutilisées partout ; gouvernance (changer la source ne casse pas N dashboards) ; cherchable (pgvector SP-7) ; générable/lisible par le MCP | Un type d'item de plus ; UI de gestion à construire |
| (b) Sources privées par app (statu quo étendu) | Zéro nouveau concept | Chaque dashboard redéfinit ses métriques ; aucune réutilisation ; dérive sémantique silencieuse |

**Décision (Q-A1, 2026-07-09) : (a).**

### A29 — Réactivité des datasets à l'emprise carte (SP-14)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Opt-in par dataset**, avec refetch à chaque déplacement de carte activable dans la config | Coût réseau/serveur maîtrisé par défaut ; le « stats sur ce que je vois » s'active là où il a du sens | Un réglage de plus à comprendre pour l'auteur |
| (b) Emprise dans le contexte global par défaut | Le geste SIG activé partout d'office | Refetch de tous les datasets à chaque pan/zoom — coût par défaut inacceptable |

**Décision (Q-A2, 2026-07-09) : (a).**

### A30 — Ambition des exports tabulaires (SP-15)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Export sec** CSV/XLSX (données brutes, DuckDB `COPY TO`) | Trivial à implémenter ; couvre l'essentiel du besoin réel | Pas de mise en forme |
| (b) Classeurs mis en forme (gabarits) | Rapports Excel « finis » | Moteur de gabarits à construire et maintenir — scope creep garanti |

**Décision (Q-A5, 2026-07-09) : (a)** — gabarits différés (§9), sur demande réelle.

### A31 — Modèle de config du portail/site (SP-16)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Sous-gabarit d'`AppConfig`** (nouveau type d'item `site`, même schéma de base, mêmes modes edit/preview/runtime) | Un seul runtime (règle n° 3) ; hérite instantanément de thèmes/pages/partage/MCP ; nouveaux widgets de contenu réutilisables partout | Le schéma `AppConfig` doit rester générique (widgets de contenu = nouveaux widgets, pas un fork de schéma) |
| (b) Nouveau type de config entièrement séparé | Liberté de modéliser une navigation multi-item différente | Deuxième runtime (viole la règle n° 3) ; double la surface de maintenance et de génération MCP |

**Décision (2026-07-14) : (a).**

### A33 — Domaine personnalisé par site (SP-16)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) V1 sans domaine personnalisé** (accès via `/sites/{slug}`) | Livrable rapidement, zéro complexité TLS/DNS multi-tenant à durcir tout de suite | Moins impressionnant face à ArcGIS Hub pour une démo commerciale |
| (b) Domaine personnalisé dès v1 | Argument de vente fort immédiat | Complexité TLS/DNS/routage multi-tenant à durcir avant toute exposition publique — risque de confusion de tenant par Host si mal isolé |

**Décision (2026-07-14) : (a)**, domaine personnalisé réévalué en v2 du
module une fois le routage multi-tenant par chemin éprouvé et audité.

### A34 — Séquencement de SP-16 vis-à-vis de SP-12/13/14 (amendement A27)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) SP-16 après SP-11, avant SP-12/13** | Le portail v1 s'appuie sur les items déjà publiés, n'a pas besoin du catalogue standard (SP-12) ni de la 3D/print (SP-13) pour son v1 | Le catalogue standard/3D restent en jachère plus longtemps que dans l'ordre A27 originel |
| (b) SP-16 après SP-12 (catalogue standard) | Alimente nativement les fiches dataset du portail en DCAT/STAC dès le départ | Retarde le portail sans raison technique — le v1 du portail assume déjà l'absence de DCAT (upgrade documenté) |
| (c) SP-16 après SP-14 (BI géospatiale) | Les portails embarquent d'emblée des widgets analytiques | Retarde un chantier commercialement stratégique (obligation open-data) sans nécessité technique |

**Décision (2026-07-14) : (a).** L'ordre relatif de SP-16 à SP-14 reste
libre (chantiers mutuellement indépendants) ; l'ordre relatif de SP-12/13/14
entre eux reste par ailleurs celui laissé ouvert par Q-A3 (A27).

### A35 — Structure du chantier Portails & Sites

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) SP-16 dédié** | Périmètre net, critères d'acceptation propres, évite de diluer SP-9 (déjà en cours) ou SP-12 (déjà chargé de 4-5 connecteurs, risque d'étalement documenté) | Un SP de plus à la feuille de route (≈ 60–100 h) |
| (b) Sous-lot de SP-12 (« le catalogue devient aussi un portail ») | Un SP de moins à nommer | Aggrave le risque d'étalement déjà noté sur SP-12 |
| (c) Sous-lot de SP-9 (durcissement v0.1) | Traité pendant la phase en cours | Retarderait la sortie v0.1, contraire au principe « ne pas toucher au chemin critique » |

**Décision (2026-07-14) : (a).**

### A36 — Storytelling : mode d'intégration au builder

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Mode de layout sur `PageManager`** (une app peut activer une navigation séquentielle scrollée sur ses pages existantes) | Zéro nouveau widget ; toute app peut devenir story a posteriori ; hérite du thème/des variables de l'app parente | Le mode doit rester optionnel et non intrusif pour le cas dashboard classique |
| (b) Nouveau widget conteneur « Story » dédié | Isolation du code, pas de risque de régression sur `PageManager` | Duplique la notion de page ; n'hérite pas gratuitement du thème/des variables de l'app parente |

**Décision (2026-07-14) : (a).**

### A37 — Storytelling : timing de livraison

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Quick win immédiat, indépendant** | Livrable dès maintenant, sans attendre SP-11/14/16 ; réutilise des briques déjà acquises (`PageManager`, CEL, `ActionBus`) | Aucun — c'est un quick win par construction |
| (b) Regroupé avec le chantier Portails & Sites (SP-16) | Une seule spec, un seul plan | Retarde inutilement une fonctionnalité qui ne dépend techniquement de rien dans SP-16 |

**Décision (2026-07-14) : (a).**

### A38 — Fonctions communautaires des portails (SP-16)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Différées, hors périmètre v1** (pas de commentaires, follow, discussions) | Catalogue + éditorial seulement — pas de charge de modération à porter tout de suite | Moins complet qu'ArcGIS Hub sur cet axe |
| (b) Incluses dès la v1 | Se rapproche davantage d'ArcGIS Hub complet | Surface d'abus/modération à gérer dès le départ, disproportionnée pour la cible (patrimoine territorial, pas réseau social) |

**Décision (2026-07-14) : (a)** — réévaluées sur demande réelle explicite.

---

## 8. Décisions d'arbitrage

> Arbitrages tranchés le **2026-07-04** (A1–A15), le **2026-07-05** (A16–A27,
> extension SP-10→SP-13) et le **2026-07-09** (A28–A30 + amendements A22/A27,
> extension SP-14/SP-15 — brainstorm Analytics Platform validé). Chaque décision
> est révisable *jusqu'au lancement du SP concerné*, figée ensuite (toute
> révision passe par une mise à jour explicite de ce document).

| # | Sujet | Décision | SP concerné |
|---|---|---|---|
| A1 | Autorisation v0 | **Tables maison + `can()` unique** (swap ReBAC possible plus tard) | SP-1c |
| A2 | Source des groupes | **Gérés par le cœur** (+ UI d'admin minimale) | SP-1c |
| A3 | RLS : quand | **SP-3, sur les données métier** (pas sur les tables du cœur) | SP-1/SP-3 |
| A4 | API d'écriture features | **OGC API Features dans le cœur** (sous-ensemble utile d'abord) | SP-3 |
| A5 | Jobs/workers | **procrastinate** (file Postgres, zéro broker) | SP-6 |
| A6 | Vignettes/fichiers | **Presigné S3 pour tout** (CORS/MinIO à soigner en SP-1b) | SP-1b/SP-6 |
| A7 | Métadonnées/STAC | **Items minimal v0, champs alignés STAC à l'ingestion** | SP-1/SP-6 |
| A8 | Expressions | **CEL**, spike cel-js d'1 jour en ouverture de SP-5, repli JSONLogic décidé d'avance | SP-5 |
| A9 | Formulaires | **Schema-driven + overrides** | SP-4 |
| A10 | Web Components | **Contrat WC natif (Lit) + pont React interne** | SP-8 |
| A11 | Client API TS | **Types générés depuis OpenAPI** (`CoreItemClient` manuel par-dessus) | SP-1d |
| A12 | Licence | **Apache-2.0 partout** ⚠ écart à la recommandation (AGPL) : on privilégie l'adoption maximale et on assume le risque de captation SaaS ; la différenciation commerciale future passera par la marque/les services, pas le copyleft | SP-9 (affichage dès publication) |
| A13 | Forme du MCP | **Module du cœur, même process** | SP-2 |
| A14 | Structure dépôt | **Monorepo, `builder-service/` renommé `core/`** dès SP-1a | SP-1a |
| A15 | Données existantes | **Repartir propre, re-seed de démo** (aucun déploiement réel à migrer) | SP-1d |
| A16 | Mécanisme CDC | **Réplication logique + worker maison** (spike d'ouverture, monitoring du lag) | SP-11 |
| A17 | Format froid | **GeoParquet plat + partitionnement** ; Iceberg réévalué avec le versioning de données | SP-11 |
| A18 | Exposition DuckDB | **Serveur d'abord** (API du cœur), WASM navigateur ensuite | SP-11 |
| A19 | Surface analytique | **API structurée pour les widgets + SQL read-only réservé au rôle analyste** | SP-11 |
| A20 | API STAC | **Routes natives dans le cœur** (conformité progressive, stac-api-validator en CI) | SP-12 |
| A21 | DCAT | **Export DCAT-AP moissonnable** (JSON-LD, validé data.gouv.fr) | SP-12 |
| A22 | Connecteurs moissonnage | **Les cinq** (amendé 2026-07-09) — ordre : STAC → **ArcGIS FS** → GetCapabilities → CSW/ISO → CKAN | SP-12 (réf. comme source de dataset dès SP-14) |
| A23 | Mode moissonnage | **Référencement pur + copie opt-in par source** | SP-12 |
| A24 | Moteur 3D | **deck.gl `Tile3DLayer` + terrain raster-dem MapLibre** | SP-13 |
| A25 | Impression | **Rendu navigateur headless (Playwright) en worker** ⚠ écart assumé avec la vision (QGIS Server) — bascule seulement sur demande réelle de print pro | SP-13 |
| A26 | Observabilité de référence | **OTel SDK + profil compose `grafana/otel-lgtm`**, dashboards & SLO packagés | SP-10 |
| A27 | Séquencement | **Après v0.1 : OTel → Lakehouse**, puis STAC / 3D-print / Analytics — ordre relatif SP-12→15 à arbitrer avant leur lancement (amendé 2026-07-09, Q-A3 ; contrainte : SP-15 après SP-13) | SP-10→15 |
| A28 | Datasets | **Objet de plateforme** (nouveau type d'item) + datasets inline dans les apps | SP-14 |
| A29 | Réactivité à l'emprise | **Opt-in par dataset** ; refetch au déplacement de carte activable en config | SP-14 |
| A30 | Exports tabulaires | **Export sec CSV/XLSX** ; classeurs mis en forme (gabarits) différés | SP-15 |
| A31 | Modèle de config du portail | **Sous-gabarit d'`AppConfig`** (nouveau type d'item `site`), un seul runtime | SP-16 |
| A33 | Domaine personnalisé | **Différé** — v1 via `/sites/{slug}`, pas de domaine tiers | SP-16 |
| A34 | Séquencement SP-16 | **Après SP-11, avant SP-12/13** ; ordre libre vis-à-vis de SP-14 | SP-16 |
| A35 | Structure du chantier | **SP dédié (SP-16)**, pas un sous-lot de SP-9/SP-12 | SP-16 |
| A36 | Storytelling : intégration | **Mode de layout sur `PageManager`**, pas de nouveau widget conteneur | Quick win |
| A37 | Storytelling : timing | **Quick win immédiat, indépendant** de SP-16/SP-11/SP-14 | Quick win |
| A38 | Communauté des portails | **Différée** (commentaires, follow, discussions) — hors périmètre v1 | SP-16 |
| A39 | Moteur ETL (Go/No-Go) | **GO cœur-first** : document `Pipeline` déclaratif + canvas no-code + runtime deux étages (in-process DuckDB/CEL/pandas/dlt ; sidecar `qgis_process` GPL opt-in) + orchestration procrastinate. **NO-GO n8n au centre** (repli nommé avec Kestra/Apache Hop). Subsume le pipeline de transformations de SP-14/A28. Posture GPL = sous-processus (agrégation), cœur Apache-2.0 intact. | SP-17 |

**Conséquences immédiates des décisions** :
- SP-1a démarre par le renommage `core/` (A14) et l'ajout de la génération
  OpenAPI→TS dans la CI (A11).
- Le fichier `LICENSE` (Apache-2.0) peut être posé dès maintenant (A12) — pas
  besoin d'attendre SP-9 ; vérifier la compatibilité des dépendances (rien de
  copyleft fort dans le lot actuel : React, FastAPI, MapLibre, ECharts, Lit sont
  MIT/Apache).
- A4 + A9 forment un couple : l'introspection de schéma (SP-3) est le socle des
  formulaires (SP-4) — toute simplification de l'un doit préserver l'autre.

---

## 9. Différé

> Mise à jour 2026-07-05 : quatre chantiers sont **sortis du différé** et intégrés
> à la feuille de route — observabilité/SLO (SP-10), lakehouse & CDC (SP-11),
> STAC/DCAT/moissonnage (SP-12), 3D & impression (SP-13).

Explicitement **hors** de cette feuille de route (réévalués après M10, ou si
Q2/Q10/Q11 tranchent autrement) :

- Temps réel *en flux* (SSE, MQTT, NATS — palier 0 de la vision §7), attend un
  besoin concret (Q10). Le rafraîchissement par intervalle arrive en SP-14 et
  les **alertes évaluées en jobs** en SP-15 — ni l'un ni l'autre n'en dépend.
- Offline/terrain, profil Edge, synchronisation.
- **Iceberg** (time-travel, schema evolution) — réévalué quand le versioning de
  données (§13.2 vision) montera (A17).
- **DuckDB-WASM navigateur** — deuxième étage de l'analytique, après SP-11 (A18).
- **Conversion 3D** (py3dtiles, nuages de points) et **QGIS Server** pour le print
  professionnel — sur demande réelle uniquement (A24/A25).
- API DCAT complète/SPARQL — l'export DCAT-AP suffit (A21).
- **Connecteurs SQL externes** (MySQL, SQL Server…) — DuckDB `ATTACH` le jour où
  une demande réelle arrive ; surface d'exploitation (drivers, credentials,
  réseau) injustifiée avant.
- **Gabarits Excel** (classeurs mis en forme) — l'export sec suffit (A30).
- **DuckDB-WASM navigateur** (déjà listé via A18) et **LOD expressions** façon
  Tableau — extensions analytiques de deuxième étage.
- Marketplace, sandbox dure des extensions, signature sigstore.
- Multi-tenant *actif* (le schéma est prêt, l'activation attend une demande).
- ~~Workflows durables, versioning de données, agent runtime hébergé~~ →
  **partiellement sorti du différé le 2026-07-22 (A39, SP-17)** : un **ETL
  no-code déclaratif borné** (DAG source→transformers→writer, orchestré par
  procrastinate) entre au périmètre. Restent différés : les **triggers durables
  événementiels** au-delà de la planification simple (Phase 4 de SP-17, sur
  demande), le **versioning de données** et l'**agent runtime hébergé** (briques
  §13 de la vision).
- CI « 8 Go » (décision Q7) — l'empreinte baissera de fait, sans garde-fou bloquant.

---

## 10. Risques transverses

| Risque | Impact | Mitigation |
|---|---|---|
| SP-1 s'enlise (le « tunnel » que l'option C promettait d'éviter) | Démotivation, produit figé | 4 sous-phases livrables, GeoNode ne sort qu'à la toute fin, E2E comme définition de « fini » |
| Sécurité du partage/publication (produit public) | Fuite de données d'un futur déployeur | `can()` unique + tests d'authz dédiés (matrice rôle×action) dès SP-1c, revue avant v0.1 |
| Scope creep Retool (SP-4/SP-5 sans fin) | La route s'arrête au milieu | Critères d'acceptation E2E fermés par SP ; toute idée hors critère va dans un backlog, pas dans le SP |
| cel-js immature (A8) | SP-5 bloqué | Spike de 1 journée en ouverture de SP-5, repli JSONLogic-syntaxe-CEL décidé d'avance |
| Pont React↔WC plus dur que prévu (SP-8) | SDK retardé | Prototype sur le Compteur avant de figer le manifeste ; SP-8 est le dernier gros SP, il peut glisser sans bloquer le reste |
| Solo : bus factor et créneaux hachés | Vélocité irrégulière | Des SP courts, des sous-phases ≤ 25 h, la doc de specs/plans comme mémoire externe |
| Dérive doc/code (3 générations de docs déjà) | Confusion contributeurs | SP-9 archive G1/G2 ; règle : un document de référence par sujet, les autres pointent dessus |
| Le CDC déraille (slot qui gonfle le WAL, worker arrêté, schéma modifié) | Disque plein côté PostGIS, lakehouse périmé | Spike d'ouverture SP-11, alerte sur le lag et la taille du slot (SP-10), procédure de re-backfill documentée, `ALTER` = re-backfill assumé en v1 |
| Étalement des connecteurs de moissonnage (4 retenus) | SP-12 sans fin | Un connecteur = un incrément livrable ; ordre A22 figé ; on peut s'arrêter entre deux |
| Le canvas de graphe ETL dérape (SP-17) | Chantier qui gonfle | MVP borné (topologie linéaire+join, canvas hand-rolled), Phase 1 livrée sans UI (auteur MCP/JSON) avant le canvas ; React Flow (MIT) seulement si nécessaire |
| Posture GPL du sidecar `qgis_process` (SP-17) | Blocage distribution | Étage 2 opt-in (profil compose `etl`), sidecar = sous-processus (agrégation) ; cœur Apache-2.0 intact ; posture confirmée avant release |
| Deux moteurs de transformation (SP-17 vs SP-14) | Viole règle #3 | A39 : SP-14 consomme le moteur de SP-17, ne le duplique pas |

---

## 11. Jalons et indicateurs

| Jalon | Définition de « atteint » | Indicateur de succès associé |
|---|---|---|
| **M1 GeoNode-free** (SP-1) | Compose sans GeoNode/Superset/Redis, E2E vertes | Empreinte mémoire du compose mesurée avant/après (attendu : −50 % ou mieux) |
| **M2 AI-operable** (SP-2) | Un agent MCP crée un dashboard valide | Démo enregistrable < 2 min |
| **M3 Les apps écrivent** (SP-4) | E2E « déclarer un incident » verte | Une app de saisie créée de zéro en < 15 min chrono sans code |
| **M4 Donnée→carte** (SP-6) | GPKG 50 k entités → carte partagée < 5 min | Temps-vers-la-première-carte mesuré |
| **M5 SDK ouvrable** (SP-8) | Widget WC externe chargé dynamiquement, E2E verte | Un widget écrit par quelqu'un d'autre (ou un agent) sans lire le code du shell |
| **M6 v0.1 publique** (SP-9) | Licence, CI, images, install docs, démo publique | Une installation tierce réussie sans assistance ; premières issues externes |
| **M7 exploitable** (SP-10) | Profil observability, dashboards alimentés, 4 SLO avec alertes | Une requête lente diagnostiquée en < 10 min via les traces |
| **M8 data platform** (SP-11) | CDC PostGIS→GeoParquet en continu, API analytique DuckDB | Écriture chaude visible au froid < 5 min ; 1 M de lignes agrégées < 2 s |
| **M9 catalogue ouvert** (SP-12) | STAC conforme, export DCAT-AP, 4 connecteurs de moissonnage | QGIS navigue le catalogue ; data.gouv.fr moissonne ; un GeoServer externe référencé en < 1 min |
| **M10 3D & print** (SP-13) | Couches 3D Tiles + terrain ; export PNG/PDF mis en page | Tileset public navigable > 30 fps ; PDF A3 avec légende/échelle fidèles |
| **M11 BI géospatiale** (SP-14) | Datasets partagés, requête visuelle, contexte global, cross-filter, SQL Lab | Une question spatiale (« incidents à < 500 m d'une école, par commune, ce trimestre ») résolue sans code ni SQL par un non-technicien |
| **M12 La plateforme prévient** (SP-15) | Alertes, rapports planifiés diffusés, exports secs | Rapport PDF hebdo reçu par email ; alerte de seuil déclenchée et journalisée < 5 min ; export XLSX permissionné |
| **M13 Portails ouverts** (SP-16) | Portail public de marque publié, galerie de découverte, fiche dataset téléchargeable | Un visiteur anonyme parcourt un portail et télécharge un jeu de données sans jamais voir un item non publié |
| **M14 ETL no-code** (SP-17) | Canvas `Pipeline` visuel, runtime deux étages, exécution planifiée, outils MCP | Un non-technicien câble sans code source→transformers→writer (data ET spatial) et publie une collection ; un agent MCP crée et exécute un pipeline |

---

*Feuille de route rédigée le 2026-07-04 sur l'état de la branche `dev`
(commit `b8eb71f`) ; étendue le 2026-07-05 (SP-10→SP-13, arbitrages A16–A27,
jalons M7–M10) puis le 2026-07-09 (SP-14/SP-15, arbitrages A28–A30, amendements
A22/A27, jalons M11–M12 — brainstorm Analytics Platform validé Q-A1→Q-A5), puis
le 2026-07-14 (SP-16 « Portails & Sites », quick win Storytelling, arbitrages
A31/A33–A38, jalon M13 — gap analysis dataviz/analytics/BI/portails, arbitrages
tranchés par Tanguy ; specs détaillées :
[storytelling](../superpowers/specs/2026-07-14-storytelling-pagemanager-design.md)
et
[SP-16](../superpowers/specs/2026-07-14-sp16-portails-sites-design.md)), puis
le 2026-07-22 (SP-17 « ETL no-code équivalent FME », arbitrage A39, jalon M14 —
étude de faisabilité, Go cœur-first tranché par Tanguy ; spec :
[étude ETL](../superpowers/specs/2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)).
Les arbitrages A1–A31, A33–A39 sont tranchés en §8 (A32, proposition de copilote
IA embarqué, reste ouverte — voir le gap analysis) ; toute révision d'un
arbitrage après lancement du SP concerné passe par une mise à jour explicite
de ce document.*
