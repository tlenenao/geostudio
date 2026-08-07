# SP-16a — Export serveur CSV/XLSX/GeoJSON/GPKG (design)

> **Date : 2026-08-07 · Statut : validé (brainstorm)**
> Première sous-partie de **SP-16 — Alertes & reporting** (feuille de route,
> jalon **M12**, brainstorm Analytics Platform 2026-07-09 §4.6/§7 vague 2,
> arbitrage **A30** — « export sec CSV/XLSX en SP-16, gabarits PDF
> différés »). SP-16 est trop large pour un plan unique (comparable à
> SP-14/SP-15, découpés en sous-parties) ; ce document ne couvre que le
> socle : l'export serveur d'un dataset, sans planification ni diffusion.
> Découpe validée avec Tanguy : **16a — export serveur** (ce document),
> **16b — `ReportSchedule`** (rapports planifiés, réutilise l'export de
> 16a), **16c — `AlertRule`** (alertes). PDF de dashboards paginés reste
> hors périmètre de toute la chaîne 16a-c (dépend du worker Playwright de
> SP-17, non lancé — contrainte structurelle documentée dans la feuille de
> route, ligne 213).
>
> Références : feuille de route (§SP-16, A30) · brainstorm Analytics
> Platform (`2026-07-09-brainstorm-geostudio-analytics-platform.md` §4.6
> Reporting & diffusion, §7 roadmap vague 2) · `CLAUDE.md` (règles
> d'architecture #1-4, arbitrages figés) · SP-11b (`app.analytics.aggregate`,
> patron DuckDB éphémère par requête) · SP-14a/SP-14k (dataset objet de
> plateforme, sources `collection`/`arcgis`) · SP-14d (drill « voir les
> entités », résolution de filtres réutilisée côté widget) · SP-15d
> (patron `COPY ... TO ... FORMAT GDAL DRIVER GPKG`, extension `spatial`
> DuckDB déjà chargée par `open_connection`) · SP-3b (`GET
> /collections/{id}/items`, OGC API Features Part 1) · SP-12d (`GET
> /datasets/{id}/arcgis/items`, `live_query.translate_features_query`
> demandant déjà `f=geojson`).

## 1. Objectif & non-buts

**Objectif.** Permettre l'export serveur d'un dataset (collection ou
arcgis) en CSV, XLSX, GeoJSON ou GPKG, respectant les mêmes permissions
`can()` que la lecture du dataset, audité, déclenché à la demande
(téléchargement synchrone) depuis un widget analytique ou la page d'édition
du dataset. C'est la brique atomique que SP-16b (rapports planifiés)
réutilisera comme corps de son export planifié, plutôt qu'une nouvelle
implémentation.

**Constat d'architecture qui cadre tout ce document.** Le contrat
`/aggregate` existant (`AggregateRequestBody`) est une API **GROUP
BY/mesures** : elle ne renvoie jamais de géométrie, seulement des lignes
attributaires. La géométrie par entité n'existe que sur le chemin `items`
(OGC API Features côté collection, `f=geojson` côté arcgis). « Export
agrégé » (CSV/XLSX) et « export d'entités brutes » (GeoJSON/GPKG) sont donc
**deux modes distincts**, chacun réutilisant un contrat de requête déjà
existant — pas une seule opération paramétrée par un format.

**Non-buts explicites** (reportés à SP-16b/16c ou hors périmètre de toute
la chaîne 16) :

- `ReportSchedule`, planification cron, livraison email/webhook, S3
  présigné — c'est SP-16b.
- `AlertRule`, évaluation périodique, seuils, canaux de notification —
  c'est SP-16c.
- Export PDF de dashboards paginés — dépend du worker Playwright de SP-17,
  non lancé (contrainte structurelle actée dans la feuille de route).
- Export asynchrone / gros volumes au-delà du plafond synchrone (§4) — non
  construit ici ; si un besoin réel apparaît, réutiliser l'infra job+S3 que
  SP-16b construira, plutôt que la dupliquer par anticipation.
- Outil MCP dédié — un fichier binaire téléchargé est peu naturel pour un
  agent MCP qui manipule du JSON ; réexaminé si un besoin agent concret
  apparaît.
- UI de filtres sur `DatasetEditPage` — l'export y est toujours non filtré
  (aperçu/vérification par l'auteur) ; les filtres ne s'appliquent que
  depuis un widget, où ils sont déjà résolus par le contexte analytique.

Le modèle reste additif : rien ici ne doit devoir être défait pour
construire SP-16b/16c par-dessus.

## 2. API cœur — quatre routes, deux modules, aucun dispatcher unifié

Le contrat `/aggregate` est déjà scindé en deux routes selon la source du
dataset (`app.features` pour collection, `app.harvest` pour arcgis) plutôt
qu'unifié par un dispatcher — le contrat d'imports en couches (`app.harvest`
peut importer `app.features`/`app.analytics`, jamais l'inverse) l'impose.
L'export suit exactement le même patron :

| Route | Module | Mirrors | Mode |
|---|---|---|---|
| `POST /collections/{id}/export?format=csv\|xlsx` (body `AggregateRequestBody`) | `app.features` | `/collections/{id}/aggregate` | agrégé |
| `POST /datasets/{id}/arcgis/export?format=csv\|xlsx` (body `AggregateRequestBody`) | `app.harvest` | `/datasets/{id}/arcgis/aggregate` | agrégé |
| `GET /collections/{id}/export/items?format=csv\|xlsx\|geojson\|gpkg` (query = filtres/bbox comme `items`) | `app.features` | `/collections/{id}/items` | entités brutes |
| `GET /datasets/{id}/arcgis/export/items?format=csv\|xlsx\|geojson\|gpkg` (query = filtres/bbox) | `app.harvest` | `/datasets/{id}/arcgis/items` | entités brutes |

Précision découverte en planification (writing-plans) : le mode agrégé n'a de
sens qu'avec un `groupBy` (le contrat `/aggregate` renvoie toujours au moins
une ligne `Total`, jamais « toutes les lignes ») — il ne peut donc pas servir
un export « aperçu complet, non filtré » comme celui de `DatasetEditPage`
(§6). Le mode entités brutes sert donc **aussi** le CSV/XLSX (colonnes
attributaires aplaties depuis `feature.properties`, géométrie ignorée),
réutilisant les mêmes fonctions de sérialisation `rows_to_csv`/`rows_to_xlsx`
que le mode agrégé — pas de nouveau code, juste un enum de formats plus
large sur la route `items`. `DatasetEditPage` et les widgets de type
« table »/liste passent donc toujours par le mode entités brutes (CSV/XLSX
compris) ; seuls les widgets chart/kpi (fondamentalement agrégés) utilisent
le mode agrégé, limité à CSV/XLSX.

Aucune nouvelle table, aucun nouveau `kind` de `BuilderConfig` — l'export
est une opération de lecture pure sur un dataset déjà résolu, pas un objet
de plateforme.

## 3. Permissions & audit

Chaque route réutilise **sans modification** le contrôle d'accès de sa
route homologue :

- Collection : `can()` read sur la collection (même dépendance
  `get_readable_collection`/`_require_collection_read` que `/aggregate` et
  `/items`).
- Arcgis : double vérification dataset-item + couche arcgis (même
  `_resolve_arcgis_dataset` que `/datasets/{id}/arcgis/aggregate` et
  `/datasets/{id}/arcgis/items`).

Chaque export réussi écrit une entrée `audit_log`
(`action="export.run"`, `object_type="collection"|"item"`, payload
`{format, mode: "aggregate"|"items"}`), conformément à l'exigence
transverse du brainstorm (§4.7 : « chaque exécution de requête analytique,
export, envoi de rapport, déclenchement d'alerte → `audit_log` »).

## 4. Limites & erreurs

- **Mode agrégé** : pas de plafond spécifique — même volume qu'un
  `/aggregate` classique (déjà borné par le nombre de groupes résultants).
- **Mode entités brutes** : pagine à travers `items`/`arcgis items` jusqu'à
  un plafond dur de **10 000 entités**. Au-delà, réponse `413` explicite
  (« affinez vos filtres ») plutôt qu'un export tronqué silencieux — pas de
  troncature muette qui produirait un fichier incomplet sans avertir
  l'utilisateur.
- Format non reconnu dans `?format=` → `400`.
- Erreurs de filtre/géométrie/service arcgis indisponible → mêmes codes
  (`400`/`502`) que les routes `aggregate`/`items` existantes, propagés tels
  quels (aucune nouvelle classe d'erreur).

## 5. Sérialisation

Format HTTP de sortie : `Content-Disposition: attachment;
filename="<slug>-<timestamp>.<ext>"` (`slug` = titre de l'item
dataset/collection translittéré, repli sur l'id si titre vide) +
`Content-Type` dédié (`text/csv`,
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
`application/geo+json`, `application/geopackage+sqlite3`).

- **CSV** — `csv.writer` (stdlib) sur un `io.StringIO`. En mémoire, aucun
  fichier temporaire.
- **GeoJSON** — `json.dumps` direct de la `FeatureCollection` déjà
  assemblée par pagination. En mémoire.
- **XLSX** — `openpyxl.Workbook` (**nouvelle dépendance**
  `core/pyproject.toml` — aucune dépendance XLSX n'existe encore dans le
  cœur), une feuille, en-têtes = clés du premier row, `.save()` sur un
  `io.BytesIO`. En mémoire, aucun fichier temporaire. Choix délibéré contre
  l'extension communautaire DuckDB `excel` : sa capacité d'écriture n'est
  pas vérifiable avec confiance depuis ce contexte, alors qu'`openpyxl` est
  un choix mûr, standard et déterministe.
- **GPKG** — seul format nécessitant un passage disque (DuckDB `COPY ...
  TO` écrit sur le système de fichiers). `tempfile.TemporaryDirectory()`
  **indépendant** du volume `/scratch` de SP-15d (pas de dépendance à
  `CORE_ETL_ENABLED` — l'export n'est pas une capacité togglable, c'est une
  fonctionnalité de base comme `/aggregate`/`items`). Séquence : écrire la
  `FeatureCollection` en `.geojson` scratch → `CREATE TABLE t AS SELECT *
  FROM ST_Read('scratch.geojson')` → `COPY t TO 'out.gpkg' WITH (FORMAT
  GDAL, DRIVER 'GPKG', SRS 'EPSG:4326')` (extension `spatial` déjà chargée
  par `open_connection`, SRS toujours WGS84 car GeoJSON l'impose) → lire les
  bytes → nettoyage automatique par le context manager.

**Pas de nouvelle capacité/flag.** Contrairement à SP-15 (ETL) ou SP-15d
(sidecar QGIS), l'export n'est gated par rien de nouveau — mêmes garanties
que `/aggregate` et `/items` aujourd'hui.

## 6. Shell — widgets & DatasetEditPage

**Widgets (chart/table/kpi, mode runtime).** Bouton « Exporter » dans la
toolbar existante du widget, menu déroulant des formats disponibles :

- CSV/XLSX toujours proposés (mode agrégé) — réutilisent **tel quel** le
  corps de requête déjà résolu par le widget pour son propre rendu (mêmes
  filtres/contexte global temps×emprise×cross-filter que ce qui est
  affiché à l'écran).
- GeoJSON/GPKG proposés **seulement si le dataset a une colonne géométrie**
  (information déjà connue via l'introspection de schéma SP-14a — pas de
  nouvel appel réseau pour le savoir) et réutilisent la résolution de
  filtres déjà construite par le drill « voir les entités » (SP-14d) pour
  bâtir la requête `items`.

Clic sur un format → téléchargement direct (lien blob), aucun état
supplémentaire à gérer.

**`DatasetEditPage`.** Section « Export » : mêmes formats disponibles selon
géométrie, export **non filtré** (voir non-but §1).

## 7. Tests

- **Cœur (pytest, TDD)** : tests table-driven par route × format
  applicable (4 routes × formats), permissions (403 sans accès lecture),
  plafond 10 000 → 413, format inconnu → 400, écriture `audit_log`
  vérifiée après chaque export réussi.
- **Shell (Vitest)** : composant bouton d'export — menu conditionnel selon
  géométrie du dataset, corps/query envoyé au bon endpoint selon le format
  choisi.
- **E2E (Playwright, obligatoire — feature visible, CLAUDE.md)** : nouvelle
  spec `dataset-export.spec.ts` — exporter un widget chart en CSV depuis une
  app en mode runtime, exporter depuis `DatasetEditPage` en XLSX, vérifier
  le téléchargement (event `download` Playwright). Les specs E2E existantes
  restent vertes sans modification (aucun changement de schéma de config).

## 8. Risques

| Risque | Garde-fou |
|---|---|
| `openpyxl` est une dépendance nouvelle, surface d'attaque/maintenance en plus | Bibliothèque mûre et largement utilisée, usage en écriture pure (pas de parsing de fichiers XLSX non fiables en entrée) |
| Export GPKG lent/coûteux sur de gros volumes | Plafond dur 10 000 entités (§4) — au-delà, erreur explicite plutôt que dégradation silencieuse |
| Confusion entre les deux modes (agrégé vs entités brutes) côté auteur du widget | Menu d'export n'affiche que les formats pertinents selon le mode implicite (CSV/XLSX toujours, GeoJSON/GPKG seulement si géométrie) — pas de format qui échoue silencieusement |
| Duplication future avec SP-16b si mal isolé | La sérialisation (§5) est conçue comme fonctions réutilisables indépendantes des routes REST, pour que SP-16b les appelle directement plutôt que de refaire un appel HTTP interne |
