# GeoStudio SP-0b.2 — Cycle de vie des items

> Design / spec. Troisième tranche du shell GeoStudio (suite de SP-0b.1, voir
> `2026-06-28-sp0b-shell-auth-itemclient-design.md`). Ajoute la création, le renommage,
> l'édition (titre/résumé/mots-clés), l'upload de miniature et la suppression des items
> App/Dashboard, avec optimistic updates. Inclut une petite extension du Builder Service
> (SP-0a) pour une suppression symétrique.
>
> Date : 2026-06-29
> Statut : design validé — prêt pour `writing-plans`.
> Prérequis : SP-0a (Builder Service) et SP-0b.1 (shell, item-client lecture) livrés.

---

## 1. Contexte et périmètre

SP-0b.1 a livré le shell authentifié avec un catalogue en **lecture seule**. SP-0b.2 ajoute
le **cycle de vie complet** des items App/Dashboard :

- **Créer** une App ou un Dashboard (titre + type).
- **Renommer** et **éditer** les métadonnées (titre, résumé/abstract, mots-clés).
- **Uploader une miniature**.
- **Supprimer** (config Builder Service + ressource GeoNode, sans orphelin).
- Le tout avec **optimistic updates + rollback** sur les opérations destructives/rename.

**Hors SP-0b.2 :** création de « maps » (SP-0c, via la visionneuse), édition du contenu
de l'app/dashboard (canvas/widgets — SP-0d), partage/permissions/groupes (SP-0b.3),
métadonnées ISO complètes (sous-projet dédié ultérieur).

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Suppression | **Symétrique côté Builder Service** : `DELETE /configs/{id}` supprime la config ET l'item GeoNode lié, via le port `ItemClient` étendu d'un `delete_item`. Le front fait un seul appel. |
| Répartition des écritures | **create + delete** passent par le Builder Service (touchent config + item) ; **rename / métadonnées / miniature** sont des champs GeoNode → `item-client` PATCH GeoNode directement. |
| Propriétés éditables | titre, résumé (abstract), mots-clés (keywords), + **upload de miniature**. |
| Réactivité | optimistic update + rollback sur delete et rename ; invalidation du cache `["items"]`. |

## 3. Changement backend — Builder Service (SP-0a)

Le Builder Service crée déjà config + item GeoNode (`POST /configs`, via le port
`ItemClient`). On le rend symétrique pour la suppression.

- **`ItemClient` (port)** : ajouter `delete_item(self, item_id: str) -> None`.
  - `StubItemClient` : enregistre l'appel (`self.deleted: list[str]`).
  - `GeoNodeItemClient` : `DELETE {base_url}/api/v2/resources/{item_id}` avec le Bearer ;
    `raise_for_status()`.
- **Repository** : `delete_config(session, config_id) -> bool` (supprime le `Config` et ses
  `ConfigRevision`; retourne `False` si introuvable).
- **Route** : `DELETE /configs/{config_id}` → récupère l'`item_id` lié, appelle
  `items.delete_item(item_id)` (si présent) puis `repo.delete_config`; `204` si supprimé,
  `404` sinon.
- **Tests pytest** : suppression supprime config + révisions + appelle `delete_item` ;
  `404` si config absente ; `delete_item` stub + adaptateur HTTP (DELETE, Bearer).

Le contrat existant (`ConfigRead`, `POST/GET/PUT /configs`, revisions, rollback) reste
inchangé.

## 4. Front — extensions

### 4.1 `item-client` (nouvelles méthodes, façade)

- `createConfigItem(input: { kind: "app" | "dashboard"; title: string; owner: string }): Promise<Item>`
  → `POST {builderUrl}/configs` avec une `BuilderConfig` squelette (`kind`, `layout` grid
  vide) ; mappe la réponse vers `Item` (lit `itemId`/`id`).
- `updateItem(pk: string, patch: { title?: string; abstract?: string; keywords?: string[] }): Promise<Item>`
  → `PATCH {geonodeUrl}/api/v2/resources/{pk}`.
- `uploadThumbnail(pk: string, file: File): Promise<void>`
  → `PUT {geonodeUrl}/api/v2/resources/{pk}/set_thumbnail` (multipart).
- `deleteItem(configId: string): Promise<void>`
  → `DELETE {builderUrl}/configs/{configId}`.

Les URLs GeoNode exactes sont isolées dans la façade et mockées en test ; seul le contrat
des méthodes ci-dessus est stable pour les consommateurs.

### 4.2 Hooks (TanStack Query mutations)

- `useCreateItem()` — sur succès, invalide `["items"]` et retourne l'`Item` créé.
- `useUpdateItem(pk)` — optimistic update du cache `["item", pk]` et de `["items"]`,
  rollback en cas d'échec ; invalide en `onSettled`.
- `useUploadThumbnail(pk)` — invalide `["item", pk]` / `["items"]` au succès.
- `useDeleteItem()` — optimistic remove de l'item dans `["items"]`, rollback en cas d'échec.

### 4.3 UI (shadcn)

- **`CreateItemDialog`** : sélecteur de type (App/Dashboard) + champ titre → `useCreateItem`
  → navigue vers `/items/{pk}`.
- Bouton **« Nouveau »** (header ou barre du catalogue) ouvrant le dialog.
- **Menu d'actions** par item (sur `ItemCard` et la page détail) : Renommer · Modifier · Supprimer.
- **`MetadataForm`** (titre, résumé, mots-clés) — utilisé pour Renommer (titre seul) et
  Modifier (tous champs).
- **`ThumbnailUpload`** : input fichier, validation **type** (image/*) et **taille** (≤ 2 Mo)
  avant envoi, aperçu.
- **`ConfirmDialog`** : confirmation explicite avant suppression.

## 5. Flux de données

- **Créer** : dialog → `useCreateItem` → `POST /configs` → invalide `["items"]` → navigue
  vers la page détail du nouvel item.
- **Renommer / Modifier** : form → `useUpdateItem` → PATCH GeoNode (optimistic) → rollback
  si échec.
- **Miniature** : `ThumbnailUpload` → `useUploadThumbnail` → PUT GeoNode → invalide.
- **Supprimer** : `ConfirmDialog` → `useDeleteItem` → `DELETE /configs/{configId}`
  (supprime config + item côté serveur) → optimistic remove de la grille.

## 6. Gestion d'erreurs

- Mutation échouée → **rollback** de l'optimistic update + toast explicite.
- Upload miniature : rejet si type non-image ou > 2 Mo (message localisé, pas d'appel réseau).
- Suppression : confirmation typée/explicite ; si le `DELETE` renvoie 404, message « déjà
  supprimé » et invalidation.
- 401/403 → re-login / accès refusé (déjà géré par le shell SP-0b.1).

## 7. Stratégie de tests

- **Backend (pytest)** : `DELETE /configs/{id}` supprime config + révisions et appelle
  `delete_item` ; `404` si absent ; `StubItemClient.delete_item` enregistre l'appel ;
  `GeoNodeItemClient.delete_item` émet un DELETE avec Bearer (MockTransport).
- **Front — façade (MSW)** : `createConfigItem`/`updateItem`/`uploadThumbnail`/`deleteItem`
  appellent les bons endpoints/méthodes et mappent correctement.
- **Hooks** : optimistic update + rollback (delete, update) vérifiés avec un cache simulé.
- **Composants (RTL)** : `CreateItemDialog`, `MetadataForm` (validation), `ThumbnailUpload`
  (validation type/taille), `ConfirmDialog`, menu d'actions.
- **E2E (Playwright, mock auth)** : créer une App → la renommer → la supprimer ; assertions
  d'URL et d'état de la grille (mocks de route pour les nouveaux endpoints).

## 8. Phasage du plan d'implémentation

- **0b.2-a — Backend** : `delete_item` (port + stub + adaptateur HTTP) + `delete_config`
  repository + `DELETE /configs/{id}` route + tests pytest. *(dans `builder-service/`)*
- **0b.2-b — Front création** : `createConfigItem` + `useCreateItem` + `CreateItemDialog` +
  bouton « Nouveau » + navigation.
- **0b.2-c — Front édition/suppression** : `updateItem`/`uploadThumbnail`/`deleteItem` +
  hooks (optimistic/rollback) + `MetadataForm`/`ThumbnailUpload`/`ConfirmDialog` + menu
  d'actions + E2E étendu.

Chaque phase est testable seule ; `writing-plans` produira d'abord le plan de **0b.2-a**.

## 9. Contraintes globales

- Suppression symétrique : aucune config orpheline après un delete réussi.
- Tout accès réseau front via `item-client` ; aucun import GeoNode/Builder hors de la façade.
- Le contrat `Item` de SP-0b.1 reste stable (extension, pas de rupture).
- Builder Service : le contrat existant (POST/GET/PUT/revisions/rollback) reste inchangé ;
  on ajoute uniquement `DELETE /configs/{id}` et `ItemClient.delete_item`.
- Upload miniature borné côté client : image/* et ≤ 2 Mo.
- Pas de token en localStorage (inchangé depuis SP-0b.1).

---

## Notes pour SP-0b.2-c (issues de la revue finale 0b.2-a)

- **Surface 404 vs 500 sur delete :** si l'item GeoNode a été supprimé hors-bande, `GeoNodeItemClient.delete_item` fait `raise_for_status()` sur le 404 GeoNode → la route `DELETE /configs/{id}` renvoie alors **500**, pas 404. Le spec §6 prévoit que le front traite un **404** comme « déjà supprimé ». Donc le `deleteItem` du front (0b.2-c) doit gérer **500** séparément (message générique + invalidation), et/ou on durcira la route plus tard pour tolérer un 404 GeoNode (traiter comme déjà-supprimé puis poursuivre `delete_config`).
- **Fenêtre d'orphelin inverse (improbable) :** si `delete_item` réussit mais `delete_config` échoue (panne DB après l'appel GeoNode), l'item GeoNode est parti mais la config subsiste. `delete_config` est une transaction unique (tout-ou-rien) ; pas de compensation — comportement distribué accepté.
- **Couverture mineure différée :** ajouter un test route du cas `item_id = None` (config sans item lié) ; le cas est déjà couvert au niveau repository.

### Notes additionnelles (revue finale 0b.2-b)

- **Garde `itemId` null à la création :** `createConfigItem` mappe `pk = String(itemId ?? "")`. Si le Builder Service renvoie `itemId: null` (GeoNode non câblé / `StubItemClient` renvoyant None), `pk` devient `""` et `navigate("/items/")` ne matche pas la route → écran vide silencieux. En 0b.2-c : faire **lever** `createConfigItem` quand `itemId` est absent (déclenche le chemin d'erreur), ou garder dans `NewItemButton` (`if (!item.pk) return;`).
- **Polish a11y du `Dialog` (pass dédié ou 0b.2-c)** : `aria-modal="true"` sur le panneau, focus initial à l'ouverture, `aria-haspopup="dialog"` sur le bouton déclencheur ; mémoïser `close` (useCallback) pour éviter le churn du listener keydown ; `aria-label` redondant sur l'Input enveloppé d'un `<label>`.
- **E2E** : couvrir aussi la branche « Dashboard » du sélecteur de type (actuellement seul « app » est testé en E2E).
