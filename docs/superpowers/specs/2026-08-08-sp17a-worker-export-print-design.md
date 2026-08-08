# SP-17a — Worker d'export Playwright & `PrintLayout`

> Brainstorm du 2026-08-08. Première tranche de SP-17 (« 3D & impression »,
> A24/A25 de `docs/vision/2026-07-04-feuille-de-route-geostudio.md`). Ordre
> retenu au sein de SP-17 : **17a (ce document) → 3D (17b, indépendant) →
> `ReportSchedule` (tranche suivante, dépend de 17a)** — la contrainte A27
> amendée (« SP-16 requiert le worker d'export de SP-17 ») s'applique
> désormais à `ReportSchedule`, qui a été déplacé de SP-16c vers SP-17 (cf.
> CLAUDE.md, entrée SP-16b).

## Objectif

Poser le socle d'export (A25) réutilisable par n'importe quelle carte ou
app/dashboard publiée : rendu headless Playwright de la vraie page runtime
(WYSIWYG exact des styles MapLibre, pas de re-génération séparée) → image
PNG haute résolution ou PDF paginé mis en page, déclenché à la demande par un
bouton « Exporter » dans la visionneuse de carte et le runtime d'app/dashboard.

Ce socle est :
- **une fonctionnalité utilisable seule** (export manuel immédiat, valeur
  livrée dès cette tranche) ;
- **le prérequis direct de `ReportSchedule`** (rapports planifiés PDF
  paginés), qui réutilisera ce worker et cette file sans les reconstruire.

## Hors périmètre (assumé, non traité ici)

- **3D** (A24, `tiles3d` + terrain deck.gl) : tranche indépendante de SP-17,
  ordre arbitraire par rapport à 17a, ne bloque ni n'est bloquée par ce
  document.
- **`ReportSchedule`** : planification récurrente, distribution, pagination
  multi-dashboards — tranche suivante, consommera ce worker tel quel.
- **Print « pro »** (CMJN, très hautes résolutions, QGIS Server) : écart
  assumé avec la vision, documenté dans A25 ; bascule uniquement sur demande
  réelle.
- **Export de sites publics** (`kind="site"`) : le worker est générique
  (rend n'importe quelle URL runtime), mais le bouton « Exporter » n'est
  câblé que sur `MapEditorPage` (mode visionneuse) et `AppRuntimePage` dans
  cette tranche. Étendre à `/sites/{slug}` est une extension future non
  planifiée.
- **Validation du contenu binaire du rendu en CI** : les tests E2E valident
  le flux (job → `done` → lien de téléchargement exposé), pas le rendu pixel
  du PNG/PDF — assumé, comme le reste des specs E2E existantes.

## Décisions arbitrées pendant le brainstorm

| Question | Décision | Pourquoi |
|---|---|---|
| Quel pan de SP-17 en premier ? | Worker d'export + `PrintLayout` (pas la 3D, pas `ReportSchedule` direct) | Prérequis direct de `ReportSchedule` (contrainte A27 déjà actée) ; livre une fonctionnalité visible sans dépendre de la 3D ; grain d'incrément cohérent avec le patron déjà utilisé (SP-15e avant SP-15f, SP-16a avant SP-16b) |
| Cartes seules ou cartes+apps/dashboards dès 17a ? | Les deux ensemble | Le worker headless et `PrintLayout` sont génériques par construction (rendent n'importe quelle page runtime) ; éviter de reconstruire le pipeline d'export une deuxième fois pour les dashboards |
| Authentification du worker Playwright | Jeton d'export éphémère signé par le cœur (TTL court, scopé item+utilisateur), plutôt qu'un compte de service à droits larges | Respecte le partage/RLS de l'utilisateur qui clique « Exporter » — l'export ne doit pas voir plus que ce que voit l'utilisateur ; symétrique au patron déjà en place (liens S3 présignés, jetons MCP) |
| Isolation du worker Playwright | Conteneur `export-worker` dédié + profil compose optionnel + flag instance-wide `CORE_EXPORT_ENABLED` (défaut désactivé) | Même patron déjà établi deux fois (sidecar `qgis-worker` SP-15d, `CORE_ETL_ENABLED` SP-15a) ; évite d'alourdir l'image worker par défaut pour tout le monde |
| Modèle de données `PrintLayout` | Champ `printLayout` optionnel embarqué dans `MapConfig`/`AppConfig` existants, pas un nouveau kind `BuilderConfig` | YAGNI : un layout d'impression n'a pas de cycle de vie propre (pas d'exécutions historisées, pas de partage indépendant contrairement à `AlertRule`/`Pipeline`) ; zéro migration, zéro nouvelle surface de permissions/catalogue |

## Modèle de données

Un champ optionnel `printLayout` ajouté au schéma `MapConfig` et au schéma
`AppConfig` (JSON déjà versionné par le cœur — pas de migration Alembic) :

```
printLayout?: {
  pageSize: "a4" | "a3"
  orientation: "portrait" | "landscape"
  title?: string
  showLegend: boolean
  showScaleBar: boolean
  showNorthArrow: boolean
  cartouche?: string
}
```

Valeurs par défaut sensées si le champ est absent (A4 portrait, pas de
titre, légende/échelle activées, flèche nord et cartouche désactivées) —
l'export fonctionne sans qu'un auteur ait configuré quoi que ce soit.

## Sécurité du rendu — jeton d'export

Au clic sur « Exporter », le cœur émet un jeton signé (JWT court, réutilise
le mécanisme de signature déjà en place pour les jetons applicatifs) :

- scope : `(tenant_id, user_id, item_id)` — un seul item, un seul
  utilisateur ;
- TTL court (~2 minutes — largement suffisant pour la navigation + le rendu
  Playwright, assez court pour limiter la fenêtre d'exposition si le lien
  fuite) ;
- transmis en paramètre de requête sur l'URL runtime du shell
  (`/maps/:pk?exportToken=…` en mode visionneuse,
  `/apps/:pk/:pageId?exportToken=…`) ;
- le bootstrap d'auth du shell (`shell/src/auth/`) le détecte, l'échange
  contre le contexte d'utilisateur correspondant côté cœur, et **saute le
  flux OIDC Keycloak** pour cette navigation précise.

Le worker Playwright ne possède donc aucune credential propre à droits
larges : il rend exactement ce que l'utilisateur cliqueur a le droit de
voir, partage/RLS inclus. Un jeton expiré ou déjà consommé fait échouer le
job en `error` avec un message actionnable, jamais un rendu partiel ou vide
pris pour un succès.

## Infrastructure

- Nouveau conteneur `export-worker` (image dédiée embarquant un navigateur
  Playwright — image plus lourde qu'un worker Python nu, volontairement
  isolée).
- Nouveau profil compose optionnel (mirroring `qgis`/`etl`) — absent du
  compose par défaut.
- Capacité instance-wide `CORE_ETL_ENABLED`-like : **`CORE_EXPORT_ENABLED`**
  (défaut `false`). Coupe la route REST d'export (403) ET masque le bouton
  « Exporter » côté shell quand désactivée — même porte que les capacités
  précédentes.
- Nouveau module cœur `core/app/export/` (routes, jobs, service de rendu et
  d'émission de jeton). Placement dans le contrat de couches import-linter à
  déterminer à l'exécution en fonction des imports réels nécessaires
  (`app.configs`, `app.items`, `app.sharing` a minima) — décision mécanique
  laissée au plan d'implémentation, pas structurante pour ce design.
- Nouvelle file procrastinate dédiée `export` : le worker Playwright n'écoute
  que cette file, séparée de `etl`/`harvest`/`ingestion`/`cdc`/`search` — la
  charge (navigateur headless) est d'une nature différente des jobs Python
  purs déjà en place, et l'isolation de conteneur ci-dessus n'a de sens que
  si la file l'est aussi.

## Flux asynchrone

1. `POST /export` `{item_id, format: "png" | "pdf"}` — vérifie
   `can(user, read, item)` et `CORE_EXPORT_ENABLED` ; échec → 403 explicite,
   jamais un job silencieusement ignoré.
2. Crée une ligne de suivi (table `export_jobs`, tenant-scopée, `audit_log`
   comme toute écriture) à l'état `pending`, **commit**, puis **defer** le
   job sur la file `export` — patron déjà établi (SP-15h : commit avant
   defer, jamais l'inverse, pour éviter qu'un worker ramasse la tâche avant
   que la ligne ne soit visible).
3. Le worker Playwright : navigue vers l'URL runtime avec le jeton d'export,
   attend le rendu stable (carte chargée, tuiles résolues), capture un PNG
   haute résolution ou imprime un PDF paginé selon `printLayout` (taille de
   page, orientation, chrome légende/échelle/flèche nord/cartouche/titre).
4. Upload du résultat sur S3, la ligne passe à `done` avec un lien présigné,
   ou à `error` avec un message si le rendu échoue (jeton expiré, timeout de
   chargement, page en erreur).
5. `GET /export/jobs/{id}` — polling côté shell, même patron que
   `PipelineRunPanel`/`node_stats` (SP-15g/h).

Exempté du garde lecture-seule démo : l'export est une action de lecture
(aucune écriture de donnée métier), même raisonnement que les routes
d'export CSV/XLSX/GeoJSON/GPKG de SP-16a.

## Shell

- Bouton « Exporter » sur `MapEditorPage` (mode visionneuse/preview) et sur
  `AppRuntimePage` (apps et dashboards, kinds `app`/`dashboard`) — masqué si
  `CORE_EXPORT_ENABLED` est désactivé (capacité résolue côté cœur, exposée
  au shell comme les capacités existantes).
- Dialogue d'export minimal : choix du format (PNG/PDF), rappel des options
  actives de `printLayout` (pas de re-saisie à l'export — configuré une fois
  dans le builder).
- Section d'édition `printLayout` dans `MapEditorPage` et `AppBuilderPage`
  (format, orientation, titre, cases légende/échelle/flèche nord,
  cartouche) — persistée dans la config existante, cycle `draft`/`onSave`
  déjà en place, pas d'action de sauvegarde séparée.
- Suivi du job après déclenchement : polling réutilisant le patron
  `PipelineRunPanel` (statut `pending`/`done`/`error`, lien de téléchargement
  dès `done`, message d'erreur actionnable si `error` — jamais un échec
  silencieux, cf. le défaut de fetch avalé trouvé en revue SP-16b).

## Tests

TDD cœur :
- Émission et validation du jeton d'export (scope correct, expiration,
  jeton déjà consommé, jeton pour un autre item/utilisateur rejeté).
- `POST /export` : flag `CORE_EXPORT_ENABLED` désactivé → 403 ; permission
  refusée (`can` faux) → 403 ; item introuvable → 404 ; succès → ligne
  `pending` créée et job déféré après commit.
- Job de rendu avec Playwright mocké (le test ne lance pas de vrai
  navigateur) : succès → `done` + lien présigné ; timeout/échec de
  navigation → `error` + message ; jeton expiré pendant le job → `error`.
- Sérialisation/validation Pydantic de `printLayout` sur les deux schémas de
  config (valeurs par défaut si absent, rejet des enums invalides).

E2E Playwright (nouvelle spec, ou extension d'une spec existante) :
- Créer une carte, configurer un `printLayout` minimal, cliquer
  « Exporter », vérifier que le job atteint `done` et qu'un lien de
  téléchargement est affiché.
- Cas capacité désactivée : bouton « Exporter » absent quand
  `CORE_EXPORT_ENABLED` est faux (cf. démo lecture-seule : contrat similaire
  déjà testé pour `CORE_ETL_ENABLED`).

## Critères d'acceptation

- Un utilisateur exporte une carte publiée en PNG et en PDF depuis la
  visionneuse ; le PDF respecte le `printLayout` configuré (format, légende,
  échelle) ; le rendu est fidèle à l'écran (mêmes styles MapLibre).
- Un utilisateur exporte un dashboard multi-widgets en PDF depuis le
  runtime ; le rendu est fidèle à l'écran.
- L'export respecte le partage : un utilisateur sans droit de lecture sur
  l'item ne peut pas déclencher d'export (403), et le rendu headless ne voit
  jamais plus que ce que l'utilisateur cliqueur voit lui-même.
- `CORE_EXPORT_ENABLED=false` (défaut) : aucune route d'export active, aucun
  bouton « Exporter » visible, aucun conteneur `export-worker` requis pour
  faire tourner le reste de la plateforme.

## Risques

- **Poids de l'image `export-worker`** (navigateur Playwright) — assumé,
  documenté dans A25 ; isolé par le profil compose optionnel, n'affecte pas
  les autres services.
- **Stabilité du rendu headless** : tuiles MapLibre/raster non chargées au
  moment de la capture → attente explicite d'un signal de « carte prête »
  côté page runtime (à préciser dans le plan d'implémentation) plutôt qu'un
  délai fixe fragile.
- **Fenêtre du jeton d'export** : TTL court limite l'exposition, mais un
  lien copié-collé pendant les ~2 minutes reste valide pour quiconque le
  possède — accepté, cohérent avec le TTL court des liens S3 présignés déjà
  utilisés ailleurs dans le projet.
