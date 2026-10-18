# Reliquats : AUD partiels ou reportés (état au 2026-10-19)

Source : sections « SP-L0 », « Lots L1a/L3/L5/L2/L1b/L6 », « SP-L4 », « L7 », « L11 » de
`docs/superpowers/2026-08-27-historique-execution-continu.md`, plus le lot L12 (couloir C).
**Limite de la méthode** : état repris de l'archive (récit, piège n°12) ; seuls les points L12
ont été revérifiés dans le code. Une relecture du code précède toute exécution d'un reliquat.
Effort : S < 0,5 j, M 0,5 à 2 j, L > 2 j.

## A. Faisables sans décision ni rejeu

| AUD | Reste | Effort |
|---|---|---|
| 051 | Filtre CEL par couche vers MapLibre / `ST_AsMVT` | M |
| 052 | Contexte du popup CEL jusqu'à `MapView` ; sanitisation markdown | M |
| 056 | Cache de tuiles ; `AsyncClient` + `Semaphore` | M |
| 057 | Séries cartographiques, mise en page composable, pied de page PDF | L |
| 059 | Comparaison conserve filtres et mesure ; cross-filter multi-entrées ; filtre au clic | M |
| 099 | Pré-agrégation/cache/backfill/index | L |
| 014 | Lecture en flux OGR/GeoParquet/XML | L |
| 029 | Arrêt d'un code Python bloquant en cours de nœud | M |
| 115 | Erreurs/e-mails/DCAT localisés, `users.locale`/`timezone`, timeZone alertes/rapports/exports | L |
| 119 | Recherche d'items/récents dans ⌘K, `HelpHint` | M |
| 126/127 | Fonds de carte thémés, contrôles vers le kit | M |
| 097 | `expires_at` : partage expiré encore listé dans GET sharing | S |
| SP-L4 | `/admin/usage` sans `maxUsers`/`maxActiveRuns` ; API d'écriture de `tenant_limits` | S/M |
| L12 | `jobs/common.py` hors contrat de couches (cycle items/notifications) ; `jobs/__init__`, `recovery.py` hors strict | M |
| L12 | Découper MapView (991 kB) / deck.gl : marge de bundle 10 Ko sur 640 | M |
| L12 | Seed de démo : pipeline et alerte | S |
| L1b/L6 | Jumelles `.defer()` sans balayage (alerts/service, geocoding/routes, harvest/routes, quality/routes, compliance/routes, embeddings) ; DROP des TEMP TABLE | M |
| SP-L0 | Matérialisation datasets arcgis/SQL/pipeline ; `invalidGeometry` + `ST_MakeValid` des intersections ; bowtie MultiPolygon ; fan-out `detectChanges` ; ctx > 16000 car. ; minuterie 90 s vs 120 s ; `entity_history` non 4326 ; `mapWidget.tsx` ~271 ; tolérance <= 0 | M chacun, S pour les deux derniers |

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
