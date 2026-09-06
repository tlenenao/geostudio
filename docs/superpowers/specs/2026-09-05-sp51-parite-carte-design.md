# SP-51 — Parité carte : widget App Builder vs éditeur autonome

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (issu de la revue SP-42, `docs/revue/2026-09-04-analyse-gaps.md`)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-52, GAP-53,
GAP-35, GAP-45, GAP-46, GAP-36), `docs/revue/2026-09-04-backlog.md`,
`CLAUDE.md` §« Pièges récurrents » (n°3, n°5, n°12).

**Portée de ce document** : un inventaire vérifié et un ordre d'exécution pour
fermer 6 écarts de parité entre la carte de l'éditeur autonome
(`shell/src/pages/MapEditorPage.tsx` + `shell/src/map/*`) et le widget carte de
l'App Builder (`shell/src/builder/widgets/mapWidget.tsx`). Aucun code n'est
modifié ici — c'est le texte qui deviendra le plan SP-51.

**Coordination avec SP-54 — à lire avant d'exécuter l'un ou l'autre plan** :
voir §7. SP-51 et SP-54 sont deux chantiers issus de la même revue, découpés
après le passage de SP-43 (qui a éclaté `shell/src/api/itemClient.ts` en
`shell/src/api/base.ts` + `shell/src/api/domains/*.ts`, et `core/app/mcp/
tools.py` en `core/app/mcp/tools/*.py` — **vérifié sur le dépôt réel au moment
d'écrire cette spec, cf. §0**, pas supposé d'après un brief antérieur).

---

## 0. Vérification préalable de la structure du dépôt (piège CLAUDE.md n°12)

Le message de commande de cette spec décrit une refonte SP-43 qui aurait
« découpé le monolithe `itemClient.ts` (1743 lignes) » — formulé au
conditionnel, à vérifier. Vérification faite le 2026-09-05 sur `dev` :

- `shell/src/api/itemClient.ts` fait aujourd'hui **58 lignes** — un point
  d'entrée qui compose les méthodes depuis 15 fichiers
  `shell/src/api/domains/*.ts` (`alerts`, `apps`, `attachments`,
  `collectionsAdmin`, `datasets`, `exportsIngestion`, `extensionsAdminTools`,
  `features`, `identity`, `items`, `layers`, `notifications`, `pipelines`,
  `reports`, `tiles3d`) + `shell/src/api/base.ts` (client HTTP bas niveau,
  cache dataset, **`toFrontLayer`/`RawMapLayer`**, `FeatureValidationError`).
  Le découpage a bien eu lieu — **déjà terminé**, pas seulement planifié.
- `shell/src/api/hooks.ts` fait **17 lignes**, ré-exportant 11 modules
  `shell/src/api/domains/*.hooks.ts` — également déjà découpé.
- `core/app/mcp/tools.py` **n'existe plus** : remplacé par un paquet
  `core/app/mcp/tools/` (12 modules par domaine : `alerts.py`,
  `analytics.py`, `attachments.py`, `bookmark.py`, `catalog.py`,
  `configs.py`, `dataset.py`, `identity.py`, `pipelines.py`, `reports.py`,
  `sharing.py`). Ce découpage aussi est **déjà terminé** (SP-43 est donc plus
  avancé, au moment d'écrire cette spec, que ce que sa propre fiche de
  clôture pourrait laisser supposer — à confirmer par la session qui clôt
  SP-43, hors périmètre d'ici).
- `core/app/roles/kind_registry.py` existe déjà (registre kind→privilège
  unique, §3.1 de la spec SP-43) — également terminé.

**Conséquence pour ce document** : tous les pointeurs de fichier ci-dessous
sont vérifiés contre l'état **actuel** du dépôt, pas contre les numéros de
ligne d'`itemClient.ts`/`mcp/tools.py` cités par la revue SP-42 originale
(devenus caducs). Quand un pointeur de `docs/revue/2026-09-04-analyse-gaps.md`
s'est révélé faux ou obsolète, c'est noté explicitement ci-dessous (piège
CLAUDE.md n°3 : « le texte littéral d'un plan ou d'un brief est régulièrement
faux sur les interfaces tierces » — s'applique aussi à un backlog de revue).

---

## 1. Motivation

Règle d'architecture n°3 de CLAUDE.md : « Apps et dashboards = un seul
runtime `AppRenderer(config, mode)` avec modes edit/preview/runtime. Pas de
deuxième moteur. » Le widget carte de l'App Builder et l'éditeur de carte
autonome partagent déjà largement ce principe côté **rendu** : les deux
délèguent la compilation de peinture à `MapView` (commentaire
`mapWidget.tsx:273-277`, hérité de SP-27), et les deux éditeurs de symbologie/
popup (`MapSymbologyEditor`, `PopupEditor`) sont **le même composant partagé**
(commentaire `MapSymbologyEditor.tsx:19-22` : « Éditeur partagé par les DEUX
surfaces... même précédent que PopupEditor.tsx »).

Mais côté **capacités d'auteur** (ce qu'un utilisateur peut configurer depuis
le `PropsPanel` du widget), cinq écarts subsistent — un auteur d'App ne peut
configurer aucune des cinq capacités suivantes, alors qu'un auteur de carte
autonome le peut toutes. Trois catégories distinctes de couches n'ont, elles,
strictement aucune UI d'auteur nulle part (deck.gl agrégé) ou une UI
incomplète sur une seule des deux surfaces (opacité raster, peinture brute).

---

## 2. GAP-52 : 5 jumelles annoncées, 4 confirmées, 1 déjà résolue

`docs/revue/2026-09-04-analyse-gaps.md:187` liste cinq jumelles manquantes
dans `mapWidget.tsx`. Vérification poste par poste :

### 2.1 Classification Jenks — **confirmé, réel**

`mapWidget.tsx:223` fige `jenksAvailable={false}`, et `sampleField` (ligne
224-228) lève systématiquement une erreur explicite : « Jenks sur le widget
carte nécessite un collectionId résolu — non câblé ». Deux tests documentent
ce choix comme délibéré (`mapWidget.test.tsx:187-235`, dont un test qui
affirme littéralement l'absence de l'option `jenks` dans le `<select>` de
classification). Le commentaire ligne 219-222 explique la raison : le
`PropsPanel` n'a pas de `collectionId` résolu de façon synchrone à l'instant
où l'auteur choisit une source de données.

**Piste de fermeture vérifiée non triviale mais réaliste** : le callback
voisin `runStatistics` (lignes 200-218) contourne exactly ce problème en
délégant la résolution asynchrone à `client.queryDataSource({ layer:
dataSource?.layer, datasetId, query })` — une méthode qui résout déjà en
interne, via `resolveDataset()` (`shell/src/api/base.ts:191`), le cas d'un
`DataSource` adossé à un `datasetId` (recherche du `collectionId` réel
derrière le dataset) **et** le cas d'une source `features` branchée
directement sur une collection (`dataSource.layer` porte alors directement le
`collectionId`, cf. commentaire lignes 205-213). `sampleField` (utilisé pour
Jenks) n'a aujourd'hui aucun équivalent asynchrone de ce patron — c'est
l'écart réel à combler, pas une impossibilité technique. `ItemClient` n'a pas
de méthode « échantillonner un champ depuis un `DataSource` » (seulement
`sampleCollectionField(collectionId, field, limit)`, qui exige un
`collectionId` déjà résolu) — il en faut une, symétrique de
`queryDataSource`.

### 2.2 Contrôle caméra 3D (pitch/bearing) — **confirmé, réel**

Le widget construit `config: MapConfig` à chaque rendu avec
`view: { center: [2.4, 46.6], zoom: 5 }` (ligne 290) — jamais de `pitch`/
`bearing`, et aucun contrôle dans le `PropsPanel` pour les régler. L'éditeur
autonome, lui, expose `CameraControls` (`shell/src/map/CameraControls.tsx`,
composant réutilisable, props `{ pitch, bearing, onChange }`) dans
`MapEditorPage.tsx:163-167`.

### 2.3 Sélection de fond de carte — **confirmé, réel**

`mapWidget.tsx:23` fige `DEFAULT_STYLE =
"https://demotiles.maplibre.org/style.json"`, utilisé tel quel ligne 289 —
aucun moyen pour l'auteur de choisir un autre fond. L'éditeur autonome
expose `BasemapSelect` (`shell/src/map/BasemapSelect.tsx`, composant
réutilisable, liste `BASEMAPS` de `shell/src/map/basemaps.ts`) dans
`MapEditorPage.tsx:161`.

### 2.4 Terrain 3D configurable — **confirmé, réel**

`config` (ligne 288-307) ne porte jamais de champ `terrain`, bien que
`MapConfig.terrain?: MapTerrainConfig | null` existe dans le type
(`shell/src/api/types.ts:251`) et soit pleinement supporté par `MapView`
(`applyTerrain`, cf. inventaire SP-43 §2.2). L'éditeur autonome expose
`TerrainPanel` (`shell/src/map/TerrainPanel.tsx`, composant réutilisable,
gère aussi le choix d'une source hébergée SP-18/Terrain3D) dans
`MapEditorPage.tsx:162`.

### 2.5 Palette « theme-primary » — **NON confirmé : déjà implémenté**

Le GAP affirme que le widget n'offre pas la palette « Thème du site »
(`theme-primary`, un `PaletteId` résolu depuis `ThemeColors.primary`,
`shell/src/builder/widgets/palette.ts:4-5,64-68`). **Faux à la date de cette
spec** :

- `mapWidget.tsx:199` passe déjà `themeColors={theme?.colors}` à
  `MapSymbologyEditor` dans le `PropsPanel` (author-time) — ligne présente
  depuis le commit `e2a0a74b` (« le widget carte utilise LayerSymbology au
  lieu d'encodings »), **antérieur** à la revue SP-42/SP-42 du 2026-09-04.
- `mapWidget.tsx:281` passe aussi `ctx.theme?.colors` à
  `symbologyToPaintInputs` au rendu (render-time, `Component`).
- Un test dédié le prouve déjà : `mapWidget.test.tsx:176-185` (« PropsPanel
  mounts MapSymbologyEditor with theme from props ») vérifie que l'option
  `theme-primary` apparaît dans le `<select>` de palette dès que
  `theme.colors.primary` est fourni ; `mapWidget.test.tsx:546-580` prouve
  que `ctx.theme.colors` atteint effectivement `MapView` pour la résolution
  au rendu.
- `FieldClassificationPicker.tsx:111` (`{themeColors?.primary && <option
  value="theme-primary">Thème du site</option>}`) est le composant partagé
  qui porte cette logique — déjà alimenté correctement par les deux
  surfaces.

**Conclusion** : ce 5e point du GAP-52 est retiré du périmètre d'exécution.
Aucune tâche ne le corrige — il n'y a rien à corriger. C'est noté
explicitement (piège CLAUDE.md n°12 : « revérifier dans le code avant
d'écrire qu'un point est réglé ou ouvert », y compris pour un point que la
revue elle-même déclare ouvert). L'effort restant du GAP-52 (annoncé 5-8j
pour cinq jumelles) est donc réévalué à ~4-6j pour les quatre jumelles
réelles.

---

## 3. GAP-53 : outils de mesure/croquis jamais montés en édition

Confirmé. `shell/src/pages/MapEditorPage.tsx` instancie `MapView` à deux
endroits (mode export ligne 96, mode édition normal ligne 145) — **aucun des
deux ne passe `interactiveTools`**. `MapView` ne rend
`MapMeasureSketchToolbar` (bouton « Mesurer », « Surface », etc. —
`shell/src/map/MapMeasureSketchToolbar.tsx:421-439`) que si
`interactiveTools && readyMap` (`shell/src/map/MapView.tsx:1420-1422`). Le
mécanisme est déjà entièrement partagé (même composant que celui utilisé par
le widget carte en mode Aperçu/Exécution, `mapWidget.tsx:321` : `
interactiveTools={ctx.mode !== "edit"}`) — c'est un oubli de câblage, pas un
mécanisme à construire. Un auteur de carte autonome ne peut aujourd'hui
mesurer une distance/surface ou faire un croquis que depuis l'Aperçu d'une
App ou un site publié, jamais depuis sa propre page d'édition.

Estimation confirmée : câblage seul (~1j), aucun code de production
nouveau — juste `interactiveTools={!readOnly}` (ou une constante `true`,
à trancher en tâche : la mesure ne modifie pas la config, donc elle n'a pas
besoin d'être gardée par `readOnly` comme `Enregistrer`) sur l'instance de
`MapView` en mode édition (ligne 145 uniquement — le mode export, ligne 96,
reste délibérément sans outils, c'est un rendu figé pour Playwright).

---

## 4. GAP-35 : opacité d'une couche raster, aucune UI

Confirmé. `LayerPicker.tsx:32` fixe `opacity: 1` à la création d'une couche
raster, sans jamais l'exposer ensuite. `LayersPanel.tsx:215` ne rend le bloc
d'édition inline (`LayerPopupEditor` + `LayerSymbologyEditor`) que pour
`layer.kind === "vector" || layer.kind === "feature"` — **une couche
`raster` n'a aucun bloc d'édition du tout**, alors que `opacity` est
pleinement consommé au rendu (`MapView.tsx:561` : `paint: { "raster-opacity":
layer.opacity ?? 1 }`). Round-trip API déjà complet (`RawMapLayer.opacity`,
`toFrontLayer()` cas `"raster"`, `base.ts:53-59`) — seul le contrôle
manque.

---

## 5. GAP-45 : peinture MapLibre brute, round-trip complet mais aucune UI

Confirmé, avec correction de pointeur. Le GAP citait `itemClient.ts:107,137`
— fichier disparu depuis SP-43. Localisation actuelle : `shell/src/api/
base.ts:46` (cas `"vector"`, `...(l.paint ? { paint: l.paint } : {})`) et
`base.ts:76` (cas `"feature"`, même patron). `MapView.tsx` consomme
`layer.paint` comme **repli** quand `layer.symbology` est absent (mécanisme
antérieur à SP-25/SP-27, conservé pour la compatibilité descendante d'une
config existante ou d'une écriture MCP/API directe — cf. §7 de la spec
SP-27 citée dans le README de cette famille de widgets). Grep confirmé vide
sur `paint` en tant que **champ écrit** dans `LayerPicker.tsx`,
`LayersPanel.tsx`, `MapSymbologyEditor.tsx` : seule la forme structurée
(`symbology`) est proposée à l'auteur, jamais l'expression MapLibre brute.

**Décision de portée** : ne pas essayer de faire disparaître `paint` (rule
CLAUDE.md n°2 : un objet de plateforme est un document déclaratif, mais
`paint` reste une échappatoire volontaire pour un usage avancé/MCP — pas un
défaut à masquer). Fournir un éditeur texte JSON minimal, réservé à un mode
« Avancé » explicite, plutôt qu'un formulaire structuré pour chaque
propriété MapLibre (dépasserait largement l'effort 2-3j annoncé et
dupliquerait la logique déjà couverte par `symbology`).

---

## 6. GAP-36 : aucune UI d'auteur pour une couche `'deck'`

Confirmé. `LayerPicker.tsx` n'a pas de branche pour créer une couche
`kind: "deck"` (seules `vector`/`raster`/`tiles3d` viennent de
`toMapLayer(source)`, et `feature`/`tiles3d` ont un formulaire d'ajout par
URL — rien pour `deck`). `LayersPanel.tsx:215` ne rend un bloc d'édition que
pour `vector`/`feature` — une couche `deck` n'a, comme `raster`, **aucun**
bloc d'édition. Pourtant `MapLayer` (kind `"deck"`, `types.ts:225-233`) et
son rendu (`MapView.tsx` : `HeatmapLayer`/`HexagonLayer`/`ColumnLayer` via
`buildDeckLayer`, `deckType`/`dataUrl`/`props`) sont pleinement implémentés
et testés unitairement avec une config écrite à la main
(`MapView.test.tsx`). Aucun outil MCP n'expose non plus la création d'une
telle couche (confirmé : `core/app/mcp/tools/catalog.py`/`configs.py` ne
citent jamais `deckType`).

**Décision de portée** : fournir l'UI d'auteur minimale (choix du type
`heatmap`/`hexbin`/`column`, URL de données, un sous-ensemble des `props`
les plus utiles par type — rayon pour heatmap/hexbin, hauteur pour column)
dans `LayerPicker.tsx` (ajout) + `LayersPanel.tsx` (édition inline, même
patron que `raster` pour l'opacité). L'exposition MCP (mentionnée par le
GAP) est **hors périmètre de ce plan** : `update_config`/`save_map_config`
génériques permettent déjà d'écrire une couche `deck` par une IA qui compose
le document JSON directement (rule CLAUDE.md n°2) — un outil MCP dédié
serait un confort, pas un déblocage, et n'est pas comptabilisé dans les
6 GAPs demandés par ce chantier ; à reprendre séparément si voulu.

---

## 7. Coordination avec SP-54 (chantier parallèle, même famille SP-43)

**SP-54** (« API shell (ItemClient) : combler les surfaces + partage
avancé ») a été spécifié le même jour, à partir de la même revue SP-42, et
touche des surfaces adjacentes issues du même découpage SP-43. Vérification
faite au moment d'écrire cette spec (transparence, pas une supposition
recopiée) :

- **Chevauchement confirmé** : `shell/src/api/base.ts` est touché par SP-54
  (TTL/invalidation de `datasetCache`, ligne 189 du fichier actuel) ; SP-51
  ne le touche **pas** dans son périmètre actuel (GAP-46, seul point qui
  aurait pu y toucher, est déjà résolu — §8 ci-dessous — donc aucune tâche
  de ce plan ne modifie `base.ts`). Même fichier, régions différentes :
  risque de conflit de merge **faible mais non nul** si les deux plans sont
  exécutés en parallèle par deux sessions distinctes sans coordination (un
  rebase mécanique suffit dans ce cas précis, mais seulement si les deux
  diffs sont vus l'un après l'autre).
- **Chevauchement probable mais non garanti** : `shell/src/api/types.ts`
  (interface `ItemClient`) est presque certainement touché par SP-54
  (`createGroup`/`addMember`, `Me` étendu, `listCollections(q)`) ; SP-51 n'a
  identifié aucun besoin d'y toucher (les cinq types de couches et leurs
  champs existent déjà, cf. §2-§6) — mais une découverte en cours
  d'exécution (ex. un champ `props` de couche `deck` jugé insuffisant)
  pourrait changer cela.
- Les deux plans touchent, plus largement, la même famille de fichiers
  générée par SP-43 (`shell/src/api/domains/*.ts` et `*.hooks.ts`) même si,
  à l'analyse, SP-51 ne touche concrètement que des fichiers UI
  (`shell/src/map/*.tsx`, `shell/src/builder/widgets/mapWidget.tsx`) et
  jamais les fichiers `domains/*.ts` eux-mêmes.

**Recommandation, à appliquer avant toute exécution réelle des deux plans** :
séquencer (SP-51 puis SP-54, ou l'inverse — l'ordre importe peu, aucune
dépendance fonctionnelle entre les deux) **ou** confier les deux à la même
session/agent si une exécution simultanée est souhaitée. Ne pas lancer deux
implémenteurs différents en parallèle sans l'un des deux garde-fous
ci-dessus — cf. précédent CLAUDE.md « Sessions concurrentes sur le même
arbre » (piège récurrent, `docs/superpowers/plans/2026-09-05-sp51-parite-
carte.md` §Global Constraints reprend cette note mot pour mot).

---

## 8. GAP-46 : déjà résolu — vérification, pas correction

Le GAP (`docs/revue/2026-09-04-analyse-gaps.md:181`) affirme un trou de
lecture dans `toFrontLayer()` pour `collectionId`/`pkColumn` sur une couche
`'feature'` — 4e occurrence de la classe de défaut documentée par CLAUDE.md
(piège récurrent n°5). **Vérification sur le code actuel : ce défaut est
déjà corrigé, avec un test de régression ET le test caractéristique de
SP-43 tous deux déjà en place :**

- `shell/src/api/base.ts:70-82` (cas `"feature"` de `toFrontLayer`) lit déjà
  `collectionId`/`pkColumn` (lignes 77-78).
- `shell/src/api/itemClient.test.ts:583-625` porte un test de régression
  nommé explicitement, commentaire à l'appui : « SP-42 F-shell-carte-01 (4e
  occurrence du piège n°5) : toFrontLayer() restaure déjà collectionId/
  pkColumn pour une couche vector ; la couche feature les perdait au
  rechargement ». Autrement dit, **la revue SP-42 elle-même a déjà trouvé et
  corrigé ce défaut**, le jour même où l'analyse de gaps citée par ce
  chantier semble l'avoir listé comme encore ouvert — un désaccord interne à
  la session SP-42, pas une régression de session ultérieure.
- Le test caractéristique ajouté par SP-43 Étape 2
  (`itemClient.test.ts:657-678`, « feature: every optional field
  survives ») couvre déjà explicitement `collectionId`/`pkColumn` dans son
  jeu d'assertions (lignes 665-666, 673-674) — donc une 5e régression sur ce
  champ précis serait détectée immédiatement, sans action supplémentaire.

**Conclusion** : aucune tâche de correction n'est nécessaire. Le plan porte
une tâche de vérification-seule (relancer les deux tests ciblés, confirmer
qu'ils passent, documenter la clôture) — pas pour ajouter du filet
(il existe déjà), mais pour que ce GAP ne soit pas rouvert par erreur dans un
futur backlog qui recopierait `docs/revue/2026-09-04-analyse-gaps.md` sans
revérifier le code (exactement le mécanisme du piège n°12).

---

## 9. Ordre d'exécution proposé (du moins au plus risqué)

1. **GAP-46** — vérification seule, risque nul.
2. **GAP-53** — câblage d'une prop déjà supportée par `MapView`, risque
   très bas.
3. **GAP-35** — ajout d'un contrôle dans un bloc conditionnel existant,
   risque bas.
4. **GAP-52 / basemap** — réutilisation directe de `BasemapSelect`, risque
   bas (composant déjà utilisé ailleurs, aucune modification du composant
   lui-même attendue).
5. **GAP-52 / terrain** — réutilisation directe de `TerrainPanel`, risque
   bas à moyen (le composant gère aussi la liste des sources hébergées via
   une capacité d'instance, `terrain3dEnabled` — à vérifier que le contexte
   du widget peut la fournir).
6. **GAP-52 / caméra** — réutilisation directe de `CameraControls`, risque
   bas (mais nécessite de faire persister `pitch`/`bearing` dans les props
   du widget, un nouveau champ jamais lu par ce widget jusqu'ici).
7. **GAP-45** — nouvelle UI (éditeur JSON en mode avancé), risque moyen
   (surface d'auteur nouvelle, à valider contre une entrée malformée sans
   jamais faire planter le rendu).
8. **GAP-52 / Jenks** — le plus délicat des quatre jumelles réelles :
   nécessite une nouvelle méthode `ItemClient` (résolution asynchrone d'un
   `collectionId` depuis un `DataSource`, symétrique de `queryDataSource`),
   risque moyen à élevé.
9. **GAP-36** — nouvelle UI + nouveau type de couche pleinement authorable,
   le plus gros morceau, risque le plus élevé (surface neuve la plus large :
   ajout à `LayerPicker`, édition inline dans `LayersPanel`, choix de
   `props` par `deckType`).

---

## 10. Hors périmètre (explicite)

- **Tout changement du contrat `ItemClient` exporté vers les autres
  domaines** (règle n°1 CLAUDE.md) — la seule extension prévue (une méthode
  d'échantillonnage de champ par `DataSource`, tâche Jenks) est additive,
  jamais un changement de signature existante.
- **L'exposition MCP de la création d'une couche `deck`** (mentionnée par
  GAP-36 mais non comptée dans son estimation d'effort ni dans le périmètre
  retenu ici, cf. §6).
- **Toute modification de `shell/src/api/domains/layers.ts` ou `base.ts`**
  — vérifié non nécessaire pour les 6 GAPs de ce chantier (le round-trip
  API existe déjà pour tous les champs concernés).
- **La 5e jumelle du GAP-52** (palette theme-primary) — déjà implémentée,
  cf. §2.5.
- **Les 3 autres divergences de patron listées par la spec SP-43 §4** (hors
  sujet ici, famille de fichiers différente).
