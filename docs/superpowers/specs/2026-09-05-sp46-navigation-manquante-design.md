# SP-46 — Découvrabilité : navigation manquante

## 1. Motivation

L'analyse des manques de SP-42
(`docs/revue/2026-09-04-analyse-gaps.md`) a trouvé quatre écrans **complets,
testés et servis par le cœur**, mais atteignables uniquement en tapant leur
URL à la main — aucun lien nulle part dans le shell ne les mentionne. Ce
n'est pas une capacité manquante : c'est un défaut de découvrabilité, la même
classe de défaut sur trois des quatre points (« ajouter un point d'entrée de
navigation qui n'existe pas »), plus une quatrième variante (masquer un lien
déjà présent mais mal gardé). Vérifié directement dans le code (piège
CLAUDE.md n°3 et n°12 : ne pas se fier au texte de l'analyse de gaps sans
relire les fichiers cités) :

- **GAP-30** — `/admin/collections` (`CollectionsAdminPage`) : la route
  existe et est gardée par `RequirePrivilege privilege="admin.collections.manage"`
  (`shell/src/shell/routes.tsx:291-300`). Aucun `<Link>` du dépôt n'y pointe
  hors de `routes.tsx` lui-même et de `domainRoutes.ts` (`ADMIN_DESTINATIONS`,
  qui ne sert qu'à calculer la destination du **domaine** Admin de la barre de
  domaines — un profil qui détient `admin.extensions.manage` ne passera
  jamais par cette entrée). `AdminExtensionsPage.tsx` (seule page qui
  regroupe aujourd'hui des liens vers les autres écrans d'administration,
  lignes 24-32) ne propose que trois liens : `/admin/infrastructure`,
  `/admin/roles`, `/admin/users`. Confirmé par une lecture complète du
  fichier — pas de quatrième lien.
- **GAP-39** — `/admin/harvest` (`HarvestSourcesAdminPage`) : même
  constat. La route existe, gardée par
  `RequirePrivilege privilege="admin.harvest.manage"`
  (`shell/src/shell/routes.tsx:302-311`), le cœur sert des routes complètes
  (`core/app/harvest/routes.py:122-257` : création/suppression/exécution de
  source, vérifié réel) et 6 suites E2E existantes (`harvest-stac.spec.ts`,
  `harvest-csw.spec.ts`, `harvest-wms.spec.ts`,
  `harvest-ogc-records.spec.ts`, `harvest-ckan.spec.ts`,
  `harvest-arcgis.spec.ts`) y naviguent — mais toutes par
  `page.goto("/admin/harvest")` direct, jamais via un clic. Aucun lien dans
  `AdminExtensionsPage.tsx`.
- **GAP-32** — `/reports` (`ReportsRoute`, catalogue filtré
  `fixedType="report"`) : la route existe
  (`shell/src/shell/routes.tsx:267`), mais le domaine Automatisation
  (`DOMAIN_PATHS.automation`, `shell/src/shell/chrome/domainRoutes.ts:14`)
  pointe vers `/?type=pipeline`, jamais vers `/reports`. Le type `report` est
  bien présent dans le sélecteur de type du catalogue générique
  (`RESOURCE_TYPE_ORDER`, `shell/src/api/resourceTypes.ts`) — un utilisateur
  qui sait que ce type existe peut le sélectionner depuis `/` — mais rien ne
  suggère son existence, et le sélecteur de type est **masqué** sur
  `/reports` lui-même et sur toute page à `fixedType` fixé (`CatalogPage.tsx`,
  `{!fixedType && (...)}`). Seule route qui mène à un rapport aujourd'hui :
  `/reports/new`, elle-même accessible uniquement depuis l'action « Planifier
  un rapport » d'un signet existant (`shell/src/shell/ItemActions.tsx:99`).
  Un utilisateur sans signet préexistant ne découvre jamais qu'un rapport
  planifié est un objet qu'on peut lister. Confirmé : aucune suite E2E
  n'appelle `page.goto("/reports")` sans suffixe.
- **GAP-67** — `AdminExtensionsPage.tsx` (lignes 24-32) propose ses trois
  liens (`/admin/infrastructure`, `/admin/roles`, `/admin/users`)
  **inconditionnellement**, sans vérifier que l'utilisateur courant détient
  le privilège que la route cible exige
  (`settings.instance.manage`/`admin.roles.manage`/`admin.users.manage`
  respectivement, `routes.tsx:315-345`). Vérifié par les tests existants
  (`AdminExtensionsPage.test.tsx:138-156`) : ils assertent la présence des
  liens vers `/admin/roles` et `/admin/users` en rendant la page avec le
  handler MSW par défaut (`shell/src/test/msw/handlers.ts:29-42`), dont les
  privilèges (`["catalog.manage", "maps.manage", "data.view",
  "data.manage"]`) ne contiennent **aucun** des trois privilèges admin
  requis — preuve directe que les liens s'affichent bien sans garde
  aujourd'hui. La garde serveur (`RequirePrivilege` sur la route cible) tient
  déjà : cliquer un lien vers une route hors de portée affiche le message de
  refus de `RequirePrivilege`, pas une faille de sécurité. C'est un défaut de
  confort — un administrateur partiel voit des portes qui claquent au lieu de
  ne pas les voir — et une divergence avec la doctrine déjà écrite ailleurs
  dans le dépôt (`shell/src/auth/capabilities.ts:6-9` : « un privilège
  manquant MASQUE, une capacité coupée VERROUILLE » — appliquée à la barre de
  domaines, jamais à cette page).

Les quatre corrections sont mécaniques : aucune des quatre ne change un
comportement de rendu, de données ou de permission déjà en vigueur (la garde
serveur ne bouge pas) — seulement ce qui est montré et où. Estimation SP-42 :
0.5j + 0.5j + 0.5j + 1j = 2.5j.

## 2. Primitive de garde de privilège côté page (GAP-67)

Le dépôt n'a **pas** de hook `usePrivilege()`/`useHasPrivilege()` réutilisable
côté composant — vérifié (`grep -rn "usePrivilege\|useHasPrivilege"
shell/src` : aucune occurrence). Les deux mécanismes existants :

1. `RequirePrivilege` (`shell/src/auth/RequirePrivilege.tsx`) : garde de
   **route entière** — rend soit les enfants, soit un message de refus. Ne
   convient pas ici : on veut masquer un lien individuel dans une page qui
   reste par ailleurs affichée, pas remplacer toute la page par un refus.
2. `Profile`/`capabilities.ts` (`shell/src/auth/capabilities.ts`) : calcule
   l'état de la **barre de domaines** à partir d'un objet `Profile` construit
   une seule fois dans `AppLayout.tsx:28-39`
   (`new Set(meQuery.data?.privileges ?? [])` + capacités d'instance) — mais
   `AppLayout` ne transmet ce `Profile` à aucun enfant (`ProtectedLayout`
   rend `<AppLayout><Outlet /></AppLayout>`, sans contexte ni prop). Une page
   comme `AdminExtensionsPage` ne le reçoit pas.

Décision : ne pas introduire de nouvelle abstraction pour 5 liens sur une
seule page. Reprendre l'idiome déjà utilisé par `RequirePrivilege` lui-même
(`meQuery.data?.privileges.includes(privilege) === true`), au niveau du
composant `AdminExtensionsPage`, avec son propre appel `useMe()` (déjà un
hook React Query mis en cache sous la clé `["me"]` — `AppLayout` l'appelle
déjà pour construire la barre de domaines : pas de requête réseau
supplémentaire, seulement une lecture de cache). Si une deuxième page a
besoin du même patron après SP-46, l'extraire en hook partagé sera un
refactor pur (même risque que les étapes de SP-43) — hors périmètre ici.

Forme retenue, un tableau de déclarations à côté des liens plutôt que cinq
conditions répétées :

```ts
const ADMIN_LINKS: { to: string; label: string; privilege: string }[] = [
  { to: "/admin/infrastructure", label: "Outils d'infrastructure →", privilege: "settings.instance.manage" },
  { to: "/admin/roles", label: "Rôles et privilèges →", privilege: "admin.roles.manage" },
  { to: "/admin/users", label: "Utilisateurs →", privilege: "admin.users.manage" },
  { to: "/admin/collections", label: "Collections →", privilege: "admin.collections.manage" },
  { to: "/admin/harvest", label: "Moissonnage →", privilege: "admin.harvest.manage" },
];
```

filtré par `meQuery.data?.privileges.includes(link.privilege)` avant de
mapper en `<Link>`. Le lien statique « ← Retour au catalogue » (vers `/`,
sans garde — le catalogue est lisible par tout utilisateur authentifié) reste
hors de ce tableau, inchangé.

Doctrine retenue, identique à `capabilities.ts` (§6.2 de la spec SP-29a citée
dans son commentaire) : **un privilège manquant masque le lien**, il n'est
jamais affiché grisé ni désactivé — cohérent avec le fait que la page elle
-même (`/admin/extensions`) n'est déjà atteignable que par un détenteur d'au
moins un privilège `admin.*` (le domaine « admin » de la barre de domaines
exige `admin.*` au sens large, `capabilities.ts:92-103`), donc un visiteur de
cette page a par construction un intérêt légitime à voir l'existence de
l'administration — sans qu'on lui liste des portes qu'il ne peut pas ouvrir.

## 3. GAP-30 / GAP-39 — point d'entrée manquant

Correctif identique aux deux : ajouter l'entrée manquante à `ADMIN_LINKS`
ci-dessus (donc déjà gardée dès son introduction — pas de fenêtre où un lien
non gardé apparaît puis se fait garder après coup). Aucun changement à
`CollectionsAdminPage.tsx`/`HarvestSourcesAdminPage.tsx` : leur propre lien
retour (`← Retour au catalogue`, vers `/`) suffit, la navigation
Administration → Collections/Moissonnage est à sens unique comme les trois
existantes (Infrastructure/Rôles/Utilisateurs n'ont pas non plus de lien
retour vers `/admin/extensions` — cohérent, pas une régression à introduire
ici).

## 4. GAP-32 — point d'entrée manquant, site différent

`AdminExtensionsPage` ne convient pas ici : les rapports planifiés ne sont
pas une page d'administration, c'est un type d'objet de contenu au même titre
que les autres (`ResourceType = "report"`). Le point d'entrée naturel est la
page que le domaine Automatisation affiche déjà : `CatalogPage.tsx`, montée
sans `fixedType` sur `/?type=pipeline` (via `DOMAIN_PATHS.automation`). Cette
page a un volet « Filtrer » (`browse`, lignes ~85-136) qui contient déjà le
sélecteur de type — mais ce sélecteur est **masqué** dès qu'un `fixedType`
est fourni (jamais le cas ici) et reste, dans tous les cas, un menu déroulant
générique qui ne suggère l'existence des rapports à personne qui ne les
connaît pas déjà.

Correctif : dans le volet « Filtrer » de `CatalogPage`, sous le sélecteur de
type, ajouter un lien conditionnel — visible uniquement quand
`type === "pipeline" && !fixedType` (c'est-à-dire : seulement sur l'atterrissage
du domaine Automatisation, jamais sur `/`, `/bookmarks`, `/reports` ou toute
autre vue à `fixedType` fixé, qui ont chacune leur propre volet de navigation
ou n'ont pas besoin de ce raccourci) :

```tsx
{type === "pipeline" && !fixedType && (
  <Link to="/reports" className="text-accent hover:underline">
    Rapports planifiés →
  </Link>
)}
```

Choix : conditionner sur `type` (dérivé de l'URL, donc de la navigation
réellement en cours) plutôt que sur un nouveau prop dédié — `CatalogPage` n'a
aujourd'hui aucune notion de « domaine actif », seulement de `type`/`fixedType`
lus depuis l'URL ; ajouter un prop supplémentaire pour une seule ligne de UI
serait une abstraction non justifiée par le reste du fichier. Pas de garde de
privilège sur ce lien : `/reports` n'est gardée par aucun `RequirePrivilege`
(catalogue filtré, lisible par tout utilisateur authentifié comme les autres
domaines de contenu — cf. commentaire existant `capabilities.ts:56-64`), donc
rien à masquer.

## 5. Hors périmètre

- Un lien retour symétrique depuis `CollectionsAdminPage`/
  `HarvestSourcesAdminPage` vers `AdminExtensionsPage` — aucune des trois
  pages existantes (Infrastructure/Rôles/Utilisateurs) ne l'a, ne pas
  introduire une asymétrie de traitement entre les cinq.
- Un hook `usePrivilege()` partagé — un seul consommateur après ce plan
  (`AdminExtensionsPage`), extraction prématurée (cf. §2).
- Un lien de création de rapport (« Nouveau rapport ») visible sans signet
  préexistant : `ReportEditPage`/`ReportNewRoute` exigent aujourd'hui un
  `bookmarkItemId` (un rapport planifié rejoue un signet) — changer ce
  couplage est une décision produit distincte de SP-16b, non demandée par
  l'analyse de gaps et hors budget de ce SP (2.5j).
- Câbler `/admin/harvest`/`/admin/collections` dans `ADMIN_DESTINATIONS`
  (`domainRoutes.ts`) au delà de ce qui y est déjà — ce tableau calcule la
  destination du **domaine** Admin pour un profil qui n'a pas
  `admin.extensions.manage`, il contient déjà les cinq entrées
  (`domainRoutes.ts:39-45`, vérifié) ; seul le lien interne à
  `AdminExtensionsPage` manquait.
- Toute correction sur les 41 autres gaps confirmés non retenus par SP-42
  (backlog `docs/revue/2026-09-04-backlog.md`).

## 6. Risques de régression

- **GAP-67, retrait de deux assertions existantes** :
  `AdminExtensionsPage.test.tsx:138-156` assertent aujourd'hui la présence
  des liens `/admin/roles`/`/admin/users` sous le mock `/me` par défaut (sans
  les privilèges requis) — ces deux tests doivent être réécrits pour mocker
  un utilisateur qui détient le privilège testé (patron
  `RequirePrivilege.test.tsx:10-23`, fonction `mockMe(privileges)`), sinon la
  Tâche 3 les fait échouer à bon droit (ils vérifiaient un comportement
  désormais invalide) — un plan qui ne les toucherait pas serait en échec
  dès `npm run test`, pas une régression silencieuse.
- **GAP-32, portée du garde `!fixedType`** : sans lui, le lien apparaîtrait
  aussi sur toute page qui passerait un jour `fixedType="pipeline"` (aucune
  aujourd'hui — `CatalogRoute`/`BookmarksRoute`/`ReportsRoute` utilisent
  respectivement aucun/`"bookmark"`/`"report"`) ; le garder rend le
  correctif robuste à un futur usage de `CatalogPage` que ce plan ne peut pas
  anticiper.
- **Tests E2E existants** (`harvest-*.spec.ts`, `admin-collections.spec.ts`)
  naviguent tous par `page.goto()` direct — ajouter un lien ne change rien à
  leur exécution, mais confirmer qu'aucun ne fait d'assertion négative du
  type « ce lien n'existe pas » avant de conclure (vérifié : aucun ne le
  fait, grep négatif effectué).

## 7. Ce que ce document ne tranche pas

- Si un futur SP ajoute une sixième destination `/admin/*`, l'ajouter à
  `ADMIN_LINKS` (§2) est mécanique — mais rien ici n'empêche une septième
  page d'admin de choisir un tout autre patron de regroupement (ex. une
  vraie page d'index `/admin` distincte d'`/admin/extensions`) : ce plan ne
  fait que réparer l'existant, pas redessiner la navigation d'administration.
