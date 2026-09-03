# LayersPanel : la colonne browse ne clippe plus son contenu (SP-37)

> Referme définitivement le lot « Carte » noté dans CLAUDE.md « À venir »
> depuis SP-28 (bug UI, pas une fonctionnalité manquante) — dernier
> mécanisme ouvert après la clôture du mécanisme (b) par SP-36. Spec
> brainstormée et validée avec Tanguy le 2026-09-04, à la suite de la
> clôture de SP-36.

## 1. Contexte & objectif

`shell/e2e/triptych-narrow.spec.ts` documente, depuis SP-33/SP-36, un
`wideBoundaryKnownIssue` sur l'écran Cartes à 900px (juste au-dessus du seuil
`NARROW_QUERY = "(max-width: 899px)"` posé par SP-33) : 1 offenseur mesuré,
`DIV.overflow-y-auto.border-r.border-rule` (scrollWidth 290 > clientWidth
249) — la colonne `browse` de `TriptychLayout.tsx` (`minmax(220px,280px)`,
rendue à ~249px dans cette bande) trop étroite pour le contenu de
`LayersPanel`. Le mécanisme (b), historiquement bundlé avec celui-ci (titre
de couche à largeur nulle), est fermé par SP-36 ; seul (a) restait à
diagnostiquer.

**Diagnostic fait par expérimentation directe dans le navigateur (pas
supposé), falsifié avant d'être retenu :**

Avec la fixture `map-1` (couche `vector` « Communes », popup+symbologie
actifs) rendue à 900px, l'inspection des largeurs en place de chaque
input/select sous le conteneur offenseur montre qu'ils sont TOUS étirés à
exactement 270px — pas leur propre plancher individuel (mesuré isolément
entre 182px et 200px chacun), mais un plancher commun imposé par un élément
tiers. En isolant chaque candidat, l'élément responsable est
`PopupEditor.tsx:160` :

```tsx
<div className="flex items-center gap-2">
  <input aria-label="Nom du champ à ajouter" className={`${inputCls} flex-1`} ... />
  <Button type="button" size="sm" variant="outline" onClick={addDraftField}>
    Ajouter le champ
  </Button>
</div>
```

Cette ligne est un flex-row **sans** `flex-wrap`. L'input `flex-1` n'annule
pas le plancher automatique (`min-width: auto`) : comme il n'est pas en
`overflow: hidden` (pas de `truncate`), son plancher automatique reste égal à
son min-content (~192px, mesuré). Additionné au bouton (~70-78px selon son
état) et au `gap-2` (8px), la ligne ne peut légalement descendre sous
~270px — plus large que les ~249px offerts par la colonne `browse` dans la
bande 900-959px. Comme cette ligne est la plus exigeante de tout le bloc
éditeur empilé en `flex-col`, sa largeur plancher se propage à TOUS ses
voisins (Champ titre, Champ couleur, Palette, Champ taille, Opacité), qui
héritent tous du même 270px bien qu'individuellement plus étroits.

**Vérifié par falsification en direct** : forcer `flex-wrap: wrap` sur cette
ligne via `page.evaluate` fait tomber l'overflow mesuré de scrollWidth 290 à
exactement 249 (= clientWidth, 0 offenseur) — confirmation sans ambiguïté du
mécanisme, avant d'écrire cette spec.

**Deuxième offenseur, trouvé et vérifié pendant l'investigation (pas la
même hypothèse que celle initialement pressentie — corrigé ici avant
d'écrire le plan) :** l'hypothèse de départ (`MapSymbologyEditor.tsx:575`,
la ligne `<span>{v}</span>` + `<button>` d'assignation d'icône par valeur de
domaine) a été **testée et infirmée** : ni `span` ni `button` n'y portent
`whitespace-nowrap`, donc leur texte enveloppe (`white-space: normal` par
défaut) au lieu de forcer une largeur — mesuré avec une valeur de domaine
longue et réaliste (« Zone industrielle secteur nord-ouest »), 0 offenseur
une fois le vrai offenseur ci-dessous corrigé.

Le vrai deuxième offenseur, **inconditionnel** (reproduit même avec des
valeurs de domaine courtes comme "A"/"B" — il suffit d'ouvrir la section
icônes) : `MapSymbologyEditor.tsx:695`, le sélecteur de fichier
d'upload d'icône personnalisée :

```tsx
<input
  aria-label="Ajouter une icône au tenant (PNG ou SVG)"
  type="file"
  accept="image/png,image/svg+xml"
  onChange={...}
/>
```

Cet `<input type="file">` ne porte **aucune classe de largeur** — ni
`inputCls`, ni `w-full`. Un input de type `file` a un plancher automatique
natif large (rendu du bouton « Parcourir »/« Choisir un fichier » +
« Aucun fichier choisi », mesuré ~300px+ selon le navigateur), et comme il
n'a pas de largeur spécifiée, la règle de plancher automatique
(`min-width: auto`) n'a rien à minorer : il s'affiche à son plein
min-content natif, qui dépasse le budget de ~249px de la colonne `browse`.
Mécanisme **différent** du premier offenseur (pas un flex-row sans
`flex-wrap` — un simple contrôle natif sans contrainte de largeur).

**Vérifié par falsification en direct** (avec des valeurs de domaine
courtes, pour isoler cet offenseur de tout effet de texte long) :
- Masquer cet `<input>` (`display:none` sur son `<label>` parent) fait
  tomber les offenseurs mesurés à 0 — confirme qu'il est bien la seule
  cause dans cet état.
- `className="w-full"` seul (sans `min-w-0`, testé et insuffisant seul)
  fait tomber l'overflow à 0 offenseurs, y compris avec la valeur de
  domaine longue ci-dessus — confirme le remède.

## 2. Périmètre

**Dans le périmètre :**

1. `shell/src/map/PopupEditor.tsx:160` — ajouter `flex-wrap` à la ligne
   d'ajout de champ (correctif confirmé, §1).
2. `shell/src/map/MapSymbologyEditor.tsx:695` — ajouter `className="w-full"`
   au `<input type="file">` d'upload d'icône personnalisée (correctif
   confirmé, §1). Mécanisme et remède différents du fix #1 : pas un
   `flex-wrap`, un contrôle natif sans classe de largeur.
3. `shell/src/map/LayerPicker.tsx:143` et `:173` — ajouter `border-rule` aux
   deux `border-t` non tokenisés (dette notée SP-30c, explicitement exclue du
   périmètre de SP-34 comme « chantier séparé », reprise ici à la demande de
   Tanguy). `className` seul, aucun changement de comportement.
4. `shell/e2e/triptych-narrow.spec.ts` — une fois §2.1 et §2.2 corrigés :
   retirer `wideBoundaryKnownIssue` de l'écran Cartes, le test à
   900px rejoint les 7 autres écrans (plus de `test.skip()`). Mettre à jour
   le commentaire du bloc `SCREENS` (lignes ~179-197) et le commentaire
   d'en-tête (~142-151) en conséquence.
5. CLAUDE.md — clore entièrement le lot « Carte » dans `### À venir` (plus
   aucun sous-mécanisme ouvert), entrée `### Livré` datée SP-37.

**Hors périmètre, explicitement :**

- Toucher `TriptychLayout.tsx` (largeur des colonnes) ou
  `useNarrowViewport.ts` (seuil `NARROW_QUERY`) — le contenu tient dans le
  plancher actuel de la colonne `browse` une fois corrigé ; élargir la
  colonne pour toute la famille de 9 écrans n'est pas nécessaire et
  réintroduirait la question du seuil partagé (SP-33).
- Toute restructuration de `PopupEditor.tsx`/`MapSymbologyEditor.tsx`/
  `FieldClassificationPicker.tsx` au-delà des classes `flex-wrap`/`w-full`/
  `border-rule` ci-dessus.
- Audit exhaustif de tout pattern similaire du dépôt en dehors des fichiers
  consommés par la colonne `browse` de l'écran Cartes — seuls les deux
  offenseurs identifiés en §1 sont dans le périmètre.

## 3. Mécanisme

**Fix #1** : identique à SP-36, ajout de `flex-wrap` au conteneur flex-row
identifié, sans restructuration. Avec `flex-wrap`, le bouton (« Ajouter le
champ ») est rejeté sur sa propre ligne dès que l'input voisin ne peut plus
tenir à côté à sa largeur normale — l'input, seul élément restant sur la
première ligne, récupère l'espace disponible sans plancher partagé avec le
bouton. Aucun changement visuel aux largeurs où tout tenait déjà côte à côte
(≥270px de colonne disponible) : le retour à la ligne ne se déclenche que
sous ce seuil.

```diff
- <div className="flex items-center gap-2">
+ <div className="flex flex-wrap items-center gap-2">
    <input aria-label="Nom du champ à ajouter" className={`${inputCls} flex-1`} ... />
    <Button ...>Ajouter le champ</Button>
  </div>
```

**Fix #2** : mécanisme différent, pas de `flex-wrap` — `w-full` donne à
l'`<input type="file">` une largeur spécifiée à 100 % de son conteneur
(`<label>`, `flex flex-col gap-1`, déjà `align-items: stretch` par défaut).
Une fois la largeur spécifiée, la règle CSS de plancher automatique
(`min-width: auto` sur un flex item) plafonne le plancher au *minimum entre*
cette largeur spécifiée et le min-content natif du contrôle — au lieu
d'utiliser le min-content natif seul (très large pour un `<input
type="file">`) quand aucune largeur n'est spécifiée. `min-w-0` seul, sans
`w-full`, a été testé et est **insuffisant** (l'overflow persiste) : c'est
la largeur spécifiée qui fait le travail ici, pas l'annulation du plancher.

```diff
  <input
    aria-label="Ajouter une icône au tenant (PNG ou SVG)"
    type="file"
+   className="w-full"
    accept="image/png,image/svg+xml"
    onChange={...}
  />
```

Pour `LayerPicker.tsx`, changement sans rapport mécaniquement (dette de
token de couleur, pas de layout) :

```diff
- <div className="border-t pt-2">
+ <div className="border-t border-rule pt-2">
```

## 4. Tests

1. **Falsification obligatoire** (piège n°10) pour chaque fix : retirer
   temporairement la classe ajoutée, confirmer sur un run Playwright réel
   que la mesure `expectNoClippedContent` (`triptych-narrow.spec.ts`)
   échoue bien avec un offenseur non-vide, remettre. Les deux fixes sont
   déjà pré-vérifiés manuellement pendant le brainstorming/l'écriture de
   cette spec (fix #1 : `flex-wrap` retiré → 1 offenseur ; fix #2 : `w-full`
   retiré → 1 offenseur, même sans texte long) — à rejouer formellement
   dans le plan, pas à supposer acquis.
2. Le fix #2 nécessite d'ouvrir réellement la section « Ajouter des
   icônes » de `MapSymbologyEditor.tsx` pour que l'`<input type="file">`
   soit monté — la couche « Communes » de la fixture `map-1` n'a pas
   d'encodage icône par défaut, il faut interagir avec l'UI (bouton
   « Ajouter des icônes », remplir « Champ icône », cliquer « Recalculer
   les valeurs ») avant de mesurer. Le champ agrégat (`POST
   /collections/communes/aggregate`) n'est stubbé nulle part dans
   `mocks.ts` pour la collection `communes` — mocker la route directement
   dans le test (mêmes formes `categoryKey`/`rows` que
   `map-symbology.spec.ts:30-37`, mode `groupBy` plutôt que `measures`, cf.
   `itemClient.test.ts:1443-1466` pour le format exact de réponse attendu).
3. `triptych-narrow.spec.ts` : re-mesurer l'écran Cartes à 900px après les
   deux correctifs — 0 offenseur attendu, retirer `wideBoundaryKnownIssue`
   et son commentaire.
4. Pas d'assertion Vitest/jsdom sur les classes CSS ajoutées (jsdom ne fait
   pas de layout — même doctrine que SP-36). Vérifier simplement, par
   lecture directe, qu'aucun test existant de `PopupEditor.test.tsx`/
   `MapSymbologyEditor.test.tsx`/`LayerPicker.test.tsx` n'assertait une
   classe exacte qui casserait avec ces ajouts.
5. `npm run test` et `npm run e2e` verts, couverture shell non régressée
   (seuil 88, mesurée après nettoyage de `dist/`/`dist-export/`).
6. Régénération OpenAPI/types TS : **non nécessaire** — aucune route ni
   modèle cœur ne change (CSS + tests shell/E2E purs).

## 5. Critères de sortie

1. Écran Cartes à 900px : 0 offenseur mesuré par
   `expectNoClippedContent` ; `test.skip()` retiré de
   `triptych-narrow.spec.ts` pour cet écran.
2. Les deux `border-t` de `LayerPicker.tsx` portent `border-rule`.
3. CLAUDE.md : le lot « Carte » est intégralement retiré de `### À venir`
   (plus aucun sous-mécanisme ouvert), avec une entrée `### Livré` datée
   SP-37.
4. Suites shell (`npm run test`) et E2E (`npm run e2e`) vertes, sans
   régression, couverture non régressée.

## 6. Risques et limites connues

- **Correction de l'hypothèse initiale de brainstorming** : cette spec a été
  révisée une fois, avant l'écriture du plan, après que l'hypothèse de
  départ pour le second offenseur (ligne `span`+`button` d'assignation
  d'icône, `MapSymbologyEditor.tsx:575`) s'est révélée fausse à la
  vérification (le texte y enveloppe, ne force pas de largeur). Le second
  offenseur réel (`<input type="file">` sans largeur, ligne 695) a été
  trouvé et vérifié à la place, par la même méthode de falsification — pas
  un changement de périmètre, une correction de diagnostic.
- **Portée limitée aux trois fichiers identifiés** (`PopupEditor.tsx`,
  `MapSymbologyEditor.tsx`, `LayerPicker.tsx`) : un pattern similaire
  ailleurs dans le shell (hors périmètre de cette spec) resterait non
  détecté par ce travail.
