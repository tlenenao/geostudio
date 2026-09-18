# Pipeline builder — backlog d'améliorations UI/UX

Date : 2026-09-18. Statut : backlog validé par Tanguy, **pas de spec/plan
d'implémentation lancé à ce stade**. Chaque item structurel (marqué ⚙️
ci-dessous) devra être brainstormé séparément avant exécution.

## Contexte

Analyse fine du pipeline builder no-code (`kind="pipeline"`, SP-15a→h et
extensions depuis) : canvas DAG, palette de connecteurs, inspecteur de
paramètres, aperçus carte/tableau, exécution/planification. Racine :
`shell/src/pages/PipelineBuilderPage.tsx`, composants sous
`shell/src/builder/pipeline/` (`PipelineCanvas.tsx`, `PipelinePalette.tsx`,
`PipelineNodeInspector.tsx`, `PipelinePreviewPanel.tsx`,
`PipelinePreviewMap.tsx`, `PipelineRunPanel.tsx`,
`PipelineScheduleEditor.tsx`, `PipelineWebhookTrigger.tsx`,
`CollectionParamSelect.tsx`, `SecretParamSelect.tsx`), validation dans
`validation.ts`.

Benchmark de référence : **FME Form** (Safe Software) — déjà le
différenciateur produit retenu pour la parité de couverture de connecteurs
(Q2, 2026-09-15, cf. `CLAUDE.md`). Patterns confirmés en source (2026-09-18) :
Transformer Gallery avec recherche clavier (`/`), feature caching avec icône
verte (aperçu à jour) / jaune (aperçu périmé, cliquable pour rouvrir la
Visual Preview), comptage de features animé sur les arêtes pendant
l'exécution, raccourcis clavier (Entrée = paramètres, Ctrl+B = bookmark).
Sources : [Data Inspection in FME](https://support.safe.com/hc/en-us/articles/34068243662989-Data-Inspection-in-FME),
[FME Workbench Keyboard Shortcuts](https://docs.safe.com/fme/html/FME-Form-Documentation/FME-Form/Workbench/Workbench-Keyboard-Shortcuts.htm),
[Setting the Feature Count Display](https://docs.safe.com/fme/2024.0/html/FME-Form-Documentation/FME-Form/Workbench/Setting_the_Feature_Count_Display.htm).

Priorisation : impact utilisateur / gravité d'abord (bugs réels avant
améliorations), ambition assumée y compris sur des changements structurels.

## 0. Bugs à corriger en priorité

Ces trois points ne sont pas des manques d'ergonomie mais des défauts de
comportement qui minent la confiance dans l'outil.

1. **Erreurs de graphe invisibles.** `validatePipelineGraphLocally`
   (`validation.ts`) calcule `graphErrors` (cycle, arête entrante en
   double, pas de reader, pas de writer) mais cette valeur n'est rendue
   nulle part dans `PipelineBuilderPage.tsx` — seul `nodeErrors[nodeId]`
   s'affiche, et seulement pour le nœud sélectionné. Le bouton
   "Enregistrer" se contente d'être désactivé (`!valid`, ligne ~262) sans
   texte explicatif, et aucun nœud fautif n'est marqué dans le canvas.
   → Bandeau d'alerte persistant en haut du canvas listant les erreurs de
   graphe + badge visuel sur chaque nœud concerné + tooltip sur le bouton
   désactivé expliquant pourquoi.

2. **Aperçu jamais synchronisé avec le brouillon en cours d'édition.**
   `usePipelinePreview` (`pipelines.hooks.ts:47-54`) et
   `client.previewPipeline(pk, nodeId)` (`types.ts:531`, `pipelines.ts:94`)
   n'envoient que `pk` et `nodeId`, jamais les paramètres en cours
   d'édition dans l'inspecteur : modifier un champ ne met jamais à jour
   l'aperçu avant un "Enregistrer" explicite, sans que rien ne le signale.
   → Envoyer le draft courant à l'aperçu ; reprendre le modèle **feature
   caching** de FME : icône verte "aperçu à jour" / jaune "aperçu périmé,
   régénérer", plutôt que de laisser croire que l'aperçu affiché est
   fiable.

3. **Carte de preview figée sur le nœud précédent.** `PipelinePreviewMap.tsx`
   (lignes ~58-99) a un `useEffect` à dépendances vides (`// eslint-disable-next-line`)
   qui ne (re)construit la carte qu'au montage ; le composant n'étant
   jamais re-keyé par `nodeId` dans `PipelinePreviewPanel.tsx`, changer de
   nœud sélectionné pendant que la vue carte est active peut laisser
   affichées les features du nœud précédent.
   → Re-keyer le composant par `nodeId` ou corriger les dépendances de
   l'effet.

## 1. Canvas DAG (React Flow)

- Câbler `useUndoableDraft` (déjà livré SP-19, non utilisé dans ce
  contexte — `PipelineBuilderPage.tsx:68` utilise un `useState` nu).
- Ajout de nœud au clavier : focus canvas → `/` → recherche → Entrée
  (complète le drag-and-drop actuel, corrige au passage l'accessibilité
  clavier absente aujourd'hui).
- Mini-map (composant natif React Flow `MiniMap`, non monté actuellement —
  seuls `Background`+`Controls` le sont).
- Badge d'erreur visible directement sur le nœud (bordure/icône rouge
  dérivée de `nodeErrors`), pas seulement quand il est sélectionné —
  `KIND_COLOR` (`PipelineCanvas.tsx:50-54`) n'a aujourd'hui aucun état
  "erreur".
- Indicateur de fraîcheur d'aperçu par nœud (vert/jaune, cf. bug #2 du
  §0), cliquable pour ouvrir la preview.
- Liste des transforms insérables sur une arête dérivée dynamiquement du
  catalogue `OperationContract` (34 op au total), au lieu de la liste de
  11 codée en dur (`INSERTABLE_TRANSFORMS`, `PipelineCanvas.tsx:36-48`).
- Bookmarks/zones nommées regroupant des nœuds (annotation visuelle sur le
  canvas, pas un signet navigateur) — utile sur les gros pipelines.
- ⚙️ **Sous-pipelines réutilisables** (équivalent *Custom Transformer*
  FME) : encapsuler un sous-graphe en un nœud composite versionné et
  réutilisable. Item structurel le plus lourd de ce backlog — spec dédiée
  si retenu.
- Bouton de suppression visible sur le nœud, pas seulement
  Suppr/Backspace (`deleteKeyCode`, `PipelineCanvas.tsx:299`).
- Connexion d'arêtes accessible au clavier (source → Tab vers handle →
  Entrée → cible) — aujourd'hui uniquement drag souris sur les handles
  React Flow.

## 2. Palette connecteurs (`PipelinePalette.tsx`)

- Recherche/filtre texte (cohérent avec le `/` proposé pour le canvas).
- Icônes par catégorie + sous-catégories (géo / attribut / agrégation /
  I/O) — aujourd'hui 3 sections fixes (sources/transforms/writers) en
  liste plate sans icône.
- Libellés humains avec description courte visible sans survol, au lieu
  de l'id technique brut (`transform.h3Aggregate` etc., description
  actuellement en `title=` seulement, ligne ~43).
- Favoris / récemment utilisés en tête de liste.

## 3. Inspecteur de paramètres (`PipelineNodeInspector.tsx`)

- Regroupement des champs par section logique (ex. extension `x-group`
  sur le JSON Schema `OperationContract`) — aujourd'hui liste plate de
  champs dans l'ordre du schéma, labels = nom brut du champ.
- ⚙️ **Éditeur CEL dédié** avec coloration syntaxique + autocomplétion des
  champs disponibles en amont dans le graphe, au lieu d'un
  `<input type=text>` brut pour toute expression CEL. Item structurel —
  spec dédiée si retenu.
- Aide contextuelle enrichie : lien vers la doc de l'opération, exemples
  de valeurs (aujourd'hui seulement `prop.description` sous le champ).
- Validation inline par champ, pas seulement au niveau du nœud entier.

Connecteurs génériques déjà corrects fonctionnellement et à conserver tels
quels : `CollectionParamSelect.tsx` (liste filtrée par droit d'écriture),
`SecretParamSelect.tsx` (sélection + création inline, 7 types de secrets,
champs sensibles masqués).

## 4. Preview carte (`PipelinePreviewMap.tsx`)

- Symbologie minimale par type de géométrie (réutiliser le moteur de
  symbologie déjà livré SP-25/27 côté éditeur de carte plutôt que d'en
  écrire un nouveau) — aujourd'hui une seule couleur fixe (`#2563eb`) pour
  toutes les géométries.
- **Panneau "feature" : clic sur une géométrie → attributs de la feature
  affichés.** Comble un vide actuel : aucun mécanisme d'inspection
  individuelle n'existe dans ce contexte pipeline.
- Sélection liée carte↔tableau (cliquer une ligne surligne la feature sur
  la carte et vice-versa, comme la Visual Preview liée de FME).
- Légende minimale.

## 5. Preview tableau (`PipelinePreviewPanel.tsx`)

- Pagination / virtualisation — aujourd'hui aucune, table HTML brute de
  tout l'échantillon.
- Formatage par type (dates, nombres ; géométrie tronquée avec bouton
  "voir sur la carte" plutôt que WKB/JSON brut affiché tel quel,
  `String(row[c])` ligne ~68).
- Tri/filtre client léger sur les colonnes.
- Compteur "N lignes affichées sur l'échantillon total".

## 6. Exécution / historique / planification

- Détail par nœud pour **chaque** run historique — aujourd'hui seul le
  *dernier* run alimente les badges du canvas (`nodeStats`,
  `PipelineBuilderPage.tsx:200`) ; l'historique paginé
  (`PipelineRunPanel.tsx`) n'expose qu'un statut + une erreur textuelle
  globale par run, sans détail par nœud pour les runs passés.
- ⚙️ Suivi live par SSE/websocket au lieu du sondage manuel 1,5s
  (`PipelineRunPanel.tsx`) — touche le backend, spec dédiée si retenu.
- Durée calculée (fin − début), dates formatées localement (aujourd'hui
  date brute non formatée).
- Prochaine exécution cron affichée en clair ("prochaine exécution :
  demain 3h") — `PipelineScheduleEditor.tsx` valide seulement la forme de
  l'expression (`ADVANCED_CRON_RE`) sans expliquer le prochain
  déclenchement.
- "Exécuter jusqu'à ce nœud" (façon *breakpoint* FME) pour déboguer un
  pipeline long sans tout relancer.

## 7. Accessibilité / responsive

- Vérifier l'usage du canvas DAG sous 900px : `TriptychLayout` bascule en
  onglets sous le seuil `useNarrowViewport`, mais l'utilisabilité du DAG
  React Flow lui-même en largeur réduite n'est pas garantie.
- Navigation clavier complète (cf. §1 — ajout de nœud, connexion
  d'arêtes) : le drag-and-drop de la palette et la connexion d'arêtes
  React Flow restent aujourd'hui totalement non accessibles au clavier.
- Passer la page au crible de l'audit a11y déjà outillé (SP-57a,
  `a11y-audit.spec.ts`, axe-core) — pas encore couverte à ce jour.

## Notes de faisabilité

Les items marqués ⚙️ (sous-pipelines réutilisables, éditeur CEL avec
autocomplétion, suivi live SSE) sont structurels et mériteraient chacun
leur propre cycle brainstorm → spec → plan s'ils sont retenus pour
exécution. Le reste (§0 bugs, et la majorité des §1-7) tient dans une
taille de SP habituelle et peut être découpé en tâches indépendantes lors
d'un futur plan.

Recherche de code réelle (2026-09-18, avant écriture du plan) — deux
correctifs factuels et trois bonnes nouvelles côté backend :

- **La palette (§2) est déjà dynamique** : `GET /pipelines/ops`
  (`core/app/pipelines/routes.py:62-64` → `ops_catalog()`,
  `contracts.py:424-438`) expose déjà les 34 op activées, et
  `PipelinePalette.tsx` construit déjà ses 3 sections depuis cette route
  (`usePipelineOps`). Le gap réel n'est que cosmétique (recherche, icônes,
  libellés humains, favoris) — aucune route à ajouter.
- **`node_stats` par run existe déjà en base** (`PipelineRun.node_stats`,
  `core/app/pipelines/models.py:15-43`, écrit nœud par nœud pendant le run
  — `repository.py:135-147`) et **est déjà renvoyé pour chaque run de
  l'historique**, pas seulement le dernier (`RunStatus.nodeStats`,
  `GET /pipelines/{item_id}/runs`, `routes.py:86-110`). Forme :
  `{nodeId, op, rowCount}` — pas de statut/erreur/durée par nœud, mais
  assez pour distinguer "nœud atteint (N lignes)" de "nœud jamais atteint"
  sur un run passé. L'item §6 "détail par nœud pour chaque run" est donc
  quasi entièrement frontend : `PipelineBuilderPage.tsx:200` n'exploite
  aujourd'hui que le *dernier* run pour badger le canvas.
- **`croniter>=6.2` est déjà une dépendance backend** (SP-15h,
  `pyproject.toml:44`), déjà utilisée pour le balayage cron
  (`repository.py:5,198`) — exposer "prochaine exécution" au frontend
  est un endpoint stateless trivial, aucune nouvelle dépendance.
- **L'arrêt partiel d'exécution existe déjà côté preview** :
  `_execute_transform_chain(..., stop_at=...)` (`runtime.py:663-741`)
  s'arrête déjà au nœud demandé. `run_pipeline()` (vrai run,
  `runtime.py:1089+`) n'expose pas ce paramètre — "Exécuter jusqu'à ce
  nœud" en run réel demanderait de le plomber à travers `run_pipeline` et
  de sauter la boucle des writers, réutilisant une logique déjà en place.
  Néanmoins la fonctionnalité complète (nouveau statut de run "partiel",
  persistance, UI dédiée) reste un morceau cohérent en soi — reportée en
  backlog (cf. ci-dessous) plutôt que downscopée dans le premier plan.

## Périmètre retenu pour le premier plan (2026-09-18)

**Correction (même jour) :** une première version de cette section
proposait une coupe à ~16 tâches, décidée avant que le plan complet ne
soit livré et sans revalidation avec Tanguy. Le plan effectivement écrit
et commité — `docs/superpowers/plans/2026-09-18-pipeline-builder-ux-improvements.md`
(`a206c529`), 22 tâches TDD — a repris le périmètre initialement validé
("bugs + tout le non-structurel des §1-7") et l'a mené à bien avec du code
réel, en ne reportant qu'un seul item au-delà des ⚙️ déjà actés. La coupe
à 16 tâches ci-dessous n'a donc **jamais été appliquée** ; cette section
est corrigée pour refléter le plan réel plutôt que l'inverse (piège n°12
du dépôt).

**Dans le plan (22 tâches, `a206c529`)** : §0 intégralement (Tasks 1-3) ;
§1 canvas sauf sous-pipelines réutilisables — badge d'erreur par nœud,
indicateur de fraîcheur d'aperçu, liste de transforms dérivée du
catalogue, mini-map, undo/redo, bouton de suppression, recherche/ajout au
clavier, connexion d'arêtes au clavier, zones annotées persistées (Tasks
1, 4-10) ; §2 palette — recherche, icônes, description visible, favoris
(Tasks 8, 11-12) ; §3 inspecteur sauf éditeur CEL — regroupement
requis/optionnel, erreurs inline par champ (Tasks 13-14) ; §4 preview
carte — couleur par type de géométrie + légende, sélection liée
carte↔tableau + panneau d'attributs de feature (Tasks 15-16) ; §5 preview
tableau — pagination, formatage par type, tri de colonnes (Tasks 17-19) ;
§6 exécution/planification sauf suivi SSE — détail par nœud par run
historique, durée calculée, prochaine exécution cron affichée en clair
(Tasks 20-22).

**Reporté (hors ce plan)** : les 3 items ⚙️ (sous-pipelines réutilisables,
éditeur CEL dédié, suivi live SSE), plus **"Exécuter jusqu'à ce nœud"**
comme fonctionnalité complète de run partiel persisté — découvert en
cours de plan comme touchant `app/pipelines/jobs.py` (le worker), pas
seulement la route ; l'infra `stop_at` reste prête côté preview
(`_execute_transform_chain`, cf. plus haut) pour qui reprend ce chantier.
§7 a11y/responsive n'a **pas besoin** d'item séparé : le plan a trouvé que
`shell/e2e/a11y-audit.spec.ts` (SP-57a) et
`shell/e2e/triptych-narrow.spec.ts` couvrent déjà cette page — seule la
vraie navigation clavier manquante est ajoutée (Tasks 8-9).
