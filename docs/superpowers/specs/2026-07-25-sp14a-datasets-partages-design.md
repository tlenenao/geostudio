# SP-14a — Datasets partagés (design)

> **Date : 2026-07-25 · Statut : validé (brainstorm)**
> Première sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11). SP-14 est trop large pour un plan unique (comparable à SP-11/SP-12,
> découpés en sous-parties) ; ce document ne couvre que le socle : le dataset
> comme objet de plateforme (arbitrage **A28**). Les autres briques du
> brainstorm analytics (pipeline de transformations, contexte global
> temps×emprise, cross-filter, requête visuelle, SQL Lab, drill, carte
> analytique) sont **hors périmètre**, réservées à SP-14b et suivants.

## 1. Objectif & non-buts

**Objectif.** Faire du dataset un objet de plateforme (A28) : une référence
nommée, cataloguée, partagée et permissionnée vers une collection (SP-3),
enrichie de métadonnées métier (libellés/descriptions/format par colonne),
immédiatement consommable par les widgets `chart`/`table`/`indicator`
existants — sans dupliquer l'agrégation ni le pipeline.

**Non-buts explicites** (reportés à SP-14b et suivants, pour ne pas fermer la
porte mais ne pas les construire ici) :

- Métriques nommées en CEL (`Metric` du brainstorm §5.2).
- Pipeline de transformations (`filter`/`join`/`derive`/`pivot`/`spatial`).
- Sources autres que `collection` (lake GeoParquet, `http`, ArcGIS FS,
  statique) — connecteurs futurs, hors A28.
- `refreshPolicy` / matérialisation planifiée (n'a de sens qu'avec un
  pipeline exécuté ; ici la requête est un passthrough vers la collection).
- Contexte analytique global (temps×emprise×filtres×sélection), cross-filter
  par défaut, bindings CEL généralisés.
- Requête visuelle, SQL Lab, drill « voir les entités », pivot, carte
  analytique (symbologie data-driven).

Le modèle reste additif : rien ici ne doit devoir être défait pour ajouter
ces briques ensuite.

## 2. Nommage — collision avec le « dataset » SP-13c

SP-13c a déjà introduit le mot « dataset » dans le shell : widget
`datasetCard` (« Fiche jeu de données »), `DatasetPage.tsx`,
`DatasetDownloadButtons` — tous désignent **une collection présentée comme
ressource open-data téléchargeable** (contexte DCAT/STAC), un concept
différent du nouvel objet de plateforme.

Décision : conserver « Dataset » pour le nouvel objet (conforme à A28,
`resource_type="dataset"` côté API), mais qualifier systématiquement dans
l'UI et la documentation :

- **« Dataset partagé »** ou **« Dataset analytique »** → le nouvel objet de
  plateforme (SP-14a).
- **« Fiche jeu de données »** → reste le libellé du widget/page SP-13c
  (téléchargement open-data), inchangé.

La distinction se fait au niveau du libellé et du contexte d'usage (catalogue
BI vs page publique de téléchargement), pas d'un renommage de `resource_type`.

## 3. Modèle de données (cœur)

Réutilisation stricte du patron existant `Item` + `BuilderConfig` discriminé
par `kind` (le même mécanisme qui a ajouté `"site"` en SP-13a) — pas de
nouveau module `core/app/datasets/` séparé : un dataset n'est aujourd'hui
qu'une référence + des libellés, un module dédié serait de la
sur-ingénierie.

- `Item.resource_type = "dataset"` : même table, même CRUD, même cycle de vie
  (owner, `is_published`/`is_public`, versionné, audité) que
  app/dashboard/map/site.
- `BuilderConfig.kind` gagne `"dataset"`, avec un champ optionnel
  `dataset: DatasetPayload | None` (miroir de `map: MapConfig | None`) :

```python
class DatasetColumnMeta(BaseModel):
    label: str | None = None
    description: str | None = None
    format: str | None = None  # libre (ex. "currency", "percent", "date"),
                                 # interprété côté widget consommateur

class DatasetPayload(BaseModel):
    source: Literal["collection"]  # seul type supporté en SP-14a
    collectionId: str
    columns: dict[str, DatasetColumnMeta] = {}
```

- **Le schéma n'est pas dupliqué.** Il reste dérivé à la volée de la
  collection source via `schema_json.table_info_to_schema` (déjà pur, déjà
  utilisé par SP-3/SP-4). Le dataset ne stocke que ses *surcharges*
  (`columns`) ; la lecture fusionne schéma introspecté + surcharges côté
  shell. Ça évite toute staleness si la collection évolue (colonne ajoutée/
  supprimée) sans avoir à invalider quoi que ce soit.

## 4. API cœur — réutilisation quasi totale

Un dataset suit le contrat générique déjà utilisé par app/dashboard/map/site :

- `POST /configs` — création (payload `kind: "dataset"`).
- `GET /configs/by-item/{pk}` / `PUT /configs/by-item/{pk}` — lecture/édition.
- `GET /items?type=dataset` — liste catalogue, filtrage/pagination déjà
  génériques (SP-1a).

**Aucune route dédiée `/datasets/*` n'est nécessaire.** Le schéma fusionné
est calculé côté shell : fetch du `DatasetPayload` (route config générique)
puis `GET /collections/{id}/schema` (SP-3, déjà existant), fusion en mémoire.

Seul ajout serveur : à la sauvegarde d'un config `kind="dataset"`, valider
que `collectionId` référence une collection existante et lisible par
l'utilisateur — même pattern que `_require_kind_payload` dans
`configs/schemas.py`, qui branche déjà par `kind`.

## 5. Permissions

Le dataset porte son propre partage (`can()`, owner, `is_published`/
`is_public`) — identique aux autres items, pas un simple héritage des droits
de la collection. Cohérent avec la règle d'architecture n°2 (tout objet de
plateforme est un document déclaratif schématisé, catalogué et permissionné
comme les autres).

**Double vérification à l'exécution** : lire le *dataset* (métadonnées,
catalogue) est une chose ; interroger les *données* via `features`/
`aggregate` re-vérifie indépendamment les droits sur la collection source
(RLS SP-3, déjà en place — rien à coder). Un dataset partagé plus largement
que sa collection source ne donne donc jamais accès aux données, seulement à
la référence et aux libellés.

## 6. Shell — gestion (création & promotion)

Deux points d'entrée, convergeant vers le même CRUD cœur :

- **Depuis le catalogue** : `NewItemButton` gagne l'option `kind: "dataset"`.
  Pas de layout builder générique (comme pour `map`, qui a déjà son propre
  flux) : un nouveau hook `useCreateDataset({title, owner, collectionId})` +
  un écran dédié `/datasets/:pk/edit` (`DatasetEditPage`, miroir de la page
  carte) — titre/résumé/tags (champs `Item` déjà génériques) + un tableau
  éditable colonne→libellé/description/format, alimenté par le schéma
  fusionné (§3).
- **Depuis le builder** : dans le panneau d'édition d'une `DataSource`
  (`features`/`statistics`), un bouton « Promouvoir en dataset partagé »
  crée l'item (`collectionId = source.layer`) et **réécrit l'entrée
  `dataSources[]` de l'app en place** pour qu'elle référence le nouveau
  dataset (`datasetId`) — pas de doublon, l'app consomme immédiatement
  l'objet partagé qu'elle vient de créer.

## 7. Shell — consommation par les widgets (sans nouveau pipeline)

`DataSource` gagne un champ optionnel `datasetId`, sibling de `layer` (qui
devient dérivable) :

```ts
export type DataSource = {
  id: string;
  type: "features" | "static" | "statistics";
  service: string;
  layer: string;       // résolu automatiquement si datasetId est présent
  datasetId?: string;
  query: Record<string, unknown>;
};
```

`itemClient.queryDataSource` / `featuresUrl` : si `datasetId` est renseigné,
résout `layer = <collectionId du dataset>` (fetch caché du config dataset)
puis délègue **strictement au code `features`/`statistics` existant**,
inchangé. Le sélecteur `DataSourceSelect` (déjà utilisé par `chart`/`data`/
`indicator`/`datasetCard`) liste en plus les datasets partagés accessibles,
à côté des sources inline de l'app — aucun widget ne change.

## 8. Catalogue & recherche

Gratuit : un item `resource_type="dataset"` traverse automatiquement
l'indexation pgvector (SP-7) et le flux de partage (SP-1c) — rien de
spécifique à coder.

## 9. Compatibilité & tests

- Config `version: 1` inchangée : `datasetId` est un champ additif optionnel
  sur `DataSource`, `"dataset"` un nouveau `kind` de `BuilderConfig` (comme
  `"site"` l'a été en SP-13a). Les 13 specs E2E existantes restent vertes
  sans modification.
- Nouvelle spec E2E : créer un dataset depuis le catalogue, éditer ses
  libellés de colonnes, le promouvoir depuis le panneau `DataSource` d'un
  widget existant, vérifier que le widget alimenté par `datasetId` affiche
  les mêmes données qu'avant promotion.
- Tests cœur : validation `collectionId` à la sauvegarde d'un config
  `kind="dataset"` (collection inexistante / non lisible → rejet), fusion
  schéma+overrides, permissions (`can()` sur le dataset indépendant de la
  RLS sur la collection sous-jacente).

## 10. Risques

| Risque | Garde-fou |
|---|---|
| Confusion avec le « dataset » SP-13c (téléchargement open-data) | Qualification systématique du libellé UI (« Dataset partagé/analytique » vs « Fiche jeu de données »), §2 |
| Un dataset pointe vers une collection supprimée/renommée | Le fetch du schéma fusionné échoue proprement (état `error` du widget, comme aujourd'hui pour une `DataSource` invalide) — pas de nouveau mode de panne |
| Sur-ingénierie prématurée (module dédié, refreshPolicy, métriques CEL) | Explicitement hors périmètre (§1) ; le modèle reste additif pour SP-14b |
