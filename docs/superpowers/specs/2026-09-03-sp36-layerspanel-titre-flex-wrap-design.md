# LayersPanel : le titre de couche ne s'effondre plus à largeur 0 (SP-36)

> Referme le lot « Carte » noté dans CLAUDE.md « À venir » depuis SP-28 (bug
> UI, pas une fonctionnalité manquante). Spec brainstormée et validée avec
> Tanguy le 2026-09-03, à la suite de la clôture de SP-35.

## 1. Contexte & objectif

Dans `LayersPanel.tsx` (`shell/src/map/LayersPanel.tsx:164`), chaque couche
est un `<li>` avec `className="flex items-center gap-2 text-sm"` — une ligne
flex sans retour à la ligne. Elle contient, dans l'ordre : le `<span
className="flex-1 truncate">` du titre, quatre boutons (↑/↓/œil/croix), et,
pour les couches `kind === "vector"` ou `"feature"`, un `<div
className="basis-full pl-2">` qui héberge `LayerPopupEditor` +
`LayerSymbologyEditor`.

`basis-full` (flex-basis: 100%) n'a d'effet de retour à la ligne que si le
parent porte `flex-wrap` — ce qui n'est pas le cas ici. Sans lui, l'algorithme
de mise en page à une seule ligne doit faire tenir tous les éléments sur la
même ligne : le bloc éditeur (base = 100 % du conteneur) absorbe l'essentiel
du rétrécissement, mais son propre plancher automatique (`min-width: auto`,
non nul car son contenu n'est pas en `overflow: hidden`) l'empêche de
descendre à 0. Le `<span>` du titre, seul élément dont le plancher automatique
est ramené à 0 par `overflow: hidden` (hérité de `truncate`), est le seul
candidat qui *peut* légalement atteindre 0 — et c'est lui que le navigateur
écrase. Résultat : pour toute couche `vector`/`feature`, le titre est présent
dans le DOM (donc lisible par un lecteur d'écran/testable par rôle) mais
rendu à 0px de large, invisible à l'écran.

Trouvé par SP-28/Task 4, contourné dans son propre test E2E (assertion sur le
bouton « Retirer … », qui porte le même titre en `aria-label` mais n'est pas
soumis à cet écrasement), jamais corrigé — noté CLAUDE.md comme hors
périmètre de chaque plan SP-30/SP-33 qui l'a croisé depuis.

## 2. Périmètre

**Dans le périmètre :**

1. `shell/src/map/LayersPanel.tsx:164` — ajouter `flex-wrap` à la classe du
   `<li>` (§3).
2. `shell/e2e/map-feature-layer-symbology.spec.ts` — remplacer le
   contournement (assertion sur le bouton « Retirer … ») par une assertion
   directe sur la visibilité du titre ; retirer le commentaire qui documente
   le bug, devenu faux.
3. `shell/e2e/map-symbology.spec.ts` — ajouter une assertion équivalente sur
   le titre de la couche vectorielle « Communes », jamais testée jusqu'ici
   (le commentaire de map-feature-layer-symbology.spec.ts le signale
   explicitement comme cas partagé non couvert).
4. `shell/e2e/triptych-narrow.spec.ts` (SP-33) — l'écran Cartes y est
   documenté avec un `test.skip()` explicite pour deux mécanismes distincts
   sur `LayersPanel`, dont celui-ci (mécanisme (b), cf. spec SP-33 §2). Ce
   plan vérifie si son sous-mécanisme disparaît de la mesure et met à jour le
   commentaire/skip en conséquence — sans toucher au mécanisme (a) (colonne
   `browse` trop étroite pour le contenu de `LayersPanel`, distinct, hors
   périmètre).
5. CLAUDE.md — clore le lot « Carte » dans `### À venir` une fois vérifié.

**Hors périmètre, explicitement :**

- Le mécanisme (a) de l'écran Cartes noté par SP-30l/SP-33 (colonne `browse`
  plafonnée à 280px, trop étroite pour `LayersPanel` à toute largeur) —
  défaut distinct, indépendant de celui-ci.
- Toute refonte de `LayersPanel`, de sa structure de boutons, ou de son
  panneau d'édition inline.
- Le `border-t` non tokenisé de `LayerPicker.tsx` (dette séparée, notée
  SP-30c, non reprise ici).

## 3. Mécanisme

```diff
- <li key={layer.id} className="flex items-center gap-2 text-sm">
+ <li key={layer.id} className="flex flex-wrap items-center gap-2 text-sm">
```

Avec `flex-wrap`, la mise en page se fait par « collecte en lignes » : le
navigateur place les éléments un par un sur la ligne courante tant que leur
taille hypothétique (leur `flex-basis`, avant toute étape de
grow/shrink) tient dans la largeur restante ; dès qu'un élément ne tient
plus, il démarre une nouvelle ligne. Le bloc éditeur (`basis-full`, base =
100 % du conteneur) ne peut par construction jamais tenir à côté du titre et
des quatre boutons — il est donc **toujours** rejeté sur sa propre ligne,
quelle que soit la largeur du conteneur (étroite ou large). Sur la première
ligne (titre + boutons), sans ce compétiteur géant, le titre (`flex-1`)
récupère normalement l'espace restant après les boutons ; s'il n'y a pas
assez de place, il rétrécit comme prévu par `truncate` (ellipse), mais ne
tombe plus à 0 par construction — il n'y a plus qu'un seul candidat aussi
extrême que lui à absorber le rétrécissement.

C'est le comportement que `basis-full` visait déjà à produire : une seule
classe manquante sur le parent, pas une restructuration de la hiérarchie
DOM. Indépendant de la largeur de colonne `browse` (fonctionne identiquement
à 220px comme à 320px, y compris dans la bande 900-959px notée par SP-33 où
cette colonne rend plus étroite que son ancien maximum fixe).

Aucun changement de comportement pour les couches `raster`/`tiles3d` (sans
bloc `basis-full`, donc jamais concernées par ce mécanisme) ni pour l'état
« Aucune couche » (`<li>` indépendant, sans classe flex).

## 4. Tests

1. **`map-feature-layer-symbology.spec.ts`** : remplacer
   `expect(page.getByRole("button", { name: "Retirer Points d'intérêt" })).toBeVisible()`
   par une assertion directe sur le titre affiché dans la ligne de couche
   (locator à choisir pour éviter toute ambiguïté avec d'autres occurrences
   du même texte à l'écran — ex. scoper au `<li>`/`role="listitem"` de
   `LayersPanel`). Retirer le commentaire qui documente le bug (lignes ~54-64
   actuelles).
2. **`map-symbology.spec.ts`** : après l'ajout de la couche « Communes »
   (ligne ~50), ajouter une assertion équivalente sur la visibilité de son
   titre dans `LayersPanel` — même précaution de locator (le bouton source
   « Communes » du `LayerPicker` porte un texte qui peut coïncider).
3. **Falsification obligatoire** (piège n°10) : avant de considérer le
   correctif acquis, retirer temporairement `flex-wrap` et confirmer que les
   deux assertions ci-dessus échouent bien sur un run Playwright réel (pas
   supposé) — puis le remettre.
4. **`triptych-narrow.spec.ts`** : mesurer l'écran Cartes après correctif ;
   si le sous-mécanisme (b) disparaît de la liste des offenseurs mesurés,
   mettre à jour le commentaire/skip pour ne plus le mentionner (le
   mécanisme (a), lui, reste).
5. `LayersPanel.test.tsx` (Vitest/jsdom) : pas de layout réel calculé en
   jsdom, donc pas d'assertion possible sur la largeur — vérifier simplement
   qu'aucun test existant n'assertait une classe exacte sur le `<li>` qui
   casserait avec l'ajout de `flex-wrap` (à confirmer par lecture directe
   avant d'écrire le plan, pas supposé).
6. Régénération OpenAPI/types TS : **non nécessaire** — aucune route ni
   modèle cœur ne change (changement CSS + tests shell/E2E purs).

## 5. Critères de sortie

1. Le titre d'une couche `vector`/`feature` est visible à l'écran
   immédiatement après ajout, sans dépendre du bouton « Retirer … » comme
   preuve indirecte — vérifié par les deux specs E2E mises à jour.
2. `npm run test` et `npm run e2e` verts, couverture shell non régressée
   (seuil 88, mesuré après nettoyage de `dist/`/`dist-export/`).
3. Le sous-mécanisme (b) de l'écran Cartes n'apparaît plus dans les
   offenseurs mesurés par `triptych-narrow.spec.ts` (le mécanisme (a) reste,
   documenté comme avant).
4. CLAUDE.md : le lot « Carte » est retiré de `### À venir`, avec une entrée
   `### Livré` datée.

## 6. Risques et limites connues

- **Portée du fix limitée au mécanisme documenté** : si un autre écrasement
  de layout existe ailleurs dans `LayersPanel` (non trouvé à ce jour), il
  n'est pas dans le périmètre de cette spec.
- **Le mécanisme (a) de l'écran Cartes (colonne `browse` trop étroite)
  demeure** après ce plan — attendu, tracé séparément, ne pas le confondre
  avec un correctif incomplet.
