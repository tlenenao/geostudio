# Plan — clôture des dettes du backlog et SP de mises à jour (2026-10-31)

**Entrée** : backlog `docs/revue/2026-09-04-backlog.md` (30 `ouvert` + 17 `partiel` au 2026-10-18,
recomptés par `scripts/revue/count-backlog-etat.sh`), reliquats AUD
(`docs/revue/audit-2026-10-16/100-reliquats-partiels.md`), et 3 SP nés de la session du 2026-10-31
(Dependabot : images, majeures du shell, Rust).

**Limite de la méthode** (piège n°12) : les états ci-dessous sont ceux des documents. Chaque voie
**relit le code avant d'agir** et marque « déjà fait » ce qui l'est.

## Règles d'exécution parallèle

- Une voie = un **worktree** (`.claude/worktrees/<voie>`) et une branche `fix/<voie>` issue de `dev`,
  fusionnée dans `dev` puis supprimée (CLAUDE.md). Ledgers `.superpowers/sdd/<voie>-*` (piège n°9).
- Voies **disjointes par fichiers** ; deux voies qui touchent `core/alembic/versions` ou
  `core/openapi.json` / `core-schema.d.ts` se **sérialisent** (numéros de migration, régénération des types).
- `postgis-test` partagé : **une base par voie** (`CORE_TEST_DATABASE_URL` distincte), sinon collisions
  (piège SP-49). Plafond RAM WSL ~12 Go : **3 voies simultanées au plus**, les autres en file.
- Chaque voie : TDD, revue par tâche + revue finale de branche, régénération OpenAPI/TS si route modifiée,
  entrée `### Livré` d'une ligne + archive, backlog mis à jour dans le même geste.

## Voies

| Voie | Contenu | Entrées | Conflits |
|---|---|---|---|
| **V1 Relations** | intégrité à la soumission publique/import/`writer.collection`, enfants orphelins au changement de `parent_key`, suppression de collection avec relations, `sensitiveFields` au PATCH + `FilterError`→4xx, `numberMatched` hors RLS | REV-371/372/373/374/375 (+403 pour ces jumelles) | OpenAPI |
| **V2 Base et migrations** | `lock_timeout`, 0071 HNSW concurrente, 0005/0007 sur tables non vides, FK `NOT VALID`+`VALIDATE`, downgrades gardés, `sql/init.sql` en prod, curseur `/changes`, `If-Match` | REV-376…383 | migrations |
| **V3 Images et supply chain** | USER non-root minio/titiler/postgis, digests, `scripts/` hors image, healthcheck/versions figées appexport, commit MinIO vérifié, `cpus`/`pids_limit` | REV-384/385/392/393/394/395 | `deploy/`, compose |
| **V4 Desktop** | `reader.file` (`/vsi*`, `allowed_directories`), allowlist d'op du sidecar, `Origin`/`Host`, CSP Tauri, job WebDriver rouge, `tauri-plugin-shell` 2.5 (Cargo.lock, ex-#196) | REV-386/387/388/389/390 | `desktop-etl/` |
| **V5 Core divers** | limiteur de soumission publique (Postgres), cache public OWS + `count_mode`, géocodage par lot, erreurs brutes de jobs, `/public/items` déprécié, mineurs d'addendum | REV-396/397/398/399/370/401/402 | OpenAPI |
| **V6 CI** | runs doublés push+PR, ~50 % de rouges, stabilité des parcours sous charge | REV-400/321 | `.github/` |
| **V7 SP images** | Keycloak 24→26, Martin 0.18→1.16, Node 22→25 (3 Dockerfile), `otel-lgtm` 0.37, `pgbouncer` 1.26, `golang` 1.25 : **rejeu stack réelle exigé** pour chacune | ex-#206/202/161/162/166/193/205/204/164 | `deploy/`, compose, realm |
| **V8 SP shell majeures** | eslint 10, vitest 5, typescript 7, jsdom 30, msw 3, react-hooks 7, react-router 7, lucide-static, deck.gl 9.4 + `@loaders.gl/core ~4.5` ; **import dynamique de deck.gl d'abord** (bundle 634/640 Ko) | ex-#213/214/116 | `shell/` |
| **V9 Reliquats AUD (A)** | popup CEL contexte + sanitisation (052), cache de tuiles (056), cross-filter multi-entrées (059), récents ⌘K + `HelpHint` (119), `<select>` restants (126/127), `jobs/common.py` hors contrat de couches, `invalidGeometry` + rapport par fid, API d'écriture `tenant_limits` | AUD-052/056/059/119/126/127, L12, SP-L0 | `shell/`, couches |
| **V10 Reliquats pré-release** | relire puis solder REV-275/276/277/278/280/282/283 (pipelines, fédération, alertes, contrats d'API, lac, import, troncatures) | REV-275…283 | variable |

Ordre conseillé : V6 d'abord (un CI lisible valide tout le reste), puis V2, V1, V5 (cœur) en parallèle
limité à 3, V3/V4 ensuite, V8 en dernier côté shell. V7 et V10 démarrent par un **rapport de relecture**
avant tout changement.

## Hors exécution automatique

**Décision de Tanguy requise** (liste B de `100-reliquats-partiels.md`) : AUD-010 instance dédiée,
AUD-116 contenu traduisible, 109, 091 scopes MCP, avg/min/max échantillonnés, RTL, Trivy bloquant,
captures d'écran/`examples/`, matérialisation des datasets arcgis/SQL/pipeline (SP-L0), PythonCaller/
Airbyte/Postgres HA/commentaires/RGAA (`102-l13-cadrage.md`).

**Rejeu stack réelle ou release requis** (ne se ferme pas par du code seul) : REV-368 (débit CDC v2),
REV-369 (fond vierge souverain en export réel), REV-391 (cosign sur une vraie release), REV-318/319
(journeys non rejoués), REV-269 (réglages hors dépôt), export réel SP-L0, `mc` arm64, `helm` local.

## Critère de clôture

Pour chaque voie : suites cœur + shell + E2E vertes en CI sur `dev`, backlog et `### Livré` à jour,
worktree et branche supprimés, revue finale sans Important ouvert. Puis PR `dev` → `main`.
