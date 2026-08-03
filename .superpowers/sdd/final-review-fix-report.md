# Correction issue de revue finale — SP-14f (branche `dev`, HEAD 5461b34)

## Constat

Le contrôle « Nombre de classes » du panneau de propriétés du widget `chart`
(`shell/src/builder/widgets/chart.tsx`, gated par `showBins =
chartType === "histogram"`) était mort : il écrivait `props.bins`, mais
`chartOption.ts`'s `buildOption` ne lit jamais ce champ — le binning de
l'histogramme est calculé côté cœur (`/collections/{id}/aggregate`) à partir
de `query.bins`, réglé par le contrôle « Nombre de classes (source …) » du
`DataSourcePanel`, qui est le seul chemin qui fonctionne réellement (et que
l'E2E `analytics-context.spec.ts` couvre).

Un auteur réglant le nombre de classes uniquement depuis le panneau du
graphique (le plus visible, juste à côté de « Type de graphique: Histogramme »)
n'avait aucun effet, et s'il ne touchait jamais le panneau DataSource,
`/aggregate` recevait une requête sans `bins`, retournant des lignes sans
`bucketStart`/`bucketEnd`/`count` → axes `"NaN–NaN"`, barres à hauteur nulle.

## Fix appliqué

Suppression du contrôle mort et de tout ce qui le supportait, la source de
vérité restant exclusivement le `DataSourcePanel` :

1. `shell/src/builder/widgets/chart.tsx`
   - Suppression du bloc JSX `{showBins && (...)}` dans `PropsPanel`.
   - Suppression de `const showBins = chartType === "histogram";`.
   - Suppression de `bins: 10` dans `defaultProps`.
2. `shell/src/builder/widgets/chartOption.ts`
   - Suppression du champ `bins?: number;` du type `ChartProps` — confirmé
     mort par recherche : aucune lecture dans `buildOption`, et après le
     point 1, plus aucune écriture nulle part (`grep -rn "props\.bins\|ChartProps"
     shell/src` ne retourne plus que la déclaration/usages de type, sans
     référence à `.bins`).
3. `shell/src/builder/widgets/chart.test.tsx`
   - Suppression du test `"PropsPanel shows a bin-count field for
     histogram"` qui exerçait le contrôle retiré (assertion sur
     `getByLabelText("Nombre de classes")`).
   - `chartOption.test.ts` ne référençait pas `bins` — rien à changer.
   - `DataSourcePanel.test.tsx` (contrôle « Nombre de classes (source …) »)
     non touché — hors périmètre, c'est le chemin correct et fonctionnel.

## Résultats de vérification

- Ciblé : `npx vitest run src/builder/widgets/chart.test.tsx
  src/builder/widgets/chartOption.test.ts` → **2 fichiers, 45 tests, tous
  verts**.
- Suite unitaire complète : `npm run test` → **101 fichiers, 752 tests, tous
  verts** (les logs d'erreur CEL affichés en stderr dans
  `exprBindings.test.ts` sont attendus — ce test vérifie justement la
  propagation d'erreur, pas un échec).
- Build : `npm run build` (`tsc --noEmit && vite build`) → **compile et
  bundle sans erreur** (seuls les avertissements pré-existants de taille de
  chunk, sans rapport avec ce changement).
- E2E complet : `VITE_AUTH_MODE=mock npm run e2e` → **69/69 specs vertes**,
  incluant les trois scénarios SP-14f (« sankey, treemap et sunburst render
  from a multi-field groupBy dataset », « a funnel click cross-filters… »,
  « a histogram renders binned data and never cross-filters on click ») qui
  passent sans le contrôle retiré, confirmant que le chemin `DataSourcePanel`
  → `/aggregate` reste seul et suffisant pour l'histogramme.

## Conclusion

Le contrôle dupliqué et non fonctionnel est retiré ; le `DataSourcePanel`
reste la source de vérité unique pour le nombre de classes de l'histogramme.
Aucune régression détectée sur les 12 tâches de la branche SP-14f — prête
pour merge après cette dernière correction.

---

# Correction issue de revue finale — SP-14h (branche `dev`, commit `eadbdd7`)

## Constat (revue whole-branch de SP-14h)

Le widget `map` du builder a reçu une symbologie pilotée par dataset
(encodages couleur/taille + légende, SP-14h) répartie sur 4 tâches, chacune
passée en revue individuellement. La revue finale de la branche entière a
trouvé un bug critique et deux points mineurs, corrigés ici avant merge.

## 1. Critique — domaines numériques couleur/taille non fonctionnels contre le vrai cœur

**Fichier : `shell/src/builder/widgets/mapWidget.tsx`, fonction `useNumericDomain`
(ligne 42, dans le bloc `query:`).**

`useNumericDomain` (utilisée à la fois pour l'encodage couleur numérique et
pour l'encodage taille) construisait sa requête sans `label` explicite :
`measures: [{ field, agg: "min" }, { field, agg: "max" }]`, puis lisait
`properties.min ?? 0` / `properties.max ?? 0`.

Or le cœur réel (`core/app/analytics/aggregate.py`, `_measure_label`) calcule
la clé de réponse d'une mesure **sans label explicite** comme
`f"{m.agg}_{m.field}"` (ex. `min_montant`, `max_montant`) — jamais `min`/`max`
tout court. Seule une mesure avec un `label` explicite dans la requête
utilise ce libellé littéral comme clé de réponse. Contre le vrai cœur,
`properties.min` et `properties.max` étaient donc toujours `undefined`,
retombaient sur `0` via `?? 0`, le domaine s'effondrait à `{min: 0, max: 0}`,
et le garde-fou `min === max` de `mapSymbology.ts` rendait alors une couleur
constante `#dbeafe` et un rayon constant de 4px partout — avec une légende
affichant « 0 – 0 ». Le bug était masqué par le test unitaire (faux
`queryDataSource`) et par le test E2E (route `/aggregate` mockée) qui
renvoyaient tous deux directement `{properties: {min, max}}` /
`{rows: [{min, max}]}` — la forme de clé pratique mais fausse.

**Fix appliqué** (identique au patron déjà correct dans
`shell/src/builder/widgets/sliderFilter.tsx` ligne 45) : ajout de
`label: "min"` sur la mesure `agg: "min"` et `label: "max"` sur la mesure
`agg: "max"`, dans `mapWidget.tsx` ligne 42 :

```ts
query: { measures: [{ field, agg: "min", label: "min" }, { field, agg: "max", label: "max" }] },
```

La lecture du résultat (`properties.min ?? 0` / `properties.max ?? 0`)
n'a pas changé — elle devient correcte une fois les labels ajoutés, le cœur
honorant désormais le label explicite comme clé de réponse. Aucune
modification dans `core/`.

## 2. Mineur — scénario E2E 25 ne testait pas ce qu'il prétendait

**Fichier : `shell/e2e/analytics-context.spec.ts`, test
`"a map with no encodings configured issues no domain query (SP-14h)"`
(ligne ~1811).**

Le test appelait `addFeaturesSource(page, "parcelles")` mais jamais
`promoteLastSource(page, ...)` ensuite. Sans promotion, aucun `datasetId`
n'est lié, donc les requêtes de domaine sont `enabled: false` de toute façon
— l'assertion `aggregateCalls === 0` passait pour la mauvaise raison
(absence de `datasetId`, pas absence d'encodings configurés). Les scénarios
22 à 24 du même fichier appellent bien `promoteLastSource(page, 1)` après
`addFeaturesSource`.

**Fix appliqué** : ajout de `await promoteLastSource(page, 1);` juste après
`await addFeaturesSource(page, "parcelles");`, en miroir des trois autres
scénarios — le test lie désormais un vrai `datasetId` et exerce
véritablement « pas d'encodings configurés → zéro requête de domaine ».

## 3. Mineur — branche `line-color` non couverte

**Fichier : `shell/src/builder/widgets/mapSymbology.ts`, fonction
`colorPaintProperty`** mappe `renderAs === "line"` vers `"line-color"`, mais
aucun test de `shell/src/builder/widgets/mapSymbology.test.ts` n'exerçait un
encodage couleur sur une géométrie ligne (seuls fill/polygone et
circle/point étaient couverts).

**Fix appliqué** : ajout d'un test dans `mapSymbology.test.ts` (juste avant
« cycles the categorical palette past 8 distinct values ») appelant
`buildMapPaint` avec `geometryKind: "line"` et un encodage couleur
catégoriel, en miroir exact du test fill-color existant, et vérifiant que
`paint["line-color"]` porte l'expression `match` attendue. Aucun changement
de code de production nécessaire — la branche `line-color` existait déjà.

## Résultats de vérification

- Ciblé unitaire : `npm run test -- mapWidget.test.tsx mapSymbology.test.ts`
  → **2 fichiers, 30 tests, tous verts** (15 + 15, incluant le nouveau test
  line-color).
- Ciblé E2E : `npm run e2e -- analytics-context.spec.ts -g "SP-14h"`
  → **4/4 scénarios verts**, en particulier le scénario 25 corrigé.
- Suite unitaire complète : `npm run test` → **104 fichiers, 793 tests, tous
  verts** (mêmes logs d'erreur CEL attendus en stderr, non liés à ce
  changement).
- Build : `npm run build` (`tsc --noEmit && vite build`) → **compile et
  bundle sans erreur** (seuls les avertissements pré-existants de taille de
  chunk et d'import dynamique/statique mixte de `MapView.tsx`, sans rapport
  avec ce changement).
- E2E complet : `npm run e2e` → **76/76 specs vertes**, incluant les 4
  scénarios SP-14h.

## Commit

`eadbdd7` — `fix(shell): label numeric domain measures, fix no-op E2E
scenario, cover line-color branch (SP-14h)`.

## Fichiers modifiés

- `shell/src/builder/widgets/mapWidget.tsx` (fix critique, ligne 42)
- `shell/e2e/analytics-context.spec.ts` (fix mineur 1, scénario 25)
- `shell/src/builder/widgets/mapSymbology.test.ts` (fix mineur 2, nouveau test)

## Conclusion

Les trois constats de la revue finale whole-branch de SP-14h sont corrigés :
le bug critique qui neutralisait la moitié de la fonctionnalité (couleur
numérique + taille proportionnelle) contre le vrai cœur est résolu, le test
E2E du scénario 25 isole désormais réellement la bonne cause, et la branche
`line-color` de `colorPaintProperty` est couverte. Suites unitaire et E2E
complètes vertes, build sans erreur — prêt pour merge.
