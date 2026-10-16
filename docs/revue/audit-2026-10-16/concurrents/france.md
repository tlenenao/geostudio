# Cartographie concurrentielle : écosystème français (audit 2026-10-16)

Méthode : WebSearch/WebFetch (octobre 2026) pour les capacités externes, lecture directe du code GeoStudio pour la parité (jamais CLAUDE.md/specs comme preuve). Lecture seule. Limites : les pages officielles IGN/INSEE/Apidae n'ont été lues qu'en résumé de recherche (sauf data.gouv.fr, testé en direct) ; ce qui n'est pas confirmé est marqué « à vérifier ». Neogeo : aucune source trouvée sur un produit « Neogeo Platform » ; seul l'écosystème geOrchestra (utilisé par GéoBretagne/PIGMA) a été documenté.

## 1. Tableau capacités / parité

Parité : oui / partiel / non / dépassé. Maturité côté concurrent : prod = service en production.

| # | Capacité (acteur) | Description, maturité, licence/coût | Source | Parité | Preuve GeoStudio (fichier:ligne) |
|---|---|---|---|---|---|
| 1 | Géoplateforme IGN : WMTS 1.0.0 / WMS / WFS publics (IGN) | Flux vecteur/raster nationaux, endpoint `data.geopf.fr`. Prod. Limite 2 couches par URL WFS/WMS-V depuis le 15/06/2026. Gratuit en grande partie | https://geoservices.ign.fr/usages | partiel | Consommer : connecteurs moissonnage WFS/WMS/WMTS `core/app/harvest/connectors/wfs.py`, `wmts.py` ; op pipeline `reader.wfs` `core/app/pipelines/ops/contracts.py:618`. Aucun fond de carte IGN préconfiguré trouvé (fonds par tenant seulement, `/v1/basemaps`) |
| 2 | Publier ses couches en OGC (WFS 2.0, WMS 1.3.0, WMTS) (IGN, GeoServer) | Standard INSPIRE/IGN | https://geoservices.ign.fr/usages | oui (derrière flags) | WFS 2.0 lecture `core/app/ows/routes.py:145-147` ; WMS/WMTS `core/app/ows/wms_routes.py:258,440` ; flags faux par défaut `.env.example:252,257` ; WMTS TileMatrixSet limité `wms_routes.py:377` |
| 3 | Géocodage/autocomplétion BAN via Géoplateforme (IGN/ANCT) | API Adresse transférée à l'IGN, ancienne URL `api-adresse.data.gouv.fr` arrêtée fin janvier 2026. Prod. Etalab 2.0 | https://www.data.gouv.fr/posts/lapi-adresse-de-la-base-adresse-nationale-est-transferee-a-lign-10 | dépassé | `core/app/geocoding/provider.py:19` (`data.geopf.fr/geocodage/search` par défaut), routes search/batch/jobs/reverse `core/app/geocoding/routes.py:28,63,122,160`, widget `shell/src/builder/widgets/addressSearch.tsx`, op `transform.geocode` |
| 4 | Recherche d'adresse dans la carte (Géoportail) | Barre de recherche | https://geoservices.ign.fr/usages | oui | `shell/src/map/AddressSearch.tsx` |
| 5 | data.gouv.fr : catalogue + API udata `/api/1/datasets` (DINUM/Etalab) | Prod. Testé le 2026-10-16 : réponse JSON `data[]`. Licence Ouverte | https://www.data.gouv.fr/api/1/datasets/?q=cadastre&page_size=1 | non (voir écart 1) | Connecteur « CKAN/data.gouv.fr » appelle `/api/3/action/package_search` `core/app/harvest/connectors/ckan.py:64` ; testé : `data.gouv.fr/api/3/...` renvoie 404 |
| 6 | API tabulaire data.gouv.fr (`tabular-api.data.gouv.fr/api/resources/<id>/data/`) | Requête de lignes sur CSV référencés. Prod (juin 2026) | https://www.mintlify.com/datagouv/datagouv-mcp/guides/datasets | partiel | Lecture générique via `reader.connector.rest` `core/app/pipelines/ops/contracts.py:251` ; aucun connecteur dédié (grep `tabular-api` : 0 résultat dans core/app) |
| 7 | Serveur MCP data.gouv.fr (9 outils, lecture seule) | `mcp.data.gouv.fr/mcp`, sans authentification | https://lawve.ai/mcp-servers/datagouv | dépassé (côté serveur) / partiel (client) | Serveur MCP propre `core/app/mcp/` ; op pipeline `mcpCall` `core/app/pipelines/ops/messaging.py` (non rejouée). Pas d'intégration du MCP data.gouv dans le copilote |
| 8 | Export DCAT-AP pour data.gouv / catalogues européens (DINUM) | Moissonnage par data.gouv/data.europa.eu | https://www.data.gouv.fr/ | oui | `core/app/dcat/routes.py:122,161`, `core/app/dcat/serializers.py:2-4,113,173` ; licence `etalab-2.0` `core/app/catalog/metadata.py:23-26` |
| 9 | Cadastre / PCI Vecteur, Parcellaire Express (Etalab, IGN) | Couverture France entière depuis 01/09/2025. Licence Ouverte 2.0 | https://www.data.gouv.fr/datasets/parcellaire-express-pci | partiel | Aucune ingestion/couche cadastre préconfigurée (grep `cadastre` hors docs : 0). Importable via GeoJSON/GPKG/Shapefile `core/app/ingestion/parsers.py` ; WFS IGN consommable (ligne 1) |
| 10 | API Carto cadastre (IGN) | Géométries parcelle/commune en GeoJSON WGS84 | https://www.data.gouv.fr/dataservices/api-carto-module-cadastre | partiel | Appelable via `reader.connector.rest` (contracts.py:251) ou `transform.httpCall` ; pas de connecteur ni widget dédié |
| 11 | INSEE : API Sirene, Melodi (SDMX), BDM, données locales | Catalogue d'API depuis 17/10/2024 ; compte + abonnement requis ; NAF 2025 au 01/01/2027 ; Licence Ouverte | https://www.insee.fr/fr/information/8184146 | partiel | Aucune référence `sirene`/`insee`/`melodi` dans `core/app` (grep). Accès générique REST + secrets `oauth2_client` ; `transform.databaseJoin` pour jointure |
| 12 | Plateformes régionales geOrchestra (GéoBretagne, PIGMA) : GeoNetwork 4.4, GeoServer, mviewer, MapStore2, Datafeeder, GeoFence, Console | Stack mutualisée INSPIRE, prod, open source (GPL/BSD selon composant) | https://www.georchestra.org/software.html | partiel | Consommation par moissonnage CSW `core/app/harvest/connectors/csw.py:2,132` ; pas de serveur CSW/ISO 19139 (`GetRecords` : seulement client) ; viewer + builder dépassent mviewer côté no-code (voir avantages) |
| 13 | Catalogue de métadonnées ISO 19115/19139 + CSW serveur (GeoNetwork) | Exigence INSPIRE (métadonnées) | https://www.georchestra.org/software.html | non | Aucun export ISO 19139 (`MD_Metadata` : uniquement en lecture `harvest/connectors/csw.py:132`). Export DCAT-AP + STAC seulement |
| 14 | Apidae (SIT tourisme coopératif) : API diffusion v2, exports JSON, schémas | Prod, SCIC ; doc sur dev.apidae-tourisme.com (non lue), OpenAPI non confirmée | https://packagist.org/packages/apidae-tourisme/apidae-sit-schemas | non | Aucune référence `apidae`/`datatourisme` dans `core/app` ni `shell/src` (grep). Possible via `reader.connector.rest` générique |
| 15 | DATAtourisme (DGE) : agrégateur open data tourisme | Prod, open data | https://www.banquedesterritoires.fr/un-nouvel-outil-public-et-gratuit-pour-exploiter-les-donnees-touristiques | non | Idem 14 |
| 16 | INSPIRE : services de téléchargement OGC API Features (guide 1.0) | Bonne pratique adoptée ; directive en fin de vie, simplification annoncée (aucune révision 2026 trouvée) | https://github.com/INSPIRE-MIF/gp-ogc-api-features/blob/master/spec/oapif-inspire-download.md | partiel | OGC API Features Part 1/2/4 `core/app/features/routes.py`, CRS 4326/3857/2154 `core/app/ogc_crs.py:7`, STAC `core/app/stac/routes.py:112-210` ; pas de profil INSPIRE (jeux de données prédéfinis, multilinguisme) ni modèles de données INSPIRE (GML lu comme du KML `ingestion/parsers.py:594`) |
| 17 | Lambert-93 (EPSG:2154) | Projection légale France | https://geoservices.ign.fr/usages | oui | `core/app/ogc_crs.py:7`, `core/app/ows/wms.py:21`, `core/app/ows/wfs.py:93`, `transform.setCrs` cible `core/app/pipelines/analysis.py:123` |
| 18 | RGAA 4.1.x (RGAA 5 / WCAG 2.2 prévu fin 2026) + EAA | Obligation des services publics ; audit manuel + déclaration d'accessibilité + schéma pluriannuel | https://sk-web.fr/article/rgaa-obligations-2026 | partiel | axe-core sur ~17 pages, échec seulement sur critical/serious `shell/e2e/a11y-audit.spec.ts:52-55`, lecteur d'écran `shell/e2e/a11y-screen-reader.spec.ts`, lien d'évitement `shell/src/shell/AppLayout.tsx:90`, `lang="fr"` `shell/index.html:2`. Aucune déclaration d'accessibilité ni référence RGAA dans le code (grep : 0 hors docs) ; axe ne couvre qu'environ un tiers des critères RGAA |
| 19 | RGS 2.0 (homologation, 4 fonctions de sécurité) | Arrêté du 13/06/2014 ; homologation des téléservices | https://cyber.gouv.fr/sites/default/files/2022-10/RGS_v-2-00_Corps_du_texte.pdf | partiel | Journal d'audit `core/app/audit/models.py:16-21`, OIDC délégué (Keycloak), CSP `core/app/security/traefik_render.py:16-17`. Aucun dossier d'homologation ni profil de certificat RGS dans le dépôt |
| 20 | SecNumCloud 3.2 (ANSSI, 08/03/2022) | Qualification d'un prestataire cloud (protection droit extra-européen) ; ne se « code » pas, se contracte | https://cyber.gouv.fr/uploads/2014/12/secnumcloud-referentiel-exigences-v3.2.pdf | partiel (auto-hébergeable) | Déploiement auto-hébergé : Helm, OCI, Proxmox (`deploy/`), S3 MinIO reconstruit depuis sources, aucun SaaS tiers obligatoire. Egress LLM/géocodage borné par allowlist `core/app/geocoding/egress.py:20`. Aucun mot-clé SecNumCloud dans le code ; le défaut du géocodage envoie des adresses à `data.geopf.fr` (hébergeur public, hors périmètre) |
| 21 | Identité d'État (FranceConnect / ProConnect) | Fédération d'identité agents/usagers | non vérifié en ligne | non (à vérifier) | OIDC générique (`core/app/auth/`), claims→groupes ARC-24 ; aucun préréglage FranceConnect/ProConnect (grep : 0 résultat) |
| 22 | Licence Ouverte 2.0 / open data | Licence par défaut de l'État | https://www.data.gouv.fr/datasets/parcellaire-express-pci | oui | `core/app/catalog/metadata.py:23-26` |

## 2. Score de parité du domaine

Barème : oui/dépassé = 1, partiel = 0,5, non = 0 ; 22 capacités.

- oui/dépassé : 6 (2, 3, 4, 8, 17, 22) = 6
- partiel : 11 (1, 6, 7, 9, 10, 11, 12, 16, 18, 19, 20) = 5,5
- non : 5 (5, 13, 14, 15, 21) = 0

Score : (6 + 5,5) / 22 = **52 %** de parité. Lecture : GeoStudio est fort sur les standards OGC/DCAT/géocodage, faible sur les connecteurs métier français, les métadonnées ISO/INSPIRE et la conformité administrative (RGAA/RGS).

## 3. Dix écarts majeurs

1. **Le connecteur « CKAN / data.gouv.fr » ne moissonne pas data.gouv.fr.** `core/app/harvest/connectors/ckan.py:64` appelle `/api/3/action/package_search` ; testé en direct le 2026-10-16, `https://www.data.gouv.fr/api/3/action/package_search` répond 404, alors que `/api/1/datasets/` (udata) répond. Le docstring (`ckan.py:2`) promet l'inverse (piège n°12). Il faut un connecteur udata.
2. **Pas de serveur CSW / export ISO 19139** : seulement un client (`harvest/connectors/csw.py`). Les catalogues régionaux geOrchestra/GeoNetwork et INSPIRE ne peuvent pas moissonner GeoStudio en CSW.
3. **Pas de profil INSPIRE** : pas de jeux de données prédéfinis, pas de modèles de données thématiques, GML/INSPIRE lu comme du KML (`ingestion/parsers.py:594`), pas de validation de métadonnées INSPIRE. La directive est en fin de vie, donc priorité moindre.
4. **Aucun connecteur dédié Sirene / Melodi / données locales INSEE** (grep : 0). Faisable via REST + `oauth2_client`, mais aucun gabarit prêt à l'emploi pour les analystes publics.
5. **Pas de jeu cadastre / Parcellaire Express préconfiguré** ni de connecteur API Carto ; un utilisateur doit importer ou câbler lui-même un flux.
6. **Aucune conformité RGAA démontrable** : pas de déclaration d'accessibilité, pas de grille RGAA, axe-core ne bloque que critical/serious (`a11y-audit.spec.ts:52-55`). RGAA 5 / WCAG 2.2 attendu fin 2026.
7. **RGS / homologation** : aucun artefact (dossier, analyse de risques, politique de certification) ; GeoStudio fournit des briques (audit, OIDC) mais pas le dossier.
8. **SecNumCloud** : pas d'offre qualifiée ; le défaut de géocodage (`data.geopf.fr`) et l'appel LLM sortent du périmètre souverain si non reconfigurés. Mode « tout interne » (géocodeur local) non documenté dans le code.
9. **Pas d'intégration FranceConnect / ProConnect** ni de connecteur Apidae/DATAtourisme (secteur collectivités/tourisme).
10. **Pas de fonds de carte IGN préconfigurés** (Plan IGN, Ortho) : le client doit les ajouter via `/v1/basemaps` ; le MCP data.gouv.fr n'est pas branché au copilote.

## 4. Cinq avantages réels de GeoStudio

1. **Builder no-code config-driven + AppRenderer unique** (carte, tableau, formulaire, CEL) : mviewer/MapStore/Géoportail n'ont pas d'équivalent d'applications composables par config ; preuve : widgets `shell/src/builder/widgets/` (ex. `addressSearch.tsx`).
2. **Pipelines ETL no-code (~150 op) intégrés** avec lecteurs WFS/REST/blob et géocodage : `core/app/pipelines/ops/contracts.py:251,618`. Les plateformes régionales n'ont que Datafeeder (import simple).
3. **Géocodage BAN à jour sur la Géoplateforme** avec lot asynchrone, reverse et reprise : `core/app/geocoding/routes.py:28-160`, `provider.py:19`, déjà migré avant l'arrêt de l'ancienne API de janvier 2026.
4. **MCP natif et copilote IA sous permissions utilisateur, audités** (`core/app/mcp/`) : ni geOrchestra ni Géoportail n'en ont ; seul data.gouv propose un MCP, en lecture seule.
5. **Sécurité au niveau ligne et colonne (RLS, masquage GAP-22) + publication OGC (WFS/WMS/WMTS) sous `can()`** : `core/app/ows/routes.py:3-9` ; GeoServer + GeoFence demandent une configuration séparée.

## 5. Réserves

- Lien Neogeo/geOrchestra non confirmé ; Neogeo non cartographié.
- RGS 2.0 : état actuel (révision éventuelle) non confirmé sur cyber.gouv.fr ; un billet d'août 2026 évoquant une « nouvelle version » de SecNumCloud n'a pas pu être recoupé.
- Chiffres INSEE/IGN issus de résumés de recherche, pas des pages complètes.
