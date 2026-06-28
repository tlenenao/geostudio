# GeoStudio SP-0b — Shell unifié + auth + item-client

> Design / spec. Deuxième sous-projet de SP-0 (voir
> `2026-06-28-plateforme-gis-unifiee-design.md`). Livre le squelette du shell React
> unifié de GeoStudio : authentification OIDC, layout unifié, et la gestion complète
> des items (catalogue, métadonnées, miniatures, partage, organisation) via une façade
> sur GeoNode + le Builder Service (livré en SP-0a).
>
> Date : 2026-06-28
> Statut : design validé — prêt pour `writing-plans`.
> Prérequis : SP-0a (Builder Service) livré ; stack backend (GeoNode, Keycloak) déployable.

---

## 1. Contexte et périmètre

SP-0b construit le **corps visible** de la plateforme, sans encore la visionneuse
cartographique (SP-0c) ni le moteur de widgets/builder (SP-0d). Il fournit :
le point d'entrée authentifié, la navigation unifiée, et la **gestion complète des
items** (apps / dashboards / maps) que les éditeurs futurs viendront créer et ouvrir.

Le shell consomme deux backends via une **façade unique** (`item-client`) :
- **GeoNode API v2** : resources (liste/détail), métadonnées, `thumbnail_url`,
  permissions de partage, groupes, utilisateur courant.
- **Builder Service** (SP-0a) : configs d'apps/dashboards (`POST/GET/PUT /configs`,
  revisions, rollback).

**Hors SP-0b :** visionneuse carte (SP-0c), canvas/widgets/builder (SP-0d), CMS Sites
(SP-1), provisioning du realm Keycloak et de l'ingress Traefik (stack backend, déjà
planifiée dans `IMPLEMENTATION_PLAN.md` phase 4).

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Livrable | Shell + **gestion d'items complète** (catalogue, métadonnées éditables, miniatures, partage par permissions, organisation par groupes) |
| Socle UI | **Tailwind + shadcn/ui** (habillage GIS construit maison) |
| Auth | **react-oidc-context** (oidc-client-ts) — OIDC Authorization Code + PKCE, agnostique du fournisseur |
| État serveur | **TanStack Query** (cache, invalidation, optimistic updates) |
| Routing | **React Router** |
| Organisation | Partage/organisation = **permissions + groupes GeoNode** ; dossiers personnels reportés (YAGNI) |
| Tests | Vitest + React Testing Library + **MSW** (mock API) + Playwright (E2E) |

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    app-shell (React)                       │
│  AuthProvider (OIDC) → garde → Layout (header/sidebar)    │
│   ┌────────────┐   ┌──────────────────┐                  │
│   │  catalog   │   │ item-management  │   + ui (shadcn)   │
│   │ grille/    │   │ create/rename/   │     ItemCard,     │
│   │ recherche  │   │ delete/meta/     │     ShareDialog…  │
│   └─────┬──────┘   │ thumbnail/share  │                  │
│         └────────┬─┴──────────────────┘                  │
│              item-client (façade, Bearer)                 │
└───────────────┬───────────────────────┬──────────────────┘
        GeoNode API v2            Builder Service (SP-0a)
   resources · sharing ·         configs · revisions
   groups · me · thumbnail
                  Keycloak (OIDC) — token
```

## 4. Unités et responsabilités

| Unité | Rôle | Interface (consommée par) | Dépend de |
|---|---|---|---|
| `auth` | `AuthProvider` + `useAuth()` (état, login, logout, `getAccessToken()`), refresh silencieux | tout le shell | react-oidc-context |
| `app-shell` | Routing, garde d'auth, layout (header/sidebar/branding), gestion d'erreurs globale | — | `auth`, react-router |
| `item-client` | Façade typée : `listItems`, `getItem`, `createConfigItem`, `updateItem`, `deleteItem`, `setSharing`, `listGroups`, `getMe` ; injecte le Bearer ; mappe GeoNode+Builder | hooks data | `auth` token |
| `data` | Hooks TanStack Query : `useItems`, `useItem`, `useMe`, `useGroups`, mutations (create/update/delete/share) | `catalog`, `item-management` | `item-client` |
| `catalog` | Page catalogue : grille d'`ItemCard`, recherche plein-texte, filtres (type, propriétaire, groupe), tri, pagination | — | `data`, `ui` |
| `item-management` | Actions : créer (App/Dashboard, crée la config via Builder Service), ouvrir, renommer, supprimer, éditer métadonnées, gérer miniature, dialog de partage (permissions + groupes) | — | `data`, `ui` |
| `ui` | Primitives shadcn/ui + composants GIS (`ItemCard`, `ShareDialog`, `MetadataForm`, `ConfirmDialog`, `Toast`) | toutes les pages | Tailwind |

**Invariants :**
- Aucun appel réseau hors `item-client` (façade unique ; GeoNode reste remplaçable).
- Le token n'est jamais stocké en `localStorage` (mémoire + refresh silencieux).

## 5. Modèle d'items (mapping)

`Item` (vue shell, alignée GeoNode `ResourceBase`) :
`pk`, `resource_type` (`app`|`dashboard`|`map`), `title`, `abstract`, `owner`,
`thumbnail_url`, `date`, `sharing` (dérivé des permissions), `group` (optionnel),
`configId` (lien vers Builder Service pour app/dashboard).

- **Création d'une App/Dashboard** : `item-management` appelle `item-client.createConfigItem`,
  qui (a) `POST /configs` au Builder Service (crée la config + l'item GeoNode lié via
  l'`ItemClient` serveur de SP-0a) puis (b) retourne l'`Item` consolidé. La config
  initiale est un squelette minimal valide (`kind`, `layout.grid` vide).
- **Organisation/partage** : via l'API permissions de GeoNode (`set` permissions par
  utilisateur/groupe) et les groupes GeoNode. Pas de dossiers personnels en SP-0b.

## 6. Flux de données

**Auth :** au boot, `AuthProvider` vérifie la session ; non authentifié → redirection
OIDC (PKCE) → callback → token en mémoire ; refresh silencieux avant expiration.

**Lecture :** `catalog` monte → `useItems({query, filters, page})` → `item-client.listItems`
→ GeoNode `/api/v2/resources` (+ enrichissement `configId` si besoin) → grille.

**Mutation :** action (rename/delete/share/meta) → mutation TanStack Query → `item-client`
→ GeoNode/Builder → invalidation du cache `items` ; optimistic update sur delete/rename
avec rollback en cas d'échec.

## 7. Gestion d'erreurs

- Token expiré → refresh ; échec → re-login.
- 401/403 backend → message d'accès refusé ; 404 → page item introuvable.
- Erreur réseau/API → toast + état d'erreur **localisé** au composant (la grille reste
  utilisable) ; bouton retry.
- Mutation échouée → rollback de l'optimistic update + toast explicite.
- Erreur de rendu non gérée → error boundary du shell (n'effondre pas toute l'app).

## 8. Stratégie de tests

- **Unitaire/Composant (Vitest + RTL)** : `ItemCard`, `ShareDialog`, `MetadataForm`,
  formulaires/validation, états de chargement/erreur.
- **Façade (`item-client`) contre MSW** : contrats GeoNode (resources, sharing, groups,
  me) et Builder Service (configs) mockés ; vérifie mapping, injection du Bearer, gestion
  des erreurs/pagination.
- **Hooks data** : invalidation de cache, optimistic update + rollback.
- **E2E (Playwright, OIDC mocké)** : login → lister/rechercher → créer une App → renommer
  → éditer métadonnées → partager (groupe) → supprimer.

## 9. Phasage du plan d'implémentation

Le périmètre « gestion complète » est large ; le plan sera découpé en phases livrables :

- **0b.1** — Fondation front : projet Vite/TS/Tailwind/shadcn, `auth` (OIDC + garde),
  `app-shell` (layout/routing), `item-client` (lecture + `getMe`), `catalog`
  (grille/recherche/filtre/pagination), ouvrir un item.
- **0b.2** — Cycle de vie : créer (App/Dashboard via Builder Service), renommer, supprimer,
  métadonnées éditables, miniatures.
- **0b.3** — Partage & organisation : dialog de partage (permissions), groupes GeoNode.

Chaque phase est testable et démontrable seule. `writing-plans` produira d'abord le plan
détaillé de **0b.1**.

## 10. Contraintes globales

- Aucun secret/token en `localStorage`.
- Tout accès réseau via `item-client` ; aucun import GeoNode/Builder hors de la façade.
- Le contrat `ConfigRead` du Builder Service (SP-0a) est stable et consommé tel quel.
- Configuration (URLs GeoNode/Builder/Keycloak, client id) via variables d'environnement
  Vite (`VITE_*`) ; aucune URL en dur.
- Cible navigateurs : evergreen ; pas d'IE.
