# Task 4 — rapport d'exécution

## Résumé

Implémenté la configuration runtime du shell (`env-config.js`) permettant de
basculer d'hôte public sans reconstruire l'image Docker, en suivant le brief
verbatim (12 étapes, TDD).

## Ce qui a été implémenté

1. `shell/src/config.ts` réécrit : `loadConfig(env, runtimeEnv?)` — nouveau
   second paramètre optionnel, `mergeRuntimeEnv()` fusionne les valeurs
   runtime par-dessus les valeurs build-time, en ignorant tout placeholder
   `${VAR}` non substitué par `envsubst` (cas dev / variable absente au
   démarrage du conteneur). Signature rétrocompatible.
2. `shell/src/App.tsx:12` lit `window.__GEOSTUDIO_ENV__` et le passe en second
   argument à `loadConfig`.
3. `shell/env-config.template.js` : template JS avec les 6 placeholders
   `${VITE_*}` à substituer, assigné à `window.__GEOSTUDIO_ENV__`.
4. `shell/docker-entrypoint.d/40-render-runtime-config.sh` (exécutable) :
   utilise `envsubst` avec une liste explicite des 6 variables (pour ne
   jamais toucher un `${...}` accidentel ailleurs dans le template), lu au
   démarrage du conteneur nginx via le mécanisme officiel
   `/docker-entrypoint.d/*.sh` de l'image `nginx:1.27-alpine`.
5. `shell/index.html` charge `<script src="/env-config.js">` avant le bundle
   module — script non-module, ignoré silencieusement en dev où le fichier
   n'existe pas.
6. `shell/Dockerfile` copie le template et le script d'entrée dans l'image
   finale nginx (`COPY`, préserve le bit exécutable posé en Step 7).

## Tests

### TDD Evidence — RED

```
cd shell && npm test -- config.test.ts 2>&1 | tail -40
```

```
 RUN  v3.2.6 /home/lenen/projets/geostudio/shell

 ❯ src/config.test.ts (6 tests | 1 failed) 13ms
   ✓ loads a full oidc config 2ms
   ✓ throws listing all missing required vars in oidc mode 1ms
   ✓ mock mode does not require oidc vars 0ms
   × runtime env overrides build-time env when present and substituted 5ms
     → expected 'https://core.test' to be 'https://prod.example' // Object.is equality
   ✓ runtime env with un-substituted envsubst placeholder falls back to build-time 0ms
   ✓ absent runtime env behaves exactly like before (undefined second arg) 0ms

 Test Files  1 failed (1)
      Tests  1 failed | 5 passed (6)
```

Conforme à la prédiction du brief : seul le premier nouveau test échoue (sur
l'assertion, pas d'erreur de compilation), car le second argument était
jusque-là simplement ignoré par `loadConfig`.

### TDD Evidence — GREEN

```
cd shell && npm test -- config.test.ts
```

```
 ✓ src/config.test.ts (6 tests) 10ms

 Test Files  1 passed (1)
      Tests  6 passed (6)
```

### Suite complète

```
cd shell && npm test
```
→ 87 fichiers, 593 tests, tous verts (20.5s).

```
cd shell && npm run build
```
→ `tsc --noEmit && vite build` réussit. Avertissement attendu (non bloquant) :
`<script src="/env-config.js"> in "/index.html" can't be bundled without
type="module" attribute` — comportement voulu (script non-module chargé avant
le bundle). Avertissements pré-existants de taille de chunk (>500kB),
inchangés par rapport à avant cette tâche.

`dist/index.html` généré confirme le script non-module préservé tel quel
(Vite le déplace après le bundle dans le HTML, mais comme les scripts
`type="module"` sont implicitement `defer`, ils s'exécutent après le script
synchrone `env-config.js` quel que soit l'ordre dans le HTML — sémantique web
standard, donc `window.__GEOSTUDIO_ENV__` est garanti défini avant l'éval du
bundle). `dist/` supprimé après vérification (gitignored, non commité).

## Vérification Docker (Step 10)

```
docker build -t geostudio-shell-test ./shell
```
→ build réussi (image nginx:1.27-alpine + les deux `COPY` ajoutés).

Vérification directe du script (sans lancer nginx) :

```
docker run --rm -e VITE_CORE_URL=https://demo.example/api \
  -e VITE_MARTIN_URL=https://demo.example/tiles \
  -e VITE_OIDC_AUTHORITY=https://demo.example/auth/realms/geostudio \
  -e VITE_OIDC_CLIENT_ID=geostudio-shell \
  -e VITE_OIDC_REDIRECT_URI=https://demo.example/ \
  -e VITE_AUTH_MODE=oidc \
  --entrypoint sh geostudio-shell-test \
  -c "/docker-entrypoint.d/40-render-runtime-config.sh && cat /usr/share/nginx/html/env-config.js"
```

Sortie observée (identique à l'attendu du brief) :

```js
window.__GEOSTUDIO_ENV__ = {
  VITE_CORE_URL: "https://demo.example/api",
  VITE_MARTIN_URL: "https://demo.example/tiles",
  VITE_OIDC_AUTHORITY: "https://demo.example/auth/realms/geostudio",
  VITE_OIDC_CLIENT_ID: "geostudio-shell",
  VITE_OIDC_REDIRECT_URI: "https://demo.example/",
  VITE_AUTH_MODE: "oidc",
};
```

Vérification supplémentaire (au-delà du brief) : lancement réel du conteneur
avec `docker run -d` (nginx démarré normalement, entrypoint automatique) avec
un second jeu de valeurs (`demo2.example`, `geostudio-shell2`) — confirme que
le mécanisme `/docker-entrypoint.d/*.sh` officiel de l'image de base déclenche
bien le script automatiquement au démarrage réel du conteneur, pas seulement
en invocation manuelle. Sortie correcte obtenue, conteneur arrêté proprement.

Image de test supprimée : `docker rmi geostudio-shell-test`.

## Fichiers modifiés

- `/home/lenen/projets/geostudio/shell/src/config.ts` (réécrit)
- `/home/lenen/projets/geostudio/shell/src/config.test.ts` (3 tests ajoutés)
- `/home/lenen/projets/geostudio/shell/src/App.tsx` (ligne 12 étendue)
- `/home/lenen/projets/geostudio/shell/env-config.template.js` (créé)
- `/home/lenen/projets/geostudio/shell/docker-entrypoint.d/40-render-runtime-config.sh` (créé, exécutable)
- `/home/lenen/projets/geostudio/shell/index.html` (script ajouté)
- `/home/lenen/projets/geostudio/shell/Dockerfile` (2 `COPY` ajoutés)

Commit : `1b3874d` — "feat(shell): configuration runtime (env-config.js) —
bascule d'hôte sans reconstruction d'image", exactement les 7 fichiers listés
dans le brief (les fichiers `.superpowers/sdd/*` et `docs/superpowers/plans/*`
présents dans l'arbre de travail à ce moment-là n'ont pas été touchés — hors
périmètre de cette tâche).

## Auto-revue

- **Complétude** : les 12 étapes du brief exécutées dans l'ordre, les 7
  fichiers du brief créés/modifiés exactement comme spécifié — aucun fichier
  additionnel touché (pas de `docker-compose.prod.yml`, pas de `core/`).
- **Qualité / rétrocompatibilité** : `loadConfig(env, runtimeEnv?)` — second
  paramètre optionnel, tous les anciens appels (`loadConfig(base)`, les 3
  tests pré-existants) continuent de fonctionner sans modification. `App.tsx`
  est le seul appelant hors tests (`grep -rn "loadConfig(" shell/src`
  reconfirmé après modification — toujours un seul appelant runtime) et lit
  `window.__GEOSTUDIO_ENV__` de façon défensive (`as unknown as {...}`,
  `undefined` en dev/Vitest/Playwright où `/env-config.js` n'existe pas).
- **Discipline** : aucun scope creep — pas touché à
  `docker-compose.prod.yml` (déjà câblé par Task 3), pas de fichier core/.
- **Couverture de test du cas non-évident** : le test "runtime env with
  un-substituted envsubst placeholder falls back to build-time" exerce
  précisément la garde `!value.startsWith("${")` dans `mergeRuntimeEnv` — sans
  cette garde, `VITE_CORE_URL: "${VITE_CORE_URL}"` écraserait la valeur
  build-time avec le literal `"${VITE_CORE_URL}"` au lieu de conserver
  `"https://core.test"`. La suite couvre les branches restantes : présence
  (override effectif), absence (comportement identique à avant), et override
  partiel (repli sur build-time pour les clés non fournies par `runtimeEnv`,
  ex. `oidcClientId`).

## Problèmes / préoccupations

Aucun. Tout s'est déroulé comme prévu par le brief, y compris l'échec rouge
attendu (assertion, pas erreur de compilation) et le rendu Docker exact.

Note : un ancien rapport `task-4-report.md` non lié (SP-12g, connecteur CKAN)
occupait ce chemin de fichier avant cette tâche — écrasé par ce rapport, comme
attendu pour ce chemin de sortie.

---

## Correctif post-revue — garde `mergeRuntimeEnv` sur chaîne vide

### Constat de la revue (finding « Important »)

`mergeRuntimeEnv` (`shell/src/config.ts:11-27`) ne rejetait que
`value === undefined` et le literal `"${VAR}"` non substitué. Le commentaire
affirmait qu'`envsubst` « laisse `${VAR}` tel quel quand VAR n'était pas
définie au démarrage du conteneur » — c'est faux : `envsubst`, appelé avec une
liste explicite de variables (comme le fait
`shell/docker-entrypoint.d/40-render-runtime-config.sh`), substitue une
variable de la whitelist non définie par une **chaîne vide**, jamais par le
texte littéral `${VAR}`. Le literal ne peut survivre que si la clé n'a jamais
été passée à `envsubst` (ex. un futur placeholder ajouté au template mais
oublié dans la whitelist du script d'entrée).

Conséquence réelle : si une des 6 variables `VITE_*` runtime venait à manquer
dans l'environnement d'un conteneur (overlay compose futur, `docker run`
manuel, faute de frappe d'un opérateur — pas le cas aujourd'hui, le service
`shell` de `docker-compose.prod.yml` fixe toujours les 6), `envsubst` produit
`""` pour cette clé. L'ancienne garde (`value !== undefined &&
!value.startsWith("${")`) traitait `""` comme une vraie override et écrasait
la valeur de build — pour les champs requis (`VITE_CORE_URL`,
`VITE_OIDC_*`), ceci fait échouer `loadConfig` au démarrage
(`Missing required env vars: ...`), exactement dans le scénario (config
runtime partielle/absente) où ce mécanisme devait au contraire être résilient.

### Correctif appliqué

`shell/src/config.ts:23` — garde étendue pour rejeter aussi la chaîne vide :

```ts
if (value !== undefined && value !== "" && !value.startsWith("${")) {
```

Commentaire (`config.ts:18-22`) réécrit pour décrire correctement les deux cas
gardés : (a) clé présente mais vide — la variable était dans la whitelist
`envsubst` mais non définie dans l'environnement du conteneur, rendue `""` ;
(b) le literal `${VAR}` qui survit uniquement si la clé n'a jamais été passée
à `envsubst` du tout (cas non observé aujourd'hui, robustesse pour l'avenir).

### Preuve TDD — RED

Nouveau test ajouté à `shell/src/config.test.ts` (sibling du test placeholder
existant) :

```ts
test("runtime env with empty string (envsubst on an unset whitelisted var) falls back to build-time", () => {
  const cfg = loadConfig(base, { VITE_CORE_URL: "" });
  expect(cfg.coreUrl).toBe("https://core.test");
});
```

Vérifié en isolant temporairement l'ancienne garde (`git stash` sur
`config.ts` seul, test conservé) :

```
cd shell && npm test -- config.test.ts
```

```
 ❯ src/config.test.ts (7 tests | 1 failed) 10ms
   ✓ loads a full oidc config 2ms
   ✓ throws listing all missing required vars in oidc mode 1ms
   ✓ mock mode does not require oidc vars 0ms
   ✓ runtime env overrides build-time env when present and substituted 0ms
   ✓ runtime env with un-substituted envsubst placeholder falls back to build-time 0ms
   × runtime env with empty string (envsubst on an unset whitelisted var) falls back to build-time 2ms
     → Missing required env vars: VITE_CORE_URL
   ✓ absent runtime env behaves exactly like before (undefined second arg) 0ms

 Test Files  1 failed (1)
      Tests  1 failed | 6 passed (7)
```

Confirme exactement le bug décrit par la revue : `""` traité comme override
valide → `coreUrl` devient `""` → validation `required` échoue.

`git stash pop` pour restaurer le correctif, puis re-vérification manuelle du
contenu de `config.ts`.

### Preuve TDD — GREEN

```
cd shell && npm test -- config.test.ts
```

```
 ✓ src/config.test.ts (7 tests) 9ms

 Test Files  1 passed (1)
      Tests  7 passed (7)
```

### Suite complète (non-régression)

```
cd shell && npm test
```

```
 Test Files  87 passed (87)
      Tests  594 passed (594)
   Duration  20.18s
```

(Le stderr affiché par `exprBindings.test.ts` — `CelParseError` logué par
`evaluateExpression` — fait partie du comportement attendu de ce test déjà
existant, sans lien avec ce correctif ; le test est vert.)

```
cd shell && npm run build
```

```
tsc --noEmit && vite build
✓ 2697 modules transformed.
✓ built in 11.33s
```

Avertissements identiques à ceux déjà documentés dans ce rapport (script
`env-config.js` non-module, chunks >500kB) — pré-existants, non liés à ce
correctif.

### Fichiers modifiés (ce correctif)

- `/home/lenen/projets/geostudio/shell/src/config.ts` (garde + commentaire)
- `/home/lenen/projets/geostudio/shell/src/config.test.ts` (1 test ajouté)

Commit : `bf56c11` — « fix(shell): mergeRuntimeEnv — une valeur runtime vide
(envsubst non substitué) ne doit pas écraser le build (revue Task 4) »,
nouveau commit distinct de `1b3874d` (pas d'amend).
