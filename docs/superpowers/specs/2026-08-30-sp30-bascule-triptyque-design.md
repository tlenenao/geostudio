# SP-30 : bascule du shell existant sur le socle triptyque

> Brainstormé et validé avec Tanguy le 2026-08-30. Fait suite à
> `2026-08-29-refonte-ui-triptyque-design.md` (le design du chantier entier,
> §9 : SP-30 = « bascule d'un bloc du shell existant sur le socle triptyque :
> 16 pages, 20 routes, 16 fichiers à dialogue »). Ce document spécifie SP-30 au
> niveau d'exécution, comme `§10` l'a fait pour SP-29. Référence visuelle :
> `docs/design/triptyque-geostudio.html` (huit écrans maquettés, chrome
> complet, dégradation 390 px).
>
> SP-29a (fondation permissions/tokens/i18n) et SP-29b (kit de primitives)
> sont livrés et mergés (PR #102) : `shell/src/auth/{Gate.tsx,capabilities.ts,
> permissions.ts,Locked.tsx}`, `shell/src/ui/kit/` (~40 primitives),
> `shell/src/styles/tokens.css`, `shell/src/i18n/` existent déjà et ne sont
> **pas** reconstruits ici — SP-30 les **consomme**.

## 1. Objectif

Remplacer `shell/src/shell/AppLayout.tsx` (un `<nav class="w-48">` de cinq
liens texte, aucune icône, aucune barre de domaines, aucun ⌘K, aucune barre
d'état — cf. diagnostic §1 du doc parent) par le chrome triptyque complet, et
faire basculer dessus les pages protégées existantes du shell, sans jamais
faire cohabiter deux styles à l'écran (A7/A8).

## 2. Périmètre

### 2.1 — Dans le périmètre

**Chrome neuf** (`shell/src/shell/`) :

1. `TopBar` : marque (identité tenant, §5.4 du doc parent), `Omnibox` (⌘K —
   palette de commandes filtrée par `capabilities.ts` + recherche sémantique
   du catalogue, SP-7, aujourd'hui sans aucune interface), menu compte
   (nom + badge de rôle, §5 ci-dessous, + déconnexion).
2. `DomainBar` : rend `navigableDomains(profile)` (déjà écrit, SP-29a,
   `shell/src/auth/capabilities.ts`) — aucune nouvelle logique de droits,
   seulement le rendu des 9 domaines. **Tâches** et **Paramètres** restent à
   l'état `visible` de `capabilities.ts` (ce n'est pas un droit manquant) et
   pointent chacun vers une route qui rend un `EmptyState` du kit annonçant la
   SP qui les livre (SP-31, SP-33) — aucune nouvelle valeur de `DomainState`
   à introduire.
3. `StatusBar` : **version + tenant seulement** dans ce SP (pas de lecture de
   la file `procrastinate` — l'API de résumé de tâches est un chantier de
   SP-31, l'ouvrir ici pour un seul champ créerait une surface que SP-31
   redessinerait).
4. `TriptychLayout` : composant générique volet1/volet2/volet3, avec la règle
   de dégradation unique sous 390 px (**un volet devient un onglet** — barre
   de domaines → barre de navigation basse à **4 entrées fixes** : Catalogue,
   Cartes, Tâches, Plus, indépendamment du profil, cf. maquette § »Sur écran
   étroit »). Chaque page instancie `TriptychLayout` avec ses propres
   contenus et ses propres libellés d'onglet (« Couches/Carte/Inspecter » pour
   la carte, « Filtrer/File/Détail » pour Tâches, etc.) — un seul gabarit,
   jamais un composant dédié par écran.

**Pages basculées** (12, + les deux routes qui réutilisent `CatalogPage` sans
page dédiée) :

`CatalogPage`, `ItemDetailPage`, `MapEditorPage`, `AppBuilderPage`,
`DatasetEditPage`, `PipelineBuilderPage`, `VisualQueryWizardPage`,
`ReportEditPage`, `SqlLabPage`, `AdminExtensionsPage`, `CollectionsAdminPage`,
`HarvestSourcesAdminPage`. `BookmarksRoute`/`ReportsRoute` (qui rendent
`CatalogPage` avec un `fixedType`) suivent automatiquement.

**Suppression** : les primitives `ui/{button,card,input,dialog}.tsx`
remplacées par leurs équivalents `ui/kit/*` ; les fichiers `*Dialog.tsx`
convertis en parcours plein écran ou en contenu de volet
(`CollectionShareDialog`, `CreateHarvestSourceDialog`, `EditCollectionDialog`,
`EditHarvestSourceDialog`, `RegisterCollectionDialog`, `ShareDialog`, et les
usages de `ui/dialog.tsx` dans `AppExportPanel`, `ExportPanel`, `modal.tsx`,
`Terrain3DUploadButton`, `ImportFileButton`, `ItemActions`, `NewItemButton`,
`Tileset3DUploadButton`). **Seul `ConfirmDialog` survit** (migré vers
`ui/kit/ConfirmDialog`, déjà outillé `aria-modal`/piège de focus/restitution
du focus/verrou de défilement) — confirmation d'action destructive
uniquement. L'inventaire exact (quel dialogue devient quel parcours) est
détaillé au plan, pas ici : le texte d'un plan sur ce genre de détail dérive
vite (piège n°3), autant le vérifier au moment de l'écrire.

**Cœur** : `CollectionPermissions`, même forme qu'`ItemPermissions` (§4).
Régénération obligatoire d'`openapi.json`/`core-schema.d.ts` (diff non vide
attendu, piège n°1) et de `GET /me` (§5).

### 2.2 — Hors périmètre

- `AppRuntimePage`, `SitePublicPage`, `PublicItemPage`, `DatasetPage`
  (public/A9) — inchangés.
- Toute nouvelle capacité (secrets, audit, utilisateurs/groupes, STAC/DCAT,
  alertes, bibliothèque d'icônes, gestion 3D) : SP-31/32/33.
- Fond de carte sombre : la carte reste toujours claire, même en ambiance
  sombre (décidé en session — évite un chantier de styles MapLibre/tuiles non
  chiffré dans un SP déjà signalé comme le plus gros bloc du dépôt, §11 du
  doc parent).
- Un premier endpoint de résumé de tâches pour la barre d'état : reporté à
  SP-31 (§2.1.3 ci-dessus).
- Optimisation tactile des outils de mesure/croquis (A10, déjà hors périmètre
  du chantier entier).

## 3. `ItemActions` : consolidation du verrou (suivi SP-29a)

SP-29a a trouvé que Modifier/Publier/Miniature sont verrouillés séparément
pour la **même** raison — trois `fieldset` désactivés répétant le même texte.
`ItemActions` groupe désormais les actions verrouillées par raison avant
rendu :

```tsx
const locked = actions.filter((a) => !hasPermission(item, a.can));
const grouped = groupBy(locked, (a) => a.lockReason(item));
```

Chaque groupe rend une seule ligne `Locked` (raison + recours) contenant les
libellés des actions concernées, liés visuellement (ex. séparés par « · »)
plutôt qu'empilés. Les actions **non verrouillées** (Partager, Supprimer si
permis) gardent le traitement individuel actuel — pas de sur-fusion : le test
couvre le cas à trois raisons identiques et un mélange de raisons différentes.

## 4. Extension des permissions aux collections

`list_collections` (`core/app/collections/routes.py:275`) appelle
`_can_write_collection` par ligne dans la liste — chaque appel refait sa
propre requête de rôles via `can()` → `roles_for_collections()` : un vrai
N+1, jamais corrigé (la classe de bug que SP-29a a fermée pour les items,
`roles_for_items`, n'a pas été reportée sur les collections).

**`CollectionPermissions`**, miroir exact d'`ItemPermissions` :

```python
class CollectionPermissions(BaseModel):
    read: bool
    write: bool
    delete: bool
    share: bool
```

Une fonction batchée, sur le même patron que le calcul des permissions
d'items : **une** requête `roles_for_collections()` pour toutes les
collections de la liste, puis `decide()` (déjà pur, déjà partagé entre `can()`
et le chemin batch des items — `core/app/sharing/authorization.py:30`) évalué
en mémoire par collection. `GET /collections/{id}` (objet seul) route par la
même fonction `decide()`, pas de nouvelle requête de lot pour un seul objet —
garantit la parité avec la liste.

`_collection_json()` gagne `permissions`, perd `canWrite`. **Pas de compat
shim** : `canWrite` est retiré, ses deux consommateurs sont mis à jour dans le
même changement :

- `builder/widgets/form.tsx:355`
- `builder/pipeline/CollectionParamSelect.tsx:22`

Côté shell, aucun nouveau type : une collection redevient un objet
`HasPermissions` (`{ permissions: {read,write,delete,share}, ... }`), donc
`Gate`/`hasPermission` (déjà écrits, SP-29a) s'appliquent sans modification —
`collection.canWrite` devient `hasPermission(collection, "write")` ou
`<Gate on={collection} can="write">`.

Test anti-régression : le même patron que
`core/tests/test_items_no_nplus1.py`, appliqué à `GET /collections`.

## 5. Badge de rôle dans le menu du compte

Décision de session : le rôle affiché (Administrateur/Analyste/Créateur/
Lecteur, matrice §6.7 du doc parent) n'a **pas** de représentation stable
côté droits — c'est une étiquette d'orientation, jamais une frontière de
sécurité (celle-ci reste `decide()`/`Gate`, objet par objet).

`GET /me` gagne un champ dérivé, **calculé à la volée, pas stocké** :

```python
class MeResponse(BaseModel):
    ...
    hasAnyEditorRole: bool
```

Une requête unique côté cœur : existe-t-il une ligne `ItemShare` **ou**
`CollectionShare` avec `role='editor'` pour cet utilisateur (`LIMIT 1`) ?
Aucune migration — pas un nouveau champ de compte, une question posée aux
tables de partage existantes à chaque appel `/me`.

Le shell en déduit le libellé affiché (première règle qui matche) :

```
isAdmin                     → "Administrateur"
isAnalyst (et pas admin)    → "Analyste"
hasAnyEditorRole (sinon)    → "Créateur"
sinon                       → "Lecteur"
```

**Placement** : pas dans la `TopBar` elle-même — la maquette garde l'avatar à
de simples initiales (`.av`), épuré. Le badge (`ui/kit/Badge`) vit dans le
menu ouvert au clic sur l'avatar, au-dessus de « Déconnexion », à côté du nom.

C'est une approximation grossière assumée : un compte avec un rôle éditeur
oublié sur une seule collection reste étiqueté « Créateur » même s'il n'a en
pratique accès à rien d'écrivable ailleurs. Le badge oriente, il ne renseigne
sur aucun droit précis.

## 6. Stratégie de bascule

### 6.1 — Familles (pour le découpage en tâches et la revue finale)

La revue finale de branche de SP-30 est annoncée comme la plus grosse jamais
pratiquée sur ce dépôt (§11 du doc parent : 16 pages, 20 routes). Le
découpage en tâches isole les écrans par famille — chaque famille se
review-t-elle avant la suivante, en plus de la revue finale transverse
(piège n°4) :

1. **Chrome** — `TopBar`, `DomainBar`, `StatusBar`, `TriptychLayout`, menu
   compte + badge — livré et testé seul, avec une page factice, avant toute
   page réelle.
2. **Catalogue** — `CatalogPage`, `ItemDetailPage`, `ItemActions` consolidé
   (§3). Domaine colonne vertébrale (§3.8 du doc parent) : sert de base au
   volet Catalogue des familles suivantes.
3. **Cartes** — `MapEditorPage`.
4. **Données** — `DatasetEditPage` + permissions collection (§4).
5. **Apps & sites** — `AppBuilderPage`.
6. **Automatisation** — `PipelineBuilderPage`, `ReportEditPage`,
   `VisualQueryWizardPage`.
7. **Analytique** — `SqlLabPage`.
8. **Administration** — `AdminExtensionsPage`, `CollectionsAdminPage`,
   `HarvestSourcesAdminPage`.
9. **Tâches/Paramètres** — les deux `EmptyState` "à venir" ; peut être fait en
   même temps que la famille Chrome.

L'ordre exact et le regroupement en tâches d'exécution (une tâche peut couvrir
plusieurs familles si elles sont petites) se décident au plan, pas ici.

### 6.2 — Tests

- **E2E** : réécrit **au fil** de la bascule, famille par famille (A2) — pas
  de gros-bang final. La suite actuelle (113 passed / 4 skipped) sert de
  checklist de couverture fonctionnelle à préserver, pas de vocabulaire
  d'interface à garder.
- **Unitaires shell** : un fichier par composant de chrome neuf (clavier,
  focus, ARIA, les deux ambiances) ; `ItemActions` sur le cas à raisons
  identiques et à raisons mixtes ; dégradation 390 px vérifiée sur les 8
  écrans de référence des maquettes.
- **Unitaires cœur** : `CollectionPermissions` — parité avec la sérialisation
  déjà testée pour `ItemPermissions` (propriétaire, éditeur, lecteur, public,
  admin) ; `hasAnyEditorRole` sur un compte avec et sans rôle éditeur.
- **Anti-N+1** : `GET /collections`, même patron que
  `test_items_no_nplus1.py`.
- **Portes de qualité** : `ruff`, `mypy --strict` sur les modules concernés,
  `lint-imports` (aucune entrée nouvelle attendue), seuils de couverture non
  régressifs (85 cœur, 88 shell — mesuré après nettoyage de `dist/` et
  `dist-export/`, piège documenté quatre fois).
- **OpenAPI + types TS régénérés** : obligatoire, `CollectionPermissions` et
  `MeResponse.hasAnyEditorRole` changent le schéma (piège n°1). Diff non vide
  attendu.

## 7. Critères de sortie

1. Aucun écran de l'ancien chrome (`AppLayout` à cinq liens) ne subsiste.
2. Les 9 domaines sont navigables selon le profil ; Tâches/Paramètres
   affichent leur `EmptyState` "à venir".
3. `npm run test`, `npm run e2e`, `uv run pytest` verts ; toutes les portes de
   qualité passent, seuils non régressés.
4. `openapi.json` et `core-schema.d.ts` régénérés et commités.
5. 390 px vérifié sans casse sur les 8 écrans de référence des maquettes.
6. `canWrite` a disparu du payload collections et du shell ; `CollectionPermissions`
   le remplace partout, testée anti-N+1.
7. `ItemActions` ne répète plus une raison de verrou identique sur plusieurs
   actions.
8. Le badge de rôle est visible dans le menu du compte pour les quatre
   profils de la matrice §6.7 (vérifié par les comptes de test E2E
   admin/analyste/créateur/lecteur-simulé).

## 8. Risques et limites connues

- **Le plus gros bloc du chantier** (hérité du doc parent, §11) : le
  découpage par famille (§6.1) et une revue par famille en plus de la revue
  finale transverse sont non négociables.
- **`StatusBar` limitée à version+tenant** : la barre d'état ne rend pas
  encore la file `procrastinate` visible — ça reste vrai jusqu'à SP-31.
  Assumé, pas un défaut de ce SP.
- **Badge de rôle approximatif** : `hasAnyEditorRole` ne distingue pas un
  éditeur actif d'un éditeur oublié sur un objet obsolète. Resserrer cette
  définition (ex. « éditeur d'au moins un objet non archivé ») serait un
  changement d'UI seul, pas une migration.
- **Carte toujours claire en ambiance sombre** : réversible plus tard sans
  migration si l'usage montre que c'est gênant.
