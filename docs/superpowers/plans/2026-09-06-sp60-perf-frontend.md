# SP-60 — Performance frontend & filets de test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-68 (performance frontend) et le reliquat de GAP-69
(filets de test troués sur l'infrastructure de qualité elle-même)
documentés par `docs/superpowers/specs/2026-09-06-sp60-perf-frontend-design.md`.
Aucune dépendance sur les chantiers SP-45→SP-58. Dépendance de vérification
seule sur SP-43 (déjà clos) : `test_model_alembic_parity.py` et
`mockCollection()` existent déjà, ce plan ne les recrée pas.

**Architecture:** Deux groupes sans dépendance dure entre eux (GAP-69,
Tasks 1-5 ; GAP-68, Tasks 6-9), plus une tâche de vérification finale
(Task 10). À l'intérieur de GAP-68, Task 8 (découpage par route) doit
suivre Task 7 (fix `MapView`) — convertir `MapEditorPage` en route lazy
avant que son propre import de `MapView` soit lui-même rendu lazy créerait
une fenêtre où les deux changements se chevauchent sur le même fichier ;
Task 9 (vendor chunks + filet de taille) doit suivre Task 8, la mesure du
seuil dépendant du découpage déjà en place.

**Tech Stack:** Python 3.12/pytest/SQLAlchemy/Alembic (Tasks 1-3),
Playwright (Task 4), Vitest + `@testing-library/react` + MSW (Tasks 5-8),
Vite/Rollup (Tasks 7-9) — aucune nouvelle dépendance npm/uv.

## Global Constraints

- Chaque tâche suit TDD (test qui échoue → implémentation minimale → test
  qui passe → commit), conformément à `CLAUDE.md`.
- Commits conventionnels français (`test(core): …`, `test(e2e): …`,
  `fix(shell): …`, `perf(shell): …`, `refactor(shell): …`), un sujet par
  commit.
- **Aucune régénération OpenAPI/types TS n'est attendue dans ce plan** :
  aucune route ni modèle du cœur ne change de forme (piège n°1 CLAUDE.md,
  vérifié — seules des assertions de test, `vite.config.ts`, `routes.tsx`
  et 4 composants de sondage bougent). Un diff non vide sur
  `core-schema.d.ts` en fin de plan serait le signe d'une régression, pas
  un oubli à combler.
- **Terrain3DUploadButton/Tileset3DUploadButton/PipelineRunPanel/
  ImportFileButton (Task 6)** : le patron de correction est **copié**
  depuis `shell/src/builder/print/ExportPanel.tsx:35-45,47-62`
  (`mountedRef`+`timerRef`), jamais réinventé — vérifier ce fichier avant
  d'écrire le correctif de chaque composant.
- Lancer la suite Vitest complète (`npm run test`), la suite Playwright
  complète (`npm run e2e`) et la suite pytest complète (`uv run pytest`)
  une fois à la toute fin du plan (Task 10), conformément à `CLAUDE.md`
  (piège n°6 : régressions cross-tâches trouvées seulement à la première
  exécution complète).
- Nettoyer `dist/`/`dist-export/` avant toute mesure de couverture shell
  (piège documenté 4 fois dans `CLAUDE.md`) — pertinent ici aussi car
  Task 9 lance `npm run build` à plusieurs reprises pendant la même
  session.

---

## File structure

**Create:**
- `shell/scripts/check-bundle-size.mjs` + `shell/.bundle-size-threshold` (Task 9)

**Modify:**
- `core/tests/test_deployability.py` (Task 1, Task 2)
- `core/tests/test_features_routes_read.py` (Task 3)
- `core/tests/test_attachments_read_routes.py` (Task 3)
- `shell/e2e/triptych-narrow.spec.ts` (Task 4)
- `shell/e2e/ingestion-gpkg.spec.ts`, `alert-rule.spec.ts`,
  `bookmarks.spec.ts`, `pipeline-builder.spec.ts`, `dataset-export.spec.ts`,
  `incident-form.spec.ts`, `datasets-shared.spec.ts`, `visual-query.spec.ts`,
  `analytics-context.spec.ts`, `admin-collections.spec.ts` (Task 5)
- `shell/src/map/Terrain3DUploadButton.tsx` + `.test.tsx` (Task 6)
- `shell/src/shell/Tileset3DUploadButton.tsx` + `.test.tsx` (Task 6)
- `shell/src/builder/pipeline/PipelineRunPanel.tsx` + `.test.tsx` (Task 6)
- `shell/src/shell/ImportFileButton.tsx` + `.test.tsx` (Task 6)
- `shell/src/pages/MapEditorPage.tsx` + `.test.tsx` (Task 7)
- `shell/src/shell/routes.tsx` + `routes.test.tsx` (Task 8)
- `shell/src/shell/AppLayout.tsx` (Task 8, `<Suspense>` autour de `<Outlet/>`)
- `shell/vite.config.ts` (Task 8, Task 9)
- `.github/workflows/ci.yml` (Task 9)

---

### Task 1: `core_env_vars()`/`compose_substitutions()`/`documented_env_vars()` — garde de borne basse

**Files:**
- Modify: `core/tests/test_deployability.py`

**Interfaces:** aucune nouvelle fonction de production — 3 tests purs sur
des fonctions déjà exportées du module de test lui-même.

Contexte (spec §2.3) : ces 3 extracteurs peuvent retourner l'ensemble vide
sans qu'aucun test existant ne le détecte. Mesuré le 2026-09-06 :
`core_env_vars()` = 68, `compose_substitutions()` = 64,
`documented_env_vars(include_commented=True)` = 76,
`documented_env_vars(include_commented=False)` = 54.
`"CORE_AUTH_MODE"`/`"S3_ATTACHMENTS_BUCKET"` sont tous deux dans
`core_env_vars()` aujourd'hui.

- [ ] **Step 1: Confirmer la mesure avant d'écrire le seuil**

Run (depuis `core/`, avec une master key de test) :
```bash
CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python -c "
import sys; sys.path.insert(0, 'tests'); sys.path.insert(0, '.')
from test_deployability import core_env_vars, compose_substitutions, documented_env_vars
print(len(core_env_vars()), len(compose_substitutions()), len(documented_env_vars(True)))
"
```
Expected: `68 64 76` (ou proche — si très différent, ajuster les seuils
des steps suivants en conséquence plutôt que de recopier aveuglément ces
chiffres).

- [ ] **Step 2: Write the failing tests**

Ajouter à la fin de `core/tests/test_deployability.py` :
```python
def test_core_env_vars_extractor_has_not_silently_regressed_to_empty():
    """REV-076/F-tests-04 : core_env_vars() est la clé de voûte de
    test_every_core_env_var_is_wired_to_a_service — si elle régressait vers
    l'ensemble vide, ce test resterait vert par construction
    (unwired = vide - vide - exemptions = vide). Plancher choisi
    confortablement sous la mesure réelle (68 au 2026-09-06), jamais un
    nombre exact fragile."""
    found = core_env_vars()
    assert len(found) >= 60, (
        f"core_env_vars() n'a trouvé que {len(found)} variable(s) — "
        "régression probable de l'extraction AST, pas une baisse légitime "
        "du nombre de variables lues par core/app/"
    )
    for sentinel in ("CORE_AUTH_MODE", "S3_ATTACHMENTS_BUCKET"):
        assert sentinel in found, f"{sentinel} doit apparaître dans core_env_vars()"


def test_compose_substitutions_extractor_has_not_silently_regressed_to_empty():
    """Même garde que ci-dessus pour compose_substitutions(), clé de voûte
    de test_every_compose_substitution_is_documented."""
    found = compose_substitutions()
    assert len(found) >= 55, (
        f"compose_substitutions() n'a trouvé que {len(found)} variable(s) — "
        "régression probable de la regex ${VAR}, pas une baisse légitime"
    )


def test_documented_env_vars_extractor_has_not_silently_regressed_to_empty():
    """Même garde pour documented_env_vars(), y compris commentées."""
    found = documented_env_vars(include_commented=True)
    assert len(found) >= 65, (
        f"documented_env_vars() n'a trouvé que {len(found)} variable(s) — "
        "régression probable de la regex sur .env.example"
    )
```

- [ ] **Step 2b: Confirmer que ces tests passent déjà (le code n'a pas de
  défaut, seul le filet manquait)**

Run: `cd core && uv run pytest tests/test_deployability.py -k "has_not_silently_regressed" -v`
Expected: 3 PASS. (Contrairement au reste du plan, il n'y a ici aucun
défaut de production à corriger — la falsification consiste à confirmer
que ces tests échoueraient si on les avait retirés de la couverture, pas à
observer un échec réel avant correctif.)

- [ ] **Step 3: Falsification — prouver que les tests détecteraient bien
  une régression**

Temporairement, dans un REPL ou un test jetable, appeler
`core_env_vars.__wrapped__` n'existe pas — plus simple : monkeypatcher
`CORE_APP` sur un répertoire vide dans un test **temporaire** (à ne pas
committer) pour vérifier que `core_env_vars()` retourne alors l'ensemble
vide et que l'assertion `>= 60` échoue bien. Documenter le résultat dans
le message de commit ou un commentaire, puis retirer le test jetable —
ne garder que les 3 tests de Step 2.

- [ ] **Step 4: Run full file to verify no regression**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: tous les tests existants + les 3 nouveaux passent.

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_deployability.py
git commit -m "test(core): garde de borne basse sur core_env_vars()/compose_substitutions()/documented_env_vars() (GAP-69)"
```

---

### Task 2: routeurs Traefik `core`/`shell` — `security-headers`/`rate-limit`

**Files:**
- Modify: `core/tests/test_deployability.py`

**Interfaces:** réutilise `services()`, `_traefik_labels()`,
`_router_middlewares()`, `BASE`, `PROD` déjà définis dans le fichier.

Contexte (spec §2.2) : un test équivalent existe pour Keycloak
(`test_keycloak_router_carries_security_and_rate_limit_middlewares`, PROD
seul) mais aucun pour `core`/`shell`, alors que les deux portent bien ces
deux middlewares aujourd'hui (`docker-compose.yml:377,780`,
`docker-compose.prod.yml:165,257`).

- [ ] **Step 1: Write the failing test**

Ajouter, à la suite du bloc Keycloak (après ligne ~1034) :
```python
@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
@pytest.mark.parametrize("router", ["core", "shell"])
def test_public_app_router_carries_security_and_rate_limit_middlewares(compose, router):
    """REV-073/F-tests-03 : les routeurs core et shell portent aujourd'hui
    security-headers@docker et rate-limit@docker (vérifié par grep direct
    sur les deux fichiers compose), mais aucun test ne le garantissait —
    contrairement au routeur keycloak (test au-dessus) et aux 3 routeurs
    admin. Une régression qui retirerait un de ces deux middlewares d'un
    des deux routeurs serait aujourd'hui invisible."""
    labels = _traefik_labels(services(compose)[router])
    middlewares = _router_middlewares(labels, router)
    for required in ("security-headers@docker", "rate-limit@docker"):
        assert required in middlewares, (
            f"le routeur {router} ({compose.name}) doit référencer {required} "
            f"dans ses middlewares, a trouvé : {middlewares}"
        )


def test_security_headers_middleware_defines_the_expected_directives():
    """Complément REV-073 : le routeur peut référencer security-headers@docker
    sans que la définition elle-même porte les 4 directives attendues (par
    ex. si un futur refactor renomme les clés de label sans y penser)."""
    labels = _traefik_labels(services(PROD)["core"])
    assert labels["traefik.http.middlewares.security-headers.headers.stsSeconds"] == "31536000"
    assert labels["traefik.http.middlewares.security-headers.headers.contentTypeNosniff"] == "true"
    assert labels["traefik.http.middlewares.security-headers.headers.frameDeny"] == "true"
    assert (
        "traefik.http.middlewares.security-headers.headers.referrerPolicy" in labels
    )


def test_rate_limit_middleware_defines_average_and_burst():
    """Complément REV-073, symétrique au test ci-dessus pour rate-limit."""
    labels = _traefik_labels(services(PROD)["core"])
    assert labels["traefik.http.middlewares.rate-limit.ratelimit.average"] == "100"
    assert labels["traefik.http.middlewares.rate-limit.ratelimit.burst"] == "200"
```

Note : les deux middlewares sont définis une seule fois, sur le service
`core` (vérifié par grep — cf. spec §2.2), et référencés par les autres
routeurs via `@docker` (même mécanisme que `admin-auth`, documenté par
`test_admin_auth_forwardauth_middleware_defined_exactly_once` plus haut
dans ce fichier) — d'où `services(PROD)["core"]` pour les deux derniers
tests, pas `services(PROD)["shell"]`. **Vérifier ce point par lecture
directe de `docker-compose.prod.yml` avant d'écrire le test** (piège n°3
CLAUDE.md) : si les labels de définition apparaissaient en fait sur un
autre service, corriger la cible en conséquence.

- [ ] **Step 2: Run to verify it passes (le câblage est déjà correct)**

Run: `cd core && uv run pytest tests/test_deployability.py -k "security_and_rate_limit_middlewares or security_headers_middleware or rate_limit_middleware" -v`
Expected: tous PASS (4 paramétrages du premier test + 2 tests simples).
Si un des 4 paramétrages échoue, c'est une découverte réelle (un routeur
mal câblé) — **ne pas contourner par un `xfail`**, corriger le compose
correspondant avant de continuer.

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_deployability.py
git commit -m "test(core): garde security-headers/rate-limit sur les routeurs core et shell (GAP-69)"
```

---

### Task 3: renforcer les deux tests « lisible anonymement »

**Files:**
- Modify: `core/tests/test_attachments_read_routes.py`
- Modify: `core/tests/test_features_routes_read.py`

**Interfaces:** aucune — renforcement d'assertions sur des tests existants.

- [ ] **Step 1: Falsifier le défaut avant de le corriger (attachments)**

Dans `core/tests/test_attachments_read_routes.py`, temporairement, faire
retourner une liste vide au lieu du vrai contenu par le repository
(monkeypatch jetable ou simple inspection manuelle) et confirmer que
`test_list_and_file_are_readable_anonymously_on_a_public_collection`
passe quand même aujourd'hui — documenter le résultat (ne pas committer
le monkeypatch de falsification), puis passer à Step 2.

- [ ] **Step 2: Renforcer le test attachments**

Dans `core/tests/test_attachments_read_routes.py`, remplacer le corps de
`test_list_and_file_are_readable_anonymously_on_a_public_collection`
(lignes 199-211) :
```python
def test_list_and_file_are_readable_anonymously_on_a_public_collection(env):
    api, Session, tenant, owner, _reader, attachment_id, _s3 = env
    with Session() as session:
        col = session.get(Collection, "col1")
        col.is_public = True
        session.commit()
    api.app.dependency_overrides.pop(get_current_user, None)
    api.app.dependency_overrides.pop(get_current_user_optional, None)

    list_res = api.get("/collections/col1/items/f1/attachments")
    assert list_res.status_code == 200
    # Renforcement REV-077/F-tests-05 : une liste vide passait avant ce
    # correctif (seul le code 200 était vérifié) — même patron que
    # test_list_visible_to_the_owner (ligne 166) et
    # test_file_visible_to_another_reader_with_read_access (lignes 175-177).
    assert list_res.json()["attachments"][0]["filename"] == "a.jpg"

    file_res = api.get(f"/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert file_res.status_code == 200
    assert file_res.content == b"jpg"
    assert file_res.headers["content-type"].startswith("image/jpeg")
```

- [ ] **Step 3: Renforcer le test features**

Dans `core/tests/test_features_routes_read.py`, `test_anonymous_reads_public_only`
(lignes 169-181), après chaque `assert ... .status_code == 200`, ajouter
une assertion de contenu s'appuyant sur `FEAT`/`make_fake_repo` déjà
définis en tête de fichier :
```python
def test_anonymous_reads_public_only(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/collections/incidents/items").status_code == 404
    _register(app, client, admin, public=True)  # re-register échoue (409) mais PATCH ok :
    _as(app, admin)
    client.patch("/collections/incidents", json={"isPublic": True})
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    res = client.get("/collections/incidents/items")
    assert res.status_code == 200
    # Renforcement REV-077 (même défaut, second site trouvé par cette
    # spec) : sans cette ligne, une réponse à liste vide passait aussi.
    assert res.json()["numberReturned"] == 1
    assert res.json()["features"][0]["id"] == 1
```
Vérifier au préalable (lecture du fichier) que la variable `_repo` n'est
pas déjà utilisée après cette ligne d'une façon qui rendrait le
renommage/l'ajout incohérent — le nom `res` introduit ici ne doit pas
entrer en collision avec une variable existante plus bas dans le test
(il n'y en a pas d'autre après, à confirmer par lecture).

- [ ] **Step 4: Run both files**

Run: `cd core && uv run pytest tests/test_attachments_read_routes.py tests/test_features_routes_read.py -v`
Expected: tous PASS.

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_attachments_read_routes.py core/tests/test_features_routes_read.py
git commit -m "test(core): les tests de lecture anonyme vérifient le contenu, pas seulement le code 200 (GAP-69)"
```

---

### Task 4: `triptych-narrow.spec.ts` — ancre positive sur la boucle 900px

**Files:**
- Modify: `shell/e2e/triptych-narrow.spec.ts`

**Interfaces:** ajoute un champ optionnel `readyAnchor?: (page: Page) =>
Promise<void>` à chaque entrée de `SCREENS` (défaut : vérifie la présence
du conteneur `div.grid` de `TriptychLayout`).

Contexte (spec §2.1) : la boucle 900px (lignes 291-305) n'a aucune
assertion prouvant que l'écran a quitté un état de chargement avant de
mesurer 0 offenseur — contrairement à la boucle 390px qui vérifie
`getByRole("navigation", { name: "Navigation" })`.

- [ ] **Step 1: Falsifier le défaut avant de le corriger**

Modifier temporairement (ne pas committer) l'un des `before` de `SCREENS`
(ex. « Automatisation ») pour ne **jamais** répondre à
`https://core.test/pipelines/ops` (retirer le `route()` de
`AUTOMATISATION_OPS_CATALOG`) — la page reste bloquée sur
`role="status"` « Chargement… ». Lancer :
```bash
cd shell && npx playwright test triptych-narrow.spec.ts -g "Automatisation à 900 px"
```
Expected AVANT correctif : le test **passe** quand même (0 offenseur
mesuré sur un écran vide) — confirme le défaut décrit par GAP-69/REV-075.
Annuler la modification temporaire avant de continuer.

- [ ] **Step 2: Ajouter une ancre positive par écran**

Dans `shell/e2e/triptych-narrow.spec.ts`, étendre le type `SCREENS` avec un
champ optionnel :
```ts
// Ancre positive pour la boucle 900px (Step 3 ci-dessous) : un sélecteur
// que seul cet écran, une fois réellement rendu (pas bloqué en
// Chargement…), satisfait. Sans elle, expectNoClippedContent() peut
// mesurer 0 offenseur sur un écran encore en train de charger et
// "passer" sans avoir rien exercé (REV-075).
readyAnchor?: (page: Page) => Promise<unknown>;
```
Puis, pour chacune des 8 entrées de `SCREENS`, choisir une ancre :
- Catalogue : `page.getByRole("heading", { name: /catalogue/i })` (ou
  équivalent déjà utilisé par les autres specs de ce fichier — vérifier le
  libellé exact rendu par `CatalogPage` avant d'écrire l'assertion).
- Cartes : `page.getByText("Carte des communes")` (titre de la fixture
  `map-1`, déjà utilisé ailleurs dans la suite E2E carte).
- Apps & sites : titre de l'item `1` (« Alpha », cf. `e2e/mocks.ts`).
- Analytique : éditeur SQL Lab — un élément stable de `SqlLabPage`
  (vérifier son rendu réel avant de choisir le sélecteur).
- Automatisation : un élément du canevas DAG rendu une fois
  `AUTOMATISATION_OPS_CATALOG` chargé (ex. le nœud `reader.collection`).
- Tâches / Paramètres : ces deux écrans ne rendent jamais de grille
  `TriptychLayout` (confirmé §2.1 de la spec) — ancre sur le contenu de
  leur `<EmptyState>` respectif, pas sur la grille.
- Administration : un élément de `AdminExtensionsPage` une fois chargé.

Pour chaque ancre choisie, **vérifier par exécution** (pas par supposition)
qu'elle apparaît bien dans le DOM une fois l'écran réellement chargé —
lancer chaque test individuellement après l'avoir écrit.

- [ ] **Step 3: Appliquer l'ancre dans les deux boucles**

Dans la boucle 390px (lignes 244-270), après
`expect(page.getByRole("navigation", ...)).toBeVisible()`, ajouter :
```ts
if (screen.readyAnchor) await screen.readyAnchor(page);
```
avant `expectNoClippedContent(page)`. Dans la boucle 900px (lignes
291-305), ajouter la même ligne juste après `await page.goto(screen.path)`
et avant `expectNoClippedContent(page)`.

- [ ] **Step 4: Re-falsifier pour confirmer la correction**

Rejouer le scénario de Step 1 (route `pipelines/ops` non répondue) : le
test doit maintenant **échouer** (timeout sur `readyAnchor`), preuve que
l'ancre détecte bien l'écran resté bloqué. Annuler la modification
temporaire.

- [ ] **Step 5: Run the full file**

Run: `cd shell && npx playwright test triptych-narrow.spec.ts`
Expected: tous PASS (390px, 900px, 700px, test dédié section icônes).

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/triptych-narrow.spec.ts
git commit -m "test(e2e): ancre positive sur la boucle 900px de triptych-narrow.spec.ts (GAP-69)"
```

---

### Task 5: adoption de `mockCollection()` dans les 9 specs E2E restantes

**Files:**
- Modify: `shell/e2e/ingestion-gpkg.spec.ts`, `alert-rule.spec.ts`,
  `bookmarks.spec.ts`, `pipeline-builder.spec.ts`, `dataset-export.spec.ts`,
  `incident-form.spec.ts`, `datasets-shared.spec.ts`, `visual-query.spec.ts`,
  `analytics-context.spec.ts`, `admin-collections.spec.ts`

**Interfaces:** consomme `mockCollection(overrides)` déjà exporté par
`shell/e2e/mocks.ts:208-210` (SP-43) — aucune nouvelle interface.

Contexte (spec §1, §2.5) : ces fichiers construisent un littéral de
collection à la main, avec seulement 10-12 champs, alors que
`_collection_json()` en produit 23 en réel aujourd'hui. `mockCollection()`
existe déjà et comble l'écart — il suffit de l'utiliser.

- [ ] **Step 1: Inventaire précis avant modification**

Run: `cd shell && grep -n "geometryType" e2e/ingestion-gpkg.spec.ts e2e/alert-rule.spec.ts e2e/bookmarks.spec.ts e2e/pipeline-builder.spec.ts e2e/dataset-export.spec.ts e2e/incident-form.spec.ts e2e/datasets-shared.spec.ts e2e/visual-query.spec.ts e2e/analytics-context.spec.ts e2e/admin-collections.spec.ts`
Noter chaque occurrence (fichier:ligne) — certaines peuvent être dans un
littéral **imbriqué** dans un tableau de plusieurs collections (cf.
`pipeline-builder.spec.ts:44-61`, 2 collections dans le même `route()`).

- [ ] **Step 2: Remplacer chaque littéral, un fichier à la fois**

Pour chaque fichier listé, importer `mockCollection` depuis `./mocks` et
remplacer le littéral complet par `mockCollection({ ...overrides })`, où
`overrides` ne porte que les champs que le littéral original fixait à une
valeur non-défaut (`id`, `title`, `isPublic`, `srid`, `geometryType`,
`featureCount`, `permissions`, `owner`, etc. — cf. `DEFAULT_COLLECTION`
dans `mocks.ts:182-206` pour les valeurs par défaut). Exemple pour
`bookmarks.spec.ts:20-28` :
```ts
// avant
{
  id: "events", title: "Événements", description: "", tableName: "events",
  isPublic: true, editable: true, geometryType: null, srid: null,
  pkColumn: "id", permissions: { ... }, featureCount: ..., owner: "alice",
},
// après
mockCollection({
  id: "events", title: "Événements", tableName: "events",
  isPublic: true, geometryType: null, srid: null,
  permissions: { ... }, featureCount: ..., owner: "alice",
}),
```
Après chaque fichier modifié, lancer sa suite immédiatement (voir Step 3)
avant de passer au suivant — un littéral qui dépendait implicitement
d'une valeur absente de `DEFAULT_COLLECTION` (peu probable mais à
vérifier) se révélera à ce moment, pas à la fin du plan.

- [ ] **Step 3: Run each modified spec file**

Run (répéter pour chaque fichier de la liste) :
```bash
cd shell && npx playwright test <fichier>.spec.ts
```
Expected: PASS, comportement inchangé — ce remplacement ne doit jamais
changer ce qu'un test observe, seulement compléter la forme servie.

- [ ] **Step 4: Confirmer qu'il ne reste plus de littéral orphelin**

Run: `cd shell && grep -rln "geometryType" e2e | grep -v mocks.ts`
Expected: liste vide, ou seulement des fichiers dont le littéral avait une
bonne raison de ne pas passer par `mockCollection()` (à documenter
explicitement en commentaire si un cas de ce genre existe — ne pas laisser
un résidu silencieux).

- [ ] **Step 5: Run the full Playwright suite**

Run: `cd shell && npm run e2e`
Expected: PASS complet (142+ tests attendus, cf. dernier compte connu
`CLAUDE.md` — ce nombre a pu changer depuis, ne pas s'alarmer d'un écart
mineur, s'alarmer d'un échec).

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/*.spec.ts
git commit -m "test(e2e): migre les mocks de collection restants vers mockCollection() (GAP-69)"
```

---

### Task 6: annuler les 4 boucles de sondage au démontage

**Files:**
- Modify: `shell/src/map/Terrain3DUploadButton.tsx` + `.test.tsx`
- Modify: `shell/src/shell/Tileset3DUploadButton.tsx` + `.test.tsx`
- Modify: `shell/src/builder/pipeline/PipelineRunPanel.tsx` + `.test.tsx`
- Modify: `shell/src/shell/ImportFileButton.tsx` + `.test.tsx`

**Interfaces:** aucune signature de prop ne change sur les 4 composants —
correctif interne uniquement (`mountedRef`/`timerRef`).

Contexte (spec §3.3/§4.4) : ces 4 sondages ne s'arrêtent jamais au
démontage, contrairement au patron déjà établi par
`ExportPanel.tsx`/`AppExportPanel.tsx`/`ReportRunPanel.tsx`/
`VisualQueryWizardPage.tsx`. Terrain3D/Tileset3D sont explicitement nommés
par GAP-68 ; PipelineRunPanel/ImportFileButton partagent exactement le
même défaut, trouvé en vérifiant la spec (décision de périmètre, spec
§3.3).

- [ ] **Step 1: Write the failing test (Tileset3DUploadButton)**

Dans `shell/src/shell/Tileset3DUploadButton.test.tsx`, ajouter (patron
copié de `ExportPanel.test.tsx:87-105`) :
```tsx
test("does not poll again or update state after the drawer is unmounted mid-finalize", async () => {
  let pollCalls = 0;
  server.use(
    http.post("https://core.test/tileset3d/uploads", () =>
      HttpResponse.json({ jobId: "job-1" }, { status: 201 }),
    ),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" }),
    ),
    http.put(
      "https://minio.test/part-1",
      () => new HttpResponse(null, { status: 200, headers: { ETag: '"etag-1"' } }),
    ),
    http.post("https://core.test/tileset3d/uploads/job-1/complete", () =>
      new HttpResponse(null, { status: 204 }),
    ),
    http.get("https://core.test/tileset3d/uploads/job-1", () => {
      pollCalls += 1;
      return HttpResponse.json({ status: "running", errorMessage: null, itemId: null });
    }),
  );

  const { unmount } = render(
    <Harness>
      <Tileset3DUploadButton pollTimeoutMs={5 * 60 * 1000} />
    </Harness>,
  );
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  await waitFor(() => expect(pollCalls).toBeGreaterThanOrEqual(1));
  const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const callsAtUnmount = pollCalls;
  unmount();
  await new Promise((r) => setTimeout(r, 2000));
  expect(pollCalls).toBe(callsAtUnmount);
  expect(errorSpy).not.toHaveBeenCalled();
  errorSpy.mockRestore();
});
```
(Ajouter `vi` à l'import `vitest` du fichier si absent.)

- [ ] **Step 2: Run to see it fail**

Run: `cd shell && npx vitest run src/shell/Tileset3DUploadButton.test.tsx`
Expected: FAIL — `pollCalls` continue d'augmenter après `unmount()` (la
boucle `for(;;)` de `poll()` ne sait pas qu'elle a été démontée), et/ou
`errorSpy` a été appelé (avertissement React de `setState` sur composant
démonté).

- [ ] **Step 3: Fix `Tileset3DUploadButton.tsx`**

Ajouter `useEffect`, `useRef` à l'import React ; ajouter
`mountedRef`/`timerRef` (patron `ExportPanel.tsx:35-45`) ; dans `poll()`,
garder chaque `setState` par `if (!mountedRef.current) return;` et
remplacer `await new Promise((r) => setTimeout(r, 1500))` par
`await new Promise<void>((resolve) => { timerRef.current = setTimeout(resolve, 1500); })`.

- [ ] **Step 4: Run to see it pass**

Run: `cd shell && npx vitest run src/shell/Tileset3DUploadButton.test.tsx`
Expected: PASS.

- [ ] **Step 5-8: répéter Steps 1-4 pour `Terrain3DUploadButton.tsx`**

Même patron. Le composant a déjà `pollIntervalMs` injectable (mettre `0`
dans le test pour un sondage rapide) — utiliser ce paramètre existant
plutôt que d'en ajouter un nouveau.

- [ ] **Step 9-12: répéter Steps 1-4 pour `PipelineRunPanel.tsx`**

Le composant n'a pas de paramètre d'intervalle injectable — utiliser un
`getPipelineRuns` mocké qui répond immédiatement (le sondage reste à
1500ms réels, comme le fait déjà `ExportPanel.test.tsx`, attente de 2000ms
après démontage acceptable pour un test unitaire). `poll()` devient une
boucle gardée par un `mountedRef` posé dans un `useEffect` de nettoyage
dédié (le composant utilise déjà `useEffect` pour `loadRuns()` — un second
effet, ou l'extension du premier avec un tableau de dépendances vide
distinct, au choix de l'implémentation — vérifier que les deux effets ne
se marchent pas dessus).

- [ ] **Step 13-16: répéter Steps 1-4 pour `ImportFileButton.tsx`**

Même patron.

- [ ] **Step 17: Run les 4 fichiers de test ensemble**

Run: `cd shell && npx vitest run src/map/Terrain3DUploadButton.test.tsx src/shell/Tileset3DUploadButton.test.tsx src/builder/pipeline/PipelineRunPanel.test.tsx src/shell/ImportFileButton.test.tsx`
Expected: PASS.

- [ ] **Step 18: Typecheck**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 19: Commit**

```bash
git add shell/src/map/Terrain3DUploadButton.tsx shell/src/map/Terrain3DUploadButton.test.tsx \
        shell/src/shell/Tileset3DUploadButton.tsx shell/src/shell/Tileset3DUploadButton.test.tsx \
        shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.test.tsx \
        shell/src/shell/ImportFileButton.tsx shell/src/shell/ImportFileButton.test.tsx
git commit -m "fix(shell): annule les 4 boucles de sondage restantes au démontage (GAP-68)"
```

---

### Task 7: `MapView` — retirer l'import statique de `MapEditorPage`

**Files:**
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/MapEditorPage.test.tsx` (si nécessaire)

**Interfaces:** `MapEditorPage` utilise désormais `lazy()`+`Suspense` pour
`MapView`, comme `mapWidget.tsx`/`ExplorerDrawer.tsx`. `MapViewHandle`
reste importé en `import type` (aucun coût runtime).

- [ ] **Step 1: Mesurer le défaut avant correctif**

Run (depuis `shell/`, `dist/` déjà nettoyé) :
```bash
rm -rf dist dist-export && npm run build 2>&1 | grep -A2 INEFFECTIVE_DYNAMIC_IMPORT
```
Expected: le warning `INEFFECTIVE_DYNAMIC_IMPORT` apparaît, citant
`MapView.tsx`/`MapEditorPage.tsx`/`ExplorerDrawer.tsx`/`mapWidget.tsx` —
confirme l'état avant correctif.

- [ ] **Step 2: Convertir l'import**

Dans `shell/src/pages/MapEditorPage.tsx` :
```ts
// avant
import { MapView, type MapViewHandle } from "../map/MapView";
// après
import { lazy, Suspense } from "react"; // ajouter aux imports React existants
import type { MapViewHandle } from "../map/MapView";
const MapView = lazy(() => import("../map/MapView").then((m) => ({ default: m.MapView })));
```
Envelopper l'usage JSX de `<MapView ...>` dans `<Suspense fallback={<div
className="text-xs text-slate-400">Carte…</div>}>...</Suspense>` — même
libellé de repli que `mapWidget.tsx`/`ExplorerDrawer.tsx` (cohérence
visuelle, pas une nouvelle chaîne à traduire).

- [ ] **Step 3: Run `MapEditorPage.test.tsx`**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx`
Expected: la plupart des assertions passent déjà en `findBy`/`await` (le
fichier est déjà majoritairement asynchrone). Si une assertion synchrone
(`getByText`/`getByRole` sans `await` précédent immédiatement après un
rendu initial) échoue à cause du nouveau `Suspense`, la convertir en
`findByText`/`findByRole`. Documenter chaque site converti.

- [ ] **Step 4: Mesurer le correctif**

Run: `cd shell && rm -rf dist dist-export && npm run build 2>&1 | grep INEFFECTIVE_DYNAMIC_IMPORT`
Expected: **aucune sortie** — le warning a disparu.

- [ ] **Step 5: Typecheck**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "fix(shell): MapView en lazy()+Suspense dans MapEditorPage, résout INEFFECTIVE_DYNAMIC_IMPORT (GAP-68)"
```

---

### Task 8: découpage par route (`routes.tsx`)

**Files:**
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/shell/routes.test.tsx`
- Modify: `shell/src/shell/AppLayout.tsx` (ou le point d'accueil de
  `<Outlet/>` réel — vérifier son emplacement exact avant d'écrire le
  `<Suspense>`)

**Interfaces:** aucun changement d'API externe — les 23 imports statiques
de pages en tête de `routes.tsx` deviennent des `lazy()`.

- [ ] **Step 1: Mesurer le bundle avant correctif**

Run: `cd shell && rm -rf dist dist-export && npm run build 2>&1 | tail -20`
Noter la taille de `dist/assets/index-*.js` (attendu ≈ 3,3 Mo, cf. spec
§3.1) — c'est la mesure de référence pour Task 9.

- [ ] **Step 2: Convertir les 23 imports de pages**

Dans `shell/src/shell/routes.tsx`, remplacer chaque `import { X } from
"../pages/X";` par :
```ts
const X = lazy(() => import("../pages/X").then((m) => ({ default: m.X })));
```
pour les 23 pages listées lignes 4-26 (garder les imports non-page en
l'état : `RequireAuth`, `RequirePrivilege`, `AppLayout`, etc.). Ajouter
`lazy`, `Suspense` à l'import `react` existant.

- [ ] **Step 3: Envelopper les points de montage dans `<Suspense>`**

Localiser le rendu de `<Outlet />` (dans `ProtectedLayout`, ligne 241-249
de `routes.tsx` actuel) et l'envelopper :
```tsx
function ProtectedLayout() {
  return (
    <RequireAuth>
      <AppLayout>
        <Suspense fallback={<p role="status">Chargement…</p>}>
          <Outlet />
        </Suspense>
      </AppLayout>
    </RequireAuth>
  );
}
```
Les 4 routes hors `ProtectedLayout` (`AppRuntimeRoute`, `SitePublicRoute`,
`PublicItemRoute`, `DatasetRoute`, lignes 373-376) n'ont pas de layout
commun à envelopper une seule fois — vérifier si `AppRoutes()` peut
envelopper l'ensemble de son retour dans un seul `<Suspense>` englobant
(couvrant les deux `<Route>` de premier niveau), plutôt que d'en poser un
par route individuelle — plus simple et suffisant (React affiche le
fallback pour n'importe quel enfant suspendu).

- [ ] **Step 4: Run `routes.test.tsx`, convertir les assertions synchrones**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: échecs sur les sites qui font `screen.getByText(...)` sans
`await`/`find` juste après une navigation (au moins les 2 sites déjà
identifiés en spec §4.1, lignes 257 et 265 : `screen.getByText("map-editor-77")`
→ `await screen.findByText("map-editor-77")`). Corriger site par site,
relancer jusqu'à PASS complet. **Ne pas se fier au seul grep de la spec** :
l'exécution réelle du fichier (418 lignes, 20+ assertions) est la seule
preuve fiable qu'aucun autre site synchrone ne subsiste.

- [ ] **Step 5: Typecheck**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Mesurer le bundle après correctif**

Run: `cd shell && rm -rf dist dist-export && npm run build 2>&1 | tail -30`
Noter la nouvelle taille du chunk d'entrée et le nombre de nouveaux chunks
de route apparus (un par page, nommés `PageName-<hash>.js`). Expected :
chunk d'entrée significativement réduit (l'essentiel du run-time React
Router/React Query/UI kit partagé reste dedans, mais chaque page lourde —
`MapEditorPage`, `SqlLabPage`, `PipelineBuilderPage`, les 6 pages Admin —
part dans son propre chunk).

- [ ] **Step 7: Run the full Vitest + Playwright suites**

Run: `cd shell && npm run test && npm run e2e`
Expected: PASS complet — le découpage par route ne doit changer aucun
comportement observable, seulement le découpage physique des fichiers
livrés.

- [ ] **Step 8: Commit**

```bash
git add shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx shell/src/shell/AppLayout.tsx
git commit -m "perf(shell): découpage par route de routes.tsx via lazy()+Suspense (GAP-68)"
```

---

### Task 9: chunks de vendeur + filet de non-régression sur la taille du bundle

**Files:**
- Modify: `shell/vite.config.ts`
- Create: `shell/scripts/check-bundle-size.mjs`
- Create: `shell/.bundle-size-threshold`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold`
  (miroir exact de `node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold`,
  déjà en CI ligne 114 de `ci.yml`).

- [ ] **Step 1: Activer le manifeste Vite**

Dans `shell/vite.config.ts`, ajouter à la config `build` (créer la clé si
absente) :
```ts
build: {
  manifest: true,
  rollupOptions: {
    output: {
      manualChunks(id) {
        if (id.includes("node_modules")) {
          if (id.includes("maplibre-gl") || id.includes("@deck.gl") || id.includes("@loaders.gl")) {
            return "vendor-map";
          }
          if (id.includes("echarts")) return "vendor-echarts"; // déjà scindé par lazy(), regroupe ses deps transitives
          if (id.includes("@xyflow")) return "vendor-flow";
          if (id.includes("lit") || id.includes("@lit")) return "vendor-lit";
        }
      },
    },
  },
},
```
Vérifier après un build que ce `manualChunks` ne casse pas l'ordre de
chargement (aucune erreur runtime au chargement d'une page qui consomme
une de ces bibliothèques — vérifier au moins une page « Cartes » en local
via `npm run preview` après build, pas seulement via les tests Vitest qui
ne passent jamais par le vrai bundler de production).

- [ ] **Step 2: Write the failing script test — mesurer AVANT d'écrire le seuil**

Créer `shell/scripts/check-bundle-size.mjs` :
```js
#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";

function initialChunkFiles(manifest, entryKey) {
  const seen = new Set();
  const files = new Set();
  function walk(key) {
    if (seen.has(key)) return;
    seen.add(key);
    const entry = manifest[key];
    if (!entry) return;
    files.add(entry.file);
    for (const css of entry.css ?? []) files.add(css);
    for (const imp of entry.imports ?? []) walk(imp);
    // volontairement : PAS entry.dynamicImports — c'est tout l'intérêt du
    // découpage par route (Task 8), un chunk atteint seulement par un
    // import dynamique ne doit jamais compter dans la charge initiale.
  }
  walk(entryKey);
  return files;
}

function main(manifestPath, thresholdPath) {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const distDir = dirname(dirname(manifestPath)); // dist/.vite/manifest.json -> dist/
  const entryKey = Object.keys(manifest).find((k) => manifest[k].isEntry);
  if (!entryKey) {
    console.error("Aucune entrée trouvée dans le manifeste Vite.");
    process.exit(1);
  }
  const files = initialChunkFiles(manifest, entryKey);
  let totalBytes = 0;
  for (const file of files) {
    totalBytes += readFileSync(join(distDir, file)).length;
  }
  const totalKb = totalBytes / 1024;
  const thresholdKb = Number(readFileSync(thresholdPath, "utf-8").trim());
  console.log(`Charge JS/CSS initiale mesurée : ${totalKb.toFixed(1)} Ko (seuil : ${thresholdKb} Ko)`);
  if (totalKb > thresholdKb) {
    console.error(`ÉCHEC : charge initiale ${totalKb.toFixed(1)} Ko > seuil ${thresholdKb} Ko`);
    process.exit(1);
  }
}

main(process.argv[2], process.argv[3]);
```

- [ ] **Step 3: Mesurer et fixer le seuil**

Run:
```bash
cd shell && rm -rf dist dist-export && npm run build
echo "999999" > .bundle-size-threshold   # seuil provisoire large, pour observer la mesure réelle sans échouer
node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```
Noter la valeur affichée (« Charge JS/CSS initiale mesurée : X Ko »).
Remplacer `.bundle-size-threshold` par cette valeur **arrondie à la
dizaine de Ko supérieure** (patron non régressif identique à
`.coverage-threshold` : le seuil committé doit être atteignable
aujourd'hui, jamais aspirationnel).

- [ ] **Step 4: Falsifier — confirmer que le script échoue sur un seuil trop bas**

Run: `echo "1" > .bundle-size-threshold && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold; echo "exit=$?"`
Expected: `exit=1`, message d'échec explicite. Remettre le seuil réel de
Step 3.

- [ ] **Step 5: Wire into CI**

Dans `.github/workflows/ci.yml`, après la ligne `- run: npm run build`
(actuellement la dernière étape du job `shell`) :
```yaml
      - run: npm run build
      - run: node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```

- [ ] **Step 6: Run the full build + check locally one more time**

Run: `cd shell && rm -rf dist dist-export && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold`
Expected: PASS, exit 0.

- [ ] **Step 7: Commit**

```bash
git add shell/vite.config.ts shell/scripts/check-bundle-size.mjs shell/.bundle-size-threshold .github/workflows/ci.yml
git commit -m "perf(shell): vendor chunks (maplibre/deck.gl/echarts/xyflow/lit) + filet de non-régression sur la taille du bundle (GAP-68)"
```

---

### Task 10: vérification finale

**Files:** aucun — vérification pure.

- [ ] **Step 1: Suite shell complète**

Run: `cd shell && rm -rf dist dist-export && npm run lint && npm run format:check && npm run test -- --coverage`
Expected: PASS. Vérifier la couverture contre `.coverage-threshold` (88) —
non censée régresser (aucune ligne de production non testée n'a été
ajoutée en net ; du code a plutôt été retiré de la surface non couverte
via Task 6/7/8's tests).

- [ ] **Step 2: Playwright complet**

Run: `cd shell && npx playwright install --with-deps chromium && npm run e2e`
Expected: PASS complet.

- [ ] **Step 3: Build + filet de taille**

Run: `cd shell && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold`
Expected: PASS.

- [ ] **Step 4: Suite core complète**

Run: `cd core && uv run ruff check . && uv run ruff format --check . && uv run pytest`
Expected: PASS (hors les 2 échecs intermittents déjà documentés dans
`CLAUDE.md` — `test_scope_preserves_original_sql_error` et
`test_every_compose_substitution_is_documented`, à ne pas imputer à ce
plan sans vérification indépendante).

- [ ] **Step 5: `lint-imports` + `mypy --strict`**

Run: `cd core && uv run lint-imports && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles`
Expected: PASS (ce plan ne touche à aucun de ces modules — un échec ici
serait sans rapport avec SP-60, à investiguer séparément avant de
conclure).

- [ ] **Step 6: Confirmer l'absence de diff OpenAPI**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && git diff --exit-code -- core/openapi.json`
Expected: diff vide (aucune route/modèle de production n'a changé de
forme dans ce plan — cf. Global Constraints).

- [ ] **Step 7: `pre-commit run --all-files`**

Run: `cd /home/lenen/projets/geostudio && uvx pre-commit run --all-files`
Expected: PASS.

- [ ] **Step 8: Mise à jour `CLAUDE.md`**

Ajouter une ligne dans `### Livré` : SP-60 clos, GAP-68/GAP-69 fermés,
mentionner le fait marquant du plan (4 boucles de sondage corrigées au
lieu des 2 nommées par le GAP d'origine ; adoption de `mockCollection()`
étendue à 9 fichiers au-delà de son unique consommateur SP-43). Ne pas
committer cette mise à jour dans le même commit que du code — commit dédié
`docs(claude): clôture SP-60`.
