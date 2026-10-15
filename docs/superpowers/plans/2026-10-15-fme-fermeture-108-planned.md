# Plan — fermeture des 108 `planned_*` (+12 `unknown`) de la matrice FME

> Date : 2026-10-15. Source de vérité du périmètre : `docs/revue/matrice-couverture-fme.jsonl`
> (290 lignes : 128 `implemented`, 108 `planned_*`, 12 `unknown`, 25 `out_of_scope`, 10 `license_blocked`, 7 `capability_removed`).
> Exécution : subagent-driven-development, **3 voies parallèles maximum**, adaptée à WSL2 16 Go
> (≈ 12 Go réellement utilisables, cf. mémoire `wsl-crash-recovery-backlog-relaunch`).

**Goal :** passer chaque ligne `planned_*`/`unknown` à `implemented` **ou** à un statut terminal
motivé (`out_of_scope`, `license_blocked`) — aucune ligne ne reste « planned » sans décision.
Les 120 lignes (108 + 12) sont réparties en 10 voies ci-dessous.

**Non-objectifs :** SDK de transformer Python / notebooks (rangs FME 20-21), les 25 `out_of_scope` existants,
les 10 `license_blocked` (la licence ne change pas).

---

## Décisions actées par Tanguy (2026-10-15) — priment sur le reste du document

- **D1 : différée** — H (OTB), I (`PythonCaller`, `NLP*`, Autodesk, Trimble) **restent `planned_*`**, hors de cette exécution. Aucune reclassification.
- **D2 : acceptée** — `TCPIPReceiver/Sender`, `JMSReceiver/Sender` → `out_of_scope` motivé (sockets hors garde d'egress).
- **D4 : pas de PDAL** — voie G **abandonnée** ; les 16 lignes `planned_pdal` → `out_of_scope` motivé (décision produit 2026-10-15), pas de sidecar PDAL.
- **D5 : acceptée** — driver GDAL absent de l'image (amd64 ou arm64) → `out_of_scope` motivé, pas de build GDAL maison.
- **Exécution** : vagues 0 → 1 → 2 → 3 (F2 seule) enchaînées sans arrêt ; périmètre implémenté = voies A, B, C, D, E (10 ops), F1, F2 ≈ 87 lignes.

## 0. Garde-fous mémoire (non négociables)

| Règle | Pourquoi |
|---|---|
| **≤ 3 sous-agents simultanés**, 1 worktree chacun (`fme-lane-<x>`), supprimé à la fusion | un `uv sync` + pytest ≈ 1,5-2 Go par voie ; 3 voies + postgis-test + Docker ≈ 10 Go |
| Avant chaque dispatch : `free -m` → si `available < 3500 Mo`, on n'envoie pas | le plafond Hyper-V, pas Docker, a déjà crashé WSL |
| **pytest ciblé uniquement** (`pytest tests/pipelines/test_<voie>*.py`), jamais la suite complète dans une voie ; **en foreground** | le watchdog tue les jobs de fond sous contention (mémoire priorite-moyenne-sante-90) |
| **Une base Postgres par voie** (`CORE_TEST_DATABASE_URL=…/gs_test_<voie>`) sur le `postgis-test` partagé | collisions `UniqueViolation`/`DuplicateTable` entre sessions (piège SP-49) |
| DuckDB en test : `SET memory_limit='768MB'; SET threads=2` ; GDAL : `GDAL_CACHEMAX=256` | rasters/nuages de points = les seuls vrais mangeurs |
| Fixtures binaires **< 1 Mo** (GeoTIFF 64×64, LAS 1 000 pts) ; jamais de jeu réel | idem |
| Voies natives lourdes (raster, PDAL, OTB) : **jamais en parallèle entre elles** | voir §3 |
| Suite complète (pytest + vitest + E2E + build) : **le contrôleur seul, en série, entre deux vagues** | pas de 3 suites complètes en parallèle |
| Pas de `docker build` dans une voie ; les images sidecar se construisent en fin de vague, une à la fois | RAM + disque |
| Sous-agents d'implémentation : `sonnet` ; revue finale de vague : `opus` | coût/qualité |

## 1. Tâche 0 — Audit de péremption + couture de registre (contrôleur, avant toute voie)

1. **Audit de péremption de la matrice** (piège n°12 : le récit ≠ le code). La matrice date d'avant ARC-33
   (`reader.raster`, `transform.zonalStats`, proxy TiTiler) et du retrait QGIS : relire chaque ligne `planned_gdal`/`planned_otb`
   contre `OPERATIONS` réel et reclasser ce qui est déjà couvert. Sortie : `docs/revue/2026-10-15-audit-peremption-fme.md`.
   Le périmètre des voies F1/F2 peut rétrécir.
2. **Couture anti-conflit** : aujourd'hui `ops/contracts.py` (import central de tous les `*Params` de `ops/schemas.py`)
   est le point de collision de toute voie. Avant de paralléliser : chaque voie reçoit **son module** `ops/<voie>.py`
   qui exporte `CONTRACTS: list[OperationContract]` + ses modèles `*Params` **dans le même fichier** ;
   `contracts.py` ne fait plus qu'agréger (`OPERATIONS = {**base, **a.CONTRACTS, …}`). Une ligne par voie, ajoutée par le contrôleur à la fusion.
   *Acceptation* : `test_operation_contract` + `lint-imports` verts ; catalogue inchangé (59 exposées / 61 brutes) ; zéro régression.
3. **Gabarit de voie** (`docs/superpowers/plans/_fme-lane-template.md`) : la liste de contrôle par op (§2) copiée dans chaque brief.
4. Tête Alembic, `git fetch`, `git worktree list` (aucun orphelin), `.superpowers/sdd/fme-<voie>-*` pour les ledgers (piège n°9).

## 2. Définition de « fait » pour une op (gabarit de brief, par transformer)

Chaque op, TDD (test rouge d'abord) :
- [x] `OperationContract` complet : schéma Pydantic strict, `engine`, **`engine_license`**, `execution_model`, règle de SRID de sortie, `is_copyleft` (⇒ sidecar obligatoire, vérifié à la construction).
- [x] **Masquage GAP-22** : une colonne masquée n'est jamais lue ni exposée par l'op ni son aperçu (jumelle déjà oubliée en P15).
- [x] **Réseau** : toute op qui sort du process passe par `egress.py` (garde SSRF + épinglage DNS) ; secrets **uniquement** via le coffre, URL bornée à la portée du secret (REV-294) ; plafonds de lignes/octets/durée.
- [x] Aperçu : comportement défini (lecture seule ⇒ OK ; effet de bord ⇒ aperçu **interdit** ou borné aux GET, cf. `httpCall`).
- [x] Étiquette i18n (détecteur de couverture en CI), entrée de palette du builder, doc d'op.
- [x] Ligne `matrice-couverture-fme.jsonl` : `coverage_status`, `geostudio_equivalent`, `engine_license`, notes.
- [x] 1 test d'**erreur par ligne / entrée dégénérée** (géométrie nulle/vide, colonne absente) — classe de défauts REV-195→199.

Intégration de fin de voie (contrôleur) : OpenAPI + types TS (incantation `api-types-drift`, **piège n°1**), `inventaire-fonctionnalites.jsonl`,
`lint-imports`, `ruff`, `mypy --strict` si le module est dans la liste, `test_deployability` pour toute nouvelle variable d'environnement **vérifiée par valeur** (piège n°2).

## 3. Voies (120 lignes)

Chaque voie = 1 sous-agent d'implémentation (tâches en séquence **à l'intérieur** de la voie), 1 revue par tâche, 1 revue de voie.

### Vague 1 — in-process, sans dépendance native nouvelle (3 voies en parallèle, ~3 Go chacune)

**Voie A — Attributs, filtres, SCR, texte, logique (19)** · `ops/attrs.py`
- Compositions (2-3 op existantes, déjà atteignables, à matérialiser en op unique) : `AttributeManager`, `DatabaseJoiner`, `AggregateFilter`, `Matcher`.
- Filtres : `GeometryFilter`, `AttributeRangeFilter`, `PlanarityFilter`, `SpatialRelator`, `FeatureTypeFilter`.
- SCR : `CoordinateSystemRemover`, `LatLongToMGRSConverter`, `MGRSToLatLongConverter` (lib `mgrs` MIT : à vérifier sur l'image, piège n°3), `LocalCoordinateSystemSetter`.
- Texte : `HTMLExtractor`, `TextEncoder`/`TextDecoder` (`encoding_rs` ⇒ en Python, `codecs` stdlib — **le moteur « rust » de la matrice se simplifie**), `TextureCoordinateSetter`.
- Logique : `Terminator` (arrêt contrôlé d'un run), `ParameterFetcher` (paramètres de run, existants depuis la vague 4).
- *Acceptation* : 19 lignes `implemented`, aucune nouvelle dépendance hors `mgrs`.

**Voie B — Bases de données & formats tabulaires (7)** · `ops/dbio.py`
- `DatabaseUpdater`, `DatabaseDeleter`, `SQLCreator` : **écriture externe** ⇒ secret de connexion en lecture/écriture distinct, `WHERE` obligatoire et borné aux clés fournies (**jamais** de `DELETE`/`UPDATE` sans clé — même règle que `writer.collection`), paramétrage SQL (jamais de concaténation), transaction unique, aperçu interdit.
- `MongoDB` (reader), `Microsoft Excel` (writer — le reader existe), `Google Sheets` (OAuth via coffre), `TopoJSON` (reader/writer).
- *Acceptation* : un test d'injection SQL par op d'écriture ; 2ᵉ run idempotent.

**Voie C — Géométrie (15)** · `ops/geom2.py` — Shapely/GEOS (BSD) et DuckDB spatial, **pas** GDAL malgré l'étiquette de la matrice (à corriger : `engine` ← `shapely`/`duckdb`).
- `Triangulator`, `VertexRemover`, `SpikeRemover`, `AreaGapAndOverlapCleaner`, `AreaAmalgamator`, `AreaBuilder`, `Intersector`, `LineOnAreaOverlayer`, `LineCombiner`, `DonutHoleExtractor`, `Chopper`, `GeometryCoercer`, `AffineWarper`, `RubberSheeter`, `CoordinateSystemDescriptionConverter`.
- Les 5 premières sont des opérations **topologiques** : borne de complexité (nombre de sommets, timeout) et test « entrée dégénérée » obligatoires.
- *Acceptation* : parité de résultat vs Shapely sur un jeu de 10 géométries pièges (vides, multi, anneaux inversés).

### Vague 2 — réseau + raster (3 voies, **une seule voie native**)

**Voie D — Stockage fichier & SaaS (10)** · `ops/cloudfiles.py` — Azure Files, Dropbox, Box, Google Drive, OneDrive, SharePoint Online, HDFS, `FTPCaller`, `ArcGISOnlineConnector`, `CKANConnector` (réutiliser la logique du connecteur de moissonnage CKAN de SP-12).
- Un seul patron `reader`/`writer` sur `fsspec` **si** déjà présent dans l'image (sinon une dépendance MIT/BSD par fournisseur, arbitrage Tanguy). Egress + coffre + plafonds (ADR 0012 connecteurs). FTP : TLS requis par défaut.

**Voie E — Messagerie & notification (14)** · `ops/messaging.py` — `Emailer`, `SlackConnector`, `TrelloConnector`, `MCPCaller`, `RabbitMQ`, `AzureServiceBus`, `AzureQueueStorage`, `KinesisReceiver`/`Sender`, `SNSSender`, `JMSReceiver`/`Sender`, `TCPIPReceiver`/`Sender`.
- **Décision de périmètre à trancher** (voir §5) : `TCPIP*` et `JMS*` = sockets arbitraires, incompatibles avec la garde d'egress sans liste d'hôtes autorisés par secret ; les *receivers* sont des déclencheurs long-vivants (déjà couverts par webhook entrant + déclencheur S3, ADR 0027).
- `Emailer` réutilise le SMTP TLS de `alerts/` ; `MCPCaller` n'a **que** les permissions de l'utilisateur et est audité (règle MCP du dépôt).

**Voie F1 — Raster ops (17)** · `ops/raster2.py` — `rasterio` (BSD, déjà dans `pyproject.toml`), lecture **fenêtrée**, jamais de raster entier en RAM.
- `RasterCellValueCalculator`, `RasterConvolver`, `RasterMosaicker`, `RasterPyramider`, `RasterStatisticsCalculator`, `RasterBand{Combiner,Separator,Remover,NodataSetter}`, `RasterExtractor`, `VectorOnRasterOverlayer`, `WebMapTiler`, `ImageFetcher`, `RasterGeoreferencer`, `RasterGCPSetter`, `RasterGCPExtractor`, `SurfaceDraper`.
- Réutilise `app/raster/` (ARC-33) et le sidecar `desktop-etl` déjà gelé avec rasterio. RLS/masquage **par item raster** (jumelle ARC-33).

### Vague 3 — natifs lourds et décisions (voies **strictement en série**, une à la fois)

**Voie F2 — Lecteurs raster/vecteur GDAL (12)** · `ops/readers2.py` — `GeoTIFF`, `NetCDF`, `ERDAS .img`, `JPEG 2000`, `GRIB`, `Sentinel-2 SAFE`, `Landsat-8`, `WMS`, `WCS`, `OSM XML/PBF`, `CityGML`, `CityJSON`.
- Passer par `reader.file` (flag `CORE_PIPELINE_FILE_IO_ENABLED`, **allowlist de répertoires**) et le chemin d'import GDAL existant (FileGDB/DXF/DGN, ARC-23) ; **VRT refusés** (déjà acquis).
- Piège : les drivers NetCDF/GRIB/JP2000 dépendent du build GDAL de l'image **arm64** (portage multi-arch) : spike d'une demi-journée sur les deux architectures avant d'engager la voie. Driver absent ⇒ ligne `out_of_scope` motivée, pas de build GDAL maison.
- `WMS`/`WCS` : egress + plafond de pixels.

**Voie G — Nuage de points PDAL (16)** · sidecar dédié — `PointCloud{Combiner,Merger,Filter,Thinner,Simplifier,Sorter,Splitter,StatisticsCalculator,SurfaceBuilder,Creator,ExpressionEvaluator,ToPointCoercer,TransformationApplier}` + readers `LAS/LAZ`, `EPT`, `E57`.
- **Spike obligatoire d'abord** : PDAL (BSD) n'a pas de roue PyPI fiable (libpdal). Soit sidecar conteneur (`execution_model="sidecar"`, comme feu `qgis-worker`, mono-arch assumé et publié `amd64` seul) soit abandon motivé. **Aucun** build dans le process `core`.
- Mémoire : fixtures LAS de 1 000 points, jamais de LAZ réel en CI ; limite de points/run ; **voie seule sur la machine**.
- Atout : fait aussi `SurfaceBuilder` ⇒ débloque la partie « nuage → MNT » pour `terrain3d`.

**Voie H — OTB (3)** — `RasterSegmenter`, `RasterObjectDetector`, `RasterObjectDetectionModelTrainer`. Image ≈ 1 Go + modèles : **recommandation = `out_of_scope` motivé** pour le détecteur et l'entraîneur (pas de pile ML dans le produit, Q2 « horizontal ») ; `RasterSegmenter` seulement si le spike G est concluant (réutilise le même patron sidecar). Décision Tanguy requise (§5).

**Voie I — Intégrations propriétaires & exécution de code (7)** — `PythonCaller`, `NLPClassifier`, `NLPTrainer`, `AutodeskBIM360Docs`, `AutodeskDocs`, `TrimbleConnect`, `TrimbleUnity`.
- `PythonCaller` = exécution de code arbitraire côté serveur : **recommandation `out_of_scope`** (contredit « pas de logique cachée hors config » et le SDK Web Components) ; l'équivalent déclaratif est CEL + `transform.derive`.
- `NLP*` : `out_of_scope` (pas de pile ML) ; Autodesk/Trimble : API propriétaires sans compte de test ⇒ **différés** sauf demande explicite d'un utilisateur.

## 4. Ordonnancement et estimation

| Vague | Voies | Parallélisme | Lignes | Effort agent estimé* |
|---|---|---|---|---|
| 0 | Tâche 0 (audit + couture) | 1 | — | ½ j |
| 1 | A, B, C | 3 | 41 | 2-3 j |
| 2 | D, E, F1 | 3 (F1 seule native) | 41 | 3-4 j |
| 3 | F2 → G → H → I | **série** | 38 | 4-6 j |
| Clôture | revue finale opus par vague + suite complète | 1 | — | 1 j |

\* durée murale avec 3 agents, hors temps de revue humaine ; ≈ 10-14 j murales au total. L'ordre des vagues 2/3 est interchangeable ; **G (PDAL) ne démarre pas tant que son spike n'est pas concluant**.

Entre deux vagues, le contrôleur, **seul** :
1. fusionne voie par voie dans `dev` (re-vérifier `git rev-list --left-right --count origin/dev...dev` : `dev` avance pendant un plan long) ;
2. lance **en série** : `ruff` + `mypy --strict` ciblé + `lint-imports` → `pytest` complet (base réelle exigée) → `npm run test` → `npm run build` → **E2E complète** (piège n°6) ;
3. régénère OpenAPI + types TS, `feature_health_cli.py --write`, matrice FME ; compteur du catalogue (`GET /pipelines/ops`) mis à jour dans les tests ;
4. **revue finale de branche, sous-agent opus** (≠ revue par tâche, piège n°4) avec la liste des jumelles : masquage GAP-22 sur chaque nouvelle op de lecture, garde d'egress sur chaque op réseau, secrets scopés, aperçu des ops à effet de bord, SRID de sortie ;
5. supprime worktrees et branches `fme-lane-*` fusionnés ; PR `dev` → `main`.

## 5. Décisions à valider par Tanguy **avant** la vague concernée

| # | Décision | Recommandation |
|---|---|---|
| D1 | Les ~15 lignes « ML / code arbitraire / API propriétaire » (H détecteur+entraîneur, I) | `out_of_scope` motivé, pas d'implémentation |
| D2 | `TCPIP*`, `JMS*` : sockets arbitraires | `out_of_scope` ; messagerie = AMQP/SQS/Service Bus/Kinesis seulement |
| D3 | Dépendances par fournisseur cloud (voie D/E) vs `fsspec` unique | `fsspec`/SDK officiel sous licence MIT/Apache uniquement ; refuser tout copyleft |
| D4 | PDAL en sidecar mono-arch `amd64` | oui, publié hors matrice multi-arch (précédent qgis-worker) |
| D5 | Une ligne FME dont le moteur n'est pas disponible dans l'image arm64 | `out_of_scope` motivé, pas de build natif maison |

Après D1/D2/D5, le décompte attendu est **≈ 95-100 lignes `implemented`** et **≈ 20-25 lignes `out_of_scope` motivées** (aucune `planned_*` résiduelle).

## 6. Clôture (même geste, jamais différé)

- [x] Une ligne par vague dans `### Livré` de `CLAUDE.md` (garde-fou de taille) ; récit complet dans l'archive d'historique.
- [x] `docs/revue/2026-09-04-analyse-gaps.md` : `GAP-nn` concernés fermés ; `backlog.md` : REV ouvertes/fermées.
- [x] Matrice FME régénérée, plus **aucune** ligne `planned_*`/`unknown`.
- [x] `docs/revue/inventaire-fonctionnalites.jsonl` + `feature_health_cli.py --write` (la CI refuse une surface non inventoriée).
- [x] ADR : un par décision D1-D5 acceptée (numérotation à partir de 0028 ; 0023/0026 restent réservés à ARC-31/35).
- [x] `CHANGELOG.md` (ops ajoutées, ops reclassées).

> **Statut final (2026-10-15)** : voies A→S exécutées et fusionnées sur `dev` (non poussé). D1 différée (OTB, voie I), HDFS en attente de décision. Voir ADR 0028 et l'archive d'exécution.
