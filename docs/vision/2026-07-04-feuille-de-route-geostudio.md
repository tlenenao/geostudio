# GeoStudio — Feuille de route Option C (spécification et phasage)

> Déclinaison opérationnelle de l'option C (« refonte par étranglement ») retenue dans
> [`2026-07-04-comparatif-projet-actuel-vs-vision.md`](./2026-07-04-comparatif-projet-actuel-vs-vision.md)
> (§9), elle-même issue de la vision
> [`2026-07-04-plateforme-webgis-nouvelle-generation.md`](./2026-07-04-plateforme-webgis-nouvelle-generation.md).
>
> Date : 2026-07-04 · Statut : feuille de route — les arbitrages techniques (§7) sont
> tranchés en §8. Chaque phase donnera lieu à sa spec + son plan détaillé
> (`docs/superpowers/`) au moment de la lancer, selon le workflow SP-0x existant.

---

## Sommaire

1. [Décisions déjà actées (rappel)](#1-décisions-déjà-actées)
2. [Principes d'exécution](#2-principes-dexécution)
3. [Architecture cible de fin de feuille de route](#3-architecture-cible)
4. [Le périmètre exact du remplacement de GeoNode](#4-périmètre-du-remplacement-de-geonode)
5. [Modèle de données du cœur v0](#5-modèle-de-données-du-cœur-v0)
6. [Phasage SP-1 → SP-9](#6-phasage)
7. [Points d'arbitrage technique (A1–A15)](#7-points-darbitrage-technique)
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
| | **Total** | **≈ 390–695 h** | | ≈ 9–18 mois à 10–25 h/sem |

L'ordre SP-3→SP-6 est inversable (ingestion avant formulaires) si un utilisateur
réel l'exige (question Q2 du comparatif, toujours ouverte). SP-2 est
volontairement minuscule et placé tôt : démo forte, coût faible, et il force la
propreté de l'API du cœur.

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
  (expression) — sans devenir un moteur de workflow (différé, §9).

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

---

## 8. Décisions d'arbitrage

> Arbitrages tranchés le **2026-07-04**. Chaque décision est révisable *jusqu'au
> lancement du SP concerné*, figée ensuite (toute révision passe par une mise à
> jour explicite de ce document).

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

Explicitement **hors** de cette feuille de route (réévalués après M6, ou si Q2/Q10/Q11
tranchent autrement) :

- Temps réel (SSE, alertes, NATS) — palier 0 de la vision, attend un besoin concret.
- Offline/terrain, profil Edge, synchronisation.
- Lakehouse complet (GeoParquet/Iceberg/DuckDB), CDC — SP-6 pose seulement l'ingestion.
- Catalogue STAC public complet, DCAT, moissonnage.
- 3D (3D Tiles), impression (QGIS Server).
- Marketplace, sandbox dure des extensions, signature sigstore.
- Multi-tenant *actif* (le schéma est prêt, l'activation attend une demande).
- Workflows durables, versioning de données, agent runtime hébergé (briques §13 de
  la vision — après M6).
- OpenTelemetry/SLO complets (un logging structuré propre suffit jusqu'à M6).
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

---

*Feuille de route rédigée le 2026-07-04 sur l'état de la branche `dev`
(commit `b8eb71f`). Les arbitrages A1–A15 sont tranchés en §8 ; toute révision
d'un arbitrage après lancement du SP concerné passe par une mise à jour explicite
de ce document.*
