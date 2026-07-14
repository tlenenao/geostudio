# Storytelling — mode narratif sur `PageManager` : design

> Quick win indépendant (arbitrages **A36/A37**, tranchés le 2026-07-14 —
> [gap analysis dataviz/analytics](../../vision/geostudio-dataviz-analytics-gap-analysis.md)
> §7.5/§9.2, validés par Tanguy). Livrable dès maintenant, en parallèle de
> SP-9 : ne dépend d'aucun autre chantier (ni SP-11, ni SP-14, ni SP-16).

## 1. Contexte et objectif

**Constat.** Le builder a déjà toutes les briques d'une expérience narrative :
pages (`PageManager`), variables/bindings CEL, `ActionBus` (dont
`map.flyTo`, câblé depuis SP-0d3). Il leur manque un **gabarit** — sans lui,
chaque auteur qui voudrait une « story cartographique » (texte + carte qui
vole d'une emprise à l'autre au fil du récit) devrait bricoler des pages et
des boutons à la main, sans progression ni immersion.

**Objectif.** Un auteur active un mode « story » sur une app existante,
associe à chaque page une action de navigation carte (`map.flyTo` vers une
emprise), et obtient une expérience de narration scrollée/séquencée — sans
nouveau widget, sans nouveau backend, sans code.

**Décision actée (A36)** : mode de layout sur `PageManager` existant, pas un
nouveau widget conteneur — toute app peut devenir une story a posteriori et
hérite gratuitement du thème/des variables de l'app parente.

## 2. Périmètre

**Dans le périmètre v1 :**
- `AppConfig.navigationMode?: "tabs" | "story"` (défaut `"tabs"`,
  rétrocompatible — les configs `version: 1` sans ce champ se comportent
  exactement comme aujourd'hui).
- En mode `"story"` : `PageManager` remplace le menu d'onglets par une barre
  de progression (chapitre *n*/*N*) + boutons **Précédent**/**Suivant** ;
  layout immersif (grille sans bordures visibles en preview/runtime, contours
  normaux en edit).
- Chaque page gagne un champ optionnel `onEnter?: ActionMessage[]` — réutilise
  **exactement** le mécanisme `ActionBus.emit` existant (mêmes types de
  messages, même validation de condition `when`, cf. SP-5b) — déclenché quand
  la page devient active en mode story.
- Nouveau panneau « Navigation » dans le builder (à côté de Pages/Variables/
  Thème existants) : bascule `navigationMode`, édition des messages `onEnter`
  par page (réutilise l'UI de liste de messages déjà écrite pour
  `ActionsPanel`).
- Nouveau gabarit de galerie **« Story cartographique »** (`templates.ts`) :
  3 pages pré-câblées, chacune avec un `onEnter: [{ type: "map.flyTo", ... }]`
  vers une emprise différente.

**Hors périmètre v1 (différé, pas oublié) :**
- Avancement auto au scroll (IntersectionObserver) — v1 se limite à des
  boutons Précédent/Suivant explicites ; le scroll-driven est une extension
  naturelle sans changement de modèle, à faire si la demande réelle l'exige.
- États analytiques figés par chapitre (bookmarks) — dépend des datasets/
  contexte global de SP-14, non disponible aujourd'hui.
- Nouveau widget conteneur dédié — explicitement refusé (A36).

## 3. Architecture (shell uniquement, aucun changement cœur)

- **`api/types.ts`** : `AppConfig.navigationMode?: "tabs" | "story"` ;
  `PageConfig.onEnter?: ActionMessage[]`. Champs optionnels : round-trip
  Pydantic côté cœur (`configs`) déjà tolérant aux champs JSON additionnels
  tant qu'ils sont déclarés côté schéma — **vérifier en ouverture de tâche**
  que `core/app/configs/schemas.py` les déclare, sur le modèle exact du bug
  latent corrigé en SP-5b (`visibleWhen`/`Message.when` silencieusement
  supprimés par un round-trip `model_validate`/`model_dump` s'ils ne sont pas
  déclarés) — **ne pas répéter cette régression**.
- **`PageManager.tsx`** : rendu conditionnel sur `navigationMode`. Mode
  `"story"` : barre de progression + navigation précédent/suivant au lieu du
  menu d'onglets actuel ; un `useEffect` sur le changement de page active émet
  les messages `onEnter` de la nouvelle page active vers `ActionBus`, exactement
  comme les émetteurs déjà câblés (`Table.itemSelected`, `Filter.changed`).
- **`configExpressionErrors.ts`** : étendu pour valider les conditions `when`
  des messages `onEnter` (même garde que pour les actions existantes) —
  bouton **Enregistrer** désactivé si une expression `onEnter` est invalide.
- **`ActionsPanel.tsx`** : réutilisé tel quel pour éditer la liste `onEnter`
  d'une page (même composant, nouvel appelant) — pas de nouveau composant de
  liste de messages à écrire.
- **`templates.ts`** : nouvelle entrée galerie « Story cartographique ».

## 4. Flux et gestion d'erreurs

- **Activation** : dans le panneau Navigation, bascule `tabs`→`story` ;
  aperçu immédiat en mode preview (barre de progression visible).
- **Édition d'un chapitre** : sélectionner une page → panneau Navigation →
  ajouter un message `onEnter` (ex. `map.flyTo` avec bounds) → même UX que
  l'édition d'actions existante.
- **Runtime** : à l'entrée dans l'app, la première page est active, ses
  `onEnter` s'exécutent une fois ; navigation Suivant/Précédent change la page
  active et déclenche les `onEnter` de la nouvelle page (pas de re-déclenchement
  au retour arrière si la config ne le souhaite pas — **à trancher en plan** :
  comportement par défaut proposé = ré-émission à chaque entrée, y compris en
  arrière, cohérent avec `map.flyTo` qui est idempotent).
- **Erreurs** : une condition `onEnter.when` invalide bloque l'enregistrement
  (message inline), jamais une exécution silencieusement dégradée.

## 5. Tests

**Shell (Vitest) :**
- `PageManager` en mode `story` : barre de progression, boutons précédent/
  suivant, absence du menu d'onglets ; navigation avant/arrière ; page
  courante correcte après plusieurs clics.
- `onEnter` émis vers `ActionBus` à l'entrée d'une page en mode story ; **non**
  émis en mode `tabs` (pas de régression du comportement actuel).
- Validation d'une condition `onEnter.when` invalide (`configExpressionErrors`).
- Rétrocompatibilité : une config sans `navigationMode` se comporte comme
  avant (test de non-régression explicite).

**E2E (nouvelle spec `storytelling.spec.ts`) :**
1. Créer une app, activer le mode story, ajouter 3 pages avec un `onEnter:
   map.flyTo` distinct chacune.
2. En runtime : vérifier que la carte se positionne sur l'emprise de la
   première page à l'entrée, que Suivant/Précédent naviguent correctement et
   déplacent la carte à chaque changement de chapitre.
3. Le template « Story cartographique » est proposé dans la galerie et
   produit une app fonctionnelle dès sa création.

## 6. Critères d'acceptation

- Une app existante (sans `navigationMode`) s'ouvre et se comporte
  **exactement** comme avant — E2E existantes vertes, aucune régression.
- Un auteur active le mode story sur une app, sans code, définit une emprise
  cible par chapitre, prévisualise puis publie une story cartographique où la
  carte vole d'un chapitre à l'autre.
- Le template « Story cartographique » est disponible dans la galerie et
  produit, dès sa création, une story fonctionnelle à éditer.

## 7. Risques

Risque quasi nul — c'est un quick win assumé : aucune nouvelle brique cœur,
aucun nouveau widget, réutilisation stricte de mécanismes déjà testés
(`ActionBus`, `ActionsPanel`, validation d'expressions). Le seul point de
vigilance documenté est la déclaration des nouveaux champs de config côté
schéma Pydantic du cœur (cf. §3), pour ne pas reproduire la régression
silencieuse déjà rencontrée et corrigée en SP-5b.
