# TriptychLayout : fin de l'affamement de la colonne centrale (SP-33)

> Reliquat de SP-30, noté dans CLAUDE.md « À venir » (entrée SP-30) : le
> critère de sortie §7 « aucun écran ne clippe au-dessus du seuil relevé »
> n'était en réalité vérifié que sur 2 des 8 écrans de référence
> (Tâches, Paramètres — les deux seuls qui ne rendent aucune grille
> `TriptychLayout`). SP-30 n'est pas redéclaré clos tant que ce chantier
> n'est pas livré. Spec brainstormée et validée avec Tanguy le 2026-09-02.

## 1. Contexte & objectif

`TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`) rend, au-dessus
du seuil `useNarrowViewport()`, une grille CSS à trois colonnes :

```
grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]
```

Mesuré par la revue transverse de sortie de SP-30 (round 2, 2026-09-02,
`shell/e2e/triptych-narrow.spec.ts`, avec un filet de test lui-même corrigé
pour mesurer l'état stabilisé plutôt que le premier échantillon — cf.
CLAUDE.md entrée SP-30l) : cette grille clippe du contenu réel, invisible et
inatteignable, sur **6 des 8 écrans de référence** dès que le viewport dépasse
légèrement le seuil actuel (641px, mesuré) — Catalogue (5 offenseurs), Cartes
(3, dont un seul relève de ce mécanisme — cf. §2), Apps & sites (2),
Analytique (1), Administration (1), Automatisation (2).

**Mécanisme exact, vérifié contre la spec CSS réelle (piège n°3) :**

1. L'algorithme de dimensionnement de CSS Grid maximise les pistes non
   flexibles (les deux colonnes latérales, `minmax(220px,280px)` et
   `minmax(260px,320px)`) en leur distribuant tout l'espace disponible
   **avant** de donner quoi que ce soit à la piste flexible (`1fr`, la
   colonne centrale `work`) — c'est l'ordre imposé par la spec, pas un bug
   d'implémentation d'un moteur particulier.
2. Le `<div>` de la colonne centrale porte `overflow-hidden`. Par la
   spécification CSS de dimensionnement (`min-width: auto` sur un enfant de
   grid/flex), la taille minimale *automatique* d'un élément est remplacée
   par `0` dès que sa valeur de `overflow` n'est pas `visible`. Une piste
   `1fr` seule (sans `minmax`) a pour fonction de dimensionnement minimale
   `auto` — donc, combinée au point 1, la colonne centrale n'a **aucun
   plancher réel** : elle reçoit ce qui reste après que les deux colonnes
   latérales ont atteint leur maximum combiné (280+320=600px), soit 41px à
   641px de large, quel que soit l'écran.

C'est un défaut de `TriptychLayout` lui-même, partagé par les neuf familles
qui l'utilisent (SP-30a→j) — pas un défaut d'une page en particulier, et pas
quelque chose qu'un réglage de seuil seul peut corriger (CLAUDE.md l'avait
déjà noté : « un vrai chantier de layout … pas un simple ajustement de
seuil »).

## 2. Périmètre

**Dans le périmètre :**

1. Donner à la colonne centrale un plancher CSS réel et explicite
   (`minmax(Npx, 1fr)` plutôt que `1fr` nu) — cf. §3.1.
2. Relever le seuil partagé `useNarrowViewport`/`NARROW_QUERY` pour que la
   grille à trois colonnes ne soit jamais rendue en dessous du point où les
   trois planchers (browse, centre, inspect) peuvent coexister sans
   dépassement — cf. §3.2. Ce seuil est **partagé** avec `AppLayout.tsx`
   (bascule `DomainBar`/`BottomNav`) : le relever change les deux bascules
   ensemble, comme aujourd'hui.
3. Vérification empirique, écran par écran, contre le filet déjà correct de
   SP-30l (`triptych-narrow.spec.ts`) — cf. §4.
4. Mise à jour de ce même fichier de test : les six `wideBoundaryKnownIssue`
   documentant le défaut corrigé par ce plan (Catalogue, Apps & sites,
   Analytique, Administration, Automatisation, et le sous-mécanisme (c) de
   Cartes — cf. point suivant) sont levés ; le test « bande 391-seuil : mode
   étroit » est réécrit à une largeur qui reste dans la nouvelle bande.

**Hors périmètre, explicitement — deux défauts distincts déjà tracés
ailleurs, sur l'écran Cartes :**

- Le mécanisme (a) noté par SP-30l sur l'écran Cartes : la colonne `browse`
  elle-même, plafonnée à 280px par son propre `minmax`, est trop étroite
  pour le contenu de `LayersPanel` — persiste identiquement à *toute*
  largeur sondée (900/1400/1920px), donc indépendant de l'affamement de la
  colonne centrale que ce plan corrige. Reste tracé CLAUDE.md/SP-30l.
- Le mécanisme (b) : le `<span>` de titre d'une couche `vector`/`feature`
  dans `LayersPanel.tsx` à largeur de layout nulle (`flex-1 truncate` +
  sibling `basis-full`) — déjà tracé CLAUDE.md, lot « Carte », depuis SP-28.
  Ce plan ne le corrige pas ; `skipClipCheckForTabs: ["Couches"]` reste en
  place dans le filet de test pour cette raison précise, pas pour masquer
  un effet de ce chantier.
- Toute refonte des minimums propres à `LayersPanel` ou de son contenu.
- Un troisième mode de rendu (« desktop compact ») pour la bande
  intermédiaire : tranché en session — la bande entre l'ancien seuil et le
  nouveau retombe dans le mode mobile existant (onglets + `BottomNav`),
  pas dans un nouveau mode à concevoir.

## 3. Mécanisme

### 3.1 — Plancher explicite sur la colonne centrale

```diff
- <div className="grid flex-1 grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)] overflow-hidden">
+ <div className="grid flex-1 grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)] overflow-hidden">
```

`minmax(360px, 1fr)` fixe la fonction de dimensionnement *minimale* de la
piste à une longueur fixe (360px) plutôt qu'à `auto` : sa taille de base
s'initialise directement à 360px, **avant** l'étape de maximisation des
pistes non flexibles, et cette initialisation n'est **pas** soumise à la
règle de mise à zéro du minimum automatique (cette règle ne s'applique
qu'à la fonction `auto`, jamais à une longueur explicite) — donc
`overflow-hidden` sur le `<div>` reste inoffensif, aucun autre changement
n'est nécessaire sur cette classe.

Aux largeurs déjà correctes aujourd'hui (desktop large), le comportement ne
change pas : la colonne centrale continue d'absorber tout l'espace restant
au-delà de son plancher, exactement comme avec `1fr` nu.

`360px` est une **hypothèse de départ**, pas une valeur mesurée contre le
contenu réel des six écrans concernés — cf. §4 pour la façon dont le plan
doit la confirmer ou l'ajuster.

### 3.2 — Seuil partagé relevé

```diff
- export const NARROW_QUERY = "(max-width: 640px)";
+ export const NARROW_QUERY = "(max-width: 899px)";
```

Le calcul : `browse_min (220) + center_min (360) + inspect_min (260) = 840px`
— en dessous, aucune disposition à trois colonnes respectant les trois
planchers ne peut tenir sans dépassement (les colonnes déborderaient du
conteneur `overflow-hidden`, ce qui **couperait une colonne entière** plutôt
que de simplement réduire la colonne centrale — un échec pire que le défaut
actuel, cf. §5). `899px` donne une marge de sécurité (~60px) au-delà de ce
minimum théorique, en plus de la marge propre à chaque écran une fois
vérifiée en §4.

**Conséquence assumée, déjà actée en session** : une fenêtre desktop en
demi-écran dans la bande ~641-899px, qui tente aujourd'hui (et échoue) à
afficher trois colonnes, bascule désormais proprement sur le mode mobile
existant (onglets + `BottomNav`), plutôt que de continuer à tenter — et
rater — trois colonnes. C'est un changement de comportement visible pour
cette bande de largeur précise, pour la persona A1 (équipe SIG/analystes,
souvent en double écran) — accepté comme le prix d'un rendu qui ne clippe
jamais plutôt que d'un rendu qui tente plus large et échoue silencieusement.

Le commentaire au-dessus de `NARROW_QUERY` (déjà dense, cf. fichier actuel)
est réécrit pour documenter ce nouveau calcul et pointer vers cette spec,
en gardant la trace de l'historique du seuil précédent (390px → 640px →
899px) plutôt que de l'effacer — même discipline que le commentaire actuel.

## 4. Tests

Le filet `shell/e2e/triptych-narrow.spec.ts` est déjà correct (SP-30l round
2 : mesure l'état stabilisé par sondage répété, pas le premier échantillon
— vérifié par falsification à l'époque). Ce plan ne le réécrit pas, il le
**fait réagir** au nouveau seuil et lève les `test.skip()` devenus caducs :

1. **Groupe « juste au-dessus du seuil relevé »** : le point de vérification
   passe de 641px à **900px** (nouveau seuil + 1px), même rôle que
   `WIDE_BOUNDARY_WIDTH` aujourd'hui. Pour les six écrans concernés par ce
   plan, `wideBoundaryKnownIssue` est retiré et le test doit passer sans
   `test.skip()` — **falsifié avant d'être considéré corrigé** : vérifier
   qu'il échoue encore si on ne change que le seuil sans le plancher (ou
   l'inverse), pour confirmer que c'est bien la combinaison des deux qui
   règle le défaut, pas l'un des deux seul par accident de largeur d'écran.
2. **Écran Cartes** : seul le sous-mécanisme (c) (la vraie famine de colonne
   centrale, cf. commentaire existant dans le fichier de test) doit
   disparaître. Les mécanismes (a) et (b) restent chacun leur propre
   `wideBoundaryKnownIssue`/`skipClipCheckForTabs`, mis à jour pour ne plus
   mentionner (c) parmi les offenseurs attendus.
3. **Groupe 390px (mode mobile)** : inchangé, ne doit pas régresser —
   c'est le mode qui absorbe maintenant une bande de largeur plus grande.
4. **Test de non-régression du seuil** (actuellement à 500px, à l'intérieur
   de l'ancienne bande 391-640) : la largeur de sonde doit rester à
   l'intérieur de la **nouvelle** bande interdite à la grille (391-899) tout
   en restant significative — proposer **700px** (solidement à l'intérieur,
   loin des deux bords) plutôt que de garder 500px sans le justifier à
   nouveau.
5. Si `360px`/`899px` ne suffisent pas à faire disparaître un offenseur sur
   l'un des six écrans une fois mesuré en vrai (pas supposé), le plan ajuste
   `center_min` et/ou le seuil et documente la valeur finale retenue et
   pourquoi — pas de "ça devrait marcher" sans le passage réel du test.
6. Vitest (`TriptychLayout.test.tsx`, `useNarrowViewport.test.ts`,
   `AppLayout.test.tsx`) : les valeurs de seuil en dur dans ces fichiers
   (s'il y en a) sont mises à jour en cohérence — vérifier par grep avant
   d'écrire le plan d'implémentation, pas supposé depuis cette spec.
7. Régénération OpenAPI/types TS : **non nécessaire** — aucune route ni
   modèle cœur ne change (changement CSS + une constante shell pur).

## 5. Critères de sortie

1. Les huit écrans de référence (`triptych-narrow.spec.ts`) passent sans
   `test.skip()` au nouveau point de vérification « juste au-dessus du
   seuil », **sauf** les deux mécanismes explicitement hors périmètre sur
   l'écran Cartes (§2), qui restent documentés, pas silencieusement
   disparus.
2. `npm run test` et `npm run e2e` verts, couverture shell non régressée
   (seuil 88, mesuré après nettoyage de `dist/`/`dist-export/`).
3. Aucune capture/vérification visuelle du desktop large (≥ 1280px, cible
   bureau prioritaire A10) ne change de comportement — seule la bande
   641-899px et le mécanisme interne de la colonne centrale changent.
4. CLAUDE.md mis à jour : l'entrée SP-30 dans `### À venir` est retirée (ou
   son bloqueur clos) une fois ce plan livré et vérifié, et SP-30 peut être
   redéclaré clos.

## 6. Risques et limites connues

- **`minmax(360px, 1fr)` sans le relèvement de seuil serait pire que le
  statu quo** : si le conteneur est plus étroit que la somme des trois
  planchers, les pistes débordent du `<div>` grid parent (lui-même
  `overflow-hidden`) — une colonne entière (probablement `inspect`, la
  dernière) se retrouverait coupée à la limite du conteneur plutôt que
  simplement réduite. C'est pourquoi les deux changements (§3.1 et §3.2)
  sont livrés **ensemble**, jamais l'un sans l'autre.
- **360px reste une hypothèse non mesurée** contre le contenu réel des six
  écrans (tableaux denses, éditeur SQL, canevas DAG…) — §4 point 5 est le
  garde-fou : le plan ajuste si le test réel dit non, il ne suppose pas que
  l'hypothèse de cette spec est juste.
- **Le point de vérification (900px) suffit à couvrir toute largeur
  supérieure, par construction** : une fois les trois planchers respectés au
  seuil, plus d'espace ne peut qu'agrandir les trois colonnes au-delà de
  leurs planchers, jamais les resserrer davantage. Aucune borne haute
  séparée n'est donc nécessaire — le seul point qui mérite un test explicite
  est le plus étroit possible en mode grille, pas les plus larges.
- **La bande 641-899px perd le rendu triptyque complet** pour la persona A1
  en fenêtre desktop partagée — arbitrage produit explicite (§3.2), pas un
  effet de bord non discuté.
