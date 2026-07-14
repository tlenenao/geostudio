# GeoStudio — Gap analysis : dataviz, analytics, BI, portails & sites, géospatial avancé

> **Date : 2026-07-14 · Statut : validé** — les arbitrages proposés en §9.2 ont
> été tranchés par Tanguy le 2026-07-14 et déclinés le même jour dans la
> [feuille de route](./2026-07-04-feuille-de-route-geostudio.md) : **SP-16
> « Portails & Sites », quick win Storytelling, arbitrages A31/A33–A38, jalon
> M13**, avec deux specs détaillées
> ([SP-16](../superpowers/specs/2026-07-14-sp16-portails-sites-design.md),
> [storytelling](../superpowers/specs/2026-07-14-storytelling-pagemanager-design.md)).
> Seul **A32** (copilote IA embarqué comme client MCP interne) reste une
> proposition ouverte, à trancher au cadrage de ce chantier. La feuille de
> route reste LA référence opérationnelle ; ce document en est le matériau
> d'analyse (benchmark, gap analysis, architecture cible).
>
> Ce document ne modifie **aucun** arbitrage déjà tranché
> (A1–A30) ni le phasage SP-1→SP-15 de la
> [feuille de route](./2026-07-04-feuille-de-route-geostudio.md) : il les reprend,
> les recoupe avec un périmètre plus large que le seul
> [brainstorm Analytics Platform](./2026-07-09-brainstorm-geostudio-analytics-platform.md)
> (qui couvrait BI/dataviz/decision support), et ajoute trois angles qu'aucun document
> existant ne traite explicitement : **portails de données / sites publics** (façon
> ArcGIS Hub), **storytelling** comme livrable de première classe, et **copilote IA
> embarqué** dans le builder (au-delà de l'opérabilité MCP externe déjà acquise).
> Toute recommandation ci-dessous qui amenderait un arbitrage existant est marquée
> **⚠ amendement proposé** et devra être validée explicitement, comme le veut la
> règle du projet.
>
> Sources : code (`shell/src/`, `core/app/`), les quatre documents de
> `docs/vision/`, les 23 specs de `docs/superpowers/specs/`, l'état d'avancement
> consigné dans `CLAUDE.md` (arrêté au 2026-07-13, SP-8 clos, SP-9 en cours de
> spécification).

---

## Sommaire

1. [Résumé exécutif](#1-résumé-exécutif)
2. [Analyse de l'existant](#2-analyse-de-lexistant)
3. [Benchmark fonctionnel et technique](#3-benchmark)
4. [Gap analysis](#4-gap-analysis)
5. [Architecture cible](#5-architecture-cible)
6. [Catalogue fonctionnel recommandé](#6-catalogue-fonctionnel)
7. [Le builder existant face aux nouveaux usages](#7-builder)
8. [Roadmap 6 / 12 / 24 / 36 mois](#8-roadmap)
9. [Priorisation des fonctionnalités](#9-priorisation)
10. [Recommandations stratégiques](#10-recommandations)
11. [Risques transverses](#11-risques)
12. [Annexes](#12-annexes)

---

## 1. Résumé exécutif

GeoStudio est aujourd'hui (2026-07-14, jalon **M1 atteint**, SP-8 clos, SP-9 en
cours) un **constructeur d'applications géospatiales no-code** solide sur ses
fondamentaux — catalogue, éditeur de carte, builder config-driven, partage et
publication, formulaires CRUD, expressions CEL, SDK Web Components — mais c'est
encore, sur l'axe **data visualisation / analytics / BI**, un *viewer figé au
fetch* : agrégation côté navigateur plafonnée à quelques dizaines de milliers de
lignes, aucune couche sémantique (métriques redéfinies à chaque dashboard),
aucun contexte analytique partagé (pas de cross-filter par défaut, pas de
« stats sur ce que je vois »), aucune sortie (pas d'export, pas de rapport
planifié, pas d'alerte). Sur l'axe **portails/sites publics**, le produit n'a
qu'un catalogue interne et des items publiés individuellement — rien d'assimilable
à un portail de données de type ArcGIS Hub ou data.gouv.fr (page d'accueil de
marque, navigation multi-app, mise en avant éditoriale, téléchargement multi-format
en libre-service).

**Le diagnostic central, hérité et confirmé** : le fossé n'est pas
technologique, il est **conceptuel et séquentiel**. La feuille de route
2026-07-04/09 a déjà posé, sans le nommer complètement, l'essentiel des
fondations (CEL comme langage de mesures/bindings, procrastinate pour les
jobs, DuckDB/GeoParquet pour le passage à l'échelle analytique, Playwright
pour le rendu WYSIWYG, MCP pour l'opérabilité IA, Web Components pour
l'extensibilité). Trois abstractions manquent encore au catalogue de la
feuille de route pour couvrir intégralement le périmètre demandé
(dataviz + analytics + BI + dashboards + portails + sites + apps + géospatial
avancé + exploration de données) :

1. **Dataset comme objet de plateforme** — déjà acté (A28, SP-14) : la couche
   sémantique qui manque à GeoStudio face à Superset/Metabase/Power BI.
2. **Portail/Site comme objet de plateforme** — **absent de la feuille de
   route actuelle**, à introduire : la façade publique multi-app, éditorialisée,
   qui manque face à ArcGIS Hub, CKAN, data.gouv.fr thématiques.
3. **Copilote IA embarqué dans le builder** — le MCP rend GeoStudio *opérable*
   par un agent externe (Claude Desktop, etc.), mais aucune expérience de chat
   assistant n'existe *dans* le shell lui-même ; c'est pourtant l'argument
   différenciant n° 1 du produit (§8 du brainstorm) et il reste, pour l'instant,
   seulement latent.

**Conclusion et recommandation centrale** : ne pas bifurquer. Poursuivre le
chemin critique déjà arbitré (A27 : SP-9 → SP-10 → SP-11) sans le perturber,
puis insérer, dans l'ordre proposé en §8 de ce document,
**SP-14 (Analytics UX) avant SP-12/SP-13**, un nouveau **SP-16 (Portails & Sites)**
et un **copilote IA embarqué** transversal (introduit dès que le MCP le permet,
sans attendre un SP dédié). Ce document chiffre, priorise et détaille ces
ajouts ; il ne remplace ni la feuille de route ni le brainstorm Analytics, il
les complète et propose les arbitrages qui manquent encore (§9, tableau A31–A36).

---

## 2. Analyse de l'existant

### 2.1 Architecture actuelle

```
Shell (React 19, Vite, TS)          Cœur (Python/FastAPI, monolithe modulaire)
├─ catalogue (recherche, partage)   ├─ items · sharing · configs (+ révisions/rollback)
├─ éditeur de carte (MapLibre GL    ├─ collections (registre + introspection + CRUD OGC API Features)
│   + deck.gl overlays)             ├─ ingestion (jobs procrastinate : GeoJSON/CSV/GPKG/SHP → PostGIS)
├─ builder no-code                  ├─ search (trigram + pgvector, RRF hybride)
│   ├─ AppRenderer(config, mode)    ├─ extensions (registre WC, activable par admin)
│   │   edit/preview/runtime         ├─ mcp (serveur OAuth2.1+PKCE, 10 outils v0/v1)
│   ├─ 11 widgets (dont chart via   ├─ auth (JWT OIDC via Keycloak, mode mock)
│   │   ECharts, map, formulaire)   ├─ tenants/users/audit_log (append-only)
│   ├─ ActionBus (événements→       └─ public (accès anonyme aux items publiés)
│   │   actions, conditions CEL)
│   ├─ expr.ts (moteur CEL client)  Stack : PostGIS+pgvector, PgBouncer, MinIO(S3),
│   ├─ variables typées + bindings  Martin (MVT), TiTiler (COG), Keycloak (OIDC),
│   │   $expr généralisés (SP-5c)   Traefik, worker procrastinate. 9 services.
│   ├─ pages, thèmes, breakpoints
│   └─ SDK Web Components (Lit) +
│       pont WidgetHost↔WC
```

**Ce qui est structurellement solide et à conserver sans réserve** :
- Un **seul runtime déclaratif** (`AppRenderer`) pour apps/dashboards/maps — la
  règle d'architecture n° 3 est exactement ce qui permettra d'ajouter BI, portails
  et storytelling **sans deuxième moteur**, contrairement à tous les concurrents
  étudiés (voir §3).
- **Tout objet est une config schématisée** (règle n° 2) — précondition du MCP
  et de la génération par IA, déjà exploitée par 10 outils MCP fonctionnels.
- **`ItemClient` comme sas unique** (règle n° 1) côté shell ; **`can()` comme
  porte unique** d'autorisation côté cœur — la sécurité ne se recâble pas à
  chaque nouvelle brique, elle en hérite.
- CEL comme langage d'expression unique client/serveur (A8), déjà généralisé à
  toute prop de widget (SP-5c) — c'est *le* langage des futures métriques,
  filtres et règles d'alerte, pas un nouveau DSL à inventer.
- procrastinate (jobs Postgres, A5) déjà en production (ingestion) — le socle
  direct des rapports planifiés et des alertes (SP-15).
- ECharts déjà intégré avec 10 types de graphiques — sankey/treemap/sunburst/
  funnel/waterfall sont dans la dépendance, pas à intégrer.

### 2.2 Inventaire fonctionnel factuel

| Domaine | État | Détail |
|---|---|---|
| **Catalogue** | ✅ | Recherche hybride trigram+vecteur (pgvector, RRF), scopes all/mine/shared/public, vignettes S3 |
| **Cartographie** | ✅ solide | Éditeur multi-couches (Martin MVT, TiTiler raster/COG, deck.gl), sélecteur de couches avec recherche |
| **Builder — widgets** | ✅ 11 types | text, image, button, list, table, indicator, chart (ECharts), map, filter, nav, form ; SDK WC (Compteur de référence) |
| **Builder — dataviz** | ⚠ v0 solide mais plafonnée | 10 types ECharts + option avancée deep-merge ; agrégation **côté client** (count/sum/avg/min/max, groupBy, pivot) — plafond réel de quelques 10⁴ lignes |
| **Data sources** | ⚠ | `features` (OGC API Features du cœur), `statistics` (agrégation client), `static` — privées à chaque app, non nommées, non réutilisables |
| **Interactions** | ⚠ embryon | ActionBus (événements→actions), conditions CEL (SP-5b), pas de cross-filter par défaut, câblage manuel source par source |
| **Variables/bindings** | ✅ récent (SP-5c) | Typées (string/number/bool/date/record/list), `{{var:nom}}` partout, `$expr` CEL sur **toute prop de tout widget** |
| **Formulaires/écriture** | ✅ (SP-4) | Génération schema-driven, validation client+serveur, sélection→édition, `canWrite` fail-open côté UI / 403 côté serveur |
| **Ingestion** | ✅ (SP-6a/b) | GeoJSON/CSV/GPKG/SHP zippé → PostGIS, reprojection auto, feature_count maintenu |
| **Partage/publication** | ✅ (SP-1c) | Groupes×rôles, publication anonyme au runtime, audit systématique |
| **Extensibilité** | ✅ (SP-8) | Contrat Web Component + manifeste JSON, chargement dynamique cross-origin, registre d'extensions admin |
| **IA/MCP** | ✅ opérabilité, ❌ copilote embarqué | 10 outils MCP (list/get/create items, sharing, search_catalog, query_features, create_form_app…) utilisables par un client MCP **externe** ; **aucune UI de chat dans le shell** |
| **Analytique/BI** | ❌ | Pas de couche sémantique, pas de jointure, pas de calcul dérivé serveur, pas de moteur de requête, pas de SQL Lab |
| **Reporting/alertes** | ❌ | Pas d'export CSV/Excel, pas de PDF, pas de rapport planifié, pas d'alerte |
| **Portails/sites publics** | ❌ | Items publiés individuellement (URL par item) ; aucune page d'accueil de marque, navigation multi-app, mise en avant éditoriale, téléchargement en libre-service |
| **Storytelling** | ❌ | Pages + navigation existent (brique), mais pas de gabarit narratif (scrollytelling carte, séquence d'états analytiques figés) |
| **Interopérabilité catalogue** | ❌ (SP-12 non lancé) | Pas de STAC, pas de DCAT, pas de moissonnage |
| **Lakehouse/passage à l'échelle** | ❌ (SP-11 non lancé) | Pas de CDC, pas de DuckDB, pas de GeoParquet |
| **3D/impression** | ❌ (SP-13 non lancé) | Pas de 3D Tiles, pas de terrain, pas d'export PDF/PNG mis en page |
| **Observabilité** | ❌ (SP-10 non lancé) | Pas d'OTel, pas de dashboards d'exploitation, pas de SLO |
| **Temps réel** | ❌ différé (Q10 ouverte) | Pas de flux live, pas de SSE/MQTT |

### 2.3 Rappel synthétique de ce qui est déjà décidé

La feuille de route couvre déjà, en 15 sous-projets (SP-1→SP-15, ≈880–1510 h,
soit 20–42 mois solo à 10–25 h/semaine), l'essentiel du chemin vers une
plateforme analytics complète :

| Bloc | SP | Apporte | Statut au 2026-07-14 |
|---|---|---|---|
| Socle produit | SP-1→9 | Cœur, MCP v0, collections/CRUD, formulaires, CEL, ingestion, recherche+MCP v1, SDK WC, durcissement v0.1 | SP-1→8 **clos** ; SP-9 en cours |
| Exploitation | SP-10 | OTel, dashboards/SLO packagés | non lancé |
| Data platform | SP-11 | CDC→GeoParquet, DuckDB, API analytique structurée + SQL analyste | non lancé |
| Catalogue ouvert | SP-12 | STAC natif, export DCAT-AP, moissonnage (STAC/ArcGIS FS/WMS-WFS/CSW/CKAN) | non lancé |
| 3D & impression | SP-13 | deck.gl 3D Tiles, terrain, export PDF/PNG (Playwright) | non lancé |
| BI géospatiale | SP-14 | Datasets partagés (A28), requête visuelle, contexte global temps×emprise (A29), cross-filter, SQL Lab, widgets analytiques v2 | non lancé, dépend de SP-11 |
| Decision support | SP-15 | AlertRule, ReportSchedule, exports secs (A30) | non lancé, dépend de SP-13/14 |

**Ce que ce document ajoute à ce socle** : (a) le cadrage benchmark élargi aux
huit produits explicitement demandés (dont ArcGIS Hub, absent du brainstorm
2026-07-09), (b) un module **Portails & Sites** non couvert par la feuille de
route actuelle, (c) le traitement explicite du **storytelling** comme gabarit
de premier rang plutôt que sous-note, (d) un **copilote IA embarqué**
transversal, (e) une reformulation de la roadmap en échéances calendaires
(6/12/24/36 mois) plutôt qu'en seule séquence de SP, pour piloter les
arbitrages de priorité.

### 2.4 Diagnostic critique étendu

Le diagnostic du brainstorm 2026-07-09 (§1.3, six points : lecture seule,
agrégation client plafonnée, pas de couche sémantique, pas d'interactions
analytiques, aucune sortie, carte pauvre côté builder) reste entièrement
valide et n'est pas répété ici in extenso. Trois points supplémentaires,
nécessaires pour couvrir le périmètre demandé par ce document :

7. **Pas de façade publique au-delà de l'item.** Un item publié est une URL
   isolée ; il n'existe aucune notion de « ce catalogue, vu de l'extérieur,
   comme un site » — pas de page d'accueil personnalisable, pas de regroupement
   thématique d'apps/dashboards/cartes pour un public externe, pas de
   téléchargement en libre-service multi-format, pas de domaine personnalisé.
   C'est le manque structurel face à ArcGIS Hub/CKAN/data.gouv.fr thématiques —
   or c'est un argument de vente fort pour les collectivités (obligation
   open-data, communication publique).
8. **Le storytelling est une capacité latente, pas un livrable.** Pages +
   navigation + variables + bindings existent ; mais rien ne *gabarit*
   l'expérience narrative (progression scrollée, carte qui vole d'une emprise à
   l'autre, état analytique figé par chapitre). Sans gabarit dédié, chaque
   auteur réinventerait la story à la main — contraire à l'esprit no-code du
   produit.
9. **L'IA est opérable de l'extérieur, invisible de l'intérieur.** Le MCP est
   un différenciateur réel (aucun des 11 produits du benchmark 2026-07-09 n'a
   d'équivalent nativement), mais il exige aujourd'hui un client MCP tiers
   (Claude Desktop, un agent custom). Rien dans le shell ne permet à un agent
   métier non technicien de taper « montre-moi les incidents de voirie de mars
   par quartier » et de voir un widget apparaître. Le levier existe (10 outils
   MCP déjà écrits), l'expérience utilisateur manque.

---

## 3. Benchmark

<a name="3-benchmark"></a>

### 3.1 Méthodologie

Pour chacun des huit produits demandés, on documente : le concept
différenciant, ce qui est directement transposable à GeoStudio (compte tenu de
ses choix déjà arbitrés — CEL, DuckDB, procrastinate, MCP, Web Components), et
ce qu'il faut délibérément **ne pas** copier. Le benchmark des 11 produits du
brainstorm 2026-07-09 (Grafana, Superset, Metabase, Power BI, Tableau, Kibana,
ArcGIS Dashboards, ArcGIS Experience Builder, Retool, Appsmith, Redash) est
repris par référence (§2 de ce brainstorm) et **résumé** ci-dessous ; seul
**ArcGIS Hub**, absent de ce premier tour, est traité en détail ici comme
apport propre à ce document.

### 3.2 Grafana — observabilité et alerting

Concept clé transposable : *time-range picker global* → généralisé chez
GeoStudio en **contexte double temps × emprise** (§4.3) ; *alerting* → objet
`AlertRule` (SP-15) ; *variables de dashboard* → variables typées + CEL
(acquis SP-5c). À ne pas copier : le modèle « un panel = une requête TSDB » —
GeoStudio a des entités géo-attributaires, pas des séries d'infra.

### 3.3 Apache Superset — la couche sémantique

Concept clé : **Dataset = table + colonnes calculées + métriques nommées**,
découplé du chart. C'est **le** concept central déjà acté côté GeoStudio (A28,
SP-14) — dataset comme objet de plateforme, catalogué, partagé, versionné. À
ne pas copier : la fragmentation dataset/chart/dashboard en trois objets
distincts sans app englobante — GeoStudio garde un seul `AppConfig`.

### 3.4 Metabase — l'analytique pour non-techniciens

Concept clé : **requête visuelle** (Filtrer→Résumer→Grouper) qui compile vers
une API structurée, jamais du SQL généré côté client — exactement l'arbitrage
A19 déjà pris. *X-rays* (auto-dashboard depuis une table) → version GeoStudio
possible par prompt MCP (« découvre-moi cette collection ») dès que
`create_dataset`/`explain_dataset` existent (SP-14).

### 3.5 Power BI — modèle relationnel et interactivité par défaut

Concept clé : **cross-highlight par défaut** — toute sélection filtre/surligne
le reste, sans câblage. Repris comme cross-filter par défaut opt-out (§4.3,
A29). *Bookmarks* → états analytiques sérialisables dans l'URL (SP-14). À ne
pas copier : le modèle propriétaire fermé, l'écosystème DAX (complexité hors
persona v1).

### 3.6 Tableau — encodage visuel et data stories

Concept clé : **encodages champ→canal** (x, y, couleur, taille) plutôt que
« type de chart d'abord » — un seul vocabulaire pour charts *et* symbologie de
carte (différenciant GeoStudio, personne d'autre n'unifie les deux). *Story
points* → traité en détail en §7.5 de ce document (storytelling), comme
gabarit `AppConfig` de premier rang plutôt qu'annexe.

### 3.7 ArcGIS Experience Builder — le concurrent frontal

Concept clé : **framework de messages/actions** (records/extent/selection
comme messages typés) — équivalent de l'ActionBus généralisé avec payloads
typés (§4.6). Ses faiblesses (fragmentation ExB/Dashboards/StoryMaps/Insights,
framework React figé, pas de BI réelle, coût de licence, pas d'IA opérante)
sont exactement les angles d'attaque de GeoStudio : un seul runtime, un SDK WC
ouvert, une BI native, un coût de possession nul, un MCP natif.

### 3.8 ArcGIS Dashboards — le dashboard cartocentrique

Concept clé : **la carte pilote les indicateurs** (extent comme variable de
contexte) — c'est le geste fondateur revendiqué par GeoStudio (« l'emprise
comme le time-picker de Grafana », §4.3, déjà acté A29 en opt-in par dataset).
*Indicateurs riches* (valeur/référence/tendance/seuils) → upgrade du widget
`indicator` (déjà dans le catalogue SP-14).

### 3.9 ArcGIS Hub — le portail de données public (apport propre à ce document)

ArcGIS Hub n'était pas dans le benchmark du 2026-07-09 (qui visait BI/dataviz).
Il couvre un besoin différent, réel chez les collectivités (persona n° 8 de la
vision) : **le portail public de données et d'initiatives**.

| Concept ArcGIS Hub | Valeur | Adaptation GeoStudio |
|---|---|---|
| **Sites** : portail de marque (thème, domaine, navigation, pages de contenu riche — hero, cartes, texte, embeds) construit sans code, distinct du contenu qu'il expose | Une collectivité communique *son* portail, pas une liste brute d'items | Nouveau type d'item **`site`** (ou **`portal`**) : un `AppConfig` dont le gabarit combine pages de contenu éditorial (texte riche, héros, sections) et blocs de **découverte** (galerie d'items publiés, recherche, filtres par tag/type). Même runtime `AppRenderer`, nouveaux widgets de contenu (§7.6) |
| **Initiatives/Programmes** : regroupement thématique d'items + pages + métriques autour d'un objectif public (« Plan vélo 2026 ») | Structure éditoriale au-dessus du catalogue technique | Un item de type `site` peut référencer une liste de tags/collections comme périmètre — pas un nouveau modèle de données, une vue configurée |
| **Pages de dataset public** : fiche par jeu de données avec description, aperçu carte/table, téléchargement multi-format (CSV/GeoJSON/Shapefile/API) | L'obligation open-data des collectivités françaises couverte nativement | Se branche directement sur DCAT-AP (SP-12, A21) + exports secs (SP-15, A30) — **aucune nouvelle brique de données**, une page de rendu en plus |
| **Métriques d'usage** (vues, téléchargements, followers) | Preuve de valeur du portail pour l'élu/le décideur | Extension légère d'`audit_log` déjà append-only (compteurs agrégés, pas de nouveau système) |
| **Discussions/commentaires, followers, events** | Communauté autour de la donnée | **Hors périmètre v1** — surface d'abus/modération disproportionnée pour la cible (patrimoine territorial, pas réseau social) ; à ne pas copier sans demande réelle explicite |
| **Domaine personnalisé par site** | Un site = une identité propre (`donnees.mairie.fr`) | Traefik (déjà dans la stack) route par `Host` vers le cœur/shell ; un enregistrement de domaine par item `site`, résolution TLS (Let's Encrypt via Traefik) |

**Verdict** : ArcGIS Hub est le seul des huit produits demandés qui pointe vers
un **type d'objet de plateforme totalement absent** de la feuille de route
actuelle (contrairement aux six premiers, largement couverts par SP-11/14/15).
C'est la raison d'être du **SP-16 (Portails & Sites)** proposé en §8.

### 3.10 Matrice de synthèse comparative

Échelle : ✅ couvert nativement · ⚠ partiel/détourné · ❌ absent.

| Capacité | Grafana | Superset | Metabase | Power BI | Tableau | ArcGIS ExB | ArcGIS Dash. | ArcGIS Hub | **GeoStudio auj.** | **GeoStudio cible** |
|---|---|---|---|---|---|---|---|---|---|---|
| Cartographie interactive multi-couches | ⚠ (panel geomap) | ⚠ | ⚠ | ⚠ | ⚠ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Analyse spatiale no-code (buffer, intersect, H3) | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠ (widgets Esri) | ❌ | ❌ | ❌ | ✅ (SP-14) |
| Couche sémantique (datasets/métriques nommées) | ⚠ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠ | ❌ | ✅ (SP-14, A28) |
| Agrégation à l'échelle (>10⁶ lignes) | ✅ (TSDB) | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠ | ❌ | ❌ | ✅ (SP-11) |
| Cross-filter / drill par défaut | ⚠ | ✅ | ✅ | ✅ | ✅ | ⚠ | ✅ | ❌ | ❌ | ✅ (SP-14, A29) |
| Contexte spatial global (emprise → filtre) | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠ | ✅ | ⚠ | ❌ | ✅ (différenciant, A29) |
| SQL Lab / accès analyste | ❌ | ✅ | ✅ | ⚠ | ⚠ | ❌ | ❌ | ❌ | ❌ | ✅ (SP-11/14, A19) |
| Alertes seuils | ✅ | ⚠ | ⚠ | ✅ | ⚠ | ❌ | ❌ | ❌ | ❌ | ✅ (SP-15) |
| Rapports planifiés (PDF/email) | ⚠ | ⚠ | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠ | ❌ | ✅ (SP-15) |
| Export Excel/CSV | ⚠ | ✅ | ✅ | ✅ | ✅ | ⚠ | ⚠ | ✅ | ❌ | ✅ (SP-15, A30) |
| Formulaires / écriture de données | ❌ | ❌ | ❌ | ⚠ (Power Apps) | ❌ | ✅ | ⚠ | ⚠ | ✅ | ✅ |
| Builder d'app complet (pages, nav, logique) | ❌ | ❌ | ❌ | ⚠ | ❌ | ✅ | ⚠ | ⚠ | ✅ | ✅ |
| SDK d'extension ouvert (tiers, sans réécriture) | ⚠ (plugins Go) | ⚠ (Python) | ⚠ | ⚠ | ❌ | ❌ (React figé) | ❌ | ❌ | ✅ (Web Components) | ✅ |
| Portail public multi-app éditorialisé | ❌ | ❌ | ❌ | ⚠ (Power BI Apps) | ⚠ | ❌ | ❌ | ✅ | ❌ | ✅ (SP-16 proposé) |
| Catalogue standard (STAC/DCAT/OGC) | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠ (propriétaire Esri) | ❌ | ⚠ (propriétaire) | ⚠ (catalogue interne) | ✅ (SP-12) |
| Storytelling / scrollytelling | ❌ | ❌ | ❌ | ❌ | ⚠ (Story Points, désuet) | ⚠ (via StoryMaps séparé) | ❌ | ⚠ | ❌ | ✅ (§7.5) |
| IA générative opérable (créer un objet par prompt) | ⚠ (copilotes récents) | ❌ | ⚠ | ⚠ (Copilot) | ⚠ | ❌ | ❌ | ❌ | ✅ (MCP, externe) | ✅ (MCP + copilote embarqué) |
| Self-hosted open-source complet | ✅ | ✅ | ⚠ (édition limitée) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Coût de possession (licence) | gratuit/payant | gratuit | freemium | payant élevé | payant élevé | payant élevé | payant élevé | payant élevé | **gratuit (Apache-2.0)** | gratuit |

**Lecture** : sur la ligne « portail public éditorialisé », GeoStudio cible
est seul, avec ArcGIS Hub, à viser un ✅ plein — et le seul des deux à le faire
en open-source self-hosted. Sur « contexte spatial global », GeoStudio cible
dépasse même ArcGIS Dashboards en le généralisant à *tout* widget (pas
seulement les indicateurs).

---

## 4. Gap analysis

<a name="4-gap-analysis"></a>

### 4.1 Par domaine fonctionnel demandé

| Domaine demandé | Couverture actuelle | Gap principal | SP porteur |
|---|---|---|---|
| **Data visualisation** | ⚠ 60 % (10 types ECharts, pas d'encodages unifiés, pas de suggestion de viz) | Encodages champ→canal unifiés charts+carte ; suggestion de viz depuis schéma ; nouveaux types (sankey, treemap, pivot) | SP-14 |
| **Data analytics** | ❌ 15 % (agrégation client seule) | Moteur DuckDB/GeoParquet, pipeline de transformation serveur, analyse spatiale no-code | SP-11, SP-14 |
| **Business intelligence** | ❌ 10 % (aucune couche sémantique) | Dataset partagé, métriques nommées, SQL Lab, gouvernance des sources | SP-14 (A28) |
| **Création de tableaux de bord** | ✅ 70 % (le builder les fait déjà) | Contexte global, cross-filter, KPI riches, bookmarks/situations | SP-14 |
| **Création de sites web / portails de données** | ❌ 5 % (aucun objet portail) | Nouveau type d'item `site`, gabarits éditoriaux, domaines personnalisés, pages dataset public | **SP-16 (nouveau, proposé)** |
| **Création d'applications web** | ✅ 75 % (formulaires, CRUD, logique CEL, SDK WC) | Conteneurs (onglets/modale/tiroir), workflows multi-étapes, déclencheurs data/timer | SP-5/SP-14 extension |
| **Cartographie et géospatial avancé** | ✅ 65 % (multi-couches, MVT, COG) | 3D Tiles/terrain, analyse spatiale packagée, symbologie data-driven unifiée | SP-13, SP-14 |
| **Exploration et analyse de données** | ⚠ 30 % (table triée/paginée, recherche catalogue) | Drill-down, « voir les entités », SQL Lab, X-rays/auto-dashboard | SP-14 |

### 4.2 Par brique technique

| Brique | État | Gap | Sévérité |
|---|---|---|---|
| Moteur de requête | Agrégation JS côté client, sur GeoJSON complet téléchargé | Aucune API d'agrégation serveur ; plafond de charge bas ; aucune jointure | ★★★ critique |
| Stockage analytique | PostGIS seul (chaud) | Pas de lakehouse froid, pas de CDC, coût de stockage/requête sur gros historiques | ★★★ critique |
| Couche sémantique | Absente | Chaque app redéfinit ses métriques ; pas de gouvernance ; MCP ne peut pas raisonner sur « le CA » | ★★★ critique |
| Contexte d'interaction | ActionBus manuel, pas de contexte partagé | Cross-filter/temps/emprise à câbler à la main, non généralisé | ★★ élevé |
| Sorties (export/PDF/alerte) | Aucune | Aucun produit BI n'est complet sans sortie — argument de vente n° 1 (« le rapport du lundi ») manquant | ★★ élevé |
| Portails/sites publics | Item isolé, pas de façade | Aucun argument face à ArcGIS Hub/CKAN pour l'obligation open-data | ★★ élevé (marché collectivités) |
| 3D/print | Absent | Pas bloquant pour le cas d'usage n°1 (dashboards métier) ; important pour aménagement/urbanisme | ★ moyen |
| Observabilité | Absente | Bloquant pour exploiter une démo publique en confiance, pas pour la valeur produit elle-même | ★★ élevé (avant v0.1 public) |
| Temps réel | Absent, différé (Q10) | Non bloquant tant qu'aucun persona réel ne l'exige — cran 0 (refresh) suffit à 80 % des cas | ★ faible (assumé) |
| IA embarquée | MCP externe seulement | Le différenciateur n°1 du produit reste invisible dans l'UX quotidienne | ★★ élevé (stratégique) |
| Storytelling | Pages/nav génériques | Pas de gabarit narratif — chaque story se bricole à la main aujourd'hui | ★ moyen |
| Standards catalogue | Absents (STAC/DCAT) | Argument réglementaire/interop manqué pour les collectivités | ★★ élevé (marché) |

### 4.3 Tableau des gaps priorisés (impact × effort)

Échelle d'effort : S (< 40 h), M (40–100 h), L (100–200 h), XL (> 200 h) —
cohérente avec les tranches d'heures déjà utilisées dans la feuille de route.

| # | Gap | Impact produit | Effort estimé | Dépend de | Recommandation |
|---|---|---|---|---|---|
| G1 | Pas de moteur d'agrégation serveur | Critique | XL | — | SP-11, chemin déjà arbitré, ne pas retarder |
| G2 | Pas de dataset/couche sémantique | Critique | L | G1 | SP-14, immédiatement après SP-11 |
| G3 | Pas de contexte analytique global (temps×emprise×filtres×sélection) | Élevé | M | G2 | SP-14 |
| G4 | Pas de sorties (export/PDF/alerte) | Élevé | M | SP-13 (Playwright) | SP-15 |
| G5 | Pas de portail/site public éditorialisé | Élevé (marché) | L | items existants, DCAT (SP-12) partiel | **SP-16 nouveau**, voir §5/§8 |
| G6 | Pas de standards catalogue (STAC/DCAT/moissonnage) | Élevé (marché) | L | — | SP-12 |
| G7 | Pas d'observabilité | Élevé (avant démo publique) | M | — | SP-10, avant tout trafic réel |
| G8 | Pas de copilote IA embarqué | Élevé (stratégique) | S–M par itération | MCP (acquis) | Transversal, dès que possible, voir §7.10 |
| G9 | Pas de gabarit storytelling | Moyen | S | pages/bindings (acquis) | Quick win, voir §7.5 |
| G10 | Pas de 3D/print | Moyen | L | — | SP-13 |
| G11 | Widgets analytiques v2 (KPI riche, pivot, filtres typés) | Moyen | M | G2/G3 | SP-14 |
| G12 | Analyse spatiale no-code packagée | Moyen | M | G1 | SP-14 |
| G13 | Workflows low-code multi-étapes (approbations) | Faible-moyen (hors persona v1) | L | actions composées (acquis) | Différé, sur demande réelle |
| G14 | Temps réel (flux live) | Faible (Q10 non tranchée) | XL | — | Différé, cran 0 (refresh) suffit |
| G15 | Connecteurs SQL externes / Iceberg | Faible | L/XL | — | Différé (déjà acté A17/§9 feuille de route) |

---

## 5. Architecture cible

<a name="5-architecture-cible"></a>

### 5.1 Principes directeurs (rappel + extension)

Les quatre règles d'architecture non négociables de `CLAUDE.md` s'appliquent
sans exception aux ajouts de ce document :

1. `ItemClient` reste le seul sas entre shell et backend — les nouveaux types
   d'item (`dataset`, `site`, `alert`, `report`) passent par les mêmes 18(+)
   méthodes, pas par un client parallèle.
2. Chaque nouvel objet (dataset, pipeline, site, alerte, rapport) est une
   **config déclarative schématisée** — condition de leur exposition MCP et de
   leur génération par IA « gratuite ».
3. **Un seul runtime** `AppRenderer(config, mode)` — un site public, un
   dashboard analytique et une story scrollée sont trois **gabarits** du même
   `AppConfig`, pas trois moteurs.
4. Frontières de modules du cœur lintées — les nouveaux modules (`datasets`,
   `analytics`, `alerts`, `reports`, `sites`) s'ajoutent au contrat
   import-linter existant dès leur première ligne de code.

### 5.2 Schéma cible

```
                    SOURCES              DATASETS (objet plateforme, A28)
        ┌──────────────────────┐      ┌─────────────────────────┐
        │ PostGIS (chaud)      │      │ source + pipeline        │
        │ GeoParquet/S3 (froid)│─────▶│ (filter/aggregate/join/  │
        │ Fichiers importés    │      │  derive/pivot/spatial)   │
        │ HTTP/GeoJSON distant │      │ + métriques CEL          │
        │ ArcGIS Feature Svc   │      │ + libellés + refreshPolicy│
        │ STAC/WMS/WFS/CSW/CKAN│      │ + permissions (can())    │
        └──────────────────────┘      └────────────┬────────────┘
                                                     │ API analytique structurée
                                                     │ (DuckDB froid / PostGIS chaud)
                                                     ▼
                                          ┌─────────────────────┐
                                          │      WIDGETS        │ encodings (x,y,color,size)
                                          │ chart·map·kpi·table·│ + $expr CEL + events typés
                                          │ pivot·filtre·form·  │
                                          │ contenu éditorial    │
                                          └──────────┬──────────┘
                                                     ▼
             ┌───────────────────────────────────────────────────────────────┐
             │                    APPCONFIG — un seul runtime                 │
             │  gabarits : dashboard · app métier · story · site/portail      │
             │  contexte global : temps × emprise × filtres × sélection       │
             └───────────────────────────────┬───────────────────────────────┘
                                              ▼
      ┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
      │  RUNTIME    │  EXPORTS    │  ALERTES    │  RAPPORTS   │  PORTAIL    │
      │ edit/preview│ CSV/XLSX    │ AlertRule   │ PDF planifié│ site public │
      │ /runtime,   │ (DuckDB     │ (CEL+spatial│ (Playwright │ multi-app,  │
      │ embed WC,   │ COPY TO)    │ , jobs)     │ worker)     │ domaine,    │
      │ MCP, copilote│            │             │             │ DCAT/STAC   │
      └─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

Ce schéma est celui du brainstorm 2026-07-09 (§4.1), **étendu** d'un étage
« PORTAIL » symétrique aux autres sorties (exports/alertes/rapports) — un site
public *consomme* des items (apps, dashboards, datasets, cartes) exactement
comme un dashboard consomme des datasets : même logique de composition, même
sécurité (`can()`), même MCP.

### 5.3 Nouveaux modules du cœur (vue consolidée)

| Module | Porté par | Contenu | État |
|---|---|---|---|
| `datasets` | SP-14 | CRUD datasets partagés, schéma inféré, métriques, refreshPolicy | à construire |
| `analytics` | SP-11 | Pipeline→plan→DuckDB/PostGIS, SQL read-only analyste, exports | à construire |
| `alerts` | SP-15 | AlertRule, évaluation jobs, canaux, journal | à construire |
| `reports` | SP-15 | ReportSchedule, orchestration Playwright, dépôt S3 | à construire |
| `connectors` | SP-6/SP-12/SP-14 | Sources http/arcgis, moissonnage STAC/WMS-WFS/CSW/CKAN | partiel (SP-6 seul acquis) |
| **`sites`** | **SP-16 (nouveau)** | CRUD sites/portails, résolution de domaine, pages dataset public, compteurs d'usage | **absent — proposé** |
| `realtime` | différé | Ingestion MQTT/HTTP, SSE | différé (Q10) |
| `copilot` | transversal | Endpoint chat qui orchestre les outils MCP existants côté serveur, historique de conversation par item | **absent — proposé, voir §7.10** |

### 5.4 Sécurité, gouvernance, multi-tenant

Rien de nouveau à inventer : chaque brique ci-dessus **hérite** de `can()` et
de `audit_log` déjà en place. Points d'attention spécifiques aux nouveaux
modules :
- **Sites publics** : un site est un item comme un autre (publication +
  `can()`) ; le risque nouveau est la **résolution de domaine** (Host header
  routé vers le mauvais tenant) — à traiter comme une frontière de sécurité de
  premier ordre, testée par une matrice domaine×tenant dédiée, symétrique à la
  matrice rôle×action déjà exigée pour SP-1c.
- **Copilote IA embarqué** : n'introduit **aucun nouveau chemin d'autorisation**
  — il orchestre les outils MCP existants avec le token de l'utilisateur
  connecté (jamais un token de service), donc les mêmes 403 s'appliquent ; le
  risque est l'**audit de la conversation** (tout appel d'outil déclenché par
  le copilote reste `actor_kind=agent`, comme le MCP externe).
- **SQL Lab / rôle analyste** : la soupape (A19) reste réservée à un rôle
  explicite, quotas et timeout dès sa première version — pas de SQL libre pour
  tout utilisateur, jamais.

---

## 6. Catalogue fonctionnel recommandé

<a name="6-catalogue-fonctionnel"></a>

Vue consolidée, tous domaines confondus, avec statut et priorité (voir grille
de priorisation en §9 pour la méthode de score).

| Module | Fonctionnalité | Statut | Priorité |
|---|---|---|---|
| **Données** | Collections PostGIS (registre, introspection, CRUD OGC API Features) | ✅ acquis | — |
| | Ingestion GeoJSON/CSV/GPKG/SHP | ✅ acquis | — |
| | Lakehouse GeoParquet + CDC logique | ❌ | P0 |
| | Connecteur HTTP/GeoJSON distant | ❌ | P1 |
| | Connecteur ArcGIS Feature Service (référencement + copie) | ❌ | P1 |
| | Moissonnage STAC / WMS-WFS / CSW / CKAN | ❌ | P1 |
| | Parquet externe déjà sur S3 client (lecture en place) | ❌ | P2 |
| **Sémantique** | Dataset objet de plateforme (schéma, métriques CEL, libellés) | ❌ | P0 |
| | Pipeline de transformation (filter/aggregate/join/derive/pivot) | ❌ | P0 |
| | Analyse spatiale no-code (buffer, intersect, countWithin, H3) | ❌ | P1 |
| | Relations déclarées entre collections | ❌ | P2 |
| **Analytique** | API structurée (DuckDB froid / PostGIS chaud) | ❌ | P0 |
| | SQL Lab (rôle analyste) | ❌ | P1 |
| | Requête visuelle (Filtrer→Joindre→Résumer→Trier) | ❌ | P0 |
| | Downsampling série temporelle (LTTB) | ❌ | P2 |
| **Dataviz** | 10 types ECharts existants | ✅ acquis | — |
| | Encodages champ→canal unifiés (charts + carte) | ❌ | P1 |
| | Sankey/treemap/sunburst/funnel/waterfall/histogramme serveur | ❌ | P1 |
| | KPI card riche (delta, sparkline, seuils CEL) | ❌ | P0 |
| | Table pivot/croisée (agrégation serveur) | ❌ | P1 |
| | Carte analytique (symbologie data-driven, MapConfig complet) | ❌ | P0 |
| | Suggestion de visualisation depuis le schéma | ❌ | P2 |
| **Interaction** | ActionBus (événements→actions, conditions CEL) | ✅ acquis | — |
| | Contexte global temps × emprise × filtres × sélection | ❌ | P0 |
| | Cross-filter par défaut (opt-out) | ❌ | P0 |
| | Drill-down « voir les entités » | ❌ | P1 |
| | Bookmarks / situations partageables (état dans l'URL) | ❌ | P1 |
| | Filtres typés (select/date-range/slider) alimentés par dataset | ❌ | P1 |
| **Apps/formulaires** | Formulaires schema-driven CRUD | ✅ acquis | — |
| | Conteneurs (onglets/modale/tiroir) | ❌ | P1 |
| | Déclencheurs data/timer (`onDataLoaded`, `timer.tick`) | ❌ | P2 |
| | Workflows multi-étapes (approbations) | ❌ | P3 (différé) |
| **Reporting** | Export CSV/XLSX serveur | ❌ | P0 |
| | Export PDF de dashboard (paginé, mise en page) | ❌ | P1 |
| | Rapports planifiés (cron + diffusion email/webhook) | ❌ | P1 |
| | Alertes de seuil (+ prédicats spatiaux) | ❌ | P0 |
| **Portails/sites** | Item `site` (gabarit éditorial + découverte) | ❌ | P0 |
| | Domaine personnalisé par site | ❌ | P2 |
| | Page dataset public (fiche + téléchargement multi-format) | ❌ | P1 |
| | Métriques d'usage (vues, téléchargements) | ❌ | P2 |
| | Discussions/communauté | ❌ | P3 (hors périmètre v1) |
| **Storytelling** | Gabarit narratif (scrollytelling, états figés par chapitre) | ❌ | P1 |
| | Carte qui vole d'une emprise à l'autre au fil du récit | ❌ | P1 |
| **Géospatial avancé** | 3D Tiles (deck.gl) + terrain raster-dem | ❌ | P2 |
| | Impression/export mis en page (Playwright) | ❌ | P1 |
| | Analyse spatiale no-code (voir Sémantique) | ❌ | P1 |
| **Catalogue standard** | API STAC native | ❌ | P1 |
| | Export DCAT-AP | ❌ | P1 |
| **IA** | 10 outils MCP (list/get/create items, sharing, search, features, form-app) | ✅ acquis | — |
| | Outils MCP dataset/analytics (`create_dataset`, `run_analytics_query`, `explain_dataset`) | ❌ | P0 |
| | Copilote de chat embarqué dans le shell | ❌ | P0 |
| | Génération de dashboard par prompt (`create_dashboard_from_prompt`) | ❌ | P1 |
| **Exploitation** | OpenTelemetry + dashboards/SLO packagés | ❌ | P0 (avant trafic public) |
| **Temps réel** | Auto-refresh par intervalle | ❌ | P0 (quick win) |
| | Flux live (SSE/MQTT) | ❌ | P3 (différé, Q10) |

---

## 7. Le builder existant face aux nouveaux usages

<a name="7-builder"></a>

Analyse point par point de la demande initiale (point 6) : ce que le builder
actuel (`shell/src/builder/`) permet déjà, ce qu'il faut adapter, effort
dominant.

### 7.1 Dashboards

**Déjà couvert** à 70 % : grille responsive, 11 widgets, thèmes, variables,
ActionBus. **Manque** : contexte analytique global (§4.3), cross-filter par
défaut, KPI riches, datasets partagés. **Adaptation** : aucune refonte du
moteur de rendu — extension du modèle de config (`DatasetRef`, `AppState`
avec `context`, voir brainstorm §5.2/5.4) et de la bibliothèque de widgets.
C'est le chantier **SP-14**, déjà cadré.

### 7.2 Rapports

**Aujourd'hui absent.** Le runtime existe déjà pour produire un rendu
WYSIWYG (`AppRenderer` en mode `runtime`) : le rapport PDF n'est pas un
deuxième moteur, c'est le **même runtime rendu par Playwright en worker**
plus un `PrintLayout` déclaratif (en-tête/pied, sauts de page, table des
matières). **Adaptation** : nouveau gabarit de config (`PrintLayout`) + worker
dédié (image séparée du cœur pour ne pas alourdir le déploiement standard,
cf. risque déjà noté en A25). C'est **SP-13** (mise en page carte) étendu par
**SP-15** (dashboards paginés).

### 7.3 Portails de données

**Absent, chantier nouveau** (voir §3.9, §5, **SP-16 proposé**). Le builder
n'a *aucune* notion de « façade multi-item » aujourd'hui — chaque item est
son propre runtime isolé. **Adaptation nécessaire** :
- Nouveau type d'item `site`, config `SiteConfig` (sous-type d'`AppConfig` ou
  gabarit dédié — **à trancher en spec**, voir A33 en §9) combinant pages de
  contenu éditorial (héros, texte riche, sections d'images) et **widgets de
  découverte** (galerie filtrable d'items publiés par tag/type/collection).
- Nouveaux widgets de contenu : héros, section riche (markdown/blocs), galerie
  de cartes (grid de vignettes cliquables), fiche dataset (aperçu +
  téléchargement DCAT/CSV/GeoJSON).
- Résolution de domaine (Traefik → routage par `Host`), traité comme
  frontière de sécurité (§5.4).

### 7.4 Catalogues

**Catalogue interne existant** (recherche hybride pgvector) — ce qui manque
est l'**interopérabilité standard** (STAC/DCAT, SP-12) et l'**exposition
publique éditorialisée** (le portail, §7.3). Les deux sont complémentaires :
STAC/DCAT est le contrat *machine* (QGIS, moissonneurs data.gouv.fr) ; le
site/portail est la façade *humaine*. Aucune refonte du catalogue interne
n'est nécessaire — SP-12 et SP-16 sont deux consommateurs du même registre
`items`/`collections`.

### 7.5 Storytelling

**Absent comme gabarit, présent comme briques.** Pages, navigation,
variables, bindings CEL existent déjà — il manque un **gabarit narratif**
au-dessus :
- Mode de navigation séquentiel (page = chapitre, avancement au scroll ou au
  clic « suivant »).
- Chaque chapitre peut figer un **état analytique** (bookmark, dépend de
  SP-14) et une **emprise de carte cible** (la carte « vole » vers l'emprise
  du chapitre — réutilise `map.flyTo`, déjà câblé dans l'ActionBus depuis
  SP-0d3).
- **Adaptation** : un gabarit de galerie (« Story » à côté d'« Application de
  saisie ») + une option de layout « scrollytelling » sur `PageManager`, pas
  de nouveau moteur. Effort dominant : UI de transition/scroll, quasi nul côté
  cœur. Bon candidat de **quick win** (§8, vague 0/1).

### 7.6 Sites web

Recouvre largement §7.3 (portails) : un « site web » GeoStudio est un item
`site` avec un domaine et une navigation propre. La distinction utile est de
**vocabulaire produit**, pas d'architecture : un « portail de données » met en
avant la découverte (galerie, recherche, fiches dataset) ; un « site »
générique met en avant le contenu éditorial (à propos, actualités, contact).
Les deux partagent le même gabarit `SiteConfig` et les mêmes widgets de
contenu — pas de bifurcation technique à prévoir.

### 7.7 Analytics avancés

Couvert par **SP-11 + SP-14**, déjà cadrés en détail dans le brainstorm
(pipeline de transformation, analyse spatiale no-code, requête visuelle, SQL
Lab). Rien à ajouter ici au-delà du renvoi — voir §4.1 du brainstorm 2026-07-09
pour le détail technique complet.

### 7.8 Widgets de datavisualisation

Couvert par **SP-14** (§5.1 du brainstorm) : KPI riche, pivot, nouveaux
ECharts, filtres typés, carte analytique, conteneurs. Le pattern d'extension
(`chartOption.ts` mapping config→option ECharts) est déjà établi et testé —
l'effort dominant est de la config, pas de l'intégration nouvelle.

### 7.9 Workflows low-code/no-code

**Couvert pour la logique légère** (CEL, actions composées avec conditions,
SP-5) — **volontairement différé pour l'orchestration lourde** (workflows
durables multi-étapes, approbations, état persistant inter-session) : c'est
un chantier explicitement listé en « différé » (§9 de la feuille de route,
« workflows durables… briques §13 de la vision »). **Recommandation** :
maintenir ce différé — aucun des personas v1 (agent métier, décideur,
analyste, géomaticien) n'exige un moteur de workflow au sens BPM ; le
introduire prématurément dupliquerait ActionBus/CEL pour un gain flou. À
réévaluer seulement si un persona « gestionnaire de processus métier
formalisé » (permis, instruction de dossiers) devient une cible commerciale
explicite.

### 7.10 IA et copilote

**Le seul point où le builder a besoin d'une brique véritablement nouvelle
sans équivalent dans la feuille de route actuelle.** Le MCP (SP-2/SP-7) donne
à un client externe (Claude Desktop, un agent custom) la capacité d'opérer
GeoStudio ; il ne donne à *aucun utilisateur du shell* une expérience de
copilote. Proposition (à cadrer en spec dédiée, hors périmètre de ce
document) :
- **Panneau de chat dans le builder**, adossé à un nouvel endpoint côté cœur
  qui orchestre les outils MCP **existants** (aucune nouvelle capacité
  d'écriture — le copilote ne fait rien qu'un agent MCP externe ne pourrait
  déjà faire aujourd'hui) avec le token de l'utilisateur connecté.
- Cas d'usage v1 : « crée un widget indicateur du nombre d'incidents ouverts »,
  « ajoute un filtre par commune », « explique ce dataset » — des
  micro-actions sur la config **en cours d'édition**, pas des générations de
  dashboard complet à l'aveugle (le risque produit est la confiance : mieux
  vaut un copilote qui édite fidèlement la config affichée qu'un générateur
  opaque).
- **Ne dépend d'aucun autre SP** pour démarrer (contrairement à ce que
  suggérerait son ambition) : les outils `list_items`/`get_app_config`/
  `save_app_config`/`create_form_app`/`search_catalog` suffisent à un v1 utile.
  Sa version avancée (`create_dataset`, `run_analytics_query`,
  `explain_dataset`, `create_dashboard_from_prompt`) attend logiquement SP-14.
- **Positionnement stratégique** : c'est l'argument différenciant n° 3 du
  produit (§8 du brainstorm — « AI-native par construction ») ; le laisser
  purement externe (MCP seul) revient à donner l'avantage compétitif à
  l'écosystème d'agents généraux plutôt qu'à l'expérience GeoStudio elle-même.

---

## 8. Roadmap 6 / 12 / 24 / 36 mois

<a name="8-roadmap"></a>

Point de départ : 2026-07-14, SP-1→8 clos, SP-9 en cours. Capacité de
référence : 10–25 h/semaine solo (+ agents IA), facteur calendrier ×1,5–2
comme dans la feuille de route. **Principe non négocié, hérité de A27** : ne
pas retarder le chemin critique vers v0.1 (SP-9) ni vers l'observabilité
(SP-10) pour des chantiers analytics/portails — les nouveautés proposées
s'insèrent **après**, avec un réordonnancement argumenté ci-dessous
(**⚠ amendement à A27 proposé**, voir A34 en §9).

### 0–6 mois — finir le socle public, semer les quick wins

| Chantier | Contenu | Statut proposé |
|---|---|---|
| SP-9 | Durcissement v0.1 (licence, CI, install docs, sécurité, démo publique, UI admin collections) | en cours, à terminer sans détour |
| Quick win — Storytelling v0 | Gabarit galerie « Story », navigation séquentielle, `map.flyTo` par chapitre | nouveau, faible effort (§7.5) |
| Quick win — Auto-refresh | `refetchInterval` configurable par source, horodatage de fraîcheur | déjà identifié « vague 0 » du brainstorm |
| Quick win — KPI enrichie | delta/seuils CEL sur `indicator` (sans backend analytique, sur agrégation client existante) | déjà identifié « vague 0 » |
| Copilote IA — v0 | Panneau de chat dans le builder, orchestration des 10 outils MCP existants, micro-actions sur la config en édition | nouveau, ne dépend de rien d'autre |
| Cadrage SP-16 | Brainstorm + spec « Portails & Sites » (comme ce document le préconise) | nouveau, spec seulement, pas d'exécution encore |

### 6–12 mois — observabilité, puis le pivot data platform

| Chantier | Contenu |
|---|---|
| SP-10 | OTel + dashboards/SLO packagés — indispensable avant que la démo publique (SP-9) reçoive du trafic réel |
| SP-11 | CDC logique → GeoParquet, DuckDB in-process, API analytique structurée, SQL read-only analyste — le plus gros pari technique de toute la route, spike de validation en ouverture |
| Datasets — fondations | Modèle `Dataset` (objet de plateforme, A28) posé en fin de SP-11 ou tout début SP-14, pour ne pas laisser l'API analytique sans réceptacle sémantique |

### 12–24 mois — BI géospatiale, portails, storytelling, 3D/print

> **⚠ Amendement à A27 proposé (voir A34)** : lancer **SP-14 avant SP-12/SP-13**.
> Justification : SP-14 (BI géospatiale) démontre la promesse « Analytics
> Platform » du produit et s'appuie directement sur SP-11 tout juste livré ;
> SP-12 (catalogue standard) et SP-13 (3D/print) sont des briques de conformité
> et de richesse cartographique **indépendantes** l'une de l'autre et de
> SP-14, insérables en parallèle ou juste après selon la disponibilité et la
> demande réelle (Q2 toujours ouverte).

| Chantier | Contenu |
|---|---|
| SP-14 | Datasets partagés, pipeline de transformation (dont spatial no-code), contexte global temps×emprise, cross-filter, drill, SQL Lab, widgets analytiques v2 — jalon **M11** |
| **SP-16 (nouveau)** | Item `site`/portail, gabarits éditoriaux + découverte, page dataset public (branchée sur DCAT dès que SP-12 existe, sinon export CSV/GeoJSON simple en v1), domaine personnalisé |
| SP-12 | STAC natif, export DCAT-AP, moissonnage (STAC→ArcGIS FS→WMS/WFS→CSW→CKAN) — alimente directement SP-16 |
| SP-13 | 3D Tiles + terrain, impression/export mis en page (Playwright) — prérequis partiel de SP-15 |
| Storytelling v1 | États analytiques figés par chapitre (dépend de SP-14/bookmarks) | 
| Copilote IA — v1 | Outils `create_dataset`/`run_analytics_query`/`explain_dataset`/`create_dashboard_from_prompt` branchés au panneau de chat |

### 24–36 mois — decision support, connecteurs stratégiques, durcissement continu

| Chantier | Contenu |
|---|---|
| SP-15 | AlertRule, ReportSchedule, exports secs — jalon **M12**, dépend de SP-13/SP-14 |
| Connecteur ArcGIS Feature Services | Référencement (dataset SP-14) + copie (moissonnage SP-12) — pont de sortie pour les collectivités équipées Esri (A22 déjà amendé, position 2) |
| Portail — communauté (évalué, pas engagé) | Discussions/followers **seulement si** une demande réelle émerge (§3.9 : hors périmètre v1 par défaut) |
| Temps réel cran 1 | SSE/MQTT — **seulement si** Q10 tranche en ce sens |
| Réévaluations différées | Iceberg (versioning de données), DuckDB-WASM navigateur, connecteurs SQL externes — triggers documentés, pas de travail engagé sans demande réelle |
| Durcissement continu | Sécurité (revues authz périodiques), performance (benchmarks de charge à 10⁶+ lignes), gouvernance des extensions tierces (marketplace, signature — si l'écosystème SDK WC a effectivement des tiers actifs) |

### Vue d'ensemble (diagramme temporel simplifié)

```
mois   0        6        12       18       24       30       36
       ├────────┼────────┼────────┼────────┼────────┼────────┤
SP-9   ███ v0.1
Copilote v0 ██
Story v0    ██
SP-10           ████ OTel
SP-11              ████████ Lakehouse/DuckDB
SP-14                       ████████████ Analytics UX (M11)
SP-16                       ████████ Portails & Sites
SP-12                                ████████ Catalogue standard
SP-13                                ████████ 3D & print
Story v1                                    ████
Copilote v1                                 ████████
SP-15                                                ████████ Alertes/reporting (M12)
ArcGIS FS                                                     ████
```

---

## 9. Priorisation des fonctionnalités

<a name="9-priorisation"></a>

### 9.1 Méthode

Score simple **Impact (1–5) × Confiance (1–5) / Effort (1–5)** — variante RICE
allégée adaptée à un pilotage solo (pas de volumétrie utilisateur fiable à ce
stade). Effort noté selon les tranches déjà utilisées par la feuille de route
(S/M/L/XL → 1/2/3/4 sur l'échelle d'effort, XL=5 pour les plus lourds comme le
CDC).

| Fonctionnalité | Impact | Confiance | Effort | Score | Rang |
|---|---|---|---|---|---|
| API analytique structurée (DuckDB/GeoParquet, SP-11) | 5 | 4 | 5 | 4,0 | 1 |
| Dataset partagé + métriques (SP-14, A28) | 5 | 5 | 3 | 8,3 | **2** |
| Contexte global temps×emprise + cross-filter (SP-14, A29) | 5 | 4 | 3 | 6,7 | 3 |
| Copilote IA embarqué v0 | 4 | 4 | 1 | 16,0 | **1 (quick win)** |
| Auto-refresh par source | 3 | 5 | 1 | 15,0 | quick win |
| KPI enrichie (delta/seuils, sans backend) | 3 | 5 | 1 | 15,0 | quick win |
| Storytelling v0 (gabarit galerie) | 3 | 4 | 1 | 12,0 | quick win |
| Alertes de seuil (SP-15) | 4 | 3 | 3 | 4,0 | 4 |
| Rapports planifiés PDF (SP-15) | 4 | 3 | 3 | 4,0 | 4 |
| Exports CSV/XLSX serveur (SP-15, A30) | 4 | 4 | 2 | 8,0 | 3 |
| Portail/site public (SP-16) | 4 | 3 | 3 | 4,0 | 4 |
| STAC natif + DCAT-AP (SP-12) | 3 | 3 | 3 | 3,0 | 5 |
| Moissonnage (STAC/ArcGIS FS/WMS-WFS/CSW/CKAN) | 3 | 2 | 4 | 1,5 | 6 |
| Analyse spatiale no-code (buffer/H3, SP-14) | 4 | 3 | 3 | 4,0 | 4 |
| 3D Tiles + terrain (SP-13) | 2 | 3 | 3 | 2,0 | 6 |
| Impression/export mis en page (SP-13) | 3 | 3 | 3 | 3,0 | 5 |
| Observabilité OTel (SP-10) | 4 | 4 | 2 | 8,0 | **3 (avant trafic public)** |
| Connecteur ArcGIS Feature Services | 3 | 2 | 3 | 2,0 | 6 |
| Workflows multi-étapes (BPM) | 2 | 1 | 4 | 0,5 | différé |
| Temps réel (SSE/MQTT) | 2 | 1 | 5 | 0,4 | différé |

**Lecture** : les quick wins (copilote v0, auto-refresh, KPI enrichie,
storytelling v0) offrent le meilleur rapport valeur/effort et **ne dépendent
d'aucun autre chantier** — ils doivent être menés en parallèle de SP-9 sans
attendre la fin de la feuille de route actuelle, cohérent avec la « vague 0 »
déjà actée dans le brainstorm 2026-07-09. Le socle analytique (SP-11) reste le
chantier le plus lourd et le plus risqué (score plus bas malgré son impact,
à cause de l'effort et de la confiance technique moindre sur le CDC) — aucune
raison n'existe cependant de le contourner : il est le prérequis structurel de
la moitié du catalogue §6.

### 9.2 Arbitrages proposés par ce document (A31–A36)

À l'image du format déjà utilisé en §7/§8 de la feuille de route — options,
avantages/inconvénients, recommandation — pour compléter A1–A30 sans les
modifier.

> **Statut (2026-07-14)** : arbitrages tranchés par Tanguy et consignés dans
> la feuille de route (§7/§8), qui fait désormais foi — **A31, A33, A34, A35,
> A36** validés dans le sens recommandé ci-dessous, complétés à la validation
> par **A37** (storytelling en quick win immédiat, indépendant de SP-16) et
> **A38** (fonctions communautaires des portails différées). **A32** (copilote
> IA embarqué = client MCP interne) reste ouvert, à trancher au cadrage du
> chantier copilote. Le texte ci-dessous est conservé tel que proposé, comme
> matériau d'analyse.

#### A31 — Le portail/site est-il un `AppConfig` ou un type de config séparé ?

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) `SiteConfig` = sous-gabarit d'`AppConfig`** (même schéma de base, mode `site` sur `AppRenderer`) | Un seul runtime (règle n° 3) ; hérite instantanément de thèmes/pages/partage/MCP | Le schéma `AppConfig` doit rester générique (widgets de contenu = nouveaux widgets, pas un fork de schéma) |
| (b) Nouveau type de config entièrement séparé | Liberté de modéliser une navigation multi-item différente | Deuxième runtime (viole la règle n° 3) ; double la surface de maintenance et de génération MCP |

**Recommandation : (a).**

#### A32 — Le copilote IA embarqué appelle-t-il le MCP en interne ou réimplémente-t-il la logique métier ?

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Le copilote est un client MCP interne** (même transport, mêmes 10+ outils, token utilisateur) | Zéro divergence de comportement entre agent externe et copilote embarqué ; chaque nouvel outil MCP profite automatiquement au copilote | Latence d'un aller-retour transport supplémentaire (négligeable en local, même process) |
| (b) Le copilote appelle directement les fonctions Python internes | Plus rapide à écrire au départ | Deux chemins de code pour la même action = dérive garantie (même leçon que l'échec évité en revue finale SP-7 sur `create_form_app`) |

**Recommandation : (a)** — cohérent avec la discipline déjà démontrée par le
projet (SP-8c a justement fermé un trou où les outils MCP contournaient une
validation présente côté REST).

#### A33 — Domaine personnalisé par site : à quel stade de maturité ?

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) V1 sans domaine personnalisé** (site accessible sous un chemin du shell, `/sites/{slug}`) | Livrable rapidement, zéro complexité Traefik/TLS | Moins impressionnant face à ArcGIS Hub pour une démo commerciale |
| (b) Domaine personnalisé dès v1 | Argument de vente fort immédiat | Complexité TLS/DNS/routage multi-tenant à durcir avant toute exposition publique — risque de sécurité si mal isolé (confusion de tenant par Host) |

**Recommandation : (a)**, domaine personnalisé en v2 du module une fois le
routage multi-tenant par chemin éprouvé et audité.

#### A34 — Ordre relatif SP-12/SP-13/SP-14/SP-15/SP-16 (⚠ amendement proposé à A27)

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) SP-14 immédiatement après SP-11, puis SP-16/SP-12/SP-13 en parallèle ou dans un ordre guidé par la demande réelle, SP-15 en dernier** | Démontre la promesse BI dès que le socle analytique existe ; le portail (SP-16) et le catalogue standard (SP-12) sont indépendants entre eux et de SP-14, donc reséquençables sans risque technique | SP-13 (3D/print) retarde d'autant, alors que SP-15 en dépend partiellement — géré en gardant SP-15 dernier |
| (b) Ordre A27 originel (OTel→Lakehouse→STAC→3D/print→Analytics→Alertes) | Conformité stricte à la décision déjà prise | Retarde la démonstration de la promesse « Analytics Platform » de deux SP complets (SP-12+SP-13) sans raison technique — seulement une raison d'ordre historique |

**Recommandation : (a)**, **à valider explicitement par Tanguy** avant le
lancement du premier des cinq SP concernés (cohérent avec la clause déjà
posée par Q-A3 : « l'ordre relatif reste à arbitrer avant le lancement du
premier d'entre eux »). Ce document propose la réponse à Q-A3, il ne la
tranche pas seul.

#### A35 — Faut-il un SP-16 dédié, ou le portail est-il un sous-lot de SP-9/SP-12 ?

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) SP-16 dédié** (comme proposé §8) | Périmètre net, critères d'acceptation propres, évite de diluer SP-9 (déjà en cours) ou SP-12 (déjà chargé de 4-5 connecteurs) | Un SP de plus à la feuille de route (effort estimé L, ~80–130 h par analogie avec SP-4/SP-8) |
| (b) Sous-lot de SP-12 (« le catalogue devient aussi un portail ») | Un SP de moins à nommer | SP-12 déjà à risque d'étalement (note du §10 risques de la feuille de route : « 4 connecteurs = risque d'étalement ») — y ajouter un portail entier l'aggrave |

**Recommandation : (a).**

#### A36 — Storytelling : widget dédié ou mode de page ?

| Option | Avantages | Inconvénients |
|---|---|---|
| **(a) Mode de layout sur `PageManager`** (une app peut activer une navigation séquentielle scrollée sur ses pages existantes) | Zéro nouveau widget ; toute app peut devenir story a posteriori ; cohérent avec « les archétypes sont tous le même AppConfig » (§3.2 brainstorm) | Le mode doit rester optionnel et non intrusif pour ne pas complexifier `PageManager` pour le cas dashboard classique |
| (b) Nouveau widget conteneur « Story » qui encapsule ses propres sous-pages | Isolation du code, pas de risque de régression sur `PageManager` | Duplique la notion de page ; une story n'hérite pas gratuitement du thème/des variables de l'app parente |

**Recommandation : (a).**

---

## 10. Recommandations stratégiques

<a name="10-recommandations"></a>

1. **Ne rien casser du chemin critique.** SP-9 (v0.1 publique) et SP-10
   (observabilité) restent la priorité absolue avant tout trafic réel — aucune
   des recommandations de ce document ne justifie de les retarder.
2. **Lancer les quick wins de la « vague 0 » sans attendre**, y compris le
   copilote IA v0 et le storytelling v0 proposés ici : impact élevé, effort
   faible, aucune dépendance sur SP-11+. Un copilote embarqué visible tôt vaut
   plus, en termes de démonstration produit, que dix outils MCP invisibles à
   l'utilisateur final.
3. **Faire trancher Q-A3 maintenant plutôt qu'« au moment venu »** — ce
   document fournit l'analyse (A34) qui manquait pour statuer ; la remettre à
   plus tard coûte de l'incertitude de planification sans bénéfice.
4. **Ouvrir formellement le chantier Portails & Sites (SP-16)** — c'est
   l'unique brique du périmètre demandé qui n'a **aucun** foyer dans la
   feuille de route actuelle, alors que c'est l'argument commercial le plus
   direct face à ArcGIS Hub/CKAN pour la cible collectivités (persona n° 8).
5. **Garder le discours produit en deux temps** (déjà décidé en 2026-07-09,
   §9 du brainstorm : « le README v0.1 reste ‘geospatial app builder' ») —
   étendre ce principe : le README v1 (post-SP-14/16) peut assumer « Analytics
   Platform **et** portail de données », mais seulement une fois les deux
   livrés et démontrables, jamais en promesse anticipée.
6. **Ne pas reconstruire Superset/ArcGIS Hub en moins bien.** Chaque nouvelle
   fonctionnalité de ce catalogue doit se justifier par le fil rouge spatial
   (« voir/comprendre/agir sur un territoire » — brainstorm §9) ou par
   l'obligation réglementaire des collectivités (open-data) ; à défaut, elle
   va au backlog, pas dans un SP.
7. **Traiter le copilote IA comme un client MCP interne, jamais comme un
   deuxième chemin de code** (A32) — c'est la garantie que chaque futur outil
   MCP (dataset, analytics, reporting) profite automatiquement à l'expérience
   embarquée sans travail de synchronisation supplémentaire.
8. **Différer sciemment** : workflows BPM multi-étapes, temps réel en flux,
   connecteurs SQL externes, Iceberg, communauté/discussion sur les portails,
   marketplace d'extensions. Chacun a un test de déclenchement documenté
   (demande réelle explicite) — les réévaluer à ce test, pas par défaut.
9. **Mesurer avant d'étendre.** Aucun des personas n'a encore d'utilisateur
   réel identifié (Q2 toujours ouverte) — chaque arbitrage de ce document
   reste une hypothèse de conception à confronter aux premiers déploiements
   réels dès qu'ils existent, en particulier l'ordre A34 et le périmètre v1
   du portail (A33/A35).
10. **Continuer le subagent-driven-development avec revue finale de branche**
    pour les chantiers larges (SP-11, SP-14, SP-16) — c'est la méthode qui a,
    documenté dans `CLAUDE.md`, trouvé et corrigé les défauts les plus sérieux
    du projet à ce jour (SP-6a, SP-6b, SP-7, SP-8c) ; SP-14 en particulier
    (le plus large de la route selon son propre risque documenté) exige des
    sous-phases livrables strictement délimitées.

---

## 11. Risques transverses

<a name="11-risques"></a>

Complète (sans les répéter) les risques déjà consignés dans la feuille de
route (§10) et le brainstorm (§9).

| Risque | Gravité | Garde-fou |
|---|---|---|
| Le SP-16 (portail) dilue encore la route d'un solo à 10–25 h/sem | ★★★ | Périmètre v1 volontairement étroit (A33 : pas de domaine personnalisé v1, pas de communauté v1) ; critères E2E fermés dès la spec |
| Le réordonnancement A34 (SP-14 avant SP-12/13) laisse le catalogue standard/3D en jachère plus longtemps que prévu | ★★ | Assumé et documenté ; réversible si Q2 révèle un besoin 3D/catalogue urgent avant BI |
| Le copilote IA embarqué déçoit s'il tente de « tout générer » sans fiabilité | ★★ | Périmètre v0 délibérément étroit : micro-actions sur la config en cours d'édition, jamais de génération de dashboard complet à l'aveugle tant que la confiance n'est pas établie |
| Confusion de tenant par résolution de domaine (portails) | ★★★ (sécurité) | Matrice de test domaine×tenant dédiée avant toute activation, symétrique à la matrice rôle×action de SP-1c ; domaine personnalisé différé en v2 (A33) le temps de la roue durcir |
| Le portail devient un « réseau social » de la donnée sans modération prévue | ★★ | Discussions/followers explicitement hors périmètre v1 (§3.9) — seulement sur demande réelle et avec un plan de modération explicite |
| Storytelling perçu comme gadget si détaché du reste du produit | ★ | Traité comme mode de `PageManager` (A36), pas comme produit à part — coût marginal, pas de risque d'enlisement dédié |

---

## 12. Annexes

<a name="12-annexes"></a>

### 12.1 Sources consultées

- `CLAUDE.md` (état d'avancement arrêté au 2026-07-13/14).
- `docs/vision/2026-07-04-feuille-de-route-geostudio.md` (référence
  opérationnelle : phasage SP-1→15, arbitrages A1–A30, jalons M1–M12).
- `docs/vision/2026-07-09-brainstorm-geostudio-analytics-platform.md`
  (benchmark 11 produits, architecture analytique cible, A28–A30).
- `docs/vision/2026-07-04-comparatif-projet-actuel-vs-vision.md` (choix de
  l'option C, décisions produit §9).
- `docs/superpowers/specs/2026-07-13-sp9-gestion-collections-design.md`
  (chantier en cours au moment de la rédaction).
- Code : `shell/src/builder/` (widgets, `AppRenderer`, `ActionBus`, `expr.ts`,
  SDK Web Components), `shell/src/api/` (`ItemClient`), `core/app/*`
  (modules : items, sharing, configs, collections, ingestion, search,
  extensions, mcp, auth, tenants, users, audit, features, public),
  `shell/package.json`, `core/pyproject.toml`, `README.md`.

### 12.2 Glossaire rapide

- **`AppConfig`** : document JSON déclaratif décrivant une app/dashboard/site
  (pages, widgets, variables, thème, actions) — le seul contrat que rend
  `AppRenderer`.
- **CEL (Common Expression Language)** : langage d'expression sandboxable,
  arbitrage A8, utilisé pour bindings, conditions, métriques, alertes.
- **Dataset (A28)** : nouveau type d'item — source + pipeline de
  transformation + métriques nommées, objet de plateforme catalogué et
  partagé.
- **`can(user, action, object)`** : porte d'autorisation unique du cœur (A1).
- **MCP (Model Context Protocol)** : protocole d'opérabilité par agent IA,
  module du cœur (A13), 10 outils v0/v1 déjà exposés.
- **RRF (Reciprocal Rank Fusion)** : méthode de combinaison des scores
  trigram/vecteur utilisée par la recherche hybride (SP-7).
- **A1…A36** : arbitrages techniques numérotés — A1–A30 dans la feuille de
  route existante, A31–A36 proposés par ce document (§9.2).

---

*Document rédigé le 2026-07-14 sur la base de l'état du dépôt à cette date
(branche `dev`, SP-1→8 clos, SP-9 en cours). Il complète — sans les modifier —
la feuille de route 2026-07-04/09 et le brainstorm Analytics Platform
2026-07-09. Les arbitrages proposés en §9.2 ont été **validés par Tanguy le
2026-07-14** et déclinés le même jour dans la feuille de route (A31/A33–A38,
SP-16, jalon M13, quick win Storytelling + specs associées) — conformément à
la règle du projet (« un arbitrage ne se rediscute pas en session ; s'il doit
changer, on met à jour le document explicitement »). Seul A32 (copilote IA
embarqué) reste une proposition ouverte, à trancher au cadrage de ce
chantier.*
