# Concurrent : ArcGIS Pro / Enterprise / Online (audit du 2026-10-16)

Périmètre : cartes, symbologie, 3D, publication, partage, administration, tarification.
Méthode : documentation Esri récente (WebSearch/WebFetch, octobre 2026) croisée avec le code GeoStudio
(lecture seule, preuves `fichier:ligne`, jamais CLAUDE.md/specs). Limite : les preuves GeoStudio sont des
ancrages de surface (définition de schéma, route, widget) ; aucune n'a été rejouée. `parité` : oui / partiel / non / dépassé.

## 1. Sources Esri consultées

| Source | URL | Ce qu'elle établit |
|---|---|---|
| Pro 3.6 (nov. 2025) | https://pro.arcgis.com/en/pro-app/get-started/whats-new-in-arcgis-pro.htm (redirigé vers doc.esri.com), https://geospatialtraining.com/whats-new-in-arcgis-pro-3-6-top-features-you-need-to-know/ | Gaussian splats, fond 3D Google Photorealistic, fuseaux horaires temporels, ModelBuilder refondu, Suitability Modeler |
| Pro 3.7 (14 mai 2026) | https://www.esri.com/arcgis-blog/products/arcgis-pro/announcements/whats-new-and-improved-in-arcgis-pro-may-2026 | visibilité de couche par cadre de mise en page, volet Analyze Map, extraction de lignes/polygones scannés, graphes de connaissance fichier, SDK .NET 10 |
| Enterprise 12.0 | https://enterprise.arcgis.com/en/get-started/12.0/linux/what-s-new-in-arcgis-enterprise.htm | audit des accès aux services, intercepteurs de service, Prometheus, assistants IA (beta), Data Pipelines (beta), Reality Server (beta), Kubernetes ; retraits : Web AppBuilder, Configurable Apps, Insights, Map Viewer Classic ; MFA imposable, connexions personnalisées |
| Enterprise 12.0 annonce | https://www.esri.com/arcgis-blog/products/arcgis-enterprise/announcements/whats-new-in-arcgis-enterprise-12-0 | sécurité, observabilité, 3D |
| ArcGIS Online juin 2026 | https://doc.arcgis.com/en/arcgis-online/reference/whats-new.htm | Review map, couches Parquet (beta), séries temporelles, formulaires, polices, Arcade Run/Debug, gabarits d'impression, ordre/verrou des symbol layers, effet glow 3D, volumes cut/fill (beta), contingent values, offline planifié, collaboration distribuée, tableau de bord d'organisation, changement de type de connexion |
| Assistants IA | https://www.esri.com/arcgis-blog/products/arcgis-online/geoai/whats-new-in-ai-assistants-june-2026 | assistants Survey123/Business Analyst/traduction GA sans surcoût, assistant Arcade, privilège de rôle pour l'IA, cartographie agentique (beta) |
| Experience Builder | https://www.esri.com/arcgis-blog/products/experience-builder/announcements/whats-new-in-arcgis-experience-builder-february-2026 | widgets Date Filter, Theme Mode Switcher, multilingue |
| Fonctions Online | https://www.esri.com/en-us/arcgis/products/arcgis-online/features | 6 familles : cartographie, analyse, gestion de données, collaboration, automatisation, IA ; hébergement US/EU/APAC |
| Tarification Online | https://www.esri.com/en-us/arcgis/products/arcgis-online/pricing | types d'utilisateur : Viewer (0 crédit), Mobile Worker et Contributor (250), Creator, Professional, Professional Plus (500). **Aucun prix public**, devis commercial |
| Licences Pro | https://www.esri.com/en-us/arcgis/products/arcgis-pro/buy | niveaux Basic/Standard/Advanced liés aux types d'utilisateur ; aucun prix public |
| Tarification Enterprise | https://esri.com/en-us/arcgis/products/arcgis-enterprise/pricing | 3 options (Standard, Advanced, Kubernetes) ; Kubernetes plafonné à 64 vCPU, inclut 100 Viewer + 25 Creator depuis 11.0 ; achat via Sales |

Non vérifié : tout montant en euros/dollars (les pages officielles n'en publient pas ; la page tierce flypix.ai est exclue,
tableau incohérent). Les mentions de TerraMind/DOFA pour Pro 3.7 viennent d'un tiers (LinkedIn), non retenues.

## 2. Tableau capacités / parité

Maturité Esri : GA = disponible ; Beta ; Retiré. Licence : `Pro`/`Online`/`Ent.` = produit payant sous abonnement par type d'utilisateur ; GeoStudio = Apache-2.0.

| # | Capacité Esri | Description | Maturité | Coût/licence Esri | Parité | Preuve GeoStudio |
|---|---|---|---|---|---|---|
| 1 | Cartes web (Map Viewer) | carte multi-couches éditable, sauvegarde, partage | GA | Creator+ | oui | `core/app/configs/schemas.py:138` (couches vector/raster/feature/deck/tiles3d), `shell/src/map/MapView.tsx` |
| 2 | Symbologie catégorielle/graduée/continue (Smart Mapping) | styles pilotés par champ, palettes | GA | Creator+ | oui | `shell/src/builder/widgets/mapSymbology.ts:20-30` (ColorClassification, ColorDomain), `shell/src/map/MapSymbologyEditor.tsx` |
| 3 | Symbologie avancée (bivariée, effets) | bivarié, bloom/ombre/blend | GA | Creator+ | partiel | `shell/src/builder/widgets/advancedSymbology.ts:7-25` ; pas d'ordre ni de verrou de symbol layers |
| 4 | Ordre/verrou de symbol layers, glow 3D, animation le long d'une ligne | finitions cartographiques juin 2026 | GA | Creator+ | non | aucun équivalent (`grep` symbol-layer vide côté `shell/src/map`) |
| 5 | Pop-ups configurables (Arcade) | gabarits, champs calculés | GA | Creator+ | oui | `core/app/configs/schemas.py:115` (PopupConfig), `shell/src/map/popupTemplate.ts`, CEL au lieu d'Arcade |
| 6 | Étiquetage | polices, expressions | GA | Creator+ | partiel | `shell/src/map/labelSource.ts`, `mapLayerBuild.ts:249` (addLabelLayer) ; catalogue de polices réduit |
| 7 | Langage d'expressions Arcade + assistant | expressions + débogueur Run/Debug | GA | inclus | partiel | CEL : `core/app/mcp/tools/query_generation.py:349` (generate_cel_expression) ; pas de débogueur pas-à-pas côté Esri-like |
| 8 | Regroupement de points (clustering) | agrégation visuelle | GA | Creator+ | oui | `core/app/configs/schemas.py:126-158` (ClusterConfig) |
| 9 | Heatmap | densité | GA | Creator+ | oui | `shell/src/map/LayersPanel.tsx:204-223` (deck `heatmap`) |
| 10 | Temps (time-aware, séries temporelles) | fenêtre temporelle, lecteur | GA | Creator+ | partiel | `shell/src/builder/widgets/timePlayer.tsx:42`, `shell/src/map/LayersPanel.tsx:184-188` (timeField) ; pas de fuseaux ni de séries séquentielles |
| 11 | Mesure et croquis | outils de dessin/mesure | GA | Creator+ | partiel | `shell/src/map/MapMeasureSketchToolbar.tsx`, `measureSketch.ts` ; pas de courbes Bézier/arcs |
| 12 | Comparaison swipe / galerie de fonds | volet avant/après | GA | Creator+ | oui | `shell/src/builder/widgets/swipe.tsx:27`, `basemapGallery.tsx` |
| 13 | Fonds de carte par organisation | galerie de fonds personnalisée | GA | admin | oui | `core/app/mapicons/basemap_routes.py:65` |
| 14 | Impression/mises en page, atlas | layouts PDF, série de pages | GA | Pro (Layout), Online gabarits | partiel | `core/app/configs/schemas.py:624-695` (AtlasConfig, printLayout) ; pas d'éditeur de layout cartographique complet |
| 15 | Scènes 3D, tuiles 3D (I3S/3D Tiles) | web scene, couches de maillage | GA | Creator+ ; Pro 3D Analyst payant | partiel | `core/app/configs/schemas.py:138` (tiles3d), `shell/src/map/mapDeckTerrain.ts:7` (loaders.gl 3d-tiles), `core/app/tileset3d/` ; pas d'I3S/SLPK |
| 16 | Terrain/élévation | modèle numérique de terrain | GA | inclus | oui | `core/app/configs/schemas.py:161` (MapTerrain), `mapDeckTerrain.ts:112` (raster-dem) |
| 17 | Gaussian splats, fond Google 3D, volumes cut/fill, line of sight | 3D avancée 2026 | GA/beta | Pro/Online | non | aucun (`grep -i gaussian\|splat` vide dans `core/app`) |
| 18 | Hébergement de couches d'entités (hosted feature layers) | publier des données éditables | GA | crédits de stockage | dépassé | collections PostGIS + OGC API Features : `core/app/features/routes.py:835-843` (ETag/If-Match), `core/app/features/tiles.py:86` (MVT) |
| 19 | Services REST ArcGIS (FeatureServer/MapServer) servis | compatibilité clients Esri | GA | Server | non | seulement en lecture : `core/app/pipelines/ops/cloudfiles.py:597-612`, `core/app/harvest/connectors/arcgis.py:42` ; GeoStudio ne sert pas de FeatureServer |
| 20 | Standards OGC (WMS/WMTS/WFS, OGC API) | interopérabilité | GA | Server | oui | `core/app/ows/wms.py:2`, `core/app/ows/wfs.py:71`, `core/app/features/routes.py` |
| 21 | Tuiles vectorielles publiées | service tuilé | GA | crédits | oui | `core/app/features/tiles.py` (ST_AsMVT) |
| 22 | Rasters/imagerie hébergés + analyse zonale | COG, statistiques | GA | Image Server (extension) | partiel | `core/app/raster/ingest.py:44`, `raster/zonal.py:50` ; pas de raster functions, ni deep learning |
| 23 | Géotraitement publié (web tools, ModelBuilder) | pipelines à publier | GA | Pro Advanced/Server | partiel | `core/app/pipelines/service.py:79`, `ops/contracts.py` (catalogue d'op), canevas DAG ; pas de bibliothèque de ~1000 outils Esri |
| 24 | Data Pipelines (no-code) | intégration de données | Beta (Ent. 12.0) | crédits | dépassé | pipeline DAG déjà livré : `core/app/configs/schemas.py:414` (PipelinePayload), `core/app/pipelines/ops/` |
| 25 | Géocodage et routage | locator, réseaux | GA | crédits | partiel | `core/app/geocoding/routes.py:2`, `core/app/routing/routes.py:2` (Valhalla) ; pas de Network Analyst complet |
| 26 | Éditeur de cartes/apps sans code (Experience Builder, Instant Apps, Dashboards) | applications | GA | Creator+ | oui | `shell/src/builder/` (AppRenderer, WidgetHost, ~40 widgets), `shell/src/builder/widgets/index.tsx:6-9` |
| 27 | Sites/portails publics (Hub) | sites de communication | GA | licence Hub | oui | `shell/src/shell/routes.tsx:379` (`/sites/:slug`), `core/app/public/routes.py:20` |
| 28 | Collecte terrain (Survey123/Field Maps) | formulaires mobiles | GA | Mobile Worker | partiel | `core/app/xlsform/routes.py:2`, `core/app/public_submit/routes.py:61` ; pas d'app native, ni de hors ligne (voir 38) |
| 29 | Partage par groupes et rôles | groupes, niveaux de partage | GA | inclus | oui | `core/app/sharing/routes.py:61-207`, `core/app/sharing/authorization.py:33-101` (decide/can) |
| 30 | Lien/intégration publique | embed d'app | GA | inclus | oui | `shell/src/shell/routes.tsx:378`, `core/app/sharing/share_links.py:18` |
| 31 | Collaboration distribuée entre organisations | synchro de contenu entre portails | GA | Ent./Online | partiel | moissonnage seulement : `core/app/harvest/connectors/arcgis.py:3` ; pas de synchro bidirectionnelle |
| 32 | Rôles et privilèges personnalisés | contrôle d'accès administratif | GA | Creator+ admin | oui | `core/app/roles/privileges.py:5-26` (23 privilèges) |
| 33 | Types d'utilisateur à crédits (Viewer…Professional Plus) | modèle de licence par utilisateur | GA | payant | partiel | pas de crédits : quotas `core/app/quotas/service.py:117`, rôles ; aucun modèle de facturation par usage (par conception) |
| 34 | SSO, groupes par attributs, MFA | identité d'entreprise | GA | inclus | oui | délégué Keycloak : `deploy/keycloak/geostudio-realm.json:420` (OTP), `core/app/auth/dependency.py`, `core/app/sharing/routes.py:246` (claim-mappings) |
| 35 | Clés d'API de service | accès programmatique | GA | crédits | oui | `core/app/apikeys/routes.py:43-98` |
| 36 | Journal d'audit, tableau de bord d'usage | gouvernance | GA | Ent. 12.0 | oui | `core/app/usage/`, `core/app/audit/` (audit_log), `shell` page Usage |
| 37 | Observabilité (Prometheus) et sauvegarde | exploitation | GA | Ent. | oui | `core/app/observability.py`, `deploy/backup/`, profil `observability` |
| 38 | Hors ligne (cartes planifiées, Field Maps) | emport de données | GA | Mobile Worker | non | `core/app/collections/routes.py:126` ne cite qu'un nom de table Keycloak ; aucune capacité hors ligne |
| 39 | Notebooks Python + assistant | science des données | GA/beta | crédits | non | aucun (SQL Lab seul : `core/app/analytics/`) |
| 40 | Assistants IA (items, Arcade, traduction, agentique) | copilote | GA/beta | sans surcoût | partiel | `core/app/copilot/routes.py:380` (/copilot/turn), outils MCP `core/app/mcp/tools/`, `copilot/llm_provider.py:5` ; pas d'assistant de traduction |
| 41 | Édition versionnée / branche / réseaux de services publics | géodatabase d'entreprise | GA | Ent. Advanced | non | `core/app/history/routes.py` (journal d'entité linéaire, pas de versions parallèles) |
| 42 | Analyse spatiale/Insights/Business Analyst | BI géospatiale | Insights retiré (Ent. 12.0) | payant | partiel | `core/app/analytics/`, widgets `pivot`, `chart`, `indicator` ; pas d'enrichissement démographique |
| 43 | Déploiement Kubernetes, haute disponibilité | exploitation à l'échelle | GA | Ent. Kubernetes | oui | `deploy/helm/geostudio/values.yaml:141-142` (replicas, PDB), `Chart.yaml:2-7` (version 0.1.0) |
| 44 | Graphes de connaissances | modèle de graphe | GA | extension | non | aucun |
| 45 | Interopérabilité import (FileGDB, DXF, DGN, MapInfo, XLSX, KML…) | formats | GA | inclus | oui | `core/app/ingestion/`, `core/app/pipelines/ops/readers2.py` |

## 3. Score de parité du domaine

Pondération : oui = 1, dépassé = 1, partiel = 0,5, non = 0 (45 capacités).
- oui : 19 (1, 2, 5, 8, 9, 12, 13, 16, 20, 21, 26, 27, 29, 30, 32, 34, 35, 36, 37) + 43, 45 = 21
- dépassé : 2 (18, 24)
- partiel : 15 (3, 6, 7, 10, 11, 14, 15, 22, 23, 25, 28, 31, 33, 40, 42)
- non : 7 (4, 17, 19, 38, 39, 41, 44)

Score = (21 + 2 + 15 x 0,5) / 45 = 30,5 / 45 = **68 %**. Hors lignes purement commerciales (33) : environ 69 %.
Lecture : la parité est forte sur la chaîne carte → app → partage → administration, faible sur la 3D de pointe,
l'édition d'entreprise (versions, réseaux), le hors ligne et le catalogue d'outils analytiques.

## 4. Dix écarts majeurs

1. **Pas de service FeatureServer/MapServer exposé** (ligne 19) : les clients Esri (Pro, Field Maps, Web AppBuilder tiers) ne peuvent pas consommer GeoStudio ; il n'existe qu'un lecteur (`cloudfiles.py:597`).
2. **Hors ligne absent** (38) : ni cartes hors ligne ni collecte déconnectée ; le périmètre terrain reste du web en ligne.
3. **Édition d'entreprise** (41) : pas de versions parallèles, ni réseaux de services publics, ni topologie ; l'historique est linéaire (`history/routes.py`).
4. **3D de pointe** (17) : pas de Gaussian splat, de fond photoréaliste, de volumes cut/fill, ni de I3S/SLPK ; Pro 3.6/Scene Viewer juin 2026 creusent l'écart.
5. **Bibliothèque d'analyse** (23, 22, 25) : ~65 op de pipeline contre des milliers d'outils Esri ; raster functions, deep learning, Network Analyst complet absents.
6. **Notebooks et science des données** (39) : aucun environnement Python hébergé.
7. **Cartographie de production** (4, 14, 3) : pas de mise en page de carte interactive complète, de symbol layers ordonnées/verrouillées, de repères de cartographie professionnelle.
8. **Application native/mobile** (28, 38) : pas de Field Maps/Survey123/QuickCapture ; XLSForm + page web seulement.
9. **Enrichissement et données de référence** (42) : pas de Business Analyst, ni de Living Atlas ; le catalogue public reste à remplir par le client.
10. **Débogage d'expressions et IA agentique** (7, 40) : pas de Run/Debug pas à pas, ni d'assistant de traduction, ni de cartographie agentique (beta Esri).

## 5. Cinq avantages réels de GeoStudio

1. **Coût et licence** : Apache-2.0, aucun type d'utilisateur ni crédit ; Esri n'affiche aucun prix public et facture par type (Creator…Professional Plus) et par crédits (`quotas/service.py:117` : quotas internes, pas de facturation).
2. **Modèle déclaratif unique, opérable par IA** : toute entité est un document schématisé (`configs/schemas.py:242, 298, 414, 523, 590`) exposé via MCP avec les permissions de l'utilisateur (`mcp/tools/`) ; Esri limite l'IA à des assistants par produit, en bêta pour l'agentique.
3. **Autorisation unique et masquage fin** : `can()`/`decide()` (`sharing/authorization.py:33-101`), RLS PostGIS, masquage de colonne sensible sur tous les mécanismes de lecture ; moins de surfaces à auditer qu'un portail + serveurs fédérés.
4. **Pipeline no-code et lakehouse intégrés** : DAG avec exécution planifiée, webhooks, reprise par nœud (`pipelines/service.py:79`) et analytique DuckDB/GeoParquet ; Esri classe Data Pipelines en beta (Ent. 12.0) et a retiré Insights.
5. **Déploiement simple et reproductible** : docker-compose + chart Helm HA (`deploy/helm/geostudio/values.yaml:141`) ; Esri impose un prérequis 11.5 avec object store et migration de caches avant 12.0, et retire Web AppBuilder/Configurable Apps (apps cassées après mise à niveau).
