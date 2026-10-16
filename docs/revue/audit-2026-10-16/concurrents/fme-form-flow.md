# Cartographie concurrentielle : FME Form / Flow / Flow Hosted vs GeoStudio

Date : 2026-10-16. Lecture seule sur le code. Preuves = code relu (pas CLAUDE.md/specs). Les `fichier:ligne` ci-dessous ont été lus ce jour ; le décompte des op vient d'un import réel de `app.pipelines.ops.contracts.OPERATIONS` (152 op : 105 transform / 31 reader / 16 writer ; 32 marquées `experimental`).

## 1. Sources FME consultées (octobre 2026)

- FME 2026.1 : https://community.safe.com/product-updates/fme-2026-1-feature-highlights-40103
- FME 2026.2 : https://community.safe.com/product-updates/fme-2026-2-feature-highlights-40528
- FME 2026.3 (dernière version trouvée) : https://community.safe.com/product-updates/fme-2026-3-feature-highlights-40901
- Automations : https://docs.safe.com/fme/html/FME-Flow/WebUI/Automations-General/Automations.htm
- 8 usages de Flow (apps, DV, streams, AR) : https://fme.safe.com/blog/2025/06/8-ways-to-automate-your-data-with-fme-flow/
- Flow Hosted (usages, modèles de prix) : https://fme.safe.com/blog/2026/05/fme-flow-hosted-vs-on-prem-5-use-cases-that-make-the-cloud-worth-it/
- Grille tarifaire Flow Hosted (page datée, ~2 ans, à confirmer) : https://support.safe.com/hc/en-us/articles/29728097481229-FME-Flow-Hosted-Pricing-and-Sizing (non lisible par WebFetch, 403 ; chiffres repris du résumé de recherche : annuel 12 000 à 75 000 USD, horaire 2,40 à 15 USD)
- Data Virtualization / Workspace Apps : https://docs.safe.com/fme/2025.0/html/FME-Flow/WebUI/Data-Virtualization.htm
- Tarifs Form : non publics (devis ; G2 https://www.g2.com/products/fme-platform/pricing). Maintenance ~25 % du prix catalogue Form (source revendeur, non officielle).
- Nombre de transformers/formats : aucun chiffre officiel actuel trouvé ; "plus de 1000 transformers avec le Hub" est une revendication de conférence 2022 (https://engage.safe.com/presentations/introducing-new-package-sdk-create-share-python-based-transformers/). Le comparatif interne `docs/revue/matrice-couverture-fme.jsonl` recense 290 transformers (périmètre choisi par nous, pas un total FME).
- Aucune documentation lue sur FME "Streams" au-delà de la description du blog (flux continus IoT/logs). Maturité non vérifiée.

## 2. Tableau de parité (40 capacités)

Légende : oui / partiel / non / dépassé. Maturité FME : GA sauf mention. Coût : FME = licence commerciale (moteurs licenciés), GeoStudio = Apache-2.0.

| # | Capacité FME | Description (source) | Maturité FME | Parité | Preuve GeoStudio |
|---|---|---|---|---|---|
| 1 | Workbench (canvas visuel Form) | Éditeur visuel de workspaces, desktop | GA | partiel | Canvas DAG web : `shell/src/builder/pipeline/PipelineCanvas.tsx` ; moteur : `core/app/pipelines/compiler.py:60-91` (acyclique, un seul prédécesseur principal par nœud) |
| 2 | Catalogue de transformers (~500 natifs + Hub) | Transformers natifs et packages Hub | GA | partiel | 105 op `transform.*` : `core/app/pipelines/ops/contracts.py:768` (`OPERATIONS`, import réel) |
| 3 | Formats lecteurs/écrivains (centaines) | 400+ sources (docs Safe 2020) | GA | partiel | Import : GeoJSON/CSV/XLSX/GPKG/SHP/GDB/DXF/DGN/KML/GML/JSONL/GeoParquet `core/app/ingestion/parsers.py:239,342,512,521,527,560,590,603,682` ; 31 readers / 16 writers de pipeline (`contracts.py:768`) |
| 4 | Rejected port FeatureWriter (2026.3) | Les écritures en échec sortent par un port | GA (3 formats) | dépassé | `core/app/pipelines/collection_writer.py:13,124` : rejets par règle vers `<cible>__rejected`, modes upsert/update/delete (`:2`) |
| 5 | Boucles natives (2026.2) | Looping dans l'éditeur | GA | non | `compiler.py:81` : graphe acyclique imposé ; aucune op de boucle (grep `loop`/`foreach` vide dans `pipelines/`) |
| 6 | Branchement / fan-in multi-ports (Testers, mergers) | Routage par ports | GA | partiel | `ops/filtering.py:46` (`testFilter`), `contracts.py:299` (`merge`), `compiler.py:86-91` : "linear+join topology only" |
| 7 | Live data caching (2026.1) | Inspecter les caches pendant l'exécution | GA | partiel | Aperçu à la demande `core/app/pipelines/routes.py:271` + `runtime.py:1001` (`preview_pipeline`), pas d'inspection pendant un run |
| 8 | AI Assist (plugin Hub, backend MCP) | Chat dans Workbench | GA | partiel | Copilote `core/app/copilot/llm_provider.py:5`, outils MCP allowlistés ; génère requêtes/apps, n'édite pas un graphe de pipeline (non vérifié en détail) |
| 9 | MCPCaller | Appeler un outil MCP dans un workflow | GA (2026.1) | partiel | `ops/messaging.py:1206` (`transform.mcpCall`), mais `contracts.py:729` la classe `experimental` (flag `CORE_PIPELINE_EXPERIMENTAL_OPS_ENABLED`) |
| 10 | Flow en serveur MCP | Workspaces publiés comme outils d'agent | GA (2026.2) | partiel | Serveur MCP `core/app/mcp/tools/__init__.py:62` (47 outils, dont `tools/pipelines.py`) ; expose la plateforme, pas des pipelines arbitraires comme outils nommés (non vérifié) |
| 11 | MCP de supervision des jobs | Historique/erreurs pour clients IA | Technical Preview | partiel | `core/app/usage/` (audit lecture seule) + MCP `tools/pipelines.py` ; pas d'équivalent confirmé "tendances de performance" |
| 12 | Automations (triggers/actions, ports succès/échec, boucles) | Moteur de workflows visuel | GA | partiel | Pas de builder d'orchestration générique ; briques éclatées : cron pipeline, webhook, S3, alertes (`core/app/alerts/models.py:44`), rapports (`core/app/reports/`) |
| 13 | Trigger Schedule | Exécution planifiée | GA | oui | `core/app/pipelines/jobs.py:435` (`run_pipeline_sweep_task`), `routes.py:97` (next-run) |
| 14 | Trigger webhook entrant | HTTP déclenche un workflow | GA | oui | `routes.py:341` (`POST /pipelines/{id}/trigger`, jeton), `service.py:205` |
| 15 | Trigger dépôt de fichier (dir/S3) | Surveillance d'un dossier | GA | oui | `core/app/webhooks/triggers.py:1-8` (sondage S3 borné, idempotent par etag), `outbox/models.py:63` |
| 16 | Triggers SFTP (2026.2) et Email IMAP | Fichier SFTP / mail reçu | GA | non | `ops/cloudfiles.py:20` ("SFTP absent"), `:783` (FTP clair refusé) ; aucun `imap` dans `core/app` |
| 17 | Webhooks/HTTP request sortants | Action HTTP Request, notifications | GA | oui | `core/app/webhooks/delivery.py:1-6` (HMAC, retries, désactivation), `transform.httpCall` (`contracts.py:768`) |
| 18 | Email / Slack / messagerie | Actions de notification | GA | partiel | `ops/messaging.py:416,450` ; classées expérimentales (`contracts.py:719-720`) ; alertes natives hors flag |
| 19 | File de jobs, retry, annulation | Gestion des jobs Flow | GA | oui | `routes.py:120,172` (retry/cancel), `jobs.py:147` (`retrying`), procrastinate |
| 20 | Paramètres de run | Paramètres publiés du workspace | GA | oui | `core/app/pipelines/service.py:86,265` (`params`), `routes.py:138` |
| 21 | Workspace Apps | Formulaire web autour d'un workspace | GA | partiel | App Builder `shell/src/builder/AppRenderer.tsx` + widget Formulaire ; pas de formulaire auto-généré depuis les paramètres d'un pipeline (non vérifié) |
| 22 | Gallery Apps / portails | Page regroupant des apps | GA | oui | Sites/portails `shell/src/pages/SitePublicPage.tsx` |
| 23 | Data Virtualization (endpoints REST sur workspaces) | Endpoints manuels / workspace, callbacks 2026.1 | GA | partiel | Pas d'endpoints utilisateur sur pipeline ; collections publiées en OGC API Features, agrégats, tuiles ; `routes.py:341` n'expose que le déclenchement |
| 24 | Streams (flux continu IoT/logs) | Traitement quasi temps réel | GA (blog) | non | Aucun moteur de flux ; CDC `core/app/cdc/parquet_writer.py:97` alimente le lac, pas du traitement de flux |
| 25 | FME Flow Hosted (SaaS géré, AWS) | Instance managée, sauvegardes, API | GA | non | Aucune offre managée ; auto-hébergement `deploy/helm/geostudio`, `deploy/oci`, `deploy/proxmox` |
| 26 | Modèle de coût | Licence par moteur ; Hosted 2,40-15 USD/h ou 12-75 k USD/an ; Form sur devis | n/a | dépassé | Apache-2.0, aucun coût par moteur/utilisateur (hébergement à la charge de l'opérateur) |
| 27 | Moteurs multiples / mise à l'échelle | Moteurs illimités en Hosted, scaling API | GA | partiel | `deploy/helm/geostudio/values.yaml:141` (`replicas: 2`, HA), files procrastinate ; pas d'API de redimensionnement |
| 28 | Niveaux de durcissement sécurité (2026.2/3) | Default/Minimal/custom | GA | partiel | Gardes d'egress (`pipelines/egress.py`), `reader.file` sous flag (`pipelines/runtime.py:606`, `auth/dependency.py:51`) ; pas de "niveaux" sélectionnables |
| 29 | Utilisateurs, rôles, SSO | Gestion Flow | GA | oui | `core/app/roles/`, `core/app/users/`, OIDC `core/app/auth/` |
| 30 | Lineage / analyse d'impact | (aucune équivalence Flow native trouvée) | n/a | dépassé | `core/app/lineage/service.py:1-12` (graphe dérivé, droits respectés), MCP `tools/lineage.py` |
| 31 | Versions / historique / rollback | Dépôts, versions de workspaces | GA | oui | `core/app/configs/` (historique, rollback), `core/app/history/` |
| 32 | PythonCaller, SDK de packages, Hub | Code et transformers custom partageables | GA | non | Aucun PythonCaller (`grep` vide dans `core/app`) ; extensions = widgets UI uniquement (`core/app/extensions/`) |
| 33 | Connecteurs cloud/lakehouse (Databricks, Fabric, Iceberg, Delta, BigQuery, Snowflake) | 2026.1-2026.3 | GA | partiel | Databricks/Snowflake/BigQuery : `ops/contracts.py:281,768` (expérimentaux) ; Iceberg/Delta/Fabric absents (grep vide) |
| 34 | pgvector / type Vector | Lecture/écriture de vecteurs PG | GA (2026.2) | oui | Recherche sémantique pgvector `core/app/search/`, migrations HNSW |
| 35 | JSON complet (JSONObjectBuilder/Appender) | 2026.2 | GA | partiel | `writer.export` JSON/GeoJSON ; pas de constructeur d'objets JSON imbriqués (non vérifié) |
| 36 | Raster, nuage de points, 3D | PDAL, tuiles 3D 1.1, WebODM | GA | partiel | Raster `ops/raster.py`, `core/app/raster/`, `core/app/tileset3d/` ; point cloud : aucun |
| 37 | FME Realize (AR) | Réalité augmentée | GA | non | Hors périmètre produit |
| 38 | Géocodage / routage | Connecteurs | GA | oui | `core/app/geocoding/`, `core/app/routing/client.py:2` (Valhalla) |
| 39 | Contrôle qualité / validation | Validators | GA | oui | `core/app/quality/runner.py`, `ops` `validateAttributes` |
| 40 | Authoring Form desktop (hors ligne) | Application bureau | GA | partiel | `shell/src/desktop/DesktopApp.tsx` existe ; maturité et périmètre non vérifiés ici |

## 3. Score de parité du domaine

Barème : oui = 1, dépassé = 1, partiel = 0,5, non = 0.

- oui 12, dépassé 3, partiel 19, non 6 (40 capacités)
- Score = (12 + 3 + 9,5) / 40 = **24,5 / 40, soit 61 %**.

Lecture : forte sur l'exécution, le déclenchement et la gouvernance ; faible sur l'orchestration visuelle générale, la programmabilité (Python/Hub) et le temps réel. Ce score pondère toutes les lignes également (pas de pondération par usage). Les lignes marquées "non vérifié" sont des partiel par prudence.

## 4. Dix écarts majeurs

1. **Pas de boucles ni de topologie non linéaire** : `compiler.py:81,86-91` ; FME 2026.2 a des boucles natives.
2. **Pas de PythonCaller ni de SDK de packages** : extensibilité de transformers fermée (ligne 32).
3. **Pas d'orchestrateur Automations générique** (triggers + actions + ports succès/échec) ; seulement des briques par domaine (ligne 12).
4. **Pas de traitement de flux continu (Streams)** (ligne 24).
5. **Pas de Data Virtualization** : un pipeline ne peut pas devenir un endpoint REST paramétré (ligne 23).
6. **Triggers SFTP/IMAP absents** (`cloudfiles.py:20`).
7. **Pas d'offre hébergée managée** (Flow Hosted) ; adoption lourde pour une petite équipe sans ops (ligne 25).
8. **Catalogue et formats plus étroits** : 105 transformers contre un catalogue FME + Hub de plusieurs centaines à plus de 1000 (revendication 2022) ; 32 op sur 152 restent expérimentales, non rejouées sur service réel (`contracts.py:729`, `docs/revue/2026-10-16-ops-experimentales.md`).
9. **Connecteurs lakehouse récents manquants** : Iceberg, Delta, Fabric (ligne 33).
10. **Pas de nuage de points** (PDAL) ni de constructeur JSON imbriqué (lignes 35-36).

## 5. Cinq avantages réels de GeoStudio

1. **Coût et licence** : Apache-2.0, pas de licence par moteur, auto-hébergeable (ligne 26) ; FME est sur devis, Hosted à 2,40-15 USD/h.
2. **Quarantaine des rejets pilotée par règle, avec upsert/delete** (`collection_writer.py:2,13,124`) ; FME n'offre le port Rejected que sur 3 formats (2026.3).
3. **Lineage/impact de bout en bout, sous droits** (`lineage/service.py:1-12`) : carte, dataset, app, alerte, rapport, pipeline ; pas de fonction native équivalente trouvée côté FME.
4. **Plateforme unifiée** : catalogue, cartes, builder d'apps, RLS PostGIS, partage, MCP et pipeline dans un seul produit ; FME exige Form + Flow + Apps pour approcher cela.
5. **Sécurité intégrée à l'exécution** : egress gardé par secret, `reader.file` désactivé par défaut (`runtime.py:606`), RBAC fin ; FME introduit seulement ses niveaux en 2026.2.

## 6. Limites

- Tarifs Form non publics ; grille Hosted non relue directement (403).
- Pas de total officiel de transformers/formats retrouvé.
- Aucune exécution : les verdicts reposent sur la lecture du code et l'import du registre, pas sur un rejeu.
