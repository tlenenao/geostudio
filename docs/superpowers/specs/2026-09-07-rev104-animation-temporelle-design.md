# REV-104/GAP-10 — Animation temporelle (play/pause/vitesse) sur le contexte temps global

Date : 2026-09-07. Ferme **REV-104**/**GAP-10** (`docs/revue/2026-09-04-backlog.md:1028`,
`docs/revue/2026-09-04-analyse-gaps.md:171`) — chantier **4.17** de la revue
de projet (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md:417`) :

> **Animation temporelle** (H3) — lecture play/pause/vitesse sur le contexte
> temps global A29 déjà livré, pas un nouveau système de filtrage. Une carte
> et un graphique liés au même dataset s'animent ensemble.

Ce chantier n'a **pas** été discuté en détail avec Tanguy (contrairement aux
six autres chantiers GAP de cette campagne) : la spec reste délibérément
**minimale et réversible** — cf. §5 Hors périmètre.

## 0. Ce qui a été vérifié avant d'écrire (piège CLAUDE.md n°3/n°12)

Le brief qui a lancé ce chantier supposait l'existence d'un composant
« `TimeSlider` ou équivalent » avec un curseur ponctuel avançant selon un
grain. **Ce composant n'existe pas.** Vérifié par lecture complète des
fichiers réels, pas par grep de surface :

- Le contexte temps×emprise global (A29) est **`AnalyticsContextState`**
  (`shell/src/builder/AnalyticsContext.tsx`, 172 lignes, lu en entier) :
  `{ timeRange: {from, to} | null; extent: [minX,minY,maxX,maxY] | null;
  crossFilter: {...} }`. `timeRange`/`extent` sont des chaînes/tuples bruts,
  aucune notion de grain n'y est stockée. Les setters (`setTimeRange`,
  `setExtent`, `setCrossFilter`, `clearCrossFilter`) sont des no-ops silencieux
  quand le `AnalyticsContextProvider` est monté avec `interactions="manual"`
  (`active = interactions === "auto"`, ligne 76) — invariant à préserver, pas
  à contourner.
- Le seul contrôle d'auteur qui **écrit** dans `timeRange` aujourd'hui est le
  widget **`dateRangeFilter`** (`shell/src/builder/widgets/dateRangeFilter.tsx`,
  67 lignes, lu en entier) : deux `<input type="date">` (« Date de début »,
  « Date de fin »), état React local `from`/`to` (jamais persisté — remis à
  `""` à chaque montage, comportement déjà existant, hors périmètre de ce
  chantier), qui appellent `setTimeRange({from, to})` dès que les deux sont
  renseignées. **Aucune notion de grain, de curseur ponctuel, ni
  d'avancement automatique n'existe dans ce widget.** C'est le composant le
  plus proche d'un « curseur temporel » du dépôt, et c'est celui que ce
  chantier étend — **pas de nouveau widget** (contrainte de scope, cf. §5).
- **`AnalyticsContextIndicator`** (`shell/src/builder/AnalyticsContextIndicator.tsx`)
  n'est qu'un bandeau de puces (« période active », « emprise active »,
  cross-filters) avec bouton de suppression par puce — pas un contrôle
  d'édition, pas un curseur.
- Les « 6 grains temporels » de SP-23 sont le type **`BucketGranularity`**
  (`shell/src/lib/comparisonWindow.ts:12`) :
  `"hour" | "day" | "week" | "month" | "quarter" | "year"` — c'est
  **exactement** `AggregateRequestBody.bucket` côté cœur
  (`core/app/analytics/aggregate.py`, confirmé par
  `shell/src/api/generated/core-schema.d.ts:1680`). Ce type existe déjà et
  est déjà exposé à l'auteur ailleurs dans le shell : le sélecteur
  `BUCKET_OPTIONS` de `shell/src/builder/DataSourcePanel.tsx:11-18` (grain de
  regroupement des sources `statistics` pour un graphique/tableau croisé),
  avec ses 6 clés i18n `dataSourcePanel.bucket{Hour,Day,Week,Month,Quarter,Year}Option`.
  Ce chantier **réutilise ce même type et ces mêmes clés i18n** plutôt que
  d'en créer un nouveau jeu (contrainte du brief).
- **`derivePatch`** (`shell/src/lib/analyticsPatch.ts:11-62`, lu en entier)
  est le mécanisme qui relie n'importe quel widget consommant des données
  (carte, graphique, indicateur, tableau…) au contexte global : pour toute
  `DataSource` dont le `DatasetConfig` déclare un `timeField`, `derivePatch`
  ajoute `${timeField}__gte`/`${timeField}__lte` dérivés de
  `ctx.timeRange`. C'est ce mécanisme, déjà livré et déjà générique
  vis-à-vis du type de widget, qui fait qu'« une carte et un graphique liés
  au même dataset s'animent ensemble » **dès que `timeRange` change** — ce
  chantier n'a donc **rien à modifier** dans `derivePatch`,
  `DataContext.tsx`, `mapWidget.tsx` ni `chart.tsx` : il suffit de faire
  avancer `timeRange` automatiquement pour que tout widget déjà lié au
  contexte se remette à jour, exactement comme il le fait déjà pour un
  déplacement manuel des deux `<input type="date">`.
- `DatasetConfig` (`shell/src/api/types.ts:756-774`) n'expose aucune borne
  min/max de date connue côté client (pas de statistique de plage
  pré-calculée) — confirmé par lecture complète du type. Il n'existe donc
  aujourd'hui aucun moyen de déduire automatiquement « la plage complète de
  ce dataset » sans une requête `statistics` dédiée (comme le fait
  `sliderFilter.tsx` pour les bornes numériques min/max d'un champ, via
  `useQuery` + agrégats `min`/`max`). Conséquence pour la conception (§2) :
  les bornes de la lecture automatique restent celles que l'auteur/l'usager
  saisit déjà dans les deux champs de date existants — **aucune requête
  réseau supplémentaire n'est ajoutée** par ce chantier.
- Précédent direct pour « minuteur annulé proprement au démontage » : SP-60
  (GAP-68) a posé le patron `mountedRef`/`timerRef` +
  `setTimeout` auto-reprogrammé (pas `setInterval`) sur
  `shell/src/builder/print/ExportPanel.tsx` (lignes 36-43, 49-61), déjà
  répliqué sur `Terrain3DUploadButton`, `Tileset3DUploadButton`,
  `PipelineRunPanel`, `ImportFileButton`. Ce chantier reprend le même
  patron plutôt que `setInterval` brut (permet de suspendre/reprendre par un
  simple test sur une ref, sans jamais laisser un tick en vol après pause ou
  démontage).
- Précédent direct pour falsifier ce patron sans assertion de durée réelle
  (piège CLAUDE.md n°7) : `shell/src/builder/print/ExportPanel.test.tsx`
  (`beforeEach(() => vi.useFakeTimers())`, `vi.advanceTimersByTimeAsync(...)`,
  test « ne re-sonde pas après démontage » ligne 87-101).

## 1. Décision de scope

**Étendre le widget `dateRangeFilter` existant** avec :

1. Un nouveau champ de config auteur **`grain`** (`BucketGranularity`,
   réutilisé tel quel), qui définit le pas d'avancement automatique.
2. Des contrôles de lecture **Lecture/Pause** + **3 préréglages de
   vitesse** (Lente/Normale/Rapide) sur le widget lui-même, à l'exécution
   (runtime/preview/édition — pas de distinction de mode, comme le reste du
   widget aujourd'hui).
3. Un état de lecture (`en cours` / `en pause`, vitesse courante, position
   du curseur) **entièrement local au composant React** (`useState`),
   **jamais persisté** dans `AppConfig`/`WidgetInstance.props` ni nulle
   part ailleurs — seul `grain` (choix d'auteur, comme `label` aujourd'hui)
   est un champ de config persistée.

### Pourquoi étendre ce widget plutôt qu'en créer un nouveau

- La contrainte de scope l'exige explicitement.
- C'est déjà le seul widget qui **écrit** dans `timeRange` — dupliquer ce
  rôle dans un second widget créerait une source de vérité concurrente pour
  le même champ du contexte global (deux widgets sur la même page
  pourraient tenter de piloter `timeRange` en même temps, avec des bornes
  différentes) sans qu'aucun mécanisme d'arbitrage n'existe aujourd'hui —
  hors périmètre d'introduire un tel arbitrage pour ce chantier Confort.
- Les deux champs de date existants sont l'ingrédient exact dont
  l'animation a besoin comme bornes (§2.1) : aucune information
  supplémentaire à collecter.

### Pourquoi les bornes de lecture sont les deux champs de date existants,
### pas une plage déduite du dataset

Sans borne connue côté client (§0), il faudrait soit (a) ajouter une requête
`statistics` min/max comme le fait `sliderFilter.tsx` pour un champ
numérique, soit (b) réutiliser un couple de dates déjà saisi. (a) ajoute une
dépendance réseau et un couplage à `ctx.data?.datasetId` que ce widget n'a
jamais eu (il ne connaît aujourd'hui aucun dataset, uniquement le contexte
global) — changement de nature du widget, pas une extension minimale. (b)
ne coûte rien de plus que ce qui existe déjà : les deux `<input type="date">`
définissent la plage de lecture exactement comme ils définissent déjà la
plage filtrée aujourd'hui en mode non animé. **Décision : (b).**

### Grain horaire : exclu du sélecteur de lecture, sans être réinventé

`BucketGranularity` inclut `"hour"`, réutilisé tel quel comme type (aucune
valeur inventée). Mais le sélecteur de vitesse/grain de **ce widget** ne
propose que 5 des 6 valeurs : `day`, `week`, `month`, `quarter`, `year` —
**`hour` est délibérément exclu de la liste déroulante**, documenté ici
plutôt que silencieusement omis : les deux champs de date du widget sont des
`<input type="date">`, précision jour. Faire avancer une chaîne
`"YYYY-MM-DD"` d'une heure ne change la date affichée qu'une fois toutes les
24 avancées (au passage de minuit) — 23 ticks sur 24 seraient visuellement
un no-op, ce qui serait un défaut d'UX immédiatement perceptible et non un
simple détail. Ajouter une précision sous-journalière au widget (passer les
deux champs en `datetime-local`) est un changement plus large que ce
chantier conservateur ne couvre pas — noté en hors périmètre (§5). Le type
`BucketGranularity` n'est pas modifié : c'est bien le sélecteur de *ce*
contrôle qui restreint les valeurs qu'il propose, pas le type partagé.

## 2. Architecture

### 2.1 État et données

```ts
// shell/src/builder/widgets/dateRangeFilter.tsx — état local, aucun ajouté
// ailleurs, rien de persisté au-delà de `grain` (nouveau champ configSchema)
type PlaybackStatus = "idle" | "playing" | "paused";
type PlaybackSpeed = "slow" | "normal" | "fast";

const SPEED_INTERVAL_MS: Record<PlaybackSpeed, number> = {
  slow: 2000,
  normal: 1000,
  fast: 400,
};
```

- `props.grain: BucketGranularity` (nouveau champ `configSchema`, défaut
  `"day"`, sélecteur dans `PropsPanel` — même forme que `BUCKET_OPTIONS`
  de `DataSourcePanel.tsx` mais limité à 5 valeurs, cf. §1). Persisté
  normalement dans `AppConfig` comme tout autre `configSchema` (ce n'est pas
  de la « donnée d'état de lecture » — c'est un choix d'auteur, au même
  titre que `label`).
- `from`, `to` (état local existant, inchangé) : les deux bornes de la
  plage de lecture, saisies par les deux `<input type="date">` existants.
- `playback: PlaybackStatus` (nouveau, local, jamais persisté).
- `speed: PlaybackSpeed` (nouveau, local, jamais persisté, défaut
  `"normal"`).
- `cursorFrom, cursorTo: string` (nouveau, local, jamais persisté) : bornes
  de la **fenêtre courante** émise vers `setTimeRange` pendant la lecture —
  une fenêtre large d'exactement un grain, qui glisse entre `from` et `to`.

### 2.2 Fonction pure d'avancement de grain

Nouveau module `shell/src/lib/timeAnimation.ts` (pur, testable
indépendamment du composant, même esprit que `comparisonWindow.ts` dont il
réutilise le type `BucketGranularity` et le style d'arithmétique UTC
calendaire — jamais `Date` en heure locale, pour rester cohérent avec le
commentaire déjà présent dans `comparisonWindow.ts:20-23`) :

```ts
export type AnimationGrain = Exclude<BucketGranularity, "hour">;

// Avance une date "YYYY-MM-DD" de `count` unités de `grain`, en arithmétique
// calendaire UTC (mois/trimestre/année : jour cadré à la fin du mois cible,
// même règle que shiftYears() dans comparisonWindow.ts — pas de dérive de
// jour en fin de mois).
export function addGrain(dateIso: string, grain: AnimationGrain, count = 1): string;

// Fenêtre initiale d'un cycle de lecture : [start, addGrain(start, grain, 1)].
export function initialWindow(
  start: string,
  grain: AnimationGrain,
): { from: string; to: string };

// Avance la fenêtre courante d'un grain ; si la nouvelle borne de fin dépasse
// `loopEnd`, boucle en repartant de `loopStart` (comportement de lecture en
// boucle, pas d'arrêt en fin de plage — cf. §2.3).
export function stepWindow(
  current: { from: string; to: string },
  bounds: { loopStart: string; loopEnd: string },
  grain: AnimationGrain,
): { from: string; to: string };
```

`stepWindow` est la seule fonction avec une règle de décision (boucle) ; les
trois autres sont de l'arithmétique de date pure. Toutes testées
indépendamment du composant React (pas de timer, pas de DOM) — cf. plan.

### 2.3 Cycle de lecture

- **Lecture non démarrée (`idle`)** : comportement **strictement
  inchangé** par rapport à aujourd'hui — modifier `from`/`to` appelle
  `setTimeRange({from, to})` directement, comme avant ce chantier. Le
  bouton Lecture n'apparaît/n'est activable que si `from` **et** `to` sont
  renseignés (il faut une plage pour définir les bornes de la boucle) et
  que `addGrain(from, grain) <= to` (au moins un pas tient dans la plage —
  sinon Lecture reste désactivé, pas d'erreur silencieuse).
- **Lecture démarrée (`playing`)** : au clic sur Lecture, capture
  `loopStart = from`, `loopEnd = to` (figés pour tout le cycle — modifier
  les champs de date pendant la lecture arrête la lecture, cf. dernier
  point ci-dessous), initialise `cursor = initialWindow(loopStart, grain)`,
  appelle `setTimeRange(cursor)` immédiatement, puis programme un
  `setTimeout` (patron `timerRef`/`mountedRef`, §0) à
  `SPEED_INTERVAL_MS[speed]`. Chaque tick : `cursor =
  stepWindow(cursor, {loopStart, loopEnd}, grain)`, `setTimeRange(cursor)`,
  reprogramme le prochain `setTimeout`.
- **Pause (`paused`)** : annule le `setTimeout` en attente
  (`timerRef.current` cleared). `timeRange` reste figé sur la dernière
  fenêtre émise (pas de remise à zéro). Cliquer de nouveau sur Lecture
  reprend l'avancement depuis cette même fenêtre — pas de redémarrage
  depuis `loopStart`.
- **Changement de vitesse en cours de lecture** : le prochain `setTimeout`
  programmé utilise le nouvel intervalle ; le tick en attente n'est pas
  ré-ordonnancé rétroactivement (cohérent avec le patron existant, pas
  besoin d'un mécanisme de rattrapage pour un chantier Confort).
- **Modifier `from` ou `to` pendant `playing` ou `paused`** : arrête la
  lecture (`playback → "idle"`, timer annulé) et retombe sur le
  comportement non animé (`setTimeRange({from, to})` direct avec les
  nouvelles valeurs) — les deux champs de date restent la seule interface
  d'édition manuelle de la plage active, exactement comme avant ce
  chantier ; il n'y a pas de bouton « Stop » séparé (hors périmètre du
  brief, qui ne demande que Lecture/Pause/Vitesse).
- **Démontage du widget pendant `playing`** : le `setTimeout` en attente
  est annulé (`mountedRef`/cleanup d'effet), aucun tick ne s'exécute après
  démontage — même garantie que SP-60/GAP-68.
- **`interactions="manual"` sur `AnalyticsContextProvider`** : `setTimeRange`
  est déjà un no-op silencieux dans ce mode (§0) ; aucun changement
  nécessaire ici, le minuteur peut tourner sans effet observable — comme le
  widget actuel le fait déjà pour l'édition manuelle des deux champs de
  date dans ce même mode (test existant « is a no-op when interactions is
  manual »).

### 2.4 Contrôles UI

Ajoutés dans le `Component` du widget, sous les deux champs de date
existants :

- Bouton unique bascule Lecture/Pause (icône/texte selon `playback`),
  `aria-pressed` reflétant `playback === "playing"`, désactivé si
  `!from || !to || addGrain(from, grain) > to`.
- Un `<select>` de vitesse (3 options, Lente/Normale/Rapide), toujours
  actif (modifiable même en pause ou à l'arrêt, prend effet au prochain
  tick si en lecture).
- Le `<select>` de grain (5 options, §1) déplacé dans `PropsPanel` (choix
  d'auteur, pas de contrôle runtime) — même styliste que
  `DataSourcePanel.tsx`'s `BUCKET_OPTIONS`, réutilisant les mêmes clés i18n
  `dataSourcePanel.bucket{Day,Week,Month,Quarter,Year}Option` plutôt que
  d'en dupliquer le texte sous de nouvelles clés.
- Nouvelles clés i18n (domaine `widgetDateRangeFilter.*`, cohérent avec les
  clés existantes du même widget) : libellé du bouton Lecture, libellé du
  bouton Pause, `aria-label` du sélecteur de vitesse, libellés des 3
  options de vitesse, `aria-label` du sélecteur de grain, libellé de champ
  du grain dans `PropsPanel`.

## 3. Critères d'acceptation

1. Un widget `dateRangeFilter` avec `from`/`to` renseignés et un grain
   configuré affiche un bouton Lecture activé ; le cliquer démarre une
   avancée automatique de la fenêtre temporelle affichée par pas de un
   grain, à la vitesse par défaut (Normale).
2. Pendant la lecture, tout autre widget de la même page lié au même
   dataset (carte, graphique, indicateur…) dont le `DatasetConfig` déclare
   un `timeField` se met à jour à chaque tick, **sans modification** de
   `DataContext.tsx`, `analyticsPatch.ts`, `mapWidget.tsx` ni `chart.tsx`
   (vérifié par un test d'intégration qui monte deux widgets consommant le
   même `AnalyticsContextProvider` et n'observe que le widget `dateRangeFilter`
   comme source d'action).
3. Pause arrête l'avancement sans réinitialiser la fenêtre affichée ;
   Lecture reprend depuis cette même fenêtre.
4. Changer de vitesse pendant la lecture change l'intervalle entre deux
   ticks suivants (mesuré en ticks simulés via `vi.useFakeTimers()`, jamais
   par une assertion de durée réelle — piège CLAUDE.md n°7).
5. La fenêtre boucle : une fois `loopEnd` dépassée, le tick suivant repart
   de `loopStart` plutôt que de continuer à avancer indéfiniment ou de
   s'arrêter.
6. Modifier `from` ou `to` pendant la lecture ou la pause arrête la lecture
   et repasse en filtrage manuel direct (comportement non animé
   préexistant, non régressé).
7. Démonter le widget pendant la lecture n'exécute plus aucun tick après
   démontage (pas d'avertissement React « state update on unmounted
   component », pas d'appel à `setTimeRange` post-démontage).
8. `interactions="manual"` sur le provider ne casse rien : le minuteur peut
   tourner, `timeRange` ne change jamais (test miroir du test existant
   « is a no-op when interactions is manual »).
9. Aucun champ nouveau n'apparaît dans `AppConfig`/`WidgetInstance.props`
   en dehors de `grain` — `playback`/`speed`/position du curseur n'existent
   dans aucune sérialisation (vérifié par un test qui inspecte les props
   sauvegardées après une session de lecture complète : elles sont
   identiques à avant le clic sur Lecture, à l'exception de `grain` s'il a
   été changé dans `PropsPanel`).
10. `addGrain`/`initialWindow`/`stepWindow` sont testés indépendamment du
    composant React (fonctions pures, `shell/src/lib/timeAnimation.test.ts`),
    y compris les cas de cadrage de fin de mois pour `month`/`quarter`/`year`
    (mois de longueurs différentes, année bissextile) — même exigence que
    `shiftYears` dans `comparisonWindow.ts`.
11. Aucune régression sur les deux tests existants de
    `dateRangeFilter.test.tsx` (comportement non animé, mode manual).
12. Diff `openapi.json`/`core-schema.d.ts` vide (chantier shell-only, aucune
    route ni modèle du cœur touché — à vérifier plutôt que supposer, piège
    CLAUDE.md n°1).

## 4. Fichiers touchés (exhaustif, aucun autre)

- `shell/src/lib/timeAnimation.ts` (nouveau) + `.test.ts` (nouveau).
- `shell/src/builder/widgets/dateRangeFilter.tsx` (modifié).
- `shell/src/builder/widgets/dateRangeFilter.test.tsx` (étendu).
- `shell/src/i18n/catalog.fr.ts` (nouvelles clés, domaine
  `widgetDateRangeFilter.*`).
- Un test d'intégration nouveau (critère d'acceptation 2), positionné à
  côté de `dateRangeFilter.test.tsx` ou dans
  `shell/src/builder/AppRenderer.test.tsx` selon ce que le plan choisit
  (décision d'implémentation, pas de spec — les deux emplacements existent
  déjà et accueillent déjà des tests inter-widgets).

Aucun fichier `core/` touché. Aucune migration. Aucun changement à
`AnalyticsContext.tsx`, `analyticsPatch.ts`, `DataContext.tsx`,
`mapWidget.tsx`, `chart.tsx`, `comparisonWindow.ts`, `DataSourcePanel.tsx`
(uniquement lus/réutilisés, jamais modifiés).

## 5. Hors périmètre (explicite)

- **Export de l'animation en vidéo/GIF** — aucune capture d'écran, aucun
  encodage, aucun job d'export. Question produit potentiellement
  intéressante mais sans rapport avec ce chantier Confort.
- **Synchronisation d'animation entre plusieurs apps ou onglets** — l'état
  de lecture est local au composant monté dans un seul onglet ; ouvrir la
  même app dans un second onglet démarre une lecture indépendante. Pas de
  canal de synchronisation (`BroadcastChannel`, WebSocket, etc.).
- **Vitesse personnalisée arbitraire** — seulement les 3 préréglages
  Lente/Normale/Rapide (`SPEED_INTERVAL_MS`) ; pas de champ numérique libre
  ni de curseur de vitesse continu.
- **Grain horaire dans le sélecteur de lecture** — cf. §1 (widget à
  précision jour, `datetime-local` hors périmètre).
- **Bornes de lecture déduites automatiquement des données du dataset**
  (comme le fait `sliderFilter.tsx` pour un champ numérique) — cf. §1,
  décision (b). Resterait une extension naturelle mais ajoute une
  dépendance réseau et un couplage nouveau (`ctx.data?.datasetId`) hors
  scope minimal.
- **Bouton Stop distinct de Pause** — le brief ne demande que
  Lecture/Pause/Vitesse ; modifier `from`/`to` fait déjà office d'arrêt
  complet (§2.3).
- **Persistance de l'état de lecture dans `AppConfig` ou un
  `BookmarkPayload`** — `playback`/`speed`/position du curseur restent
  strictement éphémères, jamais sérialisés, jamais restaurés au rechargement
  de la page (contrainte explicite du brief). Un signet (`Bookmark`,
  SP-14m) capturé pendant une lecture fige `timeRange` à sa valeur
  instantanée au moment de la capture, comme il le fait déjà aujourd'hui
  pour toute valeur de `timeRange` — comportement inchangé, pas un nouveau
  cas à gérer.
- **Un second widget capable de piloter `timeRange`** (par exemple un
  curseur ponctuel autonome hors du widget `dateRangeFilter`) — cf. §1,
  explicitement refusé par la contrainte « pas de nouveau widget ».
- **Arbitrer le comportement à date d'aujourd'hui si `to` est dans le
  futur, ou tout garde-fou lié à des dates hors plage réelle des données**
  — le widget ne connaît toujours pas les données sous-jacentes (§0),
  inchangé par ce chantier.

## 6. Auto-revue

- Pas de TBD ni de point laissé en suspens : chaque décision (§1) est
  justifiée par ce qui a été lu dans le code réel, jamais par supposition.
- Pas de contradiction : le seul champ persisté (`grain`) est cohérent avec
  §2.1, §2.4, §3 (critère 9) et §5 (« pas de persistance de l'état de
  lecture ») — ces trois passages se répondent sans se contredire.
- Portée bornée : §4 énumère exhaustivement les fichiers touchés ; tout
  fichier cité ailleurs dans le document (`AnalyticsContext.tsx`,
  `analyticsPatch.ts`, `DataContext.tsx`, `mapWidget.tsx`, `chart.tsx`,
  `comparisonWindow.ts`, `DataSourcePanel.tsx`) est marqué explicitement
  « lu, jamais modifié ».
- Le mécanisme de bouclage (§2.3) est décidé une seule fois (boucle, pas
  arrêt en fin de plage) et n'est pas remis en cause ailleurs dans le
  document.
- Falsifiabilité : chaque critère d'acceptation (§3) est formulé de façon
  observable (un test peut le vérifier vrai ou faux), et le §0 fournit déjà
  le patron exact (`ExportPanel.test.tsx`) pour falsifier le critère 7 sans
  assertion de durée réelle.
