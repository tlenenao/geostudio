# SP-20 — Copilote IA embarqué dans le builder — Progress Ledger

Plan: docs/superpowers/plans/2026-08-16-sp20-copilote-embarque.md
Spec: docs/superpowers/specs/2026-08-05-copilote-embarque-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note de reprise

Trouvé au démarrage : ledger de SP-19 (4/4 tâches + revue finale, clos,
déjà committé). Repartant de zéro pour SP-20.

Avant dispatch : committé (8f45d95) la correction de spec (CopilotPanel
reçoit undo/redo en props depuis AppBuilderPage, pas de UndoContext) + le
fichier de plan, présents non commités au démarrage de session.

## Pre-flight plan review

13 tâches, code complet à chaque étape. Le seul point notable — Task 5's
test file contient un placeholder intentionnellement signalé puis corrigé
inline dans le texte du plan lui-même (`test_allowlisted_mcp_tool_call_is_executed_via_loopback`)
— pas une contradiction, déjà résolu par le plan ; l'implémenteur doit
écrire la version corrigée, pas le premier brouillon. Aucune autre
contradiction interne trouvée.

## Tâches
Task 1: complete (commit 1a52d45, review clean — 0 Critical/Important, 2
⚠️ trust-gap résolus indépendamment par le contrôleur : commit body relu
au complet via `git log`, et vérification du token MCP reproduite en
direct contre le vrai conteneur Keycloak toujours up — `aud: ['geostudio-mcp',
'geostudio-core']`, confirmé). `deploy/keycloak/geostudio-realm.json` :
`geostudio-mcp-audience` ajouté à `optionalClientScopes` de
`geostudio-shell`, édition minimale (1 ligne), rien d'autre touché dans
le realm.
Task 2: complete (commit f572c62, review clean — 0 Critical/Important/Minor).
`is_copilot_enabled()` (`core/app/auth/dependency.py`) + `copilotEnabled`
sur `GET /instance` (`core/app/instance/routes.py`), 4 tests neufs +
3 fichiers de tests existants corrigés (assertions exact-dict, 5
occurrences au total). Transcription verbatim du brief, TDD RED→GREEN
vérifié.

Task 3: complete (commit c3da6d2, review clean — 0 Critical/Important, 2
Minor notés non bloquants : `KeyError` non gardé sur une réponse OpenAI
malformée manquant `arguments`/`id`/`name` — code exact du brief, à
durcir si besoin quand un vrai fournisseur tiers sera branché ; pas de
docstring de classe sur `OpenAICompatibleLLMProvider`, cosmétique).
`core/app/copilot/llm_provider.py` : `LLMProvider`/`LLMTurn`/`ToolCall`/
`FakeLLMProvider`/`OpenAICompatibleLLMProvider`/`get_llm_provider()`,
transcription verbatim du brief, 5/5 tests TDD RED→GREEN vérifiés.

Task 4: complete (commit 308e97d, review clean — 0 Critical/Important, 2
Minor notés). Le brief lui-même ne correspondait pas au protocole réel
`/mcp` sur 4 points — l'implémenteur a corrigé empiriquement (vérifié
indépendamment par le reviewer contre le code source réel du SDK MCP,
pas seulement pris sur parole) : (1) convention `anyio`/`@pytest.mark.anyio`
au lieu de `pytest-asyncio` (repo n'a pas cette dépendance) ; (2) garde
anti-DNS-rebinding de FastMCP (`TransportSecuritySettings`,
`allowed_hosts=["127.0.0.1:*","localhost:*",...]`) rejette
`base_url="http://test"` avec 421 — remplacé par `http://localhost:8200`
partout, y compris `CORE_BASE_URL` ; (3) un nom d'outil inconnu renvoie
`200 OK` + `isError: true`, jamais un `"error"` JSON-RPC top-level, dans
cette version du SDK — test 4 du brief réécrit en conséquence
(`test_call_tool_surfaces_unknown_tool_name_as_tool_error`), 5e test
ajouté pour couvrir le vrai cas d'échec protocolaire (421) ; (4)
`ALLOWED_MCP_TOOL_NAMES` réexporté depuis `mcp_loopback.py` (le test du
brief l'importe de là, incohérence interne du brief). 5/5 tests + 17/17
suites MCP/copilot voisines sans régression. Minor notés (non bloquants) :
`McpLoopbackSession.__init__` lève un `KeyError` brut (pas
`McpLoopbackError`) si `CORE_BASE_URL` est absent sans `http_client`
injecté — **Task 5 doit construire la session uniquement là où
`CORE_BASE_URL` est garanti défini** ; claim import-linter non
re-vérifiable depuis ce diff seul (risque faible, changement purement
additif).

Task 5: complete (commit 796b2fc, review clean — 0 Critical, 1 Important
inhérent au brief (arbitré avec Tanguy, laissé tel quel — cf. suivi
ci-dessous), 2 Minor non bloquants). `core/app/copilot/routes.py` :
`POST /copilot/turn`, boucle d'outils 6 itérations max, filtre
`ALLOWED_MCP_TOOL_NAMES`, exécution loopback réelle pour les outils
allowlistés, `clientOps` pour tout le reste (jamais exécuté côté
serveur), timeout 30s, session toujours fermée en `finally`. `main.py` :
import + exemption `read_only_guard` + montage conditionnel
(`is_copilot_enabled()`) — vérifié que `create_item`/`create_form_app`
se gardent eux-mêmes contre `is_read_only_mode()` (lu directement dans
`app/mcp/tools.py`, pas supposé). `pyproject.toml` : `app.copilot` inséré
sous `app.mcp` dans le contrat de couches. 6/6 tests neufs + suite
complète 1583 passed/153 skipped + import-linter clean + diff OpenAPI
vide (confirmés). Seule déviation : fixture de test (pas de code
production) — `CORE_BASE_URL=http://test` du brief ne résout jamais en
DNS, `McpLoopbackSession` construit avec un `http_client` réel via
`httpx.ASGITransport(app=app)` (même patron que Task 4) + `TestClient`
en context manager pour le lifespan.

**Décision explicite avec Tanguy (Task 5)** : le reviewer a trouvé qu'un
nom d'outil `clientTools` qui entrerait en collision avec
`ALLOWED_MCP_TOOL_NAMES` (ex. `create_item`/`create_form_app`, des
outils d'écriture) s'exécuterait côté serveur au lieu d'être renvoyé
comme `clientOp` — code hérité verbatim du brief, aucune garde
structurelle. Non exploitable aujourd'hui : les 5 noms d'outils client
fixés par Task 8 (`addWidget`/`updateWidgetProps`/`removeWidget`/
`addDataSource`/`setFilter`) ne recoupent jamais les 6 noms d'outils MCP.
**Laissé tel quel** (pas de fix) — à surveiller si le vocabulaire des
outils client devient un jour dynamique/extensible (ex. futurs widgets
tiers exposant leurs propres outils copilote).

Task 6: complete (commit a656a80, review clean — 0 issues). Variables
`CORE_LLM_PROVIDER`/`CORE_LLM_API_URL`/`CORE_LLM_API_KEY`/`CORE_LLM_MODEL`
transmises au service `core` de `docker-compose.yml` + documentées dans
`.env.example`, off-by-default. `docker compose config --quiet` valide.

Task 7: complete (commit a7817e5, review clean — 0 Critical/Important/Minor
sur 22 widgets vérifiés un par un par le reviewer contre le brief). Un
premier essai a été interrompu par une limite d'usage hebdomadaire avant
tout fichier écrit/commité — relancé proprement une fois la limite
réinitialisée (aucun travail perdu). `shell/src/builder/widgetPropSchema.ts`
(nouveau type `WidgetPropDescriptor`) + `registry.ts` (`configSchema?`
sur `WidgetDefinition`) + backfill des 22 définitions de widgets (19
fichiers) — aucune prop array/object (`columns`/`items`/`tabs`/`fields`/
`encodings`) n'a fuité dans un `configSchema`, les 3 schémas
intentionnellement réduits (tabs `[]`, form, pivot) sont corrects.
1215 tests + build passent.

Task 8: complete (commit 477ce89, review clean — 0 issues).
`shell/src/builder/copilot/clientTools.ts` : `buildClientToolSchemas()`
génère les 5 outils client (`addWidget`/`updateWidgetProps`/`removeWidget`/
`addDataSource`/`setFilter`) depuis `listWidgets()`/`configSchema`
(Task 7), pur/framework-free. 3/3 tests, transcription verbatim.

Task 9: complete (commit e87f01a, review clean — 0 Critical/Important, 2
Minor non bloquants notés : `getPageLayout` appelé inconditionnellement
même pour les ops qui n'en ont pas besoin, coût négligeable ; cas
`activePageId` invalide non spécifié par le brief — comportement de repli
existant (`pages.ts`, code pré-existant) vérifié sûr mais à garder en tête
pour le câblage Task 12/13). `shell/src/builder/copilot/applyClientOp.ts` :
5 ops + no-op par défaut, pur, réutilise `nextFreePosition`/
`getPageLayout`/`setPageLayout`/`getWidget` — propriété de sécurité
vérifiée réelle (filtrage par `configSchema` avant tout merge, jamais un
patch opaque, un nom de prop halluciné est silencieusement rejeté).
7/7 tests, transcription verbatim.

Task 10: complete (commit f5b5e77, review clean — 0 Critical/Important/Minor).
`isMockMode()` (`useAuth.ts`) + `shell/src/builder/copilot/useMcpToken.ts`
(second `signinSilent({scope: "...geostudio-mcp-audience"})` via
`react-oidc-context` direct, jeton en mémoire uniquement via `useRef`,
jamais `localStorage`) — code production transcrit verbatim, vérifié
ligne à ligne par le reviewer. Deux bugs réels dans le texte du brief
(pas l'implémenteur) trouvés et corrigés, confinés aux fichiers de
test : `vi.resetModules()` cassait l'isolation mock/OIDC (import statique
vs `import()` dynamique après reset — bug classique Vitest, retiré,
inutile avec un seul test dans le fichier) ; import `waitFor` mort dans
les deux fichiers de test (jamais utilisé, faisait échouer
`noUnusedLocals`). 3/3 tests + suite complète 1228/1228 + tsc clean.

Task 11: complete (commit 82c64bc, review clean — 0 issues). Types
`CopilotMessage`/`CopilotClientOp`/`CopilotTurnResult`/`CopilotToolSchema`
+ `InstanceInfo.copilotEnabled` + `ItemClient.copilotTurn()` +
implémentation dans `createItemClient` (`itemClient.ts`). Ajout hors
liste explicite du brief mais nécessaire et correctement patterné,
confirmé par le reviewer : `StaticItemClient.copilotTurn()` (rejette via
`unsupported()`, même patron que 20+ méthodes sœurs) — sinon l'élargissement
de l'interface `ItemClient` aurait cassé cette implémentation. `tsc
--noEmit`/`npm run build` clean.

Task 12: complete (commit d06b5fa, review clean — 0 Critical/Important,
1 Minor cosmétique : `lastOpsSummary` non réinitialisé au début d'un
nouvel envoi, reste affiché à côté d'une erreur d'un tour suivant en
échec — sans impact fonctionnel). `shell/src/builder/copilot/CopilotPanel.tsx` :
props exactement `{itemId, config, activePageId, setDraft}`, **aucun
bouton Annuler dédié** (contrainte de design vérifiée — réutilise le
bouton Annuler/Rétablir existant de la barre d'outils SP-19), `history`
envoyé sans dupliquer le message venant d'être tapé, `clientOps` appliqués
en un seul `setDraft`/`reduce` (une seule entrée undo par tour, vérifié),
erreur réseau affichée via `role="alert"` sans crash, opération inconnue
dégradée proprement. Câblage `AppBuilderPage.tsx` gated sur
`copilotEnabled`. 3/3 tests + suite complète 1231/1231 + build clean.

Task 13: complete (commit 5463c2a, review clean — 0 Critical/Important,
2 Minor : ⚠️ exécution Playwright non re-jouable par le reviewer
(pas de navigateur dans son environnement) — **résolu indépendamment par
le contrôleur, re-exécuté en direct : 2/2 passent (36.4s)** ; mock de
discrimination par sous-chaîne, acceptable vu le périmètre étroit du
test). `shell/e2e/copilot.spec.ts` : absence du panneau sans
`copilotEnabled`, prompt d'explication sans changement de canevas, ajout
de widget visible puis annulable via le bouton "Annuler" existant de la
barre d'outils SP-19 (pas de bouton dédié — vérifié que c'est bien le
même `setDraft`/`undo` partagé). Transcription verbatim, sélecteurs
vérifiés contre le code source réel (pas de convention inventée). Suite
E2E complète 107/107 (rapportée par l'implémenteur, note du brief "19
specs" obsolète — dérive pré-existante, sans rapport avec cette tâche).

**SP-20 : 13/13 tâches complètes, 0 Critical/Important non résolu sur
les 13 revues de tâche.**

## Revue finale de branche

Diff `8abb52e..5463c2a` (14 commits, 13 tâches). **3 Critical + 2 Important
+ 6 Minor** — invisibles à la revue par tâche (chaque tâche testait avec
`FakeLLMProvider`/mocks qui masquaient exactement les points cassés) :

- **C1** : schémas d'outils envoyés au LLM en forme MCP (`inputSchema`) au
  lieu de la forme OpenAI (`parameters`) — `llm_provider.py:54`. Tout tour
  contre un vrai fournisseur OpenAI échoue en 400/500. Présent verbatim
  dans le texte du plan (ligne 431) — un implémenteur plan-littéral ne
  pouvait pas l'éviter.
- **C2** : `tool_calls[].function.arguments` renvoyé au LLM comme un dict
  Python au lieu d'une chaîne JSON (`routes.py:82`) — casse la 2e
  itération de toute boucle utilisant un outil MCP, même après fix C1.
- **C3** : `signinSilent({scope})` (`useMcpToken.ts:34`) — `oidc-client-ts`
  ignore silencieusement `scope` sur la branche refresh-token (toujours
  empruntée en pratique, `geostudio-shell` étant un client public avec
  refresh token) : le jeton "MCP" n'a jamais l'audience `geostudio-mcp`
  en mode OIDC réel. La vérification Task 1 (curl ROPC direct) n'exerçait
  pas ce chemin de la librairie cliente — angle mort spécifique au test.
- **I1** : `provider.chat()` synchrone (`httpx.post`) appelé depuis une
  route `async def` (`routes.py:74`) — bloque toute la event loop du
  cœur pendant l'appel LLM (jusqu'à 30s × 6 itérations), et rend le
  timeout `asyncio.wait_for` inopérant contre un appel bloquant.
- **I2** : jeton MCP mis en cache indéfiniment (`useMcpToken.ts:18`),
  jamais invalidé sur expiration/401 — le copilote se bloque
  silencieusement après ~5min (durée de vie par défaut du token
  Keycloak), rechargement de page seul remède.
- **M1** : widgets d'extension (SP-8, WC tiers) n'ont jamais de
  `configSchema` (`registerExtensionWidget.ts`) — contredit le principe
  affiché de `clientTools.ts` ; `updateWidgetProps` no-ope silencieusement
  dessus tout en affichant "Widget modifié".
- **M2** : `activePageId` capturé dans la fermeture au moment de l'envoi
  (`CopilotPanel.tsx:61`) — un changement de page pendant qu'un tour est
  en vol applique les ops à la mauvaise page (même famille que le C2 de
  la revue finale SP-19, ici déclenché par l'asynchronie plutôt que
  l'undo).
- **M3** (non bloquant, documenté) : `CORE_LLM_PROVIDER` non vide mais
  invalide (valeur inconnue, `CORE_LLM_API_URL` absent) active le
  panneau et le routeur sans échec au démarrage — échoue seulement par
  message, en 500. Contraste avec `CORE_SECRETS_MASTER_KEY` (fail-fast
  au boot). Laissé non bloquant — validerait au démarrage nécessiterait
  une décision de conception plus large.
- **M4** (non bloquant, documenté) : le `signinSilent` du copilote
  remplace l'utilisateur OIDC stocké de toute la session shell —
  inoffensif sur le realm actuel (mapper d'audience `geostudio-core`
  au niveau client, pas par scope) mais fragile sur un realm différent.
  Lié à C3 ; pas re-testé séparément après le fix C3.
- **M5** (non bloquant, documenté) : `configSchema` n'a pas de validation
  par valeurs autorisées (enum) — le copilote peut écrire des valeurs
  qu'aucun `<select>` de l'UI manuelle ne peut produire (ex. `chartType`
  invalide). Hors périmètre v1 (aucune exigence d'enum dans le plan).
- **M6** : prompt système interpole la config via `repr()` Python
  (guillemets simples, `True`/`False`/`None`) tout en affirmant "JSON"
  (`routes.py:53`) — trompe le LLM sur le format réel.

**Vérifié propre** (aucune trouvaille) : prédiction de diff OpenAPI vide
confirmée, câblage `docker-compose.yml`/`.env.example` complet et correct
(4/4 variables, noms exacts), off-by-default de bout en bout, garde
lecture-seule (exemption `/copilot/turn` sûre car `create_item`/
`create_form_app` s'auto-gardent), intégrité de l'allowlist (6 outils
réels, jamais `save_app_config`/`set_sharing`), intégration undo-stack
(un seul `setDraft`/tour, pas de régression classe SP-19-C2 sur
`activePageId` lui-même), contrat import-linter.

**Décision de correction** : fix C1/C2/C3/I1/I2 (bloquants) + M1/M2/M6
(gains élevés, coût faible) en une seule passe. M3/M4/M5 laissés non
bloquants, documentés ci-dessus (matches convention CLAUDE.md des SP
précédents).

**Suivi non bloquant découvert (hors périmètre de cette tâche, laissé non
commité)** : Postgres 16 packagé par `deploy/postgis/Dockerfile` ne
démarrait pas dans la stack docker compose par défaut (config
`wal2json`/authentification incompatible) — l'implémenteur a dû créer
`deploy/postgis/pg_hba.conf` + une modification du Dockerfile pour faire
tourner un vrai Keycloak et vérifier ce Task. Ces deux fichiers restent
non commités (scope creep hors Task 1, pas dans les Files: de la
tâche) — présents dans le répertoire de travail pour référence future,
mais pas nécessaires aux tâches suivantes du plan (aucune autre tâche
SP-20 ne requiert un vrai conteneur docker). À signaler dans le suivi
CLAUDE.md si l'utilisateur veut corriger la stack par défaut séparément.

## Clôture (2026-08-20, session « termine sp20 »)

État trouvé : 13/13 tâches + revue finale de branche + passe de fix
(`d03bee4`) + redesign C3 (`f583249`), mais **aucune re-revue** de cette
passe enregistrée, et CLAUDE.md non backfillé.

### Re-revue de la passe de fix (`5463c2a..f583249`)

**0 Critical/Important.** Les 8 fixes sont réels et couverts par des tests
qui ont des dents (mutation vérifiée sur `forceIframeAuth` par
l'implémenteur, sur la garde d'identité par le contrôleur). Vérifié :
`clientTools.ts` émet bien `inputSchema`, donc le mapping C1 couvre aussi
les outils client ; `tools/list` MCP renvoie bien cette même forme ;
`manifest.props` a bien la forme de `configSchema` (M1) ; aucun reste de
la tentative n°2 (appel direct au endpoint de token) dans le code.
Minor relevés : `anyio.to_thread.run_sync` n'abandonne pas le thread à
l'annulation, donc `asyncio.wait_for` ne coupe pas l'appel LLM en vol
(borné par le timeout httpx de 30 s) — le blocage de la boucle
d'événements, lui, est bien fermé ; `anyio` non déclaré dans
`pyproject.toml` (transitif Starlette).

### Vérifications (état trouvé, avant toute modification)

| Commande | Résultat |
|---|---|
| `core: uv run pytest -q` | 1588 passed, 153 skipped |
| `core: uv run lint-imports` | layered architecture KEPT |
| `shell: npm run build` | tsc + vite OK |
| `shell: npm run test` | 152 fichiers / 1235 tests |
| `shell: playwright test` (suite complète) | 107 passed |
| job CI `api-types-drift` reproduit à l'identique | **aucune dérive** |

### Croisement avec la revue de projet 2026-08-20

`docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (session
parallèle, audit sur `a7817e5`) portait 3 Critique + 2 Important sur le
copilote, avec la recommandation explicite de ne pas merger avant.
Chacun re-vérifié contre le code réel avant d'agir (C2 déjà fermé par le
fix I1 de la revue de branche). Périmètre de correction arbitré avec
Tanguy : **C1 + C3 + I6 + I7**.

- `2773fa4` — C1, confused deputy : `app/copilot/mcp_token.py`,
  `sub` du jeton MCP == `user.oidc_sub` exigé (403), audience MCP
  obligatoire, 401 si illisible. 6 tests unitaires sur vraie paire RSA +
  2 tests de route ; garde mutée pour prouver que le test 403 a des dents.
- `113cca8` — C3, non-déployabilité : `CORE_INTERNAL_BASE_URL`,
  `loopback_base_url()`, repli sur `CORE_BASE_URL`. Câblage vérifié **par
  valeur** sur `docker compose config` (base **et** overlay prod).
- `d13aebb` — I6 + I7 : bornes Pydantic sur tous les champs + taille
  sérialisée de `currentConfig`, `role` d'historique borné à
  `user`/`assistant`, copilote éteint en mode démo (double verrou),
  bloc de config délimité par un marqueur à nonce avec consigne
  anti-injection. Test avec config hostile tentant l'évasion du bloc,
  test garde-fou qu'un tour réaliste passe toujours.
- `ee2a1cf` — hors périmètre, trouvé en route : dé-flake d'un test
  SP-17b (`test_list_due_reports_respects_cron_cadence_against_last_run`,
  ~20 % d'échec quand la suite traverse une frontière de 5 minutes).

### Points laissés ouverts (documentés dans CLAUDE.md)

Budget de temps global au tour, rate limiting applicatif sur
`/copilot/turn`, garde d'egress sur l'appel LLM sortant (constats I4/I6 de
la revue de projet, hors périmètre arbitré) ; chemin OIDC réel de
`useMcpToken` non vérifié de bout en bout ; M3/M4/M5 de la revue de
branche ; `deploy/postgis/*` non commités et **inertes** (Postgres lit
`$PGDATA/pg_hba.conf`, prouvé par sonde sur l'image réelle).
