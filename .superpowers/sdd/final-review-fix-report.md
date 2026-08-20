# SP-20 — rapport de la passe de correction (revue finale de branche)

8 constats corrigés (C1, C2, C3, I1, I2, M1, M2, M6) en une seule passe,
un seul commit. M3/M4/M5 délibérément non touchés (suivis non bloquants
documentés ailleurs) — aucun code adjacent modifié.

Toutes les corrections ont été appliquées en TDD : le test est écrit
d'abord, exécuté RED (sortie réelle reproduite ci-dessous), puis la
correction est appliquée et le test repasse GREEN.

---

## C1 — schéma d'outils envoyé au LLM en forme MCP au lieu de la forme OpenAI

**Changement :** `core/app/copilot/llm_provider.py:53-71` —
`OpenAICompatibleLLMProvider.chat` mappe désormais explicitement
`{name, description, inputSchema}` (forme MCP/shell) vers
`{name, description, parameters}` (forme chat-completions), avec des
valeurs de repli (`""` / `{"type": "object", "properties": {}}`) pour les
outils clients qui ne déclarent ni description ni schéma.

**Tests ajoutés** (`core/tests/test_copilot_llm_provider.py`) :
- `test_openai_compatible_provider_sends_tools_in_openai_shape` — capture
  le payload réellement posté et assert
  `tools[0]["function"]["parameters"] == inputSchema` **et** l'absence
  totale de la chaîne `inputSchema` dans le payload sérialisé.
- `test_openai_compatible_provider_tolerates_tools_without_description_or_schema`
  — un outil réduit à `{"name": ...}` produit quand même les trois champs.

**RED :**
```
FAILED tests/test_copilot_llm_provider.py::test_openai_compatible_provider_sends_tools_in_openai_shape
FAILED tests/test_copilot_llm_provider.py::test_openai_compatible_provider_tolerates_tools_without_description_or_schema
2 failed, 5 passed in 0.36s
```
(la 2e : `assert {'name': 'addWidget'} == {...}` — `Right contains 2 more
items: {'description': '', 'parameters': {...}}`, l'outil passait bien tel
quel.)

**GREEN :** `7 passed in 0.16s`.

---

## C2 — `tool_calls[].function.arguments` réinjecté en dict Python

**Changement :** `core/app/copilot/routes.py:92` — `json.dumps(tc.arguments)`
au lieu de `tc.arguments` (+ `import json`, ligne 3).

**Test ajouté** (`core/tests/test_copilot_routes.py`) :
`test_replayed_tool_call_arguments_are_a_json_string_not_a_dict`. Le
brief notait à raison que `FakeLLMProvider` n'expose pas les `messages`
reçus ; j'ai donc ajouté à ce fichier une classe
`CapturingLLMProvider` (fake conforme au Protocol `LLMProvider`) qui
enregistre les `messages` de chaque appel. Point non anticipé par le
brief, vérifié empiriquement : `_run_turn` **mute la même liste**
`messages` d'un tour à l'autre, donc capturer la référence donnerait
l'état final ; la capture fait un `copy.deepcopy`. Le test scripte un
tour outil (`list_items`, allowlisté, donc la boucle continue) puis une
réponse texte, et assert sur le **2e** appel que
`arguments` est une `str` et que `json.loads` la ramène à `{"limit": 5}`.

**RED :**
```
>       assert isinstance(arguments, str)
E       AssertionError: assert False
E        +  where False = isinstance({'limit': 5}, str)
```

**GREEN :** inclus dans les `16 passed` des deux fichiers copilote.

---

## C3 (+ I2) — jeton MCP en mode OIDC réel

**Changement :** `shell/src/builder/copilot/useMcpToken.ts` entièrement
réécrit selon le brief — POST direct au endpoint de token
(`grant_type=refresh_token`, scope `geostudio-mcp-audience`) au lieu de
`oidc.signinSilent({ scope })`, et cache en mémoire (`useRef`) devenu
**expiry-aware** (`expiresAt = now + expires_in - 30s`), ce qui corrige
structurellement **I2** (mise en cache indéfinie, aucune reprise après
expiration) sans changement de code séparé. La branche mock est
inchangée. Trois messages d'erreur distincts, tous préfixés
« Impossible d'obtenir un jeton MCP ».

**Tests :** `shell/src/builder/copilot/useMcpTokenOidc.test.tsx`
entièrement réécrit (l'ancien mockait `signinSilent`, qui n'existe plus
dans ce chemin) — 6 tests couvrant les 5 points demandés :
1. forme de la requête (URL dérivée de `settings.authority`, POST,
   `application/x-www-form-urlencoded`, `grant_type`/`refresh_token`/
   `client_id`/`scope` dans le corps) + jeton retourné ;
2. cache (2 appels → 1 seul `fetch`) ;
3. re-fetch à l'approche de l'expiration — **faux timers**, la convention
   déjà en place dans ce dépôt (`useUndoableDraft.test.tsx`,
   `AnalyticsContext.test.tsx`, …) : `expires_in: 60`, encore servi du
   cache à +20s, re-fetché à +40s (buffer de 30s) ;
4. absence de refresh token → rejet + aucun `fetch` ;
5. `ok: false` → rejet ; plus un 6e : réponse sans `access_token`.

**RED :** vérifié en restaurant temporairement l'ancienne implémentation
(`git show HEAD:…`) et en relançant le nouveau fichier de test :
`Test Files 1 failed (1) / Tests 6 failed (6)`, avec notamment
`AssertionError: expected [Function] to throw error matching
/Impossible d'obtenir un jeton MCP/ but got 'oidc.signinSilent is not a
function'`. Implémentation restaurée immédiatement après.

**GREEN :** `useMcpTokenOidc.test.tsx` (6) + `useMcpToken.test.tsx`
(mock-mode, inchangé, 1) → `7 passed`.

---

## I1 — appel LLM synchrone sur la boucle d'événements

**Changement :** `core/app/copilot/routes.py:81` —
`await anyio.to_thread.run_sync(provider.chat, messages, all_tools)`
(+ `import anyio`, ligne 5).

**Test ajouté** (`core/tests/test_copilot_routes.py`) :
`test_synchronous_provider_call_does_not_block_the_event_loop`. Contrairement
à ce que le brief laissait comme repli acceptable (« se contenter des
tests existants »), le test de concurrence réel s'est avéré **bon marché
et concluant** : le plugin `anyio` de pytest est déjà utilisé par
`tests/test_copilot_mcp_loopback.py`, donc j'ai extrait la construction de
l'app de la fixture `client` dans un helper `_make_copilot_app` (fixture
`client` inchangée fonctionnellement) et lancé deux requêtes concurrentes
via `httpx.AsyncClient` + `ASGITransport` contre un provider dont le
`chat` fait `time.sleep(0.4)`, en assertant que le total reste sous
`0.4 × 1.8`.

Un ajustement a été nécessaire, sans rapport avec le bug mesuré : la base
SQLite en mémoire est partagée et deux requêtes vraiment concurrentes se
disputent la création du tenant par défaut
(`sqlalchemy.exc.InvalidRequestError: Could not refresh instance
'<Tenant …>'`). Une requête d'échauffement séquentielle précède donc les
deux requêtes chronométrées, commentée comme telle.

**RED (mesure réelle du blocage) :**
```
E       AssertionError: les deux tours se sont sérialisés (0.87s pour 2×0.4s)
E       assert 0.8682945760010625 < (0.4 * 1.8)
```

**GREEN :** après le passage en `anyio.to_thread.run_sync`, le test passe
(les deux tours se recouvrent).

---

## M1 — widgets d'extension sans `configSchema`

**Changement :** `shell/src/builder/extensions/registerExtensionWidget.ts:18`
— une ligne `configSchema: manifest.props,`.

**Test ajouté :** le fichier existait déjà
(`shell/src/builder/extensions/registerExtensionWidget.test.tsx`, trouvé
par recherche comme demandé — rien à créer) ; test
`exposes the manifest's props as the widget's configSchema`.

**RED :** `→ expected undefined to deeply equal [ { name: 'initial', …(3) } ]`
— `Tests 1 failed | 3 passed (4)`.

**GREEN :** `Tests 4 passed (4)`.

`ExtensionManifest["props"]` est structurellement identique à
`WidgetPropDescriptor` (mêmes 4 champs, même union `type`) : `npm run
build` (`tsc --noEmit`) passe sans cast ni assouplissement de type.

---

## M2 — `activePageId` périmé dans la fermeture de `send()`

**Changement :** `shell/src/builder/copilot/CopilotPanel.tsx:8, 38-41, 69`
— `activePageIdRef` tenu à jour par un `useEffect`, lu via `.current`
dans l'updater `setDraft` (la config, elle, était déjà correctement lue
au plus tard via le paramètre `d`).

**Test ajouté** (`shell/src/builder/copilot/CopilotPanel.test.tsx`) :
`applies clientOps against the page active when the reply lands, not the
one active at send time`. `./applyClientOp` est mocké en conservant
l'implémentation réelle (`importOriginal` + `vi.fn(actual.applyClientOp)`)
pour pouvoir inspecter le 3e argument reçu sans changer le comportement
des autres tests du fichier. Le test envoie un message avec une promesse
`copilotTurn` contrôlée à la main, re-rend le composant avec
`activePageId="page-2"` pendant que le tour est en vol, résout la
promesse, puis invoque l'updater capturé et assert que
`applyClientOp` a reçu `"page-2"`.

**RED :** `→ expected 'page-1' to be 'page-2' // Object.is equality`.

**GREEN :** `src/builder/copilot/` → `Test Files 5 passed / Tests 21 passed`.

---

## M6 — config sérialisée en `repr()` Python dans le prompt système

**Changement :** `core/app/copilot/routes.py:55` —
`json.dumps(current_config, ensure_ascii=False)`.

**Test ajouté** (`core/tests/test_copilot_routes.py`) :
`test_system_message_serialises_the_config_as_real_json` — via
`CapturingLLMProvider`, découpe le contenu du message système après
« Configuration actuelle (JSON) : », assert que `json.loads` le reparse
exactement en la config envoyée (config de test contenant volontairement
`True`, `None` et des accents), assert l'absence de `'kind': 'app'`
(marqueur d'un `repr()`) et la présence littérale de « Café & thé »
(preuve d'`ensure_ascii=False`).

**RED :**
```
>       assert json.loads(payload) == current_config
E           json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```

**GREEN :** inclus dans les `16 passed`.

---

## Vérification finale (les 5 commandes du brief)

| # | Commande | Résultat |
|---|----------|----------|
| 1 | `cd core && uv run pytest -q` | **PASS** — `1588 passed, 153 skipped in 144.27s` |
| 2 | `cd core && uv run lint-imports` | **PASS** — `layered architecture KEPT` / `Contracts: 1 kept, 0 broken.` |
| 3 | `cd shell && npm run build` | **PASS** — `tsc --noEmit` sans erreur, `✓ built in 18.20s` (seuls les avertissements de taille de chunk préexistants) |
| 4 | `cd shell && npm run test` | **PASS** — `Test Files 152 passed (152)` / `Tests 1237 passed (1237)` |
| 5 | `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/copilot.spec.ts` | **PASS** — `2 passed (34.9s)` |

---

## Décisions de jugement

1. **`anyio` laissé en dépendance transitive** (non ajouté à
   `core/pyproject.toml`). Vérifié avant de m'y appuyer :
   `uv run python -c "import anyio, anyio.to_thread"` fonctionne, et
   `anyio.run(lambda: anyio.to_thread.run_sync(f, 1, 2))` renvoie bien
   `(1, 2)`. Ce n'est pas une dépendance transitive fragile : Starlette
   en dépend inconditionnellement et l'utilise elle-même pour chaque
   dépendance/route synchrone — la trace du test RED montre littéralement
   `anyio/_backends/_asyncio.py … run_sync_in_worker_thread` dans le
   chemin FastAPI existant. Une déclaration explicite reste possible si
   la politique du dépôt l'exige ; je ne l'ai pas faite pour ne pas
   élargir le périmètre de cette passe.
2. **`CapturingLLMProvider` avec `copy.deepcopy`** — voir C2 : sans copie
   profonde, la mutation en place de `messages` par `_run_turn` rendrait
   l'assertion sur le 1er/2e appel trompeuse.
3. **Test de concurrence réel écrit pour I1** plutôt que le repli
   « s'appuyer sur la suite existante » autorisé par le brief : il tenait
   en une vingtaine de lignes grâce au plugin anyio déjà en place, et il
   mesure le défaut (0.87s de sérialisation) au lieu de le décrire.
   Requête d'échauffement ajoutée pour neutraliser une course sur la
   création du tenant par défaut propre au SQLite en mémoire.
4. **Aucun fichier de test créé de zéro** : `registerExtensionWidget.test.tsx`
   existait déjà (M1), `useMcpTokenOidc.test.tsx` a été réécrit sur place
   (C3), les autres tests étendent des fichiers existants.
5. **`useMcpToken.test.tsx` (mode mock) laissé strictement inchangé**,
   comme prévu par le brief, et re-exécuté : vert.
6. Le dépôt contenait des modifications non liées à cette passe
   (`.superpowers/sdd/task-*`, `deploy/postgis/*`,
   `docs/vision/2026-08-20-*`) : **non stagées, non commitées** — seuls
   les 8 fichiers de cette passe sont dans le commit.
