# Reliquats : AUD partiels ou reportés (état au 2026-10-19)

Source : sections « SP-L0 », « Lots L1a/L3/L5/L2/L1b/L6 », « SP-L4 », « L7 », « L11 » de
`docs/superpowers/2026-08-27-historique-execution-continu.md`, plus le lot L12 (couloir C).
**Limite de la méthode** : état repris de l'archive (récit, piège n°12) ; seuls les points L12
ont été revérifiés dans le code. Une relecture du code précède toute exécution d'un reliquat.
Effort : S < 0,5 j, M 0,5 à 2 j, L > 2 j.

## A. Faisables sans décision ni rejeu

Statut après relecture du code (couloir C, 2e mission). « Fait » = commit dans la branche du
couloir ; « Déjà fait » = l'inventaire était périmé (piège n°12).

| AUD | Reste | Effort | Statut |
|---|---|---|---|
| 051 | Filtre CEL par couche vers MapLibre / `ST_AsMVT` | M | Fait sur le fond (relu, couloir C 4e mission) : `MapLayer.filter` en clauses ET + `LayerFilterEditor` + `applyLayerFilter` sur couches vector/feature, plage d'échelle, aller-retour par `toFrontLayer` ; seul reste un filtre CEL libre/`ST_AsMVT` côté serveur (choix produit : clauses suffisent) |
| 052 | Contexte du popup CEL jusqu'à `MapView` ; sanitisation markdown | M | Déjà fait (relu V9) : `MapView` reçoit `popupContext` (`resolvePopupContent`), gabarit rendu par `renderPopupTemplate` (valeurs échappées puis DOMPurify, tests MapPopup/MapView) |
| 056 | Cache de tuiles ; `AsyncClient` + `Semaphore` | M | Déjà fait pour le proxy TiTiler/terrain (relu V9) : `app/tile_proxy.py` (cache borné en octets + `BoundedSemaphore`, `CORE_TILE_PROXY_CONCURRENCY`, commit 697de8f7) ; reste le cache des tuiles MVT vectorielles (clé = rôle + limites géographiques + invalidation de compaction, spec 0181 : décision de conception) |
| 057 | Séries cartographiques, mise en page composable, pied de page PDF | L | Cadré dans `101-reliquats-L-cadrage.md` |
| 059 | Comparaison conserve filtres et mesure ; cross-filter multi-entrées ; filtre au clic | M | Partiel : comparaison de périodes garde les filtres de la source d'origine (fait) ; cross-filter multi-entrées : fait (V9, `Record<dataset, Record<origine, entrée>>` shell + `Bookmark.crossFilter` cœur, lecture tolérante de la forme plate) ; reste le filtre au clic |
| 099 | Pré-agrégation/cache/backfill/index | L | Partiel : cache d'agrégat et `statement_timeout` déjà là (relu) ; fait : backfill CDC en flux par segments, créneaux d'agrégat par tenant (429). Ouverts : cache de tuiles, `CollectionIndex` (spec 0181 dans la spec courte) |
| 014 | Lecture en flux OGR/GeoParquet/XML | L | Fait : fenêtres OGR/GeoParquet, `iterparse` XML ; import reste atomique (décision) ; reste le téléchargement S3 intégral en mémoire (`bytes`) |
| 029 | Arrêt d'un code Python bloquant en cours de nœud | M | Ouvert : exige des sous-processus par nœud (spec courte), SP à part |
| 115 | Erreurs/e-mails/DCAT localisés, `users.locale`/`timezone`, timeZone alertes/rapports/exports | L | Partiel : `users.timezone` consommé (défaut du `timeZone` d'agrégat sur routes/MCP/alertes, heure d'émission des e-mails d'alerte et de rapport, XLSX et nom de fichier d'export agrégé) ; XLSForm multilingue fait ; DCAT `@en` (D8) et RTL (décision) non entrepris |
| 119 | Recherche d'items/récents dans ⌘K, `HelpHint` | M | Partiel : recherche d'items du catalogue faite (palette) ; récents ⌘K déjà faits (`readRecentItems`, relu V9) ; `HelpHint` existe (PropsPanel, PopupEditor), généralisation = polish ouvert |
| 126/127 | Fonds de carte thémés, contrôles vers le kit | M | Partiel : fond vierge thémé (`--gs-map-land`, repeint au changement de thème) ; 64 `<select>` migrés vers `NativeSelect`, cliquet `rawControlGuard` sur select/input/textarea hors kit ; restent les `<select>` à `className` dynamique et ~240 `<input>`/`<textarea>` (baseline `shell/src/test/rawControlBaseline.json`) ; non traité en V9 (migration mécanique sur ~240 sites) ; NTF/CRS DOM (127 côté cœur) non traité |
| 097 | `expires_at` : partage expiré encore listé dans GET sharing | S | Fait (`list_shares` et `get_collection_sharing` filtrent par `share_active`) |
| SP-L4 | `/admin/usage` sans `maxUsers`/`maxActiveRuns` ; API d'écriture de `tenant_limits` | S/M | Partiel : `maxUsers`/`maxActiveRuns` exposés et affichés ; `PUT /v1/admin/usage/limits` (`admin.quotas.manage`, audité, test) déjà livré — relu V9 |
| L12 | `jobs/common.py` hors contrat de couches (cycle items/notifications) ; `jobs/__init__`, `recovery.py` hors strict | M | Ouvert, cadré V9 : 18 importeurs de `jobs.common` ; il tire `Item`, `User`, `notifications.repository` (3 imports ; les 3 usages sont la notification de fin de job et la résolution de session de tâche) ; refonte = passer le rappel de notification en paramètre/registre posé au démarrage, puis ajouter `app.jobs.common` aux couches ; > 1 jour avec les 18 sites et les tests, non commencé |
| L12 | Découper MapView (991 kB) / deck.gl : marge de bundle 10 Ko sur 640 | M | Ouvert (non traité) |
| L12 | Seed de démo : pipeline et alerte | S | Fait (+ jeu de données ; pipeline derrière `CORE_ETL_ENABLED`) |
| L1b/L6 | Jumelles `.defer()` sans balayage | M | Fait pour alerts/service, harvest/routes, quality/routes (`defer_resilient`) et balayages tolérants par élément ; déjà traité (relus) : geocoding/routes (balayage `sweep_geocode_jobs_task`), compliance/routes (reçu clos en échec si le defer échoue), embeddings (defer après commit + balayages) ; DROP des TEMP TABLE non traité |
| SP-L0 | Matérialisation datasets arcgis/SQL/pipeline | M | Ouvert : `appexport/datasets.py` refuse proprement (message français) les datasets non adossés à une collection ; la matérialisation demande une décision de périmètre (snapshot au moment de l'export) |
| SP-L0 | `ST_MakeValid` des intersections | M | Fait (`transform.intersection`, `spatialJoin`) ; paramètre `invalidGeometry` (`repair`/`skip`/`error`) déjà livré sur `intersection`/`spatialJoin` (`_guarded`, relu V9) ; rapport par fid des lignes écartées ouvert : exige un canal de rapport pour un nœud non-writer (hors `succeeded_with_rejects`), décision de forme |
| SP-L0 | bowtie MultiPolygon sur colonne Polygon | M | Déjà fait : rejet `geometry_mismatch` dans le rapport d'ajout (test ajouté) |
| SP-L0 | fan-out `detectChanges` | M | Déjà fait : erreur « clé dupliquée » dans le compilateur |
| SP-L0 | ctx > 16000 car. | M | Fait (message dédié à l'export, 422) |
| SP-L0 | minuterie 90 s vs 120 s | M | Fait (décompte depuis la navigation) |
| SP-L0 | `entity_history` non 4326 | M | Déjà fait : instantanés et écritures en lon/lat 4326 (`get_feature` sans `out_srid`) |
| SP-L0 | `mapWidget.tsx` ~271 | S | Fait (le badge d'échantillon est affiché) |
| SP-L0 | tolérance <= 0 | S | Fait (`snapToLayer` déjà ; `simplify` : `ge=0`, fini) |
| SP-L0 | mini-serveur d'export, lac en SRID natif | S | Fait (reprojection 4326, ajouté pendant la relecture) |

## B. Demandent une décision de Tanguy

- AUD-010 (instance dédiée, D4) ; AUD-116 (contenu utilisateur traduisible, D8) ; 109 (rattaché à L10) ; 091 (scopes MCP, L9).
- avg/min/max échantillonnés (SP-L0) ; `/public/items/{id}` servant un item `deprecated` ; RTL.
- Trivy bloquant, épinglage de digest des images de base, captures d'écran, `examples/` (L12 : défauts pris, voir la spec).

## C. Demandent un rejeu (stack réelle ou release)

- Export réel (PDF d'un tableau de bord filtré, zip d'app à `datasetId`) : AUD-133/001/003, SSRF du Chromium d'export.
- Débit CDC v2 (100 ms par ligne) ; fond vierge souverain sous sous-chemin ; journeys j02/j03/j06b/j08/j10/j10b ; e2e-oidc.
- Cosign sur une vraie release (AUD-177) ; build `mc` arm64 (seul amd64 vérifié) ; `helm` absent localement (19 tests sautés).
- L7 : suite pytest complète jamais rejouée sur base fraîche, couverture cœur non mesurée.

## D. Fermés dans ce couloir

AUD-111, 112, 113, 118, 123, 125, 137, 138 (partiel : filet nommé, découpage reporté), 139, 150
(partiel : bornes du terrain ; désynchro `timePlayer` en fin de plage non traitée).
