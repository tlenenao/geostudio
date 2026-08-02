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
