# GeoStudio Analytics Platform — brainstorm stratégique

> **Date : 2026-07-09 · Statut : brainstorm / proposition de vision — en attente de
> validation.** Ce document ne modifie **aucun** arbitrage de la
> [feuille de route](./2026-07-04-feuille-de-route-geostudio.md) (§8, A1–A27) : il
> s'appuie dessus, propose des extensions, et signale explicitement (⚠) tout point
> qui, s'il était retenu, exigerait une mise à jour de la feuille de route. Les
> chantiers proposés ici passeront chacun par le workflow spec → plan avant toute
> exécution.
>
> Question posée : faire évoluer GeoStudio d'un builder d'applications
> géospatiales vers une **plateforme complète de Data Visualization, Analytics et
> Decision Support** — capable de concurrencer simultanément ArcGIS Experience
> Builder, Grafana et Superset.

---

## Sommaire

1. [Analyse critique du projet actuel](#1-analyse-critique-du-projet-actuel)
2. [Benchmark : 11 sources d'inspiration](#2-benchmark)
3. [Vision cible : GeoStudio Analytics Platform](#3-vision-cible)
4. [Architecture fonctionnelle cible](#4-architecture-fonctionnelle-cible)
5. [Évolution du builder existant](#5-évolution-du-builder)
6. [Modules fonctionnels proposés](#6-modules-fonctionnels)
7. [Roadmap : articulation avec SP-1→13](#7-roadmap)
8. [Fonctionnalités différenciantes](#8-différenciateurs)
9. [Risques, garde-fous et critique honnête](#9-risques)
10. [Nouvelles questions à trancher](#10-questions)

---

## 1. Analyse critique du projet actuel

### 1.1 Ce que GeoStudio est aujourd'hui (état M1, 2026-07-09)

Une plateforme géospatiale open-source (Apache-2.0) : shell React (catalogue,
éditeur de cartes, builder no-code), cœur Python/FastAPI (items, partage,
publication, configs versionnées), stack conteneurisée à 10 services
(GeoNode-free depuis M1). Tout objet de plateforme est un **document déclaratif
schématisé** rendu par un **runtime unique** `AppRenderer(config, mode)` — c'est
le choix structurant qui rend la suite de ce document possible.

### 1.2 Ce que le builder couvre déjà

Inventaire factuel (code `shell/src/builder/`) :

| Capacité | État | Détail |
|---|---|---|
| Widgets | ✅ 11 types | text, image, button, list, table, indicator, **chart**, map, filter, nav, counter (exemple SDK) |
| Dataviz | ✅ solide pour un v0 | **10 types ECharts** (bar, line, area, scatter, pie, doughnut, radar, heatmap, gauge, boxplot) + échappatoire « option ECharts avancée » deep-mergée ; KPI `indicator` (count/sum) ; table triée/paginée |
| Data sources | ✅ 3 types | `features` (pg_featureserv), `statistics` (agrégation **côté client** : count/sum/avg/min/max, groupBy, pivot `split`, multi-mesures), `static` |
| Interactions | ✅ embryon sain | bus événements→actions (`ActionBus`) : list.itemSelected→map.flyTo/highlight, filter.changed→setFilter, variables comme cibles (`var:{id}`) |
| Variables | ✅ minimal | globales, **string uniquement**, non persistées |
| Bindings | ⚠ très limités | `{{champ}}`/`{{var:nom}}` **dans le seul widget texte** |
| Pages, thèmes, breakpoints | ✅ | grille 12 colonnes, overrides lg/md/sm, thème CSS variables (clair uniquement) |
| Modes | ✅ | edit/preview/runtime, un seul renderer |
| Configs | ✅ | versionnées + rollback côté cœur |

### 1.3 Limites actuelles — le diagnostic franc

Côté **analyse de données, reporting, BI et visualisation**, le produit est un
*viewer* élégant, pas un outil d'analyse :

1. **Tout est en lecture seule** (les formulaires arrivent en SP-4) et **figé au
   fetch** : aucun rafraîchissement automatique, aucun temps réel, aucune notion
   de fenêtre temporelle. Un « dashboard » GeoStudio est une photographie.
2. **L'agrégation se fait dans le navigateur** sur le GeoJSON téléchargé :
   plafond réel de quelques dizaines de milliers de lignes ; aucune jointure,
   aucun calcul dérivé, aucun langage de requête. Le widget graphique meurt là où
   la BI commence.
3. **Pas de couche sémantique** : les sources de données sont privées à chaque
   app, non nommées, non réutilisables, sans métriques définies une fois pour
   toutes. Chaque dashboard redéfinit « le nombre d'incidents ouverts ».
4. **Pas d'interactions analytiques** : pas de cross-filtering (le `setFilter`
   exige un câblage manuel source par source), pas de drill-down, pas de
   sélection comme contexte partagé, pas de filtre global (période, emprise,
   territoire).
5. **Aucune sortie** : pas d'export CSV/Excel, pas de PDF, pas de rapport
   planifié, pas d'alerte. Un dashboard qui ne sort pas de l'écran ne pilote
   rien.
6. **La carte du builder est pauvre** : le widget `map` ne consomme qu'une
   source `features` et n'expose pas le multi-couches de l'éditeur de carte —
   alors que la carte devrait être *le* widget différenciant.

### 1.4 Les atouts structurels pour pivoter

Le diagnostic serait accablant s'il ne fallait pas le lire à la lumière de ce qui
est **déjà arbitré et planifié** — la feuille de route contient, sans le nommer
ainsi, 70 % des fondations d'une plateforme analytique :

- **SP-11 (lakehouse)** : CDC PostGIS→GeoParquet, **DuckDB dans le cœur**, API
  d'agrégation structurée (A19) qui « remplace l'agrégation client actuelle » —
  c'est le moteur de requêtes ; critère d'acceptation : 1 M de lignes agrégées
  en < 2 s.
- **SP-5 (CEL)** : expressions client+serveur — c'est le langage des mesures,
  bindings, filtres et conditions.
- **SP-3 (collections + introspection de schéma)** : la matière première des
  requêtes visuelles et de la suggestion de visualisations.
- **SP-6 (jobs procrastinate)** : la planification des rapports et des alertes.
- **SP-13 (Playwright en worker)** : le rendu PDF/PNG WYSIWYG — le moteur de
  reporting.
- **SP-2/SP-7 (MCP)** : la génération de dashboards par IA, qu'aucun des 11
  concurrents étudiés ne possède nativement.
- **ECharts** : sankey, treemap, sunburst, funnel, candlestick, graph… sont déjà
  dans la dépendance — les « nouveaux » types de graphiques sont surtout du
  travail de config, pas d'intégration.

**Conclusion critique** : le fossé n'est pas technologique, il est *conceptuel*.
Il manque trois abstractions (Dataset, contexte analytique partagé, sortie
planifiée) et une couche d'UX analytique par-dessus des briques déjà décidées.
C'est une excellente nouvelle : l'évolution proposée ici est un **prolongement**
de la feuille de route, pas une bifurcation.

---

## 2. Benchmark

<a name="2-benchmark"></a>
Onze produits, trois familles : observabilité (Grafana, Kibana), BI (Superset,
Metabase, Power BI, Tableau, Redash), app builders (Retool, Appsmith, ArcGIS
Experience Builder, ArcGIS Dashboards). Pour chacun : concepts pertinents, valeur,
adaptation au contexte SIG de GeoStudio.

### 2.1 Grafana — le contexte temporel et l'alerte

| Concept | Valeur | Adaptation GeoStudio |
|---|---|---|
| **Time-range picker global** : une fenêtre temporelle unique pilote tous les panels | Un seul geste = tout le dashboard se recontextualise | Généraliser en **double contexte global : temps × emprise**. « Ce que je vois sur la carte » et « la période choisie » filtrent tous les widgets — le *spatial-range picker* n'existe nulle part ailleurs, c'est notre time-picker à nous |
| **Variables de dashboard (`$var`)** : listes déroulantes alimentées par requête, interpolées partout | Un dashboard = un template réutilisable (par commune, par réseau…) | Étendre nos variables : **typées**, alimentées par un dataset (`options from dataset`), interpolées via CEL dans filtres et titres. Un dashboard « incidents » devient instanciable par territoire |
| **Alerting** : règles d'évaluation périodique sur requête, seuils, canaux de notification | Le dashboard passe de « regarder » à « être prévenu » | Règles d'alerte = objet déclaratif du cœur, évaluées en job procrastinate sur l'API analytique ; ajout du **prédicat spatial** (entité dans zone, sortie de périmètre — géofencing léger, aligné vision §7) |
| **Auto-refresh par panel/dashboard** | Cockpit vivant | Trivial chez nous : `refetchInterval` TanStack Query piloté par la config — quick win absolu |
| **Provisioning as code** (dashboards JSON en Git) | GitOps, revue, CI | Déjà notre nature (configs déclaratives versionnées) — à *revendiquer* dans le discours produit |
| **Transformations chaînées côté client** (join, calc, filter sur les résultats) | Ajustements légers sans toucher la source | Pipeline de transformations du Dataset (§4.3), exécuté serveur (DuckDB) pour le lourd, client pour le cosmétique |

À ne **pas** copier : le modèle « un panel = une requête vers une TSDB » (nous
avons des entités géo-attributaires, pas que des séries), et la course aux
datasources d'infrastructure (Prometheus, Loki…) — l'observabilité *de*
GeoStudio est réglée par SP-10/A26 ; GeoStudio vend de la supervision *métier*,
pas de la supervision de serveurs.

### 2.2 Apache Superset — la couche sémantique

| Concept | Valeur | Adaptation |
|---|---|---|
| **Dataset = table + colonnes calculées + métriques nommées** | La métrique est définie **une fois**, réutilisée par tous les charts ; le non-technicien manipule des noms métier | **Le** concept central à adopter : Dataset objet de plateforme (item), schéma introspecté (SP-3), métriques en CEL (SP-5), servi par l'API analytique (SP-11/A19) |
| **Découplage chart ↔ dataset** : le chart référence un dataset, pas une table | Gouvernance : changer la source ne casse pas 40 dashboards | Nos `DataSource` par app deviennent des **références** à des Datasets partagés (avec datasets inline conservés pour le jetable) |
| **Cross-filters natifs** : cliquer sur une barre filtre le dashboard | L'exploration sans configuration | Contexte de sélection partagé (§5.4) : émission automatique `dimension=valeur`, opt-out par widget — remplace le câblage manuel actuel |
| **SQL Lab** : IDE SQL avec historique, résultats explorables, « save as dataset » | Le pont analystes | C'est exactement l'endpoint SQL read-only du rôle analyste (A19) — il lui manque juste son UI. « Enregistrer comme dataset » ferme la boucle analyste→métier |
| **Row-level security sur les datasets** | Multi-organisation | Convergence avec RLS SP-3 + `can()` : les permissions du dataset suivent les collections sources |

Ironie assumée : Superset est sorti du produit (Q12, « doublon du builder ») —
la bonne lecture n'est pas « pas de BI », c'est « la BI *dans* le builder, un
seul runtime ». Ce document est l'exécution de cette phrase.

### 2.3 Metabase — l'analytique pour non-techniciens

| Concept | Valeur | Adaptation |
|---|---|---|
| **Question builder visuel** (« Filtrer → Résumer → Grouper par ») en langage humain | Un agent de mairie construit sa propre analyse | UI « requête visuelle » qui **compile vers l'API analytique structurée** (A19) — jamais de SQL généré côté client, la surface sûre est déjà arbitrée |
| **Drill-through automatique** : clic sur un point → zoom, voir les enregistrements, décomposer | Zéro configuration pour explorer | Drill par défaut sur tout widget agrégé : « voir les entités » (table + carte des lignes sous-jacentes) — le drill-down *cartographique* (région→commune→adresse) est notre version différenciante |
| **Models** (datasets curés avec descriptions de colonnes) | Vocabulaire métier partagé | Métadonnées de dataset (libellés, descriptions, formats) — utile aussi au MCP : un agent IA comprend « chiffre d'affaires » mieux que `mt_rev_eur` |
| **X-rays** (analyses automatiques d'une table) | Time-to-insight nul | Version GeoStudio : « **auto-dashboard** » — depuis le schéma d'une collection, générer un dashboard de découverte (carte + distributions + top N). Avec le MCP (SP-2) c'est un prompt, pas un moteur à écrire |

### 2.4 Power BI — le modèle de données et l'interaction par défaut

| Concept | Valeur | Adaptation |
|---|---|---|
| **Modèle relationnel** (relations entre tables, propagation des filtres) | Analyses multi-tables sans écrire de jointures | Version minimale : **relations déclarées entre collections** (clé étrangère logique) exploitées par le pipeline de jointure DuckDB — pas de moteur DAX, CEL + agrégations suffisent à 90 % des cas collectivités |
| **Mesures (DAX)** définies dans le modèle | Logique métier centralisée | Métriques CEL du Dataset (déjà couvert §2.2) — refuser la complexité DAX (time intelligence exotique) : hors persona |
| **Cross-highlight par défaut** : toute sélection filtre/surligne le reste | L'interactivité n'est pas une option à câbler | Idem Superset — sélection = contexte global, opt-out |
| **Bookmarks / vues nommées** | États de dashboard partageables (« la situation du 15 mars ») | État analytique (filtres+sélection+emprise+période) **sérialisable dans l'URL** et sauvegardable — précieux pour le decision support (partager *une situation*, pas un dashboard) |

À ne pas copier : le fossé desktop/service, le modèle propriétaire fermé —
l'anti-thèse de « le format est l'API ».

### 2.5 Tableau — l'encodage visuel et les data stories

| Concept | Valeur | Adaptation |
|---|---|---|
| **Encodage par étagères** : champ → axe/couleur/taille/forme | La bonne abstraction : on mappe des *champs* sur des *canaux visuels*, le type de chart en découle | Refondre la config du widget chart autour de `encodings: {x, y, color, size}` plutôt que « type d'abord » ; le même modèle pilote la **symbologie data-driven de la carte** (champ→couleur/taille des entités) — un seul vocabulaire pour charts et cartes |
| **Show Me** (suggestion de viz selon les champs choisis) | Guidage des non-experts | L'introspection SP-3 donne les types de champs → suggestions déterministes (dimension+mesure=barres, 2 mesures=scatter, géométrie=carte, date+mesure=ligne) + variante MCP en langage naturel |
| **Story points** | La narration comme livrable | **Data stories = un `kind` de plus du même AppConfig** : séquence de pages avec états analytiques figés + scrollytelling cartographique (la carte vole d'une emprise à l'autre au fil du récit). StoryMaps + BI dans un seul runtime — personne n'a ça |
| **LOD expressions** | Agrégations à grain contrôlé | Différé — le pipeline (agrégation à deux niveaux) couvre les cas simples ; noter comme extension CEL future |

### 2.6 Kibana — la recherche comme porte d'entrée

| Concept | Valeur | Adaptation |
|---|---|---|
| **Search-first** : une barre de recherche/filtre pilote tout | L'exploration commence par une question, pas par une config | Barre de filtre globale du dashboard (KQL-like simplifié + champs proposés depuis le schéma) ; en catalogue, c'est pgvector (SP-7) |
| **Lens** (drag & drop avec suggestions) | Baisse la marche d'entrée | Convergent avec Show Me (§2.5) — une seule implémentation |
| **Live tail / streaming** | Supervision opérationnelle | Palier 0 vision §7 (SSE) quand Q10 sera tranchée — voir §4.5 |

### 2.7 ArcGIS Dashboards — le dashboard *cartocentrique*

| Concept | Valeur | Adaptation |
|---|---|---|
| **La carte est la source des interactions** : sélection/emprise pilotent indicateurs et listes | Le réflexe SIG : « montre-moi les stats de ce que je vois » | **Statistiques sur l'emprise courante** : l'extent de la carte est une variable de contexte globale que tout dataset peut consommer (`filter: within(extent)`) — poussé par l'API analytique avec prédicat spatial. Notre `map.extentChanged` existe déjà ; il faut le brancher au contexte global au lieu du câblage manuel |
| **Indicateurs riches** (valeur, référence, tendance, icône, seuils colorés) | Le langage des salles de crise | Upgrade du widget `indicator` : comparaison à une référence (période précédente, objectif), sparkline, format conditionnel CEL |
| **Sélecteurs groupés** (catégorie, plage numérique, date) | Filtres lisibles par des élus | Famille de widgets filtres typés (select/date-range/slider) alimentés par dataset, écrivant dans le contexte global |

### 2.8 ArcGIS Experience Builder — le concurrent frontal

| Concept | Valeur | Adaptation |
|---|---|---|
| **Message/actions framework** (framework-level, records/extent/selection comme messages typés) | Interactions déclaratives génériques | Notre ActionBus + le contexte partagé (§5.4) en sont l'équivalent — avec payloads **typés** (record, feature, extent, plage) pour que le câblage se propose tout seul |
| **Pages, fenêtres, layouts adaptatifs** | Vraies applications, pas que des dashboards | Nous avons pages+breakpoints ; manquent fenêtres modales/tiroirs (widgets conteneurs) — utile aux formulaires SP-4 |
| **Modes express/complet** | Progressivité builder | Templates + panneau simplifié ; à garder en tête, pas prioritaire |

Ses faiblesses = nos angles d'attaque : framework React figé (notre SDK WC, A10),
fragmentation Esri (Dashboards + ExB + StoryMaps + Insights — notre runtime
unique les couvre tous), pas de BI réelle (Insights est un produit à part,
mourant), coût des licences, pas d'IA opérante. **La cible commerciale est
précise : la collectivité qui paie ArcGIS Online et n'utilise que 10 % d'ExB.**

### 2.9 Retool — l'app data-centrique

| Concept | Valeur | Adaptation |
|---|---|---|
| **Tout est une query nommée** (SQL/REST), les composants s'y lient | Le graphe de dépendances data→UI est explicite et inspectable | Renforce le choix Dataset : dans l'inspecteur du builder, « qui consomme quoi » devient navigable ; les datasets inline gardent la légèreté Retool |
| **`{{ }}` partout** | Expressivité maximale | Bindings CEL **sur toutes les props** de tous les widgets (aujourd'hui : seul le widget texte) — SP-5 le prévoit à moitié (`visibleWhen`, champs calculés) ; le généraliser |
| **Event handlers composés** (succès/échec, chaînes, conditions) | Apps réelles | SP-5 « actions composées » — y ajouter les déclencheurs data (`onDataLoaded`, `onError`) et timer |
| **State + optimistic updates** | UX d'app moderne | Variables typées + invalidation TanStack (SP-4 la prévoit) |

À refuser : « du JS partout » — non sandboxable, non analysable, contraire à A8
(CEL). C'est un *choix*, pas un retard : nos configs restent générables et
validables par IA.

### 2.10 Appsmith — leçon de prudence

Mêmes concepts que Retool (bindings moustache, queries, widgets). Leçon
principale : le **binding universel** est ce qui fait qu'un builder « prend ».
Leçon négative : sans couche sémantique ni gouvernance, un builder low-code
produit un cimetière d'apps ; nos Datasets partagés + catalogue + permissions
sont l'antidote.

### 2.11 Redash — la simplicité qui gagne

| Concept | Valeur | Adaptation |
|---|---|---|
| **Requête sauvegardée = objet partageable** avec planification de rafraîchissement | La plus petite unité analytique utile | Le Dataset a une `refreshPolicy` (à la demande / planifié via procrastinate / continu plus tard) ; résultats matérialisés en cache |
| **Alertes sur résultat de requête** (seuil → notification) | Decision support minimal viable | Même mécanique que §2.1 alerting — Redash prouve qu'une v1 simple (une condition, un canal email/webhook) suffit largement |
| **Snapshots de viz embarquables** | Diffusion légère | Rejoint l'embed (SDK WC, SP-8) et l'export image (SP-13) |

### 2.12 Synthèse du benchmark — les 8 concepts à retenir

1. **Dataset avec métriques nommées** (Superset/Metabase) — la couche sémantique.
2. **Contexte analytique global** : temps × **emprise** × filtres × sélection
   (Grafana + ArcGIS Dashboards) — notre fusion originale.
3. **Cross-filter et drill par défaut**, opt-out (Power BI/Superset/Metabase).
4. **Bindings CEL universels** (Retool/Appsmith, en sandboxé).
5. **Encodages visuels champ→canal** unifiés charts+carte (Tableau).
6. **Requête visuelle compilant vers l'API structurée** (Metabase, sur A19).
7. **Alertes + rapports planifiés** comme objets déclaratifs (Grafana/Redash).
8. **Suggestion de viz depuis le schéma** (Tableau Show Me/Kibana Lens),
   dopée MCP.

---

## 3. Vision cible

<a name="3-vision-cible"></a>

### 3.1 Énoncé

> **GeoStudio Analytics Platform : la plateforme open-source où la donnée — 
> géospatiale ou non — devient application, analyse et décision, dans un seul
> runtime déclaratif, opérable par les humains comme par les agents IA.**

Trois verbes, un runtime :

- **Voir** — cartes, dashboards, dataviz, stories : la donnée rendue lisible.
- **Comprendre** — requêtes visuelles, agrégations lakehouse, analyse spatiale,
  drill : la donnée interrogeable par des non-techniciens.
- **Agir** — formulaires, alertes, rapports diffusés, cockpits temps réel :
  la donnée qui déclenche des décisions.

La thèse différenciante : **la géographie n'est pas un type de chart, c'est une
dimension analytique**. Chez Grafana/Superset, la carte est un panel exotique ;
chez Esri, la BI est un produit annexe. GeoStudio traite l'emprise comme Grafana
traite le temps : un contexte global qui filtre tout. « Montre-moi les
indicateurs de ce que je vois » est notre geste fondateur.

### 3.2 Ce que la plateforme permet de construire

Tous ces archétypes sont **le même `AppConfig`** (règle d'architecture n° 3 —
un seul runtime), différenciés par templates et modes :

| Archétype | Description | Briques dominantes |
|---|---|---|
| Application cartographique | carte multi-couches + navigation + fiches | MapConfig, widgets map/list |
| Tableau de bord décisionnel | KPI + charts + carte, contexte global, drill | Datasets, cross-filter, indicateurs riches |
| Cockpit temps réel | supervision live, auto-refresh/flux, alertes visibles | refresh, palier 0 §7, alerting |
| Outil de supervision | états d'équipements, seuils, historique | Datasets temporels, format conditionnel |
| Portail métier | pages, navigation, contenus mixtes, droits par groupe | pages, thèmes, partage SP-1c |
| Application d'analyse spatiale | isochrones, zones tampon, croisements | pipeline spatial DuckDB (§4.3) |
| Rapport interactif | document paginé exportable PDF, planifiable | PrintLayout SP-13, jobs |
| Data story | narration scrollée, états analytiques figés, carte animée | pages séquencées, bookmarks d'état |
| App low-code/no-code métier | formulaires + CRUD + logique CEL | SP-4/SP-5 |

### 3.3 Personas

Extension de la hiérarchie de la vision (§1) — les huit demandés, rattachés aux
cinq canoniques :

| Persona | Rattachement vision | Ce qu'il attend de l'Analytics Platform |
|---|---|---|
| **Utilisateur métier non technique** | agent métier (n° 1) | consulter un dashboard, filtrer, recevoir le rapport PDF hebdo — sans formation |
| **Décideur / élu** | agent métier (n° 1) | KPI fiables, situations partageables (bookmarks), alertes ; mobile |
| **Data analyst** | analyste (n° 2) | SQL Lab (A19), datasets curés, exploration lakehouse, export |
| **Analyste SIG / géomaticien** | géomaticien (n° 3) | analyse spatiale sans code, symbologie data-driven, qualité des référentiels |
| **Exploitant de réseaux** (eau, énergie, telecom) | agent métier + terrain | cockpit de supervision, géofencing, historique d'événements, formulaires d'intervention |
| **Gestionnaire d'infrastructures** (routes, bâtiments) | agent métier | inventaire cartographié, indicateurs d'état, rapports réglementaires planifiés |
| **Services environnementaux** | analyste + métier | séries temporelles de capteurs, seuils réglementaires, croisements spatiaux (zonages), open-data DCAT (SP-12) |
| **Collectivité** (l'organisation) | — (cliente type) | tout ce qui précède, self-hosted, coût maîtrisé, conformité open-data, sortie d'Esri progressive (connecteur ArcGIS, §4.2) |

Le développeur (n° 4, SDK WC) et l'agent de terrain (n° 5, offline — Q11
ouverte) restent servis par la feuille de route existante.

---

## 4. Architecture fonctionnelle cible

<a name="4-architecture-fonctionnelle-cible"></a>

### 4.1 Le schéma conceptuel

```
  DATA SOURCES              DATASETS                TRANSFORMATIONS
  (connexions)              (couche sémantique)     (pipeline déclaratif)
┌─────────────────┐      ┌──────────────────┐     ┌──────────────────────┐
│ PostGIS (chaud) │      │ objet de          │     │ filter (attributaire │
│ Lakehouse       │      │ plateforme :      │     │   + spatial + CEL)   │
│  GeoParquet/S3  ├─────▶│ · source ref      ├────▶│ aggregate (groupBy,  │
│ Fichiers        │      │ · pipeline        │     │   mesures)           │
│  CSV/GeoJSON/   │      │ · schéma inféré   │     │ join (relation       │
│  Parquet        │      │ · métriques CEL   │     │   déclarée / clé)    │
│ APIs REST       │      │ · libellés métier │     │ derive (colonne CEL) │
│ ArcGIS Feature  │      │ · refreshPolicy   │     │ pivot                │
│  Services       │      │ · permissions     │     │ spatial (buffer,     │
│ OGC (WFS/STAC…) │      │   (can())         │     │   within, intersect, │
└─────────────────┘      └────────┬─────────┘     │   centroid…)         │
     référencer                    │                └──────────┬───────────┘
     ou copier (A23)               │   exécution serveur : API analytique
                                   │   (A19) → DuckDB (froid) / PostGIS (chaud)
                                   ▼
                         ┌──────────────────┐
                         │     WIDGETS      │  binding = dataset + encodings
                         │ chart·map·kpi·   │  (x, y, color, size…) + props
                         │ table·filter·    │  CEL ; events typés (record,
                         │ form·…           │  extent, plage, sélection)
                         └────────┬─────────┘
                                  ▼
                         ┌──────────────────┐  contexte analytique global :
                         │   DASHBOARDS     │  temps × emprise × filtres ×
                         │ (layout + contexte│  sélection ; cross-filter par
                         │  + interactions)  │  défaut ; bookmarks d'état
                         └────────┬─────────┘
                                  ▼
                         ┌──────────────────┐  pages, navigation, formulaires,
                         │  APPLICATIONS    │  thèmes, droits, modes
                         │ (AppConfig, un    │  edit/preview/runtime ;
                         │  seul runtime)    │  + sorties : PDF, Excel,
                         └──────────────────┘  alertes, embed WC, MCP
```

Chaque étage est un **document déclaratif schématisé** (règle n° 2) : sources,
datasets, transformations, alertes, layouts d'impression — tout est config,
donc versionnable, auditée, générable par IA via MCP.

### 4.2 Couche Données — connecteurs

Principe directeur hérité de la vision : **« référencer ≠ copier »** (A23). Deux
chemins par connecteur : *référencement* (requêtable en place) ou *copie*
(pipeline d'ingestion SP-6 → PostGIS/lakehouse).

| Connecteur | Statut feuille de route | Proposition |
|---|---|---|
| PostgreSQL/PostGIS | ✅ natif (chaud) | inchangé — collections SP-3 |
| GeoParquet / Parquet sur S3 | ✅ SP-11 (froid, CDC) | étendre : **enregistrer un Parquet externe** (déjà sur un S3 du client) comme dataset sans ingestion — DuckDB httpfs le lit en place |
| CSV / GeoJSON / GPKG / SHP | ✅ SP-6 (ingestion) | inchangé + CSV « fichier joint au dataset » pour le jetable |
| DuckDB | ✅ SP-11 (moteur interne) | ce n'est pas un connecteur mais **le** moteur fédérateur : c'est lui qui lit Parquet externes, CSV, et attache PostGIS |
| APIs REST / GeoJSON distant | ❌ absent | nouveau type de source `http` : URL + auth + mapping JSON→records + cache TTL ; version fichiers plats d'abord (JSON/GeoJSON), pagination ensuite |
| **ArcGIS Feature Services** | ❌ absent | connecteur de **référencement** (query GeoJSON f=geojson) + **copie** (extraction paginée → ingestion). Stratégique : c'est la donnée existante de toutes les collectivités Esri — le pont de sortie. À ranger dans la famille moissonnage SP-12 (5ᵉ connecteur) ⚠ extension d'A22 |
| WMS/WFS, STAC, CSW, CKAN | ✅ SP-12 (moissonnage) | inchangé ; les items moissonnés deviennent sources de datasets |
| SQL externes (MySQL, SQL Server…) | ❌ absent | **différé volontairement** : surface d'exploitation énorme (drivers, credentials, réseau) pour un gain faible chez nos personas v1. DuckDB (attach MySQL/Postgres) rend ça peu coûteux le jour venu — trigger : demande réelle |
| Iceberg | différé (A17) | **maintenu différé** — réévalué avec le versioning de données, comme arbitré |

### 4.3 Couche Analyse

Le contrat est fixé par **A19** : *API structurée pour les widgets, SQL read-only
pour le rôle analyste*. Tout ce qui suit compile vers cette API — le client ne
fabrique jamais de SQL.

- **Pipeline de transformations** (du Dataset) : `filter` (prédicats
  attributaires + **spatiaux** : `within`, `intersects`, `dwithin`, emprise
  courante ; conditions CEL), `aggregate` (groupBy multi-champs + mesures),
  `join` (sur relation déclarée entre collections, ou clé explicite ; left/inner),
  `derive` (colonnes calculées CEL), `pivot`. Exécution : DuckDB sur le froid,
  PostGIS sur le chaud, choix automatique par fraîcheur demandée.
- **Analyse spatiale no-code** : opérations packagées comme des transformations —
  buffer, centroïde, intersection/découpage entre deux collections, comptage de
  points dans polygones, agrégation H3 (hexbins statistiques, pas seulement
  visuelles comme le deck.gl actuel). DuckDB spatial + PostGIS couvrent tout ;
  l'UX est « ajouter une étape », pas « écrire du SQL ».
- **Requête visuelle** (Metabase-like) : Filtrer → Joindre → Résumer → Trier,
  proposée depuis le schéma introspecté (SP-3). Sortie : un Dataset.
- **Filtres dynamiques** : toute étape peut référencer le contexte
  (`vars.commune`, `context.extent`, `context.timeRange`, `context.selection`) —
  c'est ce qui rend les dashboards vivants.
- **SQL Lab** (rôle analyste, A19) : éditeur, historique, EXPLAIN, résultats
  explorables, **« enregistrer comme dataset »** — la passerelle
  analyste→métier.

### 4.4 Couche Dataviz

- **Charts ECharts** — extension du widget existant (le moteur est déjà là) :
  ajouter sankey, treemap, sunburst, funnel, waterfall (bar stylé),
  **histogramme** (binning fait serveur par l'API analytique, pas dans le
  navigateur), combo bar+ligne, double axe. Refonte de la config autour des
  `encodings` (§2.5) avec compat ascendante.
- **Séries temporelles** : type ligne/aire dopé — plage temporelle du contexte
  global, comparaison de périodes (N vs N-1), annotations (événements),
  downsampling serveur (LTTB) pour les grosses séries.
- **KPI cards** : valeur + delta vs référence + sparkline + seuils colorés CEL
  + icône. La brique n° 1 du décideur.
- **Jauges** : existant (gauge ECharts) — enrichir de seuils/zones déclaratifs.
- **Heatmaps** : matricielle (ECharts, existant) et **spatiale** (deck.gl,
  existant) — les brancher sur les datasets agrégés serveur.
- **Diagrammes croisés / tables pivot** : widget table étendu (pivot serveur via
  l'API, sous-totaux, format conditionnel, colonnes calculées) — le widget le
  plus demandé des utilisateurs Excel.
- **Carte analytique** : le widget map rejoint l'éditeur de carte (multi-couches
  MapConfig complet) + symbologie pilotée par dataset (choroplèthe, symboles
  proportionnels, catégories) via les mêmes `encodings` que les charts.

Tout widget expose : titre/description, source dataset, état
loading/empty/error décent, menu « explorer » (drill, voir les données, export
CSV/PNG du widget).

### 4.5 Temps réel

Q10 est **ouverte** ; la vision (§7) a déjà l'échelle progressive. Position de
ce brainstorm — deux crans très asymétriques en coût :

1. **Cran 0 : le cockpit qui respire (quasi gratuit, faire tôt)** —
   `refreshPolicy` par dataset (intervalle), transitions douces des widgets,
   horodatage « données à jour à HH:MM », pause quand l'onglet est masqué.
   Couvre 80 % de la « supervision » réelle des collectivités (la fraîcheur
   minute suffit pour des capteurs de crue ou une flotte de bennes).
2. **Cran 1 : le vrai flux (palier 0 vision §7)** — ingestion HTTP/MQTT →
   PostGIS → **SSE** vers le shell (SSE plutôt que WebSocket : unidirectionnel,
   passe les proxies, suffit) ; couches live sur la carte ; déclencheurs
   d'événements data dans le bus. À lancer **seulement sur besoin concret**
   (Q10) — c'est un SP entier.

Le **monitoring métier** (seuils, alertes, journal d'événements) ne dépend pas
du cran 1 : les alertes évaluées en job (§4.6) fonctionnent dès le cran 0.

### 4.6 Reporting & diffusion

Assemblage de briques déjà arbitrées + deux objets nouveaux :

- **Génération PDF** : SP-13 (Playwright worker + `PrintLayout` déclaratif) —
  étendu des cartes aux dashboards paginés (en-tête/pied, sauts de page par
  section, table des matières). Le rendu WYSIWYG du vrai runtime est un
  avantage décisif sur les moteurs de template.
- **Exports Excel/CSV** : côté serveur par l'API analytique (DuckDB
  `COPY TO xlsx/csv` — trivial), par widget (les données visibles) ou par
  dataset ; respecte les permissions `can()`.
- **Rapports planifiés** : objet `ReportSchedule` (config : cible app/page +
  état analytique figé + format + cron + destinataires) exécuté par
  procrastinate → S3 présigné → email/webhook. « Le PDF du lundi matin dans la
  boîte du DGS » est l'argument de vente n° 1 en collectivité.
- **Alertes** : objet `AlertRule` (dataset + condition CEL + fréquence + canaux
  email/webhook, gabarit de message) — journalisées (audit), avec état
  ok/firing et historique. Prédicats spatiaux inclus (géofencing léger).
- **Diffusion** : liens publics (publication SP-1c existante), embed de widgets
  (SDK WC SP-8), et abonnements aux rapports.

### 4.7 Transverses

- **Sécurité** : rien de neuf à inventer — datasets et sorties passent par
  `can()` ; le SQL Lab reste enfermé dans A19 (vues autorisées, quotas,
  timeout) ; les rapports planifiés s'exécutent **avec les droits de leur
  propriétaire**, jamais plus.
- **Audit** : chaque exécution de requête analytique, export, envoi de rapport,
  déclenchement d'alerte → `audit_log` (dont `actor_kind=agent`).
- **MCP / IA** : chaque objet nouveau (dataset, alerte, rapport, story) est une
  config schématisée → exposée au MCP quasi gratuitement. Outils cibles :
  `create_dataset`, `run_analytics_query`, `create_dashboard_from_prompt`,
  `explain_dataset`. C'est le multiplicateur que n'a aucun des 11 benchmarkés.
- **Observabilité** : les requêtes analytiques s'instrumentent OTel (SP-10) ;
  SLO additionnel : P95 requête analytique < 2 s (déjà dans les critères SP-11).

---

## 5. Évolution du builder

<a name="5-évolution-du-builder"></a>
Concret, adossé au code actuel (`shell/src/builder/`).

### 5.1 Nouveaux widgets

| Widget | Base existante | Effort dominant |
|---|---|---|
| KPI card riche | `indicator.tsx` | UI + delta/sparkline ; les données viennent de l'API analytique |
| Pivot / tableau croisé | `data.tsx` (table) | config pivot + rendu ; agrégation serveur |
| Sankey, treemap, sunburst, funnel, histogramme | `chart.tsx`/`chartOption.ts` | mapping config→option ECharts (pattern établi, testable) |
| Séries temporelles avancées | `chart.tsx` | plage temporelle contextuelle, comparaison de périodes |
| Filtres typés (select, date-range, slider) | `filter.tsx` | options depuis dataset ; écrit dans le contexte global |
| Carte analytique | `mapWidget.tsx` + `map/MapView.tsx` | brancher le MapConfig complet + symbologie data-driven |
| Conteneurs (onglets, modale, tiroir) | `GridCanvas.tsx` | layout imbriqué — servira aussi les formulaires SP-4 |
| Formulaire | — | **c'est SP-4**, inchangé |

### 5.2 Nouveau modèle de données de la config

Évolution de `api/types.ts` (compat : voir §5.7) :

```ts
// AVANT : DataSource privée à l'app, requête ad hoc, agrégation client
type DataSource = { id; type: "features"|"static"|"statistics"; service; layer; query }

// APRÈS : le Dataset, inline OU référence à un dataset partagé (item du cœur)
type DatasetRef =
  | { kind: "shared"; datasetId: string }              // objet de plateforme
  | { kind: "inline"; source: SourceRef;               // privé à l'app
      pipeline: Transform[]; metrics?: Metric[];
      refresh?: { intervalSec?: number } }

type SourceRef =
  | { type: "collection"; id: string }                  // PostGIS chaud (SP-3)
  | { type: "lake"; path: string }                      // GeoParquet froid (SP-11)
  | { type: "http"; url: string; format: "json"|"geojson"|"csv"; auth?: … }
  | { type: "arcgis"; serviceUrl: string; layerId: number }
  | { type: "static"; records: unknown[] }

type Transform =
  | { op: "filter"; where: CelExpr | SpatialPredicate }
  | { op: "aggregate"; groupBy: string[]; measures: Measure[] }
  | { op: "join"; right: DatasetRef; on: JoinKey; how: "left"|"inner" }
  | { op: "derive"; columns: { name: string; expr: CelExpr }[] }
  | { op: "pivot"; … }
  | { op: "spatial"; fn: "buffer"|"centroid"|"intersect"|"countWithin"|…; … }

type Metric = { name; label?; agg: "count"|"sum"|"avg"|"min"|"max"|…; expr?: CelExpr; format? }
```

Le type `statistics` actuel devient un `pipeline: [aggregate]` — l'agrégation
**quitte le navigateur** pour l'API analytique (exactement ce que prévoit
SP-11 : « remplace l'agrégation client actuelle de queryDataSource »).

### 5.3 Gestion des datasets

- **Dataset partagé = item du cœur** (nouveau type d'item à côté de
  app/dashboard/map) : catalogué, cherchable (pgvector SP-7), partageable
  (groupes×rôles SP-1c), versionné comme les autres configs, audité. Le
  builder propose « promouvoir cette source en dataset partagé ».
- Métadonnées métier : libellés/descriptions de colonnes, formats, tags —
  consommées par l'UI **et** par le MCP.
- `refreshPolicy` : à la demande (défaut), intervalle (runtime), planifié
  (matérialisation en job, cache serveur).

### 5.4 Variables globales, contexte partagé, filtres croisés

Remplacement du modèle « variables string » par un **AppState** typé :

```ts
type AppState = {
  variables: Record<string, TypedValue>       // string|number|bool|date|record|list
  context: {
    timeRange?: { from; to }                   // le time-picker global
    extent?: BBox                              // l'emprise carte courante
    filters: FilterClause[]                    // filtres globaux (widgets filtres)
    selection?: { datasetId; keys: unknown[] } // sélection croisée
  }
}
```

- Tout dataset peut déclarer `respondsTo: ["timeRange","extent","filters","selection"]`
  (défaut : tout sauf extent) — le **cross-filtering devient le défaut**, le
  câblage manuel actuel (`filter.changed→setFilter`) reste possible pour les cas
  fins, et l'ActionBus existant transporte le tout.
- L'état analytique est **sérialisable dans l'URL** et sauvegardable en
  **bookmark** (vues nommées, partage de « situations »).
- Persistance légère : variables marquées `persist: "url" | "local" | "none"`.

### 5.5 Data bindings généralisés

Aujourd'hui : `{{champ}}`/`{{var:nom}}` dans le seul widget texte. Cible : toute
prop de tout widget accepte une expression CEL (`{ $expr: "…" }`) évaluée contre
`{ vars, context, data, record, user }` — mise en œuvre dans `WidgetHost` (un
seul point d'injection, déjà porteur du `WidgetContext`). C'est l'extension
naturelle de SP-5 (`visibleWhen` et champs calculés en sont des cas
particuliers). L'éditeur de props gagne un toggle « valeur fixe / expression »
par champ.

### 5.6 Moteur d'événements et moteur de requêtes

- **Événements** (extension ActionBus, pas remplacement) : payloads **typés**
  (record, feature, extent, plage, valeur) pour proposer le câblage
  automatiquement ; nouveaux déclencheurs : `data.loaded/error` (par dataset),
  `timer.tick`, `app.loaded`, `context.changed` ; actions composées avec
  conditions CEL = **SP-5 tel quel**.
- **Requêtes** : le « moteur » côté client est mince à dessein — il compose le
  JSON du pipeline + le contexte, l'envoie à l'API analytique (A19), met en
  cache (TanStack, clé = hash pipeline+contexte), déduplique et invalide après
  écriture (SP-4). Toute l'intelligence (planification, DuckDB vs PostGIS,
  limites) vit au serveur — le client reste bête et sûr.

### 5.7 Compatibilité

Les configs `version: 1` restent lisibles : migration automatique à l'ouverture
(`DataSource`→`DatasetRef inline`, `statistics`→pipeline `aggregate`, variables
→`TypedValue string`). Les 13 specs E2E existantes restent vertes — elles sont
le filet, comme pour la sortie de GeoNode.

---

## 6. Modules fonctionnels

<a name="6-modules-fonctionnels"></a>
Découpage en modules du cœur (monolithe modulaire, frontières lintées) et
chantiers shell :

| Module | Côté | Contenu | S'appuie sur |
|---|---|---|---|
| `datasets` | core | CRUD datasets partagés, schéma inféré, métriques, refreshPolicy, matérialisation | items, collections (SP-3), analytics |
| `analytics` | core | API structurée (pipeline→plan→DuckDB/PostGIS), SQL read-only analyste, exports CSV/xlsx, downsampling | **SP-11/A19** (c'est son extension directe) |
| `alerts` | core | AlertRule, évaluation en jobs, canaux email/webhook, journal | procrastinate (A5), analytics |
| `reports` | core | ReportSchedule, orchestration du worker Playwright, dépôt S3, envoi | SP-13, procrastinate |
| `connectors` | core | sources http/arcgis (référencement + copie), auth, cache | SP-6 (ingestion), SP-12 (moissonnage) |
| `realtime` (différé) | core | ingestion MQTT/HTTP, SSE, couches live | Q10, vision §7 palier 0 |
| Builder analytics UX | shell | datasets UI, requête visuelle, contexte global, cross-filter, bindings CEL, bookmarks | SP-5 (CEL), SP-3 (schémas) |
| Widgets v2 | shell | KPI riche, pivot, nouveaux charts, filtres typés, carte analytique, conteneurs | ECharts, MapView existants |
| MCP analytics | core | outils dataset/query/dashboard-from-prompt | SP-2/SP-7 |

---

## 7. Roadmap

<a name="7-roadmap"></a>
Principe : **ne pas toucher au chemin critique vers v0.1** (A27 figé : SP-2→9
puis OTel→Lakehouse→STAC→3D/print). L'analytics s'insère en trois vagues :

### Vague 0 — quick wins opportunistes (au fil de SP-4/SP-5, coût marginal)

- Auto-refresh par source (`refetchInterval` configuré) + horodatage de
  fraîcheur.
- Nouveaux types ECharts « gratuits » (sankey, treemap, funnel, histogramme
  client provisoire) dans `chartOption.ts`.
- KPI card enrichie (delta, seuils colorés — les seuils en CEL arrivent avec
  SP-5).
- Variables typées + bindings CEL sur toutes les props : **à intégrer à la spec
  SP-5** (c'en est le prolongement naturel ; ⚠ à acter dans la spec SP-5, pas un
  changement d'arbitrage).

### Vague 1 — le pivot analytique (SP-11 étendu + SP-14)

- **SP-11 (inchangé dans son cœur)** livre CDC, DuckDB, API analytique A19. 
  ⚠ Extension proposée à acter : la notion de **dataset partagé** (objet de
  plateforme) entre dans le périmètre SP-11 ou immédiatement après — c'est le
  réceptacle naturel de l'API analytique.
- **SP-14 — Analytics UX (nouveau, post-SP-11, ~60–100 h)** : requête visuelle,
  pipeline de transformations (dont jointures et spatial no-code), contexte
  global temps×emprise×filtres, cross-filter par défaut, drill « voir les
  entités », pivot, carte analytique, suggestions de viz depuis le schéma,
  SQL Lab (UI de l'endpoint analyste). Jalon proposé : **M11 « BI géospatiale »**
  — un agent non technicien répond à une question spatiale (« combien
  d'incidents à moins de 500 m d'une école, par commune, ce trimestre ? ») sans
  code ni SQL.

### Vague 2 — decision support (SP-15, ~50–80 h)

- **SP-15 — Alertes & reporting** : AlertRule (jobs), ReportSchedule,
  exports Excel/CSV serveur, PDF de dashboards paginés (extension SP-13),
  bookmarks/situations partagées, diffusion email/webhook. Jalon **M12
  « la plateforme prévient »** : un rapport hebdo arrive par email ; une alerte
  de seuil se déclenche en < 5 min.

### Vague 3 — sur déclencheur explicite

- **Temps réel cran 1** (SSE/MQTT, couches live) : si et seulement si Q10
  identifie un besoin concret.
- **Connecteur ArcGIS Feature Services** : 5ᵉ connecteur de moissonnage
  (⚠ extension d'A22) — déclencheur : première collectivité Esri en migration.
- **Connecteurs SQL externes, Iceberg, DuckDB-WASM** : maintenus différés
  (A17/A18), triggers documentés en §9 de la feuille de route.

Positionnement temporel : les vagues 1–2 s'insèrent **après SP-11** dans l'ordre
A27, avant ou en parallèle de SP-12/SP-13 selon Q2 (SP-13 print est un
prérequis partiel de SP-15 → suggérer l'ordre SP-11 → SP-14 → SP-13 → SP-15 →
SP-12 si l'analytics devient prioritaire — ⚠ ce réordonnancement amenderait A27
et sera tranché au moment venu, pas ici).

### Récapitulatif des amendements que cette vision demanderait (si retenue)

| # | Nature | Document impacté |
|---|---|---|
| 1 | SP-5 : bindings CEL généralisés + variables typées explicitement au périmètre | spec SP-5 (pas d'arbitrage changé) |
| 2 | SP-11 : datasets partagés au périmètre (ou SP-14 immédiat) | feuille de route §6 |
| 3 | Nouveaux SP-14 (Analytics UX) et SP-15 (Alertes & reporting), jalons M11/M12 | feuille de route §6/§11 |
| 4 | A22 : ArcGIS Feature Services en 5ᵉ connecteur (sur déclencheur) | feuille de route §8 |
| 5 | A27 : ordre relatif SP-12/13/14/15 à retrancher après SP-11 | feuille de route §8 |

### Coût honnête

Vagues 0–2 ≈ **170–280 h** en plus des ~595–1050 h de la route actuelle. À
10–25 h/semaine, c'est 4 à 10 mois supplémentaires. C'est le prix ; il est
soutenable précisément parce que chaque vague est livrable et démontrable
séparément — et parce que les fondations (DuckDB, CEL, jobs, Playwright, MCP)
sont déjà payées par la route existante.

---

## 8. Différenciateurs

<a name="8-différenciateurs"></a>
Ce qui permet de concurrencer *simultanément* ArcGIS Experience Builder, Grafana
et Superset — aucun des trois ne peut suivre sur les trois axes à la fois :

1. **Un seul runtime déclaratif pour carte + BI + app** — Esri fragmente
   (ExB + Dashboards + StoryMaps + Insights), Grafana n'a pas d'apps, Superset
   n'a ni cartes interactives ni formulaires. Chez GeoStudio, le dashboard qui
   *écrit* (formulaire d'intervention à côté du KPI) est natif.
2. **L'emprise comme contexte analytique global** — le « time-picker spatial ».
   Geste fondateur SIG que ni Grafana ni Superset ne peuvent copier sans
   réécrire leur modèle, et d'un niveau d'intégration qu'ArcGIS Dashboards
   n'atteint que par câblages.
3. **AI-native par construction** — tout est config schématisée + MCP dans le
   cœur avec permissions/audit : « génère le dashboard de suivi des
   subventions par canton » est un prompt, pas une roadmap. Les 11 benchmarkés
   greffent des copilotes ; GeoStudio est *opérable* par agents.
4. **Lakehouse ouvert intégré** — BI sur millions de lignes via DuckDB/GeoParquet
   sans serveur BI dédié, formats lisibles par QGIS/pandas/n'importe quoi même
   plateforme éteinte (« le format est l'API »). Superset exige un
   warehouse ; Esri enferme ; Grafana ne stocke pas.
5. **Standards OGC/STAC/DCAT + open-data intégré** — l'obligation réglementaire
   des collectivités françaises couverte nativement (SP-12) : aucun outil BI ne
   le fait, et Esri le fait en produit additionnel payant.
6. **Souveraineté et coût** — self-hosted en un `docker compose up`, Apache-2.0,
   ~10 conteneurs légers : l'argument décisif face aux licences Esri et aux
   SaaS BI pour le marché collectivités/exploitants.
7. **Continuum no-code → low-code (CEL) → code (SDK WC)** avec configs
   versionnées/GitOps — la sortie par le haut qu'Appsmith/Retool offrent sans
   gouvernance et qu'Esri n'offre pas du tout.

La **niche de départ assumée** (critique de lucidité) : GeoStudio ne battra ni
Grafana sur l'observabilité d'infrastructure, ni Power BI sur la finance
d'entreprise. Il gagne là où les trois mondes se croisent : **le patrimoine
territorial et les réseaux** — là où la donnée est spatiale, les utilisateurs
non techniciens, et le budget contraint. C'est exactement Q2.

---

## 9. Risques

<a name="9-risques"></a>

| Risque | Gravité | Garde-fou |
|---|---|---|
| **Dispersion** : l'analytics dilate la route d'un solo à 10–25 h/sem | ★★★ le risque n° 1 | Rien avant v0.1 sauf vague 0 marginale ; vagues gated par jalons ; chaque SP-1x a des critères E2E fermés |
| **Reconstruire Superset en pire** (générateur de charts générique sans âme) | ★★ | Le fil rouge est le différenciateur spatial : chaque feature doit servir « voir/comprendre/agir sur un territoire » ; sinon backlog |
| Deux moteurs de données (client actuel vs API analytique) qui coexistent longtemps | ★★ | La migration `statistics`→serveur est dans SP-11 (déjà prévu) ; compat automatique §5.7 ; supprimer l'agrégation client à la bascule |
| Cross-filter par défaut = comportements surprises dans les apps existantes | ★ | Opt-in au niveau de l'app (`interactions: "auto"|"manual"`), défaut `manual` pour les configs migrées, `auto` pour les nouvelles |
| L'API analytique devient un ORM ingérable (jointures, pivots, spatial…) | ★★ | Périmètre fermé par version ; tout ce qui déborde va au SQL analyste (A19 a prévu la soupape) |
| Alertes/rapports = surface d'abus (spam, exfiltration) | ★★ | Droits du propriétaire, quotas par tenant, canaux validés, tout audité |
| Temps réel lancé sur spéculation | ★★ | Verrou Q10 maintenu — le cran 0 (refresh) désamorce l'urgence |
| Le mot « Analytics Platform » brouille le positionnement v0.1 | ★ | Le README v0.1 reste « geospatial app builder » ; l'analytics arrive comme chapitre 2 du récit, pas comme promesse initiale |

---

## 10. Questions

<a name="10-questions"></a>
À trancher par Tanguy (elles conditionnent les vagues, pas la v0.1) :

- **Q-A1** : valider le concept **Dataset comme objet de plateforme** (nouveau
  type d'item) — c'est la clef de voûte de tout le document.
- **Q-A2** : le contexte global inclut-il l'emprise par défaut (`extent` filtre
  les datasets marqués) — ou opt-in par dataset ? (proposition : opt-in par
  dataset, car le refetch à chaque pan de carte a un coût).
- **Q-A3** : priorité relative SP-14/SP-15 vs SP-12/SP-13 après le lakehouse
  (amendement A27) — dépend de Q2 (premiers utilisateurs réels).
- **Q-A4** : le connecteur ArcGIS Feature Services mérite-t-il d'entrer en A22
  dès maintenant (argument migration Esri) ou sur déclencheur ?
- **Q-A5** : Excel — export sec (CSV/xlsx de données) suffit-il, ou faut-il des
  classeurs mis en forme (gabarits) ? (proposition : export sec en SP-15,
  gabarits différés).

---

*Brainstorm rédigé le 2026-07-09 (état M1, branche `dev`), sur la base de la
feuille de route 2026-07-04 (arbitrages A1–A27 respectés), du comparatif §9, de
la vision long terme, et de l'inventaire du code du builder
(`shell/src/builder/`). Prochaine étape si validé : mise à jour explicite de la
feuille de route (amendements §7 ci-dessus), puis specs SP dédiées le moment
venu — rien de tout ceci n'interfère avec SP-2 (MCP v0), le prochain chantier.*
