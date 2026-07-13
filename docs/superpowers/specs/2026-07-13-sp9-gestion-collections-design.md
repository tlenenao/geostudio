# SP-9 — UI de gestion des collections : design

> Sous-partie de SP-9 (Durcissement produit public v0.1). Brainstormé le
> 2026-07-13, en amont du reste de SP-9 — peut être planifiée et exécutée
> indépendamment du reste de la phase.

## 1. Contexte et objectif

**Constat.** Depuis SP-3a, `app.collections` a une API cœur complète
(`POST/GET/PATCH/DELETE /collections`, `GET/PUT /collections/{id}/sharing`,
`GET /collections/{id}/schema`) — mais aucune UI shell ne la consomme pour
la *gestion*. Le shell ne fait que **lire** les collections (`LayerPicker`,
recherche du catalogue). Aujourd'hui, un admin gère les collections à la
main (curl, `core/scripts/seed_demo.py`) ou via l'enregistrement automatique
de l'ingestion (SP-6a/6b), qui ne couvre que la création.

**Objectif.** Un admin gère le cycle de vie complet d'une collection depuis
le shell — lister, créer (en choisissant une table PostGIS candidate),
éditer, partager, supprimer (désenregistrer) — avec exactement les mêmes
garanties de sécurité que l'API existante. Aucun nouveau modèle de
permission : cette UI est une façade sur des routes déjà autorisées et
auditées.

## 2. Périmètre

**Dans le périmètre v1 :**
- Lister les collections du tenant (titre, table, public/éditable, nombre
  d'entités, propriétaire).
- Créer : sélecteur de tables PostGIS candidates (pas de saisie manuelle du
  nom de table), avec statut « enregistrable / non » et raison affichée si
  non-enregistrable (clé primaire composite, plusieurs colonnes géométrie,
  etc.) — le sélecteur ne propose jamais une table qui échouerait
  silencieusement à l'enregistrement.
- Éditer : titre, description, `isPublic`, `editable` (champs exacts de
  `CollectionPatch`, déjà existant).
- Partager : groupes × rôles (viewer/editor), même mécanique que le partage
  d'items, sur `GET/PUT /collections/{id}/sharing` (déjà existant).
- Supprimer : désenregistrement (`DELETE /collections/{id}`, la table
  PostGIS survit — comportement déjà existant, inchangé).
- Visible uniquement si l'utilisateur courant est admin (fail-open côté
  affichage ; la frontière réelle reste les 403 serveur déjà en place).

**Hors périmètre v1 (explicitement différé, pas oublié) :**
- Suppression physique de la table PostGIS sous-jacente.
- Création d'une table depuis zéro (l'ingestion SP-6 couvre déjà ce cas —
  cette UI gère des tables qui existent déjà en base).
- UI de gestion des users/groupes — mais l'entrée de nav « Administration »
  est conçue pour les accueillir dans une itération future sans redesign.
- Validation de schéma avancée, versionning de schéma, migration de colonnes.

## 3. Architecture

### 3.1 Cœur (deux ajouts, aucun changement de modèle de données)

**`GET /me` gagne `isAdmin: bool`** dans `MeResponse`
(`core/app/auth/routes.py`) — la colonne `users.is_admin` existe déjà
(SP-3a), elle n'est simplement pas exposée au client aujourd'hui. Purement
informatif côté shell (fail-open) ; toute route de mutation sur les
collections applique déjà sa propre garde admin indépendamment de ce champ.

**Nouvelle route `GET /collections/candidates`** (admin-only, même garde
`_require_admin` que `POST /collections`, `core/app/collections/routes.py`) :
- Liste les tables du schéma `public` non encore enregistrées comme
  collection pour le tenant courant, en excluant les tables cœur
  (`_core_tables()`, déjà utilisé par `register_collection`) — requête
  `information_schema.tables` filtrée, même schéma que celui déjà interrogé
  par `introspection_pg.py`.
- Pour chaque table restante, appelle l'`Introspector` déjà injecté
  (`get_introspector`, réutilisé tel quel) :
  - si l'introspection réussit → `{ tableName, registrable: true,
    geometryType, srid, columnCount }` (aperçu utile pour choisir).
  - si `UnsupportedTable` → `{ tableName, registrable: false, reason }`
    (même message que celui que `POST /collections` renverrait en 400).
  - si `TableNotFound` ne peut pas arriver ici par construction (la table
    vient de `information_schema`), donc pas de branche à gérer.
- Aucune nouvelle logique d'introspection écrite — pure recomposition de
  briques SP-3a existantes.

### 3.2 Shell

**`ItemClient` (interface + implémentation `CoreItemClient`)** gagne, en
méthodes inline (même idiome que les méthodes existantes de
`itemClient.ts` : fetch + throw sur `!res.ok`) :
- `listCollections(): Promise<CollectionAdmin[]>` — mappe `GET /collections`
  vers un type qui garde tous les champs utiles à l'admin (contrairement à
  `fetchCoreCollections`/`LayerSource`, qui n'en garde qu'un sous-ensemble
  pour le sélecteur de couches — types distincts, pas de réutilisation
  forcée entre deux usages différents).
- `listCandidateTables(): Promise<CandidateTable[]>`
- `createCollection(input): Promise<CollectionAdmin>`
- `updateCollection(id, patch): Promise<CollectionAdmin>`
- `deleteCollection(id): Promise<void>`
- `getCollectionSharing(id): Promise<Sharing>`
- `setCollectionSharing(id, sharing): Promise<void>`

**`Me` (type, `api/types.ts`)** gagne `isAdmin: boolean`.

**Hooks (`api/hooks.ts`)** : `useCollectionsAdmin`, `useCandidateTables`,
`useCreateCollection`, `useUpdateCollection`, `useDeleteCollection`,
`useCollectionSharing`, `useSetCollectionSharing` — même patron react-query
que les hooks existants (`useItems`, `useSharing`/`useSetSharing`).

**Nouvelle route shell `/admin/collections`** (`shell/src/shell/routes.tsx`),
sous `RequireAuth` **et** un garde `isAdmin` supplémentaire : si
`useMe().data?.isAdmin` est faux, redirection vers `/` (même fail-open que
le masquage du bouton d'écriture du Formulaire en SP-4c — la page ne
s'affiche pas, mais la vraie frontière reste les 403 serveur).

**Lien de nav « Administration »** dans `AppLayout`, visible seulement si
`isAdmin` — première entrée d'une future section admin (users/groupes
pourront s'y ajouter plus tard sans redesign de la nav).

**Composants nouveaux :**
- `CollectionsAdminPage` : tableau des collections (titre, table, public,
  éditable, nb d'entités, propriétaire) + bouton « Enregistrer une table ».
- `RegisterCollectionDialog` : liste les candidats
  (`useCandidateTables`), désactive/annote visuellement les
  non-enregistrables avec leur raison, formulaire titre/description/public
  pour la table choisie, soumission via `useCreateCollection`.
- `EditCollectionDialog` : titre/description/public/éditable, soumission via
  `useUpdateCollection`.
- `CollectionShareDialog` : copie de `shell/src/shell/ShareDialog.tsx`
  adaptée à `collectionId` plutôt qu'`item.pk` (hooks
  `useCollectionSharing`/`useSetCollectionSharing` au lieu de
  `useSharing`/`useSetSharing`) — duplication assumée, même arbitrage que
  les échos documentés déjà actés dans ce projet (`ExtensionManifest`↔
  `WcWidgetManifest`, mapping CEL/Python), pas de généralisation prématurée
  d'un composant qui n'a qu'un seul autre appelant aujourd'hui.
- Suppression : réutilise `ConfirmDialog` (`shell/src/ui/`) tel quel, pas de
  nouveau composant.

## 4. Flux et gestion d'erreurs

**Création :** ouverture du dialogue → `useCandidateTables()` charge la
liste → l'admin choisit une table marquée `registrable: true` (les autres
sont visibles mais désactivées, avec leur raison en tooltip/texte) → remplit
titre/description/public → `createCollection()` → invalidation de la query
`["collections", "admin"]` → apparaît dans le tableau.

**Cas vide :** si `listCandidateTables()` renvoie `[]`, message explicite
(« Aucune table à enregistrer — toutes les tables éligibles du schéma
`public` sont déjà des collections, ou importez un fichier depuis le
catalogue ») plutôt qu'un sélecteur vide silencieux.

**Erreurs :** même patron fail-open que partout ailleurs dans ce projet — le
lien de nav et la page se masquent si `isAdmin` est faux côté client, mais
la frontière réelle reste les 403 serveur sur `POST/PATCH/DELETE
/collections`, inchangés. Un 409 (table déjà enregistrée entre-temps) ou un
400 s'affichent comme message d'erreur inline dans le dialogue concerné, pas
de crash de page.

## 5. Tests

**Core (pytest) :**
- `GET /me` expose `isAdmin` conforme à `users.is_admin`.
- `GET /collections/candidates` : garde admin-only (403 sinon), exclusion
  des tables cœur, exclusion des tables déjà enregistrées **pour ce
  tenant**, `registrable: false` + raison pour une table sans PK ou avec PK
  composite (réutilise les fixtures de test déjà écrites pour
  `register_collection` dans `test_collections_routes.py`), isolation
  tenant (une table candidate pour le tenant A n'apparaît pas exclue pour
  le tenant B tant qu'elle n'est pas enregistrée par B).

**Shell (Vitest) :**
- Nouvelles méthodes `ItemClient` (MSW, même patron que les tests
  existants de `itemClient.test.ts`).
- `CollectionsAdminPage` : rendu du tableau, états loading/erreur/vide.
- `RegisterCollectionDialog` : candidats registrable vs non (désactivé +
  raison affichée), soumission, cas liste vide.
- `EditCollectionDialog`, `CollectionShareDialog` : rendu, soumission,
  erreurs (409/400 affichés inline).
- Garde de route `isAdmin` sur `/admin/collections`.

**E2E (nouvelle spec `admin-collections.spec.ts`) :**
1. Parcours admin complet : lien « Administration » visible → créer une
   collection via le sélecteur de candidats → éditer son titre → la
   partager avec un groupe en rôle éditeur → un utilisateur membre de ce
   groupe peut écrire dans la collection (Formulaire ou Table) → l'admin la
   supprime (désenregistre) → elle disparaît du tableau et du sélecteur de
   couches.
2. Un non-admin ne voit pas le lien « Administration » ; une navigation
   forcée vers `/admin/collections` redirige vers `/`.

## 6. Critères d'acceptation

- Un admin peut enregistrer une collection depuis le shell sans jamais
  taper un nom de table à la main, ni exécuter de commande hors du shell.
- Un admin peut éditer, partager et désenregistrer une collection existante
  depuis le shell.
- Un non-admin ne voit ni le lien ni la page, et une navigation forcée
  échoue proprement (redirection, pas de fuite d'information au-delà du
  masquage habituel).
- Les 30 specs E2E existantes restent vertes.
