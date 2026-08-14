# Rapport de correction — revue finale de branche « Hébergement de tilesets 3D Tiles uploadés »

Branche `dev`, plan `docs/superpowers/plans/2026-08-13-3d-tileset-hosting.md`
(commits d'origine `7479fd9..e177f16`). Périmètre traité : 3 Critical + 4
Important + 2 Minor (M1, M2). Aucun autre changement.

## Commits produits

| SHA | Sujet |
| --- | --- |
| `8a67f1d` | `fix(core): wire tileset3d into docker-compose and .env.example (C1)` |
| `8f214b4` | `fix(core): expose ETag in bucket CORS so browser multipart uploads work (C3)` |
| `3dbf257` | `fix(core): purge the rejected zip and lower the max-entries default (I4, I2)` |
| `ab5081f` | `fix(core): reject kind="tileset3d" on the public /configs routes (I1)` |
| `304de77` | `fix(core): stream-bounded read for the tileset3d proxy, plus clean 4xx on a bad archive (C2, M1)` |
| `45025fe` | `fix(shell): bound the tileset3d finalize poll with a deadline (I3)` |
| `eb3e6c3` | `fix(e2e): filter the default /items* mock by type (M2)` |
| `f1339ca` | `docs(core): corrige la docstring de la lecture bornée tileset3d (C2)` |

Granularité : un commit par groupe de findings, comme le reste de la branche.
Le 8ᵉ commit est une correction de commentaire née de l'auto-revue C2 (voir
§C2, « Auto-revue adversariale ») — isolée parce qu'elle corrige une
affirmation *fausse* laissée dans le code par le commit précédent.

---

## C1 — La fonctionnalité ne peut pas tourner dans le déploiement packagé

**Modifications**

- `docker-compose.yml:171` — file `tileset3d` ajoutée à la commande du worker :
  `-q ingestion,search,cdc,etl,tileset3d`. Sans elle, aucun
  `finalize_tileset3d_task` n'aurait jamais été dépilé : chaque upload serait
  resté bloqué en `finalizing` pour toujours (et, côté shell, sur un poll
  infini — cf. I3, les deux défauts se composaient exactement).
- `docker-compose.yml:129` — `CORE_TILESET3D_ENABLED: ${CORE_TILESET3D_ENABLED:-false}`
  sur le service `core`, calqué ligne pour ligne sur `CORE_EXPORT_ENABLED`
  juste au-dessus. Sans elle, le routeur `app.tileset3d` n'était jamais monté,
  quel que soit le `.env`.
- `docker-compose.yml:139` — `S3_TILESET3D_BUCKET: geostudio-tileset3d` sur
  `core`, littéral codé en dur comme `S3_UPLOADS_BUCKET`/`S3_CDC_BUCKET`
  voisins (et non `${...}`-templaté), par respect de la convention du fichier.
- `docker-compose.yml:181` — même ligne sur le service `worker`. La tâche de
  finalisation a bien un défaut (`geostudio-tileset3d`) mais les autres buckets
  y sont explicites ; l'implicite aurait été le seul du bloc.
- `.env.example:42` — `S3_TILESET3D_BUCKET=geostudio-tileset3d`.
- `.env.example:60-72` — `CORE_TILESET3D_ENABLED=false` + les trois garde-fous
  optionnels réellement lus par `core/app/tileset3d/jobs.py`, en lignes
  commentées avec un commentaire français chacune, sur le modèle des autres
  variables optionnelles du fichier :
  `CORE_TILESET3D_MAX_ENTRIES` (20000), `CORE_TILESET3D_MAX_TOTAL_BYTES`
  (21474836480 = 20 Gio), `CORE_TILESET3D_MAX_ENTRY_BYTES` (2147483648 = 2 Gio).

**Choix de conception.** Le worker ne reçoit **pas** `CORE_TILESET3D_ENABLED`,
conformément au brief et au précédent du fichier : l'enregistrement des tâches
dans `app.jobs` est inconditionnel, seul le montage du routeur REST sur `core`
est verrouillé par le drapeau.

**Test.** Aucun test automatisé — ce sont des fichiers de déploiement non
couverts par la CI de ce dépôt (même situation que les fixes de câblage compose
de SP-17a). Vérifié par relecture croisée avec les variables réellement lues
dans `core/app/tileset3d/{jobs,routes}.py` et `app/auth/dependency.py`.

---

## C2 — Zip-bomb : `zf.read(path)` matérialise l'entrée avant tout plafond

**Modifications** — `core/app/tileset3d/routes.py`

- `:54-58` — `_max_entry_bytes()`, calqué sur `get_tileset3d_bucket()`
  (`os.environ.get(...)` direct, style déjà en place dans ce fichier), lisant
  la **même** variable et le **même** défaut que
  `app.tileset3d.jobs._max_entry_bytes`.
- `:61` — `_READ_CHUNK_BYTES = 1024 * 1024`.
- `:64-89` — `_read_entry_bounded()` : `zf.open(path)` + lecture par tranches
  de 1 Mio, `HTTPException(413, "entry too large")` dès que le cumul dépasse le
  plafond.
- `:178` — appel substitué à `zf.read(path)`.

**Placement.** Helper local à `routes.py` plutôt qu'import partagé depuis
`app.tileset3d.jobs` : `routes.py` importe déjà `app.tileset3d.storage` mais
jamais `jobs` (qui tire `app.jobs`/procrastinate — inutile sur le chemin d'une
requête HTTP). La duplication est de 3 lignes, et le commentaire pointe
explicitement le jumeau pour que les deux plafonds restent alignés.

### Auto-revue adversariale (demandée au §7 du brief)

J'ai vérifié empiriquement au lieu d'affirmer, et **j'ai trouvé que la prémisse
du finding est partiellement inexacte** :

1. **`zf.open()` streame-t-il vraiment ?** Oui, mesuré. Sur une entrée de
   64 Mio (zip de 65 Kio, zéros compressés), `tracemalloc` donne :
   `zf.read()` → **pic de 141,45 Mio** ; lecture bornée (plafond 1 Kio) →
   **pic de 2,2 Mio**, abandon à 1 048 576 octets lus. Le pic mémoire est donc
   réellement supprimé. Aucun doute résiduel sur ce point.
2. **En revanche, `zf.read()` n'est PAS non borné.** `ZipExtFile` borne sa
   décompression sur `zinfo.file_size` (le champ du répertoire central). Un zip
   qui **sous-déclare** une entrée ne fait donc pas exploser la mémoire :
   zipfile s'arrête à la taille annoncée puis échoue le contrôle CRC. Vérifié
   en fabriquant le zip menteur (8 Mio réels, `usize` du répertoire central
   réécrit à 10) : `zf.read()` lève `BadZipFile: Bad CRC-32`, il ne renvoie ni
   ne bufferise 8 Mio.

   **Le vrai défaut est donc l'absence de tout plafond à la lecture**, pas la
   métadonnée mensongère : une entrée déclarant légitimement jusqu'à
   `CORE_TILESET3D_MAX_ENTRY_BYTES` (2 Gio par défaut) était intégralement
   chargée en mémoire à **chaque requête du proxy**, et rien côté lecture ne
   revérifiait ce plafond. Combiné à I1 (avant correction), un `sourceKey`
   arbitraire pouvait de surcroît désigner un zip **jamais validé** — donc
   jamais passé par le contrôle `max_entry_bytes` de la validation. Le fix
   ferme les deux angles ; la sévérité Critical reste justifiée, la mécanique
   décrite dans le finding non.

   J'ai corrigé la docstring en conséquence (commit `f1339ca`) : elle affirmait
   le mécanisme inexact, ce qui aurait induit en erreur la prochaine lecture.
3. **`HTTPException(413)` peut-il être avalé par mon propre `except` élargi ?**
   Non, vérifié : `HTTPException.__mro__` = `(HTTPException, HTTPException,
   Exception, BaseException, object)` — ni `RuntimeError` ni
   `NotImplementedError` n'y figurent.
4. **Pic résiduel connu, non corrigé (délibéré).** `b"".join(chunks)` double
   transitoirement l'empreinte au moment de l'assemblage : un fichier
   légitime de N octets coûte ~2N en pointe. C'est le comportement de
   `zf.read()` aussi, la route doit de toute façon renvoyer un `Response`
   corps-en-mémoire, et streamer la réponse (`StreamingResponse`) sortirait du
   périmètre de ce lot de corrections.

**Tests** — `core/tests/test_tileset3d_routes.py`

- `test_read_tileset3d_entry_413_when_the_decompressed_entry_exceeds_the_cap`
  (`:212-231`) : `CORE_TILESET3D_MAX_ENTRY_BYTES=1024` par `monkeypatch` +
  entrée réelle de 8 Mio compressibles → 413 `"entry too large"`, et une entrée
  sous le plafond répond toujours 200 par le même chemin.

  **Justification de la construction** (le brief laissait le choix) : la
  variante « répertoire central qui sous-déclare » **ne peut pas** exercer le
  garde de taille, précisément à cause du point 2 ci-dessus — zipfile
  s'arrêterait à la taille annoncée et lèverait `BadZipFile` avant que le cumul
  n'atteigne le plafond. Seul un plafond abaissé face à une entrée réellement
  volumineuse franchit la branche `total > max_bytes`. La construction menteuse
  est donc réaffectée au test M1 ci-dessous, où elle est exactement pertinente.

**M1 (groupé, même fonction)** — `core/app/tileset3d/routes.py:180-186` :
`except (zipfile.BadZipFile, RuntimeError, NotImplementedError)` →
`HTTPException(422, "cannot read entry")`, en plus du `except KeyError` → 404
préservé. Couvre l'archive corrompue/tronquée, l'entrée chiffrée
(`RuntimeError: File is encrypted`) et la méthode de compression non supportée
(`NotImplementedError`), qui produisaient toutes un 500 non typé. 422 retenu
par cohérence avec l'usage de ce code dans le dépôt pour « requête
authentifiée mais matériel malformé ». Le `try` englobe aussi la construction
`zipfile.ZipFile(range_file)`, donc une archive globalement illisible est
couverte au même titre.

- `test_read_tileset3d_entry_422_for_a_corrupt_entry` (`:234-259`) : zip dont
  le `usize` du répertoire central est réécrit à 10 pour une entrée de 8 Mio →
  `BadZipFile` côté zipfile → **422 `"cannot read entry"`** au lieu du 500
  d'avant. Vérifié aussi que `zf.open()` sur un nom absent lève bien `KeyError`
  (comportement identique à `zf.read()`, donc le 404 « entry not found » est
  inchangé) — contrôlé empiriquement, pas seulement par lecture de la doc.

**Résultat** : `uv run pytest tests/test_tileset3d_routes.py -q` → `14 passed`.

---

## C3 — L'upload multipart navigateur ne peut pas lire son propre ETag

**Modification** — `core/app/ingestion/storage.py:11-16` : `"ExposeHeaders":
["ETag"]` ajouté à `_CORS_CONFIGURATION`, avec un commentaire expliquant
pourquoi (ETag n'est pas un en-tête de réponse safelisté CORS ; sans cela
`res.headers.get("ETag")` renvoie `null`, `Tileset3DPartInput.etag`
(`min_length=1`) rejette, et `/complete` répond 422 systématiquement contre un
vrai S3/MinIO — invisible en test, MSW/Playwright n'appliquant aucun CORS réel).

**Non-régression pour l'ingestion.** Ce module est partagé avec l'ingestion
GeoJSON/CSV/GPKG, qui ne lit jamais l'ETag de son propre PUT présigné :
exposer l'en-tête y est un no-op.

**Tests** — aucun changement nécessaire, vérifié après coup comme demandé :
`core/tests/test_ingestion_storage.py` et `core/tests/test_tileset3d_routes.py`
ne capturent que l'appel `put_bucket_cors` (bucket), jamais le contenu de la
configuration. `uv run pytest tests/test_ingestion_storage.py
tests/test_tileset3d_routes.py -q` → `18 passed`.

---

## I1 — Aucun validateur sur les écritures `/configs` de `kind="tileset3d"`

**Modifications**

- `core/app/configs/tileset3d_validation.py` (nouveau) — refus inconditionnel,
  `HTTPException(422, "tileset3d configs can only be created by the finalize
  task")`. Docstring en français documentant le vecteur : sans ce garde,
  n'importe quel utilisateur authentifié POSTait un `kind="tileset3d"` avec un
  `sourceKey` arbitraire, devenait propriétaire de l'item résultant, et lisait
  ensuite les octets d'un tileset d'autrui via le proxy — lequel vérifie `can()`
  sur l'item **appelant**, jamais sur la provenance du `sourceKey` désigné.
- `core/app/configs/routes.py:16` — import aliasé, même style que les cinq
  autres (`... as _validate_tileset3d_payload`), placé après `schemas` pour
  respecter l'ordre alphabétique local.
- `core/app/configs/routes.py:102`, `:159`, `:265` — les trois points d'appel
  (create / put / patch), à la suite de `_validate_report_payload`.

**Choix de signature.** J'ai retenu la signature uniforme
`(_session: Session, config: BuilderConfig, *, user: User)` des cinq autres
validateurs, avec `_session` préfixé d'un underscore et une docstring
expliquant pourquoi les deux paramètres sont inutilisés (le refus est
inconditionnel, il n'y a rien à rechercher en base). Vérifié au préalable :
**ce dépôt n'a aucune configuration ruff** (ni `ruff.toml`, ni section
`[tool.ruff]` dans `core/pyproject.toml`, ni job CI) — aucun lint
d'argument inutilisé ne s'applique. La cohérence avec les cinq voisins prime
donc, comme suggéré. Le `# noqa: ARG001` est conservé à titre défensif si un
ruff est introduit plus tard.

**Contrat de couches** — `lint-imports` : `Contracts: 1 kept, 0 broken`. Le
nouveau module vit dans `app.configs` et n'importe pas `app.tileset3d` (qui est
*au-dessus* de `app.configs` dans le contrat) : aucune dépendance interdite.

**Confirmation demandée (point b, sans test redondant).** Relecture de
`core/app/tileset3d/jobs.py:87` : `finalize_tileset3d_task` appelle
`configs_repo.create_config(session, config, item_id=item.id,
tenant_id=tenant_id)` — un appel **repository direct**. Le validateur n'est
câblé que dans les trois gestionnaires REST de `app/configs/routes.py`, jamais
dans `repository.create_config`. Le producteur légitime est donc structurellement
inaffecté. **Confirmé par l'exécution** : le test d'intégration existant
`tests/test_tileset3d_jobs.py::test_finalize_task_creates_item_and_config_on_success`
appelle la vraie tâche de bout en bout et continue de passer (il assert
`config.config.kind == "tileset3d"` après création) — c'est la preuve
non-redondante que le chemin repository fonctionne toujours.

**Tests** — `core/tests/test_tileset3d_config_validation.py` (nouveau, calqué
sur `tests/test_report_validation.py`, qui est le fichier où vivent les tests
équivalents des autres kinds) :

- `test_ignores_non_tileset3d_kind` — un `kind="map"` traverse sans lever.
- `test_rejects_any_tileset3d_payload` — appel direct du validateur → 422.
- `test_post_configs_with_kind_tileset3d_is_rejected` — **`POST /configs` réel**
  via `TestClient`, utilisateur authentifié normal → 422 + message exact.

`uv run pytest tests/test_tileset3d_config_validation.py -q` → `3 passed`.

### Effet de bord traité : un test existant encodait le trou de sécurité

`tests/test_tileset3d_schema.py::test_tileset3d_config_round_trips` (Task 2)
créait sa config par `POST /configs` avec `kind="tileset3d"` et attendait 201 —
c'est-à-dire qu'il **assertait précisément le comportement que I1 supprime**.
Il a échoué à la première exécution de la suite complète.

Correction retenue : le test emprunte désormais le chemin producteur réel
(`items_repo.create_item` + `configs_repo.create_config`, exactement ce que fait
la tâche de finalisation) pour semer sa donnée, **la lecture restant vérifiée
via l'API REST** (`GET /configs/by-item/{id}`). L'intention d'origine du test
— « le kind `tileset3d` fait un aller-retour fidèle à travers le stockage et la
sérialisation » — est intégralement préservée ; seule la porte d'entrée change,
pour celle qui est légitime. Le second test du fichier
(`test_tileset3d_config_requires_tileset3d_payload`, 422 sur payload manquant)
est inchangé et passe toujours pour la bonne raison : la validation Pydantic du
corps s'exécute avant le gestionnaire de route, donc avant mon validateur.

---

## I2 — Plafond `_max_entries` trop haut par défaut

**Modification** — `core/app/tileset3d/jobs.py:41` : défaut `200000` → `20000`.
Réduction ×10 du pire cas de coût d'analyse du répertoire central par requête,
tout en restant large devant la cible « des dizaines de milliers de fichiers »
énoncée par le plan lui-même. `.env.example` documente le nouveau défaut (20000).

Palliatif assumé, pas un correctif complet : un cache du répertoire central par
process serait la vraie réponse — **explicitement hors périmètre, non tenté**,
comme demandé.

**Tests** — aucun test n'assertait ce défaut (les tests de
`test_tileset3d_storage.py` passent tous `max_entries` explicitement, la fixture
de `test_tileset3d_jobs.py` fixe la variable d'environnement à `1000`). Aucune
régression : suite complète verte.

---

## I3 — Poll infini + garde de fermeture = boîte de dialogue infermable

**Modifications** — `shell/src/shell/Tileset3DUploadButton.tsx`

- `:14-19` — `POLL_TIMEOUT_MS = 5 * 60 * 1000`, avec le commentaire expliquant
  la composition des deux défauts.
- `:23-25` — signature `({ pollTimeoutMs = POLL_TIMEOUT_MS }: { pollTimeoutMs?:
  number } = {})`. Prop **optionnelle** : aucun site d'appel existant ne change.
- `:41-58` — `poll()` calcule `deadline` à l'entrée et, après chaque lecture de
  statut non terminale, bascule en `phase="error"` avec
  « La validation du tileset prend trop de temps. Réessayez plus tard. » —
  `busy` retombe, la boîte redevient fermable.

**Choix testabilité (laissé à mon jugement par le brief).** J'ai retenu la
**prop injectable** plutôt que `vi.useFakeTimers()`. Raison : ce fichier de test
est intégralement MSW + `userEvent` en temps réel, et `userEvent` pilote son
propre ordonnanceur — combiner faux timers et `userEvent` y impose soit
`advanceTimers`, soit un `userEvent.setup({ advanceTimers })` qui contamine les
trois tests existants du fichier pour un seul nouveau cas. La prop est inerte en
production (défaut inchangé) et n'ajoute aucune surface publique réelle.

Valeur retenue dans le test : `pollTimeoutMs={0}`. Le délai étant vérifié
**après** chaque lecture de statut, `0` fait expirer la première lecture non
terminale — déterministe (pas de dépendance à la latence MSW, contrairement à
une valeur comme `1`) et sans attendre les 1,5 s de l'intervalle de poll.

**Test** — `shell/src/shell/Tileset3DUploadButton.test.tsx:73-108`,
`« gives up on a job that never finishes, and lets the dialog be closed again »` :
handler `/tileset3d/uploads/job-1` renvoyant **toujours** `status: "finalizing"`
→ assertion du message d'erreur, puis assertion que « Annuler » n'est plus
désactivé et **ferme effectivement** la boîte. C'est ce second volet qui prouve
le findings dans son entier (le blocage, pas seulement le message).

`npx vitest run src/shell/Tileset3DUploadButton.test.tsx` → **4 passed** (les 3
existants + le nouveau).

---

## I4 — Le zip d'un upload rejeté n'est jamais purgé

**Modification** — `core/app/tileset3d/jobs.py:96-106` : dans la branche
`except Tileset3DValidationError`, `delete_object(Bucket=_tileset3d_bucket(),
Key=source_key)` **avant** `mark_error`, enveloppé dans son propre
`try/except Exception` qui journalise (`logger.exception`) et avale. Un échec de
purge n'est pas pire que le comportement d'avant et ne doit jamais empêcher
`mark_error` de tourner ni masquer l'erreur de validation destinée à
l'utilisateur.

Conformément au brief, **aucun** nettoyage ajouté pour le cas « abandonné avant
`/complete` » (uploads multipart incomplets) : la spec le couvre par une
politique de cycle de vie du bucket, mécanisme distinct, hors périmètre.

**Test** — `core/tests/test_tileset3d_jobs.py` :

- Fixture `_FakeS3Client` (`:19-27`) — `delete_object` n'existait pas ; ajouté
  avec un suivi `self.deleted: list[tuple[str, str]]` et retrait effectif de la
  clé, dans le style des autres méthodes suivies (`# noqa: N803` compris).
- `test_finalize_task_marks_error_on_invalid_zip_without_creating_an_item`
  (`:157-160`) étendu : assert `fake_s3.deleted == [(bucket, "k")]` **et**
  `"k" not in fake_s3.objects`.

`uv run pytest tests/test_tileset3d_jobs.py -q` → `3 passed`.

---

## M2 — Le handler `/items*` par défaut de `e2e/mocks.ts` ne filtre pas par `type`

**Modification** — `shell/e2e/mocks.ts:56-68` : le filtre `type` de
`harvest-wms.spec.ts` (commit `e177f16`) est appliqué au handler par défaut
partagé —
`ALL.filter((r) => !deleted.has(r.pk) && (!type || r.resourceType === type))`.
`LayerPicker` interroge ce même endpoint générique en `?type=tileset3d` à chaque
rendu ; un handler qui ignore le paramètre fabrique des `LayerSource` fantômes
portant le titre d'une autre source (violation du mode strict Playwright). Le
correctif de Task 13 n'avait traité que l'override local du spec, laissant
l'amorce armée pour le prochain.

**Vérification** — suite E2E complète relancée comme exigé :
`npm run e2e` → **99 passed (1.3m)**, `tileset3d.spec.ts` inclus. Aucune spec ne
dépendait de l'ancien comportement non filtré ; aucun override local à corriger.

---

## Résultats de vérification

| Suite | Commande | Résultat |
| --- | --- | --- |
| Cœur | `cd core && uv run pytest -q` | **1437 passed, 145 skipped** (99 s) |
| Frontières de modules | `cd core && uv run lint-imports` | **1 kept, 0 broken** |
| Dérive OpenAPI/TS | `export_openapi.py` + `npm run gen:api-types` + `git diff` | **aucune dérive** |
| Shell (unitaire) | `cd shell && npm run test` | **140 fichiers, 1161 passed** |
| Shell (ciblé I3) | `npx vitest run src/shell/Tileset3DUploadButton.test.tsx` | **4 passed** |
| Shell (build) | `cd shell && npm run build` | **✓ built in 14.60s**, `tsc --noEmit` propre |
| E2E | `cd shell && npm run e2e` | **99 passed** (1.3 min) |

### Dérive OpenAPI/TS — vérifiée explicitement

`CLAUDE.md` signale cet oubli comme récurrent (4ᵉ occurrence sur ce dépôt). J'ai
**reproduit le job CI `api-types-drift` à l'identique** (mêmes commandes, même
`CORE_SECRETS_MASTER_KEY` de test) : `core/openapi.json` et
`shell/src/api/generated/core-schema.d.ts` sont inchangés. Attendu — aucun de ces
correctifs ne touche à une signature de route, un `response_model` ou un schéma
Pydantic ; les 413/422 ajoutés sont des `HTTPException` levées, non déclarées.

---

## Points à signaler

1. **Test préexistant instable, non corrigé (hors périmètre).**
   `tests/test_report_repository.py::test_list_due_reports_respects_cron_cadence_against_last_run`
   a échoué à une exécution de la suite complète, puis passé à la suivante. Ce
   n'est **pas** lié à ces correctifs : le test appartient à SP-17b, et
   `git diff HEAD -- app/reports tests/test_report_repository.py` est vide.
   C'est une instabilité d'horloge murale, démontrée : le test sème un run
   « vieux de 1 minute » sur un cron `*/5 * * * *` et attend « pas encore dû » —
   or si le suite l'atteint pendant la **première minute d'un bloc de 5**, le
   prochain déclenchement après `now - 1 min` est déjà passé et le rapport est
   légitimement dû. Reproduit en table sur 10 minutes : échoue pour 2 créneaux
   sur 10 (≈20 % des exécutions). Signalé, pas corrigé — discipline de
   périmètre. Candidat évident à un gel d'horloge (`freezegun`/injection de
   `now`) dans un lot dédié.
2. **C2 : la mécanique décrite dans le finding est inexacte** (voir §C2, point 2
   de l'auto-revue). Le correctif reste pleinement justifié, mais pour une
   raison différente de celle énoncée. Docstring corrigée en conséquence pour ne
   pas laisser d'affirmation fausse dans le code.
3. **C2 : pic mémoire résiduel ×2** au `b"".join(chunks)` (§C2, point 4).
   Identique à l'existant, borné par le plafond, non traité — la vraie réponse
   serait une réponse en flux, hors périmètre.
4. **I2 est un palliatif**, pas un correctif : le cache de répertoire central
   reste à faire si l'usage réel le justifie.
5. **C1 n'est pas couvert par des tests** — fichiers de déploiement, non
   exercés par la CI de ce dépôt. Un `docker compose up` réel reste la seule
   validation de bout en bout ; non exécuté ici.

---

## Round 2 — correctifs de la re-revue du lot de fix (C2 inerte + Minor audit_log)

Commits : `c449ea3` (C2 round 2), `e747abc` (audit_log de la purge I4).
Base : `f1339ca`.

### Finding 1 — C2 restait ouvert : le plafond de lecture valait le plafond de validation

**Diagnostic confirmé.** `_max_entry_bytes()` de `core/app/tileset3d/routes.py`
lisait `CORE_TILESET3D_MAX_ENTRY_BYTES`, exactement la variable (et le défaut,
2 Gio) déjà appliquée par `validate_tileset_zip` à l'upload. Comme zipfile borne
sa décompression sur `file_size` du répertoire central, toute archive ayant passé
la validation a par construction `file_size <= plafond` : la branche
`total > max_bytes` était **morte** en configuration par défaut. Un zip de ~65 Kio
déclarant honnêtement une entrée de 64 Mio (ratio deflate réel ~1000:1 sur des
zéros) était intégralement matérialisé en mémoire à chaque GET du proxy.

**Correctifs (`core/app/tileset3d/routes.py`)**

1. `_max_proxy_read_bytes()` (l. 56-68) remplace `_max_entry_bytes()` :
   nouvelle variable **`CORE_TILESET3D_MAX_PROXY_READ_BYTES`**, défaut
   **128 Mio (134217728)**, indépendante de `CORE_TILESET3D_MAX_ENTRY_BYTES`
   (validation, 2 Gio). Une entrée 3D Tiles réelle
   (`.b3dm`/`.i3dm`/`.pnts`/`.cmpt`/`.glb`) fait quelques Mio : le plafond de
   service n'a aucune raison d'approcher celui de validation.
2. `_read_entry_bounded()` est **supprimée** au profit d'un vrai streaming
   (`read_tileset3d_entry`, l. 182-263) : `StreamingResponse` alimentée par un
   générateur qui relaie les tranches de `zf.open(path)` telles quelles. Plus de
   `list[bytes]` + `b"".join()` : le pic mémoire ne dépend plus de la taille de
   l'entrée (résiduel « ~2x » signalé par l'auto-revue du round 1, fermé).
3. Docstring/commentaires réécrits (l. 184-188, 194-206, 222-225, 246-249) :
   plus aucun chiffre « ~2,2 Mio » (mesure obtenue sous un plafond artificiellement
   abaissé en test, donc trompeuse). Ce qui est conservé et exact : zipfile
   tronque la décompression à `file_size`, donc un répertoire central mensonger
   produit un `BadZipFile` (contrôle CRC), pas une bombe mémoire ; la vraie
   défense est un plafond de lecture **indépendant et plus bas** que celui de
   validation.
4. `.env.example` (l. 72-79) : `CORE_TILESET3D_MAX_ENTRY_BYTES` ne prétend plus
   plafonner la lecture ; `CORE_TILESET3D_MAX_PROXY_READ_BYTES` documenté juste
   en dessous (défaut 128 Mio, plafond de service par requête, distinct et bien
   plus bas que celui de validation).

**Gestion de « l'erreur après le début du flux »** — tout ce qui peut encore
devenir un statut HTTP est fait **avant** de construire la `StreamingResponse` :

| Cas | Détection | Statut |
|---|---|---|
| Entrée absente | `zf.getinfo(path)` → `KeyError`, synchrone | 404 propre |
| Archive corrompue / chiffrée / méthode non supportée | constructeur `ZipFile`, `getinfo`/`open`, **et la première tranche lue synchronement** (`entry.read(_READ_CHUNK_BYTES)`, l. 226) — c'est elle qui déclenche la décompression et donc le contrôle CRC d'une entrée courte | 422 propre |
| Dépassement du plafond | `info.file_size > max_bytes` **avant toute décompression** (l. 216) : `file_size` est le plafond que zipfile s'applique à lui-même, donc il majore l'octet-compte réel | 413 propre |

Le garde cumulatif en cours de flux (l. 245-254) est conservé en **filet de
sécurité** : il est inatteignable tant que zipfile respecte `file_size`, et s'il
se déclenchait, les en-têtes seraient partis — il journalise en `logger.error`
puis lève, ce qui coupe la connexion. **Limite résiduelle assumée**, et elle ne
concerne PAS les trois cas ci-dessus : une entrée dont le CRC n'échoue qu'après
la première tranche (> 1 Mio décompressé) coupera le flux au lieu de rendre un
422. Inhérent à tout streaming ; le cas testé (M1) est détecté synchronement.

Ressources : `entry`/`zf` sont fermés sur chacun des chemins d'erreur
synchrones et dans le `finally` du générateur (donc aussi sur déconnexion
client, `GeneratorExit`).

**Preuves**

Mesure `tracemalloc` hors test, entrée de 64 Mio dans un zip de 65 487 octets :

```
old zf.read() peak MiB: 141.5
streaming peak MiB: 4.2
```

Le pic du flux est indépendant de la taille de l'entrée (tranche + tampons du
décompresseur) ; celui de `zf.read()` est proportionnel. Aucun chiffre n'a été
reporté dans les commentaires du code.

Tests (`core/tests/test_tileset3d_routes.py`) :

- `test_read_tileset3d_entry_413_when_the_decompressed_entry_exceeds_the_proxy_cap`
  (adapté) — surcharge **`CORE_TILESET3D_MAX_PROXY_READ_BYTES`** et
  `delenv("CORE_TILESET3D_MAX_ENTRY_BYTES")` : le défaut de validation (2 Gio)
  reste actif et laisserait passer l'entrée de 8 Mio. C'est bien le plafond de
  service qui rend le 413 — la branche n'est plus morte.
- `test_read_tileset3d_entry_413_is_independent_of_the_validation_cap` (nouveau) —
  plafond de validation explicitement à 2 Gio, plafond de service à 1 Kio : 413.
- `test_read_tileset3d_entry_streams_a_multi_chunk_entry_byte_for_byte` (nouveau) —
  `_READ_CHUNK_BYTES` réduit à 4096, entrée de 102 400 octets (25 tranches) :
  `r.content` est identique octet pour octet. Couvre la non-régression du
  chemin nominal après la réécriture en flux.
- `test_read_tileset3d_entry_404_for_missing_entry` — assertion ajoutée sur le
  corps (`detail == "entry not found"`) : preuve que c'est bien une réponse
  d'erreur complète, pas un 200 tronqué.
- `test_read_tileset3d_entry_422_for_a_corrupt_entry` (M1, inchangé) — toujours
  vert sous la nouvelle structure.

**Non couvert par un test** (honnêteté) : la borne mémoire elle-même. `TestClient`
bufferise la réponse côté client, donc aucune assertion runtime ne prouve « jamais
plus d'une tranche en mémoire dans le processus » ; cette propriété repose sur la
lecture du code (aucune accumulation dans `_iter_entry`, Starlette itère le
générateur au fil de l'eau) et sur la mesure `tracemalloc` ci-dessus.

### Finding 2 — la purge I4 n'écrivait aucune entrée `audit_log`

`core/app/tileset3d/jobs.py` (l. 89-110) : la branche
`except Tileset3DValidationError` supprime le zip rejeté sans rien auditer,
contrairement à la règle non négociable de CLAUDE.md et au précédent SP-14o
(purge du mode `replace`, corrigée par l'ajout de `write_audit`).

Correctif : drapeau `purged`, positionné **uniquement** quand
`delete_object` retourne sans lever ; `write_audit(actor_kind="agent",
actor_id=None, action="tileset3d.purge", object_type="tileset3d_upload",
object_id=job_id, payload={"sourceKey", "reason"})` dans la **même** session
(donc la même transaction) que `mark_error`. Convention `agent`/`None` reprise
de `app/reports/jobs.py::_audit_trigger_failure`. Un échec de purge continue de
ne jamais masquer l'erreur de validation.

Tests (`core/tests/test_tileset3d_jobs.py`) :

- `test_finalize_task_marks_error_on_invalid_zip_without_creating_an_item`
  (étendu) — vérifie la ligne `AuditLog` (`select(AuditLog).where(action ==
  "tileset3d.purge")`, patron de `tests/test_analytics_sql_routes.py`) :
  `tenant_id`, `object_type`, `object_id == job_id`, `actor_kind == "agent"`,
  `actor_id is None`, `payload["sourceKey"]`, `payload["reason"]`.
- `test_finalize_task_does_not_audit_a_purge_that_failed` (nouveau) — sous-classe
  locale du `_FakeS3Client` existant dont `delete_object` lève un `ClientError`
  (aucune infrastructure nouvelle) : le job finit bien en `error` avec son
  message de validation, et **aucune** ligne `tileset3d.purge` n'est écrite.

### Vérifications

```
cd core && uv run pytest -q
1440 passed, 145 skipped in 97.89s
```

(1437 au commit de base `f1339ca` + 3 nouveaux tests.)

```
cd core && uv run lint-imports        → Contracts: 1 kept, 0 broken.
cd core && uv run python scripts/export_openapi.py <tmp> ; diff openapi.json <tmp>
                                      → identique (aucune régénération requise,
                                        aucune signature de route modifiée)
```

**Flakiness observée, sans rapport avec ce lot** : sur l'une des trois exécutions
complètes, `tests/test_report_repository.py::test_list_due_reports_respects_cron_cadence_against_last_run`
a échoué sur `procrastinate.exceptions.AppNotOpen` (pool psycopg jamais ouvert).
Le test passe seul et est repassé sur les exécutions suivantes ; il ne touche
aucun code modifié ici (aucun `defer`, aucun procrastinate dans son corps), et le
diff de ce round ne touche pas procrastinate. À surveiller comme instabilité
pré-existante du parc de tests, pas comme régression.

## Round 3 (post-merge, troisième re-revue) — 1 Important + 2 Minor

Trois derniers correctifs avant merge sur `read_tileset3d_entry` (proxy de
lecture en `StreamingResponse`) et son environnement de déploiement.

### Finding 1 (Important) — corruption en cours de flux tronque au lieu
d'échouer proprement

`core/app/tileset3d/routes.py`, construction de la `StreamingResponse` en fin
de `read_tileset3d_entry` (juste avant, ligne où `info.file_size` est déjà
connu et validé contre le plafond de service `max_bytes`) : ajout d'un
`Content-Length: str(info.file_size)` fusionné aux en-têtes existants
(`Cache-Control` conservé). Ne supprime pas la troncature elle-même (toujours
inhérente au streaming passé le point de non-retour — les en-têtes sont déjà
partis quand une corruption CRC surgit en cours de lecture d'une entrée >
`_READ_CHUNK_BYTES`), mais transforme un corps tronqué en short-read détectable
sans ambiguïté par tout client/proxy HTTP respectant `Content-Length`, au lieu
d'une réponse 200 incomplète acceptée silencieusement.

Test ajouté : `test_read_tileset3d_entry_sets_content_length_to_the_entry_size`
(`core/tests/test_tileset3d_routes.py`) — vérifie que `content-length` vaut la
taille réelle de l'entrée sur le chemin heureux (`.b3dm` de 16 octets), et
qu'il correspond à `len(r.content)`.

### Finding 2 (Minor) — `object_type` d'audit incohérent pour le même job

`core/app/tileset3d/routes.py` utilise `object_type="tileset3d_job"` dans ses
deux `write_audit(...)` (création du job, complétion de l'upload).
`core/app/tileset3d/jobs.py`, dans la branche `except Tileset3DValidationError`
(purge du zip rejeté), utilisait `object_type="tileset3d_upload"` pour le même
`job_id` — incohérence qui aurait fait rater l'événement de purge à toute
requête d'audit trail filtrant par `object_type="tileset3d_job"`. Changé en
`"tileset3d_job"`, `object_id=job_id` inchangé. Test mis à jour :
`core/tests/test_tileset3d_jobs.py`, assertion sur `log.object_type`.

### Finding 3 (Minor) — variables de tuning documentées mais jamais câblées
dans `docker-compose.yml`

`.env.example` documente `CORE_TILESET3D_MAX_ENTRIES` (défaut 20000),
`CORE_TILESET3D_MAX_TOTAL_BYTES` (défaut 21474836480), `CORE_TILESET3D_MAX_ENTRY_BYTES`
(défaut 2147483648) — lues uniquement dans `app/tileset3d/jobs.py`
(`finalize_tileset3d_task`, qui ne tourne que dans le process `worker`) — et
`CORE_TILESET3D_MAX_PROXY_READ_BYTES` (défaut 134217728) — lue uniquement dans
`app/tileset3d/routes.py` (`read_tileset3d_entry`, qui ne tourne que dans le
process `core`). Aucune des quatre n'était transmise dans le compose : les
définir dans `.env` n'avait donc aucun effet sur la stack packagée. Ajouté au
service `core` : `CORE_TILESET3D_MAX_PROXY_READ_BYTES` seule (le plafond de
lecture s'exécute côté API). Ajouté au service `worker` : les trois plafonds de
validation seuls (ils ne s'exécutent que dans la tâche procrastinate). Chaque
variable n'est câblée que sur le(s) service(s) qui exécutent réellement le code
qui la lit — pas de câblage par précaution sur les deux services.

### Vérifications

```
cd core && uv run pytest -q tests/test_tileset3d_routes.py tests/test_tileset3d_jobs.py
21 passed in 5.03s

cd core && uv run pytest -q
1441 passed, 145 skipped in 100.08s   (full green, second run after the
                                        known-flaky cron-cadence test failed
                                        once on the first full run and passed
                                        alone and on rerun — same pre-existing
                                        flake noted in Round 2 above, unrelated
                                        to this diff)

python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"
OK
```
