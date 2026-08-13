# SP-14o — Requête visuelle (dernière pièce de SP-14, jalon M11)

Date : 2026-08-12
Statut : validé, prêt pour plan d'implémentation

## Contexte

SP-14 (Analytics UX) a livré 14 sous-parties (SP-14a→n) : datasets, contexte
global temps×emprise, cross-filter (y compris inter-datasets, SP-14n), widgets,
SQL Lab, source ArcGIS, MCP analytique, bookmarks. Il ne restait, selon la
feuille de route (`docs/vision/2026-07-04-feuille-de-route-geostudio.md:720`),
que la **« requête visuelle »** (Filtrer → Joindre → Résumer → Trier compilant
vers l'API analytique structurée, A19) — explicitement bloquée par
l'amendement A39 sur le moteur de pipeline no-code de SP-15, qui n'existait
pas encore au moment où SP-14n a été spécifié (« *Une fois SP-14n livré, il ne
reste au contenu SP-14 de la feuille de route que la requête visuelle, bloquée
sur le moteur de pipeline de SP-15* », en-tête de la spec SP-14n).

SP-15 (a, c, d, e, f, g, h) est depuis livré : le moteur de pipeline no-code
existe (`core/app/pipelines/`), avec un catalogue d'opérations incluant
`transform.filter`, `transform.select`, `transform.derive`,
`transform.aggregate`, `transform.join`, `transform.merge`, et un
`writer.dataset` qui « crée/mets à jour un dataset analytique SP-14 depuis un
pipeline » (SP-15c). Ce document couvre le dernier maillon : l'UI no-code qui
compose ces briques pour l'utilisateur final, sans qu'il touche jamais au
canvas DAG complet ni à une syntaxe de requête.

Ce SP est numéroté **SP-14o** (dernière lettre de la série SP-14a→n) : il clôt
le contenu de SP-14 et le jalon M11.

## Décision structurante : mécanique choisie

Deux mécaniques étaient possibles : une requête **live** (l'API `aggregate`
existante, réévaluée à chaque affichage, mais sans support de jointure ni de
tri côté serveur — il aurait fallu les ajouter) ou une requête **matérialisée**
via le moteur de pipeline SP-15 (`writer.dataset`, rafraîchie à la demande ou
sur cron).

**Choisi : matérialisée via pipeline.** Réutilise intégralement le moteur
SP-15 (ops catalog, runtime, job procrastinate, planification SP-15h) sans
aucun ajout de capacité de jointure/tri côté API `aggregate`. Contrepartie
assumée : les données ne sont pas "live", il faut relancer le pipeline (manuel
ou cron) pour les rafraîchir — cohérent avec le reste de la plateforme
(datasets ArcGIS, exports, alertes fonctionnent déjà tous sur des cycles
d'évaluation périodiques, pas un flux continu).

## Périmètre de l'assistant

Point d'entrée : `NewItemButton` (`shell/src/shell/NewItemButton.tsx`) gagne
une option **« Dataset par requête visuelle »**, visible seulement si
`instanceQuery.data?.etlEnabled` (même garde que l'option "Pipeline"
existante). Elle navigue vers une nouvelle page `VisualQueryWizardPage`.

L'assistant présente 5 étapes en formulaire vertical (pas un wizard à
navigation forcée) — seule la première est obligatoire :

1. **Collection de base** (obligatoire) — sélection d'une collection lisible,
   plus un champ **Titre** unique. Ce titre nomme le dataset créé (l'artefact
   qui compte pour l'utilisateur) ; le pipeline sous-jacent, invisible en
   usage normal, reçoit un titre dérivé automatiquement (ex. « Requête —
   <titre> ») sans champ supplémentaire à remplir.
2. **Filtrer** (optionnel) — lignes structurées `colonne / opérateur / valeur`
   combinées en ET, opérateurs proposés selon le type de colonne (texte,
   nombre, date, booléen — métadonnées déjà exposées par le schéma de
   collection existant). Compilées en une expression scalaire SQL DuckDB
   bornée pour `transform.filter` (correction post-spec : ce champ n'est pas
   du CEL, contrairement à ce qu'affirmait une première lecture — voir
   `core/app/pipelines/expr_validation.py`, qui corrige lui-même une erreur
   similaire de l'étude de faisabilité d'origine) — **aucune syntaxe n'est
   jamais montrée à l'utilisateur**, la décision UX reste inchangée.
3. **Joindre** (optionnel, une seule collection jointe en v1 — le modèle
   `TransformJoinParams` est binaire de toute façon) — collection jointe,
   **une seule colonne de jointure, portant le même nom dans les deux
   collections** (le SQL généré utilise `JOIN ... USING (col)`, qui exige un
   nom partagé), `inner`/`left`.
4. **Résumer** (optionnel) — `groupBy` (multi-colonnes) + liste de métriques
   nommées (colonne source + fonction d'agrégat + alias).
5. **Planifier** (optionnel) — réutilise tel quel `PipelineScheduleEditor` /
   `PipelineRefreshPolicy` (SP-15h), aucun nouveau code de planification.

**Aucune étape « Trier »** : le tri reste entièrement côté client sur les
widgets consommant le dataset (comportement déjà livré,
`shell/src/builder/widgets/data.tsx`), qui satisfait déjà ce besoin sans
capacité serveur supplémentaire — il n'existe aujourd'hui aucune opération de
tri dans le catalogue de pipeline, et ce document ne propose pas d'en ajouter.

## Nouvelle capacité cœur : provisionnement de la collection de sortie

`writer.dataset` réutilise `writer.collection`
(`core/app/pipelines/runtime.py:521-534`), qui **exige une collection cible
déjà existante** avec un schéma de colonnes défini — il n'existe aujourd'hui
aucune création de collection à la volée depuis un pipeline. La route
d'enregistrement de collection existante (`POST /collections`,
`core/app/collections/routes.py:154`) est admin-only et exige que la table
Postgres existe déjà (introspection, pas création) — inadaptée à un flux
no-code pour un utilisateur non-admin.

**Précédent réutilisable** : l'ingestion GeoJSON/CSV (SP-6a,
`core/app/ingestion/importer.py:90-153`) crée déjà une table à la volée
(`CREATE TABLE public.ingest_<uuid>(...)` avec schéma inféré des valeurs
observées, `apply_collection_ddl`, puis `collections_repo.create_collection`)
— **hors du chemin admin**, pour un utilisateur normal.

**Nouvelle fonction** `create_empty_collection(session, *, tenant_id,
owner_id, title, columns: dict[str, str], geometry_type: str | None, srid:
int | None) -> Collection`, dans `core/app/collections/` (en-dessous de
`app.pipelines` dans le contrat de couches, même sens de dépendance que
`reader.collection`/`writer.collection` aujourd'hui). Factorise le motif
`CREATE TABLE` + `apply_collection_ddl` + `create_collection` de l'ingestion,
sans insertion de lignes (table vide, remplie par le premier run du
pipeline). `geometry_type`/`srid` sont nullables : si la collection de base
(et la jointe, le cas échéant) n'a pas de colonne géométrie
(`Collection.geometry_column is None`, cas déjà supporté par le modèle
`Collection` existant), la table créée n'a pas de colonne `geom` — l'ingestion
SP-6a, elle, en crée toujours une car elle importe systématiquement du
GeoJSON avec géométrie ; cette fonction partagée doit couvrir le cas
non-spatial que l'ingestion n'a jamais eu besoin de gérer. Un nouveau point de
route dédié à la création "dataset par requête" appelle cette fonction —
distinct de `POST /collections` (admin, introspection), le tracé exact de la
route est laissé au plan d'implémentation.

Note pour le plan (hors périmètre de ce lot) : l'ingestion SP-6a pourrait à
terme être refactorée pour appeler cette même fonction avant d'insérer ses
lignes — pas fait ici, pour ne pas élargir le périmètre de SP-14o.

**Règles d'inférence du schéma résultant**, calculées côté shell à partir des
schémas déjà introspectés (collection de base + éventuellement jointe,
déjà exposés par l'API collections existante) :

- Pas de jointure, pas de résumé → colonnes de la collection de base, telles
  quelles.
- Jointure active, pas de résumé → colonnes des deux collections ; en cas de
  collision de nom, le wizard insère automatiquement une étape
  **`transform.select` implicite** (pré-remplie `base.<col>` / `jointe.<col>`,
  présentée comme une simple liste de cases à cocher/renommer — jamais comme
  une "étape technique select").
- Résumé actif → colonnes = `groupBy` (type de la colonne source) + une
  colonne par métrique nommée (typage fixe par fonction : `count` → entier,
  `sum`/`avg`/`min`/`max` → type de la colonne source agrégée).

## Modèle de données

`DatasetPayload` (`core/app/configs/schemas.py:117`) gagne un champ nullable
**`sourcePipelineId: str | None = None`** — pas de migration (config JSON).
Validé seulement si présent (doit référencer un item `pipeline` existant et
lisible par l'utilisateur). Absent = dataset créé à la main (comportement
actuel inchangé, y compris les datasets `arcgis`).

## Flux de bout en bout

Au clic « Créer » dans `VisualQueryWizardPage` :

1. Le shell calcule le schéma résultant (règles ci-dessus) à partir des
   schémas déjà connus des collections base/jointe.
2. Appel au nouveau point de provisionnement → collection de sortie vide
   créée, `collectionId` retourné. Échec (collision de nom, quota...) bloque
   la création avant toute persistance de pipeline — pas d'état à moitié créé.
3. Le shell compile un `PipelineConfigPayload` standard (nœuds/arêtes,
   positions auto-calculées comme le fait déjà `PipelineCanvas` pour l'édition
   manuelle) : `reader.collection` → [`transform.filter`] → [`transform.join`]
   → [`transform.select` implicite] → [`transform.aggregate`] →
   `writer.dataset(collectionId=<sortie>, title=<titre choisi>)`, avec la
   `refreshPolicy` si une planification a été choisie.
4. Sauvegarde du pipeline via la route générique de configs (même chemin que
   `PipelineBuilderPage` à son premier "Enregistrer").
5. Déclenche `POST /pipelines/{id}/run`.
6. `writer.dataset` (déjà livré, `runtime.py:521-586`) crée l'item `dataset`
   avec `source: "collection"` pointant vers la collection de sortie. Le
   shell effectue ensuite une mise à jour de cette config pour y ajouter
   `sourcePipelineId` (`writer.dataset` ne connaît pas ce champ).
7. Redirection vers `DatasetEditPage` du dataset créé.

Un run raté laisse le pipeline sauvegardé mais aucun dataset créé — cohérent
avec le comportement pipeline existant (l'item `dataset` n'est créé que dans
la branche succès de `_write_dataset`).

## Réouverture (« Modifier la requête »)

`DatasetEditPage` affiche un bouton conditionnel **« Modifier la requête »**,
visible si `sourcePipelineId` est renseigné. Au clic, le shell lit le pipeline
lié et tente de le « décompiler » vers l'état du formulaire : reconnaît
uniquement la forme attendue (`reader.collection` → [`filter`] → [`join`] →
[`select` implicite] → [`aggregate`] → `writer.dataset`, rien d'autre — pas de
branchement supplémentaire, pas de nœud additionnel). Si la forme ne
correspond pas (pipeline modifié à la main dans le canvas complet depuis), le
bouton affiche un message explicite et renvoie vers `PipelineBuilderPage` en
lecture plutôt que vers l'assistant.

## Composants UI shell

- `VisualQueryWizardPage` — orchestre les 5 étapes.
- `QueryFilterBuilder` — lignes colonne/opérateur/valeur, compile en
  expression SQL DuckDB bornée (fonction pure, testable isolément du reste
  du composant).
- `QueryJoinPicker` — collection jointe + une colonne de jointure partagée
  + `inner`/`left`.
- `QuerySummaryBuilder` — `groupBy` multi-colonnes + liste de métriques
  (colonne source + fonction + alias).
- Réutilisés tels quels : `PipelineScheduleEditor`, un panneau de poll du même
  patron que `PipelineRunPanel` pour suivre le premier run.
- `DatasetEditPage` : nouveau bouton conditionnel « Modifier la requête ».

## Tests

- **Cœur (pytest)** : `create_empty_collection` (schémas variés, types,
  collisions de nom de table) ; nouveau point de route de provisionnement
  (permissions non-admin, 400 sur schéma invalide) ; validation
  `DatasetPayload.sourcePipelineId` (référence pipeline existante/lisible).
- **Shell (Vitest)** : compilateur SQL du filtre (cas simples + combinaisons
  ET, échappement des valeurs) ; compilateur wizard → `PipelineConfigPayload` (les combinaisons
  d'étapes actives/inactives) ; décompilation pipeline → état formulaire
  (forme reconnue vs non reconnue).
- **E2E (Playwright)** : parcours complet « Créer un dataset par requête »
  (filtre seul, puis filtre+jointure+résumé) ; le dataset créé est ensuite
  consommable par un widget existant comme n'importe quel dataset ; parcours
  « Modifier la requête » sur un dataset existant.

## Hors périmètre (explicitement)

- Jointures chaînées (plus d'une collection jointe) — le modèle
  `TransformJoinParams` reste binaire, une seule jointure par requête visuelle
  en v1.
- Toute capacité de tri côté serveur/pipeline.
- Requête live (réévaluée à chaque affichage sans matérialisation).
- Refactorisation de l'ingestion SP-6a pour réutiliser `create_empty_collection`.
- Exposition de la sélection de colonnes comme étape visible quand aucune
  jointure n'est active (le passthrough complet de la collection de base
  reste implicite).
