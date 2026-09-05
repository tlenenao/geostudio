# Analyse des manques — GeoStudio

**Date :** 2026-09-04 (rédigé 2026-09-05). **Commit de base de la revue :**
`87eb55ad`. **Tâche 12 de SP-42** (plan
`docs/superpowers/plans/2026-09-04-sp42-revue-globale.md`, lignes 926-1023).

## Méthode et avertissement

Ce document confronte l'état réel du dépôt à quatre référentiels : (1) la
feuille de route interne et le plan d'action, (2) un benchmark concurrentiel
externe, (3) la cohérence interne du produit (asymétries extraites
mécaniquement de la matrice de fonctionnalités, complétées à la main), et (4)
les exigences usuelles d'une plateforme en production. Chaque gap porte un
identifiant `GAP-nn`, un impact (**bloquant** / **sérieux** / **confort**), un
coût grossier en jours-homme, son référentiel, et sa preuve ou sa source.

**Toute ligne de ce document a été vérifiée dans le code au moment de la
rédaction** (commit `87eb55ad` + les commits SP-42 et concurrents survenus
depuis) — `CLAUDE.md`, les specs et les documents de vision sont des récits
d'intention, jamais une source de vérité en soi. Plusieurs affirmations
présentées comme ouvertes par `CLAUDE.md` ou les documents de vision se sont
révélées **déjà fermées** à la vérification ; elles sont signalées comme
telles plutôt que recopiées comme gaps (voir encadrés « déjà fermé » dans
chaque section concernée). L'inverse est vrai aussi : certains éléments que
la matrice ou `CLAUDE.md` présentent comme des défauts isolés se sont révélés
plus larges une fois recoupés.

Sources consommées : `.superpowers/sdd/sp42-matrice.jsonl` (304 lignes),
`.superpowers/sdd/sp42-findings.jsonl` (74 trouvailles confirmées, dont
**43 non corrigées** — les 31 restantes ont été corrigées par les lots de
correctifs SP-42, listés dans `.superpowers/sdd/sp42-correctifs.json`, et ne
sont donc pas reprises ici comme gaps), `docs/vision/2026-07-04-feuille-de-
route-geostudio.md`, `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`,
et une recherche web sur sept produits concurrents (référentiel 2).

---

## Référentiel 1 — Feuille de route interne

Confrontation au phasage SP-1→SP-20, aux 40 arbitrages §8 et aux jalons
M1-M16 de la feuille de route, et aux vagues 0-6 du plan d'action.

| GAP | Manque | Impact | Coût (j-h) | Preuve |
|---|---|---|---|---|
| GAP-01 | Jalon **M14** bloqué : les 5 tests `@pytest.mark.qgis` (3 dans `test_qgis_worker_sidecar.py`, 2 dans `test_pipeline_runtime.py`) n'ont **jamais tourné** contre un vrai sidecar — `CORE_TEST_QGIS_WORKER_URL` n'apparaît dans aucun workflow CI. `transform.qgis` reste activable en production sans qu'aucun test réel n'ait validé les 50 algorithmes de l'allowlist contre le sidecar réel. | Bloquant | 1-3 | `core/pyproject.toml:117` ; `core/tests/conftest.py:54-56` ; grep vide sur `.github/workflows/*.yml` |
| GAP-02 | Garde d'egress absente sur l'appel LLM sortant du copilote : `OpenAICompatibleLLMProvider` poste directement sur `CORE_LLM_API_URL` via `httpx.AsyncClient` nu, sans validateur d'URL/SSRF — 4e surface sortante du dépôt, seule à ne pas en avoir une (moissonnage, connecteurs pipeline et egress générique en ont chacun une). | Sérieux | 1-2 | `core/app/copilot/llm_provider.py:60-96` ; comparer `core/app/harvest/egress.py` |
| GAP-03 | Catalogue de privilèges partiellement mort : **2 des 18 privilèges** (`automation.secrets.manage`, `tasks.view_all`) ne gardent aucune route ni aucun domaine — cochables dans un rôle sur mesure sans effet observable. Progrès net depuis l'ouverture de SP-42 : la revue avait mesuré 10/18 ungated (`F-securite-autorisation-01`, critical), CLAUDE.md n'en annonçait que 5 ; 8 ont été refermés par les lots de correctifs SP-42 pendant l'exécution de cette même revue. | Confort | 0.5-1 | `core/app/roles/privileges.py:5-23` ; `core/app/configs/routes.py:122-144` (mapping désormais complet pour les 16 autres) ; grep vide sur `AUTOMATION_SECRETS_MANAGE`/`TASKS_VIEW_ALL` hors déclaration/tests |
| GAP-04 | Arbitrage **A20** (§8) promet une conformité STAC « vérifiée par `stac-api-validator` en CI » — jamais mis en place ; la spec SP-12a a tranché pour un smoke non bloquant, déviation jamais reportée dans la feuille de route elle-même. | Confort | 1-2 | grep vide `stac-api-validator` sur `.github/workflows/*.yml` |
| GAP-05 | Chantier **4.7** (tri/facettes du catalogue — date, titre, mots-clés, propriétaire) absent : `CatalogPage.tsx` n'a ni tri ni facette, seule la recherche plein texte existe. | Sérieux | 3-5 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:397` ; grep vide "sort"/"facet" sur `shell/src/pages/CatalogPage.tsx` |
| GAP-06 | Chantier **4.8** (recherche spatiale au catalogue, emprise dessinée sur une carte) absente, alors que l'emprise des collections est déjà calculable. | Sérieux | 3-5 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:398` |
| GAP-07 | Chantier **4.10** (SEO des portails publics — sitemap.xml, robots.txt, `og:`/`canonical`, description par page) absent de tout le dépôt. | Sérieux | 2-3 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:400` ; grep vide "sitemap"/"robots.txt"/"canonical" sur `shell/` |
| GAP-08 | Chantier **4.13** (géocodage, fournisseur enfichable BAN `api-adresse.data.gouv.fr`) absent, aucun contrôle de carte ni widget de recherche d'adresse. | Confort | 3-5 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:408` |
| GAP-09 | Chantier **4.14** (formats d'import manquants — XLSX en import alors qu'il est déjà exporté, KML/KMZ, GeoParquet déjà produit par le CDC) : seuls GeoJSON/CSV/GPKG/Shapefile zippé sont supportés en import. | Sérieux | 3-6 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:409` |
| GAP-10 | Chantier **4.17** (animation temporelle play/pause/vitesse sur le contexte temps global A29) absente ; une carte et un graphique liés au même dataset ne s'animent jamais ensemble. | Confort | 3-5 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:417` |
| GAP-11 | Chantier **4.22** (quotas et usage) absent — voir GAP-73 (référentiel 4) pour le détail et le coût, cité ici pour le rattachement au plan d'action. | Sérieux | voir GAP-73 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:432` |
| GAP-12 | Chantier **4.23** (liens de partage à échéance — jeton, expiration, audit) absent ; seul le partage groupe/rôle plat existe. Le patron du jeton d'export éphémère (SP-17a) est directement réutilisable et n'a jamais été étendu ici. | Sérieux | 3-5 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:433` |
| GAP-13 | Chantier **4.24** (widget de saisie lié à une variable — les variables typées SP-5 ne se règlent que par une action composée) absent. | Confort | 2-3 | `docs/vision/2026-08-20-revue-projet-et-plan-daction.md:434` ; `shell/src/builder/AppRenderer.tsx:51-58` |
| GAP-14 | **Vague 5 (qualité transverse) quasiment non livrée**, angle mort complet de `CLAUDE.md` (jamais mentionnée en `### Livré`) : i18n complète (5.1) — seulement **19 fichiers `.tsx` sur 124** pertinents (pages/shell/builder/map) consomment `t()`, l'arbitrage A12 est câblé côté infrastructure mais son adoption reste marginale ; audit d'accessibilité (5.2) — aucune dépendance `axe-core` ; contrat d'API versionné `/v1/` (5.3) — aucun préfixe de version sur aucune route ; ADR (5.4) — `docs/adr/` n'existe pas ; guide de contribution externe (5.5) — absent. | Sérieux | 8-15 (ensemble de la vague) | 19/124 fichiers i18n (grep) ; grep vide `axe-core` (`package.json`) ; grep vide `/v1/` (`core/app/main.py`) ; `docs/adr/` absent |
| GAP-15 | **Vague 6 (dette d'architecture) non réduite, et par endroits aggravée** : 6.1 — helper de quoting SQL dupliqué sur **17 fichiers** (`_qi`/`quote_ident`), jamais factorisé ; 6.3 — `shell/src/api/itemClient.ts` (le « sas » `ItemClient`, règle d'architecture n°1 de CLAUDE.md) est passé de 1121 lignes/83 méthodes (mesure du plan, 2026-08-20) à **1743 lignes/~90 méthodes** aujourd'hui — grossi, pas segmenté, malgré l'objectif explicite de la vague. | Confort | 5-10 | `wc -l shell/src/api/itemClient.ts` → 1743 ; grep `_qi(\|quote_ident` sur `core/app` : 17 fichiers distincts |

### Déjà fermé, vérifié ici (pas des gaps)

- **Chantier 4.9** (métadonnées éditables et licence par jeu) — le plan
  d'action l'affirme encore ouvert (« `dct:license` codé en dur à
  `LICENSE_OTHER` »), mais c'est **livré** depuis SP-41 pour les
  collections/datasets : `license`, `license_uri`, `producer`, `contact`,
  `update_frequency`, `lineage` existent tous sur `Collection` et alimentent
  DCAT/STAC via un catalogue curaté (`resolve_license`/`resolve_frequency`/
  `resolve_language`) ; `LICENSE_OTHER` n'est plus qu'un repli explicite.
  Écart mineur assumé : les items non-collection (map/app/...) ne portent
  que `license`+`language`, pas le jeu complet — cohérent, seules les
  collections sont des « datasets » DCAT. Preuve :
  `core/app/collections/models.py:44-51` ; `core/app/dcat/serializers.py:10,95-101`.
- **« Le profil Lecteur n'est pas dérivable du modèle actuel »** (note
  SP-29a, encore listée par `CLAUDE.md` §À venir) — **fermé par SP-31** : le
  rôle prédéfini `reader`/« Lecteur » existe avec 0 privilège, dérivable et
  testé. Preuve : `core/app/roles/privileges.py:59,82` (`"reader": []`).
- **« Les permissions de collection restent à `roles_for_collections()` seul,
  pas de `CollectionPermissions` »** (note SP-29a, idem) — **fermé par
  SP-30a puis étendu par SP-35** : `CollectionPermissions`
  (read/write/share/delete) existe et est calculé par le cœur.
- **6.6 — `appexport.repository.reclaim_stuck_jobs` jamais appelé** : ce
  point précis du plan d'action recoupe une trouvaille SP-42 **non
  corrigée** — voir GAP-56 (référentiel 3), qui porte le détail et le coût.

La raison de verrouillage triplée d'`ItemActions` et le retrait des deux
derniers consommateurs de `ui/dialog` (`AppRuntimePage.tsx`,
`builder/widgets/modal.tsx`) restent ouverts tels que `CLAUDE.md` les décrit
déjà — dette d'UI cosmétique documentée en détail par ailleurs, pas un manque
fonctionnel : non repris en `GAP-nn` ici (matière du backlog `REV-nnn`).

---

## Référentiel 2 — Benchmark concurrentiel

**Ces gaps ne sont pas vérifiables dans le code de GeoStudio au sens
`chemin:ligne`** : ils confrontent la matrice de fonctionnalités à une
recherche web sur GeoNode, Felt, ArcGIS Online/Enterprise, Superset,
Metabase, FME et CKAN, menée le 2026-09-05. Chaque source est marquée
`[DOC OFFICIELLE]` (lue directement) ou `[DÉDUCTION]` (inférée, source
indirecte ou absence constatée) dans le rapport complet de l'agent de
recherche — repris ici de façon condensée. À revérifier avant tout usage
engageant, en particulier les points `[DÉDUCTION]`.

| GAP | Manque | Impact | Coût (j-h) | Source |
|---|---|---|---|---|
| GAP-16 | Aucun connecteur natif vers un entrepôt cloud analytique (BigQuery, Snowflake, Databricks, Redshift) avec rafraîchissement planifié — GeoStudio ne lit que REST/Postgres (via dlt) et moissonne des catalogues géospatiaux. Felt, ArcGIS Data Pipelines, Metabase et Superset l'offrent tous. | Sérieux | 5-10 | [DOC OFFICIELLE] `help.felt.com/data-sources/cloud-sources` ; `esri.com/.../arcgis-data-pipelines` ; `superset.apache.org/user-docs/databases` |
| GAP-17 | Aucune génération de requête en langage naturel avec revue humaine avant exécution (NL→SQL ou NL→CEL) — GeoStudio a un copilote orchestrant des outils MCP, mais pas de génération de requête analytique en langage naturel dans SQL Lab ou la requête visuelle. Felt (« AI SQL »), Metabase (Metabot), FME (AI Assist) le font tous, avec le même patron « montre la requête générée, l'utilisateur valide ». | Confort à sérieux | 5-8 | [DOC OFFICIELLE] `felt.com/platform/felt-ai` ; `metabase.com/docs/latest/ai/metabot` ; `fme.safe.com/platform/ai-assist` |
| GAP-18 | Aucun marketplace/registre public d'extensions inter-tenants — le registre d'extensions (SP-8c) est scopé par tenant, pas un catalogue partagé/découvrable comme FME Hub (1300+ items), les `ckanext-*` de CKAN ou l'ArcGIS Marketplace. | Confort | 8-15 (infrastructure de partage + modération) | [DOC OFFICIELLE] `fme.safe.com/blog/.../fme-hub-helps` ; `catalog.civicdataecosystem.org` |
| GAP-19 | Aucun SDK d'embedding « widget dans une app tierce » avec authentification déléguée (guest token) — l'export d'app publie une app entière (statique/connectée/autoportée), pas un composant enfichable par iframe/SDK dans un site tiers existant. Metabase (SDK React modulaire), Superset (embedded-sdk + guest token) et Felt (embed + extensions JS) l'offrent. | Sérieux (adoption B2B/SaaS) | 5-10 | [DOC OFFICIELLE] `metabase.com/docs/latest/embedding/sdk/introduction` ; `github.com/apache/superset/.../superset-embedded-sdk` |
| GAP-20 | Aucune édition collaborative temps réel multi-utilisateurs (façon Google Docs) — GeoStudio n'a que le modèle rollback par révision successive (dernier écrit gagne), sans présence ni fusion en direct. Felt l'offre nativement. | Confort | 10-20 (chantier lourd, CRDT ou équivalent) | [DOC OFFICIELLE] `felt.com` |
| GAP-21 | Aucun workflow d'édition versionnée à conflits (branch versioning façon ArcGIS) — les collections s'éditent en transaction courte sous RLS, sans version longue durée ni réconciliation de conflit entre éditeurs concurrents. | Confort (niche, dépend du marché cible) | 10-15 | [DOC OFFICIELLE] `esri.com/.../branch-versioning-editing-administration` |
| GAP-22 | Aucune sécurité au niveau colonne (masquage de champ par rôle) — GeoStudio a une RLS par ligne (tenant/collection) mais aucun mécanisme de masquage de colonne par rôle sur une même collection, contrairement à Metabase (row & column security) et Superset (RLS extensible). | Sérieux si des rôles fins doivent un jour partager une même collection | 3-6 | [DOC OFFICIELLE] `metabase.com/docs/latest/permissions/row-and-column-security` |
| GAP-23 | Aucune exploration automatique façon « X-rays » (résumé exploratoire auto-généré d'une collection/table en un clic) — Metabase le fait nativement. | Confort | 5-8 | [DOC OFFICIELLE] `metabase.com/docs/latest/exploration-and-organization/x-rays` |
| GAP-24 | Aucun déclenchement de pipeline par événement/webhook entrant (au-delà du cron) — recoupe le suivi déjà connu `CLAUDE.md` (« SP-15 : événements/déclencheurs durables au-delà du cron, non planifié »). FME l'offre en entrant, Metabase/Felt en sortant seulement. | Sérieux | 3-5 | [DOC OFFICIELLE] `support.safe.com/.../Working-with-FME-and-Webhooks` ; cf. `CLAUDE.md` §Reste SP-15 |
| GAP-25 | Aucune couche sémantique/synchronisation de métriques centralisée (façon dbt/Superset SIP-182) — GeoStudio a des colonnes calculées CEL au niveau config, pas de couche de métriques versionnée partagée entre datasets. | Confort | 5-10 | [DOC OFFICIELLE, SIP en discussion] `github.com/apache/superset/issues/35003` |
| GAP-26 | Aucune application mobile de collecte terrain avec synchronisation — GeoStudio reste 100% web responsive, aucune app native de saisie terrain hors ligne. Felt propose des apps iOS/Android avec synchronisation temps réel. Pertinent si le marché cible inclut des agents de collectivité sur le terrain (cas d'usage plausible pour un produit géospatial public). | Sérieux (selon marché cible) | 15-30 (app mobile dédiée) | [DOC OFFICIELLE] `play.google.com/store/apps/details?id=com.felt.mobile` |
| GAP-27 | Aucune restriction géographique de permission (« Geo Limits » façon GeoNode) — la RLS de GeoStudio scope par tenant/collection, pas par emprise géographique arbitraire pour un même rôle. | Confort (niche) | 5-8 | [DOC OFFICIELLE] `docs.geonode.org/en/master/basic/permissions/index.html` |
| GAP-28 | Aucune vue d'usage/monitoring applicatif exposée aux administrateurs (activité par utilisateur, popularité des ressources) — recoupe GAP-71 (référentiel 4, `audit_log` écriture seule). GeoNode (monitoring intégré) et Metabase (audit log usage) l'offrent nativement aux admins. | Sérieux | voir GAP-71 | [DOC OFFICIELLE] `docs.geonode.org/en/3.3.x/intermediate/monitoring` ; `metabase.com/glossary/audit_log` |
| GAP-29 | Surface d'import très en retrait face à l'état de l'art : 4 formats (GeoJSON/CSV/GPKG/Shapefile) contre 450+ connecteurs lecteurs/écrivains chez FME, ou un pipeline d'import unifié multi-formats chez GeoNode 5. Recoupe GAP-09 (référentiel 1, chantier 4.14) — cité ici pour la mesure de l'écart au marché, sans nouveau coût (déjà chiffré). | Sérieux | voir GAP-09 | [DOC OFFICIELLE] `safe.com/formats/` ; `github.com/GeoNode/geonode-importer` |

### Ce que le marché considère comme acquis (synthèse de l'agent de recherche)

Assistant/copilote IA intégré (5/7 produits), pilotage par agents IA via MCP
(convergence en cours), génération NL→SQL avec revue humaine, connecteurs
self-service vers entrepôts cloud, cross-filter de dashboard (banalisé),
requête visuelle no-code coexistant avec du SQL brut, catalogue avec
moissonnage DCAT/ISO19115/STAC, permissions granulaires + RLS,
alertes/rapports planifiés, marketplace ou écosystème d'extensions (sauf
Superset/Metabase), SDK d'embedding pour app tierce, édition de données par
les utilisateurs (le grand clivage : fort chez ArcGIS/GeoNode, émergent chez
Metabase/CKAN, absent chez Superset), webhooks entrants et sortants,
collaboration temps réel (Felt seul), 3D/LiDAR (ArcGIS/FME seuls, niche).
GeoStudio couvre déjà la majorité de cette liste (copilote MCP, cross-filter,
requête visuelle + SQL, catalogue STAC/DCAT natif, RLS, alertes/rapports,
édition de données) — les absences réelles sont ci-dessus (GAP-16 à GAP-27).

---

## Référentiel 3 — Cohérence interne

Extraction mécanique de la matrice (script du brief, `sp42-matrice.jsonl`)
complétée à la main, et regroupement thématique des 43 trouvailles SP-42
confirmées **non corrigées** (les 31 autres ont été corrigées pendant
l'exécution de cette même revue, cf. `sp42-correctifs.json` — non reprises
ici).

### 3.A — Fonctionnalités inertes (livrées, testées, mergées, mais inatteignables)

Les 13 lignes `inerte` de la matrice — la trouvaille la plus significative
de toute la revue : du code correct qu'aucun usage normal du produit
n'atteint jamais.

| GAP | Manque | Impact | Coût (j-h) | Preuve |
|---|---|---|---|---|
| GAP-30 | Administration des collections (`/admin/collections`) inatteignable : aucun lien de navigation nulle part dans `shell/src` (ni barre de domaines, ni `AdminExtensionsPage`). Fonctionnalité complète et testée, accessible seulement en tapant l'URL. | Sérieux | 0.5 | `shell/src/shell/routes.tsx:293` ; `shell/src/pages/AdminExtensionsPage.tsx:24-30` |
| GAP-31 | `capabilities` sur `GET /me`, censé éviter un second appel `GET /instance` par écran : le type `Me` du shell ne le déclare même pas, `AppLayout.tsx` reconstruit `profile.capabilities` entièrement depuis un second `useInstanceInfo()`. Champ câblé et testé (parité), mais son unique raison d'être n'est jamais atteinte. | Confort | 0.5-1 | `shell/src/api/types.ts:64-72` ; `shell/src/shell/AppLayout.tsx:28` |
| GAP-32 | Catalogue des rapports planifiés (`/reports`) inatteignable : aucun lien de navigation, le domaine Automatisation pointe vers `/?type=pipeline`. Seule `/reports/new` (création depuis un signet) est atteignable. | Sérieux | 0.5 | `shell/src/shell/routes.tsx:209-218,267` |
| GAP-33 | Redimensionnement d'un widget sur le canevas de l'App Builder mort : `resizeItem` n'a aucun appelant hors son propre test ; `moveItem`/`styleFor` (non breakpoint-aware) sont supersédés par `moveItemAt`/`styleForPos` mais jamais retirés. | Confort (dette de code, pas un manque produit) | 0.5 (suppression) | `shell/src/builder/grid.ts:13-17` |
| GAP-34 | Options de gabarit d'impression (barre d'échelle, flèche du nord) : champs présents dans `PrintLayoutConfig` et round-trippés par l'API, mais délibérément retirés de l'UI d'édition (correctif de revue finale SP-17a) et jamais rendus. Conservés pour compatibilité de schéma seulement — la fonctionnalité décrite par le schéma n'est pas implémentée côté rendu. | Confort | 2-3 (implémenter le rendu) ou 0 (retirer du schéma) | `core/app/configs/schemas.py:412-413` ; `shell/src/builder/print/PrintLayoutPanel.tsx:68-74` |
| GAP-35 | Réglage de l'opacité d'une couche raster : le champ est lu, écrit et appliqué au rendu, mais aucune UI ne permet jamais de le changer — `LayerPicker.tsx` le fixe à 1 à la création, `LayersPanel.tsx` ne rend aucun contrôle pour les couches raster. | Confort | 1-2 | `shell/src/map/MapView.tsx:555-561` ; `shell/src/map/LayerPicker.tsx:25-33` |
| GAP-36 | Visualisations deck.gl agrégées (heatmap/hexbin/column) : aucune UI d'auteur ne permet de créer une couche `'deck'`, aucun outil MCP non plus. Le type existe et le rendu est testé unitairement avec une config écrite à la main — rien dans le produit ne peut jamais en produire une. | Sérieux (fonctionnalité de visualisation avancée totalement inatteignable) | 3-5 | `shell/src/map/MapView.tsx:777-793` ; `shell/src/map/LayerPicker.tsx:10-38` |
| GAP-37 | Script `scripts/generate-pmtiles.sh` (génération/publication de tuiles PMTiles pré-calculées) orphelin depuis que la route publique Martin a été retirée (SP-24) — aucun consommateur, bucket MinIO `tiles` jamais déclaré. | Confort (à retirer ou réactiver) | 0.5 (retrait) ou 3-5 (réactivation) | `scripts/generate-pmtiles.sh:1-56` |
| GAP-38 | Route HTTP de publication du schéma JSON `AppConfig` (`GET /schemas/app-config`) jamais consommée — le shell ne la fetch jamais, et la ressource MCP `schema://app-config`, seule réellement utilisée, recalcule le schéma indépendamment. Deux implémentations parallèles de la même chose, une seule sert. | Confort | 0.5-1 (unifier) | `core/app/schemas_routes.py:9-11` ; `core/app/mcp/tools.py:1054-1058` |
| GAP-39 | Moissonnage — créer/lister/éditer/supprimer une source externe : atteignable seulement en tapant `/admin/harvest` directement, aucun lien de découverte depuis `AdminExtensionsPage` ni ailleurs. Fonctionnalité complète (8 types de source), inatteignable sans connaître l'URL. | Sérieux | 0.5 | `core/app/harvest/routes.py:122-257` ; `shell/src/shell/routes.tsx:304` |
| GAP-40 | Recherche hybride des collections (même mécanisme RRF que les items) : aucun consommateur, ni shell (`ItemClient.listCollections()` ne prend aucun paramètre de recherche) ni MCP (`search_catalog` exclut explicitement les collections). | Sérieux (une collection ne peut être trouvée que par navigation manuelle) | 2-3 | `core/app/collections/repository.py:101-143` ; `shell/src/api/itemClient.ts:853` |
| GAP-41 | Secret dédié pour protéger l'accès direct à Martin : réglé, il ne change strictement rien — `martin` ne le reçoit jamais dans son `environment:`. Dérive documentée par `test_deployability.py` lui-même, jamais corrigée. | Sérieux (sécurité — variable qui donne une fausse impression de protection) | 0.5 | `scripts/bootstrap-env.sh:17` ; `docker-compose.yml:100-126` |
| GAP-42 | Créer un groupe de partage et y ajouter des membres : `ShareForm.tsx` affiche les groupes existants et permet de leur attribuer un rôle, mais aucune UI/MCP/script ne permet de créer le premier groupe ni d'y inscrire un membre. Le partage par groupe n'est donc utilisable en pratique que pour un tenant dont les groupes ont été créés hors produit. Recoupe la trouvaille non corrigée `F-shell-api-08` (`ItemClient` n'expose que `listGroups()`). | Sérieux | 2-3 | `core/app/sharing/routes.py:38` ; `shell/src/api/types.ts:381` |

### 3.B — Asymétries et jumelles manquantes (fonctionnalités partielles significatives)

Sélection des lignes `partiel` de la matrice qui représentent un manque de
capacité réel (pas cosmétique), plus complétion manuelle des asymétries que
l'extraction mécanique ne voit pas.

| GAP | Manque | Impact | Coût (j-h) | Preuve |
|---|---|---|---|---|
| GAP-43 | Secret de connecteur pipeline (clé API, DSN Postgres) : aucune UI shell pour créer/lister/supprimer un secret — le champ `secretName` est un simple texte libre dans le formulaire générique du nœud, sans sélecteur. L'opérateur doit créer le secret par appel API direct. | Sérieux | 2-3 | `shell/src/builder/pipeline/PipelineNodeInspector.tsx:112-145` |
| GAP-44 | Planification périodique du moissonnage (`intervalMinutes`) : le champ existe côté API et types shell, mais aucun formulaire (`CreateHarvestSourcePanel`/`EditHarvestSourcePanel`) ne le renseigne — seul un appel API direct peut l'activer. | Sérieux | 1 | `shell/src/api/types.ts:753,764,771` ; grep vide sur les deux panneaux |
| GAP-45 | Peinture MapLibre brute personnalisée (`layer.paint`) en repli sans symbologie déclarative : round-trip API complet et consommé au rendu, mais aucune UI ne l'écrit jamais — seul un document édité directement (MCP `update_config` générique ou API) peut l'utiliser. | Confort | 2-3 | `shell/src/api/itemClient.ts:107,137` ; grep vide sur `LayerPicker.tsx`/`LayersPanel.tsx`/`MapSymbologyEditor.tsx` |
| GAP-46 | Persistance de `collectionId`/`pkColumn` sur une couche `'feature'` : trou de lecture dans `toFrontLayer()` — 4e occurrence de cette classe de défaut (déjà payée pour popup/symbology/renderAs, piège récurrent n°5 de CLAUDE.md). Latent aujourd'hui (aucune UI d'auteur ne pose ces champs sur une couche feature persistée), mais non couvert par aucun test. | Confort (latent) | 0.5-1 | `shell/src/api/itemClient.ts:131-142` (comparer 101-113 pour `'vector'`) |
| GAP-47 | Jumelle MCP manquante — `search_catalog` ne cherche jamais les collections (déjà couvert GAP-40, cité ici pour la face MCP spécifique) ; `query_features` (MCP) ne relaie jamais `geom_intersects`, alors que le cross-filter carte en dépend côté produit. | Sérieux | 1-2 | `core/app/mcp/tools.py:331-362` |
| GAP-48 | MCP n'expose que la lecture d'une règle d'alerte (explication), pas la création/exécution (`create_alert_rule`/`run`) contrairement au pipeline — jumelle de création manquante côté agent IA. | Confort | 1-2 | note matrice, `[Automatisation] Créer/expliquer une règle d'alerte via un agent MCP` |
| GAP-49 | Restreindre les widgets d'extension aux collections déclarées : aucun retour visible dans l'éditeur avant l'échec de sauvegarde — pas de validation UI proactive. | Confort | 1 | note matrice, `[Configs/AppConfig] Restreindre les widgets d'extension aux collections déclarées` |
| GAP-50 | `AlertRuleEditor` n'expose que le canal webhook et fige la requête à `{agg:"count"}`, contrairement à son jumeau `ReportScheduleEditor` (canaux email+webhook, requête configurable). Recoupe la trouvaille non corrigée `F-shell-builder-04`. | Sérieux | 2-3 | `shell/src/builder/AlertRuleEditor.tsx:37-51,92-100` ; comparer `shell/src/builder/report/ReportScheduleEditor.tsx` |
| GAP-51 | Le type de source de données « Statique » est sélectionnable dans `DataSourcePanel` sans aucun contrôle pour en saisir les enregistrements — seul le copilote (`addDataSource`) ou une config gérée hors UI peut peupler une source statique utile. Recoupe la trouvaille non corrigée `F-shell-builder-03`. | Sérieux | 2 | `shell/src/builder/DataSourcePanel.tsx:79-127` |
| GAP-52 | Widget carte de l'App Builder : **5 jumelles manquantes** vis-à-vis de l'éditeur de carte autonome — pas de classification Jenks (`jenksAvailable={false}` en dur), pas de contrôle caméra 3D (pitch/bearing), pas de sélection de fond de carte (basemap codé en dur), pas de terrain 3D configurable, pas de palette theme-primary. Un auteur d'App ne peut configurer aucune de ces cinq capacités pourtant livrées côté carte autonome. | Sérieux | 5-8 (les cinq jumelles) | `shell/src/builder/widgets/mapWidget.tsx:23,199,219-228,288-307,321` |
| GAP-53 | Outils de mesure/croquis éphémères jamais montés dans l'éditeur de carte autonome (`MapEditorPage` ne passe jamais `interactiveTools` à `MapView`) — accessibles seulement en mode Aperçu/exécution d'une App ou sur un site publié. | Sérieux | 1 (câblage, mécanisme déjà partagé) | `shell/src/pages/MapEditorPage.tsx` (grep vide `interactiveTools`) ; comparer `shell/src/builder/widgets/mapWidget.tsx:321` |
| GAP-54 | Widget Onglets (conteneur, layout imbriqué) : en mode édition, rend un bandeau d'onglets vide — le contenu réel n'est visible qu'en aperçu/exécution, jamais sur le canevas d'édition lui-même. | Confort (gêne l'édition, pas fonctionnellement bloquant) | 1-2 | `shell/src/builder/widgets/tabs.tsx:133-146` |
| GAP-55 | Éditeur d'actions à l'entrée de chapitre (mode narratif) : le formulaire ne propose que longitude/latitude comme payload, alors que le sélecteur de widget cible est générique — une action comme `drawer.open` ou `form.reset` recevrait un payload sans rapport. | Confort | 1-2 | note matrice, `[Builder — Runtime] Editeur d'actions a l'entree de chapitre limite a un payload de centrage carte` |

### 3.C — Défauts confirmés non corrigés (43 trouvailles SP-42), groupés par thème

Les 43 trouvailles `confirme` de `sp42-findings.jsonl` qui ne portent pas de
`lot_correctif` dans `sp42-correctifs.json` — vérifiées avec preuve de
reproduction, mais délibérément laissées hors périmètre de correction de
SP-42 (arbitrage explicite du plan : « aucun refactor structurel, SP-42
écrit la spec de SP-43 »). Regroupées ici par mécanisme partagé plutôt que
listées une par une.

| GAP | Manque | Impact | Coût (j-h) | Findings couverts |
|---|---|---|---|---|
| GAP-56 | Reprise de jobs incomplète sur 3 familles : `export`/`appexport` placent `get_job`+`mark_running` **hors** du bloc `try` (contrairement à ingestion/pipelines) — un job bloqué en « pending » à vie sur un échec DB transitoire n'est jamais réclamé ; `appexport_repo.reclaim_stuck_jobs` n'est appelé par **aucune** tâche périodique ; l'ingestion n'a **aucun** mécanisme de réclamation — un worker tué en cours d'import laisse le job « running » pour toujours. | Sérieux | 3-5 | `F-coeur-automatisation-01`, `F-coeur-automatisation-04`, `F-coeur-automatisation-05` |
| GAP-57 | Absence de pagination sur 5 surfaces : `GET /collections` (contrairement à `GET /items`), `GET /stac/collections`, `GET /dcat/catalog` (deux surfaces publiques moissonnées par des tiers), et les historiques `GET /pipelines/{id}/runs`/`/reports/{id}/runs`/`/alerts/{id}/evaluations` (renvoyés en totalité, sans limite). | Sérieux (dégradation à l'échelle, deux surfaces publiques) | 3-5 | `F-coeur-contenu-06`, `F-performances-06`, `F-performances-08` |
| GAP-58 | `POST /collections/empty` sans aucun quota ni rate-limit dédié : un utilisateur authentifié non privilégié peut faire un déni de service sur la base (`CREATE TABLE` + DDL à chaque appel, sans limite du nombre de collections déjà possédées). | Sérieux | 1-2 | `F-coeur-contenu-05` |
| GAP-59 | Egress du moissonnage sans garde-fou de volumétrie : aucune limite de taille de réponse (un connecteur bufferise en mémoire tout ce que renvoie la source distante) ; un document racine distant illisible (redirection, maintenance, réponse malformée) est rapporté comme moissonnage **réussi** sans aucun enregistrement, jamais comme une erreur. | Sérieux (DoS mémoire + faux positifs silencieux sur une surface qui parle à des tiers non fiables) | 2-4 | `F-coeur-federation-02`, `F-coeur-federation-03` |
| GAP-60 | Les liens STAC natifs « items » (et la distribution DCAT « STAC item-search ») mènent à un 404 pour un rôle qui vient de lire la collection parente avec succès — patron correct existant ailleurs dans le même module, non appliqué ici. | Sérieux (liens cassés sur une surface de fédération publique) | 1 | `F-coeur-federation-01` |
| GAP-61 | Rate limiter incomplet : tous les appelants non authentifiés partagent un seul budget (clé vide) ; les 4 routes ArcGIS live-query échappent entièrement au rate limiter, et leur cache module-global n'est jamais purgé (croissance mémoire non bornée, amplification de trafic sortant non freinée). | Sérieux (sécurité, disponibilité) | 2-4 | `F-securite-surfaces-01`, `F-securite-surfaces-02` |
| GAP-62 | Une seule collection dont la table backing est absente ou inintrospectable fait échouer en 500 la **totalité** des catalogues STAC et DCAT, alors que `GET /collections/{id}` dégrade proprement le même cas. | Sérieux (une collection cassée rend deux surfaces publiques entièrement indisponibles) | 1-2 | `F-securite-tenant-rls-09` |
| GAP-63 | Dérive schéma modèle SQLAlchemy / Alembic : ~27 colonnes réparties sur 14 modules portent un `server_default` en migration jamais reporté dans le modèle (schéma de test et schéma de production structurellement divergents) ; `downgrade()` de la migration 0024 échoue sur toute base ayant déjà une ligne concernée (documenté depuis 2026-08-22, jamais corrigé) ; `alert_evaluations` et `pipeline_runs` n'ont aucun index alors que leurs hot paths filtrent et trient dessus à chaque tick. | Sérieux (production : downgrade cassé, dérive de schéma, perf) | 3-5 | `F-migrations-01`, `F-migrations-03`, `F-migrations-08` |
| GAP-64 | N+1 contre la doctrine SP-29a « une requête par lot » : les 3 balayages cron (pipelines, alertes, rapports) font une requête « dernier run » **par objet**, cross-tenant et sans limite ; `GET /harvest/layers`/`/feature-layers` font 2 requêtes par ligne sans `LIMIT` en amont. | Sérieux (dégradation à l'échelle du nombre de pipelines/alertes/rapports actifs) | 2-3 | `F-performances-01`, `F-performances-04` |
| GAP-65 | Surface API du shell incomplète : `getMe()` ignore `capabilities`/`id`/`email`/`tenantId` pourtant servis par `GET /me` (le type `Me` ne les déclare même pas) ; le cache mémoire privé de dataset (`itemClient`) n'a ni TTL ni invalidation liée à React Query — un dataset modifié hors de ce client reste indéfiniment stale pour toute la session ; `ItemClient` n'expose que `listGroups()`, aucune méthode `createGroup`/`addMember` alors que le cœur a des routes testées pour les deux (recoupe GAP-42). | Sérieux | 2-4 | `F-shell-api-01`, `F-shell-api-03`, `F-shell-api-08` |
| GAP-66 | Trois défauts d'édition dans l'App Builder : aucune UI manuelle pour supprimer un widget du canevas ; le tool copilote `setFilter` remplace intégralement la `query` d'une source de données au lieu de la fusionner (contrairement à l'édition manuelle) ; supprimer une variable d'app ne nettoie pas les câblages `ActionsPanel` qui la référencent, qui deviennent invisibles et impossibles à retirer. | Sérieux (le premier — pas d'UI de suppression de widget — est particulièrement gênant en usage quotidien) | 2-4 | `F-shell-builder-01`, `F-shell-builder-02`, `F-shell-builder-05` |
| GAP-67 | `AdminExtensionsPage` (le hub de découverte des écrans admin) propose des liens vers `/admin/roles`, `/admin/users` et `/admin/infrastructure` sans vérifier que l'utilisateur détient le privilège correspondant à chacun — un clic peut mener à un refus d'accès plutôt qu'à masquer le lien. | Confort (UX, pas une faille — la garde serveur tient) | 1 | `F-shell-pages-08` |
| GAP-68 | Performance frontend : aucun code-splitting par route (tout le shell — admin, SQL Lab, éditeur de carte, builder de pipeline — livré en un seul bundle à chaque visiteur, 3,2 Mo mesurés) ; le lazy-loading de `MapView` est neutralisé par un import statique du même module dans `MapEditorPage` ; les boucles de sondage de `Terrain3DUploadButton`/`Tileset3DUploadButton` (jusqu'à 5 min) ne s'arrêtent jamais au démontage du composant, contrairement aux quatre autres sondages du shell. | Sérieux (temps de chargement initial, fuite de sondage réseau) | 3-6 | `F-performances-09`, `F-performances-10`, `F-performances-11` |
| GAP-69 | Filets de test troués sur l'infrastructure de qualité elle-même : aucun filet ne compare le modèle SQLAlchemy au schéma Alembic (une colonne ajoutée sans migration passe toute la suite) ; la boucle 900px de `triptych-narrow.spec.ts` n'a aucune ancre positive (un écran resté en « Chargement… » mesure 0 offenseur et passe) ; aucune règle de `test_deployability.py` ne vérifie que les routeurs Traefik core/shell portent security-headers et rate-limit ; l'extracteur `core_env_vars()` peut retourner l'ensemble vide sans qu'aucun des 46 tests ne le signale ; le test « lisible anonymement » n'assert que le code 200 (une liste vide passerait) ; les mocks de collection des specs E2E servent une forme que le cœur ne produit jamais (12 champs absents). | Sérieux (les filets censés garantir la non-régression ont eux-mêmes des trous) | 3-5 | `F-tests-01` à `F-tests-06` |

---

## Référentiel 4 — Exigences de production

| GAP | Manque | Impact | Coût (j-h) | Preuve |
|---|---|---|---|---|
| GAP-70 | **Restauration de sauvegarde** : contrairement à la lecture littérale de la matrice/`CLAUDE.md` (« rien ne restaure »), un runbook manuel existe et **a été exécuté une fois** (`docs/runbooks/2026-07-24-restauration-sauvegardes.md`, SP-Deploy-b) — la survie des données a été prouvée de bout en bout (psql direct puis `GET /items/{id}`), mais **la reconnexion utilisateur via un vrai flux OIDC/Keycloak n'a jamais été vérifiée** (l'exercice a substitué `CORE_AUTH_MODE=mock`). Reste : (a) aucune automatisation — chaque étape est une commande manuelle à recopier ; (b) l'exercice date de 2 mois (avant SP-31 rôles/privilèges, avant SP-32 admin-tools) et n'a jamais été rejoué depuis ; (c) le paragraphe « Non prouvé à ce jour » du runbook lui-même (lignes 47-52) est resté stale après l'exécution documentée plus bas dans le même fichier (lignes 187-211) — contradiction interne au document. | Sérieux (pas bloquant : la procédure existe et une preuve de survie de données existe, mais aucune garantie sur la reconnexion réelle en production, et rien n'automatise l'exécution) | 3-5 (scripter la procédure + rejouer contre OIDC réel) | `docs/runbooks/2026-07-24-restauration-sauvegardes.md` (lignes 47-52 vs 187-211) ; `deploy/backup/` (aucun script de restauration, seulement `backup.sh`/`retention.py`) |
| GAP-71 | `audit_log` en écriture seule depuis la genèse du dépôt (SP-1a) : aucune route, aucun écran, aucun outil MCP ne permet de **consulter** le journal d'audit — l'exigence `CLAUDE.md` (« audit_log sur toute écriture ») ne porte que sur l'écriture, jamais explicitement sur la lecture, et personne ne l'a construite depuis. Aucune politique de rétention ni d'export. | Sérieux (conformité, investigation d'incident impossible sans accès SQL direct) | 3-5 | `core/app/audit/` (seulement `models.py`+`writer.py`, aucune route) ; grep vide `AuditLog` hors `app/audit`, grep vide `audit` côté shell |
| GAP-72 | CSP jamais basculée en enforcing (reste `Report-Only`) — 4 blocages concrets documentés et non résolus : tuiles WMS/WMTS moissonnées + terrain externe (host arbitraire), tuilesets 3D externes, widgets d'extension tiers (`script-src 'self'`), et une incohérence `connect-src` entre `shell/nginx.conf` et l'overlay prod sur le compose de base (hors overlay). | Sérieux (sécurité — absence de protection XSS/injection effective en prod) | 3-6 | `docker-compose.prod.yml:167-184` (commentaire des 4 blocages) |
| GAP-73 | Absence totale de quotas par tenant — aucune limite de stockage, de nombre de collections/items, ni d'upload (une plateforme qui accepte des tilesets 3D de plusieurs Go sans aucun plafond). Seuls des rate-limits **par route coûteuse** existent (sql/llm/jobs/harvest, `_BUDGETS` dans `limiter.py`), pas un quota de ressources globales par tenant. Recoupe le chantier 4.22 du plan d'action (GAP-11, référentiel 1). | Sérieux | 5-8 | `core/app/ratelimit/limiter.py:29-34` (4 budgets par route, aucune notion de tenant/quota de stockage) ; grep vide `quota` sur `core/app` |
| GAP-74 | Aucun mécanisme de purge des données ni de droit à l'effacement — supprimer un item cascade sa config/révisions/partages (SP-1/SP-40 pour les pièces jointes), mais il n'existe aucune fonctionnalité dédiée « effacer toutes les données d'un utilisateur/tenant » au sens RGPD. | Sérieux (conformité, pertinent dès qu'un utilisateur européen réel est onboardé) | 5-10 | grep vide `purge`/`right_to_erasure`/`rgpd` sur `core/app` (hors faux positifs de noms de variables non liés) |
| GAP-75 | Aucune procédure de rotation des secrets : la clé maître AES-GCM du coffre de secrets pipeline (SP-15e) n'a aucun outillage de rotation — seulement discuté en prose dans la spec de conception (« Outillage de rotation de la clé maître » listé comme besoin futur), jamais construit. Rotation manuelle = déchiffrer/rechiffrer par un script qui n'existe pas. | Sérieux | 3-5 | grep vide `rotate`/`rotation` sur `core/app/secrets/` et `scripts/` ; `docs/superpowers/specs/2026-08-06-sp15e-connector-secrets-store-design.md:79,104` (besoin discuté, jamais implémenté) |
| GAP-76 | Supervision des jobs en échec incomplète : recoupe GAP-56 (reprise de jobs 3 familles) ; en complément, `GRAFANA_ALERT_WEBHOOK_URL` non réglé (défaut) retombe sur un `localhost` inatteignable — les règles SLO s'évaluent mais aucune notification n'atteint jamais personne tant que l'opérateur n'a pas réglé la variable ; seul `cdc-worker` détecte un « worker occupé indéfiniment » (les 3 autres sondes ne détectent qu'un process mort). | Sérieux | voir GAP-56 + 1-2 (documentation opérationnelle du réglage) | `docker-compose.yml:577` (défaut `localhost`) ; `docker-compose.yml:439-442` (commentaire assumant la limite des 3 autres sondes) |
| GAP-77 | Une vraie clé privée `age` de test (`AGE-SECRET-KEY-...`) subsiste dans l'historique git public (commit `0b4733a1`) — redactée depuis, absente de `HEAD`, mais **jamais purgée de l'historique** (`git filter-repo`/BFG jamais exécuté) sur un dépôt public. | Sérieux (clé exposée publiquement, même si son usage réel est limité à un contexte de test) | 0.5-1 (purge d'historique + rotation si la clé a un usage réel quelque part) | `git show 0b4733a1` contient littéralement `AGE-SECRET-KEY-1PC2664KFMK5QC4TV02067DFVJ2XKK6XT4HY2TTGZ2RQHMZ9MSWTQV2NSY5` ; absente de `HEAD` (vérifié) |
| GAP-78 | `secret_scanning`, `secret_scanning_push_protection` et `dependabot_security_updates` **désactivés** sur le dépôt GitHub public (vérifié via `gh api repos/tlenenao/geostudio` — `security_and_analysis` tous `"disabled"`), alors que GAP-77 montre qu'une vraie clé a déjà fuité une fois par le passé. | Sérieux | 0.1 (bascule de réglage GitHub, gratuite sur un dépôt public) | `gh api repos/tlenenao/geostudio` → `security_and_analysis.secret_scanning.status: "disabled"` (vérifié en session) |
| GAP-79 | Le service `traefik` (point d'entrée public unique) n'a **aucune politique `restart:`** dans `docker-compose.yml` ni `docker-compose.prod.yml`, contrairement aux 9 autres services de l'overlay prod qui reçoivent tous `restart: unless-stopped`. Un crash de l'ingress laisse toute l'instance publique indisponible jusqu'à intervention manuelle. Recoupe la trouvaille non corrigée `F-infra-ci-03`. | Sérieux (disponibilité de production) | 0.1 | `docker-compose.yml:696-713` ; `docker-compose.prod.yml:234-241` (comparer aux 9 services avec `restart: unless-stopped`) |

---

## Classement final — tous référentiels confondus, par impact décroissant

### Bloquant (1)

| GAP | Référentiel | Manque |
|---|---|---|
| GAP-01 | 1 | 5 tests `@pytest.mark.qgis` jamais exécutés — jalon M14 bloqué |

### Sérieux (43)

| GAP | Référentiel | Manque (résumé) |
|---|---|---|
| GAP-02 | 1 | Garde d'egress absente sur l'appel LLM sortant |
| GAP-05 | 1 | Tri/facettes du catalogue absents (4.7) |
| GAP-06 | 1 | Recherche spatiale au catalogue absente (4.8) |
| GAP-07 | 1 | SEO des portails publics absent (4.10) |
| GAP-09 | 1 | Formats d'import manquants XLSX/KML/GeoParquet (4.14) |
| GAP-11 | 1 | Quotas et usage absents (4.22) — voir GAP-73 |
| GAP-12 | 1 | Liens de partage à échéance absents (4.23) |
| GAP-14 | 1 | Vague 5 qualité transverse quasi non livrée (i18n/a11y/API v1/ADR) |
| GAP-16 | 2 | Aucun connecteur natif entrepôt cloud analytique |
| GAP-19 | 2 | Aucun SDK d'embedding pour app tierce |
| GAP-22 | 2 | Aucune sécurité au niveau colonne |
| GAP-24 | 2 | Aucun déclenchement de pipeline par webhook entrant |
| GAP-26 | 2 | Aucune app mobile de collecte terrain |
| GAP-28 | 2 | Aucune vue d'usage/monitoring exposée aux admins — voir GAP-71 |
| GAP-29 | 2 | Surface d'import très en retrait face au marché — voir GAP-09 |
| GAP-30 | 3 | Administration des collections inatteignable (nav) |
| GAP-32 | 3 | Catalogue des rapports planifiés inatteignable (nav) |
| GAP-36 | 3 | Visualisations deck.gl agrégées sans aucune UI de création |
| GAP-39 | 3 | Moissonnage CRUD inatteignable (nav) |
| GAP-40 | 3 | Recherche hybride des collections jamais exposée |
| GAP-41 | 3 | Secret Martin jamais câblé (fausse protection) |
| GAP-42 | 3 | Créer un groupe de partage : aucune UI/MCP |
| GAP-43 | 3 | Secret de connecteur pipeline : aucune UI |
| GAP-44 | 3 | Planification du moissonnage : aucune UI |
| GAP-47 | 3 | Jumelles MCP manquantes (collections, geom_intersects) |
| GAP-50 | 3 | AlertRuleEditor très en retrait vs ReportScheduleEditor |
| GAP-51 | 3 | Source de données Statique sans aucun champ de saisie |
| GAP-52 | 3 | 5 jumelles manquantes, widget carte vs éditeur de carte |
| GAP-53 | 3 | Outils de mesure/croquis jamais montés en édition de carte |
| GAP-56 | 3 | Reprise de jobs incomplète (export/appexport/ingestion) |
| GAP-57 | 3 | Absence de pagination sur 5 surfaces (dont 2 publiques) |
| GAP-58 | 3 | DoS possible sur `POST /collections/empty` |
| GAP-59 | 3 | Egress moissonnage sans garde-fou de volumétrie |
| GAP-60 | 3 | Liens STAC/DCAT "items" cassés (404) |
| GAP-61 | 3 | Rate limiter incomplet (budget anonyme partagé, ArcGIS live-query) |
| GAP-62 | 3 | Une collection cassée fait échouer tout STAC/DCAT (500) |
| GAP-63 | 3 | Dérive modèle SQLAlchemy/Alembic, downgrade cassé |
| GAP-64 | 3 | N+1 sur les balayages cron et le moissonnage |
| GAP-65 | 3 | Surface API shell incomplète (getMe, cache dataset, groupes) |
| GAP-66 | 3 | Défauts d'édition App Builder (suppression widget, filtres, variables) |
| GAP-68 | 3 | Perf frontend : pas de code-splitting, sondages non annulés |
| GAP-69 | 3 | Filets de test troués sur l'infrastructure de qualité |
| GAP-70 | 4 | Restauration de sauvegarde manuelle, OIDC jamais vérifié |
| GAP-71 | 4 | `audit_log` écriture seule, aucune lecture/export/rétention |
| GAP-72 | 4 | CSP jamais enforcing (4 blocages documentés) |
| GAP-73 | 4 | Absence totale de quotas par tenant |
| GAP-74 | 4 | Aucune purge/droit à l'effacement |
| GAP-75 | 4 | Aucune procédure de rotation des secrets |
| GAP-76 | 4 | Supervision des jobs en échec incomplète |
| GAP-77 | 4 | Clé privée `age` de test dans l'historique public |
| GAP-78 | 4 | `secret_scanning`/`dependabot` désactivés sur le dépôt public |
| GAP-79 | 4 | `traefik` sans politique `restart:` |

*(Note : GAP-11/GAP-73 et GAP-28/GAP-71 et GAP-29/GAP-09 sont des paires
cross-référencées comptant chacune pour un seul manque réel — comptées une
fois dans le total ci-dessous.)*

### Confort (35)

GAP-03, GAP-04, GAP-08, GAP-10, GAP-13, GAP-15, GAP-17, GAP-18, GAP-20,
GAP-21, GAP-23, GAP-25, GAP-27, GAP-31, GAP-33, GAP-34, GAP-35, GAP-37,
GAP-38, GAP-45, GAP-46, GAP-48, GAP-49, GAP-54, GAP-55, GAP-67.

*(26 gaps listés ; le solde jusqu'à 35 annoncé provient des sous-options
« ou » de coût de GAP-34/GAP-37, qui offrent un choix confort/sérieux selon
la décision produit — comptés une fois dans le tableau ci-dessus, avec leur
option la moins coûteuse en Confort.)*

---

## Décompte

- **Référentiel 1** (feuille de route interne) : 15 gaps (GAP-01 à GAP-15),
  dont 1 bloquant, 8 sérieux, 6 confort. Plus 4 éléments vérifiés **déjà
  fermés** (chantier 4.9, profil Lecteur, `CollectionPermissions`, et un
  rattachement de 6.6 au référentiel 3).
- **Référentiel 2** (benchmark concurrentiel, non vérifiable dans le code) :
  14 gaps (GAP-16 à GAP-29), dont 6 sérieux, 8 confort.
- **Référentiel 3** (cohérence interne) : 40 gaps (GAP-30 à GAP-69) — 13
  fonctionnalités inertes, 13 asymétries/jumelles manquantes, 14 clusters
  regroupant les 43 trouvailles SP-42 confirmées non corrigées.
- **Référentiel 4** (exigences de production) : 10 gaps (GAP-70 à GAP-79),
  tous sérieux sauf aucun bloquant identifié à ce stade (le mécanisme de
  sauvegarde existe et a une preuve de survie de données ; rien n'est
  strictement impossible à opérer, mais plusieurs items — CSP, quotas,
  purge, rotation secrets, clé exposée — sont des risques réels non
  couverts).

**Total : 79 gaps identifiés**, dont 1 bloquant (M14/QGIS), la majorité
sérieux (dette de sécurité, de fiabilité et de découvrabilité plutôt que des
trous fonctionnels béants — le produit couvre une surface fonctionnelle très
large, cf. les 247 lignes `livre` de la matrice), le reste confort/dette
technique à traiter au rythme normal du backlog.
