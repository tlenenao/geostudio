# Backlog Plan B (L4 reliquats backend, L5 shell UX/copilote/fonctionnalités) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les reliquats codables de 24 entrées du backlog (REV-274/276/277/278/279/280/281/282/283/288/289 pour L4 ; REV-239/254/265/251/284/285/286/287/293/183/184/102/104 pour L5) : correctifs backend, UX/accessibilité du shell, copilote, et trois fonctionnalités v1 (NL→CEL, géocodage BAN, animation temporelle).

**Architecture:** Lots indépendants à correctifs ciblés, chacun en TDD ; trois sous-lots de fonctionnalités (L5b) exécutables séparément. Spec : `docs/superpowers/specs/2026-10-03-backlog-lots-l4-l5-design.md`. Les écarts spec/code trouvés à la rédaction sont consignés en fin de chaque lot (« Notes de vérification ») : **le plan prime sur la spec** là où ils divergent.

**Tech Stack:** Python/FastAPI (`core/`, pytest, postgis-test, ruff, mypy --strict, import-linter, Alembic), React/TS (`shell/`, vitest, Playwright), Docker Compose, GitHub Actions.

## Global Constraints

- Docs et messages utilisateur en **français** ; code/identifiants en anglais.
- Commits conventionnels, petits, un sujet (sujet en minuscules, ≤ 100 caractères — commitlint), terminés par `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Branche `dev` uniquement ; aucun push ni tag sans demande de Tanguy.
- TDD systématique ; un correctif de filet de test est vérifié par falsification (piège n°10).
- `CORE_TEST_DATABASE_URL` doit pointer un postgis-test réel, sinon les tests `postgis` skippent silencieusement (piège SP-43). Migrations : tester sur base non vide, dans les deux sens ; le conteneur `postgis-test` n'est pas tracké par Alembic.
- Régénérer OpenAPI + types TS dès qu'une route/un modèle change (commande exacte dans CLAUDE.md §Commandes).
- **Marge du bundle shell : 0,4 Ko** (729,6 Ko / seuil 730 Ko, `shell/.bundle-size-threshold`) : toute tâche shell mesure (`node scripts/check-bundle-size.mjs`) ; en cas d'échec, relever le seuil dans le même commit avec avant/après et cause.
- Jumelles de garde à traiter dans le même geste (piège n°14) ; vérifier dans le code, jamais dans le récit (piège n°12).
- Sous-points « rejeu stack réelle » (lot L6) et « décision produit » (lot L1) : **hors périmètre**.
- Ledgers SDD nommés `.superpowers/sdd/backlogB-*`.

## Ordre d'exécution (contraintes entre lots)

1. **L4** puis **L5a** puis **L5b**, puis la tâche CLOSE en dernier ; les trois lots sont indépendants, sauf contraintes ci-dessous.
2. Migrations L4 : **0046** (L4-3) et **0047** (L4-7) ; dernière migration présente à la rédaction : `0045_p24_indexes.py`. L5 ne crée aucune migration. Si une autre branche prend 0046/0047, renuméroter fichier, `down_revision` et tests.
3. L4-3 avant L4-4 ; L4-7 avant L4-8 (schéma avant comportement).
4. L5a-7 avant L5a-8 (même fichier `CopilotChat.tsx`). L5a-1 d'abord (libère des octets de bundle).
5. L5b : chaque sous-lot (183 / 102 / 104) est exécutable seul ; L5b-183 : 1 → 2 → 3 → 4 ; L5b-102 : 1 → 2 → 3 → 4 ; L5b-104 : 1 → 2 → 3.
6. L5a-18 (portes de qualité du lot) et L5b-*-4/-3 (E2E + bundle) closent leurs lots ; la suite E2E complète est rejouée à la tâche CLOSE (piège n°6).

---

## Lot L4 — Reliquats backend

Ce lot ferme les sous-points codables des REV-274, 276 à 283, 288 et 289. Les tâches sont ordonnées par dépendance :
- L4-3 (migration 0046) précède L4-4 ;
- L4-7 (migration 0047) précède L4-8.

Les autres tâches sont indépendantes.

Les deux migrations du lot sont numérotées **0046** et **0047** (dernière migration présente : `core/alembic/versions/0045_p24_indexes.py`). Si un autre lot du plan B prend 0046 ou 0047 avant celui-ci, le contrôleur renumérote ces fichiers, leur `down_revision` et les `command.upgrade(..., "004x")` des tests.

Recettes utilisées par toutes les tâches, à lancer depuis la racine du dépôt :

```bash
# cœur — à définir une fois par shell
pyt() { (cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run pytest "$@" -q --basetemp="$(mktemp -d)"); }
# shell
(cd shell && npx vitest run <fichiers> && npx tsc --noEmit && npm run lint && npm run format:check)
```

Marge du bundle initial : 0,4 Ko (729,6 / 730 Ko). Toute tâche qui ajoute du code au bundle initial a une étape de mesure explicite :

```bash
(cd shell && rm -rf dist dist-export && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold)
```

En cas de dépassement, la même tâche relève `shell/.bundle-size-threshold` du plus petit entier suffisant. Elle justifie ce relèvement dans le message de commit.

### Task L4-1: sonde d'état d'instance — seuil « bloqué » configurable et CDC « non configuré » (REV-274c)

**Files:**
- Modify: `core/app/instance/routes.py:1-3` (imports), `:27` (constante), `:77-82` (sonde `cdc`) et `:84-101` (sonde `jobs`)
- Modify: `docker-compose.yml:341` (service `core`, à côté de `CORE_EXPORT_ITEMS_MAX`)
- Modify: `.env.example:257`
- Modify: `shell/src/api/types.ts:211`
- Modify: `shell/src/pages/AdminInfrastructurePage.tsx:22-29` et `:92`
- Modify: `shell/src/i18n/catalog.fr.ts:391`
- Modify: `shell/src/pages/AdminInfrastructurePage.test.tsx`
- Create: `core/tests/test_instance_status_pg.py`

**Interfaces:**
- Produces : `GET /v1/instance/status`.
  - `cdc` vaut `{"ok": true, "configured": false}` quand le slot de réplication est absent, `{"ok": true, "configured": true, "slotActive": bool}` sinon.
  - `jobs.stalled` compte les jobs `doing` sans événement depuis `CORE_STALLED_JOB_MINUTES` minutes (défaut 60).
  - La route renvoie un `dict` non typé : pas de régénération OpenAPI.
- Produces (shell) : `InstanceStatus.cdc.configured?: boolean` ; `Probe` gagne la prop `notConfigured?: boolean`.
- Consumes : rien d'un autre lot.

**Correction de la spec :** la spec demande `from app.cdc.consumer import SLOT_NAME`. Le contrat de couches l'interdit : `instance` ne peut pas importer `cdc`, et `lint-imports` le refuserait. La constante `_CDC_SLOT` reste dans `instance`. Un test d'égalité avec `app.cdc.consumer.SLOT_NAME` empêche la dérive (un test peut importer les deux modules).

- [ ] **Step 1 : tests cœur échouants** — créer `core/tests/test_instance_status_pg.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-274c : seuil « job bloqué » configurable, slot CDC absent = non configuré."""

from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cdc.consumer import SLOT_NAME
from app.instance import routes


def test_slot_name_matches_the_cdc_consumer():
    # instance ne peut pas importer cdc (contrat de couches) : la constante
    # est dupliquée, ce test empêche qu'elle dérive.
    assert routes._CDC_SLOT == SLOT_NAME


@pytest.fixture
def status(monkeypatch, pg_engine_with_procrastinate_schema):
    engine = pg_engine_with_procrastinate_schema
    monkeypatch.setattr(routes, "require_privilege", lambda *a, **k: None)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        job_id = conn.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args, status) "
                "VALUES ('q', 't', NULL, '{}', 'doing') RETURNING id"
            )
        ).scalar_one()
        # Le trigger procrastinate n'insère un événement que pour 'todo' :
        # on pose à la main un « started » vieux de 30 minutes.
        conn.execute(
            text(
                "INSERT INTO procrastinate_events (job_id, type, at) "
                "VALUES (:j, 'started', now() - interval '30 minutes')"
            ),
            {"j": job_id},
        )

    def call() -> dict:
        with Session(engine) as session:
            return routes.get_instance_status(user=SimpleNamespace(), session=session, s3=None)

    yield call
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))


def test_stalled_threshold_comes_from_env(status, monkeypatch):
    monkeypatch.setenv("CORE_STALLED_JOB_MINUTES", "10")
    assert status()["jobs"]["stalled"] == 1
    monkeypatch.delenv("CORE_STALLED_JOB_MINUTES")
    assert status()["jobs"]["stalled"] == 0  # défaut 60 min


def test_stalled_threshold_ignores_invalid_values(status, monkeypatch):
    for bad in ("abc", "0", "-5"):
        monkeypatch.setenv("CORE_STALLED_JOB_MINUTES", bad)
        assert status()["jobs"]["stalled"] == 0


def test_cdc_probe_reports_absent_slot_as_not_configured(
    status, pg_engine_with_procrastinate_schema
):
    with pg_engine_with_procrastinate_schema.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_replication_slots WHERE slot_name = :n"), {"n": SLOT_NAME}
        ).first()
    cdc = status()["cdc"]
    assert cdc["ok"] is True
    if exists is None:
        assert cdc == {"ok": True, "configured": False}
    else:  # base de test où un slot traîne : la forme « configurée » est complète
        assert cdc["configured"] is True and isinstance(cdc["slotActive"], bool)
```

- [ ] **Step 2 : vérifier l'échec**
  - Commande : `pyt tests/test_instance_status_pg.py`
  - Attendu : FAIL sur `test_stalled_threshold_comes_from_env`, car le seuil est figé à 1 h et `stalled == 0` alors que 1 est attendu.
  - Attendu : FAIL sur `test_cdc_probe_reports_absent_slot_as_not_configured`, car `{"ok": True, "slotActive": False}` n'a pas de clé `configured`.
  - `test_slot_name_matches_the_cdc_consumer` passe déjà.

- [ ] **Step 3 : implémentation** dans `core/app/instance/routes.py`.

Remplacer la ligne 27 par :

```python
_CDC_SLOT = "geostudio_cdc_slot"  # = app.cdc.consumer.SLOT_NAME (import interdit, cf. test)
_STALLED_DEFAULT_MINUTES = 60


def _stalled_minutes() -> int:
    try:
        value = int(os.environ.get("CORE_STALLED_JOB_MINUTES", ""))
    except ValueError:
        return _STALLED_DEFAULT_MINUTES
    return value if value > 0 else _STALLED_DEFAULT_MINUTES
```

Remplacer la sonde `cdc` (l.77-82) par :

```python
    def cdc() -> dict:
        row = session.execute(
            text("SELECT active FROM pg_replication_slots WHERE slot_name = :n"),
            {"n": _CDC_SLOT},
        ).first()
        if row is None:  # worker CDC volontairement absent : pas une panne
            return {"configured": False}
        return {"configured": True, "slotActive": bool(row[0])}
```

Dans la sonde `jobs`, remplacer la requête `stalled` (l.91-97) par :

```python
        stalled = session.execute(
            text(
                "SELECT COUNT(*) FROM procrastinate_jobs j WHERE j.status = 'doing' "
                "AND NOT EXISTS (SELECT 1 FROM procrastinate_events e WHERE e.job_id = j.id "
                "AND e.at > now() - make_interval(mins => :m))"
            ),
            {"m": _stalled_minutes()},
        ).scalar_one()
```

- [ ] **Step 4 : câblage compose et documentation**

Dans `docker-compose.yml`, service `core`, juste après la ligne 341 (`CORE_EXPORT_ITEMS_MAX: ${CORE_EXPORT_ITEMS_MAX:-100000}`), ajouter avec la même indentation :

```yaml
      CORE_STALLED_JOB_MINUTES: ${CORE_STALLED_JOB_MINUTES:-60}
```

Dans `.env.example`, juste après la ligne 257 (`#CORE_EXPORT_ITEMS_MAX=100000`), ajouter :

```bash
# Seuil (minutes) au-delà duquel GET /v1/instance/status compte comme
# « bloqué » un job `doing` sans événement (REV-274c). Défaut 60 ; à relever
# si des jobs légitimes (gros import, pipeline) tournent plus longtemps.
#CORE_STALLED_JOB_MINUTES=60
```

- [ ] **Step 5 : vérifier le succès**
  - Commande : `pyt tests/test_instance_status_pg.py tests/test_admin_tools_routes.py tests/test_deployability.py`
  - Attendu : PASS. `test_deployability.py` contrôle que toute substitution du compose est documentée dans `.env.example`.

- [ ] **Step 6 : test shell échouant** — dans `shell/src/pages/AdminInfrastructurePage.test.tsx`, ajouter à la fin :

```tsx
test("affiche « non configuré » quand le slot CDC est absent (REV-274c)", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
    http.get("https://core.test/v1/instance/status", () =>
      HttpResponse.json({ ...statusBody(false), cdc: { ok: true, configured: false } }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("CDC : non configuré")).toBeInTheDocument();
});
```

Lancer `(cd shell && npx vitest run src/pages/AdminInfrastructurePage.test.tsx)`.
- Attendu : FAIL, car la page affiche « CDC : en échec ».

- [ ] **Step 7 : implémentation shell**

`shell/src/api/types.ts:211` devient :

```ts
  cdc: ProbeStatus & { slotActive?: boolean; configured?: boolean };
```

Dans `shell/src/i18n/catalog.fr.ts`, après la ligne 391 (`"infrastructure.statusDown": "en échec",`), ajouter :

```ts
  "infrastructure.statusNotConfigured": "non configuré",
```

Dans `shell/src/pages/AdminInfrastructurePage.tsx`, remplacer `Probe` (l.22-29) par :

```tsx
function Probe({
  label,
  ok,
  detail,
  notConfigured,
}: {
  label: string;
  ok: boolean;
  detail?: string;
  notConfigured?: boolean;
}) {
  const state = notConfigured
    ? t("infrastructure.statusNotConfigured")
    : ok
      ? t("infrastructure.statusOk")
      : t("infrastructure.statusDown");
  return (
    <li>
      {label} : {state}
      {detail ? ` (${detail})` : ""}
    </li>
  );
}
```

Et la ligne 92 par :

```tsx
                    <Probe
                      label="CDC"
                      ok={status.cdc.ok && status.cdc.slotActive === true}
                      notConfigured={status.cdc.ok && status.cdc.configured === false}
                    />
```

- [ ] **Step 8 : vérifier le succès**
  - Commande : `(cd shell && npx vitest run src/pages/AdminInfrastructurePage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check)`
  - Attendu : PASS. `AdminInfrastructurePage` est chargée en `lazy()`, donc le bundle initial ne grossit que de la clé i18n (une trentaine d'octets). La mesure du bundle se fait à L4-5.

- [ ] **Step 9 : commit**

```bash
git add core/app/instance/routes.py core/tests/test_instance_status_pg.py docker-compose.yml .env.example shell/src/api/types.ts shell/src/pages/AdminInfrastructurePage.tsx shell/src/pages/AdminInfrastructurePage.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "fix(core): seuil de job bloqué configurable et cdc non configuré distinct (rev-274c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-2: ports hôte d'outillage liés à 127.0.0.1, entrypoint traefik de prod hors tailnet (REV-274d, REV-281g)

**Files:**
- Modify: `docker-compose.yml:139` (martin), `:202` (titiler), `:775-777` (otel-lgtm)
- Modify: `docker-compose.prod.yml:327-328` (commande `traefik`)
- Modify: `core/tests/test_deployability.py` (deux tests ajoutés après `test_prod_traefik_command_also_enables_file_provider`, ~l.1537)

**Interfaces:** Produces : en compose de base, les ports hôte de Martin (3010), TiTiler (8000), Grafana (3001) et OTLP (4317/4318) ne sont plus joignables depuis le réseau. En prod, l'entrypoint `traefik` (`:8080`, `/ping`) écoute sur la boucle locale du conteneur. Le healthcheck Traefik passe par cette boucle et continue de fonctionner. Consumes : rien.

**Vérification empirique déjà faite :** sur `traefik:v3.7.13`, `--entrypoints.traefik.address=127.0.0.1:8080` démarre et `traefik healthcheck --ping` répond OK dans le conteneur.

**Audit des autres ports :** keycloak, minio et traefik `:80` restent publiés. Ils servent le parcours d'auth et l'accès navigateur en dev, et ne sont pas des outils d'observabilité.

- [ ] **Step 1 : tests échouants** — dans `core/tests/test_deployability.py`, après `test_prod_traefik_command_also_enables_file_provider`, ajouter :

```python
def test_dev_tooling_host_ports_bind_loopback_only():
    """REV-274d : Grafana (Viewer anonyme), OTLP, Martin et TiTiler ne
    doivent pas être joignables depuis le réseau sur un poste de dev."""
    svc = services(BASE)
    for name in ("martin", "titiler", "otel-lgtm"):
        for port in svc[name]["ports"]:
            assert str(port).startswith("127.0.0.1:"), f"{name}: port {port!r} exposé sur 0.0.0.0"


def test_prod_traefik_api_entrypoint_is_loopback_only():
    """REV-281g : l'entrypoint `traefik` (:8080, /ping) partage le réseau
    tailscale en prod — il doit écouter sur la boucle locale seulement."""
    assert "--entrypoints.traefik.address=127.0.0.1:8080" in services(PROD)["traefik"]["command"]
```

Lancer `pyt tests/test_deployability.py -k "loopback"`.
- Attendu : FAIL sur les deux tests (`"3010:3000"` exposé sur 0.0.0.0 ; option absente).

- [ ] **Step 2 : implémentation**

Dans `docker-compose.yml` :

| Ligne | Avant | Après |
|---|---|---|
| 139 | `- "3010:3000"` | `- "127.0.0.1:3010:3000"` |
| 202 | `- "8000:8000"` | `- "127.0.0.1:8000:8000"` |
| 775 | `- "${GRAFANA_HOST_PORT:-3001}:3000"` | `- "127.0.0.1:${GRAFANA_HOST_PORT:-3001}:3000"` |
| 776 | `- "4317:4317"` | `- "127.0.0.1:4317:4317"` |
| 777 | `- "4318:4318"` | `- "127.0.0.1:4318:4318"` |

Dans `docker-compose.prod.yml`, après la ligne 328 (`- --entrypoints.web.address=:80`), ajouter avec la même indentation :

```yaml
      - --entrypoints.traefik.address=127.0.0.1:8080
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_deployability.py`
  - Attendu : PASS.
  - Puis : `docker compose -f docker-compose.yml config --format json | python3 -c "import json,sys; s=json.load(sys.stdin)['services']; print([p.get('host_ip') for n in ('martin','titiler','otel-lgtm') for p in s[n]['ports']])"`
  - Attendu : `['127.0.0.1', '127.0.0.1', '127.0.0.1', '127.0.0.1', '127.0.0.1']`. Si le profil `observability` masque otel-lgtm de la sortie, ajouter `--profile observability`.

- [ ] **Step 4 : commit**

```bash
git add docker-compose.yml docker-compose.prod.yml core/tests/test_deployability.py
git commit -m "fix(deploy): ports d'outillage sur 127.0.0.1, entrypoint traefik hors tailnet (rev-274d, rev-281g)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-3: migration 0046 — unicité `(tenant_id, type, url)` des sources de moissonnage et compteur d'échecs (REV-276c, d — schéma)

**Files:**
- Create: `core/alembic/versions/0046_harvest_source_unique_and_backoff.py`
- Modify: `core/app/harvest/models.py:15-34` (classe `HarvestSource`)
- Modify: `core/tests/test_migrations_p09.py` (deux tests ajoutés à la fin)

**Interfaces:**
- Produces : l'index unique `uq_harvest_sources_tenant_type_url` sur `harvest_sources (tenant_id, type, url)`.
- Produces : la colonne `harvest_sources.consecutive_failures INTEGER NOT NULL DEFAULT 0`, exposée côté modèle par `HarvestSource.consecutive_failures: int`.
- Consommé par L4-4 : 409 sur `IntegrityError`, backoff.

**Décision (correction de la spec) :** la spec propose une migration qui « dédoublonne explicitement ou échoue proprement » après normalisation d'URL. La migration **ne réécrit aucune URL stockée**, pour deux raisons :
- le slash final est porteur de sens pour la résolution `urljoin` des liens STAC ;
- les `external_id` déjà moissonnés en dépendent.

La migration échoue donc proprement (`RuntimeError` listant les ids) sur les seuls doublons **exacts**. Alembic est transactionnel sur Postgres : en cas d'échec, la base reste en 0045. La normalisation (slash final, casse de l'hôte) est faite à la comparaison applicative par L4-4.

- [ ] **Step 1 : tests de migration échouants** — à la fin de `core/tests/test_migrations_p09.py`, ajouter :

```python
def _seed_harvest(conn, rows) -> None:
    for source_id, url in rows:
        conn.execute(
            sa.text(
                "INSERT INTO harvest_sources (id, tenant_id, owner_id, type, url, created_at, "
                "updated_at) VALUES (:id, 't1', 'u1', 'stac', :url, now(), now())"
            ),
            {"id": source_id, "url": url},
        )


def test_0046_adds_unique_source_index_and_failure_counter_both_ways(throwaway_database_url):
    """REV-276c/d : base non vide, deux sources qui ne diffèrent que par le
    slash final (pas des doublons exacts : la migration ne réécrit pas les URL)."""
    url = throwaway_database_url
    command.upgrade(_cfg(), "0045")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        _seed_harvest(conn, [("h1", "https://a.example/stac"), ("h2", "https://a.example/stac/")])
    eng.dispose()

    command.upgrade(_cfg(), "0046")
    assert _scalar(url, "SELECT sum(consecutive_failures) FROM harvest_sources") == 0
    url_h2 = _scalar(url, "SELECT url FROM harvest_sources WHERE id='h2'")
    assert url_h2 == "https://a.example/stac/"
    eng = sa.create_engine(url)
    with pytest.raises(sa.exc.IntegrityError), eng.begin() as conn:
        _seed_harvest(conn, [("h3", "https://a.example/stac")])
    eng.dispose()

    command.downgrade(_cfg(), "0045")
    assert _scalar(url, "SELECT count(*) FROM harvest_sources") == 2
    assert (
        _scalar(
            url,
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='harvest_sources' AND column_name='consecutive_failures'",
        )
        == 0
    )
    assert (
        _scalar(
            url,
            "SELECT count(*) FROM pg_indexes WHERE indexname='uq_harvest_sources_tenant_type_url'",
        )
        == 0
    )


def test_0046_fails_cleanly_on_exact_duplicates(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0045")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        _seed_harvest(conn, [("h1", "https://a.example/stac"), ("h2", "https://a.example/stac")])
    eng.dispose()

    with pytest.raises(RuntimeError, match="h1,h2"):
        command.upgrade(_cfg(), "0046")
    assert _scalar(url, "SELECT version_num FROM alembic_version") == "0045"
    assert _scalar(url, "SELECT count(*) FROM harvest_sources") == 2
```

- [ ] **Step 2 : vérifier l'échec**
  - Commande : `pyt tests/test_migrations_p09.py -k 0046`
  - Attendu : FAIL avec `CommandError`/`KeyError` sur la révision `0046`, qui n'existe pas encore.

- [ ] **Step 3 : migration** — créer `core/alembic/versions/0046_harvest_source_unique_and_backoff.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Unicité (tenant_id, type, url) des sources de moissonnage + compteur d'échecs (REV-276c/d)

Les URL stockées ne sont PAS réécrites (normalisation) : le slash final est
porteur de sens pour la résolution urljoin des liens STAC et les external_id
déjà moissonnés en dépendent. La normalisation (slash final, casse de l'hôte)
est faite à la comparaison applicative (app.harvest.repository.
find_duplicate_source). Seuls les doublons EXACTS bloquent cet index : la
migration échoue alors proprement en les listant (transactionnelle, la base
reste en 0045) ; supprimer ou corriger les sources listées, puis relancer.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_INDEX = "uq_harvest_sources_tenant_type_url"


def upgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT tenant_id, type, url, string_agg(id, ',' ORDER BY id) "
                "FROM harvest_sources GROUP BY tenant_id, type, url HAVING count(*) > 1"
            )
        )
        .all()
    )
    if duplicates:
        listing = "; ".join(f"{t}/{ty} {u}: {ids}" for t, ty, u, ids in duplicates)
        raise RuntimeError(
            "0046 : sources de moissonnage en double (tenant/type url : ids) — "
            f"supprimer les doublons puis relancer : {listing}"
        )
    op.create_index(_INDEX, "harvest_sources", ["tenant_id", "type", "url"], unique=True)
    op.add_column(
        "harvest_sources",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("harvest_sources", "consecutive_failures")
    op.drop_index(_INDEX, table_name="harvest_sources")
```

- [ ] **Step 4 : modèle** — dans `core/app/harvest/models.py`, classe `HarvestSource` :

Insérer après `__tablename__ = "harvest_sources"` (l.16) :

```python
    # Index(unique=True), pas UniqueConstraint : même forme que la migration
    # 0046 (op.create_index), cf. HarvestRecord ci-dessous.
    __table_args__ = (
        Index("uq_harvest_sources_tenant_type_url", "tenant_id", "type", "url", unique=True),
    )
```

Et après `last_error` (l.32) :

```python
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
```

- [ ] **Step 5 : base de test partagée** — `postgis-test` n'est pas suivi par Alembic (cf. CLAUDE.md). Lancer :

```bash
docker exec postgis-test psql -U gis -d gis_test -c "ALTER TABLE harvest_sources ADD COLUMN IF NOT EXISTS consecutive_failures integer NOT NULL DEFAULT 0"
docker exec postgis-test psql -U gis -d gis_test -c "CREATE UNIQUE INDEX IF NOT EXISTS uq_harvest_sources_tenant_type_url ON harvest_sources (tenant_id, type, url)"
```

Attendu : `ALTER TABLE` puis `CREATE INDEX`. La seconde commande échoue en cas de doublon résiduel laissé par un test. Dans ce cas, lancer `TRUNCATE harvest_sources CASCADE` puis la rejouer.

- [ ] **Step 6 : vérifier le succès et l'absence de régression**
  - Commande :
    ```bash
    pyt tests/test_migrations_p09.py tests/test_model_alembic_parity.py tests/test_harvest_repository.py tests/test_harvest_routes.py tests/test_harvest_service.py tests/test_compliance_purge.py tests/test_mcp_tools_explain_dataset_arcgis.py tests/test_security_service.py tests/test_mcp_tools_run_analytics_query_arcgis.py tests/test_security_csp_hosts.py tests/test_create_dataset_arcgis.py tests/test_mcp_tools_dataset_create.py tests/test_ratelimit.py
    ```
  - Attendu : PASS.
  - `test_migrations_p09.py::test_destructive_downgrades_are_refused_while_rows_exist` remonte jusqu'à `head`, donc à travers 0046 : ses données ne contiennent aucune source.
  - Toutes les suites listées créent des sources de moissonnage. Une mesure faite pendant la rédaction (suite `test_harvest_*` avec l'index unique, 239 passed) n'a révélé aucun test qui crée deux fois la même URL.

- [ ] **Step 7 : commit**

```bash
git add core/alembic/versions/0046_harvest_source_unique_and_backoff.py core/app/harvest/models.py core/tests/test_migrations_p09.py
git commit -m "feat(core): migration 0046, unicité des sources de moissonnage et compteur d'échecs (rev-276)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-4: moissonnage — doublons normalisés, 409 sur course, backoff exponentiel (REV-276c, d — comportement)

**Files:**
- Modify: `core/app/harvest/schemas.py:1-16` (`_check_http_url`, nouvelle `normalize_source_url`)
- Modify: `core/app/harvest/repository.py:1-10` (import), `:72-89` (`find_duplicate_source`), `:276-310` (`list_due_sources`)
- Modify: `core/app/harvest/routes.py:1-6` (import), `create_source` (l.137-166) et `patch_source` (l.306-334)
- Modify: `core/app/harvest/service.py` (les trois écritures `source.last_status` de `harvest_source`, l.~74, ~133 et ~138)
- Modify: `core/tests/test_harvest_repository.py`, `core/tests/test_harvest_routes.py`, `core/tests/test_harvest_service.py`

**Interfaces:**
- Consumes (L4-3) : `HarvestSource.consecutive_failures` et l'index unique.
- Produces :
  - `app.harvest.schemas.normalize_source_url(url: str) -> str`, la clé de comparaison : hôte en minuscules, slash final retiré, userinfo et port conservés ;
  - `POST`/`PATCH /v1/harvest/sources` stockent l'hôte en minuscules et renvoient 409 `"harvest source already exists"` sur une variante normalisée **ou** sur une course qui atteint l'index unique ;
  - `list_due_sources` espace les relances d'une source en échec par `interval × 2^n`, plafonné à `max(interval, 24 h)`.
- Pas de changement de forme de réponse : pas de régénération OpenAPI.

- [ ] **Step 1 : tests échouants (dépôt)** — à la fin de `core/tests/test_harvest_repository.py`, ajouter :

```python
def test_list_due_backs_off_exponentially_after_failures(session, tenant_and_user):
    """REV-276d : intervalle 15 min, 1 échec → 30 min avant la relance."""
    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    src = _make_source(session, tenant.id, user.id, last_run_at=now - timedelta(minutes=20))
    assert src in repo.list_due_sources(session)
    src.consecutive_failures = 1
    session.flush()
    assert src not in repo.list_due_sources(session)
    src.last_run_at = now - timedelta(minutes=31)
    session.flush()
    assert src in repo.list_due_sources(session)


def test_list_due_backoff_is_capped_at_one_day(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(UTC)
    src = _make_source(
        session,
        tenant.id,
        user.id,
        consecutive_failures=50,
        last_run_at=now - timedelta(hours=24, minutes=1),
    )
    assert src in repo.list_due_sources(session)


def test_find_duplicate_source_compares_normalized_urls(session, tenant_and_user):
    """REV-276c : slash final et casse du schéma/hôte ne font pas une autre source."""
    tenant, user = tenant_and_user
    src = repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://stac.example/api/",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )

    def dup(url, **kw):
        return repo.find_duplicate_source(
            session, tenant_id=tenant.id, type="stac", url=url, **kw
        )

    assert dup("HTTPS://STAC.Example/api") is src
    assert dup("https://stac.example/API") is None  # le chemin reste sensible à la casse
    assert dup("https://stac.example/api", exclude_id=src.id) is None
```

- [ ] **Step 2 : tests échouants (routes et service)**

À la fin de `core/tests/test_harvest_routes.py`, ajouter :

```python
def test_duplicate_detection_normalizes_url(env):
    """REV-276c : hôte stocké en minuscules, variante slash final/casse → 409."""
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post(
        "/v1/harvest/sources",
        json={**SOURCE_BODY, "url": "https://STAC.Example.com/collections"},
    )
    assert created.status_code == 201
    assert created.json()["url"] == "https://stac.example.com/collections"
    variant = {**SOURCE_BODY, "url": "HTTPS://stac.example.com/collections/"}
    assert client.post("/v1/harvest/sources", json=variant).status_code == 409


def test_concurrent_duplicate_hits_the_unique_index_as_409(env, monkeypatch):
    """REV-276c : la vérification applicative est contournée (course) → l'index
    unique lève IntegrityError, transformée en 409 (jamais 500)."""
    from app.harvest import repository as harvest_repo

    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.post("/v1/harvest/sources", json=SOURCE_BODY).status_code == 201
    other = client.post("/v1/harvest/sources", json={**SOURCE_BODY, "url": "https://b.example"})
    monkeypatch.setattr(harvest_repo, "find_duplicate_source", lambda *a, **k: None)
    r = client.post("/v1/harvest/sources", json=SOURCE_BODY)
    assert r.status_code == 409 and r.json()["detail"] == "harvest source already exists"
    r = client.patch(
        f"/v1/harvest/sources/{other.json()['id']}", json={"url": SOURCE_BODY["url"]}
    )
    assert r.status_code == 409
```

À la fin de `core/tests/test_harvest_service.py`, ajouter :

```python
def test_consecutive_failures_count_up_and_reset_on_success(
    session, tenant_and_user, monkeypatch
):
    """REV-276d : compteur d'échecs consécutifs alimentant le backoff."""
    tenant, user = tenant_and_user

    def _raise(t):
        connector = Mock()
        connector.fetch = Mock(side_effect=RuntimeError("boom"))
        return connector

    monkeypatch.setattr(service, "get_connector", _raise)
    source = harvest_repo.create_source(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        type="stac",
        url="https://a",
        mode="reference",
        enabled=True,
        interval_minutes=None,
    )
    service.harvest_source(session, source)
    service.harvest_source(session, source)
    assert source.consecutive_failures == 2
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([]))
    service.harvest_source(session, source)
    assert source.last_status == "ok"
    assert source.consecutive_failures == 0
```

- [ ] **Step 3 : vérifier l'échec**
  - Commande : `pyt tests/test_harvest_repository.py tests/test_harvest_routes.py tests/test_harvest_service.py -k "backoff or backs_off or normaliz or concurrent_duplicate or consecutive_failures"`
  - Attendu : FAIL sur les six tests :
    - les deux tests de backoff (source due malgré l'échec) ;
    - la normalisation (aucun doublon détecté, `None is not src`) ;
    - la route (URL renvoyée telle quelle, puis 201 au lieu de 409) ;
    - la course (`IntegrityError` non attrapée, qui remonte depuis le `TestClient`) ;
    - le service (`None == 2`).

- [ ] **Step 4 : normalisation** — dans `core/app/harvest/schemas.py`, remplacer l'import `from urllib.parse import urlsplit` (l.3) par `from urllib.parse import SplitResult, urlsplit, urlunsplit`.

Remplacer `_check_http_url` (l.8-16) par :

```python
def _with_lower_host(parts: SplitResult) -> SplitResult:
    # urlsplit abaisse déjà le schéma ; l'hôte est insensible à la casse
    # (RFC 3986 §3.2.2), le userinfo et le chemin ne le sont pas.
    userinfo, at, hostport = parts.netloc.rpartition("@")
    return parts._replace(netloc=f"{userinfo}{at}{hostport.lower()}")


def normalize_source_url(url: str) -> str:
    """Clé de comparaison des sources (REV-276c) : hôte en minuscules, slash
    final retiré. Jamais stockée : le slash final compte pour urljoin."""
    parts = _with_lower_host(urlsplit(url.strip()))
    return urlunsplit(parts._replace(path=parts.path.rstrip("/")))


def _check_http_url(value: str | None) -> str | None:
    # j07-004 : validation à l'écriture seulement (ces modèles ne relisent
    # jamais les sources déjà stockées, qui passent par _source_json).
    if value is None:
        return value
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("url must be an http(s) URL")
    return urlunsplit(_with_lower_host(parts))
```

- [ ] **Step 5 : comparaison et backoff dans le dépôt** — dans `core/app/harvest/repository.py`, ajouter aux imports (après `from app.harvest.models import ...`, l.9) :

```python
from app.harvest.schemas import normalize_source_url
```

Remplacer `find_duplicate_source` (l.72-89) par :

```python
def find_duplicate_source(
    session: Session,
    *,
    tenant_id: str,
    type: str,
    url: str,
    exclude_id: str | None = None,
) -> HarvestSource | None:
    # La course entre deux POST simultanés est bornée par l'index unique
    # uq_harvest_sources_tenant_type_url (0046) → 409 dans les routes.
    # ponytail: comparaison normalisée en Python sur les sources du tenant et
    # du type (quelques dizaines) ; colonne normalisée indexée si ça grossit.
    stmt = select(HarvestSource).where(
        HarvestSource.tenant_id == tenant_id, HarvestSource.type == type
    )
    if exclude_id is not None:
        stmt = stmt.where(HarvestSource.id != exclude_id)
    wanted = normalize_source_url(url)
    for source in session.scalars(stmt):
        if normalize_source_url(source.url) == wanted:
            return source
    return None
```

Dans `list_due_sources` (l.276-310), insérer juste avant `def list_due_sources` :

```python
_BACKOFF_CAP = timedelta(hours=24)


def _effective_interval(source: HarvestSource) -> timedelta:
    """REV-276d : intervalle × 2^échecs consécutifs, plafonné à max(intervalle, 24 h)."""
    base = timedelta(minutes=source.interval_minutes)
    failures = source.consecutive_failures or 0
    if failures <= 0:
        return base
    return min(base * 2 ** min(failures, 10), max(base, _BACKOFF_CAP))
```

Puis remplacer la ligne `threshold = last_run_at + timedelta(minutes=source.interval_minutes)` par :

```python
        threshold = last_run_at + _effective_interval(source)
```

- [ ] **Step 6 : 409 sur `IntegrityError`** — dans `core/app/harvest/routes.py`, ajouter après `from fastapi import ...` (l.5) :

```python
from sqlalchemy.exc import IntegrityError
```

Dans `create_source`, remplacer l'appel `source = repo.create_source(...)` (l.146-155) par :

```python
    try:
        source = repo.create_source(
            session,
            tenant_id=user.tenant_id,
            owner_id=user.id,
            type=body.type,
            url=body.url,
            mode=body.mode,
            enabled=body.enabled,
            interval_minutes=body.intervalMinutes,
        )
    except IntegrityError as exc:  # course : l'index unique (0046) a tranché
        session.rollback()
        raise HTTPException(status_code=409, detail="harvest source already exists") from exc
```

Dans `patch_source`, remplacer `repo.update_source(session, source, **fields)` par :

```python
    try:
        repo.update_source(session, source, **fields)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="harvest source already exists") from exc
```

- [ ] **Step 7 : compteur dans le service** — dans `core/app/harvest/service.py`, fonction `harvest_source` :
  - aux deux endroits où `source.last_status = "error"` est posé (bloc `except` de la récupération, l.~74, et bloc `except` après `session.rollback()`, l.~133), ajouter juste après :
    ```python
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
    ```
  - après `source.last_status = "ok"` (l.~138), ajouter :
    ```python
        source.consecutive_failures = 0
    ```

- [ ] **Step 8 : vérifier le succès**
  - Commande : `pyt tests/test_harvest_*.py tests/test_migrations_p09.py`
  - Attendu : PASS.
  - Puis : `(cd core && uv run ruff check app/harvest tests && uv run ruff format --check app/harvest tests && uv run lint-imports)`
  - Attendu : aucun constat. `app.harvest.repository` importe déjà `app.harvest.models`, et `schemas` appartient au même module : contrat inchangé.

- [ ] **Step 9 : commit**

```bash
git add core/app/harvest/schemas.py core/app/harvest/repository.py core/app/harvest/routes.py core/app/harvest/service.py core/tests/test_harvest_repository.py core/tests/test_harvest_routes.py core/tests/test_harvest_service.py
git commit -m "fix(core): doublons de moissonnage normalisés, 409 sur course et backoff exponentiel (rev-276)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-5: page Moissonnage — panneau « enregistrements » d'une source (REV-276b)

**Files:**
- Modify: `shell/src/api/types.ts:571-575` (interface `ItemClient`) et après `HarvestSourcePatchInput` (l.1042-1047)
- Modify: `shell/src/api/domains/extensionsAdminTools.ts:7-30` (imports, `Pick`) et après `updateHarvestSource` (l.~128)
- Modify: `shell/src/api/domains/extensionsAdminTools.hooks.ts` (nouveau hook après `useHarvestSources`, l.85-92)
- Modify: `shell/src/staticExport/StaticItemClient.ts:~214` et `shell/src/desktop/DesktopItemClient.ts:~348` (stubs `unsupported()`)
- Modify: `shell/src/pages/HarvestSourcesAdminPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts:581`
- Modify: `shell/src/pages/HarvestSourcesAdminPage.test.tsx`

**Interfaces:**
- Consumes : `GET /v1/harvest/sources/{id}/records` (forme vérifiée dans `core/app/harvest/routes.py:268-304` : `{total, staleCount, records: [{id, externalId, itemId, collectionId, state, harvestedAt, externalUrl}]}`). La route existe déjà et figure déjà à l'inventaire (`docs/revue/inventaire-fonctionnalites.jsonl:255`). Pas de nouvelle surface et pas de régénération OpenAPI.
- Produces :
  - `ItemClient.listHarvestSourceRecords(id: string): Promise<HarvestSourceRecordsPage>` ;
  - le hook `useHarvestSourceRecords(id: string)`, avec la clé `["harvest-source-records", id]` ;
  - un bouton « Voir les enregistrements » par ligne, visible **aussi en lecture seule** (lecture pure).

**Choix :** `externalUrl` vient du catalogue distant. Il est affiché en texte, jamais en lien, car c'est une URL non fiable dans une page d'admin. Le lien interne pointe vers `/items/:pk` (`shell/src/shell/routes.tsx:270`). Sans `itemId` (copie sans item, ou item supprimé par 0043 `SET NULL`), le panneau affiche l'`externalId` seul.

- [ ] **Step 1 : test échouant** — à la fin de `shell/src/pages/HarvestSourcesAdminPage.test.tsx`, ajouter :

```tsx
test("liste les enregistrements d'une source, avec lien vers l'item, même en lecture seule (REV-276b)", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ readOnly: true })),
    http.get("https://core.test/v1/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://stac.example.com/collections",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: "ok",
            lastError: null,
            recordCount: 2,
            staleCount: 1,
          },
        ],
      }),
    ),
    http.get("https://core.test/v1/harvest/sources/src-1/records", () =>
      HttpResponse.json({
        total: 2,
        staleCount: 1,
        records: [
          {
            id: "r1",
            externalId: "buildings",
            itemId: "item-a",
            collectionId: null,
            state: "ok",
            harvestedAt: "2026-10-01T10:00:00",
            externalUrl: "https://stac.example.com/collections/buildings",
          },
          {
            id: "r2",
            externalId: "roads",
            itemId: null,
            collectionId: null,
            state: "stale",
            harvestedAt: "2026-10-01T10:00:00",
            externalUrl: null,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  const button = await screen.findByRole("button", { name: "Voir les enregistrements" });
  expect(screen.queryByRole("button", { name: "Moissonner maintenant" })).not.toBeInTheDocument();
  await userEvent.click(button);
  const link = await screen.findByRole("link", { name: "buildings" });
  expect(link).toHaveAttribute("href", "/items/item-a");
  expect(screen.getByText("roads")).toBeInTheDocument();
  expect(screen.getByText("obsolète")).toBeInTheDocument();
  expect(button).toHaveAttribute("aria-expanded", "true");
});
```

Lancer `(cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx)`.
- Attendu : FAIL, `Unable to find role="button" and name "Voir les enregistrements"`.

- [ ] **Step 2 : types et client**

`shell/src/api/types.ts`, après le bloc `HarvestSourcePatchInput` (l.1042-1047) :

```ts
export type HarvestSourceRecord = {
  id: string;
  externalId: string;
  itemId: string | null;
  collectionId: string | null;
  state: "ok" | "stale";
  harvestedAt: string | null;
  externalUrl: string | null;
};

export type HarvestSourceRecordsPage = {
  total: number;
  staleCount: number;
  records: HarvestSourceRecord[];
};
```

Dans l'interface `ItemClient`, après `runHarvestSource(id: string): Promise<void>;` (l.575) :

```ts
  listHarvestSourceRecords(id: string): Promise<HarvestSourceRecordsPage>;
```

`shell/src/api/domains/extensionsAdminTools.ts` :
- ajouter `HarvestSourceRecordsPage,` à l'import de types (après `HarvestSourcePatchInput,`, l.9) ;
- ajouter `| "listHarvestSourceRecords"` au `Pick` (après `| "runHarvestSource"`, l.29) ;
- après la méthode `runHarvestSource`, ajouter :

```ts
    async listHarvestSourceRecords(id: string): Promise<HarvestSourceRecordsPage> {
      return request<HarvestSourceRecordsPage>("GET", `/harvest/sources/${id}/records`);
    },
```

Dans `shell/src/staticExport/StaticItemClient.ts` et `shell/src/desktop/DesktopItemClient.ts`, après le stub `runHarvestSource`, ajouter :

```ts
    async listHarvestSourceRecords(..._args: unknown[]) {
      return unsupported();
    },
```

`shell/src/api/domains/extensionsAdminTools.hooks.ts`, après `useHarvestSources` :

```ts
export function useHarvestSourceRecords(id: string) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["harvest-source-records", id],
    queryFn: () => client.listHarvestSourceRecords(id),
  });
}
```

- [ ] **Step 3 : i18n** — dans `shell/src/i18n/catalog.fr.ts`, après `"harvest.recordsStaleMany": "{count} obsolètes",` (l.581), ajouter :

```ts
  "harvest.recordsButton": "Voir les enregistrements",
  "harvest.recordsHeading": "Enregistrements de {url}",
  "harvest.recordsEmpty": "Aucun enregistrement moissonné pour cette source.",
  "harvest.recordsLoadError": "Impossible de charger les enregistrements.",
  "harvest.recordStale": "obsolète",
```

- [ ] **Step 4 : page** — dans `shell/src/pages/HarvestSourcesAdminPage.tsx` :

Imports :
- ajouter `useHarvestSourceRecords,` à l'import de `../api/hooks` (l.3-8) ;
- ajouter `import { Link } from "react-router-dom";` ;
- ajouter `import { Badge } from "../ui/kit/Badge";`.

Avant `export function HarvestSourcesAdminPage()` (l.24), ajouter :

```tsx
function HarvestRecordsPanel({ source }: { source: HarvestSource }) {
  const query = useHarvestSourceRecords(source.id);
  return (
    <section aria-label={t("harvest.recordsHeading", { url: source.url })}>
      <h2 className="mb-2 text-sm font-medium text-ink">
        {t("harvest.recordsHeading", { url: source.url })}
      </h2>
      {query.isLoading && <LoadingState />}
      {query.isError && <Banner variant="danger">{t("harvest.recordsLoadError")}</Banner>}
      {query.data && query.data.records.length === 0 && (
        <p className="text-sm text-ink-2">{t("harvest.recordsEmpty")}</p>
      )}
      {query.data && query.data.records.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {query.data.records.map((record) => (
            <li key={record.id} className="flex flex-wrap items-center gap-2">
              {record.itemId ? (
                <Link to={`/items/${record.itemId}`} className="text-accent hover:underline">
                  {record.externalId}
                </Link>
              ) : (
                <span>{record.externalId}</span>
              )}
              {record.state === "stale" && <Badge variant="warn">{t("harvest.recordStale")}</Badge>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

Dans le composant, après `const [deleting, ...]` (l.32), ajouter :

```tsx
  const [viewingRecords, setViewingRecords] = useState<HarvestSource | null>(null);
  const recordsPanel = usePanelTrigger(viewingRecords !== null);
```

L'exclusivité est la même que pour `editing` (décision 5 du plan SP-30j) :
- dans le `onClick` du bouton d'ajout (l.106-111), ajouter `setViewingRecords(null);` avant `setCreating(true);` ;
- dans le `onClick` du bouton d'édition (l.224-227), ajouter `setViewingRecords(null);` avant `setEditing(source);`.

Remplacer le rendu de la colonne `actions` (l.207-240) par :

```tsx
                      render: (source: HarvestSource) => (
                        <div className="flex gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            aria-controls={recordsPanel.panelId}
                            aria-expanded={viewingRecords?.id === source.id}
                            onClick={() => {
                              setCreating(false);
                              setEditing(null);
                              setViewingRecords(source);
                            }}
                          >
                            {t("harvest.recordsButton")}
                          </Button>
                          {!readOnly && (
                            <>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => runSource.mutate(source.id)}
                              >
                                {t("harvest.runNow")}
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                aria-controls={editPanel.panelId}
                                aria-expanded={editing?.id === source.id}
                                onClick={() => {
                                  setCreating(false);
                                  setViewingRecords(null);
                                  setEditing(source);
                                }}
                              >
                                {t("collectionsAdmin.edit")}
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(source)}
                              >
                                {t("actions.delete")}
                              </Button>
                            </>
                          )}
                        </div>
                      ),
```

Dans le panneau `inspect`, après le bloc `{editing && (...)}` (l.267-275), ajouter :

```tsx
              {viewingRecords && (
                <div id={recordsPanel.panelId}>
                  <HarvestRecordsPanel key={viewingRecords.id} source={viewingRecords} />
                </div>
              )}
```

Dans `confirmDelete` (l.80), ajouter `if (viewingRecords?.id === deleting.id) setViewingRecords(null);` après la ligne `if (editing?.id === deleting.id) setEditing(null);`. C'est la jumelle de la fermeture du panneau d'édition.

- [ ] **Step 5 : vérifier le succès**
  - Commande : `(cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx src/api && npx tsc --noEmit && npm run lint && npm run format:check)`
  - Attendu : PASS. `tsc` vérifie que les stubs `StaticItemClient`/`DesktopItemClient` couvrent la nouvelle méthode de l'interface.

- [ ] **Step 6 : bundle**
  - La page est en `lazy()`. La méthode de client et les cinq clés i18n vont en revanche dans le bundle initial.
  - Commande : `(cd shell && rm -rf dist dist-export && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold)`
  - Attendu : PASS, ou un dépassement de quelques centaines d'octets (la marge cumulée de L4-1 et L4-5 est de 0,4 Ko).
  - En cas de dépassement, relever `shell/.bundle-size-threshold` à l'entier supérieur à la taille mesurée, et mentionner le relèvement dans le corps du commit (« seuil de bundle relevé de N Ko : client + i18n des enregistrements moissonnés, rev-276b »).

- [ ] **Step 7 : commit**

```bash
git add shell/src/api/types.ts shell/src/api/domains/extensionsAdminTools.ts shell/src/api/domains/extensionsAdminTools.hooks.ts shell/src/staticExport/StaticItemClient.ts shell/src/desktop/DesktopItemClient.ts shell/src/pages/HarvestSourcesAdminPage.tsx shell/src/pages/HarvestSourcesAdminPage.test.tsx shell/src/i18n/catalog.fr.ts
# + shell/.bundle-size-threshold si relevé à l'étape 6
git commit -m "feat(shell): liste des enregistrements d'une source de moissonnage (rev-276b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-6: agrégat sans groupBy sur lac vide — une ligne « Total » à la source (REV-277c)

**Files:**
- Modify: `core/app/analytics/aggregate.py:621-622` (retour anticipé `if not _has_any_file(...)` de `_run_collection_aggregate`)
- Modify: `core/app/alerts/jobs.py:221-224` (branche `if not rows and ...`, désormais morte)
- Modify: `core/tests/test_analytics_aggregate.py` (deux tests ajoutés après `test_empty_collection_returns_empty_rows_without_error`, l.257-268)

**Interfaces:**
- Produces : `run_collection_aggregate` sans `groupBy`, sans `bins`, sans `sample` et sans `split` renvoie sur une collection dont le lac est vide `("group", [{"group": "Total", <label>: 0 | None}])`.
  - La valeur vaut 0 pour `count`/`countDistinct` et `None` pour tout autre agrégat (« indéfini n'est pas zéro », design SP-23 §3.1).
  - C'est exactement la ligne que produit le SQL sur un lac non vide filtré à zéro ligne (P25.07).
  - Les chemins avec `groupBy`, `bins` ou `sample` gardent `[]`.
- Consommé, sans modification de leur code, par `POST /v1/collections/{id}/aggregate` (le corps change de `[]` à une ligne), par l'outil MCP d'agrégat et par l'évaluation d'alerte.

**Correction de la spec :** la spec attend `[{"count": 0}]`. La forme réelle d'une ligne sans `groupBy` est `{"group": "Total", "value": 0}` (`_pivot_measures`, libellé `value` par défaut, cf. `test_no_group_by_produces_a_single_total_row`).

Le test du plan suit le code. Côté alerte, la branche « pas de ligne » (`alerts/jobs.py:221-224`) devient inatteignable. Elle est supprimée, et la branche `row[label] is None and agg in _ZERO_ON_EMPTY_AGGS` (l.241-244) prend le relais pour `sum`. Le test existant `test_alert_jobs.py::test_count_on_a_collection_without_data_evaluates_to_zero` couvre le chemin de bout en bout.

- [ ] **Step 1 : tests échouants** — dans `core/tests/test_analytics_aggregate.py`, après `test_empty_collection_returns_empty_rows_without_error`, ajouter :

```python
def test_empty_lake_without_group_by_returns_a_zero_total_row(tmp_path, conn):
    """REV-277c : même forme que le SQL sur un lac non vide filtré à vide
    (P25.07) — count vaut 0, pas « aucune ligne »."""
    category_key, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=AggregateRequestBody(),
    )
    assert category_key == "group"
    assert rows == [{"group": "Total", "value": 0}]


def test_empty_lake_sum_is_undefined_not_zero(tmp_path, conn):
    _, rows = run_collection_aggregate(
        conn,
        base_uri=str(tmp_path),
        tenant_id="t1",
        collection_id="villes",
        table_info=TABLE_INFO,
        request=AggregateRequestBody(
            measures=[AggregateMeasure(agg="count"), AggregateMeasure(agg="sum", field="pop")]
        ),
    )
    assert rows == [{"group": "Total", "count": 0, "sum_pop": None}]
```

Lancer `pyt tests/test_analytics_aggregate.py -k empty_lake`.
- Attendu : FAIL sur les deux tests (`[] == [{'group': 'Total', ...}]`).

- [ ] **Step 2 : implémentation** — dans `core/app/analytics/aggregate.py`, remplacer :

```python
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []
```

par :

```python
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        if fields or request.sample is not None or request.bins is not None or request.split:
            return category_key, []
        # REV-277c : sans groupBy, le SQL rend toujours UNE ligne (P25.07) ;
        # le lac vide doit rendre la même, pas « aucune ligne ».
        zero = ("count", "countDistinct")
        return category_key, [
            {
                "group": "Total",
                **{
                    _measure_label(m): (0 if m.agg in zero else None)
                    for m in _measures_for(request)
                },
            }
        ]
```

Dans `core/app/alerts/jobs.py`, supprimer le bloc :

```python
    if not rows and _measures_for(payload.query)[0].agg in _ZERO_ON_EMPTY_AGGS:
        # P20.02 (j09-013) : collection sans aucun fichier GeoParquet -> pas de
        # ligne, mais « zéro ligne » compte 0 / somme 0, pas une erreur.
        return 0.0
```

Puis compléter le commentaire de la branche `row[label] is None and ... in _ZERO_ON_EMPTY_AGGS` (l.~241) :

```python
        # P25 : sans groupBy l'agrégat rend toujours UNE ligne, lac vide compris
        # (REV-277c) ; somme d'un ensemble vide = NULL -> 0.
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_analytics_aggregate.py tests/test_features_aggregate_routes.py tests/test_alert_jobs.py tests/test_mcp_tools_run_analytics_query.py`
  - Attendu : PASS.
  - `test_features_aggregate_routes.py::test_aggregate_reports_lake_freshness_and_pending` ne vérifie que `pending`/`asOf`, il reste vert.
  - Puis : `(cd core && uv run ruff check app/analytics app/alerts && uv run mypy --strict app/analytics)`
  - Attendu : aucun constat.

- [ ] **Step 4 : commit**

```bash
git add core/app/analytics/aggregate.py core/app/alerts/jobs.py core/tests/test_analytics_aggregate.py
git commit -m "fix(core): agrégat sans groupby sur lac vide rend une ligne total à zéro (rev-277c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-7: migration 0047 — statut de livraison par canal d'une évaluation d'alerte (REV-277d — schéma)

**Files:**
- Create: `core/alembic/versions/0047_alert_notify_channels.py`
- Modify: `core/app/alerts/models.py:42` (après `notify_error`)
- Modify: `core/tests/test_migrations_p09.py` (test ajouté à la fin, après ceux de L4-3)

**Interfaces:**
- Consumes : la migration 0046 de L4-3 (`down_revision = "0046"`).
- Produces : la colonne `alert_evaluations.notify_channels JSON NULL` et l'attribut `AlertEvaluation.notify_channels: dict | None`, au format `{clé_de_canal: "delivered" | "failed"}`. Consommé par L4-8.
- Les lignes existantes restent NULL, ce que L4-8 interprète comme « aucun canal connu livré » : c'est le comportement actuel, tout est renvoyé.

- [ ] **Step 1 : test de migration échouant** — à la fin de `core/tests/test_migrations_p09.py`, ajouter :

```python
def test_0047_adds_notify_channels_on_a_non_empty_table_both_ways(throwaway_database_url):
    """REV-277d : statut de livraison par canal (base non vide)."""
    url = throwaway_database_url
    command.upgrade(_cfg(), "0046")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at) VALUES ('a1','t1','u1','alert','A','[]',now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO alert_evaluations (id, tenant_id, alert_rule_item_id, state, "
                "transitioned, notify_status, created_at) "
                "VALUES ('ev1','t1','a1','firing',true,'failed',now())"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0047")
    assert _scalar(url, "SELECT notify_channels FROM alert_evaluations WHERE id='ev1'") is None
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE alert_evaluations SET notify_channels='{\"k\": \"delivered\"}' "
                "WHERE id='ev1'"
            )
        )
    eng.dispose()
    assert (
        _scalar(url, "SELECT notify_channels->>'k' FROM alert_evaluations WHERE id='ev1'")
        == "delivered"
    )

    command.downgrade(_cfg(), "0046")
    assert _scalar(url, "SELECT notify_status FROM alert_evaluations WHERE id='ev1'") == "failed"
    assert (
        _scalar(
            url,
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='alert_evaluations' AND column_name='notify_channels'",
        )
        == 0
    )
```

Lancer `pyt tests/test_migrations_p09.py -k 0047`.
- Attendu : FAIL, la révision `0047` est introuvable.

- [ ] **Step 2 : migration** — créer `core/alembic/versions/0047_alert_notify_channels.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Statut de livraison par canal d'une évaluation d'alerte (REV-277d)

`notify_channels` : {clé de canal: "delivered" | "failed"}, la clé étant une
empreinte du canal (jamais l'URL en clair, qui peut porter un jeton). Une
relance (P20.03) ne renvoie qu'aux canaux non livrés. Les lignes existantes
restent NULL : aucun canal connu livré, donc relance sur tous (comportement
d'avant cette migration). Le downgrade ne perd que ce détail par canal ;
notify_status/notify_error (0044) restent.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_evaluations", sa.Column("notify_channels", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_evaluations", "notify_channels")
```

- [ ] **Step 3 : modèle** — dans `core/app/alerts/models.py`, après `notify_error` (l.42), ajouter :

```python
    # REV-277d : {empreinte de canal: "delivered" | "failed"} (cf. 0047).
    notify_channels: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
```

- [ ] **Step 4 : base de test partagée**
  - Commande : `docker exec postgis-test psql -U gis -d gis_test -c "ALTER TABLE alert_evaluations ADD COLUMN IF NOT EXISTS notify_channels json"`
  - Attendu : `ALTER TABLE`.

- [ ] **Step 5 : vérifier le succès**
  - Commande : `pyt tests/test_migrations_p09.py tests/test_model_alembic_parity.py tests/test_alert_jobs.py`
  - Attendu : PASS.

- [ ] **Step 6 : commit**

```bash
git add core/alembic/versions/0047_alert_notify_channels.py core/app/alerts/models.py core/tests/test_migrations_p09.py
git commit -m "feat(core): migration 0047, statut de livraison par canal d'une évaluation d'alerte (rev-277d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-8: relance d'alerte limitée aux canaux en échec, notification in-app unique par épisode (REV-277d — comportement)

**Files:**
- Modify: `core/app/alerts/repository.py:55-63` (`mark_notified`)
- Modify: `core/app/alerts/jobs.py`, aux endroits suivants :
  - imports (l.11-12) ;
  - commentaire ponytail (l.~87-89) ;
  - `_notify` (l.271-~335) ;
  - calcul de `retry` (l.~397-399) ;
  - appel de `_notify` et branche `except` (l.~498-532) ;
  - `mark_notified` (l.~533) ;
  - notification in-app (l.~536).
- Modify: `core/tests/test_alert_jobs.py` (helper et deux tests ajoutés à la fin)

**Interfaces:**
- Consumes (L4-7) : `AlertEvaluation.notify_channels`.
- Produces :
  - `alerts_repo.mark_notified(session, *, evaluation_id, status, error=None, channels: dict | None = None)` ;
  - `_notify(..., skip: frozenset[str] = frozenset()) -> tuple[str, str | None, dict[str, str]]`, dont le troisième élément associe chaque canal à son statut (un canal sauté vaut `"delivered"`, ce qui reporte l'information de relance en relance) ;
  - `_channel_key(channel) -> str`, soit 16 caractères hexadécimaux du SHA-256 de `channel.model_dump_json()`.
- Comportement : une relance (P20.03) n'envoie qu'aux canaux absents des « delivered » de l'évaluation terminale précédente. La notification in-app (P20.12) n'est posée qu'à une **transition**, jamais à une relance.

- [ ] **Step 1 : tests échouants** — à la fin de `core/tests/test_alert_jobs.py`, ajouter :

```python
def _set_channels(env_tuple, channels):
    _, Session, tenant, alert_item_id = env_tuple
    with Session() as s:
        cfg = configs_repo.get_config_by_item(s, alert_item_id)
        body = cfg.config.model_dump()
        body["alert"]["channels"] = channels
        configs_repo.update_config(
            s, cfg.id, BuilderConfig.model_validate(body), tenant_id=tenant.id
        )
        s.commit()


def test_retry_resends_only_to_channels_that_failed(env, monkeypatch):
    """REV-277d : le canal a livré au 1er envoi, b a échoué → la relance ne
    vise que b (plus de doublon sur a)."""
    a, b = "https://a.example.test/hook", "https://b.example.test/hook"
    _set_channels(env, [{"kind": "webhook", "url": a}, {"kind": "webhook", "url": b}])
    calls = []

    def send(channel, payload, **_kw):
        calls.append(channel.url)
        if channel.url == b and calls.count(b) == 1:
            raise alert_jobs.NotifyError("webhook delivery failed: 500")

    monkeypatch.setattr(alert_jobs, "send_webhook", send)
    e1 = _run_eval(env)
    assert e1.notify_status == "failed"
    assert sorted(e1.notify_channels.values()) == ["delivered", "failed"]
    e2 = _run_eval(env)
    assert e2.notify_status == "delivered"
    assert set(e2.notify_channels.values()) == {"delivered"}
    assert calls == [a, b, b]


def test_in_app_notification_is_posted_once_per_episode(env, monkeypatch):
    """REV-277d : déclenchement + deux relances = une seule notification in-app."""
    from app.notifications.models import Notification

    _, Session, _tenant, _alert_item_id = env
    sent = []

    def flaky(channel, payload, **_kw):
        sent.append(1)
        if len(sent) < 3:
            raise alert_jobs.NotifyError("webhook delivery failed: 500")

    monkeypatch.setattr(alert_jobs, "send_webhook", flaky)
    for _ in range(3):
        _run_eval(env)
    assert len(sent) == 3
    with Session() as s:
        assert len(s.scalars(select(Notification).where(Notification.kind == "alert")).all()) == 1
```

Lancer `pyt tests/test_alert_jobs.py -k "only_to_channels or once_per_episode"`.
- Attendu : FAIL.
  - Premier test : `AttributeError: 'AlertEvaluation' object has no attribute ...`, ou `None.values()`, puis `calls == [a, b, a, b]`.
  - Second test : 3 notifications au lieu d'une.

- [ ] **Step 2 : dépôt** — `core/app/alerts/repository.py`, remplacer `mark_notified` (l.55-63) par :

```python
def mark_notified(
    session: Session,
    *,
    evaluation_id: str,
    status: str,
    error: str | None = None,
    channels: dict | None = None,
) -> None:
    evaluation = session.get(AlertEvaluation, evaluation_id)
    if evaluation is None:
        return
    evaluation.notify_status = status
    evaluation.notify_error = error
    evaluation.notify_channels = channels
    session.flush()
```

- [ ] **Step 3 : job** — dans `core/app/alerts/jobs.py`, modifier les endroits suivants :
  1. Imports : ajouter `import hashlib` avant `import logging` (l.11).
  2. Remplacer les trois lignes de commentaire au-dessus de `_MAX_NOTIFY_RETRIES` (l.~86-89) par :

```python
# P20.03 : une livraison échouée est retentée à l'évaluation suivante (même
# état), au plus _MAX_NOTIFY_RETRIES fois d'affilée — vers les seuls canaux
# non livrés (REV-277d, notify_channels).
```

  3. Juste avant `def _notify(`, ajouter :

```python
def _channel_key(channel: AlertChannelWebhook | AlertChannelEmail) -> str:
    # Empreinte, jamais l'URL en clair : une URL de webhook peut porter un jeton.
    return hashlib.sha256(channel.model_dump_json().encode()).hexdigest()[:16]
```

  4. Dans `_notify` :
     - remplacer `actor_id: str | None = None,` puis `) -> tuple[str, str | None]:` par :
       ```python
           actor_id: str | None = None,
           skip: frozenset[str] = frozenset(),
       ) -> tuple[str, str | None, dict[str, str]]:
       ```
     - remplacer la docstring par :
       ```python
           """Retourne (notify_status, notify_error, statut par canal) : "delivered"
           si tous les canaux ont livré, sinon "failed" + motifs joints (P20.01/03).
           Les canaux de `skip` (déjà livrés lors de l'épisode) ne sont pas renvoyés
           et restent "delivered" (REV-277d)."""
       ```
     - juste après `failures: list[str] = []`, ajouter `channels: dict[str, str] = {}` ;
     - au début du corps de `for channel in payload.channels:`, ajouter :
       ```python
               key = _channel_key(channel)
               if key in skip:
                   channels[key] = "delivered"
                   continue
       ```
     - juste avant le `write_audit(` de la boucle, ajouter `channels[key] = "delivered" if success else "failed"` ;
     - remplacer les deux `return` finaux par :
       ```python
           if failures:
               return "failed", "; ".join(failures), channels
           return "delivered", None, channels
       ```
  5. Dans `evaluate_alert_task`, juste après le calcul de `retry = not transitioned and _should_retry_notification(...)`, ajouter :

```python
            # REV-277d : canaux déjà livrés pendant cet épisode, à ne pas renvoyer.
            delivered: frozenset[str] = frozenset()
            if retry:
                previous = _previous_terminal_evaluation(
                    history, current_evaluation_id=evaluation_id
                )
                done = (previous.notify_channels if previous is not None else None) or {}
                delivered = frozenset(k for k, s in done.items() if s == "delivered")
```

  6. Dans le bloc `if transitioned or retry:` :
     - remplacer les déclarations `notify_status: str | None` et `notify_error: str | None` par :
       ```python
                   notify_status: str | None
                   notify_error: str | None
                   notify_channels: dict[str, str] | None
       ```
     - remplacer `notify_status, notify_error = _notify(` par `notify_status, notify_error, notify_channels = _notify(` et ajouter `skip=delivered,` après `actor_id=owner_id,` ;
     - dans la branche `except Exception`, remplacer `notify_status, notify_error = "failed", f"erreur interne : {exc}"` par :
       ```python
                       notify_status, notify_error = "failed", f"erreur interne : {exc}"
                       notify_channels = None  # inconnu : la relance visera tous les canaux
       ```
     - remplacer l'appel `alerts_repo.mark_notified(...)` par :
       ```python
                   alerts_repo.mark_notified(
                       session,
                       evaluation_id=evaluation_id,
                       status=notify_status,
                       error=notify_error,
                       channels=notify_channels,
                   )
       ```
     - remplacer le commentaire et la condition de la notification in-app par :
       ```python
                   # P20.12 : notification in-app au propriétaire (alerte déclenchée ou
                   # livraison en échec) — une fois par épisode, à la transition
                   # seulement, jamais à chaque relance (REV-277d). Session dédiée.
                   if (
                       owner_id is not None
                       and not retry
                       and (notify_status == "failed" or new_state == "firing")
                   ):
       ```

- [ ] **Step 4 : vérifier le succès**
  - Commande : `pyt tests/test_alert_jobs.py tests/test_alert_repository.py tests/test_alert_sweep.py`
  - Attendu : PASS, y compris les tests existants :
    - `test_failed_delivery_is_exposed_retried_then_stops_once_delivered` (un seul canal, donc trois envois) ;
    - `test_retry_is_bounded` ;
    - `test_audits_carry_the_owner_and_firing_notifies_in_app` (une seule évaluation, `.one()`).
  - Puis : `(cd core && uv run ruff check app/alerts tests/test_alert_jobs.py && uv run ruff format --check app/alerts tests/test_alert_jobs.py)`
  - Attendu : aucun constat.

- [ ] **Step 5 : commit**

```bash
git add core/app/alerts/repository.py core/app/alerts/jobs.py core/tests/test_alert_jobs.py
git commit -m "fix(core): relance d'alerte vers les seuls canaux en échec, in-app une fois par épisode (rev-277d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-9: câblage d'actions d'app — cible et émetteur doivent exister (REV-278c)

**Files:**
- Modify: `core/app/configs/document_validation.py:105-116` (`_layout_errors`)
- Modify: `core/tests/test_p21_api_contracts.py` (deux tests ajoutés après `test_invalid_app_rejected`, l.93-103)

**Interfaces:**
- Produces : `validate_document(config)` (appelée à l'écriture seulement : `configs/routes.py:233,458`, `configs/service.py:108` et `mcp/tools/configs.py:118`, jamais à la relecture) renvoie 422 dans deux cas :
  - le `to` d'un message (de `config.messages` ou de l'`onEnter` d'une page) ne désigne ni un widget existant ni `var:<id>` d'une variable déclarée ;
  - le `from` d'un message de `config.messages` ne désigne aucun widget.
- Le `from` d'un `onEnter` vaut l'id de la page (`shell/src/builder/NavigationPanel.tsx:56`) : il n'est pas vérifié.
- Les widgets comptés sont ceux de tous les layouts (racine et pages), **y compris les widgets imbriqués** dans `props` (`props.items` des widgets `modal`/`drawer`, `shell/src/builder/widgets/modal.tsx:12`). Seuls les widgets qui portent un `id` comptent : le bus d'actions route par `item.id` (`shell/src/builder/WidgetHost.tsx:94`).

**Risque assumé (spec) :** une config existante au câblage orphelin reste lisible, car la relecture n'appelle jamais `validate_document`. En revanche, son prochain enregistrement est refusé en 422 avec un message qui nomme le câblage fautif. Le builder purge déjà le câblage d'un widget ou d'une variable supprimés (SP-52, `AppBuilderPage.tsx:402`) : seul un document édité à la main ou par une IA peut tomber dans ce cas.

- [ ] **Step 1 : tests échouants** — dans `core/tests/test_p21_api_contracts.py`, après `test_invalid_app_rejected`, ajouter :

```python
def test_app_messages_must_target_existing_widgets_or_variables(client):
    """REV-278c : un câblage vers un widget/une variable inexistants est refusé."""
    items = [
        {"id": "btn", "widget": "button", "x": 0, "y": 0, "w": 2, "h": 1},
        {"id": "map", "widget": "map", "x": 2, "y": 0, "w": 4, "h": 4},
    ]

    def app(messages, variables=()):
        return {
            "kind": "app",
            "layout": {"type": "grid", "items": items},
            "messages": messages,
            "variables": list(variables),
        }

    msg = {"from": "btn", "event": "clicked", "to": "map", "action": "flyTo"}
    assert _post(client, app([msg])).status_code == 201
    r = _post(client, app([{**msg, "to": "ghost"}]))
    assert r.status_code == 422 and "ghost" in r.json()["detail"]
    r = _post(client, app([{**msg, "from": "nobody"}]))
    assert r.status_code == 422 and "nobody" in r.json()["detail"]
    var = {"id": "v1", "name": "Ville"}
    to_var = {**msg, "action": "set"}
    assert _post(client, app([{**to_var, "to": "var:v1"}], [var])).status_code == 201
    assert _post(client, app([{**to_var, "to": "var:v2"}], [var])).status_code == 422


def test_app_messages_accept_nested_widgets_and_page_on_enter(client):
    nested = {"id": "inner", "widget": "text", "x": 0, "y": 0, "w": 2, "h": 1}
    modal = {
        "id": "dlg",
        "widget": "modal",
        "x": 0,
        "y": 0,
        "w": 2,
        "h": 1,
        "props": {"title": "M", "items": [nested]},
    }
    page = {
        "id": "p1",
        "name": "P1",
        "layout": {"type": "grid", "items": [modal]},
        "onEnter": [{"from": "p1", "event": "enter", "to": "dlg", "action": "open"}],
    }
    config = {
        "kind": "app",
        "layout": {"type": "grid", "items": []},
        "pages": [page],
        "messages": [{"from": "inner", "event": "clicked", "to": "dlg", "action": "close"}],
    }
    assert _post(client, config).status_code == 201
    bad = copy.deepcopy(config)
    bad["pages"][0]["onEnter"][0]["to"] = "nowhere"
    assert _post(client, bad).status_code == 422
```

Lancer `pyt tests/test_p21_api_contracts.py -k app_messages`.
- Attendu : FAIL. Le premier test reçoit 201 au lieu de 422 sur la cible `ghost`. Le second reçoit 201 au lieu de 422 sur `nowhere` (sa première assertion passe déjà).

- [ ] **Step 2 : implémentation** — dans `core/app/configs/document_validation.py`, ajouter avant `def _layout_errors` :

```python
def _widget_ids(node: object) -> set[str]:
    """Ids de tous les widgets d'un arbre de layout, imbriqués compris
    (props.items d'une modale/d'un tiroir) — REV-278c."""
    ids: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("widget"), str) and isinstance(node.get("id"), str):
            ids.add(node["id"])
        for value in node.values():
            ids |= _widget_ids(value)
    elif isinstance(node, list):
        for value in node:
            ids |= _widget_ids(value)
    return ids
```

Puis, dans `_layout_errors`, remplacer le bloc `messages = ...` / `for m in messages: ...` (l.112-115) par :

```python
    widgets = _widget_ids([lay.model_dump() for lay in layouts])
    targets = widgets | {f"var:{v.id}" for v in config.variables}
    on_enter = [m for p in config.pages for m in p.onEnter]
    for m in list(config.messages) + on_enter:
        name = m.id or m.event
        if m.when is not None and (e := _cel_syntax_error(m.when)):
            errs.append(f"message '{name}' when: {e}")
        if m.to not in targets:
            errs.append(f"message '{name}' to: unknown target '{m.to}'")
    for m in config.messages:  # le from d'un onEnter est l'id de la page
        if m.from_ not in widgets:
            errs.append(f"message '{m.id or m.event}' from: unknown widget '{m.from_}'")
```

- [ ] **Step 3 : vérifier le succès et les écrivains de configs**
  - Commande : `pyt tests/test_p21_api_contracts.py tests/test_mcp_form_app.py tests/test_mcp_tools_create_form_app.py tests/test_app_config_message_ids.py tests/test_repository.py tests/test_schemas.py tests/test_configs_if_match.py`
  - Attendu : PASS. Ces suites créent des apps câblées : génération de formulaire MCP, ids de messages.
  - Si l'une d'elles casse sur `unknown target`, le document de test est lui-même orphelin. Le corriger dans le test (ajouter le widget ou la variable cible) et ne jamais relâcher la règle. Le consigner dans le rapport de tâche.
  - Commande : `(cd core && uv run ruff check app/configs tests/test_p21_api_contracts.py && uv run ruff format --check app/configs tests/test_p21_api_contracts.py)`
  - Attendu : aucun constat.

- [ ] **Step 4 : commit**

```bash
git add core/app/configs/document_validation.py core/tests/test_p21_api_contracts.py
git commit -m "fix(core): refuse un câblage d'actions vers un widget ou une variable inconnus (rev-278c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-10: message d'erreur — afficher les `errors[]` du problem+json (REV-278e)

**Files:**
- Modify: `shell/src/api/apiErrorMessage.ts:18-22`
- Modify: `shell/src/api/apiErrorMessage.test.ts`

**Interfaces:**
- Consumes : `ApiError.errors` (déjà porté depuis P22.04, `shell/src/api/ApiError.ts:18-19`, alimenté par `base.ts:101`).
- Produces : `apiErrorMessage(error, fallback)`. Quand `errors[]` est non vide et qu'aucun cas quota/429 ne s'applique, le message affiche `champ : message`, entrées jointes par « ; », au lieu du `detail`. Le `detail` d'une `ValidationHTTPException` du cœur vaut en effet la chaîne fixe « validation failed » (`core/app/errors.py:19`).

**Re-vérification (P22.02/P22.04), demandée par la spec :** le transport est fait, `errors` est parsé et porté par `ApiError`. Seul l'affichage manque. Aucune autre page ne lit `errors` : `SqlLabPage` lit son propre corps d'erreur.

- [ ] **Step 1 : tests échouants** — à la fin de `shell/src/api/apiErrorMessage.test.ts`, ajouter :

```ts
describe("apiErrorMessage : errors[] du problem+json (REV-278e)", () => {
  it("affiche les erreurs par champ plutôt que le detail générique", () => {
    const e = new ApiError(400, {
      detail: "validation failed",
      errors: [
        { field: "url", code: "invalid", message: "url must be an http(s) URL" },
        { field: "", code: "x", message: "titre manquant" },
      ],
    });
    expect(apiErrorMessage(e, "x")).toBe("url : url must be an http(s) URL ; titre manquant");
  });
  it("retombe sur le detail sans errors[]", () => {
    expect(apiErrorMessage(new ApiError(409, { detail: "déjà existant" }), "x")).toBe(
      "déjà existant",
    );
  });
});
```

Lancer `(cd shell && npx vitest run src/api/apiErrorMessage.test.ts)`.
- Attendu : FAIL sur le premier cas (reçu : « validation failed »).

- [ ] **Step 2 : implémentation** — dans `shell/src/api/apiErrorMessage.ts`, remplacer la dernière ligne `return error.detail ?? fallback;` (l.22) par :

```ts
  if (error.errors?.length)
    return error.errors.map((e) => (e.field ? `${e.field} : ${e.message}` : e.message)).join(" ; ");
  return error.detail ?? fallback;
```

Et compléter le commentaire d'en-tête (l.6-7) :

```ts
// Message affichable d'une erreur de mutation : le `detail` RFC 7807 du cœur, avec
// « Réessayez dans N s » sur un 429, les `errors[]` par champ quand présents
// (REV-278e) ; `fallback` pour toute autre erreur.
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `(cd shell && npx vitest run src/api && npx tsc --noEmit && npm run lint && npm run format:check)`
  - Attendu : PASS.
  - Le fichier est dans le bundle initial, pour environ 150 octets. La mesure est groupée avec celle de L4-24, la dernière tâche shell du lot qui touche le bundle initial.

- [ ] **Step 4 : commit**

```bash
git add shell/src/api/apiErrorMessage.ts shell/src/api/apiErrorMessage.test.ts
git commit -m "fix(shell): les erreurs par champ du problem+json remontent dans le message (rev-278e)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-11: balayages planifiés — filtre `refreshPolicy.enabled` en SQL (REV-279b)

**Files:**
- Modify: `core/app/configs/repository.py:111-125` (`list_configs_by_kind`)
- Modify: `core/app/alerts/repository.py:157`, `core/app/reports/repository.py:137`, `core/app/pipelines/repository.py:238-240`
- Modify: `core/tests/test_p24_scans.py` (test ajouté à la fin)

**Interfaces:**
- Produces : `list_configs_by_kind(session, kind, *, refresh_enabled_only: bool = False)`. Avec `True`, la requête ajoute `CAST(data #>> '{kind,refreshPolicy,enabled}' AS BOOLEAN) IS true` en Postgres, ou `JSON_EXTRACT(...) IS 1` en SQLite. Les deux compilations ont été vérifiées pendant la rédaction.
- Une politique sans clé `enabled` vaut `False` côté modèle (`PipelineRefreshPolicy.enabled = False`, `schemas.py:277`) : elle est exclue de façon cohérente.
- Les trois balayages (alertes, rapports, pipelines) passent `refresh_enabled_only=True`. Leur filtre Python reste comme garde, pour les payloads absents.

**Choix :** pas de colonne dérivée (spec : « sauf nécessité mesurée »).

- [ ] **Step 1 : test échouant** — à la fin de `core/tests/test_p24_scans.py`, ajouter :

```python
def _alert(enabled):
    policy = {"cron": "*/5 * * * *"}
    if enabled is not None:
        policy["enabled"] = enabled
    return {
        "kind": "alert",
        "alert": {
            "datasetItemId": "d",
            "query": {"agg": "count"},
            "condition": {"expr": "value > 2"},
            "refreshPolicy": policy,
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }


def test_list_configs_by_kind_filters_enabled_refresh_in_sql(engine):
    """REV-279b : les règles désactivées ne sont plus chargées puis jetées en Python."""
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        s.execute(text("PRAGMA foreign_keys=OFF"))
        s.add(Tenant(id="t", slug="t", name="t"))
        s.flush()
        for item_id, enabled in (("on", True), ("off", False), ("legacy", None)):
            cid = uuid.uuid4().hex
            s.add(Config(id=cid, tenant_id="t", kind="alert", item_id=item_id, current_version=1))
            s.add(ConfigRevision(tenant_id="t", config_id=cid, version=1, data=_alert(enabled)))
        s.commit()
        filtered = list_configs_by_kind(s, "alert", refresh_enabled_only=True)
        assert [r[0] for r in filtered] == ["on"]
        assert len(list_configs_by_kind(s, "alert")) == 3
```

Lancer `pyt tests/test_p24_scans.py -k refresh`.
- Attendu : FAIL, `TypeError: list_configs_by_kind() got an unexpected keyword argument 'refresh_enabled_only'`.

- [ ] **Step 2 : implémentation** — dans `core/app/configs/repository.py`, remplacer la signature et la requête de `list_configs_by_kind` (l.111-125) par :

```python
def list_configs_by_kind(
    session: Session, kind: str, *, refresh_enabled_only: bool = False
) -> list[tuple[str, str, BuilderConfig]]:
    """Scan cross-tenant (pas de filtre tenant_id) — réservé aux tâches
    système (balayage périodique, SP-15h), jamais exposé via une route :
    contrairement à ConfigRead (response_model public), le tuple retourné
    porte tenant_id en clair. `refresh_enabled_only` (REV-279b) : ne charge
    que les configs dont `<kind>.refreshPolicy.enabled` est vrai, en SQL."""
    # Une seule requête (P24.06) : révision courante par jointure, plus de N+1.
    stmt = (
        select(Config, ConfigRevision)
        .join(
            ConfigRevision,
            (ConfigRevision.config_id == Config.id)
            & (ConfigRevision.version == Config.current_version),
        )
        .where(Config.kind == kind)
    )
    if refresh_enabled_only:
        enabled = ConfigRevision.data[(kind, "refreshPolicy", "enabled")].as_boolean()
        stmt = stmt.where(enabled.is_(True))
    rows = session.execute(stmt).all()
```

Le reste de la fonction (`result: list[...] = []` et la boucle) est inchangé.

Dans les trois balayages, ajouter `refresh_enabled_only=True` à l'appel :
- `core/app/alerts/repository.py:157` : `configs_repo.list_configs_by_kind(session, kind="alert", refresh_enabled_only=True)` (reformater sur plusieurs lignes si `ruff format` l'exige) ;
- `core/app/reports/repository.py:137` : `configs_repo.list_configs_by_kind(session, kind="report", refresh_enabled_only=True)` ;
- `core/app/pipelines/repository.py:238-240` : `configs_repo.list_configs_by_kind(session, kind="pipeline", refresh_enabled_only=True)`.

- [ ] **Step 3 : vérifier le succès (SQLite et Postgres)**
  - Commande : `pyt tests/test_p24_scans.py tests/test_alert_sweep.py tests/test_alert_repository.py tests/test_report_repository.py tests/test_report_sweep.py tests/test_pipeline_repository.py tests/test_pipeline_sweep.py`
  - Attendu : PASS. `test_alert_sweep.py` tourne sur Postgres et exerce donc le `#>>`.
  - Commande : `(cd core && uv run ruff check app tests/test_p24_scans.py && uv run ruff format --check app tests/test_p24_scans.py)`
  - Attendu : aucun constat.

- [ ] **Step 4 : commit**

```bash
git add core/app/configs/repository.py core/app/alerts/repository.py core/app/reports/repository.py core/app/pipelines/repository.py core/tests/test_p24_scans.py
git commit -m "perf(core): balayages planifiés filtrent refreshpolicy.enabled en sql (rev-279b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-12: cache d'introspection Postgres borné (LRU) et purgé à la disparition de la table (REV-279d)

**Files:**
- Modify: `core/app/collections/introspection_pg.py:6-7` (import) et `:77-104` (cache et `introspect_table`)
- Modify: `core/tests/test_introspection_pg.py` (test ajouté à la fin)

**Interfaces:** Produces : `_cache` devient un `OrderedDict` borné à `_CACHE_MAX = 512` entrées, avec une éviction LRU (un accès remet l'entrée en fin). L'entrée d'une table disparue (empreinte `None`) est retirée. Le comportement observable d'`introspect_table` est inchangé.

- [ ] **Step 1 : test échouant** — à la fin de `core/tests/test_introspection_pg.py`, ajouter :

```python
def test_cache_is_bounded_lru_and_forgets_dropped_tables(pg_session, pg_engine, monkeypatch):
    """REV-279d : plafond LRU, et une table supprimée ne laisse pas d'entrée."""
    from collections import OrderedDict

    from app.collections import introspection_pg

    monkeypatch.setattr(introspection_pg, "_CACHE_MAX", 2)
    monkeypatch.setattr(introspection_pg, "_cache", OrderedDict())
    url = str(pg_session.get_bind().url)
    introspection_pg._cache[(url, "old_a")] = (0.0, "x", None)
    introspection_pg._cache[(url, "old_b")] = (0.0, "x", None)
    introspect_table(pg_session, "t_incidents")
    keys = list(introspection_pg._cache)
    assert len(keys) == 2 and (url, "old_a") not in keys and keys[-1] == (url, "t_incidents")

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE t_incidents"))
    pg_session.rollback()
    with pytest.raises(TableNotFound):
        introspect_table(pg_session, "t_incidents")
    assert (url, "t_incidents") not in introspection_pg._cache
```

Lancer `pyt tests/test_introspection_pg.py -k bounded`.
- Attendu : FAIL. Le `dict` n'évince rien (3 entrées). Selon la version, l'échec vient de `len(keys) == 2` ou de la présence de `old_a`.

- [ ] **Step 2 : implémentation** — dans `core/app/collections/introspection_pg.py` :

Ajouter `from collections import OrderedDict` avant `import copy` (l.6).

Remplacer les lignes `_CACHE_TTL_S = 30.0` et `_cache: dict[...] = {}` (l.82-83) par :

```python
_CACHE_TTL_S = 30.0
# REV-279d : borné (LRU) — une instance aux milliers de collections ne doit pas
# faire croître ce cache sans limite au fil des tables touchées.
_CACHE_MAX = 512
_cache: OrderedDict[tuple[str, str], tuple[float, str, TableInfo]] = OrderedDict()
```

Remplacer le corps d'`introspect_table` (l.96-104) par :

```python
def introspect_table(session: Session, table_name: str) -> TableInfo:
    key = (str(session.get_bind().url), table_name)
    fingerprint = session.execute(text(_FINGERPRINT_SQL), {"t": table_name}).scalar()
    if fingerprint is None:  # absente : l'erreur vient du chemin non caché
        _cache.pop(key, None)
        return _introspect_table_uncached(session, table_name)
    hit = _cache.get(key)
    if hit and hit[1] == fingerprint and time.monotonic() - hit[0] < _CACHE_TTL_S:
        _cache.move_to_end(key)
        return copy.deepcopy(hit[2])
    info = _introspect_table_uncached(session, table_name)
    _cache[key] = (time.monotonic(), fingerprint, info)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return copy.deepcopy(info)
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_introspection_pg.py tests/test_features_tiles_cache.py`
  - Attendu : PASS.
  - Commande : `(cd core && uv run ruff check app/collections && uv run ruff format --check app/collections)`
  - Attendu : aucun constat.

- [ ] **Step 4 : commit**

```bash
git add core/app/collections/introspection_pg.py core/tests/test_introspection_pg.py
git commit -m "fix(core): cache d'introspection borné en lru et purgé pour une table supprimée (rev-279d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-13: catalogue public — filtre `tag` en SQL sur Postgres (REV-279e)

**Files:**
- Modify: `core/app/items/repository.py:9` (imports) et `:615-620` (`list_published_items`, avant `if tag:`)
- Create: `core/tests/test_public_items_tag_pg.py`

**Interfaces:**
- Produces : `list_published_items(..., tag=...)`. Sur Postgres, le filtre devient `CAST(items.keywords AS JSONB) @> '["tag"]'` dans la requête paginée elle-même : pagination SQL, `total` en `COUNT`. Sur SQLite (tests), le chemin Python existant (P24.05) est conservé.
- Signature et forme de réponse inchangées : pas de régénération OpenAPI.

- [ ] **Step 1 : test échouant** — créer `core/tests/test_public_items_tag_pg.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-279e : le filtre tag du catalogue public passe en SQL (jsonb @>) sur Postgres."""

import pytest
from sqlalchemy import event, text

from app.db import Base, make_session_factory
from app.items.models import Item
from app.items.repository import list_published_items
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    with make_session_factory(pg_engine)() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


def test_tag_filter_runs_in_sql_on_postgres(pg_session, pg_engine):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    for item_id, title, keywords in (("i1", "Avec", ["eau", "air"]), ("i2", "Sans", ["air"])):
        pg_session.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                owner_id=user.id,
                resource_type="app",
                title=title,
                keywords=keywords,
                is_published=True,
            )
        )
    pg_session.commit()
    statements = []

    def _capture(_conn, _cursor, statement, *_a):
        statements.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _capture)
    try:
        page = list_published_items(pg_session, tenant_id=tenant.id, tag="eau")
    finally:
        event.remove(pg_engine, "before_cursor_execute", _capture)
    assert [i.title for i in page.items] == ["Avec"] and page.total == 1
    assert any("@>" in s for s in statements)
```

Lancer `pyt tests/test_public_items_tag_pg.py`.
- Attendu : FAIL sur `any("@>" in s ...)`. Le résultat fonctionnel est déjà correct par le chemin Python.

- [ ] **Step 2 : implémentation** — dans `core/app/items/repository.py` :
  - remplacer `from sqlalchemy import func, or_, select` (l.9) par `from sqlalchemy import cast, func, or_, select`, puis ajouter `from sqlalchemy.dialects.postgresql import JSONB` juste après ;
  - dans `list_published_items`, juste avant `if tag:` (l.~617), insérer :

```python
    if tag and session.get_bind().dialect.name == "postgresql":
        # REV-279e : filtre en SQL sur Postgres (jsonb @>), pagination et total
        # en SQL ; le chemin Python ci-dessous ne sert plus qu'à SQLite (tests).
        query = query.where(cast(Item.keywords, JSONB).contains([tag]))
        tag = None
```

  - mettre à jour le commentaire du chemin Python : « Tag en Python (SQLite seulement, Postgres filtre en SQL ci-dessus — REV-279e) ».

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_public_items_tag_pg.py tests/test_public_items_list.py tests/test_public_routes.py tests/test_items_repository.py`
  - Attendu : PASS.
  - Commande : `(cd core && uv run ruff check app/items tests/test_public_items_tag_pg.py && uv run lint-imports)`
  - Attendu : aucun constat.

- [ ] **Step 4 : commit**

```bash
git add core/app/items/repository.py core/tests/test_public_items_tag_pg.py
git commit -m "perf(core): filtre tag du catalogue public en sql jsonb sur postgres (rev-279e)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-14: SQL Lab — Entrée insère réellement une ligne liste de complétion ouverte (REV-280c)

**Files:**
- Modify: `shell/src/pages/SqlLabPage.tsx:7` (import) et `:52-65` (`sqlEditorKeys`)
- Modify: `shell/src/pages/SqlLabPage.test.tsx` (imports et deux tests ajoutés à la fin)

**Interfaces:** Produces : `sqlEditorKeys` devient un tableau d'extensions, déjà consommé tel quel dans `extensions={[...]}` (l.220-225), sans changement d'appelant :
- `autocompletion({ defaultKeymap: false })` ;
- une keymap `Prec.highest` qui reprend `completionKeymap` sans sa liaison Entrée et ajoute Entrée = saut de ligne, Tab = accepter.

**Correction de la spec (défaut réel trouvé) :** la spec demande seulement « un test jsdom de `sqlEditorKeys` ». En écrivant ce test pendant la rédaction, on a constaté que **le correctif P25.16 est inopérant** : liste de complétion ouverte, Entrée valide toujours la complétion. La keymap de complétion que `basicSetup` installe via `autocompletion()` gagne sur la nôtre malgré `Prec.highest`.

Le correctif ci-dessous a été vérifié pendant la rédaction :
- avant correctif, le test Entrée échoue et le test Tab passe ;
- après correctif, les 18 tests du fichier passent.

- [ ] **Step 1 : tests échouants** — dans `shell/src/pages/SqlLabPage.test.tsx` :

Ajouter aux imports, après `import { render, screen, waitFor } from "@testing-library/react";` :

```tsx
import { completionStatus, startCompletion } from "@codemirror/autocomplete";
import { EditorView, runScopeHandlers } from "@codemirror/view";
```

Ajouter à la fin du fichier :

```tsx
async function openCompletion(): Promise<EditorView> {
  const { container } = render(<Harness />);
  const dom = await waitFor(() => {
    const el = container.querySelector(".cm-editor");
    if (!el) throw new Error("éditeur absent");
    return el as HTMLElement;
  });
  const view = EditorView.findFromDOM(dom)!;
  view.dispatch({ changes: { from: 0, insert: "SEL" }, selection: { anchor: 3 } });
  startCompletion(view);
  await waitFor(() => expect(completionStatus(view.state)).toBe("active"));
  // La liste n'accepte une validation qu'après son délai d'interaction
  // (interactionDelay, 75 ms) : sans cette attente, Entrée passe toujours
  // et le test donnait un faux positif (constaté pendant la rédaction).
  await new Promise((resolve) => setTimeout(resolve, 150));
  return view;
}

test("Entrée insère une ligne même avec la liste de complétion ouverte (REV-280c)", async () => {
  const view = await openCompletion();
  runScopeHandlers(view, new KeyboardEvent("keydown", { key: "Enter" }), "editor");
  expect(view.state.doc.toString()).toBe("SEL\n");
});

test("Tab accepte la complétion (REV-280c)", async () => {
  const view = await openCompletion();
  runScopeHandlers(view, new KeyboardEvent("keydown", { key: "Tab" }), "editor");
  expect(view.state.doc.toString().toLowerCase()).toBe("select");
});
```

Lancer `(cd shell && npx vitest run src/pages/SqlLabPage.test.tsx)`.
- Attendu : FAIL sur le test Entrée (la complétion « SELECT » est validée à la place du saut de ligne).
- Attendu : PASS sur le test Tab.

- [ ] **Step 2 : implémentation** — dans `shell/src/pages/SqlLabPage.tsx`, remplacer l'import l.7 par :

```tsx
import { acceptCompletion, autocompletion, completionKeymap } from "@codemirror/autocomplete";
```

et le bloc `const sqlEditorKeys = Prec.highest(...)` (l.52-65), commentaire compris, par :

```tsx
// P25.16 : Entrée insère une nouvelle ligne même quand la liste de complétion
// est ouverte (elle validait le mot-clé « catalog ») ; Tab accepte la complétion.
// REV-280c : `basicSetup` installe la keymap de complétion avec sa propre
// priorité, qui gagnait sur Prec.highest — on la désactive et on la remet ici
// sans sa liaison Entrée.
const sqlEditorKeys = [
  autocompletion({ defaultKeymap: false }),
  Prec.highest(
    keymap.of([
      ...completionKeymap.filter((binding) => binding.key !== "Enter"),
      {
        key: "Enter",
        run: (view) => {
          view.dispatch(view.state.replaceSelection("\n"), { scrollIntoView: true });
          return true;
        },
      },
      { key: "Tab", run: acceptCompletion },
    ]),
  ),
];
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `(cd shell && npx vitest run src/pages/SqlLabPage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check)`
  - Attendu : PASS (18 tests). `SqlLabPage` est en `lazy()` : bundle initial inchangé.
  - **Falsification** (piège n°10) : remettre temporairement l'ancien bloc, constater l'échec du test Entrée, puis restaurer.

- [ ] **Step 4 : commit**

```bash
git add shell/src/pages/SqlLabPage.tsx shell/src/pages/SqlLabPage.test.tsx
git commit -m "fix(shell): sql lab, entrée insère une ligne même liste de complétion ouverte (rev-280c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-15: connexions Postgres du cœur en UTC (REV-280g)

**Files:**
- Modify: `core/app/db.py:98-105` (après le bloc `if engine.dialect.name == "sqlite":`)
- Create: `core/tests/test_db_timezone.py`

**Interfaces:** Produces : toute connexion Postgres ouverte par `make_engine` a `TimeZone = 'UTC'`, quel que soit le fuseau du client (`PGTZ`) ou du rôle. Consumes : rien.

**Correction de la spec :** la spec propose `-c timezone=UTC` à la connexion. Le cœur passe par PgBouncer en mode transaction, et PgBouncer refuse le paramètre de démarrage `options` sauf `ignore_startup_parameters`. En revanche, PgBouncer suit `TimeZone` comme paramètre de session (ParameterStatus) et le rejoue sur le backend attribué. Le correctif fait donc un `SET TIME ZONE 'UTC'` commité dans l'événement `connect`. DuckDB est déjà en UTC (`SET TimeZone`, P25.12) : il est hors périmètre.

Constaté pendant la rédaction : avec `PGTZ=Europe/Paris`, `SHOW timezone` sur une connexion `make_engine` renvoie `Europe/Paris`.

- [ ] **Step 1 : test échouant** — créer `core/tests/test_db_timezone.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-280g : une connexion du cœur est en UTC, quel que soit le fuseau client."""

import pytest
from sqlalchemy import text

from app.db import make_engine

pytestmark = pytest.mark.postgis


def test_postgres_session_timezone_is_utc(test_db_url, monkeypatch):
    monkeypatch.setenv("PGTZ", "Europe/Paris")  # fuseau client envoyé par libpq
    engine = make_engine(test_db_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SHOW timezone")).scalar() == "UTC"
    finally:
        engine.dispose()
```

Lancer `pyt tests/test_db_timezone.py`.
- Attendu : FAIL, `assert 'Europe/Paris' == 'UTC'`.

- [ ] **Step 2 : implémentation** — dans `core/app/db.py`, juste avant le `return engine` final de `make_engine` (après le bloc `if engine.dialect.name == "sqlite": ...`), ajouter :

```python
    if engine.dialect.name == "postgresql":
        # REV-280g : horodatages et now() en UTC quel que soit le fuseau du
        # client ou du rôle. Pas de `-c timezone=UTC` au démarrage : PgBouncer
        # refuse `options` ; il suit en revanche TimeZone (ParameterStatus) et
        # le rejoue sur chaque backend attribué.
        @event.listens_for(engine, "connect")
        def _utc_session(dbapi_connection, connection_record):
            with dbapi_connection.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")
            dbapi_connection.commit()
```

- [ ] **Step 3 : vérifier le succès et l'absence de régression**
  - Commande : `pyt tests/test_db_timezone.py tests/test_alert_jobs.py tests/test_health_jobs_backlog.py tests/test_features_rls.py`
  - Attendu : PASS. `test_features_rls.py::test_scope_preserves_original_sql_error` est un intermittent connu : le rejouer isolé avant de s'imputer une régression.
  - Puis `pyt -m postgis -x`
  - Attendu : PASS. Toute la suite Postgres ouvre ses connexions par `make_engine` ou `create_engine` ; seules les premières changent.

- [ ] **Step 4 : commit**

```bash
git add core/app/db.py core/tests/test_db_timezone.py
git commit -m "fix(core): connexions postgres du cœur en utc (rev-280g)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-16: couverture par module dans le résumé CI (REV-281a)

**Files:**
- Modify: `core/scripts/check_coverage.py`
- Modify: `core/tests/test_check_coverage.py`

**Interfaces:** Produces : `check_coverage.py coverage.xml .coverage-threshold` imprime, en plus du total, un tableau markdown « Module | Couverture » trié par couverture croissante, à partir des `<package>` du XML Cobertura. Le tableau est ajouté à `$GITHUB_STEP_SUMMARY` quand cette variable est définie. Code de sortie inchangé : le seuil reste global, le rapport est non bloquant. L'invocation CI ne change pas (`ci.yml:76`).

**Choix (spec 281a, P27.06) :** la CI tourne déjà sur base réelle (`CORE_REQUIRE_DB=1`), donc le rapport par module reflète le chemin Postgres. Pas de seuil par module : rien ne le demande. On peut l'ajouter quand un module régresse en silence.

- [ ] **Step 1 : tests échouants** — dans `core/tests/test_check_coverage.py`, ajouter `import os` aux imports et remplacer `_run` par :

```python
def _run(xml_content: str, threshold: str, tmp_path, env=None):
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(xml_content)
    threshold_path = tmp_path / ".coverage-threshold"
    threshold_path.write_text(threshold)
    return subprocess.run(
        [sys.executable, "scripts/check_coverage.py", str(xml_path), str(threshold_path)],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
```

puis ajouter à la fin :

```python
PACKAGES_XML = textwrap.dedent(
    """\
    <?xml version="1.0" ?>
    <coverage line-rate="0.85">
      <packages>
        <package name="app.alerts" line-rate="0.95"/>
        <package name="app.pipelines" line-rate="0.62"/>
      </packages>
    </coverage>
    """
)


def test_reports_per_package_coverage_lowest_first(tmp_path):
    """REV-281a : rapport par module, non bloquant, aussi dans le résumé CI."""
    summary = tmp_path / "summary.md"
    result = _run(PACKAGES_XML, "80", tmp_path, env={"GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 0
    assert result.stdout.index("app.pipelines") < result.stdout.index("app.alerts")
    assert "| app.pipelines | 62.0 % |" in result.stdout
    assert "| app.alerts | 95.0 % |" in summary.read_text()
```

Lancer `(cd core && uv run pytest tests/test_check_coverage.py -q)`.
- Attendu : FAIL, `ValueError: substring not found`.

- [ ] **Step 2 : implémentation** — remplacer `core/scripts/check_coverage.py` par :

```python
import os
import sys
import xml.etree.ElementTree as ET


def coverage_percent(xml_path: str) -> float:
    root = ET.parse(xml_path).getroot()
    return float(root.attrib["line-rate"]) * 100


def package_rates(xml_path: str) -> list[tuple[str, float]]:
    """REV-281a : couverture par module (<package> Cobertura), la plus basse d'abord."""
    root = ET.parse(xml_path).getroot()
    rates = [(p.attrib["name"], float(p.attrib["line-rate"]) * 100) for p in root.iter("package")]
    return sorted(rates, key=lambda r: r[1])


def report(rates: list[tuple[str, float]]) -> str:
    rows = [f"| {name} | {rate:.1f} % |" for name, rate in rates]
    return "\n".join(["| Module | Couverture |", "|---|---|", *rows])


def main(xml_path: str, threshold_path: str) -> int:
    measured = coverage_percent(xml_path)
    with open(threshold_path) as f:
        threshold = float(f.read().strip())
    print(f"Couverture mesurée : {measured:.2f}% (seuil : {threshold:.2f}%)")
    rates = package_rates(xml_path)
    if rates:
        table = report(rates)
        print(table)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as f:
                f.write(f"### Couverture du cœur par module\n\n{table}\n")
    if measured < threshold:
        print(f"ÉCHEC : couverture {measured:.2f}% < seuil {threshold:.2f}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `(cd core && uv run pytest tests/test_check_coverage.py -q && uv run ruff check scripts/check_coverage.py tests/test_check_coverage.py && uv run ruff format --check scripts/check_coverage.py tests/test_check_coverage.py)`
  - Attendu : PASS et aucun constat.
  - Contrôle sur un vrai rapport, s'il en existe un local : `(cd core && [ -f coverage.xml ] && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold | head -5)`
  - Attendu : la ligne « Couverture mesurée », puis l'en-tête du tableau.

- [ ] **Step 4 : commit**

```bash
git add core/scripts/check_coverage.py core/tests/test_check_coverage.py
git commit -m "ci(core): rapport de couverture par module dans le résumé de la ci (rev-281a)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-17: sauvegarde — rotation hors-site malgré un envoi en échec, alerte d'abandon (REV-281f, REV-281c)

**Files:**
- Modify: `deploy/backup/backup.sh:32` (`WORKDIR`), `:102` (`tar -C`) et `:120-129` (section 6)
- Modify: `deploy/backup/entrypoint.sh:12-31`
- Modify: `docker-compose.prod.yml:397` (service `backup`) et `:400-404` (commentaire)
- Modify: `.env.example` (bloc « Sauvegarde », après `BACKUP_S3_BUCKET=geostudio-backups`)
- Create: `core/tests/test_backup_offsite_rotation.py`, `core/tests/test_backup_entrypoint.py`

**Interfaces:**
- Produces (`backup.sh`) :
  - `BACKUP_WORK_DIR`, défaut `/backup/work` : le répertoire de travail devient surchargeable, ce qui sert de point d'injection pour le test ;
  - section 6 : la rotation hors-site (`mc rm` des archives que la politique de rétention écarte) s'exécute **toujours** quand une cible est configurée, puis `exit 75` si l'envoi a échoué.
- Produces (`entrypoint.sh`) :
  - `BACKUP_SCRIPT`, défaut `/usr/local/bin/backup.sh`, autre point d'injection ;
  - quand un jour est abandonné après `BACKUP_MAX_ATTEMPTS` tentatives, un POST JSON `{"text": "..."}` part vers `BACKUP_ALERT_WEBHOOK_URL` si elle est définie. Le format est accepté par Slack, Mattermost et Rocket.Chat.

**Correction de la spec (281c) :** la spec demande une « règle d'alerte ou sonde sur `.last_success` ». Une règle Grafana est impossible : le profil observability ne scrape pas l'état Docker (`docker-compose.prod.yml:403-404`). L'alerte est donc émise à la source, par l'entrypoint, au moment exact où le jour est abandonné. Le healthcheck de fraîcheur (P27.08) reste en place pour `docker ps`. L'image contient déjà `curl` (`deploy/backup/Dockerfile:20`).

- [ ] **Step 1 : test échouant (rotation)** — créer `core/tests/test_backup_offsite_rotation.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-281f : un envoi hors-site en échec n'empêche plus la rotation hors-site
(sinon le bucket distant grossit sans fin pendant toute la panne)."""

import os
import subprocess
from pathlib import Path

BACKUP_SH = Path(__file__).resolve().parents[2] / "deploy/backup/backup.sh"
OLD = "20250101-030000.tar.gz.age"

STUBS = {
    # pg_dump : crée le fichier --file=… (du -h le mesure ensuite)
    "pg_dump": 'for a in "$@"; do case "$a" in --file=*) : > "${a#--file=}";; esac; done',
    # mc : alias/rm réussissent, cp/ls/mirror échouent (envoi hors-site en panne)
    "mc": 'echo "$@" >> "$LOG"; case "$1" in alias|rm) exit 0;; *) exit 1;; esac',
    # curl : jeton admin sur stdout, export de realm vers -o
    "curl": 'out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; '
    'if [ -n "$out" ]; then echo \'{"realm":"geostudio"}\' > "$out"; '
    "else echo '{\"access_token\":\"tok\"}'; fi",
    "jq": '[ "$1" = -r ] && echo tok; exit 0',
    # age -r R -o OUT IN : copie IN vers OUT
    "age": 'cp "$5" "$4"',
    # retention.py : désigne l'ancienne archive à supprimer
    "python3": f"echo {OLD}",
}


def test_offsite_rotation_runs_even_when_upload_fails(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in STUBS.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    archives = tmp_path / "archives"
    archives.mkdir()
    (archives / OLD).write_text("x")
    log = tmp_path / "mc.log"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LOG": str(log),
        "BACKUP_ARCHIVES_DIR": str(archives),
        "BACKUP_WORK_DIR": str(tmp_path / "work"),
        "BACKUP_AGE_RECIPIENT": "age1test",
        "BACKUP_S3_ENDPOINT": "http://offsite",
        "BACKUP_S3_ACCESS_KEY": "a",
        "BACKUP_S3_SECRET_KEY": "s",
        "BACKUP_S3_BUCKET": "b",
        "PG_PASSWORD": "p",
        "MINIO_USER": "u",
        "MINIO_PASSWORD": "p",
        "KEYCLOAK_ADMIN": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "p",
    }
    r = subprocess.run(["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True)
    assert r.returncode == 75, r.stderr
    assert f"rm --quiet offsite/b/{OLD}" in log.read_text()
    assert not (archives / OLD).exists()  # rotation locale (déjà le cas avant)
    assert not (archives / ".last_success").exists()
```

Lancer `pyt tests/test_backup_offsite_rotation.py`.
- Attendu : FAIL. Sans `BACKUP_WORK_DIR`, le script tente `mkdir -p /backup/work/...` et sort en erreur (code 1, pas 75). Une fois le répertoire de travail injectable, l'échec devient `rm --quiet offsite/b/... not in log`.

- [ ] **Step 2 : implémentation (`backup.sh`)**

Remplacer la ligne 32 `WORKDIR="/backup/work/${DATE}"` par :

```bash
WORK_ROOT="${BACKUP_WORK_DIR:-/backup/work}"
WORKDIR="${WORK_ROOT}/${DATE}"
```

Remplacer la ligne 102 `tar -czf "/tmp/${DATE}.tar.gz" -C /backup/work "${DATE}"` par :

```bash
tar -czf "/tmp/${DATE}.tar.gz" -C "$WORK_ROOT" "${DATE}"
```

Remplacer la section 6 (l.120-134, du commentaire `# ── 6.` jusqu'au `fi` qui précède `touch`) par :

```bash
# ── 6. Envoi hors-site (optionnel — avertissement clair si absent), puis
#    rotation hors-site sur la même politique — exécutée MÊME si l'envoi
#    échoue (REV-281f) : sinon le bucket distant grossit pendant toute la
#    panne. Code 75 ensuite, pour que l'entrypoint relance l'envoi seul. ──
if [ -n "${BACKUP_S3_ENDPOINT:-}" ]; then
  upload_rc=0
  upload_offsite "${DATE}.tar.gz.age" || upload_rc=$?
  for f in $TO_DELETE; do
    mc rm --quiet "offsite/${BACKUP_S3_BUCKET}/${f}" 2>/dev/null || true
  done
  if [ "$upload_rc" != 0 ]; then
    echo "[backup] ERREUR: envoi hors-site en échec — archive locale conservée" >&2
    exit 75
  fi
else
  echo "[backup] AVERTISSEMENT: aucune cible hors-site configurée (BACKUP_S3_ENDPOINT vide)." >&2
  echo "[backup] Les sauvegardes restent UNIQUEMENT sur cette machine — ne protège ni de" >&2
  echo "[backup] l'incendie, ni du vol, ni de la panne disque. Configurer BACKUP_S3_* dès que possible." >&2
fi
```

- [ ] **Step 3 : test échouant (alerte d'abandon)** — créer `core/tests/test_backup_entrypoint.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-281c : un jour de sauvegarde abandonné déclenche une alerte webhook
(aucune règle Grafana possible : l'état Docker n'est pas scrapé)."""

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[2] / "deploy/backup/entrypoint.sh"


def _run(tmp_path, webhook):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stubs = {
        "sleep": "exit 1",  # sort de la boucle infinie après le premier passage
        "curl": f'echo "$@" >> "{tmp_path}/curl.log"',
    }
    for name, body in stubs.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    failing = tmp_path / "backup.sh"
    failing.write_text("#!/bin/sh\nexit 1\n")
    failing.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        # str(int(...)) : « 08 » ferait échouer printf %02d (lu en octal)
        "BACKUP_HOUR": str(int(datetime.now(UTC).strftime("%H"))),
        "BACKUP_MAX_ATTEMPTS": "1",
        "BACKUP_SCRIPT": str(failing),
    }
    if webhook:
        env["BACKUP_ALERT_WEBHOOK_URL"] = webhook
    r = subprocess.run(["bash", str(ENTRYPOINT)], env=env, capture_output=True, text=True)
    log = tmp_path / "curl.log"
    return r, (log.read_text() if log.exists() else "")


def test_abandoned_day_posts_to_alert_webhook(tmp_path):
    r, calls = _run(tmp_path, "https://hooks.example.test/backup")
    assert "abandon" in r.stderr
    assert "https://hooks.example.test/backup" in calls
    assert "sauvegarde abandonnée" in calls


def test_no_webhook_configured_sends_nothing(tmp_path):
    r, calls = _run(tmp_path, None)
    assert "abandon" in r.stderr
    assert calls == ""
```

Lancer `pyt tests/test_backup_entrypoint.py`.
- Attendu : FAIL sur le premier test. `BACKUP_SCRIPT` est ignoré : le vrai `/usr/local/bin/backup.sh` est introuvable, le jour est quand même abandonné, mais aucun appel curl n'a lieu.

- [ ] **Step 4 : implémentation (`entrypoint.sh`)** — remplacer les lignes 12-31 (`run_day` jusqu'à la ligne `run_day || ...` incluse) par :

```bash
BACKUP_SCRIPT="${BACKUP_SCRIPT:-/usr/local/bin/backup.sh}"

run_day() {
  local rc=0 attempt
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    if [ "$rc" = 75 ]; then
      "$BACKUP_SCRIPT" --upload-only && return 0 || rc=$?
    else
      "$BACKUP_SCRIPT" && return 0 || rc=$?
    fi
    echo "[backup] échec (code ${rc}), tentative ${attempt}/${MAX_ATTEMPTS}" >&2
    [ "$attempt" -lt "$MAX_ATTEMPTS" ] && sleep "$RETRY_DELAY"
  done
  return 1
}

# REV-281c : alerte à la source quand un jour est abandonné (le profil
# observability ne scrape pas l'état Docker : pas de règle Grafana possible).
# Corps {"text": …} accepté par Slack, Mattermost et Rocket.Chat.
alert_abandon() {
  [ -n "${BACKUP_ALERT_WEBHOOK_URL:-}" ] || return 0
  curl -fsS -m 10 -H 'Content-Type: application/json' \
    -d "{\"text\":\"[GeoStudio] sauvegarde abandonnée pour $1 après ${MAX_ATTEMPTS} tentatives\"}" \
    "$BACKUP_ALERT_WEBHOOK_URL" >/dev/null \
    || echo "[backup] ERREUR: alerte webhook non délivrée" >&2
}

LAST_RUN_DATE=""
while true; do
  now_date="$(date -u +%Y-%m-%d)"
  now_hour="$(date -u +%H)"
  if [ "$now_hour" = "$HOUR" ] && [ "$now_date" != "$LAST_RUN_DATE" ]; then
    run_day || {
      echo "[backup] ERREUR: abandon pour ${now_date} après ${MAX_ATTEMPTS} tentatives" >&2
      alert_abandon "$now_date"
    }
```

Les deux lignes suivantes (`LAST_RUN_DATE="$now_date"` et `fi`) et la fin de boucle sont inchangées.

- [ ] **Step 5 : câblage**

Dans `docker-compose.prod.yml`, service `backup`, après `BACKUP_S3_BUCKET: ${BACKUP_S3_BUCKET:-geostudio-backups}` (l.397), ajouter :

```yaml
      BACKUP_ALERT_WEBHOOK_URL: ${BACKUP_ALERT_WEBHOOK_URL:-}
```

et remplacer la fin du commentaire du healthcheck (l.403-404, « Pas de règle Grafana : le profil observability ne scrape pas l'état Docker. ») par :

```yaml
    # (planifié une fois par jour, BACKUP_HOUR). Pas de règle Grafana : le
    # profil observability ne scrape pas l'état Docker — l'alerte part de
    # l'entrypoint (BACKUP_ALERT_WEBHOOK_URL) quand un jour est abandonné.
```

Dans `.env.example`, après `BACKUP_S3_BUCKET=geostudio-backups`, ajouter :

```bash
# Webhook (Slack/Mattermost/Rocket.Chat, corps {"text": …}) appelé quand une
# journée de sauvegarde est abandonnée après BACKUP_MAX_ATTEMPTS tentatives
# (REV-281c). Vide = pas d'alerte (seul `docker ps` montre unhealthy).
BACKUP_ALERT_WEBHOOK_URL=
```

- [ ] **Step 6 : vérifier le succès**
  - Commande : `pyt tests/test_backup_offsite_rotation.py tests/test_backup_entrypoint.py tests/test_backup_upload_only.py tests/test_deployability.py`
  - Attendu : PASS. `test_deployability.py` vérifie que toute substitution du compose de prod est documentée.
  - Commande : `bash -n deploy/backup/backup.sh && bash -n deploy/backup/entrypoint.sh`
  - Attendu : aucune sortie.
  - Limite connue : `test_backup_entrypoint.py` compare l'heure UTC du test à celle du script. Un passage d'heure entre les deux (fenêtre de quelques millisecondes) ferait échouer ce test une fois : le rejouer.

- [ ] **Step 7 : commit**

```bash
git add deploy/backup/backup.sh deploy/backup/entrypoint.sh docker-compose.prod.yml .env.example core/tests/test_backup_offsite_rotation.py core/tests/test_backup_entrypoint.py
git commit -m "fix(deploy): rotation hors-site malgré un envoi en échec, alerte webhook d'abandon (rev-281)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-18: hook `actionlint` et correction des 12 constats sur les workflows (REV-281e)

**Files:**
- Modify: `.pre-commit-config.yaml` (nouveau hook après `claude-md-size`)
- Modify: `.github/workflows/ci.yml:32,63,132,152,267`, `.github/workflows/release.yml:68,146,179,192`
- Modify: `.github/workflows/desktop-etl-spike.yml:31`, `desktop-etl-sidecar-freeze.yml:32`, `desktop-etl-webdriver.yml:37`
- Modify: `CLAUDE.md:195` (« 6 hooks » → « 7 hooks »)

**Interfaces:**
- Produces : un hook pre-commit local `actionlint` (`language: docker_image`, image `rhysd/actionlint:1.7.7`), déclenché sur `^\.github/workflows/.*\.ya?ml$`, ce qui couvre aussi `_build-and-push.yml`, `release.yml` et `publish-edge.yml` (spec).
- L'image embarque `shellcheck`. Le hook distant `id: actionlint`, qui compile en Go, ne l'a pas : il sauterait en silence les constats `SC*`, d'où le choix de l'image.

**Constats réels** (mesurés pendant la rédaction avec ce hook exact, `pre-commit run actionlint --all-files`, rc=1) :
- 9 × SC2034 : variable `i` inutilisée dans `for i in $(seq ...)`, aux 9 lignes listées ci-dessus ;
- 3 × SC2086 : `$extra_args` non cité dans les 3 workflows `desktop-etl-*`. Le découpage en mots y est voulu : c'est une liste d'arguments PyInstaller.

- [ ] **Step 1 : hook (porte qui échoue)** — dans `.pre-commit-config.yaml`, après le hook `claude-md-size` (fin de fichier), ajouter avec la même indentation :

```yaml
      # REV-281e : les workflows n'étaient validés que par yaml.safe_load.
      # Image Docker (et non le hook Go distant) : elle embarque shellcheck,
      # sans lequel les constats SC* des blocs `run:` sautent en silence.
      - id: actionlint
        name: actionlint (workflows GitHub)
        language: docker_image
        entry: rhysd/actionlint:1.7.7
        files: ^\.github/workflows/.*\.ya?ml$
```

Lancer `uvx pre-commit run actionlint --all-files`.
- Attendu : `Failed`, avec 12 constats : 9 `SC2034` et 3 `SC2086`.

- [ ] **Step 2 : correction des constats**

```bash
sed -i 's/for i in \$(seq/for _ in $(seq/' .github/workflows/ci.yml .github/workflows/release.yml
grep -n 'for i in\|\$i\b' .github/workflows/ci.yml .github/workflows/release.yml
```

Attendu : le `grep` ne renvoie rien, ce qui confirme que `$i` n'était lu nulle part.

Dans chacun des trois workflows `desktop-etl-spike.yml` (l.31), `desktop-etl-sidecar-freeze.yml` (l.32) et `desktop-etl-webdriver.yml` (l.37), insérer juste avant la ligne `uv run pyinstaller ... $extra_args ...`, avec la même indentation :

```bash
          # shellcheck disable=SC2086 # découpage voulu : liste d'arguments PyInstaller
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `uvx pre-commit run actionlint --all-files`
  - Attendu : `Passed`.
  - Commande : `(cd core && uv run pytest tests/test_deployability.py -q -k workflow)`
  - Attendu : PASS. Ce sont les règles existantes sur les workflows (épinglage par SHA, timeouts).

- [ ] **Step 4 : documentation** — `CLAUDE.md:195` : remplacer `# 6 hooks (commitlint ne sort qu'au commit)` par `# 7 hooks (commitlint ne sort qu'au commit)`. Puis lancer `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold`.
- Attendu : succès, car le nombre de lignes est inchangé.

- [ ] **Step 5 : commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml .github/workflows/release.yml .github/workflows/desktop-etl-spike.yml .github/workflows/desktop-etl-sidecar-freeze.yml .github/workflows/desktop-etl-webdriver.yml CLAUDE.md
git commit -m "ci: hook actionlint et correction des 12 constats shellcheck des workflows (rev-281e)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-19: import sans géométrie — le job porte l'item dataset et son type, le shell l'ouvre (REV-282b)

**Files:**
- Modify: `core/app/ingestion/importer.py:58-61` (`ImportResult`), `:375`, `:442`
- Modify: `core/app/ingestion/tasks.py:31-56` (`_notify`) et `:159-166` (appel de succès)
- Modify: `core/app/ingestion/schemas.py:32-36` (`IngestionJobStatus`)
- Modify: `core/app/ingestion/routes.py:229-252` (`get_upload_job`)
- Modify: `core/tests/test_ingestion_importer.py:582,637,668,744`, `core/tests/test_ingestion_tasks.py:169`, `core/tests/test_ingestion_routes.py:118-123`
- Modify: `shell/src/api/types.ts:711-716`, `shell/src/api/domains/exportsIngestion.ts:93-100`, `shell/src/shell/ImportFileButton.tsx:242-254`, `shell/src/shell/ImportFileButton.test.tsx`
- Regenerate: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Produces :
  - `ImportResult.item_resource_type: str | None`, qui vaut `"dataset"` (import sans géométrie) ou `"map"` ;
  - `ImportResult.item_id` porte désormais l'item dataset dans le cas sans géométrie ;
  - `GET /v1/uploads/{job_id}` renvoie un champ de plus, `itemResourceType: str | None`. Il est résolu depuis `items.resource_type` de `job.item_id`, sans nouvelle colonne ni migration.
- Shell : `getIngestionJob` renvoie `itemResourceType?: string | null`. Quand ce champ vaut `"dataset"`, `ImportFileButton` navigue vers `/datasets/{itemId}/edit` (route existante, `shell/src/shell/routes.tsx:274`).

**Corrections de la spec :**
1. La spec cite « `/datasets/{id}` », qui n'existe pas. La route réelle est `/datasets/:pk/edit`, celle qu'emprunte déjà `NewItemButton` après création d'un dataset.
2. Bug réel trouvé en vérifiant : `ingestion/tasks._notify` code en dur `item_resource_type="dataset"` dès qu'un `item_id` existe. La notification de succès d'un import **avec** géométrie, qui crée une carte, porte donc `"dataset"`, et `NotificationBell` ouvre le mauvais éditeur. `test_ingestion_tasks.py:169` fige aujourd'hui ce défaut : l'assertion passe à `"map"`.
3. Jumelle `harvest/service.py:238-263` : le moissonnage en mode copie appelle aussi `run_import` et stocke `result.item_id` dans `harvest_records.item_id`. Une fiche moissonnée sans géométrie y portera désormais l'item dataset au lieu de `None`. C'est voulu : le panneau L4-5 lie `/items/:pk`, une page générique qui convient à un dataset. Aucun autre consommateur ne suppose une carte (vérifié par `grep -n "item_id" core/app/harvest/*.py`).

- [ ] **Step 1 : tests cœur échouants**

`core/tests/test_ingestion_importer.py` : aux lignes 582, 637 et 668, remplacer `assert result.item_id is None` par :

```python
        assert result.item_id is not None and result.item_resource_type == "dataset"
```

Remplacer le test `test_tabular_import_creates_dataset_item_in_catalog` (l.741-749) par :

```python
def test_tabular_import_creates_dataset_item_in_catalog(env):
    # P28.06 (j03-021) ; REV-282b : le résultat porte l'item dataset et son type
    Session, _t, _u = env
    result = _import_csv(env, b"a,b\n1,x\n", geometry_mode="none")
    with Session() as s:
        ds = s.execute(select(Item).where(Item.resource_type == "dataset")).scalar_one()
        cfg = configs_repo.get_config_by_item(s, item_id=ds.id).config
        assert cfg.dataset.collectionId == result.collection_id
    assert result.item_id == ds.id
    assert result.item_resource_type == "dataset"
```

Dans `test_import_map_carries_bbox_and_render_hints` (l.727), ajouter après l'appel `_import_csv(...)` :

```python
    assert result.item_resource_type == "map"
```

`core/tests/test_ingestion_tasks.py:169` : remplacer `assert notification.item_resource_type == "dataset"` par :

```python
        assert notification.item_resource_type == "map"  # REV-282b : GeoJSON géo -> carte
```

`core/tests/test_ingestion_routes.py:118-123` : ajouter `"itemResourceType": None,` au dict attendu, après `"itemId": None,`. Ajouter aux imports `from app.ingestion import repository as ingestion_repo` et `from app.items import repository as items_repo`. La fixture `env` (l.55-87) renvoie `client, Session, tenant, alice, deferred, fake_s3`. Ajouter ensuite à la fin du fichier :

```python
def test_get_upload_job_reports_the_created_item_resource_type(env):
    # REV-282b : le shell choisit /maps/{id} ou /datasets/{id}/edit sur ce champ.
    client, session_factory, tenant, user = env[:4]
    with session_factory() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="T"
        )
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k",
            filename="t.csv",
            collection_title="T",
            lat_field=None,
            lon_field=None,
        )
        ingestion_repo.mark_done(s, job_id=job.id, collection_id="ingest_t", item_id=item.id)
        s.commit()
        job_id = job.id
    body = client.get(f"/v1/uploads/{job_id}").json()
    assert body["itemId"] == item.id
    assert body["itemResourceType"] == "dataset"
```

Lancer `pyt tests/test_ingestion_importer.py tests/test_ingestion_tasks.py tests/test_ingestion_routes.py`.
- Attendu : FAIL. On voit `AttributeError: 'ImportResult' object has no attribute 'item_resource_type'`, `'dataset' == 'map'` et `KeyError: 'itemResourceType'`.

- [ ] **Step 2 : implémentation cœur**

`core/app/ingestion/importer.py` — `ImportResult` :

```python
@dataclass
class ImportResult:
    collection_id: str
    item_id: str | None
    # REV-282b : "map" (géométrie -> carte) ou "dataset" (tabulaire) ; le shell
    # et la notification choisissent l'éditeur à ouvrir sur ce type.
    item_resource_type: str | None = None
```

l.375 (branche sans géométrie) devient :

```python
        return ImportResult(
            collection_id=col.id, item_id=ds_item.id, item_resource_type="dataset"
        )
```

Mettre à jour le commentaire l.346-348 : « l'item dataset est renvoyé avec son type (REV-282b) : le shell ouvre `/datasets/{id}/edit` ».

l.442 devient :

```python
    return ImportResult(collection_id=col.id, item_id=item.id, item_resource_type="map")
```

`core/app/ingestion/tasks.py` — `_notify` gagne un paramètre `item_resource_type: str | None = None` (après `item_id`). Dans l'appel à `notify_best_effort`, remplacer `item_resource_type="dataset" if item_id is not None else None,` par `item_resource_type=item_resource_type,`. Dans l'appel de succès (l.159-166), ajouter `item_resource_type=result.item_resource_type,` après `item_id=result.item_id,`. Les deux appels d'échec passent `item_id=None` et restent inchangés.

`core/app/ingestion/schemas.py` — `IngestionJobStatus` gagne `itemResourceType: str | None = None`.

`core/app/ingestion/routes.py` — ajouter `from app.items.models import Item` aux imports, et remplacer le `return IngestionJobStatus(...)` de `get_upload_job` par :

```python
    item = session.get(Item, job.item_id) if job.item_id else None
    return IngestionJobStatus(
        status=job.status,
        errorMessage=job.error_message,
        collectionId=job.collection_id,
        itemId=job.item_id,
        itemResourceType=item.resource_type if item is not None else None,
    )
```

- [ ] **Step 3 : vérifier le cœur**
  - Commande : `pyt tests/test_ingestion_importer.py tests/test_ingestion_tasks.py tests/test_ingestion_routes.py tests/test_harvest_service.py`
  - Attendu : PASS (`test_harvest_service.py` exerce le mode copie, jumelle).
  - Commande : `(cd core && uv run lint-imports)`
  - Attendu : PASS, ingestion importe déjà `app.items`.

- [ ] **Step 4 : régénérer OpenAPI et types TS**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --stat ../core/openapi.json src/api/generated/core-schema.d.ts
```

Attendu : un diff non vide sur les deux fichiers (`itemResourceType`).

- [ ] **Step 5 : test shell échouant** — dans `shell/src/shell/ImportFileButton.test.tsx`, ajouter après `MapProbe` :

```tsx
function DatasetProbe() {
  const { pk } = useParams();
  return <div>dataset-{pk}</div>;
}
```

et dans le `<Routes>` du `Harness`, après la route `/maps/:pk` :

```tsx
            <Route path="/datasets/:pk/edit" element={<DatasetProbe />} />
```

Ajouter ensuite à la fin du fichier :

```tsx
test("REV-282b : un import qui crée un dataset ouvre son éditeur, pas /maps", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-ds", key: "t/ds.geojson" }),
    ),
    http.put("https://minio.test/upload-ds", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads", () => HttpResponse.json({ jobId: "job-ds" })),
    http.get("https://core.test/v1/uploads/job-ds", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_ds",
        itemId: "ds-7",
        itemResourceType: "dataset",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Tabulaire");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("dataset-ds-7")).toBeInTheDocument());
  expect(screen.queryByText("map-ds-7")).not.toBeInTheDocument();
});
```

Lancer `(cd shell && npx vitest run src/shell/ImportFileButton.test.tsx)`.
- Attendu : FAIL, `map-ds-7` est rendu à la place de `dataset-ds-7`.

- [ ] **Step 6 : implémentation shell**

`shell/src/api/types.ts`, type de retour de `getIngestionJob` (l.711-716), et `shell/src/api/domains/exportsIngestion.ts:93-100` : ajouter, après `itemId: string | null;` :

```ts
    itemResourceType?: string | null;
```

`shell/src/shell/ImportFileButton.tsx` : remplacer le commentaire (l.244-250) et l'appel `navigate(...)` (l.251-253) par :

```tsx
        // REV-282b : un import sans géométrie crée un item « dataset »
        // (core/app/ingestion/importer.py) — on ouvre son éditeur. itemId
        // null (job antérieur) : repli inchangé. Revue finale GAP-29 (I2) :
        // /admin/collections n'est atteignable qu'avec
        // admin.collections.manage, les autres retombent sur le catalogue.
        const fallback = canManageCollections ? "/admin/collections" : "/";
        navigate(
          !job.itemId
            ? fallback
            : job.itemResourceType === "dataset"
              ? `/datasets/${job.itemId}/edit`
              : `/maps/${job.itemId}`,
        );
```

- [ ] **Step 7 : vérifier le shell**
  - Commande : `(cd shell && npx vitest run src/shell/ImportFileButton.test.tsx src/api/domains/exportsIngestion.test.ts && npx tsc --noEmit && npm run lint && npm run format:check)`
  - Attendu : PASS. Les tests GAP-29 (I2), où `itemId` vaut `null`, gardent leur repli.
  - Commande : `(cd shell && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold)`
  - Attendu : PASS. `ImportFileButton` est dans le chrome, donc dans le bundle initial : quelques octets.

- [ ] **Step 8 : commit**

```bash
git add core/app/ingestion core/tests/test_ingestion_importer.py core/tests/test_ingestion_tasks.py core/tests/test_ingestion_routes.py core/openapi.json shell/src/api/types.ts shell/src/api/domains/exportsIngestion.ts shell/src/api/generated/core-schema.d.ts shell/src/shell/ImportFileButton.tsx shell/src/shell/ImportFileButton.test.tsx
git commit -m "fix(ingestion): l'import sans géométrie renvoie son item dataset et l'ouvre (rev-282b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-20: CSV — virgule décimale reconnue hors séparateur virgule (REV-282c)

**Files:**
- Modify: `core/app/ingestion/importer.py:25-40` (import de `sniff_delimiter`), `:106-148` (`_FLOAT_RE` et voisins), `:236-237` (appel)
- Modify: `core/tests/test_ingestion_importer.py` (à la fin)

**Interfaces:**
- Produces : `_csv_column_kind(values, decimal_comma=False)` et `_infer_csv_types(rows, decimal_comma=False)`.
- Quand le séparateur détecté n'est **pas** `,`, une valeur de la forme `-?\d+,\d{1,2}` compte comme décimale et se convertit en `float` (« 1,5 » donne 1.5).
- Ambiguïté tranchée par la spec : « 1,234 » (trois chiffres, milliers ou décimale) reste du texte. Avec un séparateur `,`, rien ne change.

- [ ] **Step 1 : tests échouants** — ajouter à la fin de `core/tests/test_ingestion_importer.py` :

```python
def test_csv_column_kind_decimal_comma_only_when_separator_is_not_comma():
    # REV-282c : « 1,5 » est décimal seulement si la virgule n'est pas le séparateur ;
    # « 1,234 » (milliers ou décimale ?) reste ambigu, donc texte.
    from app.ingestion.importer import _csv_column_kind

    assert _csv_column_kind(["1,5", "2,25", "3"], decimal_comma=True) == "float"
    assert _csv_column_kind(["1,5"]) is None
    assert _csv_column_kind(["1,234"], decimal_comma=True) is None


def test_semicolon_csv_with_decimal_comma_imports_numbers(env):
    # REV-282c : export Excel FR typique (« ; » + virgule décimale)
    Session, _t, _u = env
    result = _import_csv(env, b"nom;surf\nA;1,5\nB;2,25\n", geometry_mode="none")
    with Session() as s:
        rows = (
            s.execute(text(f"SELECT surf FROM public.{result.collection_id} ORDER BY surf"))
            .scalars()
            .all()
        )
    assert rows == [1.5, 2.25]
```

Lancer `pyt tests/test_ingestion_importer.py -k "decimal_comma"`.
- Attendu : FAIL, `TypeError: _csv_column_kind() got an unexpected keyword argument 'decimal_comma'`. Le second test échoue aussi : `['1,5', '2,25']` reste texte.

- [ ] **Step 2 : implémentation** — dans `core/app/ingestion/importer.py` :

Ajouter `sniff_delimiter,` à la liste importée depuis `app.ingestion.parsers` (ordre alphabétique, après `parse_xml_generic,`).

Après `_FLOAT_RE = ...` (l.106), ajouter :

```python
# REV-282c : virgule décimale (export FR), seulement hors séparateur « , » ;
# 1 ou 2 décimales — « 1,234 » (milliers ou décimale ?) reste du texte.
_DECIMAL_COMMA_RE = re.compile(r"^-?\d+,\d{1,2}$")
```

Dans `_convert_csv_value`, remplacer `return float(value)` par :

```python
        return float(value.replace(",", "."))
```

Remplacer la signature et le test float de `_csv_column_kind` :

```python
def _csv_column_kind(values: list[str], decimal_comma: bool = False) -> str | None:
    if not values:
        return None
    if all(_INT_RE.match(v) for v in values):
        return "int"
    if all(
        _INT_RE.match(v)
        or _FLOAT_RE.match(v)
        or (decimal_comma and _DECIMAL_COMMA_RE.match(v))
        for v in values
    ):
        return "float"
```

La suite de la fonction (dates) est inchangée.

Dans `_infer_csv_types`, changer la signature en `def _infer_csv_types(rows: list, decimal_comma: bool = False) -> None:` et l'appel interne en `kind = _csv_column_kind(values, decimal_comma)`.

Remplacer l'appel l.236-237 :

```python
    if fmt == "csv":
        # même détection que parse_csv_latlon (décodage déjà validé par lui)
        _infer_csv_types(
            rows, decimal_comma=sniff_delimiter(content.decode("utf-8-sig")) != ","
        )
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_ingestion_importer.py tests/test_ingestion_parsers.py`
  - Attendu : PASS. `test_csv_column_kind_edge_cases` et `test_csv_import_infers_integer_decimal_and_date_columns` sont inchangés.

- [ ] **Step 4 : commit**

```bash
git add core/app/ingestion/importer.py core/tests/test_ingestion_importer.py
git commit -m "fix(ingestion): virgule décimale reconnue dans un csv non séparé par des virgules (rev-282c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-21: message 409 de suppression orienté utilisateur (REV-282e)

**Files:**
- Modify: `core/app/configs/repository.py` (après `find_referencing_config_kinds`, l.187-231)
- Modify: `core/app/collections/routes.py:866-871`, `core/app/configs/routes.py:101-111`
- Modify: `core/tests/test_collections_routes.py:574-575`, `core/tests/test_configs_delete_reverse_references.py:87-88`

**Interfaces:** Produces : `configs_repo.referencing_message(kinds: list[str]) -> str`, par exemple « Suppression impossible : encore utilisé par une règle d'alerte, un jeu de données. Supprimez d'abord ces éléments. ». Le statut 409 et le corps RFC 7807 ne changent pas : seul `detail` change, et le shell l'affiche déjà (`ApiError`, Vague B).

**Correction de la spec :** la spec cite `collections/routes.py:658`. La garde est en réalité aux lignes 866-871. La **jumelle** `configs/routes.py:101-111` (`_require_no_reverse_references`, qui sert `DELETE /items/{id}`, `/configs/by-item/{id}` et `/configs/{id}`) porte le même message technique : elle est traitée aussi (piège n°14). Cas fréquent : toute collection importée sans géométrie a son item dataset (P28.06), donc sa suppression renvoie toujours ce 409.

- [ ] **Step 1 : tests échouants**

`core/tests/test_collections_routes.py:575` : remplacer `assert "dataset" in response.json()["detail"]` par :

```python
    assert response.json()["detail"] == (
        "Suppression impossible : encore utilisé par un jeu de données. "
        "Supprimez d'abord ces éléments."
    )
```

`core/tests/test_configs_delete_reverse_references.py:88` : remplacer `assert "alert" in response.json()["detail"]` par :

```python
    assert response.json()["detail"] == (
        "Suppression impossible : encore utilisé par une règle d'alerte. "
        "Supprimez d'abord ces éléments."
    )
```

Lancer `pyt tests/test_collections_routes.py tests/test_configs_delete_reverse_references.py -k "referenc or 409"`.
- Attendu : FAIL, `'still referenced by config kind(s): dataset' == ...`.

- [ ] **Step 2 : implémentation**

Dans `core/app/configs/repository.py`, juste après `find_referencing_config_kinds` :

```python
_KIND_LABELS = {
    "alert": "une règle d'alerte",
    "report": "un rapport planifié",
    "dataset": "un jeu de données",
}


def referencing_message(kinds: list[str]) -> str:
    """REV-282e : detail du 409 de suppression, lisible par l'utilisateur."""
    labels = ", ".join(_KIND_LABELS.get(k, k) for k in kinds)
    return f"Suppression impossible : encore utilisé par {labels}. Supprimez d'abord ces éléments."
```

`core/app/collections/routes.py:868-871` : remplacer `detail=f"still referenced by config kind(s): {', '.join(referencing)}",` par `detail=configs_repo.referencing_message(referencing),`.

`core/app/configs/routes.py:108-111` : remplacer la même ligne par `detail=repo.referencing_message(referencing),`.

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_collections_routes.py tests/test_configs_delete_reverse_references.py tests/test_items_routes.py`
  - Attendu : PASS.
  - Commande : `grep -rn "still referenced by config" core/app shell/src shell/e2e`
  - Attendu : seul `shell/src/api/itemClient.test.ts:323,329` reste. C'est un detail simulé qui teste le relais générique du message, pas le texte du cœur : on le laisse.

- [ ] **Step 4 : commit**

```bash
git add core/app/configs/repository.py core/app/collections/routes.py core/app/configs/routes.py core/tests/test_collections_routes.py core/tests/test_configs_delete_reverse_references.py
git commit -m "fix(core): message du 409 de suppression d'un élément encore référencé, lisible (rev-282e)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-22: tuiles MVT — `ETag` et 304 sur `If-None-Match` (REV-283b)

**Files:**
- Modify: `core/app/features/tiles.py:12-15` (imports), `:137-148` (signature), `:186-198` (réponse)
- Modify: `core/tests/test_features_tiles_cache.py`

**Interfaces:**
- Produces : toute tuile 200 porte `ETag: "<sha256 des octets, 32 hex>"`.
- Une requête dont `If-None-Match` contient cet ETag reçoit 304 sans corps, avec les mêmes `Cache-Control`, `Vary` et `ETag`. La comparaison est faible : la forme `W/` et `*` sont acceptées (RFC 9110 §13.1.2).
- Le paramètre est lu par `Request`, pas `Header(...)` : l'OpenAPI ne change pas, donc pas de régénération.
- La tuile reste calculée (la RLS s'applique à chaque requête). Le gain porte sur la bande passante, pas sur le coût SQL.

- [ ] **Step 1 : tests échouants** — dans `core/tests/test_features_tiles_cache.py`, extraire la préparation du test existant dans un helper et ajouter deux tests. Remplacer tout le bloc à partir de `def test_privileged_tile_of_public_collection_is_private_and_varies` par :

```python
def _tile_client(monkeypatch):
    @contextmanager
    def null_scope(session, tenant_id, *, masked=False):
        yield

    info = TableInfo(
        table_name="employees",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=False),
            ColumnInfo(name="nom", type="string", required=True),
            ColumnInfo(name="salary", type="integer", required=False),
        ],
    )
    col = SimpleNamespace(
        id="employees",
        table_name="employees",
        tenant_id="default",
        is_public=True,
        sensitive_fields=["salary"],
    )
    app = create_app()
    session = _RecordingSession()
    monkeypatch.setattr(tiles_module, "get_collection_for_read", lambda s, u, c, *, guest=None: col)
    monkeypatch.setattr(tiles_module, "quote_ident", lambda s, name: f'"{name}"')
    app.dependency_overrides[db.get_session] = lambda: session
    app.dependency_overrides[get_current_user_optional] = lambda: SimpleNamespace(id="u")
    app.dependency_overrides[get_introspector] = lambda: lambda s, t: info
    app.dependency_overrides[get_rls_scope] = lambda: null_scope
    app.dependency_overrides[get_masked_for_user] = lambda: False  # porte data.view_sensitive
    return TestClient(app), session


_TILE = "/v1/collections/employees/tiles/0/0/0.mvt"
_AUTH = {"Authorization": "Bearer x"}


def test_privileged_tile_of_public_collection_is_private_and_varies(monkeypatch):
    client, session = _tile_client(monkeypatch)
    r = client.get(_TILE, headers=_AUTH)
    assert r.status_code == 200
    assert '"salary"' in session.calls[1][0]  # colonne sensible projetée dans la tuile
    assert r.headers["cache-control"] == "private, max-age=300"
    assert r.headers["vary"] == "Authorization"


def test_tile_etag_revalidates_to_304(monkeypatch):
    # REV-283b : une tuile inchangée se revalide sans renvoyer ses octets.
    client, _session = _tile_client(monkeypatch)
    etag = client.get(_TILE, headers=_AUTH).headers["etag"]
    assert etag.startswith('"') and len(etag) == 34
    for candidate in (etag, f"W/{etag}", f'"autre", {etag}'):
        r = client.get(_TILE, headers={**_AUTH, "If-None-Match": candidate})
        assert r.status_code == 304, candidate
        assert r.content == b""
        assert r.headers["etag"] == etag
        assert r.headers["vary"] == "Authorization"  # conservé (c01-007)


def test_tile_with_stale_etag_is_served_in_full(monkeypatch):
    client, _session = _tile_client(monkeypatch)
    r = client.get(_TILE, headers={**_AUTH, "If-None-Match": '"perime"'})
    assert r.status_code == 200
    assert r.content == b"\x1a\x02"
```

Lancer `(cd core && uv run pytest tests/test_features_tiles_cache.py -q)`.
- Attendu : FAIL, `KeyError: 'etag'`. Le test existant passe toujours.

- [ ] **Step 2 : implémentation** — dans `core/app/features/tiles.py` :

Imports : ajouter `import hashlib` (avant `import functools`, ordre ruff) et `Request` à l'import fastapi (`from fastapi import APIRouter, Depends, HTTPException, Request, Response`).

Ajouter, avant `@router.get("/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")` :

```python
def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Comparaison faible (RFC 9110 §13.1.2) : liste, `W/` et `*` acceptés."""
    if not if_none_match:
        return False
    return any(t.strip().removeprefix("W/") in (etag, "*") for t in if_none_match.split(","))
```

Ajouter `request: Request,` comme premier paramètre après `y: int,` dans `get_collection_tile`.

Remplacer la fin de la fonction, de `headers = {"Cache-Control": ...` jusqu'au `return Response(...)` final, par :

```python
    content = bytes(tile)
    # REV-283b : revalidation à 304 — même empreinte pour mêmes octets, quelle
    # que soit l'identité (Vary: Authorization garde les caches séparés).
    etag = '"' + hashlib.sha256(content).hexdigest()[:32] + '"'
    headers = {
        "Cache-Control": f"{visibility}, max-age=300",
        "Vary": "Authorization",
        "ETag": etag,
    }
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    if feature_count > MAX_TILE_FEATURES:
        headers["X-Tile-Truncated"] = "true"
    return Response(content=content, media_type=MVT_MEDIA_TYPE, headers=headers)
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_features_tiles_cache.py tests/test_features_tiles.py tests/test_features_tiles_postgis.py tests/test_features_tiles_guest_access_postgis.py`
  - Attendu : PASS.
  - Commande : `(cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py /tmp/o.json && diff <(python3 -m json.tool openapi.json) <(python3 -m json.tool /tmp/o.json))`
  - Attendu : diff vide, l'OpenAPI ne change pas.

- [ ] **Step 4 : commit**

```bash
git add core/app/features/tiles.py core/tests/test_features_tiles_cache.py
git commit -m "feat(core): etag et 304 sur if-none-match pour les tuiles mvt (rev-283b)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-23: plafond d'export ArcGIS moissonné aligné sur `CORE_EXPORT_ITEMS_MAX` (REV-283c)

**Files:**
- Modify: `core/app/harvest/routes.py:550`
- Modify: `core/tests/test_harvest_dataset_arcgis_export_routes.py` (à la fin)

**Interfaces:**
- Produces : `harvest_routes._EXPORT_ITEMS_CAP` est la même valeur que `features.routes.EXPORT_ITEMS_CAP` (`core/app/features/routes.py:387`, lue de `CORE_EXPORT_ITEMS_MAX`, 100 000 par défaut).
- Le nom local est conservé : `test_export_items_caps_at_10000_entities` le monkeypatche, l.304.
- Consumes : `app.features.routes`. `harvest` est au-dessus de `features` dans le contrat de couches (`core/pyproject.toml:333`).

**Corrections de la spec :**
- La constante source est à la ligne 387, pas 383.
- `CORE_EXPORT_ITEMS_MAX` est déjà dans l'`environment:` du service core (`docker-compose.yml:341`) et l'overlay prod en hérite, car `docker-compose.prod.yml` ne redéclare pas `environment:` en `!override`. Elle est documentée dans `.env.example:257`. Aucun câblage à ajouter.

- [ ] **Step 1 : test échouant** — ajouter à la fin de `core/tests/test_harvest_dataset_arcgis_export_routes.py` :

```python
def test_export_items_cap_is_the_shared_core_export_cap():
    # REV-283c : une seule source (CORE_EXPORT_ITEMS_MAX), pas un 10 000 local.
    from app.features.routes import EXPORT_ITEMS_CAP
    from app.harvest import routes as harvest_routes_module

    assert harvest_routes_module._EXPORT_ITEMS_CAP == EXPORT_ITEMS_CAP
```

Lancer `(cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -q -k shared_core_export_cap)`.
- Attendu : FAIL, `assert 10000 == 100000`.

- [ ] **Step 2 : implémentation** — `core/app/harvest/routes.py:550` : remplacer `_EXPORT_ITEMS_CAP = 10_000` par :

```python
# REV-283c : même plafond que l'export de collection (CORE_EXPORT_ITEMS_MAX).
from app.features.routes import EXPORT_ITEMS_CAP as _EXPORT_ITEMS_CAP  # noqa: E402
```

Si ruff (`I001`/`E402`) refuse un import hors tête de module, placer `from app.features.routes import EXPORT_ITEMS_CAP as _EXPORT_ITEMS_CAP` dans le bloc d'imports en tête (ordre alphabétique, après `from app.errors import ...`), retirer le `# noqa` et supprimer la ligne 550.

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_harvest_dataset_arcgis_export_routes.py && (cd core && uv run lint-imports && uv run ruff check app/harvest/routes.py)`
  - Attendu : PASS. `test_export_items_caps_at_10000_entities` passe toujours, car il monkeypatche le nom local.

- [ ] **Step 4 : commit**

```bash
git add core/app/harvest/routes.py core/tests/test_harvest_dataset_arcgis_export_routes.py
git commit -m "fix(harvest): plafond d'export arcgis lu de core_export_items_max (rev-283c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-24: la vue d'une carte démontée ne reste plus publiée (REV-283d)

**Files:**
- Modify: `shell/src/map/viewportTiles.ts:4-19`
- Modify: `shell/src/map/MapView.tsx:335,397` (publications) et `:429-434` (nettoyage)
- Modify: `shell/src/map/viewportTiles.test.ts`

**Interfaces:**
- Produces : `publishViewport(v, by?)` mémorise l'émetteur, et `clearViewport(by)` remet le store à `null` seulement si `by` est le dernier émetteur. Une carte qui se démonte n'efface donc pas la vue d'une autre carte encore montée.
- Consumes : `useViewport()` de `LayersPanel.tsx:237`, inchangé. Quand la valeur vaut `null`, il retombe sur la seule tuile 0/0/0 (l.241).

**Choix (spec : « store par carte ou publication à null au démontage ») :** la publication à `null` suffit. Un store par carte supposerait de passer un identifiant de carte à `LayersPanel`, qui n'en a pas. La note `ponytail:` existante, qui documente le store global, est gardée et mise à jour.

- [ ] **Step 1 : test échouant** — dans `shell/src/map/viewportTiles.test.ts`, remplacer la première ligne d'import par :

```ts
import { act, renderHook } from "@testing-library/react";
import { expect, test } from "vitest";
import { clearViewport, publishViewport, tileKeys, useViewport } from "./viewportTiles";
```

puis ajouter à la fin :

```ts
test("REV-283d : la vue d'une carte démontée n'est plus publiée", () => {
  const mapA = {};
  const mapB = {};
  const { result } = renderHook(() => useViewport());
  act(() => publishViewport({ zoom: 5, bounds: [-5, 41, 9, 51] }, mapA));
  act(() => clearViewport(mapB)); // B n'a pas publié en dernier : sans effet
  expect(result.current).not.toBeNull();
  act(() => clearViewport(mapA));
  expect(result.current).toBeNull();
});
```

Lancer `(cd shell && npx vitest run src/map/viewportTiles.test.ts)`.
- Attendu : FAIL, `clearViewport` n'est pas exporté.

- [ ] **Step 2 : implémentation** — dans `shell/src/map/viewportTiles.ts`, remplacer les lignes 4-19 par :

```ts
// P29.06 : vue courante de la carte (publiée par MapView), lue par LayersPanel
// pour sonder les tuiles réellement affichées plutôt que la seule 0/0/0.
// ponytail: un seul « dernier viewport » global — deux cartes montées en même
// temps (widgets) se partagent la valeur ; un store par carte si le besoin vient.
// REV-283d : la carte qui se démonte retire sa vue (clearViewport), sans
// effacer celle d'une autre carte qui aurait publié depuis.
export type Viewport = { zoom: number; bounds: [number, number, number, number] };

let current: Viewport | null = null;
let owner: unknown = null;
const listeners = new Set<() => void>();

export function publishViewport(v: Viewport, by?: unknown): void {
  owner = by ?? null;
  // Clé stable (zoom entier + tuiles couvertes) : un simple pan dans les mêmes
  // tuiles ne doit pas re-notifier.
  if (current && tileKeys(current).join() === tileKeys(v).join()) return;
  current = v;
  listeners.forEach((l) => l());
}

export function clearViewport(by: unknown): void {
  if (owner !== by || current === null) return;
  current = null;
  owner = null;
  listeners.forEach((l) => l());
}
```

Dans `shell/src/map/MapView.tsx` :
- l.21 : `import { clearViewport, publishViewport } from "./viewportTiles";`
- l.335-338 : ajouter `map` en second argument, soit `publishViewport({ zoom: ..., bounds: ... }, map);`
- l.397 : `publishViewport({ zoom: map.getZoom(), bounds }, map);`
- dans le nettoyage de l'effet, juste avant `map.remove();` (l.434) : `clearViewport(map);`

- [ ] **Step 3 : vérifier le succès**
  - Commande : `(cd shell && npx vitest run src/map/viewportTiles.test.ts src/map/LayersPanel.test.tsx src/map/MapView.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check)`
  - Attendu : PASS. `LayersPanel.test.tsx:490` publie sans émetteur, ce qui reste valide.
  - Commande : `(cd shell && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold)`
  - Attendu : PASS. Cette mesure couvre aussi L4-10 (`apiErrorMessage`, bundle initial).

- [ ] **Step 4 : commit**

```bash
git add shell/src/map/viewportTiles.ts shell/src/map/viewportTiles.test.ts shell/src/map/MapView.tsx
git commit -m "fix(shell): la vue d'une carte démontée n'est plus publiée au panneau des couches (rev-283d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-25: quota dépassé pendant un run de pipeline — statut lisible et notification (REV-288a)

**Files:**
- Modify: `core/app/pipelines/jobs.py:14-28` (imports) et `:270` (clause `except`)
- Modify: `core/tests/test_pipeline_jobs.py` (à la fin)

**Interfaces:**
- Consumes : `QuotaExceededError` (`core/app/quotas/service.py:183`). Les écritures de pipeline la lèvent déjà via le point unique de création : `items/repository.py:215` et `collections/repository.py:99` appellent `check_quota_or_raise`.
- Produces : le run passe `failed` avec `error` = le message du quota, sans le préfixe « erreur interne : ». La notification d'échec porte ce même message.

**Vérification (spec : « vérifier que les tâches pipeline d'écriture appellent `check_quota_or_raise` ») :** c'est le cas par construction. `_write_dataset` crée ses items et collections par les repositories qui portent la garde (P26, point unique). En revanche, l'exception tombait dans `except Exception`, avec un `logger.exception` (trace complète pour un refus métier attendu) et le préfixe « erreur interne ». Jumelle `harvest/jobs.py` : déjà lisible, comme la spec le note. La jumelle `ingestion/tasks.py:153` sert de modèle.

- [ ] **Step 1 : test échouant** — ajouter à la fin de `core/tests/test_pipeline_jobs.py` :

```python
def test_quota_exceeded_during_run_is_a_readable_failure(env, monkeypatch):
    # REV-288a : refus de quota = échec métier lisible, pas « erreur interne ».
    from app.quotas.service import QuotaExceededError

    app, Session, tenant, user, item_id = env
    message = "quota d'items du tenant dépassé : 1/1"

    def _over_quota(*args, **kwargs):
        raise QuotaExceededError("items", 1, 1, message)

    monkeypatch.setattr(pipeline_jobs, "run_pipeline", _over_quota)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.error == message
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.status == "failure"
        assert notification.error_message == message
```

Lancer `pyt tests/test_pipeline_jobs.py -k quota_exceeded`.
- Attendu : FAIL, `assert "erreur interne : quota d'items ..." == "quota d'items ..."`.

- [ ] **Step 2 : implémentation** — dans `core/app/pipelines/jobs.py` :
- Ajouter l'import `from app.quotas.service import QuotaExceededError`, en ordre alphabétique après `from app.pipelines.runtime import ...`.
- Remplacer `except (PipelineRuntimeError, ValueError) as exc:` (l.270) par :

```python
    # REV-288a : un quota atteint est un refus métier (message destiné à
    # l'utilisateur), même traitement que l'ingestion (ingestion/tasks.py).
    except (PipelineRuntimeError, ValueError, QuotaExceededError) as exc:
```

- [ ] **Step 3 : vérifier le succès**
  - Commande : `pyt tests/test_pipeline_jobs.py && (cd core && uv run lint-imports)`
  - Attendu : PASS. `app.quotas` est sous `app.pipelines` dans le contrat.

- [ ] **Step 4 : commit**

```bash
git add core/app/pipelines/jobs.py core/tests/test_pipeline_jobs.py
git commit -m "fix(pipelines): quota dépassé pendant un run, échec lisible et notifié (rev-288a)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L4-26: sitemap paginé au-delà du plafond, URL de vignette dérivée du déploiement (REV-289a, REV-289b)

**Files:**
- Modify: `core/app/public/routes.py:21-25` (commentaire du plafond), `:85-86` (`_thumb_url`), `:127-140` (sitemap), `:148` (robots, inchangé), `:171,188` (appels de `_thumb_url`)
- Modify: `docker-compose.yml:442,448` et `docker-compose.prod.yml:218,223` (routeur `seo-static`)
- Modify: `core/tests/test_public_seo.py`, `core/tests/test_deployability.py` (après `test_seo_router_is_not_gated_by_admin_auth`)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl:178-180,309`
- Regenerate: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Produces :
  - au-delà de `_SITEMAP_MAX_URLS` URL publiques (items publiés, puis datasets publics), `GET|HEAD /v1/public/sitemap.xml` rend un `<sitemapindex>` qui pointe vers `{PUBLIC_BASE_URL}/sitemap-{n}.xml` ;
  - nouvelle route `GET|HEAD /v1/public/sitemap-{n}.xml` (n ≥ 1) qui sert la tranche n, et 404 hors plage ;
  - sous le plafond, `/sitemap.xml` reste un `<urlset>` identique à aujourd'hui.
- Traefik : `seo-static` route aussi `/sitemap-N.xml` vers `/v1/public/sitemap-N.xml`.
- (b) L'URL `og:image` vaut `{CORE_BASE_URL}/v1{thumbnailUrl}` : même réglage que l'importeur (`ingestion/importer.py:393`). Avant, c'était `{PUBLIC_BASE_URL}/api/v1{thumbnailUrl}`, qui codait en dur le préfixe Traefik `/api`. La prod pose `CORE_BASE_URL=https://${GEOSTUDIO_PUBLIC_HOST}/api` (`docker-compose.prod.yml:173`) : le résultat y est identique, et correct en dev (`http://localhost:8200`).

**Corrections de la spec :**
- (a) Sans règle Traefik, `/sitemap-N.xml` tomberait dans le catch-all du shell, qui renvoie le HTML de la SPA. Le routeur `seo-static` est donc étendu dans les deux compose. `$$` est requis pour un `$` littéral (commentaire `docker-compose.yml:439-441`).
- (b) `grep -rn '/api/v1' core/app` ne trouve que `public/routes.py:86`, aucune autre occurrence.

- [ ] **Step 1 : tests échouants** — ajouter à la fin de `core/tests/test_public_seo.py` :

```python
def test_sitemap_becomes_an_index_beyond_the_cap(client, monkeypatch):
    # REV-289a : au-delà du plafond (abaissé à 2), index + tranches.
    from app.public import routes as public_routes

    monkeypatch.setattr(public_routes, "_SITEMAP_MAX_URLS", 2)
    for slug in ("s1", "s2"):
        _publish(client, _create_site(client, slug.upper(), slug))
    _make_collection(client, "ouvert", "Ouvert", is_public=True)  # 3e URL

    del client.app.dependency_overrides[get_current_user]
    index = client.get("/v1/public/sitemap.xml").text
    assert "<sitemapindex" in index
    assert f"<loc>{_PUBLIC_BASE_URL}/sitemap-1.xml</loc>" in index
    assert f"<loc>{_PUBLIC_BASE_URL}/sitemap-2.xml</loc>" in index
    assert "sitemap-3.xml" not in index

    first = client.get("/v1/public/sitemap-1.xml")
    assert first.status_code == 200
    assert first.text.count("<url>") == 2
    second = client.get("/v1/public/sitemap-2.xml").text
    assert second.count("<url>") == 1
    assert f"{_PUBLIC_BASE_URL}/public/datasets/ouvert</loc>" in second
    assert client.get("/v1/public/sitemap-3.xml").status_code == 404
    assert client.get("/v1/public/sitemap-0.xml").status_code == 404
    assert client.head("/v1/public/sitemap-1.xml").status_code == 200


def test_sitemap_under_the_cap_stays_a_urlset(client):
    _publish(client, _create_site(client, "Portail", "portail"))
    del client.app.dependency_overrides[get_current_user]
    body = client.get("/v1/public/sitemap.xml").text
    assert "<urlset" in body and "<sitemapindex" not in body
    assert client.get("/v1/public/sitemap-1.xml").status_code == 404  # pas de tranche
```

`_make_collection` est le helper existant du fichier, celui qu'utilise `test_sitemap_covers_sites_items_and_public_datasets_with_lastmod`.

Pour (b), dans `test_item_social_preview_with_public_thumbnail`, ajouter `monkeypatch` aux paramètres du test, puis en tête du corps :

```python
    monkeypatch.setenv("CORE_BASE_URL", "https://api.gis.example.fr")  # REV-289b
```

et remplacer la ligne `thumb = f"{_PUBLIC_BASE_URL}/api/v1/public/items/{item_id}/thumbnail"` par :

```python
    thumb = f"https://api.gis.example.fr/v1/public/items/{item_id}/thumbnail"
```

Dans `core/tests/test_deployability.py`, ajouter après `test_seo_router_is_not_gated_by_admin_auth` :

```python
@pytest.mark.parametrize("compose", [BASE, PROD], ids=["base", "prod"])
def test_seo_static_router_serves_sitemap_slices(compose):
    """REV-289a : /sitemap-N.xml (tranches de l'index) doit atteindre le cœur,
    sinon le catch-all shell répond le HTML de la SPA aux robots."""
    labels = _traefik_labels(services(compose)["core"])
    assert "sitemap-[0-9]+" in labels["traefik.http.routers.seo-static.rule"]
    prefix = "traefik.http.middlewares.seo-static-rewrite.replacepathregex"
    regex = labels[f"{prefix}.regex"].replace("$$", "$")
    replacement = labels[f"{prefix}.replacement"].replace("$$1", r"\1")
    for path in ("/sitemap.xml", "/sitemap-3.xml", "/robots.txt"):
        assert re.sub(regex, replacement, path) == f"/v1/public{path}", path
```

`re` est déjà importé en tête de `test_deployability.py` (l.58).

Lancer `(cd core && uv run pytest tests/test_public_seo.py tests/test_deployability.py -q -k "sitemap or thumbnail or seo_static")`.
- Attendu : FAIL :
  - `assert "<sitemapindex" in index` ;
  - l'URL `og:image` reste en `https://gis.example.fr/api/v1/...` ;
  - `assert "sitemap-[0-9]+" in ...`.

- [ ] **Step 2 : implémentation `public/routes.py`**

Remplacer le commentaire et la constante l.21-25 par :

```python
# Plafond du protocole sitemaps (50 000 URL par fichier). Appel interne : la
# borne pageSize<=100 ne vaut que pour la route anonyme /items. REV-289a :
# au-delà, /sitemap.xml devient un index de tranches /sitemap-{n}.xml.
_SITEMAP_MAX_URLS = 50_000
```

Remplacer `_thumb_url` (l.85-86) par :

```python
def _thumb_url(item: ItemRead) -> str | None:
    # REV-289b : URL publique du cœur = réglage de déploiement (comme l'importeur),
    # plus de préfixe Traefik « /api » codé en dur.
    if not item.thumbnailUrl:
        return None
    core = os.environ.get("CORE_BASE_URL", "http://localhost:8200").rstrip("/")
    return f"{core}/v1{item.thumbnailUrl}"
```

Aux deux appels (l.171 et l.188), remplacer `image_url=_thumb_url(base_url, item),` par `image_url=_thumb_url(item),`. Dans ces deux fonctions, la variable locale `base_url = os.environ["PUBLIC_BASE_URL"]` n'a alors plus d'usage : la supprimer (sinon ruff `F841`).

Remplacer la route `public_sitemap` (l.127-140) par :

```python
def _sitemap_slice(session: Session, n: int) -> tuple[list[ItemRead], list[str], int]:
    """Tranche n (1-based) de _SITEMAP_MAX_URLS URL — items publiés puis
    datasets publics — et le nombre total d'URL publiques."""
    cap = _SITEMAP_MAX_URLS
    page = items_repo.list_published_items(session, page=n, page_size=cap)
    datasets = [
        c.id
        for c in collections_repo.list_visible_collections(
            session, tenant_id=DEFAULT_TENANT_SLUG, user_id=None, can_see_all=False
        )
    ]
    start = max(0, (n - 1) * cap - page.total)
    return page.items, datasets[start : start + cap - len(page.items)], page.total + len(datasets)


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml", headers=_CACHE)


@router.get("/sitemap.xml", response_class=Response)
@router.head("/sitemap.xml", include_in_schema=False)
def public_sitemap(session: Session = Depends(get_session, scope="function")) -> Response:
    base_url = os.environ["PUBLIC_BASE_URL"]
    items, dataset_ids, total = _sitemap_slice(session, 1)
    if total <= _SITEMAP_MAX_URLS:
        return _xml(_render_sitemap_xml(base_url, items, dataset_ids))
    slices = -(-total // _SITEMAP_MAX_URLS)  # division entière par excès
    entries = "".join(
        f"<sitemap><loc>{xml_escape(f'{base_url}/sitemap-{n}.xml')}</loc></sitemap>"
        for n in range(1, slices + 1)
    )
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    return _xml(
        f'<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="{ns}">{entries}</sitemapindex>'
    )


@router.get("/sitemap-{n}.xml", response_class=Response)
@router.head("/sitemap-{n}.xml", include_in_schema=False)
def public_sitemap_slice(
    n: int, session: Session = Depends(get_session, scope="function")
) -> Response:
    items, dataset_ids, total = _sitemap_slice(session, max(n, 1))
    # Pas de tranche sous le plafond (/sitemap.xml est alors un urlset), ni hors plage.
    if n < 1 or total <= _SITEMAP_MAX_URLS or not (items or dataset_ids):
        raise HTTPException(status_code=404, detail="sitemap slice not found")
    return _xml(_render_sitemap_xml(os.environ["PUBLIC_BASE_URL"], items, dataset_ids))
```

- [ ] **Step 3 : implémentation Traefik**

Dans `docker-compose.yml:442`, remplacer la règle par :

```yaml
      - traefik.http.routers.seo-static.rule=Host(`${DOMAIN}`) && (Path(`/sitemap.xml`) || PathRegexp(`^/sitemap-[0-9]+\.xml$$`) || Path(`/robots.txt`))
```

et l.448 par :

```yaml
      - traefik.http.middlewares.seo-static-rewrite.replacepathregex.regex=^/(sitemap(?:-[0-9]+)?\.xml|robots\.txt)$$
```

Dans `docker-compose.prod.yml:218` et `:223`, faire la même chose avec `Host(`${GEOSTUDIO_PUBLIC_HOST}`)`. Le reste de chaque ligne est identique. `PathRegexp` est une règle de routeur Traefik v3 (image `traefik:v3.7.13`, `docker-compose.yml:942`).

- [ ] **Step 4 : inventaire et OpenAPI**

```bash
python3 - <<'EOF'
import json
p = "docs/revue/inventaire-fonctionnalites.jsonl"
lines = open(p, encoding="utf-8").read().splitlines()
for i, verb in ((177, "GET"), (178, "GET"), (179, "GET"), (308, "HEAD")):
    d = json.loads(lines[i])
    rest = d["surfaces"]["rest"]
    rest.append(f"{verb} /v1/public/sitemap-{{n}}.xml")
    d["surfaces"]["rest"] = sorted(set(rest))
    lines[i] = json.dumps(d, ensure_ascii=False)
open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
EOF
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types && cd ..
(cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check)
git diff --stat docs/revue/inventaire-fonctionnalites.jsonl
```

Attendus :
- `--check` réussit : la nouvelle surface est inventoriée.
- Le diff de l'inventaire touche exactement 4 lignes : `json.dumps(..., ensure_ascii=False)` reproduit à l'identique les 310 lignes existantes (vérifié).

- [ ] **Step 5 : vérifier le succès**
  - Commande : `(cd core && uv run pytest tests/test_public_seo.py tests/test_deployability.py tests/test_public_routes.py -q && uv run ruff check app/public && uv run ruff format --check app/public)`
  - Attendu : PASS.
  - Commande : `grep -rn "/api/v1" core/app`
  - Attendu : aucune sortie.

- [ ] **Step 6 : commit**

```bash
git add core/app/public/routes.py core/tests/test_public_seo.py core/tests/test_deployability.py docker-compose.yml docker-compose.prod.yml docs/revue/inventaire-fonctionnalites.jsonl core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(public): index de sitemaps au-delà du plafond, vignette sur core_base_url (rev-289)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Notes de vérification

Constats faits en vérifiant la spec contre le code (piège n°12). Chaque tâche les rappelle à l'endroit où ils s'appliquent.

- **REV-274(c)** : `from app.cdc.consumer import SLOT_NAME` dans `instance/` est interdit par le contrat de couches (`instance` est sous `cdc`). La constante locale est gardée, avec un test d'égalité (L4-1).
- **REV-274(d) / 281(g)** : liaison des ports d'outillage à `127.0.0.1` et entrypoint Traefik `--entrypoints.traefik.address=127.0.0.1:8080`, vérifiés empiriquement avant rédaction (L4-2).
- **REV-276(c)** : pas de réécriture des URL existantes. La comparaison est normalisée (`normalize_source_url`), et la migration 0046 échoue explicitement en listant les ids si des doublons exacts existent déjà (L4-3, L4-4).
- **REV-277(b)** : déjà fermé (`page=0` → 422), comme le note la spec ; rien à coder.
- **REV-277(c)** : la forme réelle sur lac vide est `{"group": "Total", "value": 0}`. La branche d'alerte qui traitait « aucune ligne » était morte et est supprimée (L4-6).
- **REV-278(c)** : les cibles comptées incluent les widgets imbriqués, les `var:` et le `from` de page. Risque : une app existante incohérente recevra un 422 au prochain enregistrement (L4-9).
- **REV-278(e)** : `errors[]` était déjà porté par `ApiError` ; seul l'affichage manquait (L4-10).
- **REV-280(c)** : **le correctif P25.16 était inopérant.** Liste ouverte, Entrée validait toujours la complétion, car la keymap de `basicSetup` primait sur `Prec.highest`. Défaut réel, reproduit puis corrigé pendant la rédaction (L4-14).
- **REV-280(g)** : DuckDB est déjà en UTC. La cible réelle est l'engine Postgres, et `-c timezone` est impossible derrière PgBouncer : on utilise `SET TIME ZONE` à la connexion (L4-15).
- **REV-281(c)** : pas de règle Grafana possible, l'état Docker n'est pas scrapé. L'alerte part en webhook depuis l'entrypoint (L4-17).
- **REV-281(e)** : 12 constats réels (9 SC2034, 3 SC2086). Le hook `docker_image` est retenu parce qu'il embarque shellcheck, contrairement au hook Go. Pas de miroir CI : la spec ne le demande pas, et pre-commit tourne déjà en CI (L4-18).
- **REV-282(b)** :
  - la route réelle est `/datasets/:pk/edit` ;
  - bug trouvé : la notification d'ingestion portait toujours `"dataset"`, y compris pour une carte ;
  - jumelle harvest (mode copie) revue, sans régression (L4-19).
- **REV-282(d)** : déjà fermé (quota à la création du job), comme le note la spec.
- **REV-282(e)** : la garde est à `collections/routes.py:866`, pas 658. La jumelle `configs/routes.py:110` est traitée aussi (L4-21).
- **REV-283(c)** : la constante est à `features/routes.py:387` (pas 383) ; la variable est déjà câblée et héritée par l'overlay prod (L4-23).
- **REV-288(a)** : les écritures de pipeline passent déjà par `check_quota_or_raise` via les repositories. Seul le traitement de l'exception manquait. La jumelle harvest est déjà lisible, et le côté ingestion déjà fait, comme le note la spec (L4-25).
- **REV-289(a)** : une règle Traefik est nécessaire pour `/sitemap-N.xml` ; sans elle, la fonctionnalité est livrée mais non câblée (piège n°2) (L4-26).
- **REV-289(b)** : seule occurrence de `/api/v1` dans `core/app` ; dérivée de `CORE_BASE_URL`, déjà posé en prod (L4-26).

---

## Lot L5a — Shell UX, accessibilité, copilote (correctifs)

Ce lot regroupe des correctifs ciblés du shell, sans fonctionnalité nouvelle. Ils portent sur la
bannière de connectivité, SQL Lab, l'assistant de requête visuelle, le copilote, l'accessibilité des
pages publiques et du catalogue, le contraste du thème d'app, deux détecteurs de lint et les
formats fr-FR. Côté carte, il couvre le geste tactile annulé, le popup au redimensionnement et le
défilement au changement de route. S'y ajoutent une route d'usage enrichie (titres résolus côté
cœur) et le double montage StrictMode.

Le budget du bundle initial n'a que **0,4 Ko** de marge (729,6 sur 730 Ko). Le catalogue i18n
`src/i18n/catalog.fr.ts`, `App.tsx`, `ConnectivityBanner`, `AppLayout` et `lib/format.ts` sont
dans le chunk d'entrée. Toutes les pages, le copilote, `map/*` et le builder sont chargés par
`lazy()` et ne comptent pas. C'est pourquoi L5a-1 vient en tête : il **retire** 4 clés mortes du
catalogue, ce qui libère des octets. Chaque tâche qui ajoute du code ou des clés au chunk d'entrée
se termine par un contrôle `check-bundle-size`. Si ce contrôle échoue, la règle est unique :
relever `.bundle-size-threshold` à `Math.ceil(mesuré)` dans le même commit, en citant avant/après
et la cause.

Recettes de test utilisées partout :
- Shell : `cd shell && npx vitest run <fichiers>`.
- Cœur : depuis `core/`, `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest <tests> -q --basetemp=/tmp/l5a-pytest`.

Contrôle de taille du bundle (étape commune, citée « Contrôle bundle » plus bas) :

```bash
cd shell && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```
Expected : `Charge JS/CSS initiale mesurée : <X> Ko (seuil : 730 Ko)`, code de sortie 0. Si la
sortie est `ÉCHEC : charge initiale <X> Ko > seuil 730 Ko` :
- écrire `Math.ceil(X)` dans `shell/.bundle-size-threshold` ;
- ajouter ce fichier au commit de la tâche ;
- ajouter au corps du message : `bundle initial <avant> -> <X> Ko (cause : <fichier/clés ajoutés>), seuil relevé à <N> Ko`.

---

### Task L5a-1: REV-285(c) — détecteur de clés i18n inutilisées et purge des 4 clés mortes

**Files:**
- Create: `shell/scripts/check-i18n-unused.mjs`
- Create: `shell/scripts/check-i18n-unused.test.mjs`
- Create: `shell/scripts/i18n-unused-allowlist.json`
- Modify: `shell/package.json`. Ajouter le script `lint:i18n-unused` (après `lint:i18n`, l.20) et le chaîner dans `lint` (l.19).
- Modify: `shell/src/i18n/catalog.fr.ts`. Supprimer 4 clés : `actions.editTitle` (l.21), `actions.thumbnailTitle` (l.22), `locked.needDelete` (l.33), `extensions.loading` (l.309).

**Interfaces:**
- Consumes : le catalogue `src/i18n/catalog.fr.ts`, un objet littéral dont chaque clé tient sur une ligne `  "a.b": …`.
- Produces : `catalogKeys(src): string[]`, `dynamicPrefixes(src): string[]` et `findUnusedKeys(keys, source, allowPrefixes): string[]`, puis `npm run lint:i18n-unused`, qui sort 1 si une clé n'est jamais citée.
- Une clé compte comme citée dans trois cas :
  - elle apparaît entre `"…"`, `'…'` ou `` `…` `` dans un `.ts/.tsx` non-test de `src/` ;
  - elle commence par un préfixe de gabarit dynamique `` `prefixe.${ `` ;
  - elle commence par un préfixe de l'allowlist.
- Les tâches suivantes (L5a-7, L5a-11, L5a-12) ajoutent des clés : chacune doit être citée littéralement, sinon ce lint casse.

Le prototype de ce détecteur a été exécuté sur `dev` pendant l'écriture du plan. Il trouve exactement 24 clés. 20 d'entre elles sont les `roles.privilege.*` : le cœur fournit ces clés (`PRIVILEGE_METADATA.labelKey`) et le shell les résout par `resolveMessageKey`, d'où l'allowlist. Les 4 autres sont de vraies orphelines. Les `extensions.field*` citées par le backlog ne sont **pas** orphelines : `AdminExtensionsPage.tsx:42` les construit par gabarit. Même cas pour `alertRule.state*` (`AlertRuleEditor.tsx:40`).

- [ ] **Step 1: Écrire le test du détecteur (échoue : module absent)**

`shell/scripts/check-i18n-unused.test.mjs` :

```js
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { catalogKeys, dynamicPrefixes, findUnusedKeys } from "./check-i18n-unused.mjs";

describe("check-i18n-unused", () => {
  it("lit les clés du catalogue, valeur sur la même ligne ou la suivante", () => {
    const src = [
      "export const fr = {",
      '  "a.one": "Un",',
      '  "a.two":',
      '    "Deux",',
      "} as const;",
    ].join("\n");
    expect(catalogKeys(src)).toEqual(["a.one", "a.two"]);
  });

  it("extrait les préfixes de gabarit dynamique pointés, pas les gabarits sans point", () => {
    const src = "t(`extensions.field${name}`); t(`alertRule.state${s}`); `q${x}`; `joined_${f}`";
    expect(dynamicPrefixes(src)).toEqual(["extensions.field", "alertRule.state"]);
  });

  it("une clé citée entre guillemets, apostrophes ou backticks est utilisée", () => {
    const src = `t("a.one"); t('a.two'); t(\`a.three\`);`;
    expect(findUnusedKeys(["a.one", "a.two", "a.three", "a.four"], src)).toEqual(["a.four"]);
  });

  it("une clé couverte par un préfixe dynamique ou d'allowlist est utilisée", () => {
    const src = "t(`extensions.field${k}`)";
    expect(
      findUnusedKeys(
        ["extensions.fieldLabel", "roles.privilege.dataView", "x.y"],
        src,
        ["roles.privilege."],
      ),
    ).toEqual(["x.y"]);
  });

  it("une sous-chaîne d'une autre clé ne compte pas comme citation", () => {
    expect(findUnusedKeys(["a.b"], 't("a.bc")')).toEqual(["a.b"]);
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run scripts/check-i18n-unused.test.mjs`
Expected: FAIL `Failed to load url ./check-i18n-unused.mjs` (module absent).

- [ ] **Step 3: Écrire le détecteur et son allowlist**

`shell/scripts/check-i18n-unused.mjs` :

```js
#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// REV-285(c) : clés du catalogue i18n jamais référencées dans le code. Même
// patron que check-i18n-coverage.mjs / check-raw-colors.mjs : parcours
// `readdirSync` sans glob (CI en Node 20, cf. check-raw-colors.mjs), mesure,
// échec si une clé morte apparaît — câblé dans `npm run lint`.
//
// Une clé est « citée » si elle apparaît entre "…", '…' ou `…` dans un
// .ts/.tsx non-test de src/ (hors le catalogue lui-même), ou si elle commence
// par un préfixe de gabarit dynamique (`extensions.field${…}`) ou par un
// préfixe d'allowlist (clé fournie par le cœur, jamais écrite côté shell).
// ponytail: recherche textuelle, pas d'AST — une clé citée seulement dans un
// commentaire passe pour utilisée ; passer à un parcours TS si ça mord.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = "src";
const CATALOG = "src/i18n/catalog.fr.ts";
const ALLOWLIST = "scripts/i18n-unused-allowlist.json";

export function catalogKeys(src) {
  return [...src.matchAll(/^\s+"([\w.]+)":/gm)].map((m) => m[1]);
}

// Le point est exigé : `q${x}` ou `joined_${f}` ne sont pas des clés i18n.
export function dynamicPrefixes(src) {
  return [...new Set([...src.matchAll(/`(\w+\.[\w.]*)\$\{/g)].map((m) => m[1]))];
}

export function findUnusedKeys(keys, source, allowPrefixes = []) {
  const prefixes = [...dynamicPrefixes(source), ...allowPrefixes];
  return keys.filter(
    (k) =>
      !source.includes(`"${k}"`) &&
      !source.includes(`'${k}'`) &&
      !source.includes(`\`${k}\``) &&
      !prefixes.some((p) => k.startsWith(p)),
  );
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (
      [".ts", ".tsx"].includes(extname(full)) &&
      !/\.test\.tsx?$/.test(entry) &&
      !entry.endsWith(".d.ts") &&
      full.replaceAll("\\", "/") !== CATALOG
    )
      out.push(full);
  }
  return out;
}

export function main() {
  const keys = catalogKeys(readFileSync(CATALOG, "utf8"));
  const source = walk(ROOT)
    .map((f) => readFileSync(f, "utf8"))
    .join("\n");
  const allow = JSON.parse(readFileSync(ALLOWLIST, "utf8")).map((e) => e.prefix);
  const unused = findUnusedKeys(keys, source, allow);
  if (unused.length > 0) {
    console.error(`Clés i18n jamais référencées dans src/ (${unused.length}) :`);
    unused.forEach((k) => console.error(`  ${k}`));
    console.error(
      "\nSupprimer la clé de src/i18n/catalog.fr.ts, ou, si elle est résolue dynamiquement " +
        `sans gabarit littéral, ajouter son préfixe à ${ALLOWLIST} avec une raison.`,
    );
    process.exit(1);
  }
  console.log(`OK : ${keys.length} clé(s) i18n, toutes référencées.`);
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) main();
```

`shell/scripts/i18n-unused-allowlist.json` :

```json
[
  {
    "prefix": "roles.privilege.",
    "reason": "clé fournie par le cœur (PRIVILEGE_METADATA.labelKey), résolue par resolveMessageKey"
  }
]
```

- [ ] **Step 4: Relancer le test unitaire**

Run: `cd shell && npx vitest run scripts/check-i18n-unused.test.mjs`
Expected: `5 passed`.

- [ ] **Step 5: Lancer le détecteur sur le dépôt, constater les 4 orphelines**

Run: `cd shell && node scripts/check-i18n-unused.mjs`
Expected : sortie 1, avec exactement :
```
Clés i18n jamais référencées dans src/ (4) :
  actions.editTitle
  actions.thumbnailTitle
  locked.needDelete
  extensions.loading
```
Si la liste diffère (une autre session a pu ajouter ou retirer des usages), traiter chaque clé listée de la même façon. Avant de supprimer une clé, vérifier par `grep -rn "<clé>" src` qu'elle n'a aucun appelant.

- [ ] **Step 6: Supprimer les 4 clés et câbler le lint**

Dans `shell/src/i18n/catalog.fr.ts`, supprimer ces 4 lignes :

```ts
  "actions.editTitle": "Modifier l'élément",
  "actions.thumbnailTitle": "Miniature",
```
```ts
  "locked.needDelete": "Suppression réservée au propriétaire et aux éditeurs.",
```
```ts
  "extensions.loading": "Chargement…",
```

Dans `shell/package.json`, la ligne `"lint"` devient :

```json
    "lint": "eslint . && npm run lint:i18n && npm run lint:i18n-unused && npm run lint:aria-panel && npm run lint:colors && npm run lint:no-window-confirm && npm run lint:arbitrary-text-size",
```
et ajouter juste après `"lint:i18n": …` :

```json
    "lint:i18n-unused": "node scripts/check-i18n-unused.mjs",
```

- [ ] **Step 7: Vérifier**

Run: `cd shell && node scripts/check-i18n-unused.mjs && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : `OK : <N> clé(s) i18n, toutes référencées.`, puis aucun diagnostic `tsc`. Le catalogue est typé `MessageKey = keyof typeof fr` : une clé encore utilisée ferait échouer `tsc` ici.

- [ ] **Step 8: Contrôle bundle** (cf. intro). Expected : la mesure **baisse** par rapport à 729,6 Ko. Noter la valeur, qui sert de référence aux tâches suivantes.

- [ ] **Step 9: Commit**

```bash
git add shell/scripts/check-i18n-unused.mjs shell/scripts/check-i18n-unused.test.mjs shell/scripts/i18n-unused-allowlist.json shell/package.json shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): détecteur de clés i18n inutilisées et purge de 4 clés mortes (rev-285)

REV-285(c). roles.privilege.* en allowlist (clés fournies par le cœur).
extensions.field* et alertRule.state* sont dynamiques, pas orphelines.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-2: REV-285(d) — détecteur de couleurs brutes étendu aux `.ts`, pragma de région pour les palettes

**Files:**
- Modify: `shell/scripts/check-raw-colors.mjs`. Modifier `walk` (l.65-78), extraire `findOffenders` (l.91-108) en `findOffendersInSource` exportée, ajouter les pragmas de région et compléter le commentaire d'en-tête (paragraphe « Allowlist », l.24-33).
- Create: `shell/scripts/check-raw-colors.test.mjs`
- Modify (pragmas seulement, en commentaires, donc aucun impact bundle) :
  - `shell/src/builder/theme.ts` (l.5-12) ;
  - `shell/src/builder/widgets/palette.ts` (l.13-42 et l.70) ;
  - `shell/src/builder/widgets/mapSymbology.ts` (l.169-180) ;
  - `shell/src/builder/widgets/iconLibrary.ts` (l.187).

**Interfaces:**
- Produces : `findOffendersInSource(content: string, file: string): string[]` (exportée), qui renvoie des lignes au format `<file>:<n>: <ligne>`.
- Nouveau pragma de bloc : `// gs-raw-color-ok-begin: <raison>` … `// gs-raw-color-ok-end`. Une région ouverte et jamais fermée est elle-même signalée.
- Périmètre : `.ts` et `.tsx` hors `*.test.ts(x)` et `*.d.ts`, toujours hors `ui/kit/` et `map/`.

`map/` reste exclu, conformément au périmètre de la spec. Le backlog visait aussi les palettes de `map/*`, mais la spec restreint (d) à l'extension `.ts` plus le pragma.

Les offenseurs `.ts` actuels, relevés par grep hors `map/` et `ui/kit/`, sont tous des hexadécimaux, aucune classe Tailwind :
- `builder/theme.ts:6-11` (couleurs par défaut du thème d'app) ;
- `builder/widgets/palette.ts:17-24, 30-37, 40-41, 70` ;
- `builder/widgets/mapSymbology.ts:170-177, 179-180` ;
- `builder/widgets/iconLibrary.ts:187`.

- [ ] **Step 1: Écrire le test (échoue : `findOffendersInSource` non exportée)**

`shell/scripts/check-raw-colors.test.mjs` :

```js
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { findOffendersInSource } from "./check-raw-colors.mjs";

describe("findOffendersInSource", () => {
  it("signale un hexadécimal littéral sans pragma", () => {
    expect(findOffendersInSource('const C = "#2563eb";', "a.ts")).toEqual([
      'a.ts:1: const C = "#2563eb";',
    ]);
  });

  it("accepte le pragma de ligne sur la ligne précédente", () => {
    const src = ["// gs-raw-color-ok: trait d'icône figé", 'const C = "#1e293b";'].join("\n");
    expect(findOffendersInSource(src, "a.ts")).toEqual([]);
  });

  it("une région begin/end couvre un bloc, la détection reprend après end", () => {
    const src = [
      "// gs-raw-color-ok-begin: palette de dataviz",
      'const A = ["#2563eb",',
      '  "#dc2626"];',
      "// gs-raw-color-ok-end",
      'const B = "#ffffff";',
    ].join("\n");
    expect(findOffendersInSource(src, "p.ts")).toEqual(['p.ts:5: const B = "#ffffff";']);
  });

  it("signale une région jamais fermée", () => {
    const src = ["// gs-raw-color-ok-begin: palette", 'const A = "#2563eb";'].join("\n");
    expect(findOffendersInSource(src, "p.ts")).toEqual([
      "p.ts:1: région gs-raw-color-ok-begin jamais fermée par gs-raw-color-ok-end",
    ]);
  });

  it("signale toujours une classe Tailwind de couleur littérale", () => {
    expect(findOffendersInSource('<p className="text-white" />', "b.tsx")).toEqual([
      'b.tsx:1: <p className="text-white" />',
    ]);
  });
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run scripts/check-raw-colors.test.mjs`
Expected: FAIL `findOffendersInSource is not a function` (ou `does not provide an export named 'findOffendersInSource'`).

- [ ] **Step 3: Implémenter**

Dans `shell/scripts/check-raw-colors.mjs` :

(a) Ajouter ce paragraphe à la fin du commentaire d'en-tête, juste avant `import { readFileSync, … }` :

```js
//
// REV-285(d) : les `.ts` sont scannés aussi (palettes de dataviz, thème
// d'app par défaut). Pour un BLOC de couleurs délibérées (palette), un pragma
// de région : `// gs-raw-color-ok-begin: <raison>` … `// gs-raw-color-ok-end`.
// Une région jamais fermée est elle-même une erreur (sinon elle couvrirait
// silencieusement tout le reste du fichier).
```

(b) Après `const PRAGMA_RE = /gs-raw-color-ok/;`, ajouter :

```js
const REGION_BEGIN_RE = /\/\/\s*gs-raw-color-ok-begin\b/;
const REGION_END_RE = /\/\/\s*gs-raw-color-ok-end\b/;
```

(c) Dans `walk`, remplacer la branche `else if (extname(full) === ".tsx" && !entry.endsWith(".test.tsx")) {` par :

```js
    } else if (
      [".ts", ".tsx"].includes(extname(full)) &&
      !/\.test\.tsx?$/.test(entry) &&
      !entry.endsWith(".d.ts")
    ) {
```
Mettre à jour son JSDoc : `liste des fichiers .ts/.tsx non-test (hors .d.ts)`.

(d) Remplacer toute la fonction `findOffenders(file)` (l.91-108) par :

```js
export function findOffendersInSource(content, file) {
  const lines = content.split("\n");
  const offenders = [];
  let regionStart = -1;
  lines.forEach((line, index) => {
    if (REGION_BEGIN_RE.test(line)) {
      regionStart = index;
      return;
    }
    if (REGION_END_RE.test(line)) {
      regionStart = -1;
      return;
    }
    if (regionStart >= 0) return;
    if (!RAW_COLOR_RE.test(line) && !HEX_COLOR_RE.test(line)) return;
    const coveredBySameLine = PRAGMA_RE.test(line);
    const prevLineTrimmed = index > 0 ? lines[index - 1].trim() : "";
    const coveredByPrecedingLine =
      prevLineTrimmed.startsWith("//") && PRAGMA_RE.test(prevLineTrimmed);
    if (coveredBySameLine || coveredByPrecedingLine) return;
    offenders.push(`${file}:${index + 1}: ${line.trim()}`);
  });
  if (regionStart >= 0) {
    offenders.push(
      `${file}:${regionStart + 1}: région gs-raw-color-ok-begin jamais fermée par gs-raw-color-ok-end`,
    );
  }
  return offenders;
}

function findOffenders(file) {
  return findOffendersInSource(readFileSync(file, "utf8"), file);
}
```
Garder au-dessus de `findOffendersInSource` le JSDoc existant de `findOffenders`, en y ajoutant : « … ou dans une région `gs-raw-color-ok-begin`/`-end` ». Dans `main`, remplacer `ui/kit/ et map/` par `ui/kit/ et map/ (.ts/.tsx)` dans le message d'erreur. Le reste est inchangé.

- [ ] **Step 4: Relancer le test unitaire**

Run: `cd shell && npx vitest run scripts/check-raw-colors.test.mjs`
Expected: `5 passed`.

- [ ] **Step 5: Lancer sur le dépôt, constater les offenseurs `.ts`**

Run: `cd shell && node scripts/check-raw-colors.mjs`
Expected : sortie 1. La liste contient **uniquement** des lignes de `src/builder/theme.ts`, `src/builder/widgets/palette.ts`, `src/builder/widgets/mapSymbology.ts` et `src/builder/widgets/iconLibrary.ts`, soit les numéros listés plus haut.

- [ ] **Step 6: Poser les pragmas**

`shell/src/builder/theme.ts`, encadrer `DEFAULT_THEME_COLORS` :

```ts
// gs-raw-color-ok-begin: couleurs par défaut du thème d'APP (choisies par l'auteur, pas l'ambiance du studio)
export const DEFAULT_THEME_COLORS: Required<ThemeColors> = {
  primary: "#2563eb",
  background: "#ffffff",
  surface: "#f8fafc",
  text: "#0f172a",
  muted: "#64748b",
  border: "#e2e8f0",
};
// gs-raw-color-ok-end
```

`shell/src/builder/widgets/palette.ts` :
- poser `// gs-raw-color-ok-begin: palettes de dataviz curatées (SP-25), choix de l'auteur d'app` sur la ligne précédant `export const CURATED_PALETTES` (l.13) ;
- poser `// gs-raw-color-ok-end` après le `};` qui ferme l'objet (l.42) ;
- poser, sur la ligne précédant `return { kind: "sequential", low: "#ffffff", high: primary };` (l.70), à la même indentation : `// gs-raw-color-ok: borne basse blanche de la rampe séquentielle sur la couleur primaire de l'app`.

`shell/src/builder/widgets/mapSymbology.ts` :
- poser `// gs-raw-color-ok-begin: palette catégorielle et rampe numérique par défaut de la symbologie (SP-25)` sur la ligne précédant `const CATEGORICAL_PALETTE = [` (l.169) ;
- poser `// gs-raw-color-ok-end` après `const NUMERIC_COLOR_HIGH = "#1e3a8a";` (l.180).

`shell/src/builder/widgets/iconLibrary.ts`, poser sur la ligne précédant `const LUCIDE_STROKE = "#1e293b";` (l.187) :

```ts
// gs-raw-color-ok: trait des icônes Lucide rastérisées pour MapLibre (image figée, pas un jeton CSS)
```

- [ ] **Step 7: Vérifier**

Run: `cd shell && node scripts/check-raw-colors.mjs && npm run lint && npm run format:check`
Expected : `OK : aucune couleur Tailwind brute hors ui/kit/, map/, tests et pragma gs-raw-color-ok (<N> fichier(s) scanné(s)).`, avec un N nettement supérieur au nombre précédent puisque les `.ts` sont désormais comptés. Lint et format verts.

- [ ] **Step 8: Commit**

```bash
git add shell/scripts/check-raw-colors.mjs shell/scripts/check-raw-colors.test.mjs shell/src/builder/theme.ts shell/src/builder/widgets/palette.ts shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/iconLibrary.ts
git commit -m "feat(shell): détecteur de couleurs brutes étendu aux .ts avec pragma de région (rev-285)

REV-285(d). Palettes de dataviz et thème d'app par défaut couverts par
gs-raw-color-ok-begin/-end ; map/ reste hors périmètre (spec).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-3: REV-285(g) — `lib/format.ts` : « — » pour une valeur absente ou non finie

**Files:**
- Modify: `shell/src/lib/format.ts` (l.5-28)
- Modify: `shell/src/lib/format.test.ts` (ajout d'un `describe`)

**Interfaces:**
- Produces : `formatNumber(n: number | null | undefined, …)` et `formatBytes(bytes: number | null | undefined)` renvoient `"—"` si `n` n'est pas un nombre fini. `formatDateTime(iso: string | number | Date | null | undefined)` renvoie `"—"` pour `null`, `undefined` et `""`. Aujourd'hui, `new Date(null)` affiche le 01/01/1970.
- Signatures élargies seulement : aucun appelant à modifier. Le fuseau horaire reste hors périmètre.

- [ ] **Step 1: Test qui échoue**

Ajouter à la fin de `shell/src/lib/format.test.ts` :

```ts
describe("valeur absente ou non finie (REV-285 g)", () => {
  it("formatNumber rend « — » pour NaN, ±Infinity, null et undefined", () => {
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—");
    expect(formatNumber(Number.NEGATIVE_INFINITY)).toBe("—");
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(0)).toBe("0");
  });

  it("formatBytes rend « — » pour une taille non finie", () => {
    expect(formatBytes(Number.NaN)).toBe("—");
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(0)).toBe("0 o");
  });

  it("formatDateTime rend « — » pour null, undefined et la chaîne vide (pas 1970)", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });
});
```
Vérifier que `formatBytes` et `formatDateTime` figurent dans l'import en tête du fichier (`import { formatBytes, formatDateTime, formatNumber } from "./format";`) et compléter l'import s'il en manque.

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/lib/format.test.ts`
Expected : FAIL. `formatNumber(Number.NaN)` donne `"NaN"`, `formatDateTime(null)` donne une date de 1970, `formatBytes(null)` donne `"0 o"`.

- [ ] **Step 3: Implémenter**

Remplacer le corps de `shell/src/lib/format.ts` sous l'en-tête (l.1-2 conservées) par :

```ts
// REV-285(g) : une valeur absente ou non finie s'affiche « — », jamais « NaN »,
// « ∞ » ni le 01/01/1970 de `new Date(null)`.
const MISSING = "—";

/** Date + heure « 30/09/2026 04:52:57 » ; l'entrée illisible est rendue telle quelle. */
export function formatDateTime(iso: string | number | Date | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return MISSING;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString("fr-FR");
}

/** Nombre fr-FR (« 1 234 567,75 ») ; au plus `maxDecimals` décimales (2 par défaut). */
export function formatNumber(
  n: number | null | undefined,
  maxDecimals = 2,
  minDecimals = 0,
): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return MISSING;
  return n.toLocaleString("fr-FR", {
    maximumFractionDigits: maxDecimals,
    minimumFractionDigits: minDecimals,
  });
}

/** Taille en octets lisible (« 3 Ko », « 1,5 Mo ») : unité adaptée, séparateur décimal fr. */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes)) return MISSING;
  const units = ["o", "Ko", "Mo", "Go", "To"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${formatNumber(value, i === 0 ? 0 : 1)} ${units[i]}`;
}
```

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/lib/format.test.ts && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tous les tests de `format.test.ts` passent, sans diagnostic.

- [ ] **Step 5: Contrôle bundle** (cf. intro). `lib/format.ts` est importé par du code du chunk d'entrée. Le surcoût attendu est d'environ 0,1 Ko.

- [ ] **Step 6: Commit**

```bash
git add shell/src/lib/format.ts shell/src/lib/format.test.ts
git commit -m "fix(shell): formats fr-fr affichent « — » pour une valeur absente ou non finie (rev-285)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-4: REV-254 — la bannière de connectivité écoute aussi les mutations

**Files:**
- Modify: `shell/src/shell/ConnectivityBanner.tsx` (abonnement l.27-43, sondage l.45-56)
- Modify: `shell/src/shell/ConnectivityBanner.test.tsx` (import l.2-7, 2 tests ajoutés)

**Interfaces:**
- Consumes : `QueryClient.getMutationCache().subscribe`, avec des événements `updated`/`removed`. Pour l'action de type `success` d'une query, `SuccessAction.manual` vaut `true` pour un `setQueryData` (React Query 5.101).
- Produces : une mutation rejetée par `CoreUnreachableError` lève la bannière, sous la clé `mutation:<mutationId>` dans le même ensemble `failed`. La bannière retombe :
  - au premier succès réseau (query non manuelle ou mutation), qui retire toutes les clés `mutation:*` ;
  - au retrait de la mutation du cache.

  Tant qu'une mutation est en échec, le sondage relance **toutes** les requêtes actives, pas seulement celles en échec : c'est leur succès qui prouve le retour du cœur.

L'autre moitié de REV-254 (les `fetch` nus des fichiers de domaine) est **déjà faite** : tous passent par `authFetch` et `fetchWithTimeout`. Seul reste le `PUT` S3 présigné de `exportsIngestion.ts:78`, une exception assumée par la spec. La coupure réelle du cœur relève de L6.

- [ ] **Step 1: Tests qui échouent**

Dans `shell/src/shell/ConnectivityBanner.test.tsx`, ajouter `MutationObserver` à l'import `@tanstack/react-query` (l.2-7) :

```ts
import {
  MutationObserver,
  QueryClient,
  QueryClientProvider,
  QueryObserver,
  onlineManager,
} from "@tanstack/react-query";
```
puis, après le helper `fail` :

```ts
const failMutation = (qc: QueryClient) =>
  new MutationObserver(qc, {
    mutationFn: () => Promise.reject(new CoreUnreachableError()),
  })
    .mutate()
    .catch(() => {});
```
et ajouter à la fin du fichier :

```ts
test("REV-254 : une mutation en échec d'injoignabilité lève la bannière, un succès réseau la baisse", async () => {
  const { queryClient } = setup();
  await failMutation(queryClient);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Connexion au serveur perdue — nouvelle tentative en cours…",
    ),
  );

  await queryClient.fetchQuery({ queryKey: ["any"], queryFn: () => Promise.resolve("ok") });
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});

test("REV-254 : un setQueryData (succès manuel) ne prouve pas le retour du cœur", async () => {
  const { queryClient } = setup();
  await failMutation(queryClient);
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  act(() => {
    queryClient.setQueryData(["local"], "x");
  });
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

test("REV-254 : mutation en échec seule, le sondage relance les requêtes actives et baisse la bannière", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { queryClient } = setup();
  const observer = new QueryObserver(queryClient, {
    queryKey: ["active"],
    queryFn: () => Promise.resolve("ok"),
  });
  const unsubscribe = observer.subscribe(() => {});
  await waitFor(() => expect(observer.getCurrentResult().isSuccess).toBe(true));

  await failMutation(queryClient);
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

  await act(async () => {
    await vi.advanceTimersByTimeAsync(CONNECTIVITY_POLL_MS);
  });
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  unsubscribe();
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/ConnectivityBanner.test.tsx`
Expected : les trois tests REV-254 échouent. Le premier et le troisième échouent en timeout de `waitFor` sur `getByRole("alert")`, car la bannière ne se lève jamais : seul le `QueryCache` est écouté. Le deuxième échoue pour la même raison. Les tests existants passent.

- [ ] **Step 3: Implémenter**

Dans `shell/src/shell/ConnectivityBanner.tsx`, ajouter après `const isOnline = …` :

```ts
// REV-254 : les mutations en échec d'injoignabilité partagent l'ensemble
// `failed`, préfixées pour ne jamais collisionner un queryHash (JSON).
const MUTATION_KEY_PREFIX = "mutation:";

// `reachable` : un succès réseau réel vient d'être observé — il prouve le
// retour du cœur pour TOUTES les mutations en échec (une mutation échouée
// n'est jamais rejouée par le sondage, elle ne peut pas se rétablir seule).
function nextFailed(
  prev: ReadonlySet<string>,
  key: string,
  down: boolean,
  reachable: boolean,
): ReadonlySet<string> {
  const cleared = reachable ? [...prev].filter((k) => k.startsWith(MUTATION_KEY_PREFIX)) : [];
  if (down === prev.has(key) && cleared.length === 0) return prev;
  const next = new Set(prev);
  for (const k of cleared) next.delete(k);
  if (down) next.add(key);
  else next.delete(key);
  return next;
}
```

Remplacer l'effet d'abonnement (l.27-43) par :

```ts
  useEffect(() => {
    const unsubscribeQueries = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" && event.type !== "removed") return;
      const { queryHash, state } = event.query;
      const down =
        event.type === "updated" &&
        state.status === "error" &&
        state.error instanceof CoreUnreachableError;
      // Un `setQueryData` (succès `manual`) n'a touché aucun réseau.
      const reachable =
        event.type === "updated" && event.action.type === "success" && !event.action.manual;
      setFailed((prev) => nextFailed(prev, queryHash, down, reachable));
    });
    const unsubscribeMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type !== "updated" && event.type !== "removed") return;
      const key = `${MUTATION_KEY_PREFIX}${event.mutation.mutationId}`;
      const down =
        event.type === "updated" &&
        event.mutation.state.status === "error" &&
        event.mutation.state.error instanceof CoreUnreachableError;
      const reachable = event.type === "updated" && event.action.type === "success";
      setFailed((prev) => nextFailed(prev, key, down, reachable));
    });
    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
  }, [queryClient]);
```

Remplacer le bloc du sondage (l.45-56) par :

```ts
  const unreachable = failed.size > 0;
  const mutationDown = [...failed].some((k) => k.startsWith(MUTATION_KEY_PREFIX));
  useEffect(() => {
    if (!unreachable) return;
    // Annulé dès que la bannière se lève ou au démontage. Une mutation en
    // échec n'a pas de requête à relancer : on relance alors toute requête
    // active, dont le succès prouve le retour du cœur (cf. nextFailed).
    // ponytail: sans requête active, la bannière d'une mutation attend le
    // prochain succès réseau ; ajouter une sonde /health si ça gêne.
    const id = setInterval(() => {
      void queryClient.refetchQueries({
        type: "active",
        predicate: (q) => mutationDown || q.state.error instanceof CoreUnreachableError,
      });
    }, CONNECTIVITY_POLL_MS);
    return () => clearInterval(id);
  }, [unreachable, mutationDown, queryClient]);
```
Compléter le commentaire de tête du composant (après « … P22.07 … son propre message. ») par : `// REV-254 : les mutations sont suivies aussi (MutationCache) — un POST/PUT/DELETE vers un cœur injoignable lève la bannière.`

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/shell/ConnectivityBanner.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tous les tests passent (existants + 3 nouveaux), sans diagnostic.

- [ ] **Step 5: Falsification**

Remplacer temporairement `event.mutation.state.error instanceof CoreUnreachableError` par `false`. Relancer le fichier : le premier test REV-254 doit échouer. Restaurer la ligne.

- [ ] **Step 6: Contrôle bundle** (cf. intro). `ConnectivityBanner` est dans le chunk d'entrée (`App.tsx`). Le surcoût attendu est d'environ 0,4 Ko ; un relèvement documenté du seuil est probable ici.

- [ ] **Step 7: Commit**

```bash
git add shell/src/shell/ConnectivityBanner.tsx shell/src/shell/ConnectivityBanner.test.tsx
git commit -m "fix(shell): bannière de connectivité levée par une mutation injoignable (rev-254)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(ajouter `shell/.bundle-size-threshold` au `git add` et la ligne de relèvement au corps si le contrôle bundle l'a exigé.)

---

### Task L5a-5: REV-265 + REV-184(5) — autocomplétion SQL Lab après restauration d'historique, commentaire de troncature

**Files:**
- Modify: `shell/src/pages/SqlLabPage.tsx`. Commentaire l.82-85, dépendances de l'effet D54b l.156-157.
- Modify: `shell/src/pages/SqlLabPage.test.tsx`. `mockCollectionsList` l.240-264 factorisé, 1 test ajouté.

**Interfaces:**
- Consumes : `useCollectionsAdmin()`, aujourd'hui **inconditionnel** (l.85). REV-184(5) parlait encore d'un `enabled: copilotEnabled`, qui n'existe plus. `?historyId=` est restauré par l'effet l.92-98.
- Produces : l'effet D54b dépend de `[sql, collectionsQuery.data]`. Quand la liste arrive après la restauration du SQL, le schéma des collections référencées est chargé sans frappe supplémentaire. `collectionsQuery.data` garde une référence stable entre rendus (React Query), contrairement à `knownCollectionIds` qui est recalculé à chaque rendu. La garde `!(id in schemaByCollection)` empêche déjà tout refetch par frappe.

- [ ] **Step 1: Test qui échoue**

Dans `shell/src/pages/SqlLabPage.test.tsx`, remplacer `mockCollectionsList` (l.240-264) par une version factorisée (le contenu de la collection est inchangé) :

```ts
function collectionsListBody() {
  return {
    collections: [
      {
        id: "parcs",
        title: "Parcs urbains",
        description: "",
        tableName: "parcs",
        isPublic: false,
        editable: true,
        geometryType: "Point",
        srid: 4326,
        pkColumn: "id",
        permissions: { read: true, write: true, delete: true, share: true },
        featureCount: 3,
        owner: "alice",
        attachmentFields: [],
      },
    ],
    numberMatched: 1,
    numberReturned: 1,
  };
}

function mockCollectionsList() {
  return http.get("https://core.test/v1/collections", () =>
    HttpResponse.json(collectionsListBody()),
  );
}
```
puis ajouter à la fin du fichier :

```ts
// REV-265 : la liste des collections arrive APRÈS la restauration du SQL
// depuis ?historyId= — l'effet D54b ne dépendait que de [sql] et ne se
// relançait jamais : aucune autocomplétion sans frappe supplémentaire.
test("REV-265 : SQL restauré avant la liste des collections → schéma chargé sans frappe", async () => {
  localStorage.setItem(
    "geostudio.sqlLab.history.anonymous",
    JSON.stringify([
      {
        id: "h1",
        sql: "select nom from parcs",
        executedAt: "2026-09-26T00:00:00Z",
        status: "ok",
        rowCount: 1,
      },
    ]),
  );
  let releaseCollections!: () => void;
  const collectionsGate = new Promise<void>((resolve) => {
    releaseCollections = resolve;
  });
  const fetchedSchemaIds = new Set<string>();
  server.use(
    http.get("https://core.test/v1/collections", async () => {
      await collectionsGate;
      return HttpResponse.json(collectionsListBody());
    }),
    http.get("https://core.test/v1/collections/parcs/schema", () => {
      fetchedSchemaIds.add("parcs");
      return HttpResponse.json({
        collection: "parcs",
        pk: "id",
        geometry: { column: "geom", type: "Point", srid: 4326 },
        fields: [{ name: "nom", type: "text", required: true }],
      });
    }),
  );
  render(<Harness initialEntries={["/analytics/sql?historyId=h1"]} />);
  expect(await screen.findByRole("textbox", { name: /requête/i })).toHaveTextContent(
    "select nom from parcs",
  );
  expect(fetchedSchemaIds.has("parcs")).toBe(false);
  releaseCollections();
  await waitFor(() => expect(fetchedSchemaIds.has("parcs")).toBe(true));
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx -t "REV-265"`
Expected : FAIL, timeout du dernier `waitFor`. `fetchedSchemaIds` reste vide parce que l'effet ne se relance pas à l'arrivée de la liste.

- [ ] **Step 3: Implémenter**

Dans `shell/src/pages/SqlLabPage.tsx`, remplacer le commentaire l.82-84 (juste au-dessus de `const collectionsQuery = useCollectionsAdmin();`) par :

```ts
  // D54 (Vague C) : la liste des collections alimente désormais aussi
  // l'autocomplétion SQL (Tâche 26, D54b), plus seulement le panneau
  // copilote — appel inconditionnel.
  // REV-184(5) : GET /v1/collections sans `limit` ne renvoie que sa première
  // page (DEFAULT_LIMIT = 100, core/app/collections/routes.py) — au-delà, ni
  // l'autocomplétion ni le copilote ne voient les collections suivantes. Et
  // un tour de copilote envoyé avant la résolution de cette requête part avec
  // `collections: []` (course de chargement assumée, rare en pratique).
```
Remplacer les deux dernières lignes de l'effet D54b (l.156-157) :

```ts
    // eslint-disable-next-line react-hooks/exhaustive-deps -- knownCollectionIds recalculé chaque rendu depuis collectionsQuery.data, l'inclure re-déclencherait l'effet inutilement à chaque frappe
  }, [sql]);
```
par :

```ts
    // REV-265 : `collectionsQuery.data` (référence stable entre rendus) relance
    // l'effet quand la liste arrive après un SQL restauré depuis l'historique.
    // knownCollectionIds (tableau neuf à chaque rendu) et schemaByCollection
    // (garde anti-refetch lue dans l'effet) restent hors dépendances.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cf. ci-dessus
  }, [sql, collectionsQuery.data]);
```

- [ ] **Step 4: Relancer le fichier complet**

Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe, y compris « propose les colonnes de la collection référencée » et le test de non-boucle de la revue Vague C (point 7).

- [ ] **Step 5: Commit** (page `lazy()` : hors chunk d'entrée, pas de contrôle bundle)

```bash
git add shell/src/pages/SqlLabPage.tsx shell/src/pages/SqlLabPage.test.tsx
git commit -m "fix(shell): autocomplétion sql lab relancée à l'arrivée des collections (rev-265, rev-184)

REV-265 + REV-184(5) (commentaire de troncature à 100 / course de chargement).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-6: REV-251 — assistant de requête visuelle : pas de « lecture seule » pendant le chargement de l'item

**Files:**
- Modify: `shell/src/pages/VisualQueryWizardPage.tsx`. `readOnly` l.68-69, bouton l.586-598.
- Modify: `shell/src/pages/VisualQueryWizardPage.test.tsx`. Ajouter 1 test dans `describe("VisualQueryWizardPage — mode édition …")`, à partir de la l.520.

**Interfaces:**
- Consumes : `useItem(pipelinePk ?? "", { enabled: pipelinePk !== null })` et `hasPermission(item, "write")`, qui renvoie faux si `item` est `undefined`. C'est la cause du bug : pendant le chargement, `readOnly` vaut vrai et le message « Modification réservée… » clignote.
- Produces : `readOnly = pipelinePk !== null && itemQuery.isSuccess && !hasPermission(…)`. Une nouvelle variable `itemPending = pipelinePk !== null && !itemQuery.isSuccess` désactive le bouton, sans message, tant que l'item n'est pas chargé ou est en erreur.

Le patron réel de `PipelineBuilderPage.tsx` a été vérifié (l.105-106, 223, 235). Il bloque **toute la page** : `LoadingState` pendant `isLoading`, page d'erreur sinon. Ici le formulaire est déjà utilisable pendant le chargement, donc on se contente de désactiver le bouton pendant que l'item est en attente, au lieu de bloquer la page.

- [ ] **Step 1: Test qui échoue**

Ajouter dans le `describe("VisualQueryWizardPage — mode édition (Modifier la requête, fix I3)", …)` de `shell/src/pages/VisualQueryWizardPage.test.tsx` :

```ts
  // REV-251 : tant que l'item du pipeline édité charge, `hasPermission(undefined)`
  // valait faux → le message « lecture seule » s'affichait à tort.
  test("REV-251 : pendant le chargement de l'item, pas de message lecture seule mais bouton désactivé", async () => {
    const datasetItem = {
      pk: "dataset-1",
      resourceType: "dataset",
      title: "Ma requête existante",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      permissions: OWNER_PERMISSIONS,
      date: "",
      configId: "cfg-1",
      isPublished: false,
    };
    renderWizardEdit({
      getItem: vi.fn((pk: string) =>
        pk === "pipeline-1" ? new Promise(() => {}) : Promise.resolve(datasetItem),
      ) as unknown as ItemClient["getItem"],
    });
    await screen.findByDisplayValue("Ma requête existante");
    expect(
      screen.queryByText("Modification réservée aux éditeurs de cet élément."),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mettre à jour" })).toBeDisabled();
  });
```
(`renderWizardEdit` monte le pipeline `pipeline-1` dont la sortie est `dataset-1`. `ItemClient` et `OWNER_PERMISSIONS` sont déjà importés par ce fichier ; vérifier l'import de `ItemClient` en tête et l'ajouter en `import type` s'il manque.)

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/VisualQueryWizardPage.test.tsx -t "REV-251"`
Expected : FAIL sur `not.toBeInTheDocument()`, parce que le message « Modification réservée… » est rendu.

- [ ] **Step 3: Implémenter**

Dans `shell/src/pages/VisualQueryWizardPage.tsx`, remplacer la l.69 :

```ts
  const readOnly = pipelinePk !== null && !hasPermission(itemQuery.data, "write");
```
par :

```ts
  // REV-251 : `hasPermission(undefined)` refuse par défaut — on ne conclut à la
  // lecture seule qu'une fois l'item chargé ; d'ici là (ou en erreur) le bouton
  // est seulement désactivé, sans message trompeur.
  const readOnly = pipelinePk !== null && itemQuery.isSuccess && !hasPermission(itemQuery.data, "write");
  const itemPending = pipelinePk !== null && !itemQuery.isSuccess;
```
et, dans la liste `disabled={…}` du bouton (l.586-598), remplacer `readOnly ||` par `readOnly ||\n                    itemPending ||`. `prettier` reformatera si besoin.

- [ ] **Step 4: Relancer le fichier complet**

Run: `cd shell && npx vitest run src/pages/VisualQueryWizardPage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe, y compris « I2 : ouvrir une requête existante sans droit d'écriture… », qui exige toujours le message une fois l'item chargé.

- [ ] **Step 5: Commit** (page `lazy()`)

```bash
git add shell/src/pages/VisualQueryWizardPage.tsx shell/src/pages/VisualQueryWizardPage.test.tsx
git commit -m "fix(shell): requête visuelle sans faux « lecture seule » pendant le chargement (rev-251)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-7: REV-184(1)-(4) — copilote de requête visuelle : statut par jambe, `null` par défaut, `join.on` validé, commentaire corrigé

**Files:**
- Modify: `shell/src/builder/copilot/applyVisualQueryClientOp.ts` : commentaire l.43-53, `isValidGeneratedJoin` l.78-93, retour l.147-203.
- Modify: `shell/src/builder/copilot/applyVisualQueryClientOp.test.ts` : test du join valide (l.131-136), test « reports whether… » (l.281-305), 4 tests ajoutés.
- Modify: `shell/src/builder/copilot/VisualQueryCopilotPanel.tsx` (l.44-52)
- Modify: `shell/src/builder/copilot/VisualQueryCopilotPanel.test.tsx` (1 test)
- Modify: `shell/src/builder/copilot/CopilotChat.tsx` : type `onClientOps` l.48-53, résumé l.126-133.
- Modify: `shell/src/i18n/catalog.fr.ts` : 4 clés après `"copilot.opVisualQueryDraftApplied"` (l.1326).

**Interfaces:**
- Produces :
  - `applyVisualQueryClientOp(...)` renvoie `{ applied: VisualQueryLeg[]; ignored: VisualQueryLeg[] }`, avec `type VisualQueryLeg = "filters" | "join" | "summary"`, au lieu d'un `boolean`. Une jambe de filtres dont **au moins une** ligne a été écartée figure dans `ignored`, même si d'autres lignes ont été appliquées.
  - `CopilotChat.onClientOps` renvoie `(boolean | string)[] | void`. Une **chaîne** est affichée telle quelle comme libellé de l'op.
  - Seul appelant de l'applier : `VisualQueryCopilotPanel` (vérifié par grep). `CopilotPanel` et `SqlLabCopilotPanel` renvoient `boolean[]` ou rien, ce qui reste compatible.
- (2) Les métriques reçues sont normalisées (`sourceColumn ?? null`, `p ?? null`) **dans l'applier**, avant validation et avant `setSummary`. La spec plaçait ce correctif dans `visualQueryClientTools.ts`. Mais ce fichier ne porte que le schéma JSON (`METRIC_JSON_SCHEMA`), alors que le rejet de `undefined` (`!== null`) est dans l'applier. On aligne donc sur `GeneratedMetric` côté serveur (`is not None`) à l'endroit où le rejet se produit.
- (3) Le compilateur joint en `USING (on)`, donc `on` doit exister **côté base**, schéma d'avant jointure. Les colonnes ajoutées par la jointure ne comptent pas.
- (4) Le commentaire « Miroir exact » est faux. Le client corrige délibérément l'aliasing serveur (`base_names = names`, `core/app/mcp/tools/query_generation.py:112-118`). Ce bug serveur est pratiquement inerte, puisque les noms de champ d'un schéma sont uniques : on ne le corrige pas ici.

- [ ] **Step 1: Tests qui échouent**

Dans `shell/src/builder/copilot/applyVisualQueryClientOp.test.ts` :

(a) Dans « applies a valid join object on a known collection » (l.131-136), remplacer `on: "code_insee"` par `on: "titre"` (colonne de base de `KNOWN`) :

```ts
    const join = { collectionId: "communes", on: "titre", how: "inner" as const };
```

(b) Remplacer le test « reports whether anything was actually applied » (l.281-305) par :

```ts
  it("reports per leg what was applied and what was ignored (REV-184 1)", () => {
    expect(
      applyVisualQueryClientOp(
        {
          op: "applyVisualQueryDraft",
          args: { filters: [{ column: "titre", operator: "eq", value: "x" }] },
        },
        setters(),
        KNOWN,
      ),
    ).toEqual({ applied: ["filters"], ignored: [] });
    expect(
      applyVisualQueryClientOp(
        {
          op: "applyVisualQueryDraft",
          args: { filters: [{ column: "titre", operator: "startswith", value: "x" }] },
        },
        setters(),
        KNOWN,
      ),
    ).toEqual({ applied: [], ignored: ["filters"] });
    expect(applyVisualQueryClientOp({ op: "somethingElse", args: {} }, setters(), KNOWN)).toEqual({
      applied: [],
      ignored: [],
    });
  });

  it("flags the filters leg as ignored when only some rows were dropped", () => {
    expect(
      applyVisualQueryClientOp(
        {
          op: "applyVisualQueryDraft",
          args: {
            filters: [
              { column: "titre", operator: "eq", value: "y" },
              { column: "colonne_hallucinee", operator: "eq", value: "x" },
            ],
          },
        },
        setters(),
        KNOWN,
      ),
    ).toEqual({ applied: ["filters"], ignored: ["filters"] });
  });

  it("valid summary + invalid join: summary applied, join reported as ignored", () => {
    const s = setters();
    const result = applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: {
          join: { collectionId: "collection_inventee", on: "titre", how: "inner" },
          summary: {
            groupBy: ["titre"],
            metrics: [{ alias: "n", function: "count", sourceColumn: null, p: null }],
          },
        },
      },
      s,
      KNOWN,
    );
    expect(result).toEqual({ applied: ["summary"], ignored: ["join"] });
    expect(s.setJoin).not.toHaveBeenCalled();
  });

  // REV-184(3) : `USING (on)` — la colonne doit exister côté base.
  it("ignores a join on a real collection whose `on` column is not a base column", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { join: { collectionId: "communes", on: "colonne_hallucinee", how: "inner" } },
      },
      s,
      KNOWN,
    );
    expect(s.setJoin).not.toHaveBeenCalled();
  });

  // REV-184(2) : le schéma client n'exige que alias/function — un LLM qui
  // omet sourceColumn/p (au lieu de null) ne doit pas faire rejeter le résumé.
  it("accepts a count metric that omits sourceColumn and p, normalized to null", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { summary: { groupBy: ["titre"], metrics: [{ alias: "n", function: "count" }] } },
      },
      s,
      KNOWN,
    );
    expect(s.setSummary).toHaveBeenCalledWith({
      groupBy: ["titre"],
      metrics: [{ alias: "n", function: "count", sourceColumn: null, p: null }],
    });
  });
```

Dans `shell/src/builder/copilot/VisualQueryCopilotPanel.test.tsx`, ajouter dans le `describe` :

```ts
  it("REV-184 : annonce les jambes ignorées quand le brouillon n'est appliqué qu'en partie", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "Voici.",
      clientOps: [
        {
          op: "applyVisualQueryDraft",
          args: {
            filters: [{ column: "titre", operator: "eq", value: "Nid de poule" }],
            join: { collectionId: "collection_inventee", on: "titre", how: "inner" },
          },
        },
      ],
    });
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <VisualQueryCopilotPanel
          baseCollectionId="incidents"
          baseSchema={BASE_SCHEMA}
          joinedSchema={null}
          collectionIds={["incidents"]}
          filters={[]}
          join={null}
          summary={null}
          setFilters={vi.fn()}
          setJoin={vi.fn()}
          setSummary={vi.fn()}
        />
      </ItemClientProvider>,
    );
    await userEvent.type(screen.getByLabelText("Message au copilote"), "les nids de poule");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(
      await screen.findByText("Requête visuelle mise à jour ; ignoré (invalide) : jointure."),
    ).toBeVisible();
  });
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/copilot/applyVisualQueryClientOp.test.ts src/builder/copilot/VisualQueryCopilotPanel.test.tsx`
Expected, en FAIL :
- les `toEqual({ applied, ignored })`, qui reçoivent un booléen ;
- « ignores a join … `on` … » (`setJoin` appelé) ;
- « accepts a count metric that omits… » (`setSummary` jamais appelé) ;
- le test du panneau (texte introuvable).

- [ ] **Step 3: Implémenter l'applier**

Dans `shell/src/builder/copilot/applyVisualQueryClientOp.ts` :

(a) Remplacer le paragraphe de commentaire l.43-46 (« Miroir exact de `_known_field_names` … inferOutputColumns/compileVisualQueryToPipeline côté shell). ») par :

```ts
// Même règle que `_known_field_names` (core/app/mcp/tools/query_generation.py) :
// les champs de la collection jointe gardent leur nom, sauf collision avec un
// champ de base, auquel cas ils sont préfixés `joined_` (même règle que
// inferOutputColumns/compileVisualQueryToPipeline côté shell). REV-184(4) : PAS
// un miroir exact — le serveur aliase `base_names = names` (le même ensemble,
// muté pendant la boucle) là où ce code copie (`new Set(names)`). Écart
// pratiquement inerte (les noms d'un schéma sont uniques), corrigé ici seulement.
```

(b) Dans `isValidGeneratedJoin`, remplacer la ligne `typeof j.on === "string" &&` par :

```ts
    typeof j.on === "string" &&
    // REV-184(3) : la jointure compile en `USING (on)` — la colonne doit
    // exister côté BASE (schéma d'avant jointure), sinon le pipeline créé
    // n'échoue qu'à l'exécution.
    ctx.baseSchema.fields.some((f) => f.name === j.on) &&
```

(c) Juste avant le JSDoc de `applyVisualQueryClientOp`, ajouter :

```ts
export type VisualQueryLeg = "filters" | "join" | "summary";
export type VisualQueryApplyResult = { applied: VisualQueryLeg[]; ignored: VisualQueryLeg[] };

// REV-184(2) : METRIC_JSON_SCHEMA n'exige que alias/function — un modèle qui
// omet sourceColumn/p (au lieu de les envoyer à null) faisait rejeter tout le
// résumé. Aligné sur GeneratedMetric côté serveur (`is not None`).
function withNullMetricDefaults(summary: unknown): unknown {
  if (typeof summary !== "object" || summary === null) return summary;
  const s = summary as Record<string, unknown>;
  if (!Array.isArray(s.metrics)) return summary;
  return {
    ...s,
    metrics: s.metrics.map((m) => {
      if (typeof m !== "object" || m === null) return m;
      const metric = m as Record<string, unknown>;
      return { ...metric, sourceColumn: metric.sourceColumn ?? null, p: metric.p ?? null };
    }),
  };
}
```

(d) Dans le JSDoc de `applyVisualQueryClientOp`, remplacer la phrase « Retourne `true` si au moins un des trois volets a réellement été appliqué (M1 : CopilotChat n'annonce « Requête visuelle mise à jour. » que dans ce cas). » par : « Retourne, par volet, ce qui a été appliqué et ce qui a été ignoré (REV-184(1), affiné depuis M1) : VisualQueryCopilotPanel n'annonce « Requête visuelle mise à jour. » sans réserve que si rien n'a été ignoré. »

(e) Remplacer le corps de la fonction, de sa signature de retour jusqu'à la fin (l.161-203) :

```ts
): VisualQueryApplyResult {
  const result: VisualQueryApplyResult = { applied: [], ignored: [] };
  if (raw.op !== "applyVisualQueryDraft") return result;
  const known = knownColumnNames(ctx);
  const args = raw.args as { filters?: unknown; join?: unknown; summary?: unknown };
  if (Array.isArray(args.filters)) {
    const rows = args.filters.filter((r) => isValidGeneratedFilterRow(r, known)) as FilterRow[];
    // I4 : ne jamais vider les filtres existants parce que TOUT ce que le
    // modèle a proposé était invalide. Un tableau vide envoyé explicitement
    // reste une demande légitime d'effacement, et passe.
    if (rows.length > 0 || args.filters.length === 0) {
      setters.setFilters(rows);
      result.applied.push("filters");
    }
    // REV-184(1) : une seule ligne écartée suffit à signaler la jambe.
    if (rows.length < args.filters.length) result.ignored.push("filters");
  }
  if ("join" in args) {
    if (args.join === null) {
      setters.setJoin(null);
      result.applied.push("join");
    } else if (isValidGeneratedJoin(args.join, ctx)) {
      setters.setJoin(args.join);
      result.applied.push("join");
    } else {
      result.ignored.push("join");
    }
  }
  if ("summary" in args) {
    if (args.summary === null) {
      setters.setSummary(null);
      result.applied.push("summary");
    } else {
      const summary = withNullMetricDefaults(args.summary);
      if (isValidGeneratedSummary(summary, known)) {
        setters.setSummary(summary);
        result.applied.push("summary");
      } else {
        result.ignored.push("summary");
      }
    }
  }
  return result;
}
```

- [ ] **Step 4: Panneau, chat et clés i18n**

`shell/src/i18n/catalog.fr.ts`, juste après `"copilot.opVisualQueryDraftApplied": "Requête visuelle mise à jour.",` :

```ts
  "copilot.opVisualQueryPartial": "Requête visuelle mise à jour ; ignoré (invalide) : {legs}.",
  "copilot.legFilters": "filtres",
  "copilot.legJoin": "jointure",
  "copilot.legSummary": "résumé",
```

`shell/src/builder/copilot/VisualQueryCopilotPanel.tsx` :
- remplacer l'import `import { t } from "../../i18n";` par `import { t, type MessageKey } from "../../i18n";` ;
- remplacer `import { applyVisualQueryClientOp } from "./applyVisualQueryClientOp";` par `import { applyVisualQueryClientOp, type VisualQueryLeg } from "./applyVisualQueryClientOp";` ;
- ajouter avant `export function VisualQueryCopilotPanel` :

```ts
const LEG_LABELS: Record<VisualQueryLeg, MessageKey> = {
  filters: "copilot.legFilters",
  join: "copilot.legJoin",
  summary: "copilot.legSummary",
};
```
- remplacer `handleClientOps` (l.44-52) par :

```ts
  // REV-184(1) : `false` = rien appliqué (CopilotChat annonce l'op abandonnée),
  // `true` = tout appliqué, chaîne = appliqué en partie, avec les volets ignorés.
  function handleClientOps(ops: CopilotClientOp[]): (boolean | string)[] {
    return (ops as RawClientOp[]).map((op) => {
      const { applied, ignored } = applyVisualQueryClientOp(
        op,
        { setFilters, setJoin, setSummary },
        { baseSchema, joinedSchema, collectionIds },
      );
      if (applied.length === 0) return false;
      if (ignored.length === 0) return true;
      return t("copilot.opVisualQueryPartial", {
        legs: ignored.map((leg) => t(LEG_LABELS[leg])).join(", "),
      });
    });
  }
```
Vérifier que `MessageKey` est bien exporté par `src/i18n/index.ts` (`UsagePage.tsx` l.14 l'importe déjà depuis `../i18n`). S'il ne l'est pas en export nommé du même module, utiliser `import type { MessageKey } from "../../i18n";` séparément.

`shell/src/builder/copilot/CopilotChat.tsx` :
- dans les props, remplacer le commentaire et le type l.48-53 par :

```ts
  // Retour optionnel (M1, revue finale de branche GAP-17) : un tableau
  // aligné sur `ops`, `true` quand l'op a réellement été appliquée, une
  // CHAÎNE quand elle ne l'a été qu'en partie (REV-184(1) : libellé affiché
  // tel quel). Un appelant qui ne renvoie rien (CopilotPanel, qui édite via
  // setDraft et n'a rien à abandonner) garde le comportement historique —
  // tout est annoncé comme appliqué.
  onClientOps: (ops: CopilotClientOp[]) => (boolean | string)[] | void;
```
- remplacer le `map` du résumé (l.127-132) par :

```ts
        setLastOpsSummary(
          result.clientOps.map((o, i) => {
            const outcome = Array.isArray(applied) ? applied[i] : true;
            if (typeof outcome === "string") return outcome;
            if (outcome !== true) return t("copilot.opDropped", { op: o.op });
            return opLabels[o.op] ?? t("copilot.opUnknownIgnored", { op: o.op });
          }),
        );
```

- [ ] **Step 5: Relancer**

Run: `cd shell && npx vitest run src/builder/copilot/ && node scripts/check-i18n-unused.mjs && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tous les tests du dossier `copilot/` passent, `OK` du détecteur de clés, aucun diagnostic.

- [ ] **Step 6: Contrôle bundle** (cf. intro). Les 4 clés du catalogue sont dans le chunk d'entrée, environ 0,15 Ko.

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/copilot/applyVisualQueryClientOp.ts shell/src/builder/copilot/applyVisualQueryClientOp.test.ts shell/src/builder/copilot/VisualQueryCopilotPanel.tsx shell/src/builder/copilot/VisualQueryCopilotPanel.test.tsx shell/src/builder/copilot/CopilotChat.tsx shell/src/i18n/catalog.fr.ts
git commit -m "fix(shell): copilote de requête visuelle — statut par volet, join.on validé (rev-184)

REV-184 (1) jambes ignorées annoncées, (2) sourceColumn/p absents
normalisés à null, (3) join.on vérifié côté base, (4) commentaire
« miroir exact » corrigé.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-8: REV-287(a) — après une écriture confirmée du copilote, le catalogue se rafraîchit

**Files:**
- Modify: `shell/src/builder/copilot/CopilotChat.tsx`. Import l.6, `confirmWrite` l.75-95.
- Modify: `shell/src/builder/copilot/CopilotChat.test.tsx` (1 test)

**Interfaces:**
- Consumes : les seules écritures confirmables sont `create_item` et `create_form_app` (`core/app/copilot/tools_allowlist.py`, `COPILOT_WRITE_TOOL_NAMES`). Ces deux outils **créent** un item. La clé à invalider est donc la liste du catalogue `["items"]` (`api/hooks/items.hooks.ts:18`), et non les requêtes de l'item ouvert comme le supposait la spec.
- Produces : après un `copilotTurn` de confirmation **réussi**, `queryClient.invalidateQueries({ queryKey: ["items"] })`. Le client est lu via `useContext(QueryClientContext)`, qui est optionnel : 5 fichiers de test montent `CopilotChat` sans `QueryClientProvider` (`CopilotChat.test`, `CopilotPanel.test`, `SqlLabCopilotPanel.test`, `VisualQueryCopilotPanel.test`, `CopilotChatBounds.test`). `useQueryClient()` y lèverait une erreur.

Dépend de L5a-7, qui modifie le même fichier.

- [ ] **Step 1: Test qui échoue**

Dans `shell/src/builder/copilot/CopilotChat.test.tsx`, ajouter `import { QueryClient, QueryClientProvider } from "@tanstack/react-query";` en tête, puis dans le `describe` :

```ts
  it("REV-287 : une écriture confirmée invalide la liste du catalogue", async () => {
    const copilotTurn = vi
      .fn()
      .mockResolvedValueOnce({
        reply: "Je crée l'app.",
        clientOps: [{ op: "confirmWrite", args: { name: "create_item", arguments: { a: 1 } } }],
      })
      .mockResolvedValueOnce({ reply: "create_item effectué : ok", clientOps: [] });
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    render(
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
          <CopilotChat
            surface="builder"
            contextPayload={{}}
            clientTools={[]}
            opLabels={{}}
            onClientOps={() => {}}
          />
        </ItemClientProvider>
      </QueryClientProvider>,
    );
    await userEvent.type(screen.getByLabelText("Message au copilote"), "Crée une app");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(invalidate).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: "Confirmer" }));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["items"] }));
  });
```
Vérifier que `"builder"` est une valeur de `CopilotSurface` (`api/types.ts`) ; sinon prendre celle qu'utilise `CopilotPanel.tsx`.

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/copilot/CopilotChat.test.tsx -t "REV-287"`
Expected : FAIL, timeout du `waitFor` (`invalidateQueries` jamais appelé).

- [ ] **Step 3: Implémenter**

`shell/src/builder/copilot/CopilotChat.tsx` :
- l.6 : `import { useContext, useEffect, useRef, useState } from "react";` ;
- ajouter l'import `import { QueryClientContext } from "@tanstack/react-query";` ;
- après `const getMcpToken = useMcpToken();`, ajouter :

```ts
  // REV-287(a) : contexte lu sans exiger de provider (plusieurs montages de
  // test n'en ont pas) — useQueryClient() lèverait.
  const queryClient = useContext(QueryClientContext);
```
- dans `confirmWrite`, après `setHistory((h) => [...h, { role: "assistant", content: result.reply }]);`, ajouter :

```ts
      // Les écritures confirmables (create_item, create_form_app) CRÉENT un
      // item : la liste du catalogue est périmée.
      void queryClient?.invalidateQueries({ queryKey: ["items"] });
```

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/builder/copilot/ && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe.

- [ ] **Step 5: Commit** (copilote `lazy()`)

```bash
git add shell/src/builder/copilot/CopilotChat.tsx shell/src/builder/copilot/CopilotChat.test.tsx
git commit -m "fix(shell): écriture confirmée du copilote invalide la liste du catalogue (rev-287)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-9: REV-287(b) — l'échec d'audit d'un tour de copilote est journalisé, plus avalé

**Files:**
- Modify: `core/app/copilot/routes.py`. Imports l.2-6, `finally` l.378-383.
- Modify: `core/tests/test_copilot_routes.py` (1 test)

**Interfaces:**
- Produces : le module a un `logger = logging.getLogger(__name__)`, nommé `app.copilot.routes`. En cas d'exception de `_write_turn_audit`, il émet `logger.exception("copilot.turn audit failed")`. La réponse reste 200 : la trace reste best-effort.

- [ ] **Step 1: Test qui échoue**

Ajouter à `core/tests/test_copilot_routes.py`, à la suite de `test_plain_text_reply_with_no_tool_calls` :

```python
def test_turn_audit_failure_is_logged_not_swallowed(client, monkeypatch, caplog):
    import logging

    import app.copilot.routes as routes_module

    monkeypatch.setattr(
        routes_module,
        "get_llm_provider",
        lambda: FakeLLMProvider(responses=[LLMTurn(text="ok")]),
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("audit indisponible")

    monkeypatch.setattr(routes_module, "_write_turn_audit", _boom)
    with caplog.at_level(logging.ERROR, logger="app.copilot.routes"):
        resp = client.post(
            "/v1/copilot/turn",
            json={
                "itemId": "1",
                "message": "bonjour",
                "history": [],
                "mcpToken": "x",
                "currentConfig": {},
                "clientTools": [],
            },
        )
    assert resp.status_code == 200
    assert "copilot.turn audit failed" in caplog.text
    assert "audit indisponible" in caplog.text
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run (depuis `core/`): `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_copilot_routes.py -k audit_failure -q --basetemp=/tmp/l5a-pytest`
Expected : `1 failed`. `assert "copilot.turn audit failed" in caplog.text` échoue, car l'exception est avalée par `pass`.

- [ ] **Step 3: Implémenter**

`core/app/copilot/routes.py` : ajouter `import logging` dans le bloc stdlib (entre `import json` et `import secrets`), et après `router = APIRouter()` (ou à défaut juste après les imports) :

```python
logger = logging.getLogger(__name__)
```
Remplacer :

```python
        except Exception:  # pragma: no cover
            pass
```
par :

```python
        except Exception:
            # REV-287(b) : best-effort (la réponse part quand même), mais jamais
            # silencieux — une trace d'audit perdue doit se voir dans les logs.
            logger.exception("copilot.turn audit failed")
```

- [ ] **Step 4: Relancer**

Run (depuis `core/`): `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_copilot_routes.py -q --basetemp=/tmp/l5a-pytest && uv run ruff check app/copilot tests/test_copilot_routes.py && uv run ruff format --check app/copilot tests/test_copilot_routes.py && uv run mypy --strict app/copilot`
Expected : le fichier est entièrement vert, ruff est propre et mypy affiche `Success`.

- [ ] **Step 5: Commit** (pas de changement de route ni de modèle : pas de régénération OpenAPI)

```bash
git add core/app/copilot/routes.py core/tests/test_copilot_routes.py
git commit -m "fix(core): échec d'audit d'un tour de copilote journalisé au lieu d'être avalé (rev-287)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-10: REV-284(b) — `<h1>` (sr-only) sur les pages embarquée, d'item public et de site

**Files:**
- Modify: `shell/src/pages/EmbedPage.tsx` : `EmbedApp` l.29, `EmbedAppRenderer` l.50-66, appel l.93.
- Modify: `shell/src/pages/PublicItemPage.tsx` (`<main>` l.50)
- Modify: `shell/src/pages/SitePublicPage.tsx` (`<main>` l.52)
- Modify: `shell/src/pages/EmbedPage.test.tsx`, `shell/src/pages/PublicItemPage.test.tsx` et `shell/src/pages/SitePublicPage.test.tsx` (1 test chacun)

**Interfaces:**
- Consumes :
  - `ResolvedShareLink.title`, déjà renvoyé par `GET /v1/share-links/{token}` (`pages/embed/resolveShareLink.ts:4`) ;
  - `itemQuery.data.title` sur les deux pages publiques.

  `AppConfig` ne porte aucun titre.
- Produces : un `<h1 className="sr-only">{titre}</h1>`, premier enfant de `<main>`. Si la mise en page de l'app contient elle-même un widget héros qui rend un `<h1>`, la page en aura deux. C'est un cas toléré ici ; le rejeu au lecteur d'écran relève de L6.

- [ ] **Step 1: Tests qui échouent**

`shell/src/pages/PublicItemPage.test.tsx`, à la suite du test « 200: … » :

```ts
test("REV-284(b) : un <h1> (sr-only) porte le titre de l'item", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getPublicAppConfig: vi.fn().mockResolvedValue(config),
  });
  expect(
    await screen.findByRole("heading", { level: 1, name: "Mon jeu de données" }),
  ).toBeInTheDocument();
});
```

`shell/src/pages/SitePublicPage.test.tsx`, à la suite du test « 200: … » :

```ts
test("REV-284(b) : un <h1> (sr-only) porte le titre du site", async () => {
  renderSite({
    getItemBySlug: vi.fn().mockResolvedValue(siteItem),
    getPublicAppConfig: vi.fn().mockResolvedValue(config),
  });
  expect(await screen.findByRole("heading", { level: 1, name: "Mon Portail" })).toBeInTheDocument();
});
```

`shell/src/pages/EmbedPage.test.tsx`, à la fin :

```ts
test("REV-284(b) : un <h1> (sr-only) porte le titre résolu du lien de partage", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/tok-app", () =>
      HttpResponse.json({
        itemId: "app-1",
        title: "Mon App",
        resourceType: "app",
        expiresAt: "2026-10-01",
      }),
    ),
    http.get("https://core.test/v1/configs/by-item/app-1", () =>
      HttpResponse.json({
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", items: [] },
        },
      }),
    ),
  );
  renderWithClient("tok-app");
  expect(await screen.findByRole("heading", { level: 1, name: "Mon App" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/EmbedPage.test.tsx src/pages/PublicItemPage.test.tsx src/pages/SitePublicPage.test.tsx -t "REV-284"`
Expected : 3 FAIL `Unable to find role="heading"`.

- [ ] **Step 3: Implémenter**

`shell/src/pages/PublicItemPage.tsx` et `shell/src/pages/SitePublicPage.tsx` : dans chacun, remplacer

```tsx
    <main className="h-full w-full">
      <AppRenderer config={configQuery.data} mode="runtime" />
    </main>
```
par

```tsx
    <main className="h-full w-full">
      {/* REV-284(b) : repère de titre pour les technologies d'assistance. */}
      <h1 className="sr-only">{itemQuery.data?.title}</h1>
      <AppRenderer config={configQuery.data} mode="runtime" />
    </main>
```

`shell/src/pages/EmbedPage.tsx` :
- `function EmbedApp({ itemId, token }: { itemId: string; token: string })` devient `function EmbedApp({ itemId, token, title }: { itemId: string; token: string; title: string })` ;
- dans son JSX, `<EmbedAppRenderer itemId={itemId} />` devient `<EmbedAppRenderer itemId={itemId} title={title} />` ;
- `function EmbedAppRenderer({ itemId }: { itemId: string })` devient `function EmbedAppRenderer({ itemId, title }: { itemId: string; title: string })` ;
- son `<main className="h-screen w-screen">` reçoit en premier enfant :

```tsx
      {/* REV-284(b) : titre résolu par le lien de partage (AppConfig n'en porte pas). */}
      <h1 className="sr-only">{title}</h1>
```
- dans `EmbedPage`, le dernier `return` devient :

```tsx
  return (
    <EmbedApp itemId={linkQuery.data.itemId} token={token} title={linkQuery.data.title} />
  );
```

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/pages/EmbedPage.test.tsx src/pages/PublicItemPage.test.tsx src/pages/SitePublicPage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe, y compris `expectTokenizedClasses`, car `sr-only` n'est pas une couleur.

- [ ] **Step 5: Commit** (pages `lazy()`)

```bash
git add shell/src/pages/EmbedPage.tsx shell/src/pages/PublicItemPage.tsx shell/src/pages/SitePublicPage.tsx shell/src/pages/EmbedPage.test.tsx shell/src/pages/PublicItemPage.test.tsx shell/src/pages/SitePublicPage.test.tsx
git commit -m "fix(shell): titre h1 sr-only sur les pages embarquée, item public et site (rev-284)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-11: REV-284(c) — `<h2>` « Résultats » (sr-only) avant la grille du catalogue, et sa jumelle publique

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx` (grille l.381-392)
- Modify: `shell/src/pages/PublicCatalogPage.tsx` (grille l.99-107). C'est la jumelle oubliée par la spec (piège n°14).
- Modify: `shell/src/i18n/catalog.fr.ts` (1 clé, à côté des `catalog.empty*` l.154-165)
- Modify: `shell/src/pages/CatalogPage.test.tsx` et `shell/src/pages/PublicCatalogPage.test.tsx` (1 test chacun)

**Interfaces:**
- Produces : la clé `"catalog.resultsHeading": "Résultats"`. Les deux grilles sont précédées de `<h2 className="sr-only">`. `ItemCard` rend un `<h3>` (`ui/kit/ItemCard.tsx:32`), et la hiérarchie devient h1 > h2 > h3.

- [ ] **Step 1: Tests qui échouent**

`shell/src/pages/CatalogPage.test.tsx`, à la suite de « lists items from the catalog » :

```ts
test("REV-284(c) : un <h2> « Résultats » (sr-only) précède la grille", async () => {
  mockCatalogItems();
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByText("Alpha");
  expect(screen.getByRole("heading", { level: 2, name: "Résultats" })).toBeInTheDocument();
});
```

`shell/src/pages/PublicCatalogPage.test.tsx`, à la fin :

```ts
test("REV-284(c) : un <h2> « Résultats » (sr-only) précède la grille publique", async () => {
  const list = vi.fn().mockResolvedValue({
    items: [item("2", "map")],
    total: 1,
    page: 1,
    pageSize: 12,
  });
  renderCatalog(list);
  expect(
    await screen.findByRole("heading", { level: 2, name: "Résultats" }),
  ).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx src/pages/PublicCatalogPage.test.tsx -t "REV-284"`
Expected : 2 FAIL `Unable to find role="heading"`.

- [ ] **Step 3: Implémenter**

`shell/src/i18n/catalog.fr.ts`, après `"catalog.emptyFilteredTitle": "Aucun résultat",` :

```ts
  "catalog.resultsHeading": "Résultats",
```

`shell/src/pages/CatalogPage.tsx`, remplacer le bloc l.381-392 :

```tsx
              {query.isSuccess && query.data.items.length > 0 && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
```
par l'ouverture suivante. Le contenu de la grille est inchangé, puis on referme le fragment.

```tsx
              {query.isSuccess && query.data.items.length > 0 && (
                <>
                  {/* REV-284(c) : repère de section pour la navigation par titres. */}
                  <h2 className="sr-only">{t("catalog.resultsHeading")}</h2>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
```
et la fermeture `                </div>\n              )}` devient `                  </div>\n                </>\n              )}`. Prettier réindente le contenu.

`shell/src/pages/PublicCatalogPage.tsx`, même transformation sur

```tsx
      {items.length > 0 && (
        <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
```
qui devient

```tsx
      {items.length > 0 && (
        <>
          <h2 className="sr-only">{t("catalog.resultsHeading")}</h2>
          <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
```
avec la fermeture `        </ul>\n      )}` qui devient `          </ul>\n        </>\n      )}`. `t` est déjà importé par les deux pages.

- [ ] **Step 4: Relancer**

Run: `cd shell && npx prettier --write src/pages/CatalogPage.tsx src/pages/PublicCatalogPage.tsx && npx vitest run src/pages/CatalogPage.test.tsx src/pages/PublicCatalogPage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe.

- [ ] **Step 5: Contrôle bundle** (cf. intro). Il y a 1 clé de catalogue en plus, de l'ordre de 40 octets.

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/PublicCatalogPage.tsx shell/src/i18n/catalog.fr.ts shell/src/pages/CatalogPage.test.tsx shell/src/pages/PublicCatalogPage.test.tsx
git commit -m "fix(shell): titre h2 « résultats » sr-only avant les grilles du catalogue (rev-284)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-12: REV-284(e) — contraste WCAG du thème d'app signalé dans `ThemePanel`

**Files:**
- Modify: `shell/src/builder/theme.ts` (ajout de `contrastRatio` en fin de fichier)
- Modify: `shell/src/builder/theme.test.ts`
- Modify: `shell/src/builder/ThemePanel.tsx` (dans le `return`, après la boucle `COLOR_FIELDS`)
- Modify: `shell/src/builder/ThemePanel.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts` (1 clé, après `"themePanel.colorBorder"` l.1837)

**Interfaces:**
- Produces :
  - `contrastRatio(a: string, b: string): number | null`. Le calcul suit le ratio WCAG 2.x sur des couleurs `#rgb` ou `#rrggbb`. La fonction renvoie `null` pour tout autre format, puisqu'`<input type="color">` produit toujours du `#rrggbb`.
  - `ThemePanel` affiche un `role="status"` quand le ratio du texte ou de la couleur atténuée sur le fond est inférieur à 4,5.
- Clé : `"themePanel.lowContrast"`.

- [ ] **Step 1: Tests qui échouent**

`shell/src/builder/theme.test.ts` : ajouter `contrastRatio` à l'import depuis `./theme`, puis :

```ts
test("contrastRatio : ratios WCAG de référence", () => {
  expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 5);
  expect(contrastRatio("#000", "#fff")).toBeCloseTo(21, 5);
  expect(contrastRatio("#ffffff", "#ffffff")).toBe(1);
  expect(contrastRatio("red", "#ffffff")).toBeNull();
});

test("contrastRatio : la couleur atténuée par défaut passe AA sur le fond par défaut", () => {
  expect(
    contrastRatio(DEFAULT_THEME_COLORS.muted, DEFAULT_THEME_COLORS.background),
  ).toBeGreaterThanOrEqual(4.5);
});
```

`shell/src/builder/ThemePanel.test.tsx`, à la fin :

```ts
test("REV-284(e) : signale une couleur atténuée illisible sur le fond", () => {
  render(<ThemePanel theme={{ colors: { muted: "#ffffff" } }} onChange={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Contraste insuffisant : « Couleur atténuée » sur la couleur de fond (1:1, minimum recommandé 4,5:1).",
  );
});

test("REV-284(e) : aucun avertissement avec le thème par défaut", () => {
  render(<ThemePanel theme={{}} onChange={vi.fn()} />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/theme.test.ts src/builder/ThemePanel.test.tsx`
Expected : FAIL. `contrastRatio` n'est pas exporté (`is not a function`) et `role="status"` est introuvable.

- [ ] **Step 3: Implémenter**

`shell/src/builder/theme.ts`, en fin de fichier :

```ts
// REV-284(e) : ratio de contraste WCAG 2.x entre deux couleurs #rgb/#rrggbb
// (format de <input type="color">) ; null pour tout autre format.
export function contrastRatio(a: string, b: string): number | null {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  if (la === null || lb === null) return null;
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

function relativeLuminance(color: string): number | null {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return null;
  const hex = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
```

`shell/src/i18n/catalog.fr.ts`, après `"themePanel.colorBorder": "Couleur de bordure",` :

```ts
  "themePanel.lowContrast":
    "Contraste insuffisant : « {label} » sur la couleur de fond ({ratio}:1, minimum recommandé 4,5:1).",
```

`shell/src/builder/ThemePanel.tsx` :
- import `contrastRatio` : `import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE, contrastRatio } from "./theme";` ;
- ajouter `import { formatNumber } from "../lib/format";` ;
- ajouter avant `export function ThemePanel` :

```ts
// REV-284(e) : paires vérifiées contre le fond — le texte courant et la
// couleur atténuée (texte secondaire) ; seuil AA texte normal.
const MIN_CONTRAST = 4.5;
const CONTRAST_CHECKED: (keyof NonNullable<Theme["colors"]>)[] = ["text", "muted"];
```
- dans le composant, avant le `return` :

```ts
  const colorOf = (key: keyof NonNullable<Theme["colors"]>) =>
    theme.colors?.[key] ?? DEFAULT_THEME_COLORS[key];
  const lowContrast = CONTRAST_CHECKED.flatMap((key) => {
    const ratio = contrastRatio(colorOf(key), colorOf("background"));
    if (ratio === null || ratio >= MIN_CONTRAST) return [];
    const label = COLOR_FIELDS.find(([k]) => k === key)?.[1] ?? key;
    return [{ key, label, ratio }];
  });
```
- dans le JSX, juste après `{COLOR_FIELDS.map(…)}` :

```tsx
      {lowContrast.map(({ key, label, ratio }) => (
        <p key={key} role="status" className="text-xs text-warn">
          {t("themePanel.lowContrast", { label, ratio: formatNumber(ratio, 1) })}
        </p>
      ))}
```

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/builder/theme.test.ts src/builder/ThemePanel.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe. `expectTokenizedClasses` reste vert puisque `text-warn` est un jeton.

- [ ] **Step 5: Contrôle bundle** (cf. intro). Il y a 1 clé de catalogue en plus. `ThemePanel` et `theme.ts` vivent dans le builder `lazy()`.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/theme.ts shell/src/builder/theme.test.ts shell/src/builder/ThemePanel.tsx shell/src/builder/ThemePanel.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): avertissement de contraste wcag dans le panneau de thème (rev-284)

REV-284(e) : texte et couleur atténuée contre le fond, seuil AA 4,5:1.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-13: REV-286(e) — `touchcancel` annule le tracé libre au lieu de le valider

**Files:**
- Modify: `shell/src/map/MapMeasureSketchToolbar.tsx` (handlers l.340-384)
- Modify: `shell/src/map/MapMeasureSketchToolbar.test.tsx` (1 test)

**Interfaces:**
- Produces : `touchcancel` remet le geste à zéro (`drawingRef=false`, points vidés) sans appeler `setShapes`. `touchend` et `mouseup` gardent la validation.

- [ ] **Step 1: Test qui échoue**

Ajouter après le test « le tracé libre fonctionne aux événements tactiles… » de `shell/src/map/MapMeasureSketchToolbar.test.tsx` :

```ts
// REV-286(e) : un geste interrompu par le système (appel entrant, geste
// multi-doigts) n'est pas une intention de dessiner.
test("touchcancel annule le tracé libre en cours sans l'enregistrer", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  act(() => map.emit("touchstart", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("touchmove", { lngLat: { lng: 1, lat: 1 } }));
  act(() => map.emit("touchcancel", {}));
  expect(screen.queryByText(/\d+ tracés?/)).not.toBeInTheDocument();
  // Un touchend tardif ne ressuscite pas le geste annulé.
  act(() => map.emit("touchend", {}));
  expect(screen.queryByText(/\d+ tracés?/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx -t "touchcancel"`
Expected : FAIL, avec `1 tracé` trouvé après `touchcancel`.

- [ ] **Step 3: Implémenter**

Dans `shell/src/map/MapMeasureSketchToolbar.tsx`, ajouter après `function onMouseUp() { … }` :

```ts
    // REV-286(e) : touchcancel = geste interrompu par le système, pas validé.
    function onCancel() {
      if (!drawingRef.current) return;
      drawingRef.current = false;
      freehandRef.current = [];
      setFreehandPoints([]);
    }
```
et remplacer `["touchcancel", onMouseUp],` par `["touchcancel", onCancel],`.

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe, y compris « le démontage retire les écouteurs », qui compte toujours 7 écouteurs.

- [ ] **Step 5: Commit** (`map/*` est `lazy()`)

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx
git commit -m "fix(shell): touchcancel annule le tracé libre au lieu de le valider (rev-286)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-14: REV-286(d) — le popup de carte se recadre quand le conteneur change de taille

**Files:**
- Modify: `shell/src/map/MapPopup.tsx` (`useLayoutEffect` l.49-61)
- Modify: `shell/src/map/MapPopup.test.tsx` : import l.2, 1 test.

**Interfaces:**
- Produces : le clamp P31.11 est recalculé à chaque redimensionnement du conteneur positionné (`offsetParent`), par exemple un volet replié ou une rotation d'écran. Si `ResizeObserver` existe, il observe ce conteneur et se déconnecte au démontage ou au changement de position. Sans `ResizeObserver` (jsdom), le comportement est inchangé.

- [ ] **Step 1: Test qui échoue**

`shell/src/map/MapPopup.test.tsx` : l'import l.2 devient `import { act, render, screen } from "@testing-library/react";`. Puis, à la fin :

```ts
// REV-286(d) : stub de ResizeObserver LOCAL au test (piège n°10, jamais
// dans setup.ts) ; mise en page simulée par des getters espionnés.
test("le clamp horizontal est recalculé quand le conteneur rétrécit", () => {
  const ro = { callback: () => {}, observe: vi.fn(), disconnect: vi.fn() };
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        ro.callback = cb;
      }
      observe = ro.observe;
      disconnect = ro.disconnect;
      unobserve() {}
    },
  );
  const parent = document.createElement("div");
  let parentWidth = 400;
  Object.defineProperty(parent, "clientWidth", { get: () => parentWidth });
  Object.defineProperty(parent, "clientHeight", { get: () => 300 });
  const spies = [
    vi.spyOn(HTMLElement.prototype, "offsetParent", "get").mockReturnValue(parent),
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(100),
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(50),
  ];
  try {
    const { unmount } = render(
      <MapPopup content={{ title: "T", rows: [], html: null }} x={350} y={200} onClose={() => {}} />,
    );
    const popup = screen.getByRole("dialog");
    expect(popup.style.left).toBe("300px"); // min(350 - 50, 400 - 100)
    expect(ro.observe).toHaveBeenCalledWith(parent);
    parentWidth = 200;
    act(() => ro.callback());
    expect(popup.style.left).toBe("100px"); // min(300, 200 - 100)
    unmount();
    expect(ro.disconnect).toHaveBeenCalled();
  } finally {
    spies.forEach((s) => s.mockRestore());
    vi.unstubAllGlobals();
  }
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/map/MapPopup.test.tsx -t "conteneur rétrécit"`
Expected : FAIL sur `expect(ro.observe).toHaveBeenCalledWith(parent)` (jamais appelé). La première assertion `300px` passe déjà, ce qui prouve que la simulation de mise en page fonctionne.

- [ ] **Step 3: Implémenter**

Dans `shell/src/map/MapPopup.tsx`, remplacer le `useLayoutEffect` (l.49-61) par :

```ts
  useLayoutEffect(() => {
    const el = containerRef.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    const popup: HTMLElement = el;
    const box: HTMLElement = parent;
    function place() {
      const w = popup.offsetWidth;
      const h = popup.offsetHeight;
      const pw = box.clientWidth;
      const ph = box.clientHeight;
      if (pw === 0 || ph === 0) return; // pas de mise en page mesurable (jsdom, conteneur masqué)
      const left = Math.max(0, Math.min(x - w / 2, pw - w));
      const above = y - h;
      const top = above >= 0 ? above : Math.max(0, Math.min(y, ph - h));
      setPlaced((p) => (p && p.left === left && p.top === top ? p : { left, top }));
    }
    place();
    // REV-286(d) : volet replié, rotation d'écran — le conteneur change de
    // taille sans que x/y bougent ; on recalcule le clamp.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(place);
    observer.observe(box);
    return () => observer.disconnect();
  }, [x, y, content, attachments]);
```

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/map/MapPopup.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe, et « is positioned where the map projected the clicked point » reste vert grâce au repli de jsdom.

- [ ] **Step 5: Commit** (`map/*` est `lazy()`)

```bash
git add shell/src/map/MapPopup.tsx shell/src/map/MapPopup.test.tsx
git commit -m "fix(shell): popup de carte recadré au redimensionnement du conteneur (rev-286)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-15: REV-286(f) — défilement de `<main>` remis en haut au changement de route

**Files:**
- Modify: `shell/src/shell/AppLayout.tsx` (imports l.2, hooks avant le retour anticipé `isExportRender` l.51, `<main>` l.89-95)
- Modify: `shell/src/shell/AppLayout.test.tsx` (1 test)

**Interfaces:**
- Produces : un changement de `location.pathname` remet `main#main-content.scrollTop` à 0. La recherche (`?q=`) et le hash ne déclenchent rien : changer un filtre ne doit pas faire remonter la page.
- `ScrollRestoration` de React Router ne convient pas. Il restaure le défilement de la **fenêtre**, alors qu'ici c'est `<main>` qui défile (P31.03, `overflow-y-auto` dans un `h-dvh`).

- [ ] **Step 1: Test qui échoue**

`shell/src/shell/AppLayout.test.tsx` :
- l'import `react-router-dom` devient `import { Link, MemoryRouter } from "react-router-dom";` ;
- ajouter à la fin :

```ts
test("REV-286(f) : changer de route remet le défilement de <main> en haut", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/a"]}>
          <AppLayout>
            <Link to="/b">aller plus loin</Link>
          </AppLayout>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  const main = screen.getByRole("main");
  main.scrollTop = 500;
  expect(main.scrollTop).toBe(500);
  await userEvent.click(screen.getByRole("link", { name: "aller plus loin" }));
  expect(main.scrollTop).toBe(0);
});
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx -t "REV-286"`
Expected : FAIL `expected 500 to be 0`.

- [ ] **Step 3: Implémenter**

`shell/src/shell/AppLayout.tsx` :
- l.2 : `import { lazy, Suspense, useEffect, useRef, useState } from "react";` ;
- ajouter `import { useLocation } from "react-router-dom";` ;
- juste après l'effet du raccourci ⌘K et **avant** `if (isExportRender) {`, puisque les hooks ne doivent pas suivre un retour anticipé :

```ts
  // REV-286(f) : c'est <main> qui défile (P31.03), pas la fenêtre —
  // ScrollRestoration de React Router n'y peut rien. Nouvelle page = en haut ;
  // un changement de ?filtre (même pathname) ne fait pas remonter.
  const mainRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname]);
```
- sur `<main id="main-content" …>`, ajouter `ref={mainRef}`.

- [ ] **Step 4: Relancer**

Run: `cd shell && npx vitest run src/shell/ && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe. `AppLayout` est toujours monté sous un routeur (`routes.tsx:252`).

- [ ] **Step 5: Contrôle bundle** (cf. intro). `AppLayout` est dans le chunk d'entrée, pour quelques dizaines d'octets.

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/AppLayout.tsx shell/src/shell/AppLayout.test.tsx
git commit -m "fix(shell): défilement du contenu remis en haut au changement de route (rev-286)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-16: REV-285(f) — titres des ressources d'usage résolus côté cœur, en une requête groupée

**Files:**
- Modify: `core/app/usage/schemas.py`. Ajouter `objectTitle` à `UsageTaskRead` (l.5-12) et à `UsageResourceStatRead` (l.28-31).
- Modify: `core/app/usage/service.py`. Imports l.9-16, nouvelle fonction `readable_item_titles`.
- Modify: `core/app/usage/routes.py`. `list_usage_tasks` l.34-86, `get_usage_summary` l.89-117 (la jumelle `byResource`).
- Modify: `core/app/sharing/authorization.py`. Liste des appelants de `decide()` dans la docstring, l.45-63.
- Modify: `core/tests/test_usage_routes.py` (2 tests)
- Modify (régénérés) : `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`
- Modify: `shell/src/api/types.ts` (`UsageTask` l.142-150, `UsageResourceStat` l.158)
- Modify: `shell/src/pages/UsagePage.tsx` (`ResourceLabel` l.21-37, imports l.2 et 5, appels l.161 et l.228)
- Modify: `shell/src/pages/UsagePage.test.tsx` (1 test)

**Interfaces:**
- Consumes :
  - `items_repo.get_access_facts_by_ids(session, *, tenant_id, item_ids)` (`app/items/repository.py:279`) ;
  - `roles_for_items(session, *, tenant_id, user_id, item_ids)` (`app/sharing/repository.py:24`) ;
  - `decide(*, action, kind, is_owner, is_public, is_published, roles, actor_is_admin)`.

  C'est le même patron groupé que `app.harvest.routes` (SP-49). La couche `app.usage` est au-dessus de `app.items` et `app.sharing` dans le contrat `lint-imports` (`pyproject.toml`).
- Produces :
  - `service.readable_item_titles(session, *, user, item_ids) -> dict[str, str]` renvoie les titres des seuls items **lisibles** par `user`, avec la même règle que `GET /v1/items/{id}` : propriétaire, public, publié ou rôle de partage. `tasks.view_all` n'ouvre pas la lecture d'un item privé.
  - `objectTitle: str | None` sur chaque tâche et chaque `byResource`.
  - Le shell n'appelle plus `getItem` par ligne. Avant ce correctif, il lançait N requêtes et chaque item illisible renvoyait un 404.
- Ce n'est pas une nouvelle route, juste un champ ajouté au modèle : l'inventaire de fonctionnalités ne change pas, mais OpenAPI et les types TS sont **à régénérer**.

- [ ] **Step 1: Tests cœur qui échouent**

Dans `core/tests/test_usage_routes.py`, ajouter l'import `from app.items.repository import create_item`, puis à la fin :

```python
def test_tasks_carry_title_of_readable_items_only(env):
    app, client, Session, creator, admin, reader = env
    with Session() as s:
        tenant_id = s.get(User, creator.id).tenant_id
        item = create_item(
            s,
            tenant_id=tenant_id,
            owner_id=creator.id,
            resource_type="dataset",
            title="Nettoyage des adresses",
        )
        write_audit(
            s,
            tenant_id=tenant_id,
            actor_id=creator.id,
            actor_kind="user",
            action="pipeline.run",
            object_type="pipeline",
            object_id=item.id,
        )
        s.commit()
        item_id = item.id

    _as(app, Session, creator)
    tasks = client.get("/v1/usage/tasks").json()["tasks"]
    titles = {t["objectId"]: t["objectTitle"] for t in tasks}
    assert titles[item_id] == "Nettoyage des adresses"
    assert titles["p1"] is None  # objet sans item correspondant

    # tasks.view_all n'ouvre pas la lecture d'un item privé d'un autre.
    _as(app, Session, admin)
    tasks = client.get(f"/v1/usage/tasks?actorId={creator.id}").json()["tasks"]
    assert {t["objectId"]: t["objectTitle"] for t in tasks}[item_id] is None


def test_summary_by_resource_carries_readable_title(env):
    app, client, Session, creator, admin, reader = env
    with Session() as s:
        tenant_id = s.get(User, admin.id).tenant_id
        item = create_item(
            s, tenant_id=tenant_id, owner_id=admin.id, resource_type="dataset", title="Parcs"
        )
        write_audit(
            s,
            tenant_id=tenant_id,
            actor_id=admin.id,
            actor_kind="user",
            action="export.run",
            object_type="dataset",
            object_id=item.id,
        )
        s.commit()
        item_id = item.id

    _as(app, Session, admin)
    by_resource = client.get("/v1/usage/summary").json()["byResource"]
    titles = {r["objectId"]: r["objectTitle"] for r in by_resource}
    assert titles[item_id] == "Parcs"
    assert titles["d1"] is None
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run (depuis `core/`): `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_usage_routes.py -k "title" -q --basetemp=/tmp/l5a-pytest`
Expected : `2 failed`, avec `KeyError: 'objectTitle'`.

- [ ] **Step 3: Implémenter le cœur**

`core/app/usage/schemas.py` : ajouter `objectTitle: str | None = None` en dernier champ de `UsageTaskRead` (après `createdAt`) et de `UsageResourceStatRead` (après `count`).

`core/app/usage/service.py` : compléter les imports.

```python
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.items import repository as items_repo
from app.items.models import Item
from app.sharing.authorization import decide
from app.sharing.repository import roles_for_items
from app.users.models import User
```
puis ajouter en fin de fichier :

```python
def readable_item_titles(
    session: Session, *, user: User, item_ids: Iterable[str]
) -> dict[str, str]:
    """Titres des items de `item_ids` LISIBLES par `user` (REV-285(f)) — même
    règle que GET /v1/items/{id} (propriétaire, public, publié, rôle de
    partage ; tasks.view_all n'ouvre rien). Trois requêtes quelle que soit la
    taille de la page, patron groupé de app.harvest.routes (SP-49). Un
    object_id sans item (collection, job, id supprimé) est simplement absent."""
    ids = sorted({i for i in item_ids if i})
    facts_by_id = items_repo.get_access_facts_by_ids(
        session, tenant_id=user.tenant_id, item_ids=ids
    )
    remaining = [
        item_id
        for item_id, facts in facts_by_id.items()
        if not (facts.owner_id == user.id or facts.is_public or facts.is_published)
    ]
    roles_by_id = roles_for_items(
        session, tenant_id=user.tenant_id, user_id=user.id, item_ids=remaining
    )
    readable = [
        item_id
        for item_id, facts in facts_by_id.items()
        if decide(
            action="read",
            kind="item",
            is_owner=facts.owner_id == user.id,
            is_public=facts.is_public,
            is_published=facts.is_published,
            roles=roles_by_id.get(item_id, frozenset()),
            actor_is_admin=False,
        )
    ]
    if not readable:
        return {}
    rows = session.execute(
        select(Item.id, Item.title).where(
            Item.tenant_id == user.tenant_id, Item.id.in_(readable)
        )
    ).all()
    return {row.id: row.title for row in rows}
```

`core/app/usage/routes.py` :
- dans `list_usage_tasks`, après le calcul de `names` :

```python
    # REV-285(f) : titres résolus ici en une passe groupée (plus de getItem
    # par ligne côté shell), filtrés par le droit de lecture du demandeur.
    titles = service.readable_item_titles(session, user=user, item_ids=[r.object_id for r in rows])
```
  et dans le constructeur `UsageTaskRead(…)`, ajouter `objectTitle=titles.get(r.object_id),` après `objectId=r.object_id,` ;
- dans `get_usage_summary`, après `summary = service.summarize(…)` :

```python
    titles = service.readable_item_titles(
        session, user=user, item_ids=[r.object_id for r in summary.by_resource]
    )
```
  et remplacer la compréhension `byResource=[…]` par :

```python
        byResource=[
            UsageResourceStatRead(
                objectType=r.object_type,
                objectId=r.object_id,
                count=r.count,
                objectTitle=titles.get(r.object_id),
            )
            for r in summary.by_resource
        ],
```

`core/app/sharing/authorization.py` : dans la docstring de `decide()`, ajouter après le tiret `app.harvest.routes` :

```
    - `app.usage.service.readable_item_titles` (REV-285(f), titres du journal
      d'usage) : même appel direct groupé que `app.harvest.routes`, sans
      surcharge ;
```
et remplacer, dans le paragraphe « Portée de la preuve de parité », « Les deux appels directs d'`app.harvest.routes` ne sont couverts » par « Les appels directs d'`app.harvest.routes` et d'`app.usage.service` ne sont couverts ».

- [ ] **Step 4: Relancer le cœur et les portes**

Run (depuis `core/`): `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_usage_routes.py tests/test_sharing_decide.py -q --basetemp=/tmp/l5a-pytest && uv run ruff check app/usage app/sharing tests/test_usage_routes.py && uv run ruff format --check app/usage app/sharing tests/test_usage_routes.py && uv run lint-imports`
Expected : tout vert. `lint-imports` affiche `Contracts: N kept, 0 broken`.

- [ ] **Step 5: Régénérer OpenAPI et les types TS**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --stat -- ../core/openapi.json src/api/generated/core-schema.d.ts
```
Expected : `openapi.json` et `core-schema.d.ts` modifiés, chacun avec `objectTitle` dans `UsageTaskRead` et `UsageResourceStatRead`. Un diff vide serait anormal, la route n'étant derrière aucun flag.

- [ ] **Step 6: Test shell qui échoue**

`shell/src/pages/UsagePage.test.tsx`, à la fin :

```ts
test("REV-285(f) : titre fourni par l'API d'usage, aucun GET /items par ligne", async () => {
  mockMe(["tasks.view"]);
  let itemFetches = 0;
  server.use(
    http.get("https://core.test/v1/items/:pk", () => {
      itemFetches += 1;
      return HttpResponse.json({}, { status: 404 });
    }),
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "abcdef1234",
            objectTitle: "Nettoyage des adresses",
            createdAt: "2026-09-01T00:00:00Z",
          },
          {
            id: 2,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "0123456789",
            objectTitle: null,
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 2,
        page: 1,
        pageSize: 50,
      }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("Nettoyage des adresses (Pipeline)")).toBeInTheDocument();
  expect(screen.getByText("Pipeline 01234567…")).toBeInTheDocument();
  expect(itemFetches).toBe(0);
});
```

Run: `cd shell && npx vitest run src/pages/UsagePage.test.tsx -t "REV-285"`
Expected : FAIL, car `itemFetches` vaut 2 (et le titre de repli dépend du 404).

- [ ] **Step 7: Implémenter le shell**

`shell/src/api/types.ts` : ajouter `objectTitle?: string | null;` après `objectId: string;` dans `UsageTask`, et remplacer `UsageResourceStat` par :

```ts
export type UsageResourceStat = {
  objectType: string;
  objectId: string;
  count: number;
  objectTitle?: string | null;
};
```

`shell/src/pages/UsagePage.tsx` :
- supprimer `import { useQuery } from "@tanstack/react-query";` (l.2) ;
- l.5 devient `import { useMe, useUsageSummary, useUsageTasks } from "../api/hooks";` ;
- remplacer `ResourceLabel` (commentaire inclus, l.21-37) par :

```tsx
// Ressource d'une ligne du journal : titre de l'élément (résolu par le cœur,
// REV-285(f), seulement s'il est lisible par ce profil) et son type en
// français ; repli sur « type · début d'identifiant » sinon.
function ResourceLabel({
  objectType,
  objectId,
  objectTitle,
}: {
  objectType: string;
  objectId: string;
  objectTitle?: string | null;
}) {
  const typeLabel =
    (RESOURCE_TYPE_LABELS as Record<string, string | undefined>)[objectType] ?? objectType;
  if (objectTitle) return <>{t("usage.resourceLabel", { title: objectTitle, type: typeLabel })}</>;
  return <>{t("usage.resourceFallback", { type: typeLabel, id: objectId.slice(0, 8) })}</>;
}
```
- passer la prop aux deux appels :
  `<ResourceLabel objectType={task.objectType} objectId={task.objectId} objectTitle={task.objectTitle} />` (colonne Ressource) et `<ResourceLabel objectType={r.objectType} objectId={r.objectId} objectTitle={r.objectTitle} />` (`byResource`).
- Si `useItemClient` n'a plus d'autre usage dans le fichier, `tsc`/ESLint le signaleront. Le retirer de l'import est alors déjà fait par la ligne ci-dessus.

- [ ] **Step 8: Relancer**

Run: `cd shell && npx vitest run src/pages/UsagePage.test.tsx && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : tout passe. Le test « un profil tasks.view_all voit les deux sections » rend désormais `byResource` sans titre, avec le repli « Collection c1… », et reste vert.

- [ ] **Step 9: Commit** (`UsagePage` est `lazy()` ; `types.ts` n'est que du typage)

```bash
git add core/app/usage/schemas.py core/app/usage/service.py core/app/usage/routes.py core/app/sharing/authorization.py core/tests/test_usage_routes.py core/openapi.json shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts shell/src/pages/UsagePage.tsx shell/src/pages/UsagePage.test.tsx
git commit -m "feat(core): titres des ressources d'usage résolus côté cœur, filtrés par lecture (rev-285)

REV-285(f) : objectTitle sur /usage/tasks et /usage/summary.byResource,
une passe groupée (décide() comme harvest) ; le shell n'appelle plus
getItem par ligne. OpenAPI + types TS régénérés.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L5a-17: REV-293 — double montage StrictMode et `releaseLumaCanvasObserver` : mesurer puis décider

**Files:**
- Create (temporaire, **jamais commité**) : `shell/playwright.strictdev.config.ts`
- Create: `.superpowers/sdd/backlogB-L5a-293-mesure.txt` (ledger de mesure)
- Modify (seulement si la branche B s'applique) : `shell/src/map/mapDeckTerrain.ts` (commentaire au-dessus de `releaseLumaCanvasObserver`, l.79-84)

**Interfaces:**
- Consumes :
  - `releaseLumaCanvasObserver(map)` (`mapDeckTerrain.ts:85-94`), qui n'a qu'**un seul** site d'appel : le nettoyage d'effet de `MapView.tsx:433`, une fois par instance de carte ;
  - `e2e/map-editor-leak.spec.ts`, qui fait 8 cycles d'ouverture de l'éditeur et vérifie que les nœuds restent sous 400 et les écouteurs sous 200.
- Produces : un verdict documenté, sans code de production modifié en branche A.

La spec demande une libération idempotente (`WeakSet` de contextes détruits) avec un test de double appel. Le code réel ne le justifie pas. Sous StrictMode, chaque montage crée **sa propre** carte et donc son propre canvas et son propre contexte WebGL, et le nettoyage n'est appelé qu'une fois par carte. Un `WeakSet` ne verrait donc jamais deux fois le même contexte : ce serait du code mort, testé sur un scénario qui n'arrive pas. `canvasContext.destroy?.()` est en outre déjà protégé par `try/catch`. Il reste un seul vrai doute, la fuite elle-même en mode développement : le e2e normal tourne sur `build` + `preview`, et le double montage n'existe qu'en dev. On mesure donc avant de toucher le code.

- [ ] **Step 1: Configuration Playwright temporaire contre `vite dev`**

`shell/playwright.strictdev.config.ts` :

```ts
// TEMPORAIRE (REV-293) — ne pas commiter. Rejoue le test de fuite contre
// `vite dev`, seul mode où StrictMode double-monte (main.tsx).
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /map-editor-leak\.spec\.ts$/,
  use: { baseURL: "http://localhost:5175" },
  webServer: {
    command: "npx vite --port 5175 --strictPort",
    url: "http://localhost:5175",
    reuseExistingServer: false,
    timeout: 120_000,
    env: { VITE_AUTH_MODE: "mock", VITE_CORE_URL: "https://core.test" },
  },
});
```

- [ ] **Step 2: Mesurer**

Run: `cd shell && npx playwright test -c playwright.strictdev.config.ts 2>&1 | tee /tmp/l5a-293.log`
Puis consigner dans `.superpowers/sdd/backlogB-L5a-293-mesure.txt` :
- la date et le commit (`git rev-parse --short HEAD`) ;
- le verdict `passed`/`failed` ;
- si le test échoue, les valeurs `nodes`/`listeners` affichées par l'assertion en échec.

Enfin, `rm shell/playwright.strictdev.config.ts`.

- [ ] **Step 3a (branche A — le test passe en dev) : non-reproduction documentée**

Aucun changement de code. Le ledger reçoit cette conclusion : « double montage StrictMode : pas de fuite mesurée en vite dev, chaque montage détruit le CanvasContext de sa propre carte ; WeakSet de la spec non appliqué (site d'appel unique par carte) ». REV-293 est fermé par la note de clôture du lot, qui cite ce ledger.

- [ ] **Step 3b (branche B — le test échoue en dev seulement) : acceptation documentée**

Le e2e normal sur build reste vert : c'est lui le filet de production. Ajouter à la fin du commentaire au-dessus de `releaseLumaCanvasObserver` dans `shell/src/map/mapDeckTerrain.ts` (après la ligne `// deck.gl détruit lui-même ce contexte à MapboxOverlay.onRemove.`) :

```ts
// REV-293 : en `vite dev`, StrictMode double-monte MapView ; une croissance
// résiduelle y a été mesurée (cf. .superpowers/sdd/backlogB-L5a-293-mesure.txt),
// absente du build de production (e2e/map-editor-leak.spec.ts). Acceptée :
// chaque montage a sa propre carte, la libération n'est appelée qu'une fois
// par carte — une garde d'idempotence (WeakSet) n'y changerait rien.
```
Puis : `cd shell && npx vitest run src/map/ && npm run lint && npm run format:check`. Expected : tout passe.

- [ ] **Step 4: Commit**

Branche A, ledger seul. Le dossier `.superpowers/sdd/` est partiellement tracké : vérifier d'abord avec `git check-ignore -v .superpowers/sdd/backlogB-L5a-293-mesure.txt`. Si le fichier est ignoré, ne rien commiter et le citer dans la note de clôture. Sinon :

```bash
git add .superpowers/sdd/backlogB-L5a-293-mesure.txt
git commit -m "docs(shell): mesure du double montage strictmode sur la fuite luma (rev-293)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Branche B, ajouter `shell/src/map/mapDeckTerrain.ts` au même `git add`, avec le sujet `docs(shell): fuite luma résiduelle en dev strictmode documentée et acceptée (rev-293)`.

Dans les deux branches, vérifier `git status --short shell/playwright.strictdev.config.ts`. Expected : sortie vide, car le fichier est supprimé et jamais commité.

---

### Task L5a-18: portes de qualité du lot L5a

**Files:** aucun (vérification). Un correctif éventuel est commité dans la tâche fautive, en `fix(...)`.

**Interfaces:**
- Consumes : L5a-1 à L5a-17.
- Produces : un lot vert sur les mêmes portes que la CI.

- [ ] **Step 1: Shell complet**

```bash
cd shell && rm -rf dist dist-export && npm run test -- --coverage && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold && npx tsc --noEmit && npm run lint && npm run format:check
```
Expected : Vitest est entièrement vert, la couverture reste au-dessus du seuil, et `lint` (qui inclut `lint:i18n-unused` et `lint:colors` étendus) est vert.

- [ ] **Step 2: Bundle final**

```bash
cd shell && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```
Expected : la mesure reste sous le seuil, éventuellement relevé et justifié en L5a-4, L5a-3, L5a-7, L5a-11, L5a-12 ou L5a-15. Noter la mesure finale pour la note de clôture.

- [ ] **Step 3: Cœur, fichiers touchés et portes**

Run (depuis `core/`): `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_usage_routes.py tests/test_copilot_routes.py tests/test_sharing_decide.py tests/test_feature_inventory.py -q --basetemp=/tmp/l5a-pytest && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles`
Expected : tout vert. `test_feature_inventory` reste vert puisqu'aucune route, outil MCP ou route shell n'est nouveau.

- [ ] **Step 4: Dérive OpenAPI nulle**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types && git diff --exit-code -- ../core/openapi.json src/api/generated/core-schema.d.ts
```
Expected : code 0, aucune dérive, car L5a-16 a déjà commité la régénération.

- [ ] **Step 5: E2E complet (piège n°6)**

Run: `cd shell && npm run e2e`
Expected : `0 failed`. Rejouer d'abord en isolation tout rouge sur `a11y-audit.spec.ts`, `pipeline-builder`/`visual-query*`, `sql-lab*`, `map-*` et `catalog*`, qui sont les surfaces touchées par ce lot. Depuis le 2026-09-06, un rouge est réel : corriger dans la tâche fautive.

---

### Notes de vérification (lot L5a)

- **REV-254** : la moitié « `fetch` nus » est déjà faite, puisque tous les fichiers de domaine passent par `authFetch`/`fetchWithTimeout`. Seul reste le `PUT` S3 présigné de `exportsIngestion.ts:78`, une exception assumée. L5a-4 ne traite que les mutations.
- **REV-285(c)** :
  - les `extensions.field*` (`AdminExtensionsPage.tsx:42`) et `alertRule.state*` (`AlertRuleEditor.tsx:40`) ne sont **pas** orphelines : elles sont construites par gabarit ;
  - les vraies orphelines sont 4 clés : `actions.editTitle`, `actions.thumbnailTitle`, `locked.needDelete` et `extensions.loading` ;
  - les 20 `roles.privilege.*` sont fournies par le cœur et passent en allowlist.
- **REV-285(d)** : les `.ts` hors `map/` et `ui/kit/` sont désormais couverts. `map/*` reste exclu, conformément au périmètre de la spec. Les seuls offenseurs `.ts` sont des hexadécimaux délibérés (palettes, thème d'app, trait d'icône), couverts par un pragma de région.
- **REV-285(f)** :
  - jumelle oubliée : `GET /usage/summary.byResource` a le même N+1 côté shell (piège n°14), corrigé dans la même tâche ;
  - le titre est filtré par le droit de lecture via `decide()` (patron harvest), car `tasks.view_all` n'ouvre pas la lecture d'un item privé ;
  - pas de nouvelle route, donc l'inventaire est inchangé, mais OpenAPI et les types TS sont régénérés.
- **REV-284(c)** : jumelle `PublicCatalogPage` ajoutée.
- **REV-287(a)** : les écritures confirmables (`create_item`, `create_form_app`) **créent** un item. On invalide donc `["items"]` (le catalogue), pas les requêtes de l'item ouvert. `useContext(QueryClientContext)` plutôt que `useQueryClient()`, car 5 montages de test n'ont pas de provider.
- **REV-293** : un `WeakSet` d'idempotence serait du code mort. Il n'y a qu'un site d'appel par carte, et chaque montage StrictMode a sa propre carte. La tâche est remplacée par une mesure en `vite dev` (seul mode avec double montage), suivie soit d'une non-reproduction, soit d'une acceptation documentée.
- **REV-184(5)** : `useCollectionsAdmin()` est inconditionnel. Le `enabled: copilotEnabled` cité n'existe plus, et la troncature de la première page (`DEFAULT_LIMIT=100`) est documentée en commentaire.
- **REV-184(2)** : la normalisation `?? null` va dans l'applier (lieu du rejet), pas dans `visualQueryClientTools.ts`, qui ne porte que le schéma JSON.
- **REV-184(4)** : l'aliasing serveur `base_names = names` est pratiquement inerte, puisque les noms d'un schéma sont uniques. Seul le commentaire « miroir exact » est corrigé.
- **REV-251** : le patron cité de `PipelineBuilderPage` bloque toute la page (`LoadingState` / page d'erreur). Il est adapté ici en désactivant le bouton sans message pendant le chargement.
- **REV-286(f)** : `ScrollRestoration` agit sur la fenêtre alors que c'est `<main>` qui défile, d'où une remise à zéro manuelle par `pathname`.
- **Bundle** : seuls le catalogue i18n, `ConnectivityBanner`, `AppLayout` et `lib/format.ts` sont dans le chunk d'entrée. L5a-1 libère des octets en premier. L5a-4 risque de demander un relèvement documenté du seuil.

---

## Lot L5b — Fonctionnalités v1 (REV-183, REV-102, REV-104)

Trois fonctionnalités v1 indépendantes : chaque sous-section s'exécute seule, dans n'importe quel ordre
relatif aux deux autres. À l'intérieur d'une sous-section, les tâches sont ordonnées par dépendance.
Garde-fous communs aux trois :

- **Bundle shell** (marge 0,4 Ko sur 730 Ko) : tout nouveau composant shell est chargé par `lazy()`.
  Seule la charge **initiale** compte (`scripts/check-bundle-size.mjs` additionne l'entrée et ses
  imports statiques). Les pages concernées sont déjà des routes lazy (`shell/src/shell/routes.tsx`).
  Le coût initial résiduel vient donc des clés i18n : `i18n/index.ts` importe statiquement
  `catalog.fr.ts`. Pour REV-102, il faut ajouter aussi une méthode `ItemClient`. Chaque sous-section
  finit par une étape de mesure et, seulement en cas de dépassement, relève le seuil au plafond mesuré
  avec une justification.
- **OpenAPI/TS** : seul REV-102 ajoute une route REST. Pour REV-183, le changement est un outil MCP
  et le routeur copilote est derrière un flag, absent de `core/openapi.json`. Pour REV-104, les
  props de widget sont un `dict` non typé. La régénération y est quand même lancée, et un diff vide
  est attendu et légitime (piège n°1).
- **Inventaire** : toute route REST ou tout outil MCP nouveau est ajouté à
  `docs/revue/inventaire-fonctionnalites.jsonl` **dans la même tâche** que la surface. Sinon
  `core/tests/test_feature_inventory.py` échoue. Le `--write` du bilan relève de la tâche de clôture
  du contrôleur ; ici, on lance seulement `--check`.

Recette de test cœur : depuis `core/`, préfixer chaque `uv run pytest` par
`CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="`.
Dans les étapes ci-dessous, ce préfixe est noté `$CORE_ENV`. Exemple :
`$CORE_ENV uv run pytest tests/x.py -q --basetemp=/tmp/pytest-l5b`.

---

### REV-183 — NL→CEL v1 (`visibleWhen` uniquement)

Flux : bouton « Générer » sous `visibleWhen` dans `PropsPanel`
→ `client.copilotTurn(itemId, {surface: "visible_when", clientTools: [applyCelDraft]})`
→ le LLM appelle l'outil MCP `generate_cel_expression`, qui fait une génération pure et n'écrit rien
→ le LLM appelle l'outil client `applyCelDraft`
→ le shell affiche le brouillon validé par `validateExpression`.
Le brouillon n'est **appliqué que sur clic « Appliquer »**.

Hors v1 : colonnes calculées, actions, bindings, champs `record.*` (la liste proposée se limite à
`vars.<nom>` des variables de l'app et à `user.name`).

#### Task L5b-183-1 : outil MCP `generate_cel_expression` (génération pure, bornée, validée)

**Files:**
- Modify: `core/app/mcp/tools/query_generation.py`
  - import `require_access` (l.25-30)
  - nouvelles constantes après `_strip_code_fence` (l.44-52)
  - nouvel outil à la fin de `register()`, après `generate_visual_query` (fin de fichier, l.260)
- Create: `core/tests/test_mcp_tools_generate_cel_expression.py`
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (1 ligne ajoutée en fin de fichier)

**Interfaces:**
- Consumes:
  - `require_access(session, *, user, item_id, action)` (`core/app/mcp/tools/identity.py:73`)
  - `_cel_syntax_error(expr) -> str | None` (`core/app/configs/document_validation.py:22`).
    `app.mcp` est au-dessus de `app.configs` dans le contrat de couches, donc l'import est autorisé.
  - `get_llm_provider()` et `_strip_code_fence()` (même fichier)
- Produces: l'outil MCP `generate_cel_expression(itemId: str, question: str, availableFields: list[str]) -> {"expression": str}`.
  Consommé par L5b-183-2 (allowlist) et L5b-183-3 (via le tour de copilote).
  - Erreurs (ValueError → `isError`) :
    - `item not found` / `not allowed to modify this item`
    - `question trop longue…`
    - `trop de champs…`
    - `le fournisseur LLM est indisponible`
    - `…aucune expression`
    - `expression CEL invalide : …`
    - `champs inconnus dans l'expression : …`

- [ ] **Step 1 : écrire les tests (échouent)**

Create `core/tests/test_mcp_tools_generate_cel_expression.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""generate_cel_expression (REV-183) — brouillon CEL pour visibleWhen. Génération
pure : n'écrit ni n'exécute jamais rien (même patron que generate_sql_query)."""

import asyncio

import httpx
from mcp.server.fastmcp import FastMCP

from app.copilot.egress import EgressBlockedError
from app.copilot.llm_provider import LLMTurn
from app.mcp.tools import register_tools
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import (  # noqa: F401
    _seed_item,
    app_client,
    call_tool,
    call_tool_expecting_error,
)

FIELDS = ["vars.statut", "user.name"]


class _StubLLMProvider:
    def __init__(self, text):
        self._text = text
        self.prompts: list[str] = []

    async def chat(self, messages, tools):
        self.prompts.append(messages[0]["content"])
        return LLMTurn(text=self._text)


class _FailingLLMProvider:
    def __init__(self, exc):
        self._exc = exc

    async def chat(self, messages, tools):
        raise self._exc


def _stub(monkeypatch, provider):
    monkeypatch.setattr("app.mcp.tools.query_generation.get_llm_provider", lambda: provider)


def _args(item_id, **over):
    base = {"itemId": item_id, "question": "visible si le statut est ouvert"}
    return {**base, "availableFields": FIELDS, **over}


def test_schema_declares_item_question_and_fields():
    server = FastMCP("schema")
    register_tools(server, None)
    tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "generate_cel_expression")
    schema = tool.inputSchema
    assert set(schema["required"]) == {"itemId", "question", "availableFields"}
    assert schema["properties"]["itemId"]["type"] == "string"
    assert schema["properties"]["question"]["type"] == "string"
    assert schema["properties"]["availableFields"]["type"] == "array"
    assert schema["properties"]["availableFields"]["items"] == {"type": "string"}


def test_generates_a_fenced_expression_and_lists_fields_in_the_prompt(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    provider = _StubLLMProvider('```cel\nvars.statut == "ouvert"\n```')
    _stub(monkeypatch, provider)
    with app_client:
        result = call_tool(app_client, "generate_cel_expression", _args(item_id))
    assert result == {"expression": 'vars.statut == "ouvert"'}
    assert "vars.statut" in provider.prompts[0] and "user.name" in provider.prompts[0]


def test_refuses_an_item_the_caller_cannot_see(app_client, monkeypatch):
    with app_client.session_factory() as session:
        other = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="other-sub",
            username="other",
            email=None,
            first_name="O",
            last_name="T",
        )
        session.commit()
        other_id = other.id
    item_id = _seed_item(app_client, owner_id=other_id)
    _stub(monkeypatch, _StubLLMProvider("true"))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "item not found" in error


def test_rejects_a_syntactically_broken_draft(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("vars.statut =="))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "expression CEL invalide" in error


def test_rejects_a_draft_referencing_an_unknown_field(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider('vars.inconnu == "x" && user.name == "a"'))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "champs inconnus dans l'expression : vars.inconnu" in error


def test_empty_llm_answer_is_an_error(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("   "))
    with app_client:
        error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
    assert "aucune expression" in error


def test_llm_egress_failures_become_a_generic_refusal(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    for exc in (EgressBlockedError("10.0.0.1"), httpx.ConnectError("boom")):
        _stub(monkeypatch, _FailingLLMProvider(exc))
        with app_client:
            error = call_tool_expecting_error(app_client, "generate_cel_expression", _args(item_id))
        assert "le fournisseur LLM est indisponible" in error
        assert "10.0.0.1" not in error


def test_bounds_question_and_field_list(app_client, monkeypatch):
    item_id = _seed_item(app_client, owner_id=app_client.mock_user.id)
    _stub(monkeypatch, _StubLLMProvider("true"))
    with app_client:
        long_q = call_tool_expecting_error(
            app_client, "generate_cel_expression", _args(item_id, question="x" * 2001)
        )
        many = call_tool_expecting_error(
            app_client,
            "generate_cel_expression",
            _args(item_id, availableFields=[f"vars.v{i}" for i in range(201)]),
        )
    assert "question trop longue" in long_q
    assert "trop de champs" in many
```

- [ ] **Step 2 : lancer, attendre l'échec**

Run (depuis `core/`) : `$CORE_ENV uv run pytest tests/test_mcp_tools_generate_cel_expression.py -q --basetemp=/tmp/pytest-l5b-183`
Expected : 8 tests en échec.
- `test_schema_declares…` : `StopIteration`, l'outil est absent.
- Les 7 autres : `AssertionError` (`tool generate_cel_expression errored: Unknown tool…`), ou un
  message attendu absent de l'erreur `Unknown tool`.

- [ ] **Step 3 : implémenter l'outil**

Dans `core/app/mcp/tools/query_generation.py` :

1. Docstring du module : remplacer `"""Tools MCP de génération (GAP-17) : produisent un brouillon SQL ou une`
   par `"""Tools MCP de génération (GAP-17, REV-183) : produisent un brouillon SQL, CEL ou une`.
2. Ajouter l'import, après `from app.collections.schema_json import table_info_to_schema` :
   `from app.configs.document_validation import _cel_syntax_error`
3. Ajouter `require_access,` dans le bloc `from app.mcp.tools.identity import (...)`, entre
   `http_exception_to_value_error,` et `require_collection_read,`.
4. Après la fonction `_strip_code_fence` (fin l.52), ajouter :

```python
# REV-183 : références de champ CEL d'un brouillon (vars.x, record.x, user.x).
# Toute référence absente de availableFields est refusée : le modèle ne doit
# pas inventer de variable. ponytail: une référence citée dans une chaîne
# littérale est aussi contrôlée (faux positif accepté, jamais un faux négatif).
_CEL_FIELD_REF_RE = re.compile(r"\b(?:vars|record|user)\.[A-Za-z_]\w*")
_MAX_CEL_QUESTION_CHARS = 2000
_MAX_CEL_FIELDS = 200
```

5. À la fin de `register()`, après le `return` de `generate_visual_query` (fin de fichier), ajouter
   au même niveau d'indentation que les autres `@server.tool()` :

```python
    @server.tool()
    async def generate_cel_expression(
        ctx: Context, itemId: str, question: str, availableFields: list[str]
    ) -> dict:
        """Generate a CEL boolean expression draft for a widget's visibleWhen
        condition from a natural-language question. Only the references
        listed in availableFields (e.g. "vars.statut", "user.name") may
        appear in it. Never writes anything: the caller inserts the draft
        with the client tool applyCelDraft and the human applies it. REV-183."""
        if len(question) > _MAX_CEL_QUESTION_CHARS:
            raise ValueError("question trop longue (2000 caractères maximum)")
        if len(availableFields) > _MAX_CEL_FIELDS:
            raise ValueError("trop de champs disponibles (200 maximum)")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_access(session, user=user, item_id=itemId, action="write")

        prompt = (
            "Écris une unique expression CEL booléenne (Common Expression Language) "
            "servant de condition d'affichage d'un widget. N'utilise QUE les références "
            f"suivantes (JSON) : {json.dumps(availableFields)}. Réponds uniquement par "
            "l'expression, sans aucun texte autour (un bloc de code Markdown est toléré "
            f"mais pas requis). Question : {question}"
        )
        provider = get_llm_provider()
        try:
            turn = await provider.chat(messages=[{"role": "user", "content": prompt}], tools=[])
        except EgressBlockedError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        except httpx.HTTPError as exc:
            raise ValueError("le fournisseur LLM est indisponible") from exc
        expression = _strip_code_fence(turn.text)
        if not expression:
            raise ValueError("le fournisseur LLM n'a renvoyé aucune expression")
        if error := _cel_syntax_error(expression):
            raise ValueError(f"expression CEL invalide : {error}")
        unknown = sorted(set(_CEL_FIELD_REF_RE.findall(expression)) - set(availableFields))
        if unknown:
            raise ValueError(f"champs inconnus dans l'expression : {', '.join(unknown)}")
        return {"expression": expression}
```

- [ ] **Step 4 : lancer, attendre le succès**

Run : `$CORE_ENV uv run pytest tests/test_mcp_tools_generate_cel_expression.py -q --basetemp=/tmp/pytest-l5b-183`
Expected : `8 passed`.

- [ ] **Step 5 : inventaire + porte d'inventaire**

Ajouter **en fin** de `docs/revue/inventaire-fonctionnalites.jsonl` (une seule ligne) :

```json
{"id": "plateforme-ia-generer-une-condition-d-affichage-cel-en-langage-naturel-agent-mcp", "domaine": "Plateforme IA", "fonctionnalite": "Générer une condition d'affichage CEL (visibleWhen) en langage naturel (agent MCP)", "description": "L'outil MCP generate_cel_expression demande au fournisseur LLM une expression CEL booléenne n'utilisant que les références fournies (availableFields : vars.<nom>, user.name), contrôle sa syntaxe (_cel_syntax_error) et refuse toute référence inconnue ; gardé par le droit d'écriture sur l'item, jamais écrit ni appliqué depuis l'outil : le brouillon revient au shell par l'outil client applyCelDraft et n'est appliqué que sur clic « Appliquer » (VisibleWhenGenerator). Erreurs d'egress LLM traduites en refus générique. REV-183.", "preuve": ["core/app/mcp/tools/query_generation.py", "core/tests/test_mcp_tools_generate_cel_expression.py"], "surfaces": {"rest": [], "mcp": ["generate_cel_expression"], "shell": [], "autre": []}, "publiques": [], "priorite": "moyenne", "priorite_source": "manuel-l5b", "note_sp42": "Entrée créée par le lot L5b (REV-183) : outil MCP ajouté après la matrice SP-42.", "note_sp42_date": "2026-10-04"}
```

Run :
- `$CORE_ENV uv run pytest tests/test_feature_inventory.py tests/test_mcp_copilot_p23.py -q --basetemp=/tmp/pytest-l5b-183`
- `PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`

Expected : tous les tests passent ; `--check` sort en code 0.

- [ ] **Step 6 : qualité + commit**

Run : `uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected : aucune erreur ; `lint-imports` affiche `0 broken`.

```bash
git add core/app/mcp/tools/query_generation.py core/tests/test_mcp_tools_generate_cel_expression.py docs/revue/inventaire-fonctionnalites.jsonl
git commit -m "feat(core): outil mcp generate_cel_expression, brouillon cel pour visiblewhen (rev-183)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-183-2 : copilote — allowlist + surface `visible_when`

**Files:**
- Modify: `core/app/copilot/tools_allowlist.py`
  - docstring (l.1-12)
  - `ALLOWED_MCP_TOOL_NAMES` (l.14-25)
- Modify: `core/app/copilot/routes.py`
  - `surface: Literal[...]` (l.72)
  - `_SURFACE_INTROS` : nouvelle entrée avant le `}` de la l.139
- Modify: `core/tests/test_copilot_routes.py` (nouveaux tests après le dernier test de surface,
  ~l.892)

**Interfaces:**
- Consumes: l'outil `generate_cel_expression` (L5b-183-1).
- Produces:
  - la surface `"visible_when"` acceptée par `POST /v1/copilot/turn`
  - un message système qui oriente vers `generate_cel_expression` puis l'outil client
    `applyCelDraft` (nom figé, consommé par L5b-183-3)
  - l'outil hors `COPILOT_WRITE_TOOL_NAMES`, puisqu'il n'écrit rien

- [ ] **Step 1 : tests (échouent)**

Ajouter à la fin de `core/tests/test_copilot_routes.py` :

```python
def test_surface_visible_when_points_to_cel_generation_and_keeps_item_line(client, monkeypatch):
    captured = {}

    class _CapturingProvider:
        async def chat(self, messages, tools):
            captured["system"] = messages[0]["content"]
            return LLMTurn(text="ok")

    monkeypatch.setattr("app.copilot.routes.get_llm_provider", lambda: _CapturingProvider())
    response = client.post(
        "/v1/copilot/turn",
        json={
            "itemId": "1",
            "message": "visible si le statut est ouvert",
            "history": [],
            "mcpToken": "anything",
            "currentConfig": {"availableFields": ["vars.statut"], "visibleWhen": ""},
            "clientTools": [],
            "surface": "visible_when",
        },
    )
    assert response.status_code == 200
    intro = captured["system"].split("<<<CONFIG-")[0]
    assert "generate_cel_expression" in intro
    assert "applyCelDraft" in intro
    assert "Item en cours d'édition : 1" in captured["system"]


def test_cel_generation_is_allowlisted_but_not_a_write_tool():
    from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES, COPILOT_WRITE_TOOL_NAMES

    assert "generate_cel_expression" in ALLOWED_MCP_TOOL_NAMES
    assert "generate_cel_expression" not in COPILOT_WRITE_TOOL_NAMES
```

Run (depuis `core/`) : `$CORE_ENV uv run pytest tests/test_copilot_routes.py -q -k "visible_when or cel_generation" --basetemp=/tmp/pytest-l5b-183`
Expected : `2 failed`. Le premier échoue sur un 422, puisque la surface est inconnue du `Literal`.
Le second échoue sur un `AssertionError`.

- [ ] **Step 2 : implémenter**

Dans `core/app/copilot/tools_allowlist.py` :

1. Docstring : remplacer `generate_sql_query/generate_visual_query (GAP-17) sont des outils de`
   par `generate_sql_query/generate_visual_query (GAP-17) et generate_cel_expression (REV-183) sont des outils de`.
2. Remplacer `jamais exécuté côté serveur."""` par
   `jamais exécuté côté serveur (applyCelDraft pour un brouillon CEL)."""`.
3. Dans le frozenset, après `"generate_visual_query",`, ajouter la ligne `"generate_cel_expression",`.

Dans `core/app/copilot/routes.py` :

1. l.72 : remplacer
   `surface: Literal["app_builder", "sql_lab", "visual_query"] = "app_builder"` par
   `surface: Literal["app_builder", "sql_lab", "visual_query", "visible_when"] = "app_builder"`.
2. Juste avant le `}` qui ferme `_SURFACE_INTROS` (après l'entrée `"visual_query": (...)`), ajouter :

```python
    # REV-183 : condition d'affichage d'un widget. Le contexte porte
    # {availableFields, visibleWhen} ; rien n'est appliqué sans clic humain.
    "visible_when": (
        "Tu es le copilote qui rédige la condition d'affichage (visibleWhen, "
        "expression CEL booléenne) d'un widget du builder GeoStudio. Le contexte "
        'ci-dessous porte un champ "availableFields" : les seules références '
        "utilisables. Utilise l'outil generate_cel_expression (avec ces "
        "availableFields et l'itemId en cours d'édition) pour proposer une "
        "expression, PUIS l'outil applyCelDraft pour la proposer comme brouillon "
        "— ne l'applique jamais toi-même, l'utilisateur doit cliquer sur Appliquer."
    ),
```

- [ ] **Step 3 : lancer, attendre le succès + non-régression**

Run :
- `$CORE_ENV uv run pytest tests/test_copilot_routes.py tests/test_copilot_mcp_loopback.py tests/test_mcp_copilot_p23.py -q --basetemp=/tmp/pytest-l5b-183`
- `uv run mypy --strict app/copilot`

Expected : tous les tests passent. `test_list_tools_returns_full_catalog` prouve que le nouveau nom
de l'allowlist existe côté serveur. mypy affiche `Success: no issues found`.

- [ ] **Step 4 : OpenAPI (diff vide attendu)**

Run :

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Expected : aucune sortie, donc un diff vide. Le routeur copilote est derrière `CORE_LLM_PROVIDER` et
absent de la spec committée ; un outil MCP n'est pas une route REST. Si un diff apparaît, l'inspecter :
seule une nouvelle valeur d'énumération `visible_when` serait légitime, et on la committe alors avec
la tâche.

- [ ] **Step 5 : qualité + commit**

Run : `cd core && uv run ruff check . && uv run ruff format --check .`
Expected : aucune erreur.

```bash
git add core/app/copilot/tools_allowlist.py core/app/copilot/routes.py core/tests/test_copilot_routes.py
git commit -m "feat(core): surface copilote visible_when et generate_cel_expression en allowlist (rev-183)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-183-3 : shell — bouton « Générer » sous `visibleWhen` (lazy, application sur clic)

**Files:**
- Modify: `shell/src/api/types.ts` (l.229, `CopilotSurface`)
- Create: `shell/src/builder/copilot/celClientTools.ts`
- Create: `shell/src/builder/copilot/VisibleWhenGenerator.tsx`
- Create: `shell/src/builder/copilot/VisibleWhenGenerator.test.tsx`
- Modify: `shell/src/builder/PropsPanel.tsx`
  - imports (l.1-9)
  - props (l.11-25)
  - rendu après la fermeture du `</label>` de `visibleWhen` (l.66)
- Modify: `shell/src/builder/PropsPanel.test.tsx` (2 tests ajoutés en fin de fichier)
- Modify: `shell/src/pages/AppBuilderPage.tsx` (usage de `PropsPanel`, l.533-541)
- Modify: `shell/src/i18n/catalog.fr.ts` (5 clés après `"propsPanel.visibleWhenAria"`, l.1815)

**Interfaces:**
- Consumes:
  - `ItemClient.copilotTurn(itemId, payload)` (`shell/src/api/types.ts:500`)
  - `useMcpToken()` (`builder/copilot/useMcpToken.ts`), qui renvoie `"mock-mcp-token"` sous
    `enableMockAuth()`
  - `validateExpression` (`builder/expr.ts:22`)
  - `formatCelError` (`builder/celError.ts`)
  - la surface `visible_when` (L5b-183-2)
- Produces:
  - `VisibleWhenGenerator({itemId, availableFields, current, onApply})`
  - le prop optionnel `PropsPanel.generateItemId?: string`. Le générateur est absent sans ce prop,
    donc `LayoutEditor.tsx:94` n'est pas affecté.

- [ ] **Step 1 : tests (échouent)**

Create `shell/src/builder/copilot/VisibleWhenGenerator.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { VisibleWhenGenerator } from "./VisibleWhenGenerator";

enableMockAuth();

function renderWith(copilotTurn: ReturnType<typeof vi.fn>, onApply = vi.fn()) {
  render(
    <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
      <VisibleWhenGenerator
        itemId="9"
        availableFields={["vars.statut", "user.name"]}
        current=""
        onApply={onApply}
      />
    </ItemClientProvider>,
  );
  return onApply;
}

async function ask() {
  await userEvent.click(screen.getByText("Générer"));
  await userEvent.type(screen.getByLabelText("Décrire la condition"), "statut ouvert");
  await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
}

describe("VisibleWhenGenerator", () => {
  it("shows the draft and applies it only on click", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "Voici une condition.",
      clientOps: [{ op: "applyCelDraft", args: { expression: 'vars.statut == "ouvert"' } }],
    });
    const onApply = renderWith(copilotTurn);
    await ask();

    expect(await screen.findByText('vars.statut == "ouvert"')).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Appliquer" }));
    expect(onApply).toHaveBeenCalledWith('vars.statut == "ouvert"');

    const [itemId, payload] = copilotTurn.mock.calls[0];
    expect(itemId).toBe("9");
    expect(payload.surface).toBe("visible_when");
    expect(payload.mcpToken).toBe("mock-mcp-token");
    expect(payload.clientTools.map((tool: { name: string }) => tool.name)).toEqual([
      "applyCelDraft",
    ]);
    expect(payload.currentConfig).toEqual({
      availableFields: ["vars.statut", "user.name"],
      visibleWhen: "",
    });
  });

  it("blocks an invalid draft and explains why", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "",
      clientOps: [{ op: "applyCelDraft", args: { expression: "vars.statut ==" } }],
    });
    renderWith(copilotTurn);
    await ask();
    await screen.findByText("vars.statut ==");
    expect(screen.getByRole("button", { name: "Appliquer" })).toBeDisabled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("says when the copilot proposed nothing, and when the call failed", async () => {
    const copilotTurn = vi
      .fn()
      .mockResolvedValueOnce({ reply: "Je ne sais pas.", clientOps: [] })
      .mockRejectedValueOnce(new Error("502"));
    renderWith(copilotTurn);
    await ask();
    expect(await screen.findByText("Aucune condition proposée.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
    await waitFor(() =>
      expect(screen.getByText("Échec de la requête au copilote.")).toBeInTheDocument(),
    );
  });
});
```

Ajouter à la fin de `shell/src/builder/PropsPanel.test.tsx` :

```tsx
test("REV-183 : pas de bouton Générer sans generateItemId", () => {
  render(<PropsPanel item={item} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />, {
    wrapper,
  });
  expect(screen.queryByText("Générer")).not.toBeInTheDocument();
});

test("REV-183 : bouton Générer (chargé à la demande) avec generateItemId", async () => {
  render(
    <PropsPanel
      item={item}
      dataSources={[]}
      variables={[{ id: "v1", name: "statut", initialValue: "" }]}
      generateItemId="9"
      onChange={vi.fn()}
      onVisibleWhenChange={vi.fn()}
    />,
    { wrapper },
  );
  expect(await screen.findByText("Générer")).toBeInTheDocument();
});
```

Run : `cd shell && npx vitest run src/builder/copilot/VisibleWhenGenerator.test.tsx src/builder/PropsPanel.test.tsx`
Expected :
- `VisibleWhenGenerator.test.tsx` échoue à l'import (`Failed to resolve import "./VisibleWhenGenerator"`).
- Le 2e test REV-183 de `PropsPanel` échoue (`Unable to find an element with the text: Générer`).

- [ ] **Step 2 : implémenter**

`shell/src/api/types.ts` l.229 : remplacer
`export type CopilotSurface = "app_builder" | "sql_lab" | "visual_query";` par
`export type CopilotSurface = "app_builder" | "sql_lab" | "visual_query" | "visible_when";`.

Create `shell/src/builder/copilot/celClientTools.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
// i18n-ok-file: description de schéma d'outil envoyée au LLM (invite), pas de l'interface.
// Outil CLIENT du copilote sur la condition d'affichage (REV-183) : propose un
// brouillon CEL, jamais appliqué sans clic « Appliquer ». Même patron que
// sqlLabClientTools.ts.
import type { CopilotToolSchema } from "../../api/types";

export const CEL_DRAFT_TOOL: CopilotToolSchema = {
  name: "applyCelDraft",
  description:
    "Propose une expression CEL comme brouillon de condition d'affichage (visibleWhen). " +
    "Ne l'applique jamais — l'utilisateur doit cliquer sur Appliquer.",
  inputSchema: {
    type: "object",
    properties: { expression: { type: "string", description: "Expression CEL brouillon" } },
    required: ["expression"],
  },
};
```

Create `shell/src/builder/copilot/VisibleWhenGenerator.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
// REV-183 : brouillon de condition d'affichage (CEL) généré par le copilote
// (surface visible_when → outil MCP generate_cel_expression → op client
// applyCelDraft). Validé par validateExpression ; n'est appliqué que sur
// clic « Appliquer », jamais automatiquement. Chargé par lazy() depuis
// PropsPanel (marge de bundle initial).
import { useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import { Button } from "../../ui/kit/Button";
import { t } from "../../i18n";
import { formatCelError } from "../celError";
import { validateExpression } from "../expr";
import { CEL_DRAFT_TOOL } from "./celClientTools";
import { useMcpToken } from "./useMcpToken";

export function VisibleWhenGenerator({
  itemId,
  availableFields,
  current,
  onApply,
}: {
  itemId: string;
  availableFields: string[];
  current: string;
  onApply: (expr: string) => void;
}) {
  const client = useItemClient();
  const getMcpToken = useMcpToken();
  const [question, setQuestion] = useState("");
  const [draft, setDraft] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function propose() {
    setPending(true);
    setError(null);
    setDraft(null);
    try {
      const result = await client.copilotTurn(itemId, {
        message: question,
        history: [],
        mcpToken: await getMcpToken(),
        currentConfig: { availableFields, visibleWhen: current },
        clientTools: [CEL_DRAFT_TOOL],
        surface: "visible_when",
      });
      const op = result.clientOps.find((o) => o.op === CEL_DRAFT_TOOL.name);
      const expression = typeof op?.args.expression === "string" ? op.args.expression.trim() : "";
      if (expression) setDraft(expression);
      else setError(t("celGen.noDraft"));
    } catch {
      setError(t("copilot.requestFailed"));
    } finally {
      setPending(false);
    }
  }

  const draftError = draft ? validateExpression(draft) : null;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-xs text-ink-2">{t("celGen.summary")}</summary>
      <div className="mt-2 flex flex-col gap-2">
        <textarea
          aria-label={t("celGen.questionAria")}
          className="rounded-md border border-rule p-2 text-xs"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button
          size="sm"
          variant="outline"
          className="w-fit"
          disabled={pending || !question.trim()}
          onClick={() => void propose()}
        >
          {t("celGen.propose")}
        </Button>
        {error && (
          <span role="alert" className="text-xs text-danger">
            {error}
          </span>
        )}
        {draft !== null && (
          <>
            <code className="rounded-md border border-rule p-2 font-mono text-xs">{draft}</code>
            {draftError && (
              <span role="alert" className="whitespace-pre-line text-xs text-danger">
                {formatCelError(draftError)}
              </span>
            )}
            <Button
              size="sm"
              className="w-fit"
              disabled={draftError !== null}
              onClick={() => onApply(draft)}
            >
              {t("celGen.apply")}
            </Button>
          </>
        )}
      </div>
    </details>
  );
}
```

`shell/src/builder/PropsPanel.tsx` :
1. Ajouter en tête des imports : `import { lazy, Suspense } from "react";`.
2. Après la ligne `import { t } from "../i18n";`, ajouter :

```tsx
// REV-183 : lazy — n'alourdit pas la charge initiale (marge de bundle).
const VisibleWhenGenerator = lazy(() =>
  import("./copilot/VisibleWhenGenerator").then((m) => ({ default: m.VisibleWhenGenerator })),
);
```

3. Dans la déstructuration des props, ajouter `generateItemId,` après `onVisibleWhenChange,`. Dans le
   type, ajouter après `onVisibleWhenChange: (expr: string) => void;` :

```tsx
  // REV-183 : id de l'item à passer au copilote ; absent = pas de bouton Générer
  // (copilote désactivé, lecture seule, ou éditeur sans item).
  generateItemId?: string;
```

4. Juste après le `</label>` qui ferme le bloc `visibleWhen` (l.66), avant `<Panel`, insérer :

```tsx
      {generateItemId && (
        <Suspense fallback={null}>
          <VisibleWhenGenerator
            itemId={generateItemId}
            availableFields={[...(variables ?? []).map((v) => `vars.${v.name}`), "user.name"]}
            current={visibleWhen}
            onApply={onVisibleWhenChange}
          />
        </Suspense>
      )}
```

`shell/src/pages/AppBuilderPage.tsx` : dans le `<PropsPanel` (l.533-541), après
`onVisibleWhenChange={updateSelectedVisibleWhen}`, ajouter
`generateItemId={copilotEnabled && !readOnly ? pk : undefined}`. `copilotEnabled` est l.85,
`readOnly` l.81 et `pk` l.65.

`shell/src/i18n/catalog.fr.ts` : après la ligne
`"propsPanel.visibleWhenAria": "Condition d'affichage (visibleWhen)",` (l.1815), ajouter :

```ts
  "celGen.summary": "Générer",
  "celGen.questionAria": "Décrire la condition",
  "celGen.propose": "Proposer",
  "celGen.apply": "Appliquer",
  "celGen.noDraft": "Aucune condition proposée.",
```

- [ ] **Step 3 : lancer, attendre le succès**

Run : `cd shell && npx vitest run src/builder/copilot/VisibleWhenGenerator.test.tsx src/builder/PropsPanel.test.tsx src/builder/copilot/`
Expected : tous les tests passent (3 nouveaux + 2 PropsPanel + existants copilote).

- [ ] **Step 4 : qualité**

Run : `cd shell && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : aucune erreur. `lint:i18n` ne signale rien, puisque la description d'outil est sous
`i18n-ok-file`. `lint:aria-panel` ne signale rien : aucun `onClick` ne fait `setX(true)`.

- [ ] **Step 5 : commit**

```bash
git add shell/src/api/types.ts shell/src/builder/copilot/celClientTools.ts shell/src/builder/copilot/VisibleWhenGenerator.tsx shell/src/builder/copilot/VisibleWhenGenerator.test.tsx shell/src/builder/PropsPanel.tsx shell/src/builder/PropsPanel.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): bouton générer une condition visiblewhen par le copilote (rev-183)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-183-4 : E2E « Générer » + filet de bundle

**Files:**
- Create: `shell/e2e/visible-when-generator.spec.ts`
- Modify (conditionnel, Step 3): `shell/.bundle-size-threshold`

**Interfaces:**
- Consumes: L5b-183-3 (libellés « Générer », « Décrire la condition », « Proposer », « Appliquer »).
  Mocks `mockCore`. Création d'app → `/apps/9/edit` (`e2e/copilot.spec.ts:39-45`).
- Produces: une spec E2E.

- [ ] **Step 1 : écrire la spec**

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("REV-183 : générer une condition d'affichage, l'appliquer seulement sur clic", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, copilotEnabled: true } });
  });
  let turnBody: Record<string, unknown> = {};
  await page.route("https://core.test/v1/copilot/turn", async (route) => {
    turnBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        reply: "Voici une condition.",
        clientOps: [{ op: "applyCelDraft", args: { expression: 'user.name == "alice"' } }],
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte", exact: true }).click();
  const condition = page.getByLabel("Condition d'affichage (visibleWhen)");
  await expect(condition).toHaveValue("");

  await page.getByText("Générer", { exact: true }).click();
  await page.getByLabel("Décrire la condition").fill("visible pour alice");
  await page.getByRole("button", { name: "Proposer" }).click();
  await expect(page.getByText('user.name == "alice"')).toBeVisible();
  // Jamais appliqué sans clic humain.
  await expect(condition).toHaveValue("");

  await page.getByRole("button", { name: "Appliquer" }).click();
  await expect(condition).toHaveValue('user.name == "alice"');

  expect(turnBody.surface).toBe("visible_when");
  expect((turnBody.clientTools as { name: string }[])[0].name).toBe("applyCelDraft");
  expect((turnBody.currentConfig as { availableFields: string[] }).availableFields).toContain(
    "user.name",
  );
});
```

- [ ] **Step 2 : lancer la spec**

Run : `cd shell && npx playwright test e2e/visible-when-generator.spec.ts`
Expected : `1 passed`. Si « Texte » ne sélectionne pas le widget, vérifier contre
`e2e/expressions.spec.ts`, qui remplit déjà le même champ, et aligner la sélection sur ce fichier.

- [ ] **Step 3 : filet de bundle**

Run :
```bash
cd shell && rm -rf dist dist-export && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```
Expected : `Charge JS/CSS initiale mesurée : X Ko (seuil : 730 Ko)`, code 0.
`VisibleWhenGenerator`/`celClientTools` doivent être dans un chunk à part. Le vérifier :
`grep -l "applyCelDraft" dist/assets/*.js` ne doit pas lister le fichier d'entrée
(`index-*.js` référencé par `dist/.vite/manifest.json` → `"isEntry": true`).
**Seulement si** la commande échoue avec `ÉCHEC : charge initiale Y Ko > seuil 730 Ko` :
1. Écrire `ceil(Y)` dans `shell/.bundle-size-threshold`.
2. Relancer et attendre le code 0.
3. Committer à part avec la justification. Le surcoût vient des 5 clés i18n de `catalog.fr.ts`
   (catalogue chargé statiquement par `i18n/index.ts`), le composant étant déjà lazy.

```bash
git add shell/.bundle-size-threshold
git commit -m "chore(shell): relève le seuil de bundle initial (clés i18n de rev-183)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4 : commit de la spec**

```bash
git add shell/e2e/visible-when-generator.spec.ts
git commit -m "test(shell): e2e génération de condition visiblewhen (rev-183)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### REV-102 — géocodage BAN v1

Flux : le shell envoie `GET /v1/geocode?q=…&limit=5` au cœur, qui proxy vers la Géoplateforme
(BAN) derrière une garde d'egress SSRF dédiée. Celle-ci a sa propre allowlist, qui vaut par défaut
`data.geopf.fr`. Le cœur renvoie `{results: [{label, lon, lat}]}`, puis le contrôle
`map/AddressSearch.tsx` de l'éditeur de carte fait un `flyTo`.

**CSP** : aucun changement de `connect-src`. Le navigateur ne parle qu'au cœur (même origine,
déjà autorisée) ; seul le cœur sort vers la BAN, sous garde d'egress.

**Rate limit** : nouveau groupe `geocode`, 60 requêtes/min par clé d'appelant. Le shell n'envoie
qu'à la soumission, jamais à la frappe. L'API amont tolère 50 req/s/IP.

Hors v1 : widget de recherche, outil MCP (exclusion de parité documentée).

#### Task L5b-102-1 : garde d'egress `app.geocoding.egress` + câblage env

**Files:**
- Create: `core/app/geocoding/__init__.py`
- Create: `core/app/geocoding/egress.py`
- Create: `core/tests/test_geocoding_egress.py`
- Modify: `core/tests/test_egress_dns_pinning.py`
  - `EGRESS_MODULES` (l.11-17)
  - fixture autouse ajoutée après `PUBLIC` (l.18)
- Modify: `docker-compose.yml` (service `core`, après `CORE_EMBEDDING_EGRESS_ALLOWLIST` l.309)
- Modify: `.env.example` (après `CORE_EMBEDDING_EGRESS_ALLOWLIST=` l.153)

**Interfaces:**
- Consumes: `app.net_pin.pin_httpx_request` (anti-TOCTOU DNS, REV-273d).
- Produces:
  - `app.geocoding.egress` : `EgressBlockedError`, `assert_egress_allowed(url) -> str`,
    `build_guarded_client(timeout=10.0) -> httpx.Client`
  - deux variables d'env câblées sur `core` : `CORE_GEOCODING_URL` et
    `CORE_GEOCODING_EGRESS_ALLOWLIST`

- [ ] **Step 1 : tests (échouent)**

Create `core/tests/test_geocoding_egress.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress du géocodage (REV-102) : plages internes bloquées, allowlist
propre (CORE_GEOCODING_EGRESS_ALLOWLIST, défaut data.geopf.fr)."""

import socket

import httpx
import pytest

from app.geocoding.egress import EgressBlockedError, assert_egress_allowed, build_guarded_client

PUBLIC = "93.184.216.34"


def _public(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, 0))],
    )


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://10.0.0.5/x", "http://[::1]/x"])
def test_internal_targets_are_blocked(monkeypatch, url):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_default_allowlist_is_the_geoplateforme_only(monkeypatch):
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    _public(monkeypatch)
    assert assert_egress_allowed("https://data.geopf.fr/geocodage/search") == PUBLIC
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/geocodage/search")


def test_operator_allowlist_overrides_the_default(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "geocodeur.interne.example")
    _public(monkeypatch)
    assert assert_egress_allowed("https://geocodeur.interne.example/search") == PUBLIC
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://data.geopf.fr/geocodage/search")


def test_guarded_client_blocks_before_connecting(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "")
    with build_guarded_client() as client, pytest.raises(EgressBlockedError):
        client.get("http://127.0.0.1:1/x")


def test_guarded_client_does_not_follow_redirects():
    with build_guarded_client() as client:
        assert client.follow_redirects is False
        assert isinstance(client, httpx.Client)
```

Dans `core/tests/test_egress_dns_pinning.py` :

1. Ajouter `"app.geocoding.egress",` à `EGRESS_MODULES`, après `"app.search.egress",`.
2. Juste après `PUBLIC = "93.184.216.34"`, ajouter :

```python
@pytest.fixture(autouse=True)
def _no_default_geocoding_allowlist(monkeypatch):
    # app.geocoding.egress a une allowlist par défaut (data.geopf.fr) ; ces tests
    # exercent la seule garde réseau sur des hôtes arbitraires.
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "")
```

Run (depuis `core/`) : `$CORE_ENV uv run pytest tests/test_geocoding_egress.py tests/test_egress_dns_pinning.py -q --basetemp=/tmp/pytest-l5b-102`
Expected : erreurs de collecte `ModuleNotFoundError: No module named 'app.geocoding'`.

- [ ] **Step 2 : implémenter**

Create `core/app/geocoding/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Géocodage d'adresse (REV-102) : proxy cœur vers la Géoplateforme (BAN)."""
```

Create `core/app/geocoding/egress.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF du géocodage (REV-102). Copie délibérée de
app.search.egress (chaque domaine a sa propre allowlist, cf. sa docstring) :
CORE_GEOCODING_EGRESS_ALLOWLIST, défaut « data.geopf.fr » quand la variable
est absente ; vide = seules les plages internes sont bloquées. Synchrone,
connexion sur l'IP validée (app.net_pin, REV-273d), jamais de suivi de
redirection (l'ancien hôte api-adresse.data.gouv.fr redirige)."""

import ipaddress
import os
import socket
from urllib.parse import urlparse

import httpx

from app.net_pin import pin_httpx_request

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_GEOCODING_EGRESS_ALLOWLIST"
_DEFAULT_ALLOWLIST = "data.geopf.fr"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, _DEFAULT_ALLOWLIST)
    return {h.strip() for h in raw.split(",") if h.strip()}


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global or ip.is_multicast


def assert_egress_allowed(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise EgressBlockedError(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise EgressBlockedError(f"hôte d'egress absent dans l'URL : {url!r}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise EgressBlockedError(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses:
        raise EgressBlockedError(f"hôte non résoluble : {host!r}")
    for ip in addresses:
        if _is_internal(ip):
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r} → {ip}")
    allowlist = _allowlist()
    if allowlist and host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")
    return str(addresses[0])


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        pin_httpx_request(request, assert_egress_allowed(str(request.url)))
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(
        transport=_GuardedTransport(httpx.HTTPTransport()),
        timeout=timeout,
        follow_redirects=False,
    )
```

`docker-compose.yml`, service `core`, après la ligne
`      CORE_EMBEDDING_EGRESS_ALLOWLIST: ${CORE_EMBEDDING_EGRESS_ALLOWLIST:-}` (l.309) :

```yaml
      # Géocodage d'adresse (REV-102) : proxy cœur vers la Géoplateforme (BAN).
      # URL vide = route /v1/geocode en 503 ; allowlist d'egress dédiée.
      CORE_GEOCODING_URL: ${CORE_GEOCODING_URL:-https://data.geopf.fr/geocodage/search}
      CORE_GEOCODING_EGRESS_ALLOWLIST: ${CORE_GEOCODING_EGRESS_ALLOWLIST:-data.geopf.fr}
```

`.env.example`, après la ligne `CORE_EMBEDDING_EGRESS_ALLOWLIST=` (l.153) :

```bash

# ─── Cœur : géocodage d'adresse (REV-102) ──────────────
# Point d'entrée BAN de la Géoplateforme (api-adresse.data.gouv.fr est déprécié,
# sunset 2026-01-31). Vide = géocodage désactivé (GET /v1/geocode répond 503).
CORE_GEOCODING_URL=https://data.geopf.fr/geocodage/search
# Garde d'egress SSRF dédiée — hôtes séparés par des virgules ; vide = seules
# les plages réseau internes/privées sont bloquées.
CORE_GEOCODING_EGRESS_ALLOWLIST=data.geopf.fr
```

`CORE_GEOCODING_URL` n'est encore lue par aucun code. Elle le sera en L5b-102-2. Le test de
déployabilité exige qu'une variable documentée soit câblée (fait ici) ; l'inverse n'est testé
qu'en L5b-102-2.

- [ ] **Step 3 : lancer, attendre le succès**

Run : `$CORE_ENV uv run pytest tests/test_geocoding_egress.py tests/test_egress_dns_pinning.py tests/test_deployability.py -q --basetemp=/tmp/pytest-l5b-102`
Expected : tous les tests passent. `test_deployability.py` contient
`test_every_documented_env_var_is_wired_or_declared_inert` (l.613), qui couvre les deux nouvelles
variables.

- [ ] **Step 4 : qualité + commit**

Run : `uv run ruff check . && uv run ruff format --check . && docker compose config --quiet`
Expected : aucune erreur (`docker compose config` exige un `.env` ; à défaut, `cp .env.example .env`
dans un arbre jetable, à ne pas committer).

```bash
git add core/app/geocoding/__init__.py core/app/geocoding/egress.py core/tests/test_geocoding_egress.py core/tests/test_egress_dns_pinning.py docker-compose.yml .env.example
git commit -m "feat(core): garde d'egress dédiée au géocodage ban (rev-102)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-102-2 : route `GET /v1/geocode` + couches + rate limit + parité + OpenAPI + inventaire

**Files:**
- Create: `core/app/geocoding/provider.py`
- Create: `core/app/geocoding/routes.py`
- Create: `core/tests/test_geocoding_routes.py`
- Modify: `core/app/main.py`
  - import après `from app.copilot import routes as copilot_routes` (l.41)
  - `include_router` après `compliance_routes` (l.399)
- Modify: `core/pyproject.toml` (contrat `layers` : `"app.geocoding"` entre `"app.catalog"` l.366
  et `"app.auth"` l.367)
- Modify: `core/app/ratelimit/limiter.py`
  - regex après `_SHARE_LINK_RE`
  - `_BUDGETS`
  - `route_group()`
- Modify: `core/tests/test_ratelimit.py` (1 test en fin de fichier)
- Modify: `core/tests/test_mcp_copilot_p23.py` (`PARITY`, ~l.153-184)
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (1 ligne)

**Interfaces:**
- Consumes: `build_guarded_client` et `EgressBlockedError` (L5b-102-1) ; `get_current_user`
  (`app.auth.dependency`).
- Produces:
  - `GET /v1/geocode?q=<3..200 car.>&limit=<1..10, défaut 5>` qui renvoie
    `200 {"results": [{"label": str, "lon": float, "lat": float}]}`
  - codes d'erreur : 401 sans jeton ; 422 hors bornes ; 502 « Le service de géocodage est
    indisponible. » ; 503 « Géocodage désactivé sur cette instance. »
  - Consommé par L5b-102-3 (`ItemClient.geocode`).

- [ ] **Step 1 : tests (échouent)**

Create `core/tests/test_geocoding_routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""GET /v1/geocode (REV-102) : proxy BAN authentifié, borné, erreurs RFC 7807."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import init_db, make_engine
from app.geocoding.provider import BanGeocoder, get_geocoder
from app.main import create_app

BAN_ANSWER = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [2.0628, 49.0316]},
            "properties": {"label": "1 Rue de Pontoise 95000 Cergy", "score": 0.9},
        }
    ],
}


@pytest.fixture
def app_and_client(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'geocode.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    app = create_app()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return app, client


def _fake_ban(app, handler):
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    app.dependency_overrides[get_geocoder] = lambda: BanGeocoder(
        "https://data.geopf.fr/geocodage/search",
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(recording)),
    )
    return seen


def test_returns_label_and_coordinates(app_and_client):
    app, client = app_and_client
    seen = _fake_ban(app, lambda r: httpx.Response(200, json=BAN_ANSWER))
    r = client.get("/v1/geocode", params={"q": "1 rue de pontoise cergy", "limit": 3})
    assert r.status_code == 200
    assert r.json() == {
        "results": [{"label": "1 Rue de Pontoise 95000 Cergy", "lon": 2.0628, "lat": 49.0316}]
    }
    assert seen[0].url.params["q"] == "1 rue de pontoise cergy"
    assert seen[0].url.params["limit"] == "3"


def test_requires_authentication(app_and_client):
    app, client = app_and_client
    _fake_ban(app, lambda r: httpx.Response(200, json=BAN_ANSWER))
    del client.headers["Authorization"]
    assert client.get("/v1/geocode", params={"q": "cergy"}).status_code == 401


@pytest.mark.parametrize(
    "params", [{"q": "ab"}, {"q": "x" * 201}, {"q": "cergy", "limit": 0}, {"q": "cergy", "limit": 11}]
)
def test_rejects_out_of_bounds_parameters(app_and_client, params):
    app, client = app_and_client
    _fake_ban(app, lambda r: httpx.Response(200, json=BAN_ANSWER))
    assert client.get("/v1/geocode", params=params).status_code == 422


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, content=b"pas du json"),
        lambda r: httpx.Response(200, json={"features": [{"geometry": None}]}),
    ],
)
def test_upstream_failure_is_a_502_problem(app_and_client, handler):
    app, client = app_and_client
    _fake_ban(app, handler)
    r = client.get("/v1/geocode", params={"q": "cergy"})
    assert r.status_code == 502
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["detail"] == "Le service de géocodage est indisponible."


def test_empty_url_disables_geocoding(app_and_client, monkeypatch):
    _, client = app_and_client
    monkeypatch.setenv("CORE_GEOCODING_URL", "")
    r = client.get("/v1/geocode", params={"q": "cergy"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Géocodage désactivé sur cette instance."


def test_egress_guard_failure_is_a_502(app_and_client, monkeypatch):
    _, client = app_and_client
    monkeypatch.setenv("CORE_GEOCODING_URL", "http://127.0.0.1:1/search")
    r = client.get("/v1/geocode", params={"q": "cergy"})
    assert r.status_code == 502
```

Ajouter à la fin de `core/tests/test_ratelimit.py` :

```python
def test_route_group_covers_geocode_with_its_own_budget():
    from app.ratelimit.limiter import _BUDGETS

    assert route_group("/v1/geocode", "GET", _EXPORT_PATH_RE) == "geocode"
    assert _BUDGETS["geocode"] == 60
```

Run (depuis `core/`) : `$CORE_ENV uv run pytest tests/test_geocoding_routes.py tests/test_ratelimit.py -q --basetemp=/tmp/pytest-l5b-102`
Expected :
- `test_geocoding_routes.py` en erreur de collecte (`ModuleNotFoundError: app.geocoding.provider`).
- Le nouveau test de rate limit échoue (`None == 'geocode'`).

- [ ] **Step 2 : implémenter fournisseur + route**

Create `core/app/geocoding/provider.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Fournisseur de géocodage (REV-102). Une petite interface (Geocoder) et un
seul fournisseur, la BAN servie par la Géoplateforme (data.geopf.fr) :
api-adresse.data.gouv.fr est déprécié (sunset 2026-01-31) et redirige."""

import os
from collections.abc import Callable
from typing import Protocol

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from app.geocoding.egress import build_guarded_client

DEFAULT_GEOCODING_URL = "https://data.geopf.fr/geocodage/search"


class GeocodeResult(BaseModel):
    label: str
    lon: float
    lat: float


class Geocoder(Protocol):
    def search(self, q: str, limit: int) -> list[GeocodeResult]: ...


class BanGeocoder:
    def __init__(
        self, base_url: str, client_factory: Callable[[], httpx.Client] = build_guarded_client
    ):
        self._url = base_url
        self._client_factory = client_factory

    def search(self, q: str, limit: int) -> list[GeocodeResult]:
        with self._client_factory() as client:
            response = client.get(self._url, params={"q": q, "limit": limit})
        response.raise_for_status()
        return [
            GeocodeResult(
                label=f["properties"]["label"],
                lon=f["geometry"]["coordinates"][0],
                lat=f["geometry"]["coordinates"][1],
            )
            for f in response.json()["features"]
        ]


def get_geocoder() -> Geocoder:
    url = os.environ.get("CORE_GEOCODING_URL", DEFAULT_GEOCODING_URL)
    if not url:
        raise HTTPException(status_code=503, detail="Géocodage désactivé sur cette instance.")
    return BanGeocoder(url)
```

Create `core/app/geocoding/routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""GET /v1/geocode (REV-102) : proxy authentifié vers le fournisseur de
géocodage. Le navigateur ne parle qu'au cœur (pas de changement CSP
connect-src) ; groupe de rate limit dédié « geocode »."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependency import get_current_user
from app.geocoding.egress import EgressBlockedError
from app.geocoding.provider import GeocodeResult, Geocoder, get_geocoder

router = APIRouter(prefix="/geocode", tags=["geocoding"], dependencies=[Depends(get_current_user)])


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]


@router.get("", response_model=GeocodeResponse)
def geocode(
    q: str = Query(min_length=3, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
    geocoder: Geocoder = Depends(get_geocoder),
) -> GeocodeResponse:
    try:
        return GeocodeResponse(results=geocoder.search(q, limit))
    # Réponse amont illisible (JSON invalide, feature sans géométrie) = même
    # 502 que l'amont injoignable : jamais de 500 ni de fuite réseau interne.
    except (EgressBlockedError, httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Le service de géocodage est indisponible."
        ) from exc
```

`core/app/main.py` :
- Après `from app.copilot import routes as copilot_routes` (l.41), ajouter
  `from app.geocoding import routes as geocoding_routes`.
- Après `    v1_router.include_router(compliance_routes.router)` (l.399), ajouter
  `    v1_router.include_router(geocoding_routes.router)`.

La route est inconditionnelle. La désactivation passe par `CORE_GEOCODING_URL=""`, ce qui donne un
503.

`core/pyproject.toml`, contrat `layers` : entre `    "app.catalog",` (l.366) et
`    "app.auth",` (l.367), insérer `    "app.geocoding",`. Le module ne dépend que de `app.auth` et
de `app.net_pin`.

`core/app/ratelimit/limiter.py` :
- Après la ligne `_SHARE_LINK_RE = re.compile(r"^/v1/share-links/[^/]+$")`, ajouter :

```python
# REV-102 : GET /v1/geocode déclenche un appel sortant vers la Géoplateforme
# (BAN, 50 req/s/IP côté amont) — budget propre, le shell n'appelle qu'à la
# soumission du formulaire, jamais à la frappe.
_GEOCODE_RE = re.compile(r"^/v1/geocode$")
```

- Dans `_BUDGETS`, après `"share-link": 60,`, ajouter `"geocode": 60,`.
- Dans `route_group()`, avant le `return None` final, ajouter :

```python
    if _GEOCODE_RE.match(path):
        return "geocode"
```

`core/tests/test_mcp_copilot_p23.py`, dans `PARITY`, après la ligne `"extensions": (...)`, ajouter :
`    "geocode": ("excluded", "recherche d'adresse interactive du shell ; outil MCP hors v1 (REV-102)"),`

- [ ] **Step 3 : lancer, attendre le succès (hors parité)**

Run : `$CORE_ENV uv run pytest tests/test_geocoding_routes.py tests/test_ratelimit.py tests/test_deployability.py -q --basetemp=/tmp/pytest-l5b-102`
Expected : tous les tests passent. `test_every_core_env_var_is_wired_to_a_service` (l.540) voit
`CORE_GEOCODING_URL` lue et câblée.

- [ ] **Step 4 : régénérer OpenAPI + types TS**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Expected : les deux fichiers modifiés. Le diff contient `"/v1/geocode"` et les schémas
`GeocodeResponse`/`GeocodeResult` ; `core-schema.d.ts` contient `"/v1/geocode"`.

- [ ] **Step 5 : inventaire + parité + portes**

Ajouter **en fin** de `docs/revue/inventaire-fonctionnalites.jsonl` :

```json
{"id": "carte-recherche-d-adresse-ban-et-centrage-de-la-carte", "domaine": "Carte", "fonctionnalite": "Recherche d'adresse (BAN) et centrage de la carte", "description": "GET /v1/geocode?q= proxifie côté cœur la BAN de la Géoplateforme (data.geopf.fr) derrière une garde d'egress SSRF dédiée (CORE_GEOCODING_EGRESS_ALLOWLIST, connexion sur l'IP validée, sans suivi de redirection), authentifiée, bornée (q 3..200, limit 1..10), groupe de rate limit « geocode » (60/min) ; amont injoignable ou illisible = 502, CORE_GEOCODING_URL vide = 503. L'éditeur de carte propose un champ « Rechercher une adresse » (une requête par soumission) et centre la carte (flyTo) sur le résultat choisi. REV-102.", "preuve": ["core/app/geocoding/routes.py", "core/app/geocoding/provider.py", "core/app/geocoding/egress.py", "shell/src/map/AddressSearch.tsx"], "surfaces": {"rest": ["GET /v1/geocode"], "mcp": [], "shell": [], "autre": []}, "publiques": [], "priorite": "moyenne", "priorite_source": "manuel-l5b", "note_sp42": "Entrée créée par le lot L5b (REV-102, GAP-08) : route ajoutée après la matrice SP-42.", "note_sp42_date": "2026-10-04"}
```

La preuve `shell/src/map/AddressSearch.tsx` n'existe qu'à partir de L5b-102-3. Si `--check`
refuse une preuve inexistante, retirer cette entrée de `preuve` ici et la rajouter au Step 5 de
L5b-102-3.

Run :
- `$CORE_ENV uv run pytest tests/test_feature_inventory.py tests/test_mcp_copilot_p23.py -q --basetemp=/tmp/pytest-l5b-102`
- `PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
- `uv run lint-imports && uv run ruff check . && uv run ruff format --check .`

Expected :
- tous les tests passent ; `test_every_rest_route_group_has_an_explicit_mcp_decision` voit
  `geocode` classé
- `--check` sort en code 0
- `lint-imports` affiche `0 broken`
- ruff ne remonte aucune erreur

- [ ] **Step 6 : commit**

```bash
git add core/app/geocoding/provider.py core/app/geocoding/routes.py core/tests/test_geocoding_routes.py core/app/main.py core/pyproject.toml core/app/ratelimit/limiter.py core/tests/test_ratelimit.py core/tests/test_mcp_copilot_p23.py core/openapi.json shell/src/api/generated/core-schema.d.ts docs/revue/inventaire-fonctionnalites.jsonl
git commit -m "feat(core): route get /v1/geocode, proxy ban sous garde d'egress et rate limit (rev-102)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-102-3 : shell — `ItemClient.geocode` + `AddressSearch` dans l'éditeur de carte

**Files:**
- Modify: `shell/src/api/types.ts`
  - type `GeocodeResult` près de `CopilotSurface` (l.229)
  - méthode `geocode` dans l'interface `ItemClient`, après `getUsageSummary` (~l.492-497)
- Create: `shell/src/api/domains/geocoding.ts`
- Modify: `shell/src/api/itemClient.ts`
  - import après `createUsageMethods` (l.27)
  - spread après `...createUsageMethods(base),` (l.55)
- Modify: `shell/src/staticExport/StaticItemClient.ts` (après `listUsageTasks`, l.457)
- Modify: `shell/src/desktop/DesktopItemClient.ts` (après `listUsageTasks`, l.561)
- Create: `shell/src/map/AddressSearch.tsx`
- Create: `shell/src/map/AddressSearch.test.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
  - lazy import près de `MapView` (l.14)
  - rendu avant `<CameraControls` (l.284)
  - fonction `goToAddress` après `setCamera` (l.137-143)
- Modify: `shell/src/i18n/catalog.fr.ts` (4 clés après `"mapEditor.inspectLabel"`, l.652)

**Interfaces:**
- Consumes: `GET /v1/geocode` (L5b-102-2) ; `MapViewHandle.flyTo(opts, instant?)`
  (`map/MapView.tsx:36-55`).
- Produces:
  - `ItemClient.geocode(q: string, limit?: number): Promise<GeocodeResult[]>`
  - `AddressSearch({onSelect: (center: [lon, lat]) => void})`

- [ ] **Step 1 : tests (échouent)**

Create `shell/src/map/AddressSearch.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";
import { createGeocodingMethods } from "../api/domains/geocoding";
import { expectTokenizedClasses } from "../ui/kit/testUtils";
import { AddressSearch } from "./AddressSearch";

function renderWith(geocode: ReturnType<typeof vi.fn>, onSelect = vi.fn()) {
  const view = render(
    <ItemClientProvider client={{ geocode } as unknown as ItemClient}>
      <AddressSearch onSelect={onSelect} />
    </ItemClientProvider>,
  );
  return { onSelect, container: view.container };
}

describe("AddressSearch", () => {
  it("searches on submit only and flies to the chosen result", async () => {
    const geocode = vi
      .fn()
      .mockResolvedValue([{ label: "1 Rue de Pontoise 95000 Cergy", lon: 2.0628, lat: 49.0316 }]);
    const { onSelect } = renderWith(geocode);
    await userEvent.type(screen.getByLabelText("Rechercher une adresse"), "1 rue de pontoise");
    expect(geocode).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Localiser" }));
    expect(geocode).toHaveBeenCalledWith("1 rue de pontoise");
    await userEvent.click(await screen.findByRole("button", { name: "1 Rue de Pontoise 95000 Cergy" }));
    expect(onSelect).toHaveBeenCalledWith([2.0628, 49.0316]);
  });

  it("disables the search below 3 characters", async () => {
    renderWith(vi.fn());
    await userEvent.type(screen.getByLabelText("Rechercher une adresse"), "ab");
    expect(screen.getByRole("button", { name: "Localiser" })).toBeDisabled();
  });

  it("says when nothing matches and when the service fails", async () => {
    const geocode = vi.fn().mockResolvedValueOnce([]).mockRejectedValueOnce(new Error("502"));
    const { container } = renderWith(geocode);
    await userEvent.type(screen.getByLabelText("Rechercher une adresse"), "nulle part");
    await userEvent.click(screen.getByRole("button", { name: "Localiser" }));
    expect(await screen.findByText("Aucune adresse trouvée.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Localiser" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Recherche d'adresse indisponible.",
    );
    expectTokenizedClasses(container);
  });
});

describe("createGeocodingMethods", () => {
  it("calls GET /geocode with an encoded query and unwraps results", async () => {
    const request = vi.fn().mockResolvedValue({ results: [{ label: "A", lon: 1, lat: 2 }] });
    const methods = createGeocodingMethods({ request } as never);
    await expect(methods.geocode("1 rue & co")).resolves.toEqual([{ label: "A", lon: 1, lat: 2 }]);
    expect(request).toHaveBeenCalledWith("GET", "/geocode?q=1+rue+%26+co&limit=5");
  });
});
```

Run : `cd shell && npx vitest run src/map/AddressSearch.test.tsx`
Expected : échec à l'import (`Failed to resolve import "./AddressSearch"` ou
`"../api/domains/geocoding"`).

- [ ] **Step 2 : implémenter le client**

`shell/src/api/types.ts`, juste après la ligne `export type CopilotSurface = …;` (l.229) :

```ts
// REV-102 : un résultat de GET /v1/geocode.
export type GeocodeResult = { label: string; lon: number; lat: number };
```

Dans l'interface `ItemClient`, juste après la déclaration de `getUsageSummary(...)`, terminée par
`): Promise<UsageSummary>;`, ajouter :

```ts
  // REV-102 : recherche d'adresse (BAN via le cœur).
  geocode(q: string, limit?: number): Promise<GeocodeResult[]>;
```

Create `shell/src/api/domains/geocoding.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import type { GeocodeResult, ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type GeocodingMethods = Pick<ItemClient, "geocode">;

export function createGeocodingMethods(base: Pick<ItemClientBase, "request">): GeocodingMethods {
  return {
    async geocode(q: string, limit = 5): Promise<GeocodeResult[]> {
      const query = new URLSearchParams({ q, limit: String(limit) });
      const body = await base.request<{ results: GeocodeResult[] }>(
        "GET",
        `/geocode?${query.toString()}`,
      );
      return body.results;
    },
  };
}
```

`shell/src/api/itemClient.ts` : après `import { createUsageMethods } from "./domains/usage";`,
ajouter `import { createGeocodingMethods } from "./domains/geocoding";`. Après
`    ...createUsageMethods(base),`, ajouter `    ...createGeocodingMethods(base),`.

`shell/src/staticExport/StaticItemClient.ts` et `shell/src/desktop/DesktopItemClient.ts` : juste
avant `    async listUsageTasks(..._args: unknown[]) {`, ajouter dans chacun :

```ts
    async geocode(..._args: unknown[]) {
      return unsupported();
    },
```

- [ ] **Step 3 : implémenter le composant + montage**

Create `shell/src/map/AddressSearch.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
// REV-102 : recherche d'adresse (BAN via GET /v1/geocode). Une requête par
// soumission, jamais à la frappe (budget de rate limit « geocode »). Chargé
// par lazy() depuis MapEditorPage.
import { useState, type FormEvent } from "react";
import { useItemClient } from "../api/ItemClientProvider";
import type { GeocodeResult } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { t } from "../i18n";

export function AddressSearch({ onSelect }: { onSelect: (center: [number, number]) => void }) {
  const client = useItemClient();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[] | null>(null);
  const [failed, setFailed] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setFailed(false);
    try {
      setResults(await client.geocode(query.trim()));
    } catch {
      setResults(null);
      setFailed(true);
    }
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={(e) => void submit(e)}>
      <div className="flex gap-2">
        <Input
          aria-label={t("addressSearch.inputAria")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" size="sm" variant="outline" disabled={query.trim().length < 3}>
          {t("addressSearch.submit")}
        </Button>
      </div>
      {failed && (
        <p role="alert" className="text-xs text-danger">
          {t("addressSearch.failed")}
        </p>
      )}
      {results?.length === 0 && <p className="text-xs text-ink-2">{t("addressSearch.empty")}</p>}
      {results && results.length > 0 && (
        <ul className="flex flex-col gap-1">
          {results.map((r) => (
            <li key={`${r.lon},${r.lat},${r.label}`}>
              <button
                type="button"
                className="text-left text-xs text-ink underline"
                onClick={() => onSelect([r.lon, r.lat])}
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
```

`shell/src/pages/MapEditorPage.tsx` :
1. Juste après la ligne `const MapView = lazy(...)` (l.14), ajouter :

```tsx
// REV-102 : lazy, hors charge initiale (marge de bundle).
const AddressSearch = lazy(() =>
  import("../map/AddressSearch").then((m) => ({ default: m.AddressSearch })),
);
```

2. Après la fonction `setCamera` (qui finit l.143), ajouter :

```tsx
  function goToAddress(center: [number, number]) {
    updateDraft((d) => (d ? { ...d, view: { ...d.view, center, zoom: 16 } } : d));
    mapViewRef.current?.flyTo({ center, zoom: 16 });
  }
```

3. Dans le panneau `inspect`, juste avant `<CameraControls` (l.284), insérer :

```tsx
              <Suspense fallback={null}>
                <AddressSearch onSelect={goToAddress} />
              </Suspense>
```

`shell/src/i18n/catalog.fr.ts`, après `"mapEditor.inspectLabel": "Inspecter",` (l.652) :

```ts
  "addressSearch.inputAria": "Rechercher une adresse",
  "addressSearch.submit": "Localiser",
  "addressSearch.empty": "Aucune adresse trouvée.",
  "addressSearch.failed": "Recherche d'adresse indisponible.",
```

- [ ] **Step 4 : lancer, attendre le succès + non-régression**

Run :
- `cd shell && npx vitest run src/map/AddressSearch.test.tsx src/pages/MapEditorPage.test.tsx src/staticExport src/desktop`
- `npx tsc --noEmit && npm run lint && npm run format:check`

Expected : tous les tests passent ; `tsc`, `lint` (i18n, aria-panel, couleurs) et `format:check`
passent sans erreur. Si `src/pages/MapEditorPage.test.tsx` n'existe pas sous ce nom, lancer
`npx vitest run src/pages/MapEditor` ; vitest filtre par motif.

- [ ] **Step 5 : commit**

```bash
git add shell/src/api/types.ts shell/src/api/domains/geocoding.ts shell/src/api/itemClient.ts shell/src/staticExport/StaticItemClient.ts shell/src/desktop/DesktopItemClient.ts shell/src/map/AddressSearch.tsx shell/src/map/AddressSearch.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): recherche d'adresse et centrage dans l'éditeur de carte (rev-102)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-102-4 : E2E recherche d'adresse + filet de bundle

**Files:**
- Create: `shell/e2e/address-search.spec.ts`
- Modify (conditionnel): `shell/.bundle-size-threshold`

**Interfaces:**
- Consumes:
  - L5b-102-3
  - mocks `mockCore` : création de carte → `/maps/77` ; le `PUT configs/by-item/77` stocke `body`,
    et `body.map.view` porte la vue (`e2e/mocks.ts:636-650`)
- Produces: une spec E2E.

- [ ] **Step 1 : écrire la spec**

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("REV-102 : rechercher une adresse centre la carte et la vue est enregistrée", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/geocode*", async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q");
    expect(q).toBe("1 rue de pontoise cergy");
    await route.fulfill({
      json: { results: [{ label: "1 Rue de Pontoise 95000 Cergy", lon: 2.0628, lat: 49.0316 }] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Ma carte");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);

  await page.getByLabel("Rechercher une adresse").fill("1 rue de pontoise cergy");
  await page.getByRole("button", { name: "Localiser" }).click();
  await page.getByRole("button", { name: "1 Rue de Pontoise 95000 Cergy" }).click();

  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().includes("/configs/by-item/77"),
  );
  await page.getByRole("button", { name: "Enregistrer" }).click();
  const body = (await saved).postDataJSON() as { map: { view: { center: number[]; zoom: number } } };
  expect(body.map.view.center[0]).toBeCloseTo(2.0628, 3);
  expect(body.map.view.center[1]).toBeCloseTo(49.0316, 3);
});
```

- [ ] **Step 2 : lancer la spec**

Run : `cd shell && npx playwright test e2e/address-search.spec.ts`
Expected : `1 passed`. Si le panneau « Inspecter » est replié à la largeur du test, l'ouvrir d'abord
avec le même geste que `e2e/map-editor.spec.ts` pour `CameraControls` (2e test du fichier).

- [ ] **Step 3 : filet de bundle**

Run :
```bash
cd shell && rm -rf dist dist-export && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```
Expected : `Charge JS/CSS initiale mesurée : X Ko (seuil : 730 Ko)`, code 0.
`grep -l "addressSearch\|Localiser" dist/assets/*.js` doit lister le chunk du catalogue i18n
(entrée), mais pas de chunk contenant le JSX d'`AddressSearch` dans l'entrée.
**Seulement si** la commande échoue avec `ÉCHEC : charge initiale Y Ko > seuil 730 Ko` :
1. Écrire `ceil(Y)` dans `shell/.bundle-size-threshold`.
2. Relancer et attendre le code 0.
3. Committer à part avec la justification : 4 clés i18n + la méthode `geocode` du client composé,
   tous deux dans l'entrée par construction ; le composant est lazy.

```bash
git add shell/.bundle-size-threshold
git commit -m "chore(shell): relève le seuil de bundle initial (client geocode et clés i18n, rev-102)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4 : commit**

```bash
git add shell/e2e/address-search.spec.ts
git commit -m "test(shell): e2e recherche d'adresse et centrage de carte (rev-102)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### REV-104 — animation temporelle v1

**Vérification préalable faite (avant plan)** : le widget carte **applique déjà `timeRange`** à sa
couche de données principale. Il n'y a donc pas de tâche de câblage ; L5b-104-3 ajoute un test de
caractérisation. La chaîne de code :

1. `builder/DataContext.tsx:87-89` (`mergedQueryFor`) fusionne `derivePatch(...)`
   (`lib/analyticsPatch.ts:22-25` : `${timeField}__gte/__lte`) dans la requête.
2. `DataContext.tsx:127` expose `url: client.featuresUrl(merged)`.
3. `api/domains/datasets.ts:89-105` (`buildFeaturesUrl`) sérialise la requête dans l'URL.
4. `builder/widgets/mapWidget.tsx` construit la couche depuis `ctx.data?.url`.
5. `map/MapView.tsx:464-467` : `layersKey` inclut l'URL, donc la source GeoJSON est retirée puis
   rajoutée.

Limites assumées en v1 :
- effet seulement pour une source liée à un dataset dont `timeField` est renseigné ;
- couches additionnelles `props.layers` non filtrées ;
- à chaque pas, toutes les couches sont réappliquées (scintillement possible) ;
- comme `dateRangeFilter`, rien ne se passe sans `interactions: "auto"` (`AnalyticsContext.tsx:95-101`).

Hors v1 : interpolation, export vidéo, pas irréguliers.

#### Task L5b-104-1 : cœur — validation à l'écriture des props `timePlayer`

**Files:**
- Modify: `core/app/configs/document_validation.py`
  - import `date`
  - nouvelle fonction avant `_item_errors` (l.91)
  - appel dans `_item_errors`
- Modify: `core/tests/test_p21_api_contracts.py` (1 test après `test_invalid_app_rejected`, ~l.104)

**Interfaces:**
- Consumes: `LayoutItem.props: dict` (`core/app/configs/schemas.py:56`, non typé).
- Produces: un 422 à l'écriture (POST/PUT config, `save_app_config` MCP) si un widget `timePlayer`
  porte une des valeurs suivantes :
  - `from`/`to` non-ISO, ou `from > to` ;
  - `stepDays`/`windowDays` hors entier 1..3660 ;
  - `intervalMs` hors entier 500..10000.

  Ces bornes sont reprises telles quelles par le PropsPanel shell de L5b-104-2. Elles ne valent
  qu'à l'écriture : une config relue n'est jamais refusée (principe P21).

- [ ] **Step 1 : test (échoue)**

Ajouter après `test_invalid_app_rejected` dans `core/tests/test_p21_api_contracts.py` :

```python
def test_time_player_props_are_validated_on_write(client):
    def app(props):
        item = {"id": "tp", "widget": "timePlayer", "x": 0, "y": 0, "w": 6, "h": 1, "props": props}
        return {"kind": "app", "layout": {"type": "grid", "items": [item]}}

    ok = {"from": "2026-06-01", "to": "2026-06-30", "stepDays": 1, "windowDays": 7, "intervalMs": 1000}
    assert _post(client, app(ok)).status_code == 201
    assert _post(client, app({})).status_code == 201  # non configuré : accepté, le widget le dit
    for bad in (
        {**ok, "from": "01/06/2026"},
        {**ok, "from": "2026-07-01"},  # from > to
        {**ok, "stepDays": 0},
        {**ok, "windowDays": 3661},
        {**ok, "intervalMs": 100},
        {**ok, "stepDays": 1.5},
        {**ok, "stepDays": True},
    ):
        r = _post(client, app(bad))
        assert r.status_code == 422, bad
        assert "timePlayer" in r.json()["detail"] or "tp" in r.json()["detail"], bad
```

Run (depuis `core/`) : `$CORE_ENV uv run pytest tests/test_p21_api_contracts.py -q -k time_player --basetemp=/tmp/pytest-l5b-104`
Expected : `1 failed` (`assert 201 == 422`).

- [ ] **Step 2 : implémenter**

Dans `core/app/configs/document_validation.py` :
1. Après `import re`, ajouter `from datetime import date`.
2. Juste avant `def _item_errors(` (l.91), ajouter :

```python
# REV-104 : bornes des props du widget timePlayer (lecteur temporel). Les
# props de widget sont un dict non typé (LayoutItem.props) : bornes à
# l'écriture seulement, comme le reste de ce module.
_TIME_PLAYER_INT_BOUNDS = {
    "stepDays": (1, 3660),
    "windowDays": (1, 3660),
    "intervalMs": (500, 10000),
}


def _time_player_errors(props: dict, name: str) -> list[str]:
    errs: list[str] = []
    dates: dict[str, date] = {}
    for key in ("from", "to"):
        value = props.get(key)
        if value in (None, ""):
            continue
        try:
            dates[key] = date.fromisoformat(value)
        except (TypeError, ValueError):
            errs.append(f"widget '{name}' {key}: must be an ISO date (YYYY-MM-DD)")
    if len(dates) == 2 and dates["from"] > dates["to"]:
        errs.append(f"widget '{name}': from must be <= to")
    for key, (lo, hi) in _TIME_PLAYER_INT_BOUNDS.items():
        value = props.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            errs.append(f"widget '{name}' {key}: must be an integer within {lo}..{hi}")
    return errs
```

3. Dans `_item_errors`, juste avant `    return errs`, ajouter :

```python
    if item.widget == "timePlayer":
        errs += _time_player_errors(item.props, name)
```

`name` vaut `item.id or item.widget` (l.93), donc le message contient `tp` ou `timePlayer`.

- [ ] **Step 3 : lancer, attendre le succès**

Run : `$CORE_ENV uv run pytest tests/test_p21_api_contracts.py tests/test_schemas.py -q --basetemp=/tmp/pytest-l5b-104`
Expected : tous les tests passent.

- [ ] **Step 4 : qualité + commit**

Run : `uv run ruff check . && uv run ruff format --check .`
Expected : aucune erreur.

```bash
git add core/app/configs/document_validation.py core/tests/test_p21_api_contracts.py
git commit -m "feat(core): bornes des props du lecteur temporel validées à l'écriture (rev-104)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-104-2 : shell — widget `timePlayer` (play/pause, vitesse, pas fixe) + allowlist d'export

**Files:**
- Create: `shell/src/builder/widgets/timePlayer.tsx`
- Create: `shell/src/builder/widgets/timePlayer.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
  - import après `registerVariableInputWidget` (l.23)
  - appel après `registerVariableInputWidget();` (l.214)
- Modify: `shell/src/i18n/catalog.fr.ts` (clés après `"widgetDateRangeFilter.periodDefault"`, l.1067)
- Modify: `core/app/appexport/guard.py` (`_SUPPORTED_WIDGET_TYPES`, après `"variableInput",`, l.58)

**Interfaces:**
- Consumes:
  - `useSetTimeRange()` (`builder/AnalyticsContext.tsx:160`)
  - `registerWidget` (`builder/registry.ts`)
  - les bornes de L5b-104-1
- Produces:
  - le widget `type: "timePlayer"` avec les props `{from?, to?, stepDays, windowDays, intervalMs}`
  - la fonction pure exportée `windowAt(from, to, stepDays, windowDays, index)`
  - l'entrée `"timePlayer"` dans l'allowlist d'export d'app. La parité est testée par
    `core/tests/test_appexport_guard.py:315`.

  Rendu : le widget est un contrôle global (pas d'`events`/`actions`), comme `dateRangeFilter`. Le
  « composant » est enregistré dans le registre des widgets, comme tous les widgets intégrés. Son
  coût initial est traité en L5b-104-3, Step 4.

- [ ] **Step 1 : tests (échouent)**

Create `shell/src/builder/widgets/timePlayer.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { registerTimePlayerWidget, windowAt } from "./timePlayer";
import { expectTokenizedClasses } from "../../ui/kit/testUtils";

beforeEach(() => {
  _resetRegistry();
  registerTimePlayerWidget();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

function TimeRangeProbe() {
  const ctx = useAnalyticsContext();
  return <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>;
}

const PROPS = { from: "2026-06-01", to: "2026-06-03", stepDays: 1, windowDays: 1, intervalMs: 1000 };

function renderPlayer(props: Record<string, unknown> = PROPS) {
  const TimePlayer = getWidget("timePlayer")!.Component;
  return render(
    <AnalyticsContextProvider interactions="auto">
      <TimePlayer props={props} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
}

test("windowAt : fenêtre glissante UTC, bornée par la fin, null au-delà", () => {
  expect(windowAt("2026-06-01", "2026-06-10", 1, 7, 0)).toEqual({
    from: "2026-06-01",
    to: "2026-06-07",
  });
  expect(windowAt("2026-06-01", "2026-06-10", 1, 7, 5)).toEqual({
    from: "2026-06-06",
    to: "2026-06-10",
  });
  expect(windowAt("2026-06-01", "2026-06-10", 3, 1, 3)).toEqual({
    from: "2026-06-10",
    to: "2026-06-10",
  });
  expect(windowAt("2026-06-01", "2026-06-10", 1, 7, 10)).toBeNull();
  expect(windowAt("pas une date", "2026-06-10", 1, 7, 0)).toBeNull();
});

test("Lecture pousse la 1re fenêtre tout de suite, avance à chaque intervalle et s'arrête à la fin", () => {
  renderPlayer();
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  expect(screen.getByText("timeRange:2026-06-01..2026-06-01")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText("timeRange:2026-06-02..2026-06-02")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText("timeRange:2026-06-03..2026-06-03")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1000));
  // Fin dépassée : arrêt, dernière fenêtre conservée, prêt à rejouer.
  expect(screen.getByRole("button", { name: "Lecture" })).toBeInTheDocument();
  expect(screen.getByText("timeRange:2026-06-03..2026-06-03")).toBeInTheDocument();
  expect(vi.getTimerCount()).toBe(0);
});

test("Pause fige la fenêtre ; la vitesse ×2 divise l'intervalle", () => {
  renderPlayer();
  fireEvent.change(screen.getByLabelText("Vitesse"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  act(() => vi.advanceTimersByTime(500));
  expect(screen.getByText("timeRange:2026-06-02..2026-06-02")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  act(() => vi.advanceTimersByTime(5000));
  expect(screen.getByText("timeRange:2026-06-02..2026-06-02")).toBeInTheDocument();
});

test("le minuteur est nettoyé au démontage", () => {
  const { unmount } = renderPlayer();
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  expect(vi.getTimerCount()).toBe(1);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

test("sans début ni fin : message de configuration, pas de bouton Lecture", () => {
  renderPlayer({ stepDays: 1, windowDays: 7, intervalMs: 1000 });
  expect(
    screen.getByText("Lecteur temporel non configuré : renseignez le début et la fin."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Lecture" })).not.toBeInTheDocument();
});

test("PropsPanel : champs bornés, sans couleur brute, vide = prop retirée", () => {
  const Panel = getWidget("timePlayer")!.PropsPanel;
  const onChange = vi.fn();
  const { container } = render(
    <Panel props={{ ...PROPS }} dataSources={[]} onChange={onChange} />,
  );
  expect(screen.getByLabelText("Pas (jours)")).toHaveAttribute("min", "1");
  expect(screen.getByLabelText("Intervalle (ms)")).toHaveAttribute("min", "500");
  fireEvent.change(screen.getByLabelText("Fenêtre (jours)"), { target: { value: "" } });
  expect(onChange.mock.calls.at(-1)![0].windowDays).toBeUndefined();
  fireEvent.change(screen.getByLabelText("Début de l'animation"), {
    target: { value: "2026-05-01" },
  });
  expect(onChange.mock.calls.at(-1)![0].from).toBe("2026-05-01");
  expectTokenizedClasses(container);
});
```

Run : `cd shell && npx vitest run src/builder/widgets/timePlayer.test.tsx`
Expected : échec à l'import (`Failed to resolve import "./timePlayer"`).

- [ ] **Step 2 : implémenter**

Create `shell/src/builder/widgets/timePlayer.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
// REV-104 : lecteur temporel. Fait avancer une fenêtre [début, fin] à pas
// fixe sur la plage configurée et la pousse dans le contexte analytique
// global (useSetTimeRange), comme dateRangeFilter. Sans effet si
// config.interactions !== "auto". Bornes des props validées à l'écriture
// côté cœur (document_validation._time_player_errors).
import { useEffect, useState } from "react";
import { registerWidget } from "../registry";
import { useSetTimeRange } from "../AnalyticsContext";
import { t } from "../../i18n";

const DAY_MS = 86_400_000;
const SPEEDS = [0.5, 1, 2];
const NUMBER_FIELDS = [
  { key: "stepDays", label: "widgetTimePlayer.stepDays", min: 1, max: 3660 },
  { key: "windowDays", label: "widgetTimePlayer.windowDays", min: 1, max: 3660 },
  { key: "intervalMs", label: "widgetTimePlayer.intervalMs", min: 500, max: 10000 },
] as const;
const DATE_FIELDS = [
  { key: "from", label: "widgetTimePlayer.from" },
  { key: "to", label: "widgetTimePlayer.to" },
] as const;

/** Fenêtre n° `index` (dates ISO AAAA-MM-JJ, UTC), ou null une fois `to` dépassé. */
export function windowAt(
  from: string,
  to: string,
  stepDays: number,
  windowDays: number,
  index: number,
): { from: string; to: string } | null {
  const start = Date.parse(from) + index * stepDays * DAY_MS;
  const last = Date.parse(to);
  if (Number.isNaN(start) || Number.isNaN(last) || start > last) return null;
  const end = Math.min(start + (windowDays - 1) * DAY_MS, last);
  const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
  return { from: iso(start), to: iso(end) };
}

export function registerTimePlayerWidget(): void {
  registerWidget({
    type: "timePlayer",
    label: t("widgetTimePlayer.paletteLabel"),
    defaultProps: { stepDays: 1, windowDays: 7, intervalMs: 1000 },
    defaultSize: { w: 6, h: 1 },
    configSchema: [
      { name: "stepDays", type: "number", label: t("widgetTimePlayer.stepDays"), default: 1 },
      { name: "windowDays", type: "number", label: t("widgetTimePlayer.windowDays"), default: 7 },
      { name: "intervalMs", type: "number", label: t("widgetTimePlayer.intervalMs"), default: 1000 },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        {DATE_FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">
            {t(f.label)}
            <input
              type="date"
              aria-label={t(f.label)}
              className="h-9 rounded-md border border-rule px-2"
              value={String(props[f.key] ?? "")}
              onChange={(e) => onChange({ ...props, [f.key]: e.target.value || undefined })}
            />
          </label>
        ))}
        {NUMBER_FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">
            {t(f.label)}
            <input
              type="number"
              aria-label={t(f.label)}
              min={f.min}
              max={f.max}
              step={1}
              className="h-9 rounded-md border border-rule px-2"
              value={props[f.key] === undefined ? "" : String(props[f.key])}
              onChange={(e) =>
                onChange({
                  ...props,
                  [f.key]: e.target.value === "" ? undefined : Number(e.target.value),
                })
              }
            />
          </label>
        ))}
      </div>
    ),
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      const [index, setIndex] = useState(0);
      const [playing, setPlaying] = useState(false);
      const [speed, setSpeed] = useState(1);
      const from = String(props.from ?? "");
      const to = String(props.to ?? "");
      const stepDays = Number(props.stepDays) || 1;
      const windowDays = Number(props.windowDays) || 7;
      const intervalMs = Number(props.intervalMs) || 1000;

      // Un pas par intervalle ; nettoyé à la pause, au changement de vitesse
      // et au démontage.
      useEffect(() => {
        if (!playing) return;
        const timer = setInterval(() => setIndex((i) => i + 1), intervalMs / speed);
        return () => clearInterval(timer);
      }, [playing, intervalMs, speed]);

      // Pousse la fenêtre courante ; au-delà de la fin : arrêt et retour au début.
      useEffect(() => {
        if (!playing) return;
        const current = windowAt(from, to, stepDays, windowDays, index);
        if (current) {
          setTimeRange(current);
        } else {
          setPlaying(false);
          setIndex(0);
        }
      }, [playing, index, from, to, stepDays, windowDays, setTimeRange]);

      function play() {
        setPlaying(true);
      }
      function pause() {
        setPlaying(false);
      }

      if (!from || !to) {
        return (
          <p className="text-xs text-[var(--gs-color-text)]">
            {t("widgetTimePlayer.notConfigured")}
          </p>
        );
      }
      const shown = windowAt(from, to, stepDays, windowDays, index);
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--gs-color-text)]">
          <button
            type="button"
            className="h-9 rounded-md border border-[var(--gs-color-border)] px-3"
            onClick={() => (playing ? pause() : play())}
          >
            {playing ? t("widgetTimePlayer.pause") : t("widgetTimePlayer.play")}
          </button>
          <select
            aria-label={t("widgetTimePlayer.speed")}
            className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
            value={String(speed)}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={String(s)}>
                {t("widgetTimePlayer.speedOption", { speed: s })}
              </option>
            ))}
          </select>
          {shown && <span>{t("analyticsContext.periodLabel", shown)}</span>}
        </div>
      );
    },
  });
}
```

Si `t()` refuse un objet `{from, to}` typé comme paramètres (signature à vérifier dans
`shell/src/i18n/index.ts`), passer `{ from: shown.from, to: shown.to }`.

Le `onClick` du bouton passe par `play()`/`pause()`. Ce n'est pas un `setX(true)` inline, donc
`lint:aria-panel` ne le prend pas pour un déclencheur de panneau.

`shell/src/builder/widgets/index.tsx` :
- Après `import { registerVariableInputWidget } from "./variableInput";` (l.23), ajouter
  `import { registerTimePlayerWidget } from "./timePlayer";`.
- Après `  registerVariableInputWidget();` (l.214), ajouter `  registerTimePlayerWidget();`.

`shell/src/i18n/catalog.fr.ts`, après `"widgetDateRangeFilter.periodDefault": "Période",` (l.1067) :

```ts
  "widgetTimePlayer.paletteLabel": "Lecteur temporel",
  "widgetTimePlayer.from": "Début de l'animation",
  "widgetTimePlayer.to": "Fin de l'animation",
  "widgetTimePlayer.stepDays": "Pas (jours)",
  "widgetTimePlayer.windowDays": "Fenêtre (jours)",
  "widgetTimePlayer.intervalMs": "Intervalle (ms)",
  "widgetTimePlayer.play": "Lecture",
  "widgetTimePlayer.pause": "Pause",
  "widgetTimePlayer.speed": "Vitesse",
  "widgetTimePlayer.speedOption": "×{speed}",
  "widgetTimePlayer.notConfigured": "Lecteur temporel non configuré : renseignez le début et la fin.",
```

`core/app/appexport/guard.py`, dans `_SUPPORTED_WIDGET_TYPES`, après `        "variableInput",`,
ajouter `        "timePlayer",`.

- [ ] **Step 3 : lancer, attendre le succès + parité d'export**

Run :
- `cd shell && npx vitest run src/builder/widgets/timePlayer.test.tsx src/builder/widgets/ src/builder/PropsPanel.test.tsx`
- `cd ../core && $CORE_ENV uv run pytest tests/test_appexport_guard.py -q --basetemp=/tmp/pytest-l5b-104`

Expected : tous les tests passent. `test_allowlist_matches_shell_builtin_widget_registry` relit
`registerWidget({ type: "timePlayer"` et le retrouve dans l'allowlist.

- [ ] **Step 4 : qualité + commit**

Run : `cd shell && npx tsc --noEmit && npm run lint && npm run format:check`
Expected : aucune erreur.

```bash
git add shell/src/builder/widgets/timePlayer.tsx shell/src/builder/widgets/timePlayer.test.tsx shell/src/builder/widgets/index.tsx shell/src/i18n/catalog.fr.ts core/app/appexport/guard.py
git commit -m "feat(shell): widget lecteur temporel qui anime la plage du contexte analytique (rev-104)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

#### Task L5b-104-3 : caractérisation carte (timeRange → URL de couche), E2E, OpenAPI vide, inventaire, bundle

**Files:**
- Modify: `shell/src/builder/DataContext.test.tsx` (1 test en fin de fichier)
- Modify: `shell/e2e/analytics-context.spec.ts` (1 test en fin de fichier ; réutilise `createApp`,
  `addFeaturesSource`, `promoteLastSource`, `mockCore`, `mockCollection`, `mockItemDetail`)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (1 ligne)
- Modify (conditionnel): `shell/.bundle-size-threshold`

**Interfaces:**
- Consumes: L5b-104-1 et L5b-104-2 ; la chaîne `DataContext` → `featuresUrl` décrite en tête de
  sous-section.
- Produces:
  - un test qui fige la propriété « le timeRange atteint l'URL de couche du widget carte »
  - une spec E2E du lecteur temporel

- [ ] **Step 1 : test de caractérisation + falsification**

Ajouter à la fin de `shell/src/builder/DataContext.test.tsx` :

```tsx
test("REV-104 : la plage temporelle du contexte atteint l'URL de couche (featuresUrl) d'une source liée à un dataset", async () => {
  const featuresUrl = vi.fn().mockReturnValue("https://fs/parcs/items.json");
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([]),
    featuresUrl,
    getDatasetConfig: vi.fn().mockResolvedValue({
      source: "collection",
      collectionId: "parcs",
      columns: {},
      timeField: "date_releve",
      reactsToExtent: false,
    }),
    getCollectionSchema: vi
      .fn()
      .mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [
    {
      id: "ds1",
      type: "features",
      service: "featureserv",
      layer: "parcs",
      datasetId: "dataset-1",
      query: {},
    },
  ];

  function SetRange() {
    const setTimeRange = useSetTimeRange();
    return (
      <button type="button" onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-01-31" })}>
        régler
      </button>
    );
  }
  function Probe() {
    useDataStates();
    return <p>rendered</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <DataProvider sources={src}>
            <SetRange />
            <Probe />
          </DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await screen.findByText("rendered");
  await waitFor(() => expect(client.getDatasetConfig).toHaveBeenCalledWith("dataset-1"));
  await userEvent.click(screen.getByRole("button", { name: "régler" }));
  await waitFor(() =>
    expect(featuresUrl).toHaveBeenLastCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({
          date_releve__gte: "2026-01-01",
          date_releve__lte: "2026-01-31",
        }),
      }),
    ),
  );
});
```

Modifier l'import l.9 en
`import { AnalyticsContextProvider, useSetTimeRange } from "./AnalyticsContext";`.

Run : `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected : tout passe. C'est un test de **caractérisation** : le comportement existe déjà.

**Falsification (piège n°10)** :
1. Dans `shell/src/builder/DataContext.tsx:89`, remplacer temporairement
   `query: { ...s.query, ...contextPatch, ...(filters[s.id] ?? {}) }` par
   `query: { ...s.query, ...(filters[s.id] ?? {}) }`.
2. Relancer la commande : le nouveau test **doit échouer**.
3. Restaurer la ligne (`git checkout shell/src/builder/DataContext.tsx`), relancer et attendre le
   succès.

- [ ] **Step 2 : E2E du lecteur temporel**

Ajouter à la fin de `shell/e2e/analytics-context.spec.ts`. Les mocks sont repris du scénario 3
(l.309-371). L'intervalle de 3000 ms laisse le temps d'asserter la 1re fenêtre avant le 2e pas,
sans horloge simulée.

```ts
// -------------------------------------------------------------------------
// REV-104 — lecteur temporel : Lecture pousse une fenêtre glissante dans le
// contexte global ; la table liée au dataset timeField refetch à chaque pas.
// -------------------------------------------------------------------------
test("a time player steps a sliding window through a timeField-bound dataset", async ({
  page,
}) => {
  await mockCore(page);
  let savedDataset: Record<string, unknown> = {};
  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          mockCollection({
            id: "events",
            title: "Événements",
            tableName: "events",
            isPublic: true,
            geometryType: null,
            srid: null,
            permissions: { read: true, write: true, delete: false, share: false },
            featureCount: 2,
          }),
        ],
      },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "events",
        pk: "id",
        geometry: null,
        fields: [
          { name: "nom", type: "string" },
          { name: "date", type: "string" },
        ],
      },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("date__gte");
    const lte = url.searchParams.get("date__lte");
    const all = [
      { id: 1, properties: { nom: "Ancien", date: "2020-05-01" } },
      { id: 2, properties: { nom: "Récent", date: "2026-06-01" } },
    ];
    const features =
      gte && lte ? all.filter((f) => f.properties.date >= gte && f.properties.date <= lte) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({
        json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset },
      });
      return;
    }
    await route.fulfill({
      json: {
        id: "cfg-dataset",
        itemId: "dataset-1",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset },
        },
      },
    });
  });
  await mockItemDetail(page, "dataset-1", {
    title: "Événements partagés",
    configId: "cfg-dataset",
  });

  // Montage : dataset timeField "date", puis app Lecteur temporel + table.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "Lecteur temporel");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Lecteur temporel" }).click();
  await page.getByLabel("Début de l'animation").fill("2026-06-01");
  await page.getByLabel("Fin de l'animation").fill("2026-06-30");
  await page.getByLabel("Intervalle (ms)").fill("3000");
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeVisible();

  // 1re fenêtre (fenêtre de 7 jours par défaut) : 2026-06-01..2026-06-07.
  const first = page.waitForRequest(
    (r) =>
      r.url().includes("/collections/events/items") &&
      r.url().includes("date__gte=2026-06-01") &&
      r.url().includes("date__lte=2026-06-07"),
  );
  await page.getByRole("button", { name: "Lecture" }).click();
  await first;
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();

  // 2e pas (+1 jour) : 2026-06-02..2026-06-08, "Récent" sort de la fenêtre.
  await page.waitForRequest(
    (r) =>
      r.url().includes("/collections/events/items") &&
      r.url().includes("date__gte=2026-06-02") &&
      r.url().includes("date__lte=2026-06-08"),
  );
  await expect(page.getByRole("cell", { name: "Récent" })).toBeHidden();
  await page.getByRole("button", { name: "Pause" }).click();
});
```

Run : `cd shell && npx playwright test e2e/analytics-context.spec.ts`
Expected : tous les tests du fichier passent, dont le nouveau.

Si le palette button « Lecteur temporel » entre en collision avec le titre de l'app « Lecteur
temporel » (même nom accessible), renommer l'app passée à `createApp` en `"Animation"`.

- [ ] **Step 3 : OpenAPI (diff vide attendu) + inventaire**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Expected : aucune sortie. `LayoutItem.props` est un `dict` non typé et la validation vit hors des
modèles Pydantic.

Ajouter **en fin** de `docs/revue/inventaire-fonctionnalites.jsonl` :

```json
{"id": "builder-widgets-widget-lecteur-temporel-anime-le-contexte-temporel-global", "domaine": "Builder — Widgets", "fonctionnalite": "Widget Lecteur temporel (anime le contexte temporel global)", "description": "Lecture/pause, vitesse ×0,5/×1/×2 et pas fixe : fait avancer une fenêtre glissante [début, fin] (stepDays, windowDays, intervalMs) et la pousse via useSetTimeRange, sans effet hors config.interactions==='auto' ; minuteur nettoyé au démontage, arrêt en fin de plage. La carte suit : la plage atteint l'URL de couche de la source liée à un dataset timeField (DataContext → featuresUrl → layersKey). Bornes des props validées à l'écriture côté cœur. REV-104.", "preuve": ["shell/src/builder/widgets/timePlayer.tsx", "shell/src/builder/widgets/timePlayer.test.tsx", "core/app/configs/document_validation.py"], "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []}, "publiques": [], "priorite": "moyenne", "priorite_source": "manuel-l5b", "note_sp42": "Entrée créée par le lot L5b (REV-104, GAP-10).", "note_sp42_date": "2026-10-04"}
```

Run (depuis `core/`) :
- `$CORE_ENV uv run pytest tests/test_feature_inventory.py -q --basetemp=/tmp/pytest-l5b-104`
- `PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`

Expected : les tests passent ; `--check` sort en code 0.

- [ ] **Step 4 : filet de bundle**

Run :
```bash
cd shell && rm -rf dist dist-export && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
```
Expected : `Charge JS/CSS initiale mesurée : X Ko (seuil : 730 Ko)`, code 0.
`registerBuiltinWidgets` est importé par le builder et les runtimes d'app, tous des routes lazy ;
vérifier que `timePlayer` n'est pas dans l'entrée avec `grep -l "widgetTimePlayer.notConfigured\|registerTimePlayerWidget" dist/assets/*.js`.
Le catalogue i18n (dans l'entrée) contiendra la clé : c'est attendu.
**Seulement si** la commande échoue avec `ÉCHEC : charge initiale Y Ko > seuil 730 Ko` :
1. Écrire `ceil(Y)` dans `shell/.bundle-size-threshold`.
2. Relancer et attendre le code 0.
3. Committer à part avec la justification : 11 clés i18n `widgetTimePlayer.*` dans le catalogue
   chargé statiquement ; le widget lui-même est hors entrée.

```bash
git add shell/.bundle-size-threshold
git commit -m "chore(shell): relève le seuil de bundle initial (clés i18n du lecteur temporel, rev-104)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5 : commit**

```bash
git add shell/src/builder/DataContext.test.tsx shell/e2e/analytics-context.spec.ts docs/revue/inventaire-fonctionnalites.jsonl
git commit -m "test(shell): caractérise timerange vers couche carte et e2e du lecteur temporel (rev-104)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Notes de vérification (L5b)

1. **REV-102 — hôte BAN périmé dans la spec.** La spec dit `api-adresse.data.gouv.fr`. Vérifié par
   curl le 2026-10-04 : cet hôte répond encore, mais avec les en-têtes `deprecation`,
   `sunset: Sat, 31 Jan 2026` et `location: https://data.geopf.fr/geocodage/search…`.
   - Le plan cible `https://data.geopf.fr/geocodage/search`, même format GeoJSON (`features[].geometry.coordinates`
     en [lon, lat], `properties.label`), limite amont 50 req/s/IP.
   - L'allowlist par défaut vaut `data.geopf.fr`. Le client ne suit pas les redirections.
   - L'URL est configurable (`CORE_GEOCODING_URL`, vide = 503).
2. **REV-102 — CSP `connect-src` : aucun changement nécessaire.** Le navigateur n'appelle que le cœur
   (même origine, déjà autorisée) ; seul le cœur sort, sous garde d'egress. La spec citait la CSP
   comme point d'attention ; c'est consigné ici et dans l'intro de la sous-section.
3. **REV-104 — `configs/schemas.py`, OpenAPI et types TS : pas de changement de schéma.**
   - `LayoutItem.props` est un `dict` non typé (`core/app/configs/schemas.py:56`). Les props du widget
     ne passent donc ni par un modèle Pydantic, ni par l'OpenAPI.
   - Les bornes sont validées à l'écriture dans `document_validation.py` (L5b-104-1), conformément au
     principe P21 du module : un modèle borné rendrait illisibles des configs déjà enregistrées.
   - La régénération est quand même lancée (diff vide attendu).
   - Le chemin `builder/TimePlayer.tsx` de la spec devient le widget enregistré
     `builder/widgets/timePlayer.tsx`. Les widgets vivent dans le registre ; un composant hors
     registre ne serait pas plaçable dans une app.
4. **REV-104 — « carte applique-t-elle `timeRange` ? » : OUI, vérifié dans le code.** La chaîne
   `DataContext.tsx:87-89`/`:127` → `datasets.ts:89-105` → `mapWidget.tsx` (`ctx.data?.url`) →
   `MapView.tsx:464-467` (`layersKey`) est déjà en place, donc pas de tâche de câblage. L5b-104-3
   ajoute un test de caractérisation falsifié. Limites v1 :
   - source liée à un dataset avec `timeField` uniquement ;
   - couches additionnelles non filtrées ;
   - réapplication de toutes les couches à chaque pas ;
   - inactif hors `interactions: "auto"`.
5. **REV-183 — « OpenAPI à mettre à jour » : diff vide attendu.** Un outil MCP n'est pas une route
   REST, et `POST /v1/copilot/turn` est derrière `CORE_LLM_PROVIDER`, donc absent de
   `core/openapi.json`. `CopilotSurface` est un type shell écrit à la main (`api/types.ts:229`) : il
   est étendu explicitement en L5b-183-3.
6. **REV-183 — référence de ligne.** La spec cite `PropsPanel.tsx:36-42`. Le bloc `visibleWhen` réel
   est l.40-66 : label, aide `Popover`, `textarea`, erreur `formatCelError`.
7. **Jumelles repérées (piège n°14), traitées dans les tâches :**
   - (a) allowlist d'export d'app `core/app/appexport/guard.py` et son test de parité
     `test_appexport_guard.py:315` pour le nouveau widget (L5b-104-2) ;
   - (b) table `PARITY` de `test_mcp_copilot_p23.py` pour le nouveau groupe REST `geocode`
     (L5b-102-2) ;
   - (c) `EGRESS_MODULES` de `test_egress_dns_pinning.py` pour la 6e copie de garde d'egress,
     avec neutralisation de son allowlist par défaut (L5b-102-1) ;
   - (d) `StaticItemClient`/`DesktopItemClient` pour la nouvelle méthode `ItemClient.geocode`
     (L5b-102-3) ;
   - (e) le test de déployabilité pour les 2 nouvelles variables d'env (L5b-102-1/2).
8. **Bundle : composants déjà hors entrée.** Les pages concernées (builder, éditeur de carte, runtime)
   sont déjà des routes lazy. Les nouveaux composants sont malgré tout chargés par `lazy()` comme
   demandé. Le seul coût initial réel vient des clés i18n (catalogue importé statiquement) et, pour
   REV-102, d'une méthode du client composé. Chaque sous-section se termine donc par une mesure et un
   relèvement **conditionnel** et justifié du seuil.
9. **REV-183 — périmètre des champs.** Côté shell, `availableFields` se limite à `vars.<nom>` (clé
   par nom, `VariablesContext.tsx:20`) et à `user.name`. Les champs `record.*` sont hors v1 : ils
   dépendent du widget et de sa source. Le cœur refuse toute référence `vars./record./user.` absente
   de la liste ; une référence citée dans une chaîne littérale est aussi refusée (faux positif
   assumé, commenté `ponytail:`).

---

## Task CLOSE : Clôture du plan B

**Files:**
- Modify: `CLAUDE.md` (§ `### Livré`, UNE ligne ajoutée après la puce du plan A)
- Modify: `docs/superpowers/2026-08-27-historique-execution-continu.md` (entrée détaillée en fin de fichier)
- Modify: `docs/revue/2026-09-04-backlog.md` (états REV du plan B + sommaire ; nouvelles entrées pour les défauts découverts)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (seulement les surfaces nouvelles : `GET /v1/geocode`, outil MCP `generate_cel_expression`, `/sitemap-N.xml`, widget `timePlayer`… — vérifier chaque ligne ajoutée par les tâches de lot)
- Regénérer : `docs/revue/bilan-fonctionnalites.{html,md}`, `docs/revue/historique-sante.jsonl`
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (GAP-nn concernés, s'il y en a)
- Modify: `CHANGELOG.md` (`[Unreleased]` : nouvelles variables d'environnement, géocodage BAN, ports d'outillage liés à 127.0.0.1, hook actionlint, UTC des connexions Postgres)

**Interfaces:**
- Consumes : tout le plan B mergé sur `dev`, suites vertes.
- Produces : documentation alignée sur le code (règle CLAUDE.md « obligatoire dans le même geste »).

- [ ] **Step 1: Vérifier la fermeture par le code, pas par le récit (piège n°12)**

```bash
git log --oneline c33dd036..HEAD | grep -iE 'REV-(239|254|265|251|274|276|277|278|279|280|281|282|283|284|285|286|287|288|289|293|183|184|102|104)'
```
(remplacer `c33dd036` par le commit de base du plan B, relevé avant la première tâche : `git rev-parse HEAD` au démarrage de l'exécution.) Une REV sans commit livrant au moins une de ses lettres ne change pas d'état. Une REV dont toutes les lettres **dans le périmètre de la spec** sont livrées passe `fermé` si aucune lettre hors périmètre ne subsiste, sinon `partiellement fermé` avec la liste des lettres restantes (L1/L6 comprises). Les « Notes de vérification » de chaque lot listent les REV déjà closes sans code.

- [ ] **Step 2: Mettre à jour la ligne `**État :**` de chaque REV du plan B**

Edit sur la première ligne `- **État` sous chaque `### REV-nnn` ; texte : `fermé|partiellement fermé (<date>, plan B lot L4|L5) — <ce qui a été livré, commits/tâches>` ; conserver les renvois L1/L6 des lettres non faites. Ne rien inventer de plus que ce que les commits livrent.

- [ ] **Step 3: Nouvelles entrées de backlog**

Ajouter (`### REV-nnn`, numéros à la suite du dernier existant, état `ouvert`) toute limite assumée ou défaut découvert pendant l'exécution (ex. v1 NL→CEL limité à `vars.*`/`user.name` ; animation temporelle : couches `props.layers` non filtrées ; apps existantes incohérentes recevant un 422 au prochain enregistrement — L4-9 ; clés i18n `roles.privilege.*` allowlistées).

- [ ] **Step 4: GAP-nn concernés dans `analyse-gaps.md`**

`grep -n "GAP-" docs/revue/2026-09-04-analyse-gaps.md` pour les GAP rattachés à REV-102 (géocodage), REV-104 (animation temporelle), REV-183 (NL→CEL) : passer en « ✅ Fermé »/« 🟡 Partiel » selon ce que le code livre, mettre à jour les effectifs du titre en recomptant à la main les lignes de table.

- [ ] **Step 5: Recomptage mécanique du sommaire du backlog**

```bash
sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md
sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md lists
```
Reporter exactement les effectifs mesurés (jamais les attendus) dans la phrase de sommaire, les titres `### ✅ Fermé (n)` etc. et les 3 listes d'ids. Vérification : somme des 4 nombres = `grep -c '^### REV-' docs/revue/2026-09-04-backlog.md`.

- [ ] **Step 6: CLAUDE.md § `### Livré` (UNE ligne) + CHANGELOG**

Insérer une puce après celle du plan A, par exemple : `- **Backlog plan B (L4 reliquats backend, L5 shell UX/copilote/features)** — ferme <REV réellement fermées> (… ), ajoute géocodage BAN (`GET /v1/geocode`), NL→CEL (`generate_cel_expression`), animation temporelle (`timePlayer`) ; <REV> restent partielles (L1/L6).` Une seule puce, aucun récit. Adapter la liste aux seules REV fermées au Step 2.

- [ ] **Step 7: Entrée détaillée dans l'archive d'exécution**

Ajouter à la FIN de `docs/superpowers/2026-08-27-historique-execution-continu.md` une section `## Backlog plan B — lots L4/L5 (<date>)` avec : spec/plan, ce que chaque lot a livré, écarts plan/réalité et défauts trouvés en revue (depuis les ledgers `.superpowers/sdd/backlogB-*`), résultat de la revue finale (nb Critical/Important), non-faits (L1/L6). Aucun crochet `<…>` ne doit subsister : `grep -n '<' ` sur la section ajoutée.

- [ ] **Step 8: Bilan de fonctionnalités**

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
```
`--check` doit sortir 0 (aucune surface non inventoriée, santé médiane ≥ plancher). Si un test épingle un décompte périmé, recaler le test, pas le code.

- [ ] **Step 9: Gardes finales complètes**

```bash
python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold
cd core && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles app/net_pin.py && uv run lint-imports
CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest -q --cov=app --cov-report=xml   # long : lancer en tâche de fond
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && rm -rf dist dist-export && npm run lint && npm run format:check && npx vitest run --coverage && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold
npm run e2e        # suite complète : 0 failed attendu
cd .. && uvx pre-commit run --all-files
```
Tout test rouge en suite complète se rejoue d'abord en isolation (collisions `postgis-test` partagé, piège SP-49) avant d'être imputé.

- [ ] **Step 10: Commit de clôture**

```bash
git add CLAUDE.md CHANGELOG.md docs/superpowers/2026-08-27-historique-execution-continu.md docs/revue/
git commit -m "docs(revue): cloture du plan b — etats rev, sommaire, bilan, claude.md

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Puis, avant tout push : `git fetch && git rev-list --left-right --count origin/dev...dev`. Promotion vers `main` = PR `origin/dev` → `origin/main`, sur demande de Tanguy.
