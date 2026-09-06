# SP-52 — App Builder : UX d'édition

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (via SP-42, référentiel 3)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-13, GAP-33,
GAP-51, GAP-54, GAP-66), `.superpowers/sdd/sp42-findings.jsonl`
(`F-shell-builder-01`, `F-shell-builder-02`, `F-shell-builder-03`,
`F-shell-builder-05`), `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
(chantier 4.24), `CLAUDE.md` §« Pièges récurrents ».

**Portée de ce document** : fermer 5 manques d'UX du builder d'App
(`shell/src/builder/`, `shell/src/pages/AppBuilderPage.tsx`), tous trouvés et
vérifiés par la revue SP-42, tous confirmés par lecture directe du code
pendant la rédaction de cette spec (2026-09-05, branche `dev`) — pas
seulement recopiés depuis le document de revue. Aucune dépendance sur
SP-43 : ces 5 manques ne touchent ni le mapping kind→privilège
(`core/app/roles/…`), ni les jobs procrastinate, et l'unique fichier qu'un
des GAP-source citait dans `itemClient.ts` a changé d'emplacement depuis
(cf. §2.3) — vérifié directement, pas supposé.

---

## 1. Pourquoi ces 5 manques, dans ce périmètre

La revue SP-42 (référentiel 3, cohérence interne) a trouvé 79 `GAP-nn`. Cinq
d'entre eux partagent un trait commun : ce sont des trous d'UX d'édition du
builder d'App, pas des manques de plateforme ou de sécurité — l'utilisateur
qui les rencontre est un auteur d'app en train d'éditer, pas un opérateur ni
un attaquant. Trois d'entre eux (GAP-66 a/b/c) recoupent trois trouvailles
`important` distinctes de la revue (`F-shell-builder-01/02/05`), toutes avec
un scénario d'échec concret et une preuve de reproduction ; deux (GAP-51,
GAP-54) sont des surfaces où une capacité existe côté modèle/rendu mais
jamais côté UI d'édition. Regroupés parce qu'ils touchent tous le même
triptyque de fichiers (`AppBuilderPage.tsx`, `GridCanvas.tsx`/`LayoutEditor.tsx`,
`DataSourcePanel.tsx`/`VariablesPanel.tsx`/`ActionsPanel.tsx`) et peuvent donc
partager un même plan sans dépendance externe.

Coût catalogué par la revue (`docs/revue/2026-09-04-analyse-gaps.md`, tableau
de décompte) : GAP-33 0.5j, GAP-54 1-2j, GAP-66 2-4j (le plus consistant des
trois, impact « Sérieux »), GAP-51 2j, GAP-13 2-3j — total ≈ 8-12j,
cohérent avec un seul plan à 5 tâches.

---

## 2. Analyse par manque, vérifiée sur le code réel

### 2.1 GAP-33 — code mort dans `grid.ts`

`shell/src/builder/grid.ts:7-24` déclare trois fonctions non
breakpoint-aware : `moveItem`, `resizeItem`, `styleFor`. Un grep exhaustif du
dépôt (`grep -rn "resizeItem\|\bmoveItem\b\|styleFor(" shell/src`) confirme :

- `resizeItem` n'a **aucun appelant** en dehors de son propre test
  (`grid.test.ts:14-17`) — aucun bouton de redimensionnement n'existe nulle
  part dans le builder (seuls des boutons de déplacement à 4 flèches
  existent, `GridCanvas.tsx:57-100`).
- `moveItem`/`styleFor` ont exactement un appelant chacun : leur propre test
  (`grid.test.ts:8-11,21-24`). Le code de production utilise partout
  `moveItemAt`/`styleForPos` (breakpoint-aware, `grid.ts:41-62`), consommés
  par `GridCanvas.tsx:4,31,38`, `LayoutEditor.tsx:5,55`, `AppRenderer.tsx:6,153`.

Ces trois fonctions datent d'avant l'introduction des breakpoints
(`BREAKPOINTS`/`posFor`, `grid.ts:26-39`) et ont été supersédées sans être
retirées. Retrait pur : aucun comportement de production ne les exerce.

### 2.2 GAP-54 — bandeau d'onglets vide en édition

`shell/src/builder/widgets/tabs.tsx:120-146` (`Component`) a deux branches :
en mode `edit` (lignes 133-145), il rend un bandeau de libellés d'onglets
(`<span>` non cliquables) suivi d'un `<div className="flex-1 bg-slate-50" />`
**vide** — le contenu réel de l'onglet actif n'est jamais rendu sur le
canevas d'édition lui-même. En mode `preview`/`runtime` (lignes 148-182), le
même widget rend des `<button>` d'onglets cliquables et un `GridCanvas`
complet avec le contenu de l'onglet actif.

Le contenu **est** éditable — mais uniquement depuis le panneau Propriétés
(`PropsPanel` du widget, lignes 23-118, qui embarque son propre
`LayoutEditor` à la ligne 111-116, un canevas miniature indépendant). Le
défaut n'est donc pas « le contenu des onglets est inéditable » (il l'est,
via un second canevas dans le panneau latéral) mais « le rendu du widget sur
le canevas principal en mode édition n'a aucun aperçu du contenu » — un
auteur qui n'ouvre pas le panneau Propriétés du widget Onglets voit un
rectangle vide sur le canevas, ce qui rend la mise en page ambiguë tant
qu'il n'a pas cliqué dessus.

### 2.3 GAP-51 — source « Statique » sans UI de saisie

`shell/src/builder/DataSourcePanel.tsx` : le sélecteur de type
(ligne 85-94) propose `"static"` (ligne 93). Le bloc conditionnel qui suit
ne couvre que `s.type === "features" || s.type === "statistics"`
(lignes 104, 128) — jamais `"static"`. Côté runtime, la résolution des
enregistrements d'une source statique lit `resolved.query.records`.

**Correction par rapport au GAP source** : `docs/revue/2026-09-04-analyse-gaps.md`
cite `shell/src/api/itemClient.ts:1442-1444` — ce chemin est **obsolète**.
Le dépôt a depuis subi une partie de la refactorisation SP-43 (barrel
`itemClient.ts` réduit à 53 lignes, logique éclatée en
`shell/src/api/domains/*.ts`, commits visibles sur `dev` :
« extrait le domaine datasets d'itemClient.ts », etc.). La lecture réelle
vit aujourd'hui à `shell/src/api/domains/datasets.ts:245` :

```ts
if (resolved.type === "static") {
  return (resolved.query.records as DataRecord[] | undefined) ?? [];
}
```

`DataRecord` (`shell/src/api/types.ts:778-782`) est
`{ id: string | number; properties: Record<string, unknown>; geometry?: unknown }`.
Sans UI, seul le copilote (`addDataSource`, `applyClientOp.ts:75-84`, qui ne
pose jamais `query.records` non plus) ou une édition de config hors produit
peut peupler une source statique utile — un auteur qui choisit « Statique »
dans le sélecteur obtient une source qui produit silencieusement 0
enregistrement, sans message d'erreur, pour tout widget qui s'y abonne.

### 2.4 GAP-66 — trois défauts d'édition distincts

**(a) Aucune UI manuelle de suppression d'un widget.**
`shell/src/builder/PropsPanel.tsx` ne rend que la condition d'affichage et
le `PropsPanel` propre au widget (aucun bouton Supprimer, lignes 29-53).
`shell/src/builder/GridCanvas.tsx:56-101` : le cluster de boutons du widget
sélectionné n'a que 4 flèches de déplacement, aucune suppression. Aucun
raccourci clavier (le seul `onKeyDown` du dépôt, `AppBuilderPage.tsx:99-114`,
ne gère que Ctrl/Cmd+Z et sa variante Maj). La seule opération
`removeWidget` de tout le shell est le tool copilote
(`applyClientOp.ts:68-73`), gated par `CORE_LLM_PROVIDER`/
`instance.copilotEnabled` — une capacité optionnelle, absente par défaut.
Sans copilote actif, le seul recours est Ctrl+Z immédiatement après l'ajout
(annule aussi tout autre changement du même burst d'undo, fenêtre de
coalescing 400 ms, SP-19) ou vivre indéfiniment avec le widget indésirable.

**(b) `setFilter` du copilote remplace au lieu de fusionner.**
`shell/src/builder/copilot/applyClientOp.ts:86-93` :

```ts
case "setFilter": {
  const dataSourceId = String(raw.args.dataSourceId ?? "");
  const query = (raw.args.query ?? {}) as Record<string, unknown>;
  return {
    ...config,
    dataSources: config.dataSources.map((s) => (s.id === dataSourceId ? { ...s, query } : s)),
  };
}
```

`query` (objet reçu de l'outil) **remplace** l'objet entier. L'édition
manuelle équivalente, `DataSourcePanel.tsx::patchQuery` (lignes 68-71),
fusionne toujours : `{ ...(s?.query ?? {}), ...changes }`. Scénario réel :
une source `statistics` déjà configurée avec
`{groupBy:"category", agg:"sum", field:"amount", bucket:"month"}` ; un
auteur demande au copilote de filtrer sur un statut ; le LLM appelle
`setFilter({dataSourceId, query:{status:"active"}})` — la description du
tool (« Modifie la requête (filtre) d'une source de données existante »,
`clientTools.ts:87`) suggère un ajout, pas un remplacement. Le widget perd
silencieusement son agrégation. Le test existant
(`applyClientOp.test.ts:101-114`) ne peut pas détecter la divergence : il
part d'une `query` déjà vide, où remplacement et fusion produisent le même
résultat.

**(c) Supprimer une variable ne nettoie pas les câblages `ActionsPanel`.**
`shell/src/builder/VariablesPanel.tsx:44-46` :
`remove(id)` → `onChange(variables.filter((v) => v.id !== id))` — ne touche
jamais `config.messages`. `ActionsPanel.tsx:22-25`
(`resolvesOnThisPage`) teste `variables.some(v => 'var:'+v.id === id)` :
une fois la variable supprimée, ce test devient faux, donc
`visibleMessages` (`ActionsPanel.tsx:51-54`) filtre le message hors
d'affichage — il devient invisible et impossible à retirer depuis l'UI,
mais reste indéfiniment dans `config.messages` (grossissement silencieux de
la config). Au runtime, `ActionBus.emit` ne crashe pas (no-op silencieux)
mais le comportement voulu par l'auteur ne se produit plus jamais, sans
qu'aucun message ne l'indique. Seul appelant de `VariablesPanel` dans tout
le shell : `AppBuilderPage.tsx:429` — la correction se fait entièrement au
niveau de son wrapper `setVariables` (ligne 277-278), sans élargir le
contrat de `VariablesPanel` lui-même.

### 2.5 GAP-13 — pas de widget de saisie lié directement à une variable

Chantier 4.24 du plan d'action (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md:434`) :
« les variables typées SP-5 ne se règlent que par une action composée ».
Vérifié sur `shell/src/builder/AppRenderer.tsx:56-64`
(`VariableBusBridge`) : une variable ne peut être modifiée qu'en émettant un
événement depuis un widget (ex. Filtre, Curseur) puis en câblant ce
signal, dans `ActionsPanel`, vers la cible `var:<id>.set`. C'est un montage
à deux niveaux (ajouter un widget émetteur, puis lui composer une action)
pour un besoin aussi simple que « saisir directement une valeur qui pilote
un indicateur » — aucun widget du catalogue ne lit *et* n'écrit directement
une variable dans son propre `Component`.

Mécanisme disponible pour construire la correction (déjà utilisé, non
exposé jusqu'ici à un widget applicatif) :
`shell/src/builder/VariablesContext.tsx` expose `useVariables()` (valeurs
courantes, indexées par **nom**) et `useSetVariable()` (écrivain, par nom)
— déjà réexportés publiquement par `shell/src/builder/sdk.ts:6` pour les
widgets WC/extension (SP-8). Un widget `Component` est toujours rendu à
l'intérieur du `VariablesProvider` posé par `AppRenderer.tsx:188` (y
compris en mode édition — le provider n'est pas conditionné par `mode`),
donc un widget peut appeler ces deux hooks directement, sans passer par
`ActionBus`. Ce qui manque : un moyen de résoudre, à partir d'un
identifiant de variable **stable** (`Variable.id`, pas son `name` mutable
— cf. §3.2 pour la justification), le nom et le type courants de la
variable, pour lire/écrire la bonne clé et choisir le bon contrôle natif.
`VariablesContext.tsx` n'expose aujourd'hui que la carte de valeurs, jamais
la liste `Variable[]` (id/name/type) elle-même une fois le provider monté.

---

## 3. Décisions de conception

### 3.1 GAP-54 : rendre le contenu réel visible en édition, pas juste le bandeau

Le canevas principal (`Component`, mode `edit`) doit rendre le même
`GridCanvas` que le mode `preview`/`runtime` (contenu de l'onglet actif),
mais **non interactif au niveau widget** (comme le fait déjà
`LayoutEditor`'s propre canevas imbriqué : `editable` contrôle seulement
les poignées de sélection/déplacement, pas le rendu). On garde le bandeau
d'onglets cliquable en édition (utile pour prévisualiser chaque onglet sans
rouvrir le panneau Propriétés), et on ajoute le `GridCanvas` du contenu de
l'onglet actif en dessous, avec `editable={false}` (cohérent avec
`modal.tsx`/`drawer.tsx`, qui rendent déjà leur propre canevas imbriqué en
lecture seule sur le canevas principal). L'édition du contenu reste au
panneau Propriétés (`LayoutEditor` existant, inchangé) — cette tâche ne
duplique pas la capacité d'édition, elle ajoute seulement l'aperçu qui
manque sur le canevas principal.

### 3.2 GAP-66(a) : bouton de suppression sur `GridCanvas`, prop requise partout

`GridCanvas` gagne un prop `onRemoveItem: (id: string) => void`
**obligatoire** (pas optionnel) : un bouton « Supprimer » rejoint le
cluster des 4 flèches sur le widget sélectionné. Rendre le prop obligatoire
(plutôt qu'optionnel avec un défaut silencieux) force le compilateur à
signaler tout site qui construit un `<GridCanvas>` sans le fournir —
cohérent avec la doctrine déjà exprimée par ce dépôt sur la classe de bug
« jumelle oubliée » (CLAUDE.md, piège n°4 et n°5) : mieux vaut une erreur de
compilation qu'un site qui redevient silencieusement sans suppression un
jour. Recherche préalable (`grep -rl "<GridCanvas" shell/src`) : 6 fichiers
construisent un `GridCanvas` — `AppRenderer.tsx`, `LayoutEditor.tsx`,
`widgets/tabs.tsx`, `widgets/modal.tsx`, `widgets/drawer.tsx`,
`GridCanvas.test.tsx` (2 sites) — tous à mettre à jour dans la même tâche
(les 3 widgets conteneurs passent `onRemoveItem={() => {}}` sur leur
canevas non-éditable imbriqué, exactement comme ils passent déjà
`onMoveItem={() => {}}`).

La suppression elle-même : `AppRenderer.tsx` gagne `handleRemove(id)`,
miroir de `handleMove` existant (filtre `activeLayout.items`, appelle
`onChange(setPageLayout(...))`). Pas de nettoyage de sélection explicite
nécessaire : `AppBuilderPage.tsx:144-148` réconcilie déjà `selectedId` dès
qu'il ne correspond plus à un item du layout actif (effet ajouté par
SP-19, finding M2 — même mécanisme, pas de duplication).

**Précision ajoutée après vérification croisée avec §2.4(c)/§3.4 (à ne pas
perdre en exécutant le plan) :** `applyClientOp.ts`'s cas `"removeWidget"`
existant (le copilote peut déjà retirer un widget aujourd'hui) ne purge pas
`config.messages` non plus — `ActionsPanel.resolvesOnThisPage()` masque déjà
silencieusement tout message dont `from`/`to` est un id de widget disparu,
exactement le même symptôme que §2.4(c) documente pour une variable
supprimée. Poser `handleRemove(id)` sans purger `config.messages` pour cet
`id` **réintroduirait sciemment, une case plus loin, le défaut que ce même
plan corrige pour les variables** (CLAUDE.md, piège n°4 : croisement entre
tâches d'un même plan, pas seulement entre plans). `handleRemove(id)` doit
donc filtrer `config.messages` sur l'id de widget retiré, par le même
mécanisme que §3.4 — voir le plan pour le point d'extraction commun
(fonction pure partagée entre les deux call sites plutôt que la logique de
filtrage écrite deux fois).

### 3.3 GAP-66(b) : fusionner `setFilter` comme `patchQuery`

`applyClientOp.ts::setFilter` passe de `query` (remplacement) à
`{ ...s.query, ...query }` (fusion), symétrique de
`DataSourcePanel::patchQuery`. Mettre à jour la description du tool
(`clientTools.ts:87`) pour ne plus suggérer une sémantique ambiguë :
« Fusionne des clés dans la requête d'une source de données existante (les
clés déjà présentes et non citées sont conservées) ».

### 3.4 GAP-66(c) : nettoyage au niveau du wrapper, pas du composant

`VariablesPanel` garde son contrat actuel (`onChange: (variables) => void`)
— aucun élargissement de sa signature. Le nettoyage se fait entièrement
dans `AppBuilderPage.tsx::setVariables`, en comparant l'ancien
`draft.variables` au nouveau tableau reçu pour déterminer les ids retirés,
puis en filtrant `config.messages` sur ces ids (`from`/`to` valant
`var:<id retiré>`). Un seul point de correction, aucune nouvelle prop à
faire remonter depuis `VariablesPanel`.

Puisque §3.2 étend le même besoin de purge à la suppression de widget (id
nu, pas préfixé `var:`), le filtrage lui-même (« retirer tout message dont
`from`/`to` figure dans un ensemble d'ids retirés ») est extrait en une
seule fonction pure partagée entre les deux call sites
(`AppBuilderPage.tsx::setVariables` et `AppRenderer.tsx::handleRemove`) —
pas dupliqué deux fois avec une légère variation, ce qui reproduirait
exactement la classe de défaut que `CLAUDE.md` §1.1/§1.3 documente déjà pour
d'autres règles écrites à plusieurs endroits. Nom et emplacement exacts
laissés au plan.

### 3.5 GAP-51 : éditeur JSON local pour `query.records`

Pas de constructeur de table ligne-par-ligne (coût disproportionné pour ce
scope) : un éditeur JSON texte local au bloc `s.type === "static"` de
`DataSourcePanel.tsx`, remonté seulement quand le JSON parse en un tableau
valide (état local non commis tant que le texte ne parse pas, erreur
affichée en `role="alert"`, patron déjà utilisé par `ActionsPanel`/
`PropsPanel` pour `visibleWhen`/`when`). Alimente `patchQuery(s.id, {
records: parsed })`, donc reste sur le même chemin d'écriture que tous les
autres champs du panneau — aucune nouvelle prop distincte.

### 3.6 GAP-13 : nouveau widget « Saisie », lié par `Variable.id` (pas par nom)

Nouveau widget builtin `variableInput` (« Saisie »),
`shell/src/builder/widgets/variableInput.tsx`. Décisions :

- **Référence par `id`, jamais par `name`.** Le nom d'une variable est
  renommable (`VariablesPanel::rename`) ; son `id` ne change jamais. Toute
  référence stockée dans la config doit survivre à un renommage — c'est
  déjà l'invariant respecté par `ActionMessage.to = "var:<id>"` et par
  `VariableBusBridge` (résolution fraîche du nom courant à chaque rendu,
  jamais un nom figé au moment du câblage). Le widget stocke donc
  `props.variableId` (un `Variable.id`), jamais un nom dénormalisé — un
  nom capturé au moment du choix deviendrait périmé exactement comme
  décrit en §2.4(c) pour un autre mécanisme.
- **Résolution du nom/type à l'affichage, pas au choix.** Pour lire/écrire
  la bonne clé de `useVariables()`/`useSetVariable()` (indexées par nom) et
  choisir le bon contrôle natif selon `VariableType`, il faut, à partir de
  l'id stocké, retrouver la définition `Variable` courante. Nouveau hook
  `useVariableDefs(): Variable[]` sur `VariablesContext.tsx` (le provider
  reçoit déjà `variables: Variable[]` en prop — il ne l'expose simplement
  pas encore lui-même après construction de la carte de valeurs), exporté
  aussi depuis `sdk.ts` pour rester cohérent avec les deux hooks déjà
  publics.
- **Types éditables** : `string` (texte), `number`, `bool` (case à cocher),
  `date` — un contrôle natif par type, même mapping que
  `VariablesPanel.tsx:85-118` (valeur initiale). `record`/`list` : pas de
  contrôle (ces types ne se règlent que par câblage d'action selon
  `VariablesPanel.tsx:119-121`, « Définie par câblage d'action » —
  cohérence délibérée, pas une lacune de cette tâche).
- **Sélecteur de variable dans le panneau Propriétés** : nécessite la liste
  `Variable[]` de l'app dans le `PropsPanel` du widget — aujourd'hui non
  transmise (`WidgetDefinition.PropsPanel` ne reçoit que
  `props/onChange/dataSources/theme`). Ajout d'un champ **optionnel**
  `variables?: Variable[]` sur ce type (registry.ts), threadé à travers
  `shell/src/builder/PropsPanel.tsx` (nouveau prop optionnel, défaut `[]`)
  depuis ses deux appelants (`AppBuilderPage.tsx`, `LayoutEditor.tsx`), puis
  re-threadé depuis les 3 widgets conteneurs (`tabs.tsx`/`modal.tsx`/
  `drawer.tsx`) vers leur `LayoutEditor` imbriqué — pour que le widget
  Saisie soit également configurable une fois posé **à l'intérieur** d'un
  onglet/modale/tiroir, pas seulement au premier niveau de page. Champ
  optionnel partout : aucun test existant construisant un `PropsPanel`
  minimal (`() => <div />`) ne casse.
- **Pas de nouveau type de `WidgetPropDescriptor`.** `variableId` reste
  typé `"string"` dans `configSchema` (comme les autres identifiants
  stockés en toutes lettres) — évite de toucher
  `widgetPropSchema.ts`/`coerceProp` (`applyClientOp.ts:18-22`), consommé
  par le copilote pour 22 widgets existants.
- **Pas de câblage `ActionBus`.** Le widget lit/écrit la variable
  directement via les hooks — un autre widget qui interpole `{{var:nom}}`
  (`widgets/index.tsx::interpolate`) ou une expression CEL référençant
  `vars.nom` voit la valeur à jour au prochain rendu, sans médiation par
  bus : c'est exactement le comportement demandé par le chantier 4.24
  (« Saisir un seuil… recalcule un indicateur lié par binding CEL »).

---

## 4. Ordre d'exécution et risques

Du moins au plus invasif — chaque tâche peut se merger indépendamment,
aucune dépendance dure entre elles (contrairement à SP-43, aucune tâche
n'a de filet transverse préalable).

1. **GAP-33** (retrait de code mort) — risque nul, aucun filet nouveau
   requis au-delà de « la suite passe toujours après suppression ».
2. **GAP-54** (aperçu du contenu des onglets en édition) — risque bas,
   un seul fichier de widget, changement additif (rendu), aucune donnée de
   config ne change de forme.
3. **GAP-51** (éditeur `query.records`) — risque bas, un seul fichier
   (`DataSourcePanel.tsx`), état local non commis tant qu'invalide.
4. **GAP-66** (a+b+c) — risque moyen : (a) touche 6 fichiers simultanément
   (prop obligatoire sur `GridCanvas`, cf. §3.2) — le risque principal est
   d'oublier un des 6 sites, mitigé par le prop obligatoire lui-même (le
   compilateur refuse de builder tant qu'un site manque) et par un grep de
   clôture ; (b) et (c) sont des correctifs ciblés d'un seul fichier
   chacun, risque bas.
5. **GAP-13** (widget Saisie) — le plus invasif : nouveau widget +
   threading d'un nouveau prop optionnel à travers 6 fichiers
   (`registry.ts`, `PropsPanel.tsx`, `LayoutEditor.tsx`, 3 widgets
   conteneurs) + nouveau hook sur `VariablesContext.tsx`. Risque mitigé par
   le caractère strictement optionnel du nouveau prop (aucun site existant
   ne casse à la compilation s'il est oublié — donc, contrairement à GAP-66(a),
   **le compilateur ne peut pas servir de filet de complétude ici** ; la
   mitigation est le grep de clôture explicite en fin de tâche, pas le
   typage).

---

## 5. Hors périmètre (explicite)

- **GAP-52** (5 jumelles manquantes widget carte vs éditeur de carte
  autonome) et **GAP-53** (outils de mesure/croquis jamais montés dans
  `MapEditorPage`) : voisins par thème (« builder — carte ») mais
  substantiellement plus gros (5-8j et 1j respectivement, surface carte,
  pas surface générique du builder) — un futur SP dédié à la carte, pas
  celui-ci.
- **GAP-34/35/36/37/38** (options d'impression non rendues, opacité
  raster non éditable, visualisations deck.gl inatteignables, script
  PMTiles orphelin, route de schéma dupliquée) : autres manques « Confort »
  du même référentiel 3, sans lien de fichier avec les 5 traités ici.
- **Vague 5 transverse** (i18n, a11y, `/v1/`, ADR — GAP-14) : ce plan
  n'introduit ni ne retire de littéral traduisible en dehors des libellés
  déjà en français des nouveaux contrôles (cohérent avec l'état actuel du
  dépôt : aucun widget existant n'est i18n-isé aujourd'hui).
- **Toute correction de fond du mécanisme d'undo/redo, de l'ActionBus ou du
  DataContext** : ce plan les consomme tels quels, ne les modifie pas.
- **Un constructeur de table ligne-par-ligne pour les enregistrements
  statiques** (alternative plus riche à l'éditeur JSON, §3.5) : hors
  scope, l'éditeur JSON suffit à débloquer la capacité manquante au
  coût catalogué (2j).
- **Étendre `variableId` à un nouveau type `WidgetPropDescriptor`
  dédié** (ex. `"variable"`, avec validation dans `coerceProp`) : non
  retenu, cf. §3.6 — `"string"` suffit sans toucher une surface partagée
  par 22 widgets.

---

## 6. Ce que ce document ne tranche pas

Le nom exact des classes CSS/`aria-label` des nouveaux contrôles (bouton
Supprimer de `GridCanvas`, contrôles natifs du widget Saisie) est laissé au
plan — cohérent avec les conventions déjà tranchées le 2026-09-01
(`h-9`, `Button`/`<button>` natif) que le plan doit suivre sans les
rouvrir.
