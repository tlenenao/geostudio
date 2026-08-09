# SP-17a Task 2 — Rapport : capacité `CORE_EXPORT_ENABLED` (cœur + shell)

## Ce qui a été implémenté

Nouvelle capacité instance-wide `CORE_EXPORT_ENABLED`, même convention que
`CORE_ETL_ENABLED` (SP-15a) : lue à chaque appel via `os.environ`, sans
cache, défaut `false`.

- **Cœur** : `is_export_enabled()` ajoutée dans `core/app/auth/dependency.py`
  juste après `is_etl_enabled()`. `GET /instance` renvoie désormais
  `{"readOnly": bool, "etlEnabled": bool, "exportEnabled": bool}`
  (`core/app/instance/routes.py`).
- **Shell** : `InstanceInfo` (`shell/src/api/types.ts`) gagne
  `exportEnabled: boolean`. Le fallback défensif de `useInstanceInfo`
  (`shell/src/api/hooks.ts`) résout désormais à
  `{ readOnly: false, etlEnabled: false, exportEnabled: false }` quand le
  client de test ne fournit pas `getInstanceInfo`.
- **`.env.example`** : `CORE_EXPORT_ENABLED=false` ajouté juste après
  `CORE_ETL_ENABLED=false`.

## Écart par rapport au brief : fichier de test shell

Le brief pointait vers `shell/src/api/hooks.test.ts` (à créer si absent).
En pratique, `shell/src/api/hooks.test.tsx` existe déjà (extension `.tsx`,
pas `.ts`) et couvre déjà `useInstanceInfo` (deux tests : `readOnly` via
MSW, et le cas fail-open réseau). Le contexte React n'est **pas** exporté
sous le nom `ItemClientContext` depuis un module `itemClientContext.ts`
comme le suggérait le brief — il vit en `const` privée dans
`ItemClientProvider.tsx` et n'est jamais exporté ; le harnais existant
utilise `ItemClientProvider` (composant) + un `makeWrapper(client)` local
pour les mocks `Partial<ItemClient>`. J'ai suivi cette convention réelle
plutôt que le boilerplate suggéré (import cassé de toute façon).

Deux tests ajoutés à la suite des deux tests `useInstanceInfo` existants :
1. `useInstanceInfo returns exportEnabled from the core` — via
   `server.use(http.get(".../instance", ...))` (MSW), même patron que le
   test `readOnly` voisin.
2. `useInstanceInfo falls back to exportEnabled: false when the client
   doesn't implement getInstanceInfo` — via `makeWrapper({} as ItemClient)`,
   même patron que les autres tests du fichier utilisant des mocks
   `Partial<ItemClient>`.

## Écart par rapport au brief : régression sur deux tests existants

Ajouter `exportEnabled` au corps de `/instance` casse deux tests
pré-existants qui asseyaient une égalité stricte de dict (`==`) sans ce
champ :
- `core/tests/test_etl_enabled_flag.py` (2 tests)
- `core/tests/test_read_only_mode.py` (2 tests)

Ces fichiers n'étaient pas dans le périmètre `Touches only` du brief, mais
les laisser casser aurait été une régression réelle de la suite cœur
(explicitement vérifiée dans le self-review demandé). J'ai ajouté
`"exportEnabled": False` aux quatre assertions concernées — c'est
exactement le même geste qui avait dû être fait pour ces deux fichiers
quand `etlEnabled` avait été introduit (ils contiennent déjà `etlEnabled`
dans leurs assertions). Changement mécanique, pas de logique touchée.

## TDD — preuves RED/GREEN

### Cœur

RED (avant implémentation) :
```
$ cd core && uv run pytest tests/test_export_enabled_flag.py -v
ImportError: cannot import name 'is_export_enabled' from 'app.auth.dependency'
```

GREEN (après `is_export_enabled()` + réécriture de `routes.py`) :
```
$ cd core && uv run pytest tests/test_export_enabled_flag.py -v
tests/test_export_enabled_flag.py::test_is_export_enabled_defaults_to_false PASSED
tests/test_export_enabled_flag.py::test_is_export_enabled_reads_env_var PASSED
tests/test_export_enabled_flag.py::test_instance_reports_export_disabled_by_default PASSED
tests/test_export_enabled_flag.py::test_instance_reports_export_enabled PASSED
4 passed in 1.87s
```

### Shell

RED (test ajouté, fallback pas encore mis à jour) :
```
$ cd shell && npx vitest run src/api/hooks.test.tsx
× useInstanceInfo falls back to exportEnabled: false when the client doesn't implement getInstanceInfo
  expected { readOnly: false, etlEnabled: false } to deeply equal { readOnly: false, …(2) }
23 passed | 1 failed (24)
```
(le test « returns exportEnabled from the core » passait déjà à ce stade
car il passe par le vrai client HTTP + MSW, pas par le fallback — seul le
test de fallback exerçait le code à changer.)

GREEN (après mise à jour du fallback dans `hooks.ts`) :
```
$ cd shell && npx vitest run src/api/hooks.test.tsx
Test Files  1 passed (1)
Tests  24 passed (24)
```

## Fichiers modifiés

- `core/app/auth/dependency.py` — ajout `is_export_enabled()`
- `core/app/instance/routes.py` — `GET /instance` renvoie `exportEnabled`
- `core/tests/test_export_enabled_flag.py` — nouveau, 4 tests
- `core/tests/test_etl_enabled_flag.py` — fix régression (2 assertions)
- `core/tests/test_read_only_mode.py` — fix régression (2 assertions)
- `shell/src/api/types.ts` — `InstanceInfo` gagne `exportEnabled`
- `shell/src/api/hooks.ts` — fallback `useInstanceInfo` gagne `exportEnabled: false`
- `shell/src/api/hooks.test.tsx` — 2 tests ajoutés
- `.env.example` — `CORE_EXPORT_ENABLED=false` ajouté après `CORE_ETL_ENABLED=false`

## Self-review

- [x] `is_export_enabled()` et le fallback shell défaultent tous deux à
      `false` quand la variable/le mock est absent(e).
- [x] 4 nouveaux tests cœur passent.
- [x] 2 nouveaux tests shell passent, plus les 22 tests pré-existants du
      même fichier (24/24).
- [x] Pas de régression dans la suite auth/hooks élargie (voir suites
      complètes ci-dessous).
- [x] Ligne `.env.example` ajoutée au bon endroit (juste après
      `CORE_ETL_ENABLED=false`).
- [x] `tsc --noEmit && vite build` passe (aucun site consommateur
      d'`InstanceInfo` ne construit de littéral, tous lisent seulement
      `.readOnly`/`.etlEnabled` — l'ajout d'un champ est rétrocompatible).

## Suites complètes

Cœur (avant commit) :
```
$ cd core && uv run pytest -q
1281 passed, 137 skipped in 85.71s
```

Shell — suite Vitest complète :
```
$ cd shell && npm run test -- --run
Test Files  124 passed (124)
Tests  1001 passed (1001)
```

Shell — build (tsc + vite) :
```
$ cd shell && npm run build
tsc --noEmit && vite build
✓ built in 11.96s
```
(warnings pré-existants sans rapport : bundle-size, import dynamique
`MapView.tsx` — aucune erreur.)

## Préoccupations

Aucune préoccupation bloquante. Seul point notable : le fichier
`.superpowers/sdd/progress.md` est apparu modifié dans `git status` en
cours de tâche (probablement l'orchestrateur qui tient le ledger de la
session en parallèle) — je ne l'ai pas touché et l'ai explicitement exclu
du commit.

## Commit

`474b6e9` — `feat: SP-17a — capacité CORE_EXPORT_ENABLED (cœur + shell)`
(message étendu pour documenter le fix de régression sur les deux tests
existants, cf. corps du commit).
