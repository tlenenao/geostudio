# Hébergement de tilesets 3D Tiles uploadés — Progress Ledger

Plan: docs/superpowers/plans/2026-08-13-3d-tileset-hosting.md
Spec: docs/superpowers/specs/2026-08-13-3d-tileset-hosting-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note de reprise

Cette session reprend un plan déjà entamé par une session précédente. Le
fichier `progress.md` trouvé au démarrage documentait un tout autre plan
(3D tiles3d/terrain, déjà mergé — commits jusqu'à `5ea5243`/`9de292a`),
jamais écrasé après coup : **4e occurrence** du problème de collision de
fichier scratch réutilisé déjà noté dans CLAUDE.md/ledgers précédents (SP-16b,
SP-17b/SP-16b, SP-15g/h...). Reconstruction de l'état réel à partir de
`git log` + vérification directe du code, faute de ledger fiable :

- Task 1 (modèle/migration/repository `tileset3d_jobs`) : commit `7479fd9`.
- Task 2 (`Tileset3DPayload` + `BuilderConfig.kind="tileset3d"`) : commit `50810ee`.
- Task 3 (`S3RangeFile` + validation zip) : commit `7d8d690`.
- Task 4 (routes upload + flag capacité + wiring app) : commit `a8cc08b`.
- Task 5 (finalize task — validate, create item+config) : commit `232f1ca`.

Vérifié avant reprise : `core/app/tileset3d/{models,repository,schemas,storage,routes,jobs}.py`
tous présents ; `uv run pytest -k tileset3d` → 32 passed. Reprise à Task 6
sans re-dispatch des tâches 1-5 (déjà committées, tests verts).

Les fichiers `task-1..8-brief.md`/`task-N-report.md` trouvés dans l'arbre au
démarrage appartiennent également à l'ancien plan (3D tiles/terrain) — non
liés à ce plan-ci, laissés intacts, seront écrasés au fil des `task-brief`
de ce plan au besoin.

## Tâches

Task 6: complete (commit d7c6bf6, review clean — 0 Critical/Important, 2
Minor cosmétiques (imports mi-fichier, pas de garde zip corrompu — hors
périmètre du brief). 5/5 nouveaux tests + suite complète 1432 passed/145
skipped. Ordre d'enregistrement des routes vérifié sûr par le reviewer
(catch-all `{path:path}` après `/uploads/{job_id}`, pas d'écrasement).
Task 7: complete (commit d0b39bc, review clean — 0 finding). **Écart réel
trouvé dans le texte du brief** : Step 2 prédisait "aucun diff, grep -c
tileset3d = 0" après régénération sans le flag — faux en pratique. Le
contrôleur a exécuté directement (tâche de vérification mécanique, pas de
subagent implémenteur dispatché) : `Kind` enum + schéma `Tileset3DPayload`
apparaissent bien même flag désactivé, conforme à la contrainte globale du
plan elle-même ("`kind=tileset3d` n'est PAS gated, seules les routes le
sont") — l'auteur du brief a oublié cette clause en écrivant sa
prédiction Step 2. Confirmé : 0 route `/tileset3d/...` dans le diff (le
gate des routes tient), `openapi.json`/`core-schema.d.ts` régénérés en
tandem et cohérents, `tsc --noEmit` propre. Committé sous son propre
message expliquant l'écart.
Task 8: complete (commit 09bcce1, review clean — 0 finding). Changement de
types pur (`ResourceType`, `LayerSource`, `InstanceInfo`, `ItemClient`),
échec de build attendu et confirmé à l'étape 6 (4 méthodes manquantes sur
`itemClient.ts`, `getAuthToken?` bien optionnelle donc non listée) —
séquencement intentionnel du plan, corrigé par Task 9.
Task 9: complete (commit ccc5413, review clean — 0 finding). 2 écarts
auto-signalés par l'implémenteur, tous deux vérifiés fidèles par le
reviewer (pas des findings) : (1) le brief décrivait
`fetchHostedTileset3dSources` comme une fonction libre `(coreUrl,
getToken, q)` — en réalité les 3 helpers sœurs (`fetchMartinSources`
etc.) sont des closures internes à `createItemClient`, implémenté en
closure pour rester fidèle au pattern réel du fichier ; (2) l'ajout d'une
4e source à `listLayerSources` cassait le test préexistant "throws when
both services fail" (handler MSW par défaut `/items` matchait aussi le
nouvel appel) — corrigé en ajoutant des handlers d'échec explicites aux 4
endpoints, test renommé "all services fail", assertion réelle préservée
(vérifié par le reviewer, pas affaibli en tautologie). URL du proxy
authentifié (`${coreUrl}/tileset3d/{itemId}/tileset.json`, jamais une URL
S3 brute) vérifiée par le reviewer contre `routes.py` réel. Suite complète
139 fichiers/1151 tests + build vert.
Task 10: complete (commit 45b1d89, review clean — 0 finding). Vrai bug
latent corrigé : `toMapLayer` n'avait pas de branche `tiles3d`, une source
hébergée serait tombée silencieusement dans le catch-all `feature`. 11/11
tests passants.
Task 11: complete (commit c0a06c5 + fix a33717a, re-revue clean). **1
Critical réel trouvé et corrigé** — plan-mandated (code du brief suivi
verbatim par l'implémenteur) : le gate d'attache du bearer token
(`layer.url.includes("/tileset3d/")`) était un simple test de
sous-chaîne — une URL externe forgée du type
`https://attacker.example/x/tileset3d/y/tileset.json` matchait quand
même et recevait le token de session en cross-origin (fuite
d'identifiants vers un hôte tiers, contraire à la contrainte globale du
plan). Corrigé par comparaison d'origine réelle
(`new URL(url).origin === new URL(coreUrl).origin && pathname.startsWith`),
`coreUrl` exposé via un nouveau `ItemClient.getCoreUrl?()` (miroir de
`getAuthToken?()`), fail-closed sur URL malformée/coreUrl absent, câblé
aux mêmes 4 sites d'appel réels. Non demandé au préalable de décision
utilisateur car alignement direct avec la contrainte globale du plan
elle-même (pas une décision produit), sur le modèle des corrections
autonomes déjà pratiquées sur ce dépôt pour des bugs factuels du texte
littéral du brief. Test de régression réel ajouté (URL sous-chaîne sur
mauvaise origine), 186/186 + suite complète 1157 tests + build propre,
re-revue confirme aucun chemin résiduel de fuite.
Task 12: complete (commit 29b1b03 + fix 507514a, re-revue clean). Spec
conforme, aucune régression du pattern de fuite Task 11 (le PUT vers
`uploadUrl` présigné n'attache jamais d'en-tête `Authorization` — design
plus robuste qu'une vérification d'origine). **1 Important réel trouvé,
plan-mandated** (code verbatim du brief) : fermer le dialogue (Annuler/
Échap/clic sur le fond) pendant un upload/poll en cours n'annulait rien —
un 2e upload démarré ensuite pouvait voir son état écrasé silencieusement
par la résolution tardive du 1er (fermeture surprise, ou erreur mal
attribuée). **Décision de Tanguy** : fix minimal — désactiver Annuler et
bloquer Échap/backdrop tant que `busy` (pas d'`AbortController`).
`Dialog` partagé non modifié (guard dans `Tileset3DUploadButton` via
`requestClose`), fermeture normale hors busy confirmée intacte. Nouveau
test prouve les 3 chemins de fermeture bloqués individuellement + levée
du garde une fois la requête relâchée. 140 fichiers/1160 tests + build
propres, re-revue confirme les 3 chemins réellement fermés (bouton
disabled natif, Échap et backdrop tous deux funnelés par `requestClose`).
Task 13: complete (commits 0c78d90 + e177f16, review clean — 0
Critical/Important, 1 Minor). Spec E2E complète vérifiée contre le code
source réel (upload → fermeture dialogue → création carte →
LayerPicker → clic source hébergée → requête proxy `tileset.json` 200).
2 sélecteurs `exact: true` légitimes (ambiguïté réelle "Nouveau"/
"Nouveau tileset 3D", "Importer"/"Importer un fichier", même convention
que `ingestion.spec.ts`). **Hors périmètre justifié** : régression réelle
préexistante trouvée dans `harvest-wms.spec.ts` — `fetchHostedTileset3dSources`
(Task 9) s'exécute sans condition à chaque montage de `LayerPicker`, son
mock `/items*` non filtré par `type` renvoyait son item WMS en réponse à
`type=tileset3d`, cassant l'assertion stricte Playwright dès qu'un test
avec `tileset3dEnabled: true` existe (ce plan est le premier). Corrigé en
filtrant le mock local de ce spec par `type`, aucune assertion existante
affaiblie. Suite E2E complète 99/99 (98/99 avant fix). 1 Minor documenté :
même fragilité latente dans `mocks.ts`'s défaut `/items*` (non filtré par
`type`) pour tout futur spec — inoffensif aujourd'hui, pas dans le
périmètre de cette tâche (fichier partagé), noté comme suivi non
bloquant.

## Toutes les tâches (1-13) closes.

## Revue finale de branche (089e4ca → e177f16, 16 commits)

Reviewer opus : 3 Critical + 4 Important + 5 Minor. Points forts confirmés
indépendamment : couches import-linter correctes, autorisation `can()`
réelle sur le chemin de lecture (testée), les 4 sites `<MapView>` câblés
correctement (fix Task 11), aucune régression de l'invariant "jamais
d'état partiel" au finalize, OpenAPI/TS jamais oublié (fix Task 7 land
au bon endroit dans l'ordre des commits).

**C1** : la feature ne peut pas tourner dans la stack packagée — 3 trous
de câblage indépendants, invisibles tâche par tâche (aucune tâche du plan
ne touche `docker-compose.yml`/`.env.example`) : (a) aucun worker ne
consomme la queue procrastinate `tileset3d` (le worker partagé tourne
`-q ingestion,search,cdc,etl`, jamais `tileset3d` — un upload complété
reste `finalizing` pour toujours) ; (b) `CORE_TILESET3D_ENABLED` absent
de l'environnement du service `core` dans le compose (même défaut que le
C3 round 1 de SP-17a) ; (c) `.env.example` ne documente aucune des
variables tileset3d. **3e occurrence de la même classe de bug après
SP-17a et SP-17b.**
**C2** : zip-bomb — le plafond anti-zip-bomb se base sur `info.file_size`
(métadonnées du central directory, contrôlées par l'attaquant, jamais
vérifiées), mais `read_tileset3d_entry` sert via `zf.read(path)` qui
décompresse le flux réel en mémoire avant toute troncature. Reproduit
empiriquement par le reviewer : zip de 204 Ko déclarant `file_size=100`
pour une entrée de 200 Mo → pic mesuré à 458 Mo alloués par requête,
~1000:1, répétable et concurrent dans le process `core`.
**C3** : l'upload multipart navigateur ne peut pas aboutir contre un vrai
S3/MinIO — la config CORS du bucket uploads (`_CORS_CONFIGURATION`,
réutilisée d'`app.ingestion`) n'expose pas l'en-tête `ETag`
(`ExposeHeaders` absent), qui n'est pas safelisted CORS par défaut ; le
shell lit `res.headers.get("ETag")` → `null` en cross-origin → `etag: ""`
→ rejeté par la validation Pydantic `min_length=1` → 422 systématique sur
`/complete`. Invisible en test car MSW/mocks Playwright n'appliquent
jamais de vraie policy CORS.
**I1** : `kind="tileset3d"` n'a aucun validateur de payload sur les 3
routes d'écriture `/configs` (contrairement à dataset/bookmark/pipeline/
alert/report) — un utilisateur authentifié quelconque peut POST un
config `tileset3d` avec un `sourceKey` arbitraire et devenir propriétaire
de l'item résultant, contournant `can()` en pointant vers la clé S3
d'un tileset d'un autre tenant (si elle a fuité) ou en conservant un accès
après un un-partage (la clé est visible via `GET /configs/by-item/...`).
**I2** : coût par requête linéaire en nombre d'entrées (parse complet du
central directory à chaque lecture de tuile), plafond par défaut 200 000
entrées — contredit potentiellement le "coût constant" du design pour un
usage réel à dizaines de milliers de fichiers ; vérification de perf
manuelle du plan à traiter comme bloquante avant activation réelle.
**I3** : composition C1(a) × fix Task 12 — le poll infini (aucune borne
de tentatives/délai) + le garde de fermeture Task 12 (bloque Annuler/
Échap/backdrop tant que `busy`, `finalizing` inclus) produit un dialogue
définitivement infermable si le job n'atteint jamais un état terminal.
**I4** : le zip d'un upload rejeté (`Tileset3DValidationError`) n'est
jamais purgé du bucket — accumulation illimitée, n'importe quel
utilisateur authentifié peut remplir le bucket en uploadant des archives
invalides en boucle.
**5 Minor** : M1 `read_tileset3d_entry` ne catche que `KeyError` (pas
`BadZipFile`/`zlib.error`/`RuntimeError` chiffré/`NotImplementedError`
compression non supportée → 500 opaques, lié à C2) ; M2
`fetchHostedTileset3dSources` pageSize=200 sans pagination + tourne sans
condition à chaque montage `LayerPicker` + `mocks.ts` toujours non filtré
par `type` (fragilité latente identique à Task 13, non corrigée côté
fichier partagé) ; M3 `tilesetJsonPath` stocké mais jamais lu (chemin
`/tileset.json` en dur côté shell) ; M4 imports mi-fichier dans
`test_tileset3d_routes.py` (style, pas de ruff en CI) ; M5 l'assertion
finale de l'E2E Task 13 prouve la requête proxy, pas l'en-tête bearer
(déjà prouvé séparément par `MapView.test.tsx`).

**Décision** : fix batch dispatché pour C1+C2+C3+I1+I2+I3+I4 (+ M1/M2 à
faible risque, bundlés car directement liés à C2/Task 13), un seul agent
opus. M3/M4/M5 laissés en suivi non bloquant.

**Round 1 (commits 8a67f1d..f1339ca, 8 commits)** : C1/C3/I1/I2/I3/I4/M1/M2
tous corrigés et vérifiés. **Re-revue (opus)** a trouvé que le fix C2
était lui-même inerte : le plafond de lecture réutilisait la même
variable/valeur que le plafond de validation (`CORE_TILESET3D_MAX_ENTRY_BYTES`,
2 Gio) — puisque la validation garantit déjà `file_size <= max_bytes`, la
branche 413 ne pouvait jamais se déclencher pour une archive validée.
Le reviewer a reproduit empiriquement l'attaque originale sans mensonge de
métadonnées (zip honnête à ratio de compression ~1000:1 proche du plafond
deflate) : ~2 Mo de zip → ~2-4 Gio alloués par requête proxy, répétable.
Un Minor de cette même re-revue a été élevé en correction obligatoire
(non « nice to have ») : la purge du zip rejeté (I4) n'écrivait aucune
entrée `audit_log`, contraire à la règle CLAUDE.md non-négociable (précédent
SP-14o identique).

**Round 2 (commits c449ea3, e747abc)** : nouveau plafond de lecture
indépendant `CORE_TILESET3D_MAX_PROXY_READ_BYTES` (128 Mio, découplé du
plafond de validation), vérifié contre `file_size` déclaré **avant toute
décompression** ; réponse convertie en vrai `StreamingResponse` (plus de
`b"".join()` — mesuré 141,5 Mio → 4,2 Mio de pic mémoire sur une entrée de
64 Mio) ; `write_audit` ajouté sur la purge (uniquement si la suppression
S3 réussit réellement, jamais sur un échec — testé dans les deux sens).
**Re-revue (opus)**, adversariale, a vérifié empiriquement (pas seulement
lu le code) : 413 déclenché après 204 octets tirés de S3 sur un total de
8 Mio déclarés, confirmant un rejet en amont et non un plafond en cours de
flux. A trouvé 1 Important réel et nouveau (pas préexistant round 1) :
la conversion en streaming déplace la détection d'une corruption CRC
après le premier chunk (>1 Mio) après le point de non-retour HTTP — le
corps tronque silencieusement au lieu d'un 422 propre (round 1, qui
matérialisait l'entrée avant de répondre, ne l'avait pas). Repro des deux
côtés confirmée. Plus 2 Minor : `object_type` de l'audit incohérent avec
la convention du fichier (`tileset3d_upload` vs `tileset3d_job` utilisé
ailleurs) ; les 4 variables de tuning documentées dans `.env.example`
jamais câblées dans `docker-compose.yml` (le défaut applicatif reste actif
malgré tout, donc pas bloquant contrairement au C1 d'origine).

**Round 3 (commits 21624e0, 03e527d, 027526e)** : `Content-Length` ajouté
sur le `StreamingResponse` (= `info.file_size`, déjà validé) — un corps
tronqué devient un short-read HTTP sans ambiguïté pour tout client/proxy
au lieu d'être accepté silencieusement ; `object_type` unifié à
`tileset3d_job` (test mis à jour) ; les 4 variables de tuning câblées
chacune sur le seul service qui les lit réellement (`CORE_TILESET3D_MAX_PROXY_READ_BYTES`
→ `core`, les 3 autres → `worker`, valeurs par défaut vérifiées identiques
au code Python). Suite complète 1441 passed/145 skipped (deux exécutions),
`lint-imports` 1 kept/0 broken, diff inspecté directement par le
contrôleur (changements suffisamment petits et précisément spécifiés pour
ne pas justifier une 4e revue complète par agent).

**0 Critical/Important non résolu au merge, sur 3 rounds de fix.** Suivi
non bloquant restant : `test_list_due_reports_respects_cron_cadence_against_last_run`
(SP-17b, préexistant, sans rapport avec ce plan) est flaky à horloge murale
(~20% des exécutions, dépend de l'heure réelle par rapport à une cadence
cron `*/5 * * * *`) — confirmé par la re-revue round 2, non corrigé (hors
périmètre).

**Branche tileset3d hosting prête à merger.**
