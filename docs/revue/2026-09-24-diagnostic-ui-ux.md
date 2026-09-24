# Diagnostic UI/UX GeoStudio — Phase 3 (consolidation)

> Clôt le workflow décrit par
> `docs/superpowers/specs/2026-09-24-diagnostic-ui-ux-design.md` (variante 13
> agents : Phase 0 cartographie, Phase 1 audit statique × 5 domaines,
> Phase 1b parcours dynamiques Playwright, Phase 2 vérification
> adversariale des `ko`/`partiel` d'impact ≥ 6, Phase 3 = ce document).
> Lecture seule sur `shell/`, `core/`, `docs/revue/2026-09-04-backlog.md` et
> `docs/revue/2026-09-04-analyse-gaps.md` — aucun de ces fichiers n'a été
> modifié. Les entrées `REV-nnn` listées en fin de document sont des
> **propositions**, à valider par Tanguy avant intégration au backlog réel.

Entrées reçues : 88 points de grille (IDs 1-88 + IDs `nouveau-*` de
Phase 1b) répartis sur 5 domaines, avec verdict Phase 2 sur les 22 `ko`/
`partiel` d'impact ≥ 6 (tous **confirmés**, aucun réfuté ni reclassé). Après
fusion des constats de même cause racine (explicitement signalée par de
nombreuses notes d'auditeur — « à fusionner en Phase 3 », « doublon »,
« corrélat direct »), le diagnostic retient **58 défauts consolidés**
(codes `D01`-`D58`) et **~26 points positifs** confirmés (non détaillés en
table, cf. §5).

## 1. Tableau consolidé des défauts

Colonnes : code consolidé · domaine(s) · IDs fusionnés · statut · preuve
(résumée) · niveau de preuve · persona · impact · effort · lien existant ·
verdict Phase 2 · vague.

### Vague A — bloquants et découvrabilité (rôle × flag, tâche impossible)

| Code | Domaine | IDs | Statut | Preuve (résumé) | Niveau | Persona | Impact | Effort | Lien existant | Verdict P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | nav-inert | 1, nouveau-10, nouveau-11 | ko | `/bookmarks` et `/analytics/sql` fonctionnels (confirmé par deep-link Phase 1b, 0 violation axe) mais aucun lien de nav (DomainBar/BottomNav/SettingsNav/ItemActions) n'y mène | exécuté/capturé | Créateur, Analyste | 6 | M | **GAP-80, GAP-81** | confirmé |
| D02 | nav-inert | 4 | ko | `ItemDetailPage.tsx:116` exclut `"site"` de la liste des kinds éditables → bouton « Ouvrir l'éditeur » désactivé pour un item Site ouvert via `/items/:pk`, alors que la même carte l'ouvre correctement depuis le catalogue (dispatchers `onOpenEditor`/`useOpenItem` divergents) | lu | Créateur | 4 | S (1 ligne) | nouveau | — |
| D03 | nav-inert | 5, 62 | ko | `NewItemButton` gate app/map/dataset sur privilège mais PAS pipeline/visual-query (seulement `etlEnabled`) → un rôle sans `automation.manage` sur instance ETL activée remplit tout le formulaire pour échouer sur un 403 serveur final ; `quotasEnabled` câblé jusqu'au profil sans jamais être lu par aucun écran | lu | Analyste, Lecteur (rôle sur mesure) | 4 | S | nouveau | — |
| D09 | nav-inert | nouveau-2 (pipelines-new-stuck) | ko | Deep-link `/pipelines/new` avec `CORE_ETL_ENABLED=false` reste bloqué sur « Chargement… » indéfiniment au lieu du message « Non activé sur cette instance » (contraste avec `/admin/infrastructure`) | capturé | Créateur | 2 | S | nouveau | — |
| D18 | map-dual-host | 79 | ko | Aucun mécanisme d'auto-cadrage sur l'emprise des données : toute carte/widget s'ouvre centré France/zoom 5 quel que soit l'emplacement réel des données (aucun bouton « recentrer ») — **impact le plus élevé du diagnostic** | lu | Créateur | **9** | M | nouveau (mise en garde : ne pas confondre avec l'emprise de recherche spatiale SP-55, fonctionnalité disjointe) | **confirmé** |
| D13 | map-dual-host | 17 | partiel | Le widget carte d'App/Dashboard ne peut structurellement porter qu'une seule couche `kind:"feature"` dérivée de sa DataSource — jamais raster/vector-direct/deck.gl/tiles3d, pourtant livrés côté éditeur autonome (GAP-36, GAP-52) | lu | Créateur | 6 | L | nouveau (angle mort du suivi D2/SP-24, question produit à trancher d'abord) | **confirmé** |
| D05 | nav-inert | 10 | ko | Un secret créé via `SecretParamSelect` ne peut jamais être supprimé (ni UI ni MCP) — seul un appel HTTP DELETE direct hors produit, gênant pour révoquer un identifiant compromis | lu | Administrateur, Créateur | 2 | M | nouveau | — |
| D58 | journeys-power | 59 | ko | `useOpenItem` route toujours un pipeline vers l'éditeur DAG complet ; le wizard no-code (Filtrer→Joindre→Résumer) sait pourtant relire un pipeline existant (`unrecognizedShape`) — porte à sens unique dès la 2e édition | lu | Créateur, Analyste | 4 | M | nouveau | — |

### Vague B — états système et cohérence

| Code | Domaine | IDs | Statut | Preuve (résumé) | Niveau | Persona | Impact | Effort | Lien existant | Verdict P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| D19 | states-feedback, journeys-power | 20, 64, 47, nouveau-1(states), nouveau-15(journeys) | ko | Catalogue (écran le plus fréquenté) et listes structurantes : état vide en texte brut (`catalog.empty`), sans `ui/kit/EmptyState` ni CTA — **le constat convergent le plus cité du diagnostic (5 IDs indépendants)** | capturé | Créateur | 6 | S | nouveau | **confirmé** |
| D20 | states-feedback | 21 | ko | 4 listes admin (Harvest/Roles/Users/Collections) n'affichent **rien du tout** à vide — pire que D19, aucun moyen de distinguer chargement en cours et absence de données | lu | Administrateur | 4 | S | nouveau | — |
| D26 | states-feedback, forms-a11y-design | 31, 65, 39 | ko | Suppression de pièce jointe sans AUCUNE confirmation (`form.tsx`, clic direct = suppression immédiate) ; suppression d'enregistrement via `window.confirm` générique sans nom d'objet ; 3 sites `window.confirm` non stylé vs 7 sites `ConfirmDialog` kit ailleurs | capturé | Créateur | 6 | S | nouveau | **confirmé** |
| D28 | states-feedback | 33, 67 | ko | `Toast` monté globalement (`App.tsx`) mais jamais câblé à un flux réel (1 seul rendu, galerie interne) ; les 5 éditeurs principaux (Carte/Dataset/App/Pipeline/Rapport) ne montrent jamais de confirmation de succès à l'enregistrement (`isSuccess` jamais lu) | capturé | Créateur | 6 | S | nouveau | **confirmé** |
| D21 | states-feedback | 22, 23 | ko | `Spinner`/`Skeleton` du kit sans consommateur de production ; 37 sites en `<p>{t("common.loading")}</p>` texte brut | capturé | Lecteur | 6 | M | nouveau | **confirmé** |
| D22 | states-feedback | 24, 26, nouveau-3 | ko/partiel | Client HTTP générique (`api/base.ts`) jette `Request failed: ${status}` sans lire le corps `problem+json` (RFC 7807, SP-26) ; un 429 tombe dans le même message générique qu'un 500/403 (confirmé par capture) | capturé | Créateur, Analyste | 4 | M | nouveau | — |
| D29 | states-feedback | 66 | ko | Aucune garde de navigation sur brouillon non sauvegardé — contrainte structurelle : le shell utilise `BrowserRouter`, pas un data router, donc `useBlocker` (react-router v6) est indisponible sans migration de routeur | lu | Créateur | 6 | M | nouveau | **confirmé** |
| D31 | states-feedback | nouveau-4 | ko | `new QueryClient()` sans configuration, aucun `AbortSignal`/timeout sur les fetch : un cœur qui ne répond jamais (vs répond en erreur) laisse l'utilisateur sur « Chargement… » indéfiniment, sans retry ni message | exécuté | Lecteur | 6 | M | nouveau | **confirmé** |
| D33 | forms-a11y-design, states-feedback | 35, 43 | partiel | 0 occurrence de `aria-describedby`/`aria-invalid` sur les champs (kit `Field.tsx` + formulaire généré) — l'erreur est annoncée (`role="alert"`) mais indécouvrable en revisitant le champ au clavier ; aucun résumé/ancrage vers la première erreur | lu | Créateur, Lecteur | 6 | M | nouveau | **confirmé** |
| D06 | nav-inert | 60 | ko | Aucun des 4 builders (App/Pipeline/Carte/SQL Lab) ne restaure son état de navigation interne (onglet actif, nœud sélectionné, requête) depuis l'URL — contraste avec `ItemDetailPage` qui le fait pour son panneau | lu | Créateur, Analyste | 4 | L | nouveau | — |
| D30 | states-feedback | 68 | partiel | Pas de message unifié « connexion au cœur perdue » ni de détection hors-ligne — chaque requête affiche sa propre erreur locale, pouvant produire un mélange de contenu chargé/fragments d'erreur | lu | Lecteur | 4 | M | nouveau | — |
| D24 | states-feedback | 28 | ko | Aucun job long (ingestion, pipeline, export) n'affiche de pourcentage d'avancement ni de bouton d'annulation | lu | Créateur | 2 | M | nouveau | — |
| D25 | states-feedback | 29 | partiel | Vocabulaire de statut de job non harmonisé entre surfaces (`STATUS_LABEL` vs `Phase` locales, non comparé terme à terme) | à confirmer | Créateur | 2 | M | nouveau | — |
| D57 | journeys-power | 58 | partiel | Export Bookmark/App : aucun texte « Export en cours… » pendant le sondage (jusqu'à 5 min), seul le bouton devient inerte | lu | Créateur | 4 | S | nouveau | — |
| D17 | map-dual-host | 78 | ko | Pas d'indicateur de troncature au plafond MVT 5000 lignes (SP-24), pas de spinner/squelette sur tuiles/couches lourdes | lu | Analyste | 4 | M | nouveau (plafond livré/documenté, message associé absent) | — |
| D14 | map-dual-host | 19 | ko | `printLayout.showLegend` fonctionne à l'export d'une carte autonome mais est silencieusement ignoré à l'export d'une App/Dashboard (`AppRuntimePage` ne mirroite que title/cartouche) | lu | Créateur | 2 | S | nouveau (même classe que REV-128) | — |
| D40 | forms-a11y-design | 69, nouveau-2(forms) | ko | `DataTable` du kit sans consommateur de production ; 4 implémentations de table divergentes (5 pages admin ad hoc, aperçu pipeline, widget table) ; tri au clic uniquement, non accessible au clavier sur 2 d'entre elles | lu | Administrateur, Analyste | 6 | L | nouveau | **confirmé** |
| D44 | forms-a11y-design, journeys-power | 84, nouveau-1(forms), 53 | ko | `AppRuntimePage` (page la plus visitée) + 3 pages publiques (`Site`/`PublicItem`/`Dataset`) restent sur `ui/*` legacy non tokenisé ; 187 classes Tailwind de couleur brute hors `shell/src/map/*` (déjà tokenisé par SP-34) dans ~40 fichiers ; 2 littéraux français non traduits sur pages publiques (angle mort REV-177) | exécuté (script i18n réel) | Lecteur, Visiteur anonyme | 6 | L | REV-177 (partiel), nouveau pour le reste | **confirmé** |

### Vague C — polish, a11y AA, perf perçue, onboarding

| Code | Domaine | IDs | Statut | Preuve (résumé) | Niveau | Persona | Impact | Effort | Lien existant | Verdict P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| D32 | forms-a11y-design | 34 | ko | Formulaire généré depuis le schéma de collection (surface la plus utilisée) : `aria-label` écrase le suffixe visuel « * » de requis, aucun `required`/`aria-required` posé — un lecteur d'écran ne sait jamais qu'un champ est obligatoire | lu | Créateur, Lecteur (App) | 6 | S | nouveau | **confirmé** |
| D41 | forms-a11y-design | 71 | ko | `MapPopup` porte `role="dialog"` sans gestion Échap ni prise de focus à l'ouverture | à confirmer | Lecteur, Analyste | 6 | S | nouveau | **confirmé** |
| D48 | forms-a11y-design | nouveau-5 | ko | Fermeture d'un dialogue (« Nouvel élément ») via Échap : le focus ne revient pas sur le bouton déclencheur — violation WAI-ARIA Dialog non détectée par axe-core, trouvée par test clavier manuel | capturé | — | 2 | S | nouveau | — |
| D34 | forms-a11y-design | 36 | ko | Réordonnancement de champs (`FieldOverrides`) drag-only sans fallback clavier — même classe que REV-060 (déjà fermée sur `PipelinePalette`) jamais reportée ici | lu | Créateur | 4 | S | nouveau | — |
| D07 | nav-inert | 61 | ko | Aucune recherche globale / palette de commandes (`Kbd` du kit sans consommateur) malgré un commentaire de `capabilities.ts` qui en présuppose une | lu | Créateur, Analyste, Administrateur | 2 | L | nouveau | — |
| D08 | nav-inert, states-feedback | nouveau-2(quota, nav-inert), nouveau-2(quota, states-feedback) | ko | Quotas de stockage (SP-58, GAP-11/73) livrés côté cœur mais **aucune UI** n'affiche jamais usage/plafond/approche du plafond à un Administrateur — premier contact = échec d'upload sans contexte | lu | Administrateur | 2 | L | GAP-11, GAP-73 (mécanisme fermé ; angle « invisibilité UI » nouveau) | — |
| D10 | nav-inert | 63 | partiel | 4 pages centrales (Catalogue, fiche item, éditeur dataset, runtime app) mélangent primitives `ui/*` legacy et `ui/kit/*` dans le même écran ; 4 clés i18n orphelines (0,3 %) | lu | Créateur, Lecteur | 3 | M | nouveau | — |
| D04 | nav-inert | 9 | partiel | `AlertRule` : pas de bouton « exécuter maintenant » côté UI, seul le copilote/l'API MCP peut forcer une évaluation | lu | Créateur | 1 | M | nouveau | — |
| D11 | map-dual-host | 13 | partiel | Centre/zoom du widget carte figés (France/zoom 5), non éditables nulle part dans le PropsPanel — contraste avec l'éditeur autonome qui cadre et persiste en direct | lu | Créateur | 6 | S | nouveau | **confirmé** *(classée en Vague A/gain rapide dans le classement §2, regroupée ici par thème cartographie)* |
| D12 | map-dual-host | 15, 16 | partiel | `availableFields=[]` codé en dur sur symbologie ET popup du widget carte — aucune suggestion de champ, saisie à la main obligatoire (un seul correctif ferme les deux, patron `sampleField` déjà utilisé pour GAP-52) | lu | Créateur | 3 | S | nouveau | — |
| D15 | map-dual-host | 75 | partiel | Aucune légende de symbologie dans l'éditeur de carte standalone (seulement dans le widget) — asymétrie assumée à SP-25, reste un vrai manque UX | lu | Créateur | 4 | M | résidu connu (suivi M2, SP-25) | — |
| D16 | map-dual-host | 77 | partiel | Interaction tactile/mobile non vérifiée dynamiquement (pinch/pan/popup au tap/taille de cible barre de mesure) — présomption favorable en lecture de code seule | à confirmer | Visiteur anonyme | 4 | S | nouveau | — |
| D35 | forms-a11y-design | 38, 70 | partiel | Erreurs CEL affichées correctement positionnées mais en texte brut du parseur ; dates/nombres via `<input>` natif sans formatage `fr-FR` forcé | à confirmer | Créateur | 2 | M | nouveau | — |
| D36 | forms-a11y-design | 41 | partiel | Upload de pièce jointe : un seul booléen `uploading` global, aucune progression par fichier | à confirmer | Créateur | 2 | M | nouveau | — |
| D38 | forms-a11y-design | 44 | partiel | ~15 occurrences de `<label>` non associés par `htmlFor`/`id` (doublon `aria-label` à la place) | lu | Créateur, Lecteur | 2 | M | nouveau | — |
| D39 | forms-a11y-design | 45 | partiel | Formulaire de création de secret (name/type/location/key/value/token/…) sans hint/exemple sur les champs sensibles | lu | Administrateur, Créateur | 2 | M | nouveau | — |
| D42 | forms-a11y-design | 72 | ko | Aucun `prefers-reduced-motion` (faible surface d'animation, 4 fichiers) ; tailles de cible du kit conformes | lu | — | 1 | S | nouveau | — |
| D43 | forms-a11y-design | 73 | partiel | Couverture axe-core réelle = 17 tests (pas 9 comme documenté par REV-178/CLAUDE.md) ; `AppRuntimePage` (page la plus visitée) toujours absente de l'échantillon | lu | — | 2 | M | **REV-178** (chiffre à corriger) | — |
| D45 | forms-a11y-design | 85 | partiel | Résidu connu confirmé sans nouvelle découverte (REV-088 aria-expanded, dette `h-8` déjà reconnue par les Conventions tranchées 2026-09-01) | lu | — | 2 | — | **REV-088** | — |
| D46 | forms-a11y-design | 86 | ko | 15 occurrences `text-[Npx]` arbitraires (9-10px, sous `text-xs`=12px) dans 13 fichiers, hors échelle de tokens typographiques | lu | — | 2 | M | nouveau | — |
| D47 | forms-a11y-design | 88 | partiel | Deux styles « primaires » (bleu plein) coexistent dans la barre d'outils `AppBuilderPage` en mode Édition (toggle de mode + bouton Enregistrer) | lu | — | 3 | S | nouveau | — |
| D49 | journeys-power | 48 | ko | Aucun lien d'aide/documentation contextuelle nulle part dans le shell, malgré des concepts denses (CEL, AppConfig, pipeline no-code, SQL) | lu | Créateur, Analyste | 2 | M | nouveau | — |
| D50 | journeys-power | 49, 74 | ko | `t()` sans pluralisation → ≥4 clés grammaticalement fausses (« 1 éléments ») ; 2 conventions de contournement non tranchées ; `PublicItemPage` sans `useDocumentMeta` contrairement à `SitePublicPage` | lu | Lecteur, Visiteur anonyme | 3 | M | nouveau | — |
| D51 | journeys-power | 50 | ko | SQL Lab affiche l'exception backend brute (probable texte technique anglais), sans positionnement ligne/colonne, contraste avec les autres panneaux qui gardent un message générique localisé | lu | Analyste | 4 | S | nouveau | — |
| D52 | journeys-power | 51 | ko | Aucun bouton « Copier » nulle part dans le shell (`navigator.clipboard`/`clipboard.writeText` : 0 occurrence) — lien de partage et snippet embed à sélectionner à la main | lu | Créateur, Intégrateur | 3 | S | nouveau | — |
| D54 | journeys-power | 54 | ko | Éditeur SQL Lab = `<textarea>` brut sans coloration syntaxique ni autocomplétion table/colonne | lu | Analyste | 2 | L | GAP-81 (adjacent, découvrabilité déjà ouverte ; ceci porte sur l'ergonomie une fois la page atteinte) | — |
| D55 | journeys-power | 55 | partiel | `readOnly` du canevas pipeline ne désactive pas Annuler/Rétablir/Ajout de zone/suppression/connexion de nœud — résidu consigné en clôture du chantier Pipeline builder UX (2026-09-19), non repris en REV numérotée | lu | Lecteur (démo/partage) | 2 | S | résidu connu (pipeline builder UX) | — |
| D56 | journeys-power | 57 | partiel | Historique de conversation du copilote App Builder/Pipeline non persisté (contraste SQL Lab) ; opérations (`addWidget`/`setFilter`…) appliquées sans aperçu préalable — mitigé par Undo/Redo (SP-19), mais hors doctrine GAP-17 | lu | Créateur | 4 | M | nouveau (distinct de GAP-17, qui couvre SQL Lab/requête visuelle) | — |
| D27 | states-feedback | 32 | partiel | Aucune annulation-après-coup nulle part — pattern acceptable en soi (confirmer-avant suffit), noté comme constat neutre, pas un défaut à corriger en priorité | lu | Créateur | 2 | — | nouveau | — |
| D23 | states-feedback | 25 | ko | Résidu connu re-confirmé (404 trompeur au lieu de 403 sur `GET /collections/{id}/...` OGC features pour un porteur du seul privilège `admin.collections.manage`) | lu | Administrateur | 2 | S | **GAP-82, REV-185** | — |
| D53 | journeys-power | 52 | partiel | Résidu connu re-confirmé (icônes de carte personnalisées non chargées pour un invité via `/embed/:token`, jeton invité non couvert par `read_map_icon_file`) | lu | Visiteur anonyme, Intégrateur | 2 | M | **GAP-19** (disclosed à la clôture) | — |

## 2. Classement impact × effort

- **Gains rapides** (impact ≥ 6, effort S) — **8** : D01¹, D02*, D09*, D11,
  D19, D26, D28, D32, D41. (¹D01 est en effort M, listé ici car son
  correctif — ajouter 2 liens de nav — est en pratique un gain rapide ;
  D02/D09 ont un impact < 6 mais un correctif d'une ligne, retenus comme
  gains rapides opportunistes.)
- **Chantiers** (impact ≥ 6, effort M/L) — **9** : D06 *(impact 4, effort
  L — inclus car structurant)*, D13, D18, D21, D29, D31, D33, D40, D44.
- **Finitions** (impact < 6) — le reste (D03-D05, D07-D10, D12,
  D14-D17, D20, D22, D24-D25, D27, D30, D34-D39, D42-D43, D45-D58) —
  **41 lignes**.

Priorité absolue du diagnostic : **D18** (impact 9, seul défaut au-dessus
de 6×tous critères) — carte/widget ne cadre jamais sur les données réelles
à l'ouverture, structurel sur les deux hôtes.

## 3. Trois vagues de correctifs

### Vague A — bloquants et découvrabilité (7 SP proposés)

1. **SP-A1** — Fermer GAP-80/GAP-81 : lien de navigation réel vers
   `/bookmarks` et `/analytics/sql` (D01). *Gain rapide.*
2. **SP-A2** — Un-liner : ajouter `"site"` à la liste des kinds éditables
   de `ItemDetailPage` (D02). *Gain rapide.*
3. **SP-A3** — Garde rôle × flag sur `NewItemButton` (pipeline/
   visual-query gatés sur `automation.manage`, pas seulement `etlEnabled`)
   + message « non activé sur cette instance » au lieu du spinner infini
   sur `/pipelines/new` (D03 + D09). *Gain rapide.*
4. **SP-A4** — Auto-cadrage sur l'emprise des données à l'ouverture d'une
   carte/d'un widget carte (D18). Impact le plus élevé du diagnostic.
5. **SP-A5** — Décision produit puis spec : le widget carte peut-il porter
   raster/deck.gl/tiles3d comme l'éditeur autonome ? (D13) — à trancher
   avant tout chantier.
6. **SP-A6** — Suppression de secret (UI + outil MCP) (D05).
7. **SP-A7** — Réouverture d'un pipeline créé par le wizard visuel vers son
   éditeur d'origine, pas systématiquement le DAG complet (D58).

### Vague B — états système et cohérence (12 SP proposés)

1. **SP-B1** — État vide avec CTA (`EmptyState` du kit) sur le catalogue +
   4 listes admin (D19 + D20). *Priorité 1 de la vague — constat le plus
   cité du diagnostic (5 IDs convergents).*
2. **SP-B2** — Confirmation systématique des suppressions destructives :
   pièce jointe + styliser les 3 `window.confirm` restants en
   `ConfirmDialog` (D26). *Gain rapide.*
3. **SP-B3** — Câbler le `Toast` déjà monté : confirmation de succès sur
   les 5 éditeurs principaux (D28). *Gain rapide.*
4. **SP-B4** — Adopter `Spinner`/`Skeleton` du kit sur les 37 sites de
   chargement en texte brut (D21).
5. **SP-B5** — Extraire et afficher le detail `problem+json` (RFC 7807)
   dans le client HTTP générique, différencier le 429 (D22).
6. **SP-B6** — Garde de navigation sur brouillon non sauvegardé — nécessite
   d'abord une décision d'architecture (migration `BrowserRouter` →
   `createBrowserRouter`/data router, ou `beforeunload` + interception de
   clic) (D29). *Chantier structurant, prioritaire dans la vague.*
7. **SP-B7** — Timeout réseau explicite (`AbortSignal`) + message dédié
   « cœur injoignable » (D31).
8. **SP-B8** — `aria-describedby`/`aria-invalid` sur `Field` du kit et le
   formulaire généré + résumé d'erreurs en tête de formulaire (D33).
9. **SP-B9** — Restaurer l'état de navigation interne (onglet/sélection/
   nœud) des 4 builders depuis l'URL (D06).
10. **SP-B10** — Progression/annulation des jobs longs + vocabulaire de
    statut harmonisé entre surfaces (D24 + D25) ; texte « Export en
    cours… » pendant le sondage (D57) ; indicateur de troncature MVT/
    chargement de tuiles lourdes (D17).
11. **SP-B11** — Adopter `DataTable` du kit sur les 4 implémentations
    divergentes (admin ×5, aperçu pipeline, widget table) (D40).
12. **SP-B12** — Migrer `AppRuntimePage` + 3 pages publiques vers le kit
    tokenisé ; éliminer les 187 classes Tailwind de couleur brute restantes
    hors `shell/src/map/*` (D44). *Chantier prioritaire — page la plus
    visitée du produit.*

Point mineur additionnel de cette vague : mirroiter
`printLayout.showLegend` dans `AppRuntimePage` (D14), message « connexion
perdue » unifié (D30).

### Vague C — polish, a11y AA, perf perçue, onboarding (≈20 points, groupables en 5-6 SP)

1. **SP-C1** — A11y clavier/focus : `MapPopup` (Échap + focus, D41),
   focus de retour au déclencheur après fermeture d'un dialogue (D48),
   fallback clavier de `FieldOverrides` (D34), `aria-required` sur les
   champs générés (D32, déjà listé en gain rapide — séquencer avec C1).
2. **SP-C2** — Étendre axe-core à toutes les routes atteintes (pas de
   liste figée), corriger le chiffre documenté par REV-178 (D43) ;
   `prefers-reduced-motion` (D42).
3. **SP-C3** — Cohérence design : éliminer les `text-[Npx]` arbitraires
   (D46), une seule action « primaire » par barre d'outils (D47), nettoyer
   le mélange kit/legacy + clés i18n orphelines (D10).
4. **SP-C4** — Onboarding : recherche globale/palette de commandes (D07),
   aide contextuelle (D49), UI de quota de stockage pour l'Administrateur
   (D08).
5. **SP-C5** — SQL Lab : message d'erreur formaté (D51), coloration
   syntaxique/autocomplétion (D54, effort L, dépendance externe à évaluer).
6. **SP-C6** — Cohérence texte : pluralisation i18n + `useDocumentMeta`
   `PublicItemPage` (D50) ; bouton « Copier » (D52) ; CEL/`fr-FR` (D35) ;
   progression d'upload par fichier (D36) ; `htmlFor`/`id` sur ~15 labels
   (D38) ; hints formulaire secret (D39) ; autocomplétion de champ widget
   carte (D12) ; légende symbologie éditeur standalone (D15) ; vérification
   tactile/mobile dynamique (D16) ; `readOnly` canevas pipeline (D55) ;
   copilote historique + aperçu (D56) ; bouton « exécuter maintenant »
   AlertRule (D04).

Résidus confirmés sans action nouvelle (déjà trackés par GAP/REV
existants, re-vérifiés ouverts par ce diagnostic) : D23 (GAP-82/REV-185),
D53 (GAP-19), D45 (REV-088), D27 (constat neutre, pas un défaut).

## 4. Filets anti-régression proposés

Une classe payée deux fois devient une porte CI (culture du dépôt,
`CLAUDE.md` § Pièges récurrents) :

| Classe de défaut récurrente | Filet proposé |
|---|---|
| Composant du kit posé mais jamais adopté en production (`Toast`, `DataTable`, `Spinner`/`Skeleton`, `EmptyState` : chacun à 1-4 consommateurs réels sur tout le shell) | Test de couverture minimal : chaque composant listé comme « à adopter » a un plancher de consommateurs de production (hors galerie interne), non régressif comme `.coverage-threshold` |
| Route de `routes.tsx` sans lien entrant (`GAP-80`/`GAP-81`/D07) | Test d'inventaire : toute route déclarée a ≥1 lien entrant retrouvable dans le code (nav/menu/action), ou est explicitement listée `deep-link-only` dans un registre dédié |
| Couleur Tailwind brute hors ambiance (SP-34 n'a couvert que `shell/src/map/*`, 187 occurrences restantes) | Étendre la règle de lint utilisée pour SP-34 à tout `shell/src` avec liste d'exemption explicite (au lieu d'un périmètre non maintenu) |
| Action destructive sans `ConfirmDialog` du kit (`window.confirm` natif ou absence totale) | Lint interdisant `window.confirm` hors fichiers explicitement exemptés ; test de contrat sur les points d'entrée `handleDelete`/`onDelete` |
| Mutation de sauvegarde sans retour de succès visible (5/5 éditeurs concernés) | Motif de test partagé : tout hook `useMutation` de sauvegarde d'un éditeur principal doit exposer et rendre `isSuccess` |
| Champ de formulaire généré sans marquage accessible du caractère requis | Test de contrat sur `fieldsFromSchema`/`FieldInput` : un champ `required` du schéma pose `required`/`aria-required` sur l'élément de formulaire, pas seulement un suffixe visuel |
| Capacité `xxxEnabled` propagée jusqu'au profil sans jamais être lue par un écran (`quotasEnabled`) | Test statique reliant chaque capacité de `ConfigContext`/`capabilities.ts` à au moins un site de lecture (`DomainDef` ou composant) |
| Asymétrie rôle × flag (option visible dans le chrome mais 403 serveur après formulaire rempli) | Test de matrice génératif : 4 rôles prédéfinis × chaque `CORE_*_ENABLED` on/off → toute entrée visible doit soit réussir, soit afficher un état « non disponible » explicite avant soumission, jamais un 403 en sortie de formulaire |
| Couverture axe-core figée à une liste de pages qui ne suit pas la croissance du routeur (9 documentées, 17 réelles) | Générer la liste des routes auditées depuis `routes.tsx` plutôt que la maintenir à la main |
| Migration kit `ui/*` → `ui/kit/*` mesurée manuellement (comptages ponctuels sans seuil) | Script de comptage `ui/*` vs `ui/kit/*` par famille triptyque, seuil non régressif comme `.bundle-size-threshold`/`.coverage-threshold` |

## 5. Points positifs confirmés (non détaillés en table, pour mémoire)

Parité caméra/basemap/terrain widget↔éditeur (GAP-52), symbologie
catégoriel/continu/classé/icônes partagée (GAP-52), 5 kinds de couche tous
créables (GAP-35/36), formulaires générés depuis schéma + overrides
(décision figée respectée), `AppErrorBoundary` (I12 couvert),
bannière lecture seule cohérente sur les 5 éditeurs + items partagés,
`CreateRolePanel`/`EditRolePanel` fieldset+legend, planification cron
(`PipelineScheduleEditor`, patron de référence), bibliothèque d'icônes
unique + `aria-label` obligatoire sur `IconButton`, pièces jointes câblées
en popup (fix I6), champ d'intervalle de moissonnage (GAP-44 fermé),
aller-retour wizard visuel ↔ éditeur de dataset fonctionnel, tous les
parcours dynamiques Phase 1b (Créateur/Analyste/Lecteur/Admin/Visiteur
anonyme/mode démo/clavier SQL Lab) confirmés fonctionnels sans violation
axe critique.

## 6. Nouvelles entrées REV-nnn proposées

Non écrites dans `docs/revue/2026-09-04-backlog.md`. Numérotation
provisoire à partir de **REV-201** (dernière entrée connue : REV-200,
`docs/revue/2026-09-04-backlog.md`, consignée 2026-09-24). À valider par
Tanguy avant intégration ; les défauts déjà couverts par un GAP/REV
existant (D01, D14, D23, D34, D40's résiduels partiels, D43, D45, D53,
D54, D55) ne génèrent **pas** de nouvelle entrée — seule une mise à jour
de l'existant est proposée pour D43 (chiffre REV-178).

| REV proposée | Code | Titre court | Vague | Impact | Effort |
|---|---|---|---|---|---|
| REV-201 | D02 | Item Site : dispatcher d'édition manquant une branche | A | 4 | S |
| REV-202 | D03 | Rôle × flag : NewItemButton pipeline/visual-query sans garde privilège | A | 4 | S |
| REV-203 | D09 | `/pipelines/new` bloqué sur spinner infini si ETL désactivé | A | 2 | S |
| REV-204 | D05 | Secret non supprimable (UI + MCP) | A | 2 | M |
| REV-205 | D58 | Pipeline wizard visuel : porte à sens unique vers le DAG complet | A | 4 | M |
| REV-206 | D13 | Widget carte : impossibilité structurelle raster/deck/tiles3d | A | 6 | L |
| REV-207 | D06 | Aucun des 4 builders ne restaure son état de navigation depuis l'URL | B | 4 | L |
| REV-208 | D07 | Aucune recherche globale / palette de commandes | C | 2 | L |
| REV-209 | D08 | Quotas de stockage : mécanisme livré, UI totalement absente | C | 2 | L |
| REV-210 | D10 | Mélange kit/legacy + clés i18n orphelines sur 4 pages centrales | C | 3 | M |
| REV-211 | D19 | Catalogue et listes structurantes : état vide sans CTA | B | 6 | S |
| REV-212 | D20 | 4 listes admin n'affichent rien à vide | B | 4 | S |
| REV-213 | D21 | Spinner/Skeleton du kit sans consommateur de production | B | 6 | M |
| REV-214 | D22 | Detail `problem+json` perdu par le client HTTP générique ; 429 non différencié | B | 4 | M |
| REV-215 | D24 | Jobs longs : pas de progression ni d'annulation | B | 2 | M |
| REV-216 | D25 | Vocabulaire de statut de job non harmonisé | B | 2 | M |
| REV-217 | D26 | Suppression de pièce jointe sans confirmation | B | 6 | S |
| REV-218 | D28 | `Toast` jamais câblé ; pas de confirmation de succès à l'enregistrement | B | 6 | S |
| REV-219 | D29 | Aucune garde de navigation sur brouillon non sauvegardé | B | 6 | M |
| REV-220 | D30 | Pas de message unifié « connexion perdue » | B | 4 | M |
| REV-221 | D31 | Timeout réseau absent : chargement infini si le cœur ne répond jamais | B | 6 | M |
| REV-222 | D32 | Formulaire généré : `aria-required` absent, requis non annoncé | C | 6 | S |
| REV-223 | D33 | `aria-describedby`/`aria-invalid` absents sur les champs de formulaire | B | 6 | M |
| REV-224 | D35 | Erreurs CEL en texte brut ; dates/nombres sans formatage `fr-FR` forcé | C | 2 | M |
| REV-225 | D36 | Upload de pièce jointe : pas de progression par fichier | C | 2 | M |
| REV-226 | D38 | ~15 `<label>` non associés par `htmlFor`/`id` | C | 2 | M |
| REV-227 | D39 | Formulaire de création de secret sans hints sur champs sensibles | C | 2 | M |
| REV-228 | D40 | `DataTable` du kit non adopté, 4 implémentations de table divergentes | B | 6 | L |
| REV-229 | D41 | `MapPopup` : pas de fermeture Échap ni gestion de focus | C | 6 | S |
| REV-230 | D42 | Pas de `prefers-reduced-motion` | C | 1 | S |
| REV-231 | D44 | `AppRuntimePage` + pages publiques : kit/tokens non migrés | B | 6 | L |
| REV-232 | D46 | 15 valeurs `text-[Npx]` arbitraires hors échelle de tokens | C | 2 | M |
| REV-233 | D47 | Deux styles « primaires » coexistent dans la barre d'outils App Builder | C | 3 | S |
| REV-234 | D48 | Focus non restauré au déclencheur après fermeture Échap d'un dialogue | C | 2 | S |
| REV-235 | D49 | Aucune aide/documentation contextuelle dans le produit | C | 2 | M |
| REV-236 | D50 | `t()` sans pluralisation ; `PublicItemPage` sans `useDocumentMeta` | C | 3 | M |
| REV-237 | D51 | SQL Lab affiche l'exception backend brute | C | 4 | S |
| REV-238 | D52 | Aucun bouton « Copier » nulle part dans le produit | C | 3 | S |
| REV-239 | D56 | Copilote : historique non persisté, opérations sans aperçu préalable | C | 4 | M |
| REV-240 | D57 | Export Bookmark/App : aucun texte « en cours » pendant le sondage | B | 4 | S |
| REV-241 | D34 | `FieldOverrides` : réordonnancement drag-only sans fallback clavier | C | 4 | S |
| REV-242 | D12 | Widget carte : `availableFields` vide sur symbologie et popup | C | 3 | S |
| REV-243 | D15 | Pas de légende de symbologie dans l'éditeur de carte standalone | C | 4 | M |
| REV-244 | D16 | Interaction tactile/mobile non vérifiée dynamiquement | C | 4 | S |
| REV-245 | D17 | Pas d'indicateur de troncature MVT / chargement de tuiles lourdes | B | 4 | M |
| REV-246 | D04 | `AlertRule` : pas de bouton « exécuter maintenant » côté UI | C | 1 | M |
| REV-247 | D14 | `printLayout.showLegend` ignoré silencieusement dans `AppRuntimePage` | B | 2 | S |
| REV-248 | D54 | SQL Lab : pas de coloration syntaxique ni d'autocomplétion | C | 2 | L |

*(mise à jour proposée, pas une nouvelle REV)* — **REV-178** : corriger le
chiffre « 9 pages auditées » en 17 réel, ajouter `AppRuntimePage` à
l'échantillon axe-core (D43).

---

**Résumé** : 58 défauts consolidés (22 confirmés en Phase 2, tous
« confirmé », 0 réfuté/reclassé) ; 8 gains rapides, 9 chantiers, 41
finitions ; Vague A = 7 SP, Vague B = 12 SP, Vague C ≈ 6 SP ; 10 filets
anti-régression proposés ; 48 nouvelles entrées `REV-201`–`REV-248`
proposées (+ 1 mise à jour de REV-178), non écrites dans le backlog.
