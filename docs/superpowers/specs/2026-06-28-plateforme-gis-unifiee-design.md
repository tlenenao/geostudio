# GeoStudio — Plateforme GIS unifiée open-source

> Design / spec. Remplaçant open-source de la couche « création » d'ArcGIS Enterprise 12.1
> (Experience Builder + Dashboards + Hub/Sites + StoryMaps), posé sur la stack backend
> déjà documentée dans ce repo (PostGIS, Martin, TiTiler, GeoServer, GeoNode, Keycloak).
>
> Date : 2026-06-28
> Nom de travail : **GeoStudio** (placeholder, à renommer librement).
> Statut : design validé — prêt pour `writing-plans` sur le premier sous-projet (SP-0).

---

## 1. Contexte et problème

Le repo documente déjà une stack backend open-source complète équivalente à ArcGIS
Enterprise (voir `synthese.md`, `stack3-modern-web-gis.md`, `stacks-production.md`,
`IMPLEMENTATION_PLAN.md`). Le **chaînon manquant** est la couche applicative *unifiée* :
aujourd'hui la création de cartes, dashboards et portails est éclatée entre GeoNode,
Superset, Grafana et MapStore — interfaces disjointes, modèles de contenu distincts,
UX hétérogène.

L'objectif est une **interface unique, user-friendly et performante** permettant de créer,
sans code, des **sites web, des applications et des dashboards**, autour d'un **modèle de
contenu partagé**, et extensible par un **système de briques** intégrables ultérieurement.

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Architecture cœur | **Nouveau shell React unifié** (Vite + TypeScript), MapLibre GL + Deck.gl, moteur de dashboard, modèle de contenu partagé |
| Mode d'édition | **No-code WYSIWYG** (glisser-déposer), cible auteurs non-techniciens |
| Périmètre « Sites » | **Mini-CMS complet** (pages, menus, actualités/blog, médias, SEO, multilingue, brouillons/versions) — sous-projet ultérieur |
| Backend de contenu | **Hybride** : GeoNode (catalogue, items, métadonnées, partage, identité via Keycloak) + **Builder Service** dédié (FastAPI) pour les configs d'apps/sites/dashboards |
| Premier jalon | **SP-0 : Fondation + moteur Apps/Dashboards** |

### Choix techniques retenus

1. **Système de briques** : registre runtime à **manifeste JSON** + bundle, chargement
   dynamique, activation par admin. (Alternatives écartées pour SP-0 : Module Federation
   — trop complexe ; registre build-time — recompilation à chaque ajout.)
2. **Moteur de dashboard/widgets** : **moteur maison léger** (canvas + manifeste + bus de
   messages). Apps et Dashboards = deux presets de layout du même moteur.
3. **Liaison de données / état** : modèle **« data sources » déclaratif** (sources typées +
   état réactif partagé, widgets abonnés), inspiré d'ArcGIS Experience Builder.

## 3. Vision d'ensemble

```
┌──────────────────────────────────────────────────────────────┐
│                     GeoStudio (shell React)                    │
│   Accueil · Catalogue · Visionneuse · 3 éditeurs no-code      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐              │
│  │ Éditeur    │  │ Éditeur    │  │ Éditeur    │   + Briques  │
│  │ Apps       │  │ Dashboards │  │ Sites/CMS  │   (plugins)  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘              │
│        └── moteur widget/canvas ──┘     (moteur pages/CMS)    │
└───────────────┬───────────────────────────┬──────────────────┘
        Builder Service (FastAPI)      GeoNode API v2
     configs apps/dashboards/sites   catalogue · items · partage
                │                          │  identité (Keycloak)
                └─────────────┬────────────┘
              PostGIS · Martin · TiTiler · GeoServer · MinIO
```

## 4. Découpage en sous-projets

Le programme est trop vaste pour un seul spec/plan. Chaque sous-projet est livrable et
autonome, et aura son propre cycle spec → plan → implémentation.

| # | Sous-projet | Contenu | Statut |
|---|---|---|---|
| **SP-0** | **Fondation + moteur Apps/Dashboards** | Shell, auth, modèle d'items (GeoNode), visionneuse MapLibre/Deck.gl, moteur widget/canvas no-code, framework de briques, Builder Service, jeu minimal de widgets | **spécifié ci-dessous** |
| SP-1 | Builder Sites / Mini-CMS | Pages, menus, actualités, médias, SEO, multilingue, brouillons/versions | à venir |
| SP-2 | Bibliothèque de widgets étendue | Filtres avancés, charts, tableaux riches, recherche, impression, éditeur de features | à venir |
| SP-3 | StoryMaps / scrollytelling | brique narration cartographique | à venir |
| SP-4+ | Briques métier | Temps réel/IoT, analytique (Sedona/DuckDB), imagerie/raster, routage, géocodage | à venir |

---

## 5. SP-0 — Spécification détaillée

### 5.1 Périmètre

**Dans :** shell + auth + modèle d'items + visionneuse carte + moteur widget/canvas no-code
+ framework de briques + Builder Service + un jeu minimal de widgets suffisant pour publier
une vraie App **et** un vrai Dashboard.

**Jeu de widgets minimal (MVP) :** Carte · Légende · Liste/Tableau de features · Indicateur
(KPI/stat) · Graphique simple (barres/lignes) · Filtre · Texte/Image · Sélecteur de couches.

**Hors SP-0 :** CMS/Sites (SP-1), widgets avancés (SP-2), StoryMaps (SP-3), briques métier
(SP-4+).

### 5.2 Composants & responsabilités

Unités isolées, chacune avec une responsabilité claire, une interface définie, testable
indépendamment.

| Unité | Rôle | Dépend de |
|---|---|---|
| `shell-app` | Routing, navigation, thème/branding, montage du registre de briques, garde d'auth | `auth`, `plugin-registry` |
| `auth` | Login OIDC Keycloak, contexte utilisateur, propagation token | Keycloak |
| `item-client` | Façade lecture/écriture des items via GeoNode API v2 + Builder Service | GeoNode, Builder Service |
| `map-viewer` | MapLibre + overlay Deck.gl, gestion couches/sources | Martin, TiTiler, pg_featureserv |
| `canvas-engine` | Grille responsive, drag-drop, modes édition/runtime, sérialisation layout | — |
| `widget-sdk` | Contrat de widget (manifeste, props, settings panel, lifecycle) | — |
| `datasource-layer` | Sources de données typées + état réactif + bus de messages inter-widgets | `item-client`, `map-viewer` |
| `plugin-registry` | Découverte/activation des briques via manifeste runtime | `widget-sdk` |
| `builder-service` | API FastAPI : CRUD configs JSON versionnées, validation de schéma, runtime | PostgreSQL, GeoNode |

**Invariant clé :** chaque widget (y compris ceux du MVP) est une brique conforme au
`widget-sdk`. Le cœur ne connaît aucun widget en dur.

### 5.3 Modèle de données

**Item** — unité partageable, alignée sur GeoNode `ResourceBase`, stockée/partagée via
GeoNode :
`id`, `type` (`app` | `dashboard` | `map` | `layer`), `title`, `owner`,
`sharing` (privé / groupe / public), `thumbnail`, `created`, `updated`.

**AppConfig / DashboardConfig** — artefact du builder, JSON versionné, stocké dans le
Builder Service. Les deux `kind` partagent le **même schéma** ; seuls le preset de layout
et le set de widgets par défaut diffèrent.

```jsonc
{
  "version": 1,
  "itemId": "…",            // FK vers item GeoNode
  "kind": "app",            // ou "dashboard"
  "theme": { /* couleurs, logo, typo */ },
  "dataSources": [
    { "id": "ds1", "type": "feature", "service": "martin",
      "layer": "communes", "query": { /* filtres, champs */ } }
  ],
  "layout": {
    "type": "grid",
    "breakpoints": { /* lg, md, sm */ },
    "items": [
      { "widget": "map",   "x": 0, "y": 0, "w": 8, "h": 6, "props": { /* … */ } },
      { "widget": "table", "x": 8, "y": 0, "w": 4, "h": 6, "props": { /* … */ } }
    ]
  },
  "messages": [
    { "from": "map", "event": "select", "to": "table", "action": "filter" }
  ]
}
```

### 5.4 Flux de données

**Édition :** auteur ouvre l'éditeur → `canvas-engine` en mode édition → drag d'un widget
depuis la palette → settings panel fourni par le `widget-sdk` → le widget s'abonne à une
`dataSource` → autosave → `builder-service` valide le schéma et crée une révision.

**Runtime (consultation) :** le shell charge l'item (GeoNode) + la config (Builder Service)
→ `datasource-layer` instancie les sources → `canvas-engine` rend les widgets en lecture
seule → les interactions sont propagées par le **bus de messages**
(ex. clic carte → filtre tableau + recalcul KPI).

**Accès aux données géo :** les widgets carte tirent les tuiles de Martin/TiTiler ; les
widgets data (tableau / KPI / graphique) interrogent pg_featureserv (OGC API Features) ou
des endpoints de statistiques exposés par le Builder Service. **Le navigateur n'accède
jamais à PostGIS en direct.**

### 5.5 Gestion d'erreurs

- **Auth** : token expiré → refresh silencieux puis redirection login ; 401 backend → re-login.
- **Config invalide** : validation de schéma côté Builder Service (rejet en écriture) **et**
  côté shell (rendu dégradé : widget en erreur isolé, le reste de l'app continue).
- **Source indisponible** : le widget affiche un état d'erreur localisé + retry, sans casser
  le canvas.
- **Brique manquante/incompatible** : le registre rend un placeholder « widget indisponible »
  plutôt qu'un crash.
- **Versionnage** : chaque sauvegarde crée une révision ; rollback possible.

### 5.6 Stratégie de tests

- **Unitaire** : `canvas-engine` (sérialisation/désérialisation du layout), `datasource-layer`
  (bus de messages, abonnements), validation de schéma du Builder Service.
- **Contrat** : conformité d'un widget au `widget-sdk` (test partagé, réutilisable par chaque
  future brique).
- **Intégration** : Builder Service ↔ GeoNode (création item + config, partage),
  `item-client` ↔ API.
- **E2E (Playwright)** : parcours « créer une App, ajouter carte + tableau + KPI, lier
  carte→tableau, publier, consulter en runtime » ; idem pour un Dashboard.
- **Performance** : budget de rendu carte cohérent avec les cibles du repo (P95 tuile Martin
  < 20 ms) ; audit Lighthouse sur le runtime.

### 5.7 Risques & parades

| Risque | Parade |
|---|---|
| Ampleur du builder no-code | MVP borné à 8 widgets ; le `widget-sdk` permet d'ajouter le reste en SP-2 sans refonte |
| Couplage à GeoNode | Toute interaction passe par la façade `item-client` ; GeoNode reste remplaçable |
| Perf canvas avec beaucoup de widgets | Virtualisation + rendu mémoïsé dès le départ |
| Dérive de périmètre vers les autres SP | Frontière SP-0 explicite (§5.1) ; CMS/StoryMaps/briques métier hors scope |

### 5.8 Critères d'acceptation SP-0

- [ ] Un utilisateur s'authentifie via Keycloak (SSO) et voit ses items.
- [ ] Création d'une **App** : ajout carte + tableau + KPI sur le canvas, liaison
      carte→tableau, sauvegarde versionnée, publication.
- [ ] Création d'un **Dashboard** : même moteur, preset de layout dashboard.
- [ ] Consultation runtime : interactions inter-widgets fonctionnelles (sélection carte →
      filtre tableau → recalcul KPI).
- [ ] Item partageable (privé / groupe / public) via GeoNode.
- [ ] Une brique widget peut être ajoutée via son manifeste **sans recompiler le cœur**.
- [ ] Suite de tests (unitaire + contrat + 1 parcours E2E App + 1 E2E Dashboard) au vert.

---

## 6. Pile technique (SP-0)

| Couche | Choix |
|---|---|
| Frontend | React + Vite + TypeScript |
| Carte | MapLibre GL JS + Deck.gl (overlay) |
| Layout/canvas | moteur maison (grille responsive + drag-drop) |
| Auth client | keycloak-js (OIDC) |
| Builder Service | Python + FastAPI, PostgreSQL (configs versionnées) |
| Contenu/identité | GeoNode (API v2) + Keycloak |
| Données géo | Martin (MVT), TiTiler (raster COG), pg_featureserv (OGC API Features) |
| Tests | Vitest/Jest (unitaire), Playwright (E2E), pytest (Builder Service) |

## 7. Suite

`writing-plans` sur **SP-0** uniquement. Les sous-projets SP-1+ feront l'objet de leurs
propres cycles brainstorming → spec → plan.
