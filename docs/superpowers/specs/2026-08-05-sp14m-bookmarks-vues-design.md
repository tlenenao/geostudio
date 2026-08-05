# SP-14m — Bookmarks : vues analytiques enregistrées (design)

> **Date : 2026-08-05 · Statut : validé (brainstorm)**
> Treizième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**,
> **SP-14g — Tableau croisé / pivot**, **SP-14h — Carte analytique**,
> **SP-14i — SQL Lab**, **SP-14j — Conteneurs**, **SP-14k — Source `arcgis`**
> et **SP-14l — MCP analytique**. Traite l'un des deux éléments restés
> explicitement « hors périmètre » depuis 14b (« Bookmarks nommés persistés
> côté serveur (« situations » cataloguées) — seule l'URL du navigateur porte
> l'état en v1, pas de nouvel objet de plateforme », répété identique en
> 14h/14i) : les **bookmarks** deviennent cet objet de plateforme. Le second
> élément resté hors périmètre depuis 14b (**cross-filter inter-datasets** :
> une sélection sur un widget d'un dataset qui filtre aussi les widgets d'un
> *autre* dataset) reste hors périmètre ici — sous-partie SP-14 ultérieure si
> le besoin émerge. **Requête visuelle** reste également hors périmètre :
> dépend du moteur de pipeline livré par **SP-15** (A39, ETL no-code), qui
> n'existe pas encore.

## 1. Objectif & non-buts

**Objectif.** Un utilisateur qui a configuré un contexte analytique (période,
emprise, filtres croisés — `AnalyticsContextState`, SP-14b) sur un dashboard
`interactions: "auto"` peut le nommer et le sauvegarder comme **vue** : un
item de plateforme au même titre qu'une app ou un dataset (catalogué,
partagé via `can()`, audité), qu'il retrouve ensuite depuis une page dédiée
« Mes vues » et rouvre en un clic — le contexte analytique est rejoué
exactement comme au moment de la sauvegarde. C'est la réalisation du passage
de la vision (2026-07-09 §2.4/§5.4) : « état analytique sérialisable dans
l'URL et sauvegardable en bookmark — précieux pour partager *une situation*,
pas un dashboard ».

**Non-buts explicites** (pour rester dans une sous-partie livrable) :

- **Cross-filter inter-datasets.** Toujours hors périmètre depuis 14b — sans
  rapport avec la persistance d'un contexte, sous-partie SP-14 ultérieure
  distincte si le besoin émerge.
- **Requête visuelle.** Dépend de SP-15 (cf. en-tête), inchangé.
- **Nouveau widget ni modification du contexte analytique lui-même.** SP-14b
  reste l'unique source de vérité d'`AnalyticsContextState` ; SP-14m ne fait
  que le sérialiser côté serveur au lieu de la seule URL.
- **Snapshot des données.** Une vue rejoue la requête au moment de
  l'ouverture (mêmes datasets, données à jour) — ce n'est pas un export figé
  ni un cache de résultats (ça, c'est le périmètre de SP-16, rapports).
- **Édition d'une vue existante.** Une vue se supprime et se resauvegarde ;
  pas de flux d'édition dédié (il n'y a pas de builder pour ce kind).
- **`list_bookmarks` (MCP).** Inutile : l'outil générique
  `list_items(type="bookmark")` (déjà existant depuis SP-2b) le couvre
  intégralement.
- **Validation de fraîcheur de `pageId`/du contexte vis-à-vis de l'app
  cible.** Une vue peut devenir orpheline si l'app/la page a changé entre
  temps (page supprimée, dataset renommé) — même risque qu'un lien
  copié-collé aujourd'hui ; pas un nouveau mode de panne, pas traité.

Le modèle reste additif : rien ici ne doit être défait pour les sous-parties
suivantes, et les specs E2E existantes restent vertes sans modification
(aucune config existante n'a `kind="bookmark"`).

## 2. Modèle de données

Aucune migration Alembic requise : `configs.kind` et `items.resource_type`
sont de simples colonnes `String` sans contrainte DB (pas d'enum/`CheckConstraint`,
vérifié dans `core/app/configs/models.py` et `core/app/items/models.py`).
L'extension est purement au niveau des schémas Pydantic/TypeScript.

**`core/app/configs/schemas.py`** (additif) :

```python
class BookmarkCrossFilterEntry(BaseModel):
    field: str
    value: str | list[str]
    originSourceId: str

class BookmarkTimeRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    to: str

class BookmarkPayload(BaseModel):
    appId: str
    pageId: str
    timeRange: BookmarkTimeRange | None = None
    extent: tuple[float, float, float, float] | None = None
    crossFilter: dict[str, BookmarkCrossFilterEntry] = Field(default_factory=dict)

class BuilderConfig(BaseModel):
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark"]
    ...
    bookmark: BookmarkPayload | None = None
```

`BookmarkPayload` est le miroir exact d'`AnalyticsContextState`
(`shell/src/builder/AnalyticsContext.tsx`, SP-14b) — mêmes trois champs, même
forme de `crossFilter` (`Record<datasetId, {field, value, originSourceId}>`)
— pour que la sérialisation shell↔serveur soit un aller-retour sans perte,
sans traduction ad hoc.

`resource_type="bookmark"` côté `items` ; `Item.title` = le nom donné par
l'utilisateur à sa vue.

**Shell** (`shell/src/api/types.ts`) : `ResourceType` gagne `"bookmark"` ;
nouveau type `BookmarkPayload` en miroir exact du type core, construit
directement depuis `AnalyticsContextState` (aucune transformation).

## 3. Validation & permissions

Contrairement à `DatasetPayload` (qui a besoin d'un hook registry pour éviter
une dépendance interdite de `app.configs` vers `app.collections`/`app.harvest`,
cf. `dataset_validation.py`), **`app`/`dashboard` sont déjà des kinds natifs
de `app.configs`** — la validation se fait directement dans ce module, sans
indirection :

- `appId` doit référencer un item existant de kind `app`/`dashboard`,
  **lisible par l'utilisateur courant** au moment de la création
  (`can(user, "read", item)`, même vérification que toute lecture d'item).
- `pageId` : chaîne non vide requise. Pas de validation contre les pages
  réelles de l'app cible (évite le couplage et le problème de fraîcheur —
  cf. non-buts §1).

Permissions de la vue elle-même : **intégralement héritées du modèle
générique item** (SP-1c) — privée par défaut à son propriétaire, partageable
via `can()`/groupes exactement comme un dataset ou une app. Aucun mécanisme
de partage neuf à écrire.

## 4. API (core)

**Aucune nouvelle route REST.** Le chemin générique existant, déjà utilisé
par `createDatasetItem`, suffit intégralement :

- Créer : `POST /items` (`resource_type=bookmark`) puis `POST /configs`
  (`kind=bookmark`).
- Lire : `GET /configs/by-item/{id}`.
- Lister « mes vues » : `GET /items?type=bookmark&scope=mine` (générique,
  déjà utilisé par le catalogue pour tout kind).
- Supprimer : `DELETE /items/{id}` (générique, déjà existant pour tout kind).

## 5. Shell — câblage

- `api/itemClient.ts` : `createBookmarkItem(input)`, miroir direct de
  `createDatasetItem` (création `Item` + `Config` en une opération).
- **Bouton « Enregistrer la vue »** dans la barre de `AppRuntimePage`,
  affiché seulement si `config.interactions === "auto"` (seul mode où
  `AnalyticsContextState` porte une information non triviale, cohérent avec
  la garde déjà appliquée à l'écriture de l'URL en SP-14b). Au clic : petite
  boîte de dialogue (nom de la vue) puis
  `createBookmarkItem({ title, appId: pk, pageId: pageId ?? config.pages[0].id, ...ctx })`
  — `pageId` résolu côté client exactement comme le fait déjà `onNavigate`
  pour l'URL, pas de nouvelle notion de « page courante ». Le contexte
  analytique courant est déjà remonté par `handleAnalyticsContextChange` ; il
  suffit de le garder aussi en state local du composant (pas seulement dans
  la closure du debounce d'écriture URL) pour l'exposer au bouton.
- **Page dédiée `/bookmarks` (« Mes vues »)** : réutilise `CatalogPage` avec
  le filtre `type` figé à `"bookmark"` (le filtre par `ResourceType` existe
  déjà) — pas de composant de liste/pagination/recherche à réécrire.
- **Ouverture d'une vue** : cas spécial dans le handler `onOpenItem` — pour
  `type === "bookmark"`, ne pas naviguer vers un éditeur (il n'y en a pas
  pour ce kind) mais directement vers
  `/apps/${bookmark.appId}/${bookmark.pageId}?ctx=${encodeAnalyticsContext(ctx)}`,
  en réutilisant `encodeAnalyticsContext` (SP-14b) telle quelle — le
  mécanisme de restauration du contexte au chargement (`AppRuntimePage`
  décode déjà `?ctx=` au montage) n'a besoin d'aucune modification.
- Suppression d'une vue : bouton delete générique déjà présent pour tout
  item — aucun code neuf.

## 6. MCP

Un seul outil nouveau, miroir direct de `create_dataset` (SP-14l) :

```python
@server.tool()
async def create_bookmark(
    ctx: Context, title: str, appId: str, pageId: str,
    timeRange: BookmarkTimeRange | None = None,
    extent: tuple[float, float, float, float] | None = None,
    crossFilter: dict[str, BookmarkCrossFilterEntry] | None = None,
) -> ItemRead:
    """Save a named analytics view (time range/extent/cross-filter) on an
    app page — mirrors POST /configs with kind="bookmark". SP-14m."""
```

Même séquence interne que `create_dataset` : résoudre l'utilisateur,
construire le `BookmarkPayload`, valider (§3), créer l'item puis le config,
journaliser deux entrées `audit_log` (`item.create`, `config.create`), même
garde `is_read_only_mode()`.

`list_items(type="bookmark")` (déjà générique depuis SP-2b) couvre le
listing — pas d'outil `list_bookmarks` dédié (§1).

## 7. Compatibilité & tests

Compatibilité : `kind` gagne un littéral supplémentaire, additif ; aucune
config existante n'a `kind="bookmark"` ; aucune migration DB. Les specs E2E
existantes restent vertes sans modification.

**Core (unitaires)** :
- `BookmarkPayload` : `appId` doit référencer un item lisible de kind
  `app`/`dashboard` sinon 403/404 explicite ; `pageId` vide rejeté.
- Permissions : création par un utilisateur sans accès en lecture à l'app
  cible → refusée ; vue privée illisible par un autre utilisateur tant
  qu'elle n'est pas partagée (réutilise les tests de partage génériques
  existants pour un item quelconque, pas de nouveau test de partage à
  écrire).
- `create_bookmark` (MCP) : crée l'item + le config, journalise l'audit,
  refuse en mode démo lecture seule (même patron que `create_dataset`).

**Shell (unitaires)** :
- Bouton « Enregistrer la vue » : absent/désactivé si
  `interactions !== "auto"` ; capture correctement l'`AnalyticsContextState`
  courant au moment du clic.
- `onOpenItem` : `type === "bookmark"` navigue vers l'URL app+page+`ctx`
  attendue (pas vers un éditeur).
- `CatalogPage` filtrée `type="bookmark"` : rendu correct de la liste (pas de
  logique neuve, juste un test de câblage).

**E2E nouvelle** (calquée sur les specs `datasets-shared`/`bookmarks`
existantes) : sur un dashboard `interactions: "auto"`, poser un filtre croisé
et une période → « Enregistrer la vue » → la vue apparaît dans `/bookmarks`
→ l'ouvrir restaure exactement le même contexte (même barre surlignée, même
période) que celui sauvegardé ; une vue non partagée est invisible pour un
second utilisateur du même tenant.

## 8. Risques

| Risque | Garde-fou |
|---|---|
| Vue orpheline (app/page supprimée après coup) | Ouverture échoue proprement (l'app cible renvoie son 404/403 habituel) — pas différent d'un lien cassé, hors périmètre de traiter (§1) |
| Confusion « vue » vs « dataset » vs « app » dans le catalogue général | La page `/bookmarks` filtre déjà par kind ; dans le catalogue général une vue porte son propre badge de type comme tout autre kind, aucune UI neuve à concevoir |
| Bouton « Enregistrer la vue » visible sur des dashboards sans contexte utile | Gated strictement sur `interactions === "auto"`, même garde que la persistance de contexte dans l'URL depuis SP-14b |
| Sur-ingénierie prématurée (édition de vue, snapshot de données, cross-filter inter-datasets, `list_bookmarks` MCP) | Explicitement hors périmètre (§1) ; le modèle reste additif pour une sous-partie ultérieure si le besoin émerge |
