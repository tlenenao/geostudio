# Export d'apps déployables sans GeoStudio (SP-18)

> Spec issue du brainstorm du 2026-08-05. Objectif : permettre de **créer une
> app dans le builder GeoStudio puis l'exporter** sous une forme qui tourne
> **hors d'une instance GeoStudio en marche**, selon trois modes
> d'indépendance croissante. Inscrit comme **SP-18** dans la feuille de route
> (`docs/vision/2026-07-04-feuille-de-route-geostudio.md`, jalon **M15 apps
> portables**), dépend de SP-11, indépendant de SP-12/SP-14/SP-16/SP-17.

## 1. Contexte & motivation

GeoStudio permet déjà de construire des apps no-code (`AppConfig` +
`AppRenderer(config, mode)`, cf. règle d'architecture n°3 du CLAUDE.md) et de
les publier via des portails/sites hébergés par l'instance GeoStudio elle-même
(SP-13, `/sites/{slug}`). Ce qui manque : un utilisateur qui a construit une
app veut parfois la faire vivre **ailleurs** — sur son propre domaine, sur un
hébergeur statique gratuit, ou sur une machine qui n'aura jamais GeoStudio
installé dessus — sans dépendre en permanence de l'instance GeoStudio
d'origine.

C'est un chantier **orthogonal à SP-Deploy**
(`docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md`) : SP-Deploy
déploie **toute la plateforme** GeoStudio (catalogue, builder, cœur complet)
sur une machine. Ce chantier-ci exporte **une app unique**, déjà construite
sur une instance GeoStudio, pour qu'elle tourne **seule, ailleurs**, avec un
degré d'indépendance choisi par l'auteur de l'app.

### Pourquoi c'est faisable sans reconstruire le moteur de rendu

L'architecture actuelle rend ce chantier tractable pour une raison précise :
**`ItemClient` est déjà le seul point de contact entre le rendu et les
données** (règle d'architecture n°1 du CLAUDE.md). `AppRenderer`, `ActionBus`,
le moteur d'expressions CEL, les variables typées et le thème sont déjà
100% côté client et ne parlent jamais directement à une base ou à Keycloak —
ils passent tous par `ItemClient` (résolution de `DataSource` via
`DataProvider`, cf. `shell/src/builder/DataContext.tsx`). Exporter une app
revient donc à **fournir une implémentation alternative d'`ItemClient`** par
mode d'export ; le moteur de rendu lui-même ne change pas d'une ligne.

## 2. Les trois modes d'export

Un même mécanisme d'export produit un artefact différent selon le mode choisi
par l'auteur de l'app au moment de l'export. Les trois modes sont légitimes
selon le cas d'usage (dashboard qui doit rester à jour vs rapport figé
vs totale portabilité) — aucun ne remplace les deux autres.

### 2.1 Mode Connecté

Le bundle exporté (HTML/JS statique, buildé avec Vite) embarque `AppRenderer`
+ la config, et continue d'appeler **le cœur GeoStudio d'origine**, en
lecture, via les mêmes endpoints que l'instance normale (OGC API Features,
`/aggregate`, `/analytics/sql` si le SQL Lab est utilisé par l'app). C'est
l'équivalent d'un widget embarqué sur un domaine tiers, mais qui reste
« branché » sur ses données vivantes.

**Restriction v1 :** seuls les items/collections déjà **partagés
publiquement** (groupe de partage existant, mécanisme `can()` du cœur) sont
exportables dans ce mode. Aucun identifiant, token ou secret n'est embarqué
dans le bundle exporté — si l'app référence une donnée non publique, l'export
en mode Connecté est refusé avec un message explicite listant les sources
concernées.

### 2.2 Mode Autoporté (mini-serveur)

Le mode le plus ambitieux : l'artefact exporté est un **conteneur autonome**
(image Docker + `docker-compose.yml` minimal) contenant le bundle statique de
l'app **et** un mini-serveur read-only, sous-ensemble du cœur (uniquement OGC
API Features Part 1 + `/aggregate`), qui sert un **instantané** des
collections référencées par l'app.

L'instantané est produit à l'export : les collections/datasets utilisés par
l'app sont extraits en **GeoParquet** et interrogés côté serveur via **DuckDB**
— réutilisation directe du moteur analytique déjà construit en SP-11
(lakehouse CDC→GeoParquet, module DuckDB). Aucune dépendance à Postgres,
Keycloak ou MinIO dans l'artefact exporté.

Pas de synchronisation automatique post-export en v1 : l'instantané est figé
au moment de l'export, un **ré-export manuel** le régénère. Le mini-serveur
est **read-only** (pas d'écriture via widget Formulaire dans ce mode en v1).

### 2.3 Mode Statique (zéro backend)

Les données référencées par l'app sont figées en JSON/GeoJSON au moment de
l'export et embarquées directement dans le bundle. Déployable sur
**n'importe quel hébergeur statique** (Netlify, S3, GitHub Pages, un simple
`python -m http.server`) — aucun serveur, aucune base.

Le cross-filter, les expressions CEL, les variables typées et les actions
composées fonctionnent à l'identique (déjà exécutés côté client, cf. §1) :
seule la couche `ItemClient` change (lit des fichiers JSON bundlés au lieu
d'appeler une API). Toute écriture (widget Formulaire, actions d'écriture) est
**désactivée** dans ce mode faute de backend — le builder avertit l'auteur si
son app en contient avant l'export.

## 3. Mécanisme d'export commun

- **Déclenchement** : action « Exporter » dans le builder, sur une app
  publiée, avec un choix de mode (Connecté / Autoporté / Statique). Traduit en
  `POST /items/{appId}/export?mode=connected|standalone|static` côté cœur.
- **Build** : réutilise Vite (le shell le fait déjà). Le bundle exporté ne
  contient que les widgets réellement utilisés par la config — lu depuis
  `config.pages[].items[].type` — pour rester petit. Les widgets tiers WC
  (SP-8, chargés dynamiquement en ES modules) sont soit bundlés (Statique /
  Autoporté, pour rester utilisables hors-ligne), soit laissés en chargement
  dynamique depuis leur URL d'origine (Connecté).
- **`ItemClient` par mode** : trois implémentations concrètes de l'interface
  existante (`shell/src/api/itemClient.ts`) —
  - Connecté : quasi identique à `CoreItemClient` actuel, pointé sur l'URL du
    cœur d'origine, restreint aux endpoints de lecture publique.
  - Autoporté : pointe sur le mini-serveur embarqué dans le conteneur exporté.
  - Statique : lit des fichiers JSON bundlés au build, aucun réseau.
- **Garde de partage** : avant tout export (les 3 modes), le cœur vérifie que
  chaque `DataSource` de la config référence un item/collection partagé
  publiquement. Un export qui échoue à cette vérification liste précisément
  les sources bloquantes — jamais d'échec silencieux ni de donnée privée
  fuitée dans l'artefact.

## 4. Hors périmètre v1

- Données privées/RLS (seuls les items publiquement partagés sont
  exportables).
- Écritures en mode Statique ; écritures en mode Autoporté (mini-serveur
  read-only pour commencer).
- Rafraîchissement/synchronisation automatique de l'instantané après export
  (ré-export manuel uniquement).
- Auto-déploiement CI/CD de l'app exportée (l'utilisateur récupère un artefact
  et le déploie lui-même).
- Hébergement par GeoStudio des apps exportées (c'est l'utilisateur qui
  s'auto-héberge ailleurs — cf. SP-Deploy pour l'hébergement de la plateforme
  elle-même, sujet distinct).
- 3D (`Tile3DLayer`) et impression (Playwright worker) dans les artefacts
  exportés — ces widgets restent hors périmètre analytique et n'ont pas de
  scénario d'export figé évident ; à traiter si demandé.

## 5. Validation & tests

Un test E2E par mode, chacun vérifié **réellement en conditions**, pas
asséré :

1. **Statique** : bundle exporté servi par un simple serveur HTTP statique,
   sans aucune instance GeoStudio derrière — l'app se charge, les données
   affichées correspondent à l'instantané, le cross-filter fonctionne, toute
   action d'écriture est visiblement désactivée.
2. **Connecté** : bundle exporté pointé sur un cœur GeoStudio réel (test) —
   les données affichées sont à jour côté cœur ; un item non partagé
   publiquement bloque l'export avec le message attendu.
3. **Autoporté** : conteneur démarré à froid (image + volumes vierges) — le
   mini-serveur répond, sert l'instantané GeoParquet via DuckDB, l'app se
   charge sans Postgres/Keycloak/MinIO dans le compose.
4. **Non-régression** : les suites cœur/shell/E2E existantes restent vertes
   (le mécanisme d'export est additif, ne modifie pas `AppRenderer` ni les
   `ItemClient` existants côté instance GeoStudio normale).

## 6. Questions ouvertes (à trancher en plan ou en session dédiée)

- Format exact de l'artefact Connecté/Statique (zip téléchargeable ? dépôt Git
  généré ? les deux ?).
- Où vit le code du mini-serveur Autoporté : sous-ensemble du cœur existant
  (`core/app/features`, `core/app/analytics`) packagé séparément, ou service
  neuf dédié à l'export — impact sur la dette de maintenance à trancher au
  moment du plan.
- Position exacte de SP-18 dans le calendrier réel (aucun autre SP n'en
  dépend ; peut être planifié dès SP-11 clos, à trancher au moment du plan).
