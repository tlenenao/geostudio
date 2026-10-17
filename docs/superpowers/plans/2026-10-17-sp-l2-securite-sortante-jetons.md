# SP-L2 « Sécurité sortante et jetons » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fermer les AUD du lot L2 de `docs/revue/audit-2026-10-16/99-synthese.md` §4 et de l'addendum §2 (AUD-152 à 157) : une seule garde d'egress SSRF (y compris NAT64), un Chromium d'export qui ne sort plus vers le réseau interne, un jeton d'export qui n'est plus un bearer complet dans l'URL, une CSP dynamique qui ne casse plus et ne s'empoisonne plus, des widgets/popups sans injection, des clés d'API à portée, un effacement de compte qui coupe toute identité résiduelle, des plafonds de corps et des budgets sur les routes anonymes ou coûteuses, et plus aucune erreur interne brute servie à l'utilisateur.

**Architecture:** un module racine `app/egress_guard.py` (hors contrat de couches, comme `app/net_pin.py`) porte la logique de garde ; les 6 `egress.py` de domaine n'y gardent que leur variable d'allowlist et leur classe d'exception ; le Chromium d'export la consomme via `page.route`. Le plafond des clés d'API est un attribut non persisté posé sur l'instance `User` de la requête et lu par l'unique porte `has_privilege`. Les plafonds de corps passent par un seul middleware à table, les budgets par `route_group`. Les messages d'erreur des jobs passent par `app/job_errors.py`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, procrastinate, Playwright (sync), boto3/MinIO, DuckDB (`json_serialize_sql`), pymongo `bson.json_util`, React/Vitest (shell), marked + DOMPurify.

## Périmètre

**AUD couverts :** AUD-023, 024, 050, 064, 066 (portée invité), 081, 089 (robustesse + directives), 090, 091 (clés d'API), 094, 096, 100 (+ jumelles AUD-172), 101 (partiel, cf. écarts), 108, 124, 152, 153, 154, 155, 156, 157 ; AUD-169 (addendum, rattaché L2 : mêmes fichiers d'egress) traité dans la Task 1.

**Reportés (avec raison) :**
- **AUD-109** (intégrité SRI des extensions + `connect-src`/`img-src` de l'origine d'extension) → lot L10 (SDK) : le format du manifeste (`integrity`, `connectHosts`) est un contrat SDK, et D4 place l'ouverture du SDK après L10. Aucun tiers ne peut enregistrer d'extension aujourd'hui (privilège `admin.extensions.manage`).
- **AUD-089, volet « CSP élargie par n'importe quel Créateur »** : décision produit (approbation admin des hôtes vs proxy des tuiles par le cœur). Avec D3 (instance dédiée par client), le Créateur qui élargit la CSP est de la même organisation. La Task 3 traite la robustesse (hôte malformé, cron qui casse) et les directives manquantes (`base-uri`, `form-action`, `frame-ancestors`).
- **AUD-066, volet liens d'embed** (TTL 30 j, restriction d'origine par lien, mot de passe, compteur de vues) : fonctionnalité « différenciateur », exige une colonne `allowed_origins` + un `frame-ancestors` calculé par lien côté nginx du shell (qui ne connaît pas le jeton). À spécifier dans un SP dédié. La Task 3 corrige le défaut de portée invité.
- **AUD-091, volet MCP** (scopes OAuth `mcp:write`, clé `gsk_` utilisable par le MCP) → lot L9 (« IA gouvernée », qui dépend explicitement de L2 pour les scopes) : l'imposer ici casserait le copilote (bouclage `/mcp` avec le jeton OIDC du shell, sans scope dédié) et exige un client scope Keycloak. La Task 5 livre le modèle de portée des clés que L9 consommera.
- **AUD-154, volet quotas éteints par défaut** (`CORE_QUOTAS_ENABLED=false`) : réglage d'exploitation, pas un défaut de code. Le noter dans le runbook d'installation à la clôture.
- **AUD-155, volet « cache public court »** : une réponse WMS dépend des droits de l'appelant, `private` est correct ; non traité.
- **AUD-156, volet pacer partagé entre process** : déjà marqué `ponytail:` dans `geocoding/batch.py:51-52` ; non traité.

**Dépendances :** SP-L1a fusionné (`8b09c207`, `app/jobs/defer.py`). Aucune dépendance sur L3. L9 consommera `ApiKey.scopes` (Task 5).

**Plage de migrations réservée :** `0083`–`0086`. Utilisée : `0083_api_key_scopes` uniquement (Task 5). Head actuel : `0082_pipeline_run_heartbeat`.

**Fichiers/zones touchés (détection de collisions avec les lots parallèles) :**
- Cœur : `app/egress_guard.py` (nouveau), `app/*/egress.py` (6), `app/routing/client.py`, `app/webhooks/delivery.py`, `app/alerts/notify.py`, `app/export/jobs.py`, `app/auth/export_tokens.py`, `app/auth/dependency.py`, `app/security/{csp_hosts,traefik_render,jobs}.py`, `app/configs/{guest_access,extension_permissions,document_validation}.py`, `app/apikeys/*`, `app/roles/guards.py`, `app/users/models.py`, `app/compliance/{service,routes}.py`, `app/jobs/common.py`, `app/pipelines/service.py`, `app/main.py` (middleware de corps), `app/ratelimit/limiter.py`, `app/public_submit/{routes,service}.py`, `app/ingestion/{routes,storage,schemas,tasks}.py`, `app/raster/{routes,schemas,zonal,jobs}.py`, `app/terrain3d/{routes,schemas,jobs}.py`, `app/attachments/{routes,schemas}.py`, `app/ows/{routes,wms_routes}.py`, `app/geocoding/{routes,jobs}.py`, `app/pipelines/{connector_runtime,jobs}.py`, `app/pipelines/ops/{cloudfiles,dbio2}.py`, `app/pipelines/sidecar/runner.py`, `app/analytics/sql_sandbox.py`, `app/job_errors.py` (nouveau) et les catch-all des jobs `tileset3d/terrain3d/raster/quality/reports/alerts/dataexport/appexport/export`.
- Shell : `src/auth/{exportAwareToken.ts,RequireAuth.tsx}`, `src/App.tsx`, `src/map/popupTemplate.ts`, `src/builder/widgets/{sanitizeMarkdown.ts,index.tsx}`, `src/api/domains/{identity,exportsIngestion,raster,tiles3d,attachments,apiKeys}.ts`, `src/api/itemClient.ts`, `src/api/types.ts`, `src/desktop/DesktopItemClient.ts`, `src/staticExport/StaticItemClient.ts`, les 4 boutons/flux d'upload, `src/pages/{ComplianceAdminPage,UsersAdminPage,ApiKeysSection}.tsx`.
- Déploiement : `docker-compose.yml` (port core, label `shell-embed`), `docker-compose.prod.yml` (label `shell-embed`), `core/tests/test_deployability.py`.
- Collisions probables : **L5** (shell : popups, widgets, `ItemClient`, pages admin), **L4** (compliance, audit, multi-tenant), **L9** (MCP), **L1b** (jobs/catch-all, si L1b touche les mêmes `except`), toute voie qui modifie `app/main.py` ou `ratelimit/limiter.py`.

## Global Constraints

- `CORE_TEST_DATABASE_URL` pointe une **base jetable dédiée** sur `postgis-test` (`createdb geostudio_spl2`), DSN `postgresql+psycopg://…/geostudio_spl2` : d'autres agents tournent en parallèle sur le même conteneur (piège SP-49). Sans la variable, les tests `postgis` skippent silencieusement.
- Toute route ou modèle exposé modifié (Tasks 5, 6) : régénérer OpenAPI + types TS avec l'incantation exacte —
  `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types`. Aucune route nouvelle dans ce lot : l'inventaire `docs/revue/inventaire-fonctionnalites.jsonl` ne change pas (le vérifier par `feature_health_cli.py --check` en clôture).
- Migration `0083` : tester `upgrade`/`downgrade` **sur base non vide** (piège n°8), patron `core/tests/test_migration_0081_geocode_jobs.py` ; après migration, `ALTER TABLE` manuel sur `postgis-test` si besoin (piège SP-42).
- Piège n°14 : chaque tâche liste ses jumelles ; les relire avant de clore la tâche.
- Piège n°3 : tout nom de variable/ligne repris de l'audit a été revérifié (section « Faits vérifiés ») ; en cas de nouvel écart, corriger et le consigner dans le rapport de tâche.
- Commits conventional en français, un sujet par commit, trailer exact : `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Vérifier soi-même `git show --stat` (le sous-agent embarque parfois des fichiers non liés).
- `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, Helm : modifications localisées aux lignes citées ; toute nouvelle substitution compose documentée dans `.env.example` (règle de `test_deployability.py`).
- **Interdits :** modifier `CLAUDE.md`, `docs/revue/*`, `docs/superpowers/2026-08-27-historique-execution-continu.md` (clôture documentaire par le contrôleur).
- Portes avant chaque commit côté cœur : `uv run ruff check . && uv run ruff format --check . && uv run lint-imports` ; côté shell : `npm run lint && npm run format:check` et `npx vitest run <fichiers touchés>` ; `npm run build` en fin de Task 2, 4, 5, 6 (tsc attrape ce que vitest par fichier ne voit pas).

## Faits vérifiés / écarts à l'audit

- **AUD-124** : 6 copies identiques (`alerts`, `copilot`, `geocoding`, `harvest`, `pipelines`, `search`) + une 7e garde **réécrite** dans `routing/client.py:59-81` (autorise le privé à dessein : Valhalla est interne). « 6 à 9 copies » → 7. `geocoding` a une allowlist par défaut `data.geopf.fr` (appliquée seulement si la variable est absente). Le contrat import-linter est dans `core/pyproject.toml:326-569` (pas de `core/.importlinter`) ; un module racine hors liste `layers` est importable partout sans exemption (précédent `app/sql_ident.py`).
- Mesuré (Python 3.14 local, image 3.12 : à épingler par test) : `64:ff9b::a9fe:a9fe` (NAT64 → 169.254.169.254), `64:ff9b::7f00:1`, `64:ff9b::a00:1` ont `is_global=True` et **passent** la garde ; second trou non signalé par l'audit : les adresses IPv4-compatibles `::/96` (`::a9fe:a9fe`) passent aussi (`is_reserved=True`).
- **AUD-169** : le fichier est `core/app/webhooks/delivery.py:53-60` (pas `alerts/delivery.py`) ; jumelle non listée : `core/app/alerts/notify.py:88-97` (même POST qui suit les redirections, en-tête `X-GeoStudio-Signature` réémis sur 307/308).
- **AUD-023** : les lignes ont bougé depuis l'audit (commits `6f59426b`, `1424e0b1`) : `_launch_and_navigate` est en `export/jobs.py:223-283`, `goto` l.259, mint l.329, URL `?exportToken=` l.334, lancement l.354. « aucune occurrence de `route(` » est périmé : `page.route` existe l.258 pour le pont AUD-133 (`{public}/**`) ; aucun filtrage du reste. `RENDER_TIMEOUT_MS = 120_000` (`rendering.py:14`) = TTL du jeton (120 s) : confirmé.
- **AUD-024** : `export_tokens.py` fait 78 lignes ; `decode` sans `require`, sans liaison à l'item ni au job ; la branche de `get_current_user` (`dependency.py:230-240`) ne teste pas `erased_at` (non signalé par l'audit). Côté shell, `exportAwareToken.ts:18-23` honore tout `?exportToken=` ; `RequireAuth.tsx:16-25` saute la connexion ; `App.tsx:46-51` coupe le renouvellement.
- **AUD-089** : `_origin` (`csp_hosts.py:23-29`) laisse passer `"`, `;`, espace dans l'hôte ; `parsed.port` lève `ValueError` sur `https://x:abc/` et `https://x:99999/` → `refresh_csp_dynamic_conf_task` (`security/jobs.py:32-41`, aucun try) échoue à chaque tick. Entrées non validées : basemap (`basemap_routes.py:41-52`), moissonnage (`harvest/schemas.py:22-30`), `ModuleUrl` d'extension (`extensions/schemas.py:9`, pas « ~141 »), `map.terrain.tilesUrl` jamais validé. Docstring `traefik_render.py:8-11` fausse ; écriture non atomique (`open(..., "w")`).
- **AUD-066** : `resolve_guest_scope` (`configs/guest_access.py:68-117`, pas `app/embed/`) ne parcourt que `config.dataSources` ; `widget_nodes` (`document_validation.py:128-141`) existe déjà. Le routeur `shell-embed` (`docker-compose.yml:1053`, prod `:311`) n'a ni `X-Frame-Options` ni `frame-ancestors`.
- **AUD-108** : en plus du contournement par `props.dataSourceId` : `_all_layout_items` (`extension_permissions.py:20-26`) ignore les widgets imbriqués (modale/tiroir) ; une source `datasetId` n'est jamais résolue en collection.
- **AUD-050** : la valeur entre dans le markdown en `popupTemplate.ts:94` (pas 79), `sanitizeMarkdown.ts:9-12` appelle DOMPurify sans config. `interpolatePopupTemplate` est aussi appelé en texte brut par `map/labelSource.ts:86` et `builder/print/EntityFiche.tsx:29,32` : ne pas changer son comportement par défaut.
- **AUD-064** : `window.open` non gardé en `builder/widgets/index.tsx:191` ; `isSafeHref` exporté par `hero.tsx:9-21` (accepte relatif et `mailto:`) ; côté serveur `_http_url_error` ne couvre que les couches de carte et refuse le relatif : ne pas le réutiliser tel quel pour `href`.
- **AUD-091** : `ApiKey` sans portée (`apikeys/models.py`), dernière migration `0053_api_keys.py`. Porte unique `has_privilege` (`roles/guards.py:12`, 127 appels) ; aucun `ContextVar` d'auth, et un `ContextVar` posé dans une dépendance **sync** n'est pas vu par la route (contexte copié par appel de threadpool) : d'où l'attribut d'instance.
- **AUD-094** : `anonymize_user` (`compliance/service.py:52-99`) révoque les clés d'API seulement. `resolve_owner_user` (`jobs/common.py:48-63`) ne teste pas `erased_at` (appelants : pipelines, alertes, rapports, déclencheur webhook `pipelines/service.py:295`) ; copie `alerts/notify.py:45`. `User.role_id` est **non nullable** : on ne retire pas le rôle, on bloque l'identité aux points de résolution. Route d'effacement sans `forbid_api_key`.
- **AUD-096** : confirmé (`mcp/tools/identity.py:64-77`).
- **AUD-101** : `docker-compose.yml:449-451` publie `8200:8200` sans profil ; `docker-compose.prod.yml` remet `ports: !reset []` ; défaut `CORE_TRUSTED_PROXIES` = RFC 1918 partout (compose, `.env.example:158-161`, Helm `values.yaml:118`). Commentaire `main.py:605` « core:8000 » faux (8200).
- **AUD-090/153** : `submit` (`public_submit/routes.py:61-122`) parse le multipart avant tout contrôle (Starlette 1.3.1 ne plafonne que les champs non-fichier). Presign : `PresignRequest`/`RasterPresignRequest`/`Terrain3DPresignRequest`/`AttachmentPresignRequest` sans taille ; `generate_presigned_put_url` (`ingestion/storage.py:110-122`) ne signe pas `Content-Length`. Mesuré : `make_s3_client` (`storage.py:33-41`) produit des URL **SigV2** (pas de `SignedHeaders`) ; avec `Config(signature_version="s3v4")` + `ContentLength`, `X-Amz-SignedHeaders=content-length;content-type;host`.
- **AUD-154** : ADR 0017:16 promet une limite horaire « par IP et par jeton » ; le code ne limite que par IP exacte (`service.py:82`).
- **AUD-155** : `route_group` ne couvre ni `/v1/ows/*` ni les tuiles raster/terrain ; WFS `resulttype=hits` (`ows/routes.py:221-230`) en `count_mode="exact"` **sans** `statement_timeout` (WMS en a un, `wms_routes.py:147`).
- **AUD-156** : `_GEOCODE_RE` (`limiter.py:66`) exclut `/jobs` ; aucun privilège, aucun plafond de jobs actifs ; statuts réels `pending|running|succeeded|failed` ; aucune purge hors `purge_tenant`.
- **AUD-157** : `MAX_WINDOW_PIXELS = 50_000_000` (`raster/zonal.py:16`), délai testé entre polygones seulement ; route `raster/routes.py:264` hors `route_group`.
- **AUD-100** : le fichier est `ingestion/tasks.py:223-244` (pas `ingestion/jobs.py`). Jumelles `f"erreur interne : {exc}"` : `pipelines/jobs.py:447,450,458`, `pipelines/sidecar/runner.py:51`, `tileset3d/jobs.py:163,165`, `terrain3d/jobs.py:173,175`, `raster/jobs.py:165`, `quality/jobs.py:56`, `reports/jobs.py:263,269,295,445`, `alerts/jobs.py:479,549`, `geocoding/jobs.py:99` (`str(exc)[:500]`) ; `str(exc)` brut sans branche typée : `dataexport/jobs.py:191,193` (= AUD-172), `appexport/jobs.py:190,197`, `export/jobs.py:424,433`. Aucun helper existant.
- **AUD-152** : confirmé `cloudfiles.py:856-864` ; les usages de `sanitize_cell` dans `runtime.py` sont en `:1375/:1380` (pas 1371/1376). `app.cell_safety` est un module racine.
- **AUD-081** : confirmé ; mesuré : `validate_select_only` accepte `SELECT pg_terminate_backend(1)`, `lo_export(...)`. Aucun lien secret ↔ dialecte hors Databricks : un secret `postgres_dsn` peut contenir `sqlite:////chemin` (hôte vide, garde d'egress sautée). DuckDB : nœud `{"class": "FUNCTION", "function_name": "<nom en minuscules>"}` (vérifié). `bson.json_util.loads` convertit `$oid`/`$date` (vérifié, pymongo 4.19).

---

### Task 1: AUD-124 + AUD-169 — garde d'egress unique, NAT64 fermé, redirections refusées

**Files:**
- Create: `core/app/egress_guard.py`
- Modify: `core/app/{alerts,copilot,geocoding,harvest,pipelines,search}/egress.py`, `core/app/routing/client.py:59-81`, `core/app/webhooks/delivery.py:53-60`, `core/app/alerts/notify.py:88-97`
- Test: `core/tests/test_egress_guard.py` (nouveau), `core/tests/test_egress_site_local.py`, `core/tests/test_webhook_delivery_redirects.py` (nouveau)

**Interfaces:**
- Produces: `app.egress_guard.is_internal(ip: IPv4Address | IPv6Address) -> bool` ; `embedded_ipv4(ip) -> IPv4Address | None` ; `check_url(url: str, *, allowlist_env: str, default_allowlist: str = "", error: type[Exception]) -> ValidatedIp`. Chaque `app/<domaine>/egress.py` garde **le même nom public** `assert_egress_allowed(url) -> ValidatedIp` et sa propre `EgressBlockedError` (les appelants l'attrapent par domaine, ne rien renommer).

Jumelles (piège n°14) : les 6 `egress.py`, `routing/client.py` (règle différente, ne reçoit que le déballage NAT64), `webhooks/delivery.py` + `alerts/notify.py` (redirections), `cloudfiles.py:343` et `messaging.py:265` (déjà `allow_redirects=False`, rien à faire). Garde Chromium : Task 2.

- [ ] **Step 1: Test qui échoue** — `core/tests/test_egress_guard.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-124 : une seule garde, paramétrée sur les 6 domaines (parité)."""

import importlib
import ipaddress

import pytest

from app.egress_guard import embedded_ipv4, is_internal

MODULES = [
    "app.alerts.egress",
    "app.copilot.egress",
    "app.geocoding.egress",
    "app.harvest.egress",
    "app.pipelines.egress",
    "app.search.egress",
]

INTERNAL = [
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "::1", "fec0::1",
    "::ffff:169.254.169.254", "64:ff9b::a9fe:a9fe", "64:ff9b::7f00:1", "64:ff9b::a00:1",
    "64:ff9b:1::a00:1", "::a9fe:a9fe", "2002:a9fe:a9fe::1", "224.0.0.1",
]
PUBLIC = ["8.8.8.8", "2001:4860:4860::8888", "64:ff9b::808:808"]


@pytest.mark.parametrize("addr", INTERNAL)
def test_internal_addresses_are_internal(addr):
    assert is_internal(ipaddress.ip_address(addr))


@pytest.mark.parametrize("addr", PUBLIC)
def test_public_addresses_are_not_internal(addr):
    assert not is_internal(ipaddress.ip_address(addr))


def test_embedded_ipv4_unwraps_nat64_mapped_and_compat():
    assert str(embedded_ipv4(ipaddress.ip_address("64:ff9b::a9fe:a9fe"))) == "169.254.169.254"
    assert str(embedded_ipv4(ipaddress.ip_address("::ffff:10.0.0.1"))) == "10.0.0.1"
    assert embedded_ipv4(ipaddress.ip_address("8.8.8.8")) is None


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("addr", ["64:ff9b::a9fe:a9fe", "::a9fe:a9fe", "127.0.0.1"])
def test_every_domain_guard_blocks_internal_literals(monkeypatch, module_name, addr):
    mod = importlib.import_module(module_name)
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    host = f"[{addr}]" if ":" in addr else addr
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed(f"http://{host}/x")


@pytest.mark.parametrize("module_name", MODULES)
def test_every_domain_guard_refuses_non_http(module_name):
    mod = importlib.import_module(module_name)
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("file:///etc/passwd")


def test_geocoding_keeps_its_default_allowlist(monkeypatch):
    mod = importlib.import_module("app.geocoding.egress")
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    with pytest.raises(mod.EgressBlockedError, match="allowlist"):
        mod.assert_egress_allowed("http://8.8.8.8/")
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_egress_guard.py -q` → FAIL (`ModuleNotFoundError: app.egress_guard`).

- [ ] **Step 3: Implémenter** `core/app/egress_guard.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF unique (AUD-124). Module racine sans dépendance
applicative (hors liste `layers` du contrat import-linter, comme
`app.net_pin`/`app.sql_ident`) : chaque domaine n'y ajoute que sa variable
d'allowlist et sa classe d'exception."""

import ipaddress
import os
import socket
from urllib.parse import urlparse

from app.net_pin import ValidatedIp

IP = ipaddress.IPv4Address | ipaddress.IPv6Address

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def embedded_ipv4(ip: IP) -> ipaddress.IPv4Address | None:
    """IPv4 transportée par une IPv6 (mappée, NAT64 bien connue, 6to4,
    IPv4-compatible dépréciée), sinon None."""
    if ip.version != 6:
        return None
    assert isinstance(ip, ipaddress.IPv6Address)
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour is not None:
        return ip.sixtofour
    if int(ip) >> 32 == 0 and int(ip) > 1:  # ::a.b.c.d (IPv4-compatible)
        return ipaddress.IPv4Address(int(ip))
    return None


def is_internal(ip: IP) -> bool:
    # tout ce qui n'est pas globalement routable (CGNAT 100.64/10, TEST-NET…) ;
    # fec0::/10 : is_global le laisse passer (j06-003) ; NAT64/::/96 : AUD-124.
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return True
    if getattr(ip, "is_site_local", False):
        return True
    v4 = embedded_ipv4(ip)
    return v4 is not None and is_internal(v4)


def allowlist(env: str, default: str = "") -> set[str]:
    raw = os.environ.get(env, default)
    return {h.strip() for h in raw.split(",") if h.strip()}


def check_url(
    url: str, *, allowlist_env: str, default_allowlist: str = "", error: type[Exception]
) -> ValidatedIp:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise error(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise error(f"hôte d'egress absent dans l'URL : {url!r}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise error(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses:
        raise error(f"hôte non résoluble : {host!r}")
    for ip in addresses:
        if is_internal(ip):
            raise error(f"cible réseau interne bloquée : {host!r}")
    allowed = allowlist(allowlist_env, default_allowlist)
    if allowed and host not in allowed:
        raise error(f"hôte hors allowlist d'egress : {host!r}")
    return ValidatedIp(str(addresses[0]), [str(a) for a in addresses])  # REV-273d
```

- [ ] **Step 4: Brancher les 6 domaines.** Dans chaque `app/<domaine>/egress.py`, supprimer `_allowlist`, `_is_internal` et le corps de `assert_egress_allowed` (copie identique vérifiée) ; garder la classe `EgressBlockedError`, la constante `_ALLOWLIST_ENV` et tout le reste (transports, `build_guarded_*`, `PinnedAioResolver`, DSN). Exemple pour `alerts/egress.py` (même forme pour `copilot`, `harvest`, `pipelines`, `search`) :

```python
from app.egress_guard import check_url


def assert_egress_allowed(url: str) -> ValidatedIp:
    return check_url(url, allowlist_env=_ALLOWLIST_ENV, error=EgressBlockedError)
```

Pour `geocoding/egress.py` : `check_url(url, allowlist_env=_ALLOWLIST_ENV, default_allowlist=_DEFAULT_ALLOWLIST, error=EgressBlockedError)`. Retirer les imports devenus inutiles (`ipaddress`, `socket`, `urlparse` si plus utilisés — `pipelines/egress.py` garde `urlparse` pour les DSN). Mettre à jour les docstrings qui assument « la duplication délibérée ». Remplacer, partout dans `core/tests`, les références à `<module>._is_internal`/`_allowlist` (`grep -rn "_is_internal\|\._allowlist" core/tests`) par `app.egress_guard.is_internal`/`allowlist` ; `test_egress_site_local.py` devient un appel paramétré de `is_internal`.

- [ ] **Step 5: `routing/client.py`** — dans la boucle de `assert_egress_allowed` (l.77-80), remplacer `ip = getattr(ip, "ipv4_mapped", None) or ip` par :

```python
        ip = embedded_ipv4(ip) or ip  # mappée ET NAT64/6to4 (AUD-124)
```
(`from app.egress_guard import embedded_ipv4`.) La règle reste « privé autorisé, link-local/multicast/réservé refusés » : Valhalla est interne.

- [ ] **Step 6:** `uv run pytest tests/test_egress_guard.py tests/test_egress_site_local.py tests/test_egress_dns_pinning.py tests/test_net_pin.py tests/test_alert_egress.py tests/test_copilot_egress.py tests/test_geocoding_egress.py tests/test_harvest_egress.py tests/test_search_egress.py tests/test_pipeline_egress.py -q` → PASS ; `uv run lint-imports` → vert.

- [ ] **Step 7: Test redirections (AUD-169)** — `core/tests/test_webhook_delivery_redirects.py`

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-169 : un POST signé ne suit jamais une redirection ; 3xx = échec."""

import pytest
import requests

from app.webhooks import delivery


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.is_redirect = 300 <= status < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_a_delivery_failure_and_is_not_followed(monkeypatch, status):
    seen = {}

    class _Session:
        def post(self, url, **kw):
            seen.update(kw)
            return _Resp(status)

    monkeypatch.setattr(delivery, "build_guarded_session", lambda: _Session())
    with pytest.raises(delivery.DeliveryError):
        delivery._http_post("https://hook.example/x", b"{}", {})
    assert seen["allow_redirects"] is False
```

- [ ] **Step 8:** lancer → FAIL (`KeyError: 'allow_redirects'`). **Implémenter** dans `webhooks/delivery.py:_http_post` :

```python
def _http_post(url: str, body: bytes, headers: dict) -> None:
    try:
        resp = build_guarded_session().post(
            url, data=body, headers=headers, timeout=_TIMEOUT_S, allow_redirects=False
        )
        if 300 <= resp.status_code < 400:  # AUD-169 : jamais suivie, jamais « delivered »
            raise requests.HTTPError(f"redirection refusée ({resp.status_code})", response=resp)
        resp.raise_for_status()
    except EgressBlockedError as exc:
        raise DeliveryError(f"egress bloqué : {exc}") from exc
    except requests.RequestException as exc:
        raise DeliveryError(f"livraison échouée : {exc}") from exc
```
Corriger la docstring l.2-3 (« redirections refusées »). Même correctif dans `alerts/notify.py` autour de l.90 : `session_http.post(channel.url, timeout=10, allow_redirects=False, **request_kwargs)` puis, avant `resp.raise_for_status()`, la même ligne `if 300 <= resp.status_code < 400: raise requests.HTTPError(...)` ; mettre à jour sa docstring l.7-18 (elle promet des redirections re-gardées). Ajouter un test jumeau dans `test_webhook_delivery_redirects.py` qui monkeypatche `app.alerts.notify.build_guarded_session` et appelle la fonction d'envoi webhook de `notify.py` (lire son nom réel l.80-100) en vérifiant l'échec et `allow_redirects is False`.
- [ ] **Step 9:** `uv run pytest tests/test_webhook_delivery_redirects.py tests -k "webhook or notify or alert" -q` → PASS ; ruff + lint-imports.
- [ ] **Step 10: Commits** — `refactor(core): garde d'egress unique, NAT64 et ::/96 bloqués (AUD-124)` puis `fix(core): les webhooks ne suivent plus les redirections (AUD-169)`.

---

### Task 2: AUD-023 + AUD-024 — Chromium d'export gardé, jeton d'export borné et hors URL

**Files:**
- Modify: `core/app/export/jobs.py` (`_launch_and_navigate` l.223-283, `render_export_task` l.329-356), `core/app/auth/export_tokens.py`, `core/app/auth/dependency.py` (`get_current_user`, `get_current_user_optional`), `shell/src/auth/exportAwareToken.ts`, `shell/src/auth/RequireAuth.tsx`, `shell/src/App.tsx:46-51`
- Test: `core/tests/test_export_jobs.py`, `core/tests/test_export_tokens.py`, `core/tests/test_auth_export_token.py`, `shell/src/auth/exportAwareToken.test.ts`, `shell/src/auth/RequireAuth.test.tsx`

**Interfaces:**
- Consumes: `app.egress_guard.check_url` (Task 1).
- Produces: `mint_export_token(*, tenant_id, user_id, job_id, item_id, ttl_seconds=EXPORT_TOKEN_TTL_S) -> str` ; `EXPORT_TOKEN_TTL_S = RENDER_TIMEOUT_MS // 1000 + 60` ; `ExportTokenClaims.item_id` ; `_egress_route_handler(allowed_origins: frozenset[str]) -> Callable[[Route], None]` ; `_launch_and_navigate(url, viewport=None, core_bridge=None, export_token: str | None = None)` ; shell `EXPORT_TOKEN_STORAGE_KEY = "gs_export_token"`, `readExportToken(): string | null`. Variable optionnelle `CORE_EXPORT_EGRESS_ALLOWLIST` (vide = tout hôte public).

Décision de conception : le jeton n'est plus dans l'URL ; Playwright l'injecte dans `sessionStorage` de l'origine du shell par `add_init_script` avant tout script de la page. Le shell ne l'honore que si `exportRender=1` **et** la clé est en `sessionStorage` : un lien piégé `?exportToken=` n'a plus d'effet (login-CSRF fermé). `extra_http_headers` est écarté : il enverrait le jeton à tous les hôtes de tuiles tiers. Jumelles : `get_current_user_optional` (délègue), branche export de `get_current_user` (ajout `erased_at`, aussi requis par AUD-094).

- [ ] **Step 1: Tests jeton (cœur)** — ajouter à `core/tests/test_export_tokens.py` :

```python
def test_token_carries_item_and_ttl_covers_the_render_budget(monkeypatch):
    import jwt

    from app.auth import export_tokens
    from app.export.rendering import RENDER_TIMEOUT_MS

    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "s" * 32)
    tok = export_tokens.mint_export_token(tenant_id="t", user_id="u", job_id="j", item_id="i")
    claims = jwt.decode(tok, "s" * 32, algorithms=["HS256"])
    assert claims["item_id"] == "i"
    assert claims["exp"] - claims["iat"] >= RENDER_TIMEOUT_MS // 1000 + 60
    assert export_tokens.decode_export_token(tok).item_id == "i"


def test_decode_requires_exp(monkeypatch):
    import jwt
    import pytest

    from app.auth import export_tokens

    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "s" * 32)
    tok = jwt.encode(
        {"typ": "export", "tenant_id": "t", "user_id": "u", "job_id": "j", "item_id": "i", "iat": 1},
        "s" * 32,
        algorithm="HS256",
    )
    with pytest.raises(export_tokens.ExportTokenError):
        export_tokens.decode_export_token(tok)
```
Et à `core/tests/test_auth_export_token.py` (réutiliser la fixture et l'helper de requête déjà présents dans ce fichier, lire leur nom avant d'écrire) : un `DELETE /v1/items/<id>` avec un jeton d'export valide → `403` ; un `GET` du même chemin → pas `403` ; un jeton d'export d'un utilisateur effacé (`erased_at` posé) → `401`.

- [ ] **Step 2:** `uv run pytest tests/test_export_tokens.py tests/test_auth_export_token.py -q` → FAIL.
- [ ] **Step 3: Implémenter** `export_tokens.py` :

```python
from app.export.rendering import RENDER_TIMEOUT_MS  # lire d'abord : si lint-imports refuse
# (app.auth sous app.export dans le contrat), recopier la constante 120_000 avec un
# commentaire « miroir de app.export.rendering.RENDER_TIMEOUT_MS » et un test d'égalité.

_REQUIRED_CLAIMS = ("tenant_id", "user_id", "job_id", "item_id")
# AUD-024 : le jeton couvre tout le budget de rendu, plus une marge (D04-05).
EXPORT_TOKEN_TTL_S = RENDER_TIMEOUT_MS // 1000 + 60


class ExportTokenClaims:
    def __init__(self, *, tenant_id: str, user_id: str, job_id: str, item_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.job_id = job_id
        self.item_id = item_id


def mint_export_token(
    *, tenant_id: str, user_id: str, job_id: str, item_id: str, ttl_seconds: int = EXPORT_TOKEN_TTL_S
) -> str:
    now = int(time.time())
    claims = {
        "typ": _TYP, "tenant_id": tenant_id, "user_id": user_id, "job_id": job_id,
        "item_id": item_id, "iat": now, "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)
```
Dans `decode_export_token` : `jwt.decode(token, _secret(), algorithms=[_ALGORITHM], options={"require": ["exp", "iat"]})` et passer `item_id=claims["item_id"]`. Mettre à jour la docstring du module (portée lecture seule, TTL = budget de rendu + 60 s).

Dans `dependency.py` : ajouter `request: Request` (de `fastapi`) en **premier** paramètre de `get_current_user` et de `get_current_user_optional` (qui le passe : `get_current_user(request=request, authorization=authorization, session=session)`), puis dans la branche export :

```python
    if is_export_token(token):
        try:
            claims = decode_export_token(token)
        except ExportTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid export token") from exc
        if claims.tenant_id != tenant.id:
            raise HTTPException(status_code=401, detail="invalid export token")
        # AUD-024 : un jeton d'export ne fait que lire, quelle que soit la route.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            raise HTTPException(status_code=403, detail="export token is read-only")
        user = session.get(User, claims.user_id)
        if user is None or user.erased_at is not None:  # AUD-094
            raise HTTPException(status_code=401, detail="invalid export token")
        return user
```
`grep -rn "get_current_user(" core/app core/tests` : tout appel direct (hors `Depends`) passe désormais `request=` (dans les tests, `starlette.requests.Request({"type": "http", "method": "GET", "headers": []})`).

- [ ] **Step 4:** tests de Step 1 → PASS.
- [ ] **Step 5: Test garde Chromium** — ajouter à `core/tests/test_export_jobs.py` :

```python
class _Req:
    def __init__(self, url):
        self.url = url


class _Route:
    def __init__(self, url):
        self.request = _Req(url)
        self.outcome = None

    def continue_(self):
        self.outcome = "continue"

    def abort(self, reason="failed"):
        self.outcome = f"abort:{reason}"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://shell.test/assets/app.js", "continue"),
        ("https://geo.example/api/v1/items", "continue"),
        ("data:image/png;base64,AAAA", "continue"),
        ("http://169.254.169.254/opc/v2/instance/", "abort:blockedbyclient"),
        ("http://minio:9000/bucket/x", "abort:blockedbyclient"),
        ("http://[64:ff9b::a9fe:a9fe]/", "abort:blockedbyclient"),
        ("https://8.8.8.8/tiles/1/2/3.png", "continue"),
    ],
)
def test_egress_route_handler_blocks_internal_targets(monkeypatch, url, expected):
    import socket

    real = socket.getaddrinfo
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(0, 0, 0, "", ("172.18.0.5", 0))] if host == "minio" else real(host, *a, **k),
    )
    handler = export_jobs._egress_route_handler(
        frozenset({"http://shell.test", "https://geo.example"})
    )
    route = _Route(url)
    handler(route)
    assert route.outcome == expected


def test_render_url_no_longer_carries_the_token(db_session, monkeypatch):
    session, tenant, user, item = db_session
    urls, tokens = [], []
    monkeypatch.setattr(
        export_jobs,
        "_launch_and_navigate",
        lambda url, **kw: urls.append(url) or tokens.append(kw.get("export_token")) or _FakePage(),
    )
    monkeypatch.setattr(export_jobs, "s3_client_from_env", lambda: _FakeUploadS3Client())
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf"
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant.id)

    assert "exportToken" not in urls[0]
    assert "exportRender=1" in urls[0]
    assert tokens[0]
```
Mettre aussi à jour `test_render_export_task_url_unchanged_when_page_id_and_ctx_absent` (l.313 : `f"/maps/{item.id}?exportToken="` → `f"/maps/{item.id}?exportRender=1"`) et toute autre assertion `exportToken=` du fichier (`grep -n "exportToken" core/tests/test_export_jobs.py`). Adapter les fakes Playwright de `test_launch_and_navigate_shares_one_120s_budget` et `test_launch_and_navigate_cleans_up_driver_and_browser_on_mid_sequence_failure` : `_Page` reçoit `def route(self, pattern, handler): calls.setdefault("routes", []).append(pattern)` et `def add_init_script(self, script): calls["init"] = script` ; `_Browser.new_page(**kw)` mémorise `kw` ; asserter `kw["service_workers"] == "block"`, `"**/*" in calls["routes"]`, et l'ordre (`"**/*"` enregistré **avant** le motif du pont).

- [ ] **Step 6:** lancer → FAIL.
- [ ] **Step 7: Implémenter** dans `export/jobs.py` :

```python
import json
from urllib.parse import urlparse

from app.egress_guard import check_url


class _ExportEgressBlocked(Exception):
    pass


def _egress_route_handler(allowed_origins: frozenset[str]):
    """AUD-023 : le navigateur du worker ne joint que le shell, le cœur public et
    des hôtes publics ; toute cible interne (métadonnées cloud, minio, core…)
    est refusée. ponytail: Chromium résout le DNS lui-même après ce contrôle
    (TOCTOU) ; une allowlist stricte via CORE_EXPORT_EGRESS_ALLOWLIST ferme ce reste."""

    def handle(route) -> None:
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme in {"data", "blob"} or f"{parsed.scheme}://{parsed.netloc}" in allowed_origins:
            route.continue_()
            return
        try:
            check_url(url, allowlist_env="CORE_EXPORT_EGRESS_ALLOWLIST", error=_ExportEgressBlocked)
        except _ExportEgressBlocked:
            logger.warning("export : requête sortante bloquée vers %s", parsed.hostname)
            route.abort("blockedbyclient")
            return
        route.continue_()

    return handle
```
Dans `_launch_and_navigate`, ajouter le paramètre `export_token: str | None = None` et remplacer la création de page + route :

```python
        page_kw: dict = {"service_workers": "block"}
        if viewport:
            page_kw["viewport"] = {"width": viewport[0], "height": viewport[1]}
        page = browser.new_page(**page_kw)
        shell = urlparse(url)
        shell_origin = f"{shell.scheme}://{shell.netloc}"
        allowed = {shell_origin}
        published = _published_core_url(shell_origin)
        if published:
            p = urlparse(published)
            allowed.add(f"{p.scheme}://{p.netloc}")
        # Garde d'abord : Playwright donne la main à la route enregistrée EN DERNIER,
        # le pont (plus spécifique) reste donc prioritaire sur son motif.
        page.route("**/*", _egress_route_handler(frozenset(allowed)))
        if core_bridge is not None:
            public, internal = core_bridge
            page.route(f"{public}/**", _core_bridge_handler(public, internal))
        if export_token is not None:
            page.add_init_script(
                f"if (location.origin === {json.dumps(shell_origin)}) "
                f"sessionStorage.setItem('gs_export_token', {json.dumps(export_token)});"
            )
        page.goto(url, wait_until="load", timeout=remaining_ms())
```
(Vérifier la signature réelle de `_published_core_url`, l.143-150 ; si elle prend l'URL du shell, l'appel ci-dessus est correct.) Dans `render_export_task` : supprimer la ligne `token = mint_export_token(...)` de la l.329 et le `exportToken={token}&` de l'URL (`target_url = f"{base}?exportRender=1"`) ; après le contrôle d'annulation et juste avant `_launch_and_navigate`, émettre `token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id, item_id=item_id)` et passer `export_token=token`.

- [ ] **Step 8:** `uv run pytest tests/test_export_jobs.py tests/test_export_tokens.py tests/test_auth_export_token.py tests/test_export_rendering.py -q` → PASS (le test `real_chromium` skippe sans Chromium).
- [ ] **Step 9: Tests shell** — remplacer les deux tests de `exportAwareToken.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test } from "vitest";
import { buildExportAwareToken, EXPORT_TOKEN_STORAGE_KEY, readExportToken } from "./exportAwareToken";

afterEach(() => {
  window.sessionStorage.clear();
  window.history.pushState({}, "", "/");
});

test("uses the worker-injected token only in export render mode", () => {
  window.sessionStorage.setItem(EXPORT_TOKEN_STORAGE_KEY, "tok");
  window.history.pushState({}, "", "/maps/x?exportRender=1");
  expect(buildExportAwareToken(() => "oidc")()).toBe("tok");
});

test("ignores an exportToken query param (no login-CSRF through a link)", () => {
  window.history.pushState({}, "", "/maps/x?exportToken=attacker&exportRender=1");
  expect(readExportToken()).toBeNull();
  expect(buildExportAwareToken(() => "oidc")()).toBe("oidc");
});

test("ignores the stored token outside export render mode", () => {
  window.sessionStorage.setItem(EXPORT_TOKEN_STORAGE_KEY, "tok");
  window.history.pushState({}, "", "/maps/x");
  expect(buildExportAwareToken(() => "oidc")()).toBe("oidc");
});
```
Dans `RequireAuth.test.tsx:70`, remplacer la mise en place `?exportToken=` par `sessionStorage.setItem("gs_export_token","t")` + URL `?exportRender=1`, et ajouter un cas : `?exportToken=x` seul → `signIn` appelé.
- [ ] **Step 10: Implémenter** `exportAwareToken.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0

// AUD-024 : le worker d'export injecte son jeton dans sessionStorage (add_init_script
// Playwright) ; il n'est jamais lu depuis l'URL, sinon un lien piégé ferait opérer
// la session de la victime sous le compte de l'attaquant.
export const EXPORT_TOKEN_STORAGE_KEY = "gs_export_token";

export function readExportToken(): string | null {
  if (new URLSearchParams(window.location.search).get("exportRender") !== "1") return null;
  try {
    return window.sessionStorage.getItem(EXPORT_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function buildExportAwareToken(getAccessToken: () => string | undefined) {
  return () => readExportToken() ?? getAccessToken();
}
```
`RequireAuth.tsx` : `const hasExportToken = readExportToken() !== null;` (supprimer `useSearchParams` s'il n'a plus d'usage). `App.tsx` : `if (readExportToken() !== null) return undefined;`.
- [ ] **Step 11:** `cd shell && npx vitest run src/auth src/App.test.tsx && npm run lint && npm run build` → vert. `grep -rn "exportToken" shell/src shell/e2e` : plus aucune lecture du paramètre (les E2E qui le posaient passent à `sessionStorage` + `exportRender=1`).
- [ ] **Step 12: Commits** — `fix(core): le Chromium d'export ne joint plus le réseau interne (AUD-023)` puis `fix(auth): jeton d'export en lecture seule, hors URL, couvrant le rendu (AUD-024)`.

---

### Task 3: AUD-089 + AUD-066 — CSP dynamique robuste et complète, portée invité des couches de widget

**Files:**
- Modify: `core/app/security/csp_hosts.py:23-29`, `core/app/security/traefik_render.py`, `core/app/security/jobs.py:32-41`, `core/app/configs/guest_access.py:82-108`, `docker-compose.yml:1053`, `docker-compose.prod.yml:311`
- Test: `core/tests/test_security_csp_hosts.py`, `core/tests/test_security_jobs.py`, `core/tests/test_configs_guest_access.py`, `core/tests/test_deployability.py`

**Interfaces:**
- Produces: `_origin(url) -> str | None` qui renvoie `None` pour tout hôte hors `^[a-z0-9.-]+$` ou port invalide ; `render_dynamic_conf` rend **deux** middlewares Traefik : `csp-dynamic` (avec `frame-ancestors 'self'`) et `csp-dynamic-embed` (sans `frame-ancestors`, pour `/embed/`).

Jumelles : les 4 extracteurs (`extract_harvest_hosts`, `extract_config_external_hosts`, `extract_basemap_hosts`, `extract_extension_hosts`) passent tous par `_origin` → couverts par un seul correctif ; les deux overlays compose (`shell-embed`) ; Helm : `grep -rn "csp-dynamic" deploy/helm` (aucun résultat attendu ; sinon reporter le middleware embed).

- [ ] **Step 1: Tests** — ajouter à `test_security_csp_hosts.py` :

```python
import pytest

from app.security.csp_hosts import _origin, extract_config_external_hosts


@pytest.mark.parametrize(
    "url",
    ['https://a"b.example/x', "https://x:abc/", "https://x:99999/", "https://a b.example/",
     "https://a;b.example/", "https://évil.example/"],
)
def test_malformed_hosts_are_dropped_not_raised(url):
    assert _origin(url) is None


def test_valid_origin_keeps_port():
    assert _origin("https://tiles.example.org:8443/{z}/{x}/{y}.png") == "https://tiles.example.org:8443"


def test_one_bad_layer_does_not_hide_the_good_ones():
    body = {"layers": [
        {"kind": "raster", "url": "https://x:abc/{z}"},
        {"kind": "raster", "url": "https://ok.example/{z}"},
    ]}
    assert extract_config_external_hosts(body) == {"https://ok.example"}
```
Et à `test_security_jobs.py` :

```python
def test_rendered_conf_is_valid_yaml_with_two_middlewares_and_directives():
    import yaml

    from app.security.service import CspAllowlist
    from app.security.traefik_render import render_dynamic_conf

    allow = CspAllowlist(img_hosts={"https://t.example"}, connect_hosts={"https://t.example"}, script_hosts=set())
    doc = yaml.safe_load(render_dynamic_conf(allow, mode="enforce"))
    mws = doc["http"]["middlewares"]
    main = mws["csp-dynamic"]["headers"]["customResponseHeaders"]["Content-Security-Policy"]
    embed = mws["csp-dynamic-embed"]["headers"]["customResponseHeaders"]["Content-Security-Policy"]
    for directive in ("base-uri 'self'", "form-action 'self'"):
        assert directive in main and directive in embed
    assert "frame-ancestors 'self'" in main
    assert "frame-ancestors" not in embed
```
(Vérifier le nom/l'import réel de `CspAllowlist` dans `security/service.py` ou `csp_hosts.py` avant d'écrire.)
- [ ] **Step 2:** lancer → FAIL.
- [ ] **Step 3: Implémenter** `csp_hosts.py:_origin` :

```python
_HOST_RE = re.compile(r"^[a-z0-9.-]+$")


def _origin(url: str | None) -> str | None:
    """Origine sûre à insérer dans la CSP, ou None (entrée ignorée, jamais levée :
    un seul enregistrement piégé ne doit pas figer la CSP de l'instance, AUD-089)."""
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or not _HOST_RE.fullmatch(host):
        return None  # relative (proxy interne), schéma non pertinent ou hôte malformé
    try:
        port = parsed.port
    except ValueError:
        return None
    return f"{parsed.scheme}://{host}" + (f":{port}" if port else "")
```
(`import re`.) `traefik_render.py` : `_build_csp_value(allowlist, *, frame_ancestors: bool)` ajoute `"base-uri 'self'; form-action 'self'; "` toujours et `"frame-ancestors 'self'; "` si `frame_ancestors` ; `render_dynamic_conf` émet les valeurs via `json.dumps` (une chaîne JSON est un scalaire YAML double-quoté valide) :

```python
def render_dynamic_conf(allowlist: CspAllowlist, *, mode: str) -> str:
    if mode not in _HEADER_NAMES:
        raise ValueError(f"mode CSP inconnu : {mode!r}")
    header = json.dumps(_HEADER_NAMES[mode])
    lines = ["http:", "  middlewares:"]
    for name, frame in (("csp-dynamic", True), ("csp-dynamic-embed", False)):
        value = json.dumps(_build_csp_value(allowlist, frame_ancestors=frame))
        lines += [f"    {name}:", "      headers:", "        customResponseHeaders:",
                  f"          {header}: {value}"]
    return "\n".join(lines) + "\n"
```
Corriger la docstring l.8-11. `security/jobs.py` : écriture atomique (`tmp = CSP_DYNAMIC_CONF_PATH + ".tmp"`, écrire, `os.replace(tmp, CSP_DYNAMIC_CONF_PATH)`) et corriger le message de log (« script-src enforcé si mode=enforce »).
- [ ] **Step 4: Compose** — `docker-compose.yml:1053` et `docker-compose.prod.yml:311` : remplacer `csp-dynamic@file` par `csp-dynamic-embed@file` sur le routeur `shell-embed` uniquement. Test dans `test_deployability.py` (suivre le patron des règles existantes qui lisent les labels du compose résolu) : le routeur `shell-embed` référence `csp-dynamic-embed@file` et aucun autre routeur ne le référence.
- [ ] **Step 5:** `uv run pytest tests/test_security_csp_hosts.py tests/test_security_jobs.py tests/test_security_service.py tests/test_basemaps_routes.py tests/test_deployability.py -q` → PASS.
- [ ] **Step 6: Test portée invité (AUD-066)** — dans `test_configs_guest_access.py`, en copiant le montage de `test_resolve_guest_scope` « direct layers » (l.109) : une app sans `dataSources` mais dont un widget `map` porte `props.layers=[{"id":"l","title":"t","kind":"vector","collectionId":"col-x"}]`, et un second widget carte **imbriqué** dans `props.items` d'une modale avec `collectionId="col-y"` → `scope.allowed_collection_ids >= {"col-x","col-y"}`.
- [ ] **Step 7: Implémenter** dans `resolve_guest_scope`, après la boucle `dataSources` :

```python
    # AUD-066 : couches additionnelles des widgets carte (imbriqués compris) ; la
    # lecture reste recoupée par can(created_by) côté collections (routes.py:392).
    for node in widget_nodes(root.config.model_dump(mode="json")):
        for layer in (node.get("props") or {}).get("layers") or []:
            if isinstance(layer, dict) and isinstance(layer.get("collectionId"), str):
                allowed_collection_ids.add(layer["collectionId"])
```
(`from app.configs.document_validation import widget_nodes`.) → PASS ; `uv run pytest tests -k "guest_access" -q`.
- [ ] **Step 8: Commits** — `fix(core): CSP dynamique robuste aux hôtes malformés, base-uri/form-action/frame-ancestors (AUD-089)` puis `fix(core): portée invité étendue aux couches des widgets carte (AUD-066)`.

---

### Task 4: AUD-050 + AUD-064 + AUD-108 — popups, bouton et extensions sans injection

**Files:**
- Modify: `shell/src/builder/widgets/sanitizeMarkdown.ts`, `shell/src/map/popupTemplate.ts:78-102`, `shell/src/builder/widgets/index.tsx:188-192`, `core/app/configs/document_validation.py` (`document_warnings`), `core/app/configs/extension_permissions.py`
- Test: `shell/src/map/popupTemplate.test.ts`, `shell/src/builder/widgets/sanitizeMarkdown.test.ts`, `shell/src/builder/widgets/index.test.tsx` (ou le fichier de test existant du bouton : `grep -ln "Bouton" shell/src/builder/widgets/*.test.tsx`), `core/tests/test_document_validation.py` (nom réel : `ls core/tests | grep document_validation`), `core/tests/test_configs_extension_permissions.py`

**Interfaces:**
- Produces: `renderMarkdownWithValues(markdown: string, values: string[]): string` (dans `sanitizeMarkdown.ts`, seul fichier autorisé à appeler `marked.parse`) ; `interpolatePopupTemplate(template, ctx, wrap?: (value: string) => string)` (comportement par défaut inchangé pour `labelSource`/`EntityFiche`) ; `_widget_href_errors(config_dict: dict) -> list[str]`.

Conception AUD-050 : les valeurs `record.*` ne sont plus du markdown. On interpole des jetons opaques, on rend le markdown **du gabarit**, puis on remplace chaque jeton par la valeur échappée en HTML, et DOMPurify passe en dernier (un lien d'auteur `[voir](${record.url})` reste fonctionnel, son schéma reste filtré). Jumelles : `RichSection` (même `sanitizeMarkdown`, reçoit le hook `rel`/`target`), `hero.tsx` (déjà gardé), image `src` (exposition = pistage seulement, non traité), MCP `save_app_config` (passe par `validate_document` : couvert).

- [ ] **Step 1: Tests shell** — ajouter à `popupTemplate.test.ts` :

```ts
test("a property value cannot inject a markdown link or image", () => {
  const html = renderPopupTemplate(
    "**Nom** ${record.nom}",
    ctx({ nom: "[Réclamer](https://evil.example) ![](https://evil.example/p.gif)" }),
  );
  expect(html).not.toContain("<a");
  expect(html).not.toContain("<img");
  expect(html).toContain("[Réclamer](https://evil.example)");
});

test("an author link built from a value still works, scheme still filtered", () => {
  expect(renderPopupTemplate("[voir](${record.url})", ctx({ url: "https://ok.example/a" }))).toContain(
    'href="https://ok.example/a"',
  );
  expect(renderPopupTemplate("[voir](${record.url})", ctx({ url: "javascript:alert(1)" }))).not.toContain(
    "javascript:",
  );
});
```
Et à `sanitizeMarkdown.test.ts` :

```ts
test("links open in a new tab without opener nor referrer", () => {
  const html = sanitizeMarkdown("[x](https://ok.example)");
  expect(html).toContain('rel="noopener noreferrer"');
  expect(html).toContain('target="_blank"');
});
```
Test du bouton (copier le montage de `hero.test.tsx:83` « javascript: ctaHref does not open a window » en remplaçant le widget `hero`/`ctaHref` par `button`/`href`) : `href: "javascript:alert(1)"` → `window.open` non appelé ; `href: "/apps/x"` → appelé.
- [ ] **Step 2:** `cd shell && npx vitest run src/map/popupTemplate.test.ts src/builder/widgets` → FAIL.
- [ ] **Step 3: Implémenter** `sanitizeMarkdown.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { marked } from "marked";
import DOMPurify from "dompurify";

// AUD-050 : tout lien rendu ouvre un nouvel onglet sans opener ni referrer.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.hasAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// Single, non-bypassable path from author-supplied Markdown to inserted DOM (…commentaire existant…).
export function sanitizeMarkdown(markdown: string): string {
  const html = marked.parse(markdown, { async: false }) as string;
  return DOMPurify.sanitize(html);
}

/** Gabarit d'auteur contenant des jetons `gspv<N>x` : le markdown est celui de
 * l'auteur seul ; chaque jeton devient la valeur échappée (texte ou attribut),
 * puis DOMPurify filtre le tout (schémas d'URL compris). */
export function renderMarkdownWithValues(markdown: string, values: string[]): string {
  const html = marked.parse(markdown, { async: false }) as string;
  const filled = html.replace(/gspv(\d+)x/g, (_, i: string) => escapeHtml(values[Number(i)] ?? ""));
  return DOMPurify.sanitize(filled);
}
```
`popupTemplate.ts` : ajouter le paramètre optionnel `wrap` à `interpolatePopupTemplate` (`out += wrap ? wrap(value) : value;` où `value = stringify(evaluateExpression(...))`), mettre à jour l'en-tête (l.5-16 : « on interpole des jetons, la valeur n'est jamais du markdown ») et :

```ts
export function renderPopupTemplate(template: string, ctx: ExprContext): string {
  const values: string[] = [];
  const markdown = interpolatePopupTemplate(template, ctx, (v) => {
    values.push(v);
    return `gspv${values.length - 1}x`;
  });
  return renderMarkdownWithValues(markdown, values);
}
```
`index.tsx` (bouton) : `import { isSafeHref } from "./hero";` et `if (href && isSafeHref(href)) window.open(href, "_blank", "noopener");`.
- [ ] **Step 4:** vitest des fichiers touchés + `src/map` → PASS ; `npm run lint && npm run build`.
- [ ] **Step 5: Test serveur des href** — dans le fichier de test de `document_validation` :

```python
import pytest
from fastapi import HTTPException

from app.configs.document_validation import _widget_href_errors


def test_widget_hrefs_must_be_http_mailto_or_relative():
    cfg = {"layout": {"items": [
        {"id": "b", "widget": "button", "props": {"href": "javascript:alert(1)"}},
        {"id": "m", "widget": "modal", "props": {"items": [
            {"id": "h", "widget": "hero", "props": {"ctaHref": "data:text/html,x"}}]}},
        {"id": "ok", "widget": "button", "props": {"href": "/apps/x"}},
        {"id": "e", "widget": "button", "props": {"href": {"$expr": "record.url"}}},
    ]}}
    errs = _widget_href_errors(cfg)
    assert len(errs) == 2 and "b.href" in errs[0] and "h.ctaHref" in errs[1]
```
- [ ] **Step 6: Implémenter** dans `document_validation.py` :

```python
_SAFE_HREF_SCHEMES = {"", "http", "https", "mailto"}


def _widget_href_errors(config_dict: dict) -> list[str]:
    """AUD-064 : jumeau serveur d'isSafeHref (hero.tsx). Une expression liée
    ($expr) est jugée au clic par isSafeHref, côté shell."""
    errs: list[str] = []
    for node in widget_nodes(config_dict):
        props = node.get("props") or {}
        for key in ("href", "ctaHref"):
            value = props.get(key)
            if isinstance(value, str) and value.strip():
                if urlparse(value.strip()).scheme.lower() not in _SAFE_HREF_SCHEMES:
                    errs.append(f"widget {node.get('id', '?')}.{key} must be an http(s), mailto or relative URL")
    return errs
```
Et dans `document_warnings` : `errs += _widget_href_errors(config.model_dump(mode="json"))` (avant le bloc `map`). → PASS ; `uv run pytest tests -k "document_validation or configs" -q`.
- [ ] **Step 7: Tests extensions (AUD-108)** — ajouter à `test_configs_extension_permissions.py`, en réutilisant son montage d'extension restreinte `collections=["a"]` : (a) widget d'extension portant `props.dataSourceId="ds_b"` (source `layer="b"`) sans prop `dataSource` déclarée → `ExtensionPermissionError` ; (b) même widget **imbriqué** dans `props.items` d'une modale avec la prop déclarée → erreur ; (c) source `datasetId` d'un dataset dont `collectionId="b"` → erreur ; (d) valeur `{"$expr": "..."}` → erreur ; (e) source `static` → accepté.
- [ ] **Step 8: Implémenter** dans `extension_permissions.py` (remplacer `_all_layout_items` et la boucle) :

```python
def _source_collection(session: Session, source) -> str | None:
    if source.layer:
        return source.layer
    if source.datasetId:
        cfg = configs_repo.get_config_by_item(session, source.datasetId)
        dataset = getattr(cfg.config, "dataset", None) if cfg is not None and cfg.kind == "dataset" else None
        if dataset is not None and dataset.source == "collection":
            return dataset.collectionId
    return None


def validate_extension_permissions(session, config, *, tenant_id) -> None:
    nodes = widget_nodes(config.model_dump(mode="json"))  # imbriqués compris (AUD-108)
    widget_types = {n["widget"] for n in nodes}
    # … chargement `extensions` inchangé …
    data_sources_by_id = {ds.id: ds for ds in config.dataSources}
    for node in nodes:
        ext = extensions.get(node["widget"])
        if ext is None:
            continue
        allowed = ext.permissions.get("collections", "all")
        if allowed == "all":
            continue
        props = node.get("props") or {}
        # dataSourceId est lu par WidgetHost quel que soit le manifeste (AUD-108).
        names = {p["name"] for p in ext.props if p["type"] == "dataSource"} | {"dataSourceId"}
        for prop_name in sorted(names):
            value = props.get(prop_name)
            if value in (None, ""):
                continue
            if not isinstance(value, str):
                raise ExtensionPermissionError(node["widget"], prop_name, "<expression>")
            source = data_sources_by_id.get(value)
            if source is not None and source.type == "static":
                continue
            collection = _source_collection(session, source) if source is not None else None
            if collection is None or collection not in allowed:
                raise ExtensionPermissionError(node["widget"], prop_name, collection or value)
```
(Imports : `widget_nodes` depuis `app.configs.document_validation`, `configs_repo` avec le même import que `guest_access.py`.) Mettre à jour `docs/guides/2026-07-13-ecrire-un-widget-web-component.md:101-111` : `permissions.collections` borne les sources passées au widget, ce n'est **pas** une sandbox (le code tiers peut appeler l'API avec la session).
- [ ] **Step 9:** `uv run pytest tests/test_configs_extension_permissions.py tests/test_mcp_tools_extension_permissions.py -q` → PASS.
- [ ] **Step 10: Commits** — `fix(shell): une valeur de donnée ne devient plus du markdown dans une popup (AUD-050)`, `fix(shell): le widget Bouton refuse les URL javascript:/data: (AUD-064)`, `fix(core): permissions d'extension vérifiées sur dataSourceId, imbriqués et datasets (AUD-108)`.

---

### Task 5: AUD-091 + AUD-096 + AUD-094 — clés à portée, groupes OIDC côté MCP, effacement qui coupe tout

**Files:**
- Create: `core/alembic/versions/0083_api_key_scopes.py`
- Modify: `core/app/apikeys/{models,schemas,service,routes}.py`, `core/app/users/models.py`, `core/app/roles/guards.py:12-14`, `core/app/auth/dependency.py` (branche clé + `forbid_api_key` déplacé), `core/app/mcp/tools/identity.py:64-77`, `core/app/compliance/{service,routes}.py`, `core/app/jobs/common.py:48-63`, `core/app/alerts/notify.py:45`, `core/app/pipelines/service.py:288-296`, `shell/src/api/domains/{identity,apiKeys}.ts`, `shell/src/api/itemClient.ts`, `shell/src/api/types.ts`, `shell/src/desktop/DesktopItemClient.ts`, `shell/src/staticExport/StaticItemClient.ts`, `shell/src/pages/{ComplianceAdminPage,UsersAdminPage,ApiKeysSection}.tsx`
- Test: `core/tests/test_api_keys.py`, `core/tests/test_migration_0083_api_key_scopes.py` (nouveau), `core/tests/test_mcp_identity_claims.py` (nouveau), `core/tests/test_compliance_service.py`, `core/tests/test_compliance_routes.py`, `shell/src/pages/ApiKeysSection.test.tsx`

**Interfaces:**
- Produces: colonnes `api_keys.scopes JSON NULL` (None = plafond = rôle du créateur, comportement historique) et `api_keys.read_only BOOLEAN NOT NULL DEFAULT false` ; attributs non persistés `User.api_key_scopes: frozenset[str] | None` et `User.api_key_read_only: bool` ; `ApiKeyCreate.scopes: list[str] | None`, `ApiKeyCreate.readOnly: bool` ; `ApiKeyRead.scopes`, `ApiKeyRead.readOnly` ; `app.auth.dependency.forbid_api_key` (déplacé, réexporté par `apikeys/routes.py`) ; `EraseRequest.confirmUsername: str` ; shell `eraseUser(userId: string, confirmUsername: string)`. **L9 consommera `ApiKey.scopes` pour le MCP.**

Jumelles AUD-094 (points de résolution d'identité) : `resolve_owner_user`, `alerts/notify.py:_owner_user`, branche export (fait en Task 2), branche clé (déjà gardée), déclencheur webhook (`pipelines/service.py:295`), liens de partage (révoqués). Jumelles `forbid_api_key` : effacement, création de lien de partage, création de jeton webhook de pipeline, rôles, rôle d'utilisateur.

- [ ] **Step 1: Tests clés** — ajouter à `test_api_keys.py` (fixture `env` et helpers `_get` existants ; étendre `_mint` avec `**kw` passés à `create_api_key`) :

```python
def test_scoped_key_is_capped_to_its_scopes(env):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id, scopes=["catalog.view"])
    # /v1/users exige admin.users.manage (cf. test_valid_key_acts_as_its_creator) : hors scope
    assert _get(client, token).status_code == 403


def test_read_only_key_refuses_writes(env):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id, read_only=True)
    assert _get(client, token).status_code == 200
    resp = client.post("/v1/api-keys", json={"name": "x"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_scopes_cannot_exceed_creator_privileges(env):
    client, Session, (_, _, reader_id) = env
    import pytest

    with pytest.raises(PermissionError):
        _mint(Session, reader_id, scopes=["admin.users.manage"])
```
(Vérifier les valeurs réelles de privilège dans `app/roles/privileges.py` — `catalog.view` est un exemple à remplacer par un privilège de lecture existant que le rôle Administrateur possède.)
- [ ] **Step 2:** lancer → FAIL.
- [ ] **Step 3: Migration** `0083_api_key_scopes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-091 : portée et mode lecture seule des clés d'API."""

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("scopes", sa.JSON(), nullable=True))
    op.add_column(
        "api_keys", sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("api_keys", "read_only")
    op.drop_column("api_keys", "scopes")
```
(Vérifier le format `revision` réel de `0082_pipeline_run_heartbeat.py` et s'y conformer.) Modèle : `scopes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)` ; `read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())`.
`users/models.py`, dans `User`, attributs de classe **non annotés** (ignorés par le mapping déclaratif) :

```python
    # AUD-091 : plafond posé par une clé d'API pour la requête en cours ; non persisté,
    # porté par l'instance de la session de la requête (lu par has_privilege).
    api_key_scopes = None  # frozenset[str] | None
    api_key_read_only = False
```
`roles/guards.py` :

```python
def has_privilege(session: Session, user: User, privilege: str) -> bool:
    scopes = getattr(user, "api_key_scopes", None)
    if scopes is not None and privilege not in scopes:
        return False
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    return role is not None and privilege in role.privileges
```
`apikeys/service.py` : `create_api_key(..., scopes: list[str] | None = None, read_only: bool = False)` — refuser un privilège inconnu (`ValueError`) ou non détenu par le créateur (`PermissionError`, via `has_privilege(session, user, p)` appelé **avant** de poser quoi que ce soit) ; persister ; ajouter `scopes`/`readOnly` au payload d'audit. Dans `authenticate`, avant `return user` :

```python
    user.api_key_scopes = frozenset(key.scopes) if key.scopes is not None else None
    user.api_key_read_only = key.read_only
```
Schémas : `scopes: list[str] | None = Field(default=None, max_length=50)`, `readOnly: bool = False` sur `ApiKeyCreate` ; `scopes: list[str] | None`, `readOnly: bool` sur `ApiKeyRead`. Route de création : `ValueError` → 422, `PermissionError` → 403. Rendre l'expiration par défaut inchangée (90 j, déjà).
`dependency.py`, branche clé :

```python
    if api_key_service.is_api_key(token):
        api_user = api_key_service.authenticate(session, token=token, tenant_id=tenant.id)
        if api_user is None:
            raise HTTPException(status_code=401, detail="invalid api key")
        if api_user.api_key_read_only and request.method not in {"GET", "HEAD", "OPTIONS"}:
            raise HTTPException(status_code=403, detail="read-only api key")
        return api_user
```
Déplacer `forbid_api_key` de `apikeys/routes.py` vers `auth/dependency.py` (même corps) et l'importer dans `apikeys/routes.py`.
- [ ] **Step 4:** tests de Step 1 + `uv run pytest tests/test_api_keys.py tests/test_apikeys_admin.py tests/test_roles* -q` → PASS.
- [ ] **Step 5: Migration sur base non vide** — `test_migration_0083_api_key_scopes.py`, patron `test_migration_0081_geocode_jobs.py` : base à `0082` avec une ligne `api_keys`, `upgrade` → `scopes IS NULL`, `read_only = false` ; `downgrade` → colonnes absentes, ligne intacte. Lancer avec `CORE_TEST_DATABASE_URL` (base dédiée) ; comparateur modèle↔Alembic : `uv run pytest tests -k "alembic or model_matches" -q`.
- [ ] **Step 6: AUD-096** — `test_mcp_identity_claims.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

from app.mcp.tools import identity


def test_resolve_actor_applies_oidc_group_claims(monkeypatch):
    seen = {}
    user = SimpleNamespace(id="u1", tenant_id="t1")
    monkeypatch.setattr(identity, "get_or_create_default_tenant", lambda s: SimpleNamespace(id="t1"))
    monkeypatch.setattr(identity, "get_or_create_user", lambda s, **kw: user)
    monkeypatch.setattr(
        identity, "apply_from_token_claims", lambda s, **kw: seen.update(kw)
    )
    token = SimpleNamespace(subject="sub", claims={"groups": ["/sig"], "preferred_username": "u"})
    assert identity.resolve_actor(object(), token) is user
    assert seen == {"tenant_id": "t1", "user_id": "u1", "claims": token.claims}
```
→ FAIL ; implémenter dans `resolve_actor` : stocker le résultat de `get_or_create_user` dans `user`, puis `apply_from_token_claims(session, tenant_id=tenant.id, user_id=user.id, claims=claims)` (ne lève jamais) et `return user` (`from app.sharing.claim_sync import apply_from_token_claims`) → PASS.
- [ ] **Step 7: Tests effacement** — ajouter à `test_compliance_service.py` (patron de `test_preserves_owned_objects`, l.138) : après `anonymize_user`, (a) les `PipelineWebhookToken` créés par l'utilisateur n'existent plus ; (b) ses `ShareLink` ont `revoked_at` non nul ; (c) `resolve_owner_user(session, tenant_id=..., item_id=<item de l'utilisateur>)` lève `LookupError`. À `test_compliance_routes.py` : `POST .../erase` sans corps → 422 ; avec `{"confirmUsername": "mauvais"}` → 409 ; avec le bon nom → 204 (adapter les 6 tests existants qui postent sans corps) ; via une clé `gsk_` (montage `_mint` de `test_api_keys.py`) → 403.
- [ ] **Step 8: Implémenter** :
  - `jobs/common.py:resolve_owner_user` : remplacer `assert user is not None` par
    ```python
    if user is None or user.erased_at is not None:
        # AUD-094 : un compte effacé n'agit plus (cron, alertes, rapports, webhook).
        raise LookupError(f"owner of item '{item_id}' is unavailable")
    ```
  - `alerts/notify.py:_owner_user` (l.45, renvoie `User | None`) : renvoyer `None` si `erased_at` posé.
  - `pipelines/service.py` autour de l.295 (déclencheur webhook) : si `resolve_owner_user` n'est pas déjà dans un `except LookupError`, l'envelopper : `except LookupError as exc: raise HTTPException(status_code=410, detail="pipeline owner account erased") from exc`.
  - `compliance/service.py:anonymize_user`, après `revoke_all_for_user` :
    ```python
    session.execute(delete(PipelineWebhookToken).where(PipelineWebhookToken.created_by == user_id))
    session.execute(
        update(ShareLink)
        .where(ShareLink.created_by == user_id, ShareLink.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    ```
    (imports `PipelineWebhookToken` de `app.pipelines.models`, `ShareLink` de `app.sharing.models` ; si `lint-imports` refuse, suivre le précédent `compliance/purge.py` qui importe déjà des modèles d'autres domaines.)
  - `compliance/routes.py` : `class EraseRequest(BaseModel): confirmUsername: str = Field(min_length=1)` ; la route prend `body: EraseRequest` et `dependencies=[Depends(forbid_api_key)]` ; après la résolution de `target_id` et le contrôle de privilège : charger la cible (`session.get(User, target_id)`, 404 si absente ou autre tenant) et `if body.confirmUsername != target.username: raise HTTPException(409, "confirmation username does not match")`.
  - `forbid_api_key` sur les jumelles : `grep -n "share-links\|webhook-token\|webhook_token\|@router.\(post\|put\|patch\|delete\)" core/app/items/routes.py core/app/pipelines/routes.py core/app/roles/routes.py core/app/users/routes.py` puis ajouter `dependencies=[Depends(forbid_api_key)]` à : `POST /items/{id}/share-links`, la création de jeton webhook de pipeline, `POST/PATCH/DELETE /roles…`, `PUT /users/{id}/role`. Un test par route dans `test_api_keys.py` (clé admin → 403).
- [ ] **Step 9:** `uv run pytest tests -k "compliance or api_key or apikeys or webhook or share_link or roles or alert or report or pipeline_jobs" -q` → PASS.
- [ ] **Step 10: Shell** — `identity.ts` : `async eraseUser(userId: string, confirmUsername: string) { await request<void>("POST", \`/compliance/users/${userId}/erase\`, { confirmUsername }); }` ; même signature dans l'interface `ItemClient` (`itemClient.ts`), `DesktopItemClient.ts`, `StaticItemClient.ts` ; `grep -rn "eraseUser(" shell/src` et passer le nom affiché (`username`) depuis `ComplianceAdminPage.tsx`/`UsersAdminPage.tsx` (et la page de paramètres si elle efface « me »). `apiKeys.ts` : `createApiKey(input: { name: string; expiresInDays?: number; readOnly?: boolean })` ; `ApiKeysSection.tsx` : case « Lecture seule » (`<label><input type="checkbox">…`, clé i18n dans le catalogue du domaine) et colonne « Lecture seule » ; test vitest de la case. La saisie de `scopes` dans l'UI est un reliquat (consigné en clôture), l'API l'accepte.
- [ ] **Step 11:** régénérer OpenAPI + types TS (incantation des Global Constraints) ; `npx vitest run src/pages src/api && npm run lint && npm run build` → vert ; `git diff --stat shell/src/api/generated` non vide (attendu).
- [ ] **Step 12: Commits** — `feat(core): clés d'API à portée et en lecture seule (AUD-091)`, `fix(core): le MCP applique la synchro de groupes OIDC (AUD-096)`, `fix(core): un compte effacé ne garde ni jeton, ni lien, ni exécution planifiée (AUD-094)`, `feat(shell): confirmation d'effacement et clé en lecture seule`.

---

### Task 6: AUD-090 + AUD-153 + AUD-154 — plafonds de corps et de téléversement, soumission publique bornée

**Files:**
- Modify: `core/app/main.py` (`config_body_limit` l.310-335 → middleware à table), `core/app/ratelimit/limiter.py` (`route_group`, `caller_key`, `_BUDGETS`), `core/app/public_submit/{routes,service}.py`, `core/app/ingestion/{storage,schemas,routes}.py`, `core/app/raster/{schemas,routes}.py`, `core/app/terrain3d/{schemas,routes}.py`, `core/app/attachments/{schemas,routes}.py`, `docs/adr/0017-soumission-publique-moderee.md:16`, shell : `src/api/domains/{exportsIngestion,raster,tiles3d,attachments}.ts`, `src/api/itemClient.ts`, `src/desktop/DesktopItemClient.ts`, `src/staticExport/StaticItemClient.ts` et leurs appelants
- Test: `core/tests/test_body_limits.py` (nouveau), `core/tests/test_ratelimit.py`, `core/tests/test_presign_size.py` (nouveau), `core/tests/test_public_submit*.py` (existants)

**Interfaces:**
- Produces: `_BODY_LIMITS: list[tuple[re.Pattern[str], int]]` dans `main.py` ; groupe de limite `"public-submit"` (20/min) ; `ip_bucket(host: str | None) -> str` (IPv6 ramenée au /64) dans `limiter.py`, utilisé par `caller_key` ; `service.token_limiter = HourlyLimiter(100)` ; `generate_presigned_put_url(..., content_length: int)` ; champ `size: int` (requis) sur les 4 requêtes de présignature ; shell : `presignUpload(filename, contentType, size)`, `presignTerrain3DUpload(filename, contentType, size)`, `presignAttachmentUpload(collectionId, fid, { fieldKey, filename, contentType, size })`, idem raster.

Jumelles : 4 routes de présignature (ingestion, raster, terrain3d, attachments ; `tileset3d` = multipart S3 par parties, hors périmètre, à consigner) ; plafonds `config` et `public/submit` dans le même middleware.

- [ ] **Step 1: Test plafond de corps** — `core/tests/test_body_limits.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-153 : le corps d'une soumission publique est refusé AVANT le parsing multipart."""

from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_ENV", "development")
    return TestClient(create_app())


def test_oversized_public_submit_is_413_before_parsing(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/v1/public/submit/gss_bidon",
        content=b"x" * 10,
        headers={"Content-Length": str(30 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=b"},
    )
    assert resp.status_code == 413


def test_public_submit_without_length_is_411(monkeypatch):
    client = _client(monkeypatch)

    def gen():
        yield b"--b--"

    resp = client.post("/v1/public/submit/gss_bidon", content=gen(),
                       headers={"Content-Type": "multipart/form-data; boundary=b"})
    assert resp.status_code == 411
```
(Patron de montage : `tests/test_ratelimit.py:_client`, l.14-28 — reprendre ses variables d'environnement exactes.)
- [ ] **Step 2:** lancer → FAIL.
- [ ] **Step 3: Implémenter** dans `main.py` : remplacer `config_body_limit` par

```python
_PUBLIC_SUBMIT_PATH_RE = re.compile(r"^/v1/public/submit/[^/]+$")
# AUD-153 : pièce jointe (25 Mo) + charge GeoJSON (64 Ko) + enveloppe multipart.
MAX_PUBLIC_SUBMIT_BODY_BYTES = 26 * 1024 * 1024
_BODY_LIMITS = [
    (_CONFIG_WRITE_PATH_RE, MAX_CONFIG_BODY_BYTES, "config"),
    (_PUBLIC_SUBMIT_PATH_RE, MAX_PUBLIC_SUBMIT_BODY_BYTES, "submission"),
]

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        # P09.07 (t02-001) + AUD-153 : plafond lu sur Content-Length, avant tout parsing.
        if request.method in {"POST", "PUT"}:
            for pattern, max_bytes, label in _BODY_LIMITS:
                if not pattern.match(request.url.path):
                    continue
                length = request.headers.get("content-length")
                if length is None or not length.isdigit():
                    status, detail = 411, "Content-Length required"
                elif int(length) > max_bytes:
                    status, detail = 413, f"{label} too large (max {max_bytes} bytes)"
                else:
                    break
                return JSONResponse(
                    status_code=status,
                    media_type="application/problem+json",
                    content={"type": "about:blank", "title": HTTPStatus(status).phrase,
                             "status": status, "detail": detail},
                )
        return await call_next(request)
```
(L'ordre d'enregistrement reste celui de `config_body_limit` : `rate_limit_guard` s'exécute avant.) → PASS ; `uv run pytest tests -k "config_body or body_limit" -q`.
- [ ] **Step 4: Tests budget public** — ajouter à `test_ratelimit.py` :

```python
def test_public_submit_has_its_own_budget_and_ipv6_is_bucketed():
    from app.ratelimit.limiter import _BUDGETS, caller_key, ip_bucket

    assert route_group("/v1/public/submit/gss_x", "POST", _EXPORT_PATH_RE) == "public-submit"
    assert route_group("/v1/public/submit/gss_x", "GET", _EXPORT_PATH_RE) is None
    assert _BUDGETS["public-submit"] == 20
    assert ip_bucket("2001:db8:1:2:aaaa::1") == ip_bucket("2001:db8:1:2:bbbb::9") == "2001:db8:1:2::/64"
    assert ip_bucket("203.0.113.7") == "203.0.113.7"
    assert caller_key(None, "2001:db8:1:2::5", "public-submit") == "submit:2001:db8:1:2::/64"
```
Et dans les tests `public_submit` (fichier existant de routes : `ls core/tests | grep public_submit`) : 101e soumission du **même jeton** depuis 101 IP différentes → 429 (`service.token_limiter.reset()` en fixture, comme `ip_limiter.reset()`).
- [ ] **Step 5: Implémenter** `limiter.py` :

```python
_PUBLIC_SUBMIT_RE = re.compile(r"^/v1/public/submit/[^/]+$")


def ip_bucket(host: str | None) -> str:
    """AUD-154 : une IPv6 compte pour son /64 (un abonné en a des milliards)."""
    if not host:
        return "unknown"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host
    if ip.version == 6 and ip.ipv4_mapped is None:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip.ipv4_mapped or ip)
```
`_BUDGETS["public-submit"] = 20` ; dans `route_group`, avant le `REV-299` : `if method == "POST" and _PUBLIC_SUBMIT_RE.match(path): return "public-submit"` ; dans `caller_key` : `bucket = ip_bucket(client_host)` puis `if group == "public-submit": return f"submit:{bucket}"` et utiliser `bucket` à la place de `client_host or 'unknown'` dans les branches `trigger`, `share`, `anon`. `public_submit/service.py` : `token_limiter = HourlyLimiter(100)` à côté de `ip_limiter` (commentaire `ponytail:` : compteurs horaires par process ; le budget par minute partagé est dans `PgRateLimiter`) ; `routes.py:submit` : `ip = ip_bucket(request.client.host if request.client else None)` puis, après le test IP, `if not service.token_limiter.allow(token): raise HTTPException(429, "too many submissions for this form, retry later")`. ADR 0017:16 : préciser « par IP (/64 en IPv6) et par jeton, compteur horaire par process + budget par minute partagé ».
- [ ] **Step 6:** `uv run pytest tests/test_ratelimit*.py tests -k public_submit -q` → PASS.
- [ ] **Step 7: Test présignature** — `core/tests/test_presign_size.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-090 : l'URL présignée fige la taille annoncée (S3 refuse tout autre Content-Length)."""

from urllib.parse import parse_qs, urlparse

from app.ingestion.storage import generate_presigned_put_url, make_s3_client


def test_presigned_put_signs_content_length():
    client = make_s3_client(endpoint_url="http://minio:9000", access_key="a", secret_key="b")
    url = generate_presigned_put_url(
        client, bucket="b", key="k", content_type="text/csv", content_length=123
    )
    signed = parse_qs(urlparse(url).query)["X-Amz-SignedHeaders"][0].split(";")
    assert "content-length" in signed
```
Plus, par route (ingestion, raster, terrain3d, attachments), un test « `size` > plafond → 413 » et « `size` absent → 422 » en réutilisant le montage existant du test de présignature de chaque domaine (`grep -ln "presign" core/tests`).
- [ ] **Step 8: Implémenter** :
  - `storage.py:make_s3_client` : `config=Config(signature_version="s3v4")` (`from botocore.config import Config`) — mesuré : sans cela boto3 signe en SigV2 et `Content-Length` n'est pas signé. Vérifier ensuite `uv run pytest tests -k "s3 or presign or storage" -q` (les URL changent de forme, les tests qui parsent `Signature=` sont à adapter).
  - `generate_presigned_put_url(client, *, bucket, key, content_type, content_length: int, expires_in=900)` : `Params={"Bucket": bucket, "Key": key, "ContentType": content_type, "ContentLength": content_length}`.
  - Schémas : `size: int = Field(ge=1)` sur `PresignRequest`, `RasterPresignRequest`, `Terrain3DPresignRequest`, `AttachmentPresignRequest`.
  - Routes : ingestion `if body.size > max_upload_bytes(): raise HTTPException(413, ...)` ; raster `_max_upload_bytes()` de `raster/jobs.py` ; terrain3d `_max_upload_bytes()` de `terrain3d/jobs.py` ; attachments `MAX_ATTACHMENT_BYTES` ; chaque appel passe `content_length=body.size`.
- [ ] **Step 9: Shell** — ajouter `size` (= `file.size`) aux 4 méthodes de présignature (`exportsIngestion.ts:81`, `tiles3d.ts:47`, `attachments.ts:19`, `raster.ts` : `grep -n presign shell/src/api/domains/raster.ts`), à l'interface `ItemClient` et aux deux implémentations alternatives ; mettre à jour les appelants (`ImportFileButton.tsx`, `RasterUploadButton.tsx`, `Terrain3DUploadButton.tsx`, `builder/widgets/form.tsx`, `map/LayersPanel.tsx`, `builder/widgets/mapWidget.tsx` : `grep -rn "presign" shell/src --include=*.tsx`) et leurs tests/mocks (`shell/e2e/mocks.ts` si les corps sont vérifiés). Le `fetch(PUT, body: file)` envoie déjà `Content-Length = file.size`.
- [ ] **Step 10:** régénérer OpenAPI + types TS ; `uv run pytest tests -k "presign or upload or attachment or raster or terrain3d or ingestion" -q` ; `cd shell && npx vitest run src/api src/shell src/map src/builder/widgets && npm run lint && npm run build` → vert.
- [ ] **Step 11: Commits** — `fix(core): plafond de corps et budget avant parsing sur la soumission publique (AUD-153)`, `fix(core): limite par jeton et IPv6 au /64 pour la soumission publique (AUD-154)`, `fix(core): l'URL présignée fige la taille du téléversement (AUD-090)`.

---

### Task 7: AUD-155 + AUD-156 + AUD-157 + AUD-101 — budgets des lectures coûteuses et du proxy

**Files:**
- Modify: `core/app/ratelimit/limiter.py`, `core/app/ows/routes.py:221-230`, `core/app/ows/wms_routes.py` (GetMap), `core/app/geocoding/{routes,jobs}.py`, `core/app/raster/{zonal,routes}.py`, `core/app/main.py:605` (commentaire), `docker-compose.yml:449-451`, `deploy/helm/geostudio/values.yaml:118` (commentaire), `core/tests/test_deployability.py`
- Test: `core/tests/test_ratelimit.py`, `core/tests/test_geocode_jobs.py`, `core/tests/test_geocoding_routes.py`, `core/tests/test_raster_zonal*.py` (`ls core/tests | grep zonal`), tests WFS existants (`ls core/tests | grep -i wfs`)

**Interfaces:**
- Produces: groupes `"ogc-read"` (600/min) et `"zonal"` (10/min) ; `_GEOCODE_RE` couvrant `POST /v1/geocode/jobs` ; `MAX_ACTIVE_JOBS_PER_USER = 3` et `RETENTION_DAYS = 7` dans `geocoding/jobs.py` ; `purge_finished_jobs(session, *, now: datetime) -> int` ; `MAX_WINDOW_PIXELS = 16_000_000` et `_ZONAL_SLOTS` dans `raster/zonal.py` ; `_RENDER_SLOTS` dans `wms_routes.py`.

Jumelles : WMS (`wms_routes.py`, déjà sous `statement_timeout`) ↔ WFS ; tuiles raster ↔ terrain3d ; `/batch` ↔ `/jobs` du géocodage ; STAC/DCAT anonymes (d16 #4) **hors lot** (pas dans la liste AUD de L2 : à consigner pour L4/L6).

- [ ] **Step 1: Tests** — ajouter à `test_ratelimit.py` :

```python
def test_costly_reads_and_jobs_have_budgets():
    from app.ratelimit.limiter import _BUDGETS

    assert route_group("/v1/ows/wms", "GET", _EXPORT_PATH_RE) == "ogc-read"
    assert route_group("/v1/ows/wfs", "GET", _EXPORT_PATH_RE) == "ogc-read"
    assert route_group("/v1/raster/i/tiles/1/2/3", "GET", _EXPORT_PATH_RE) == "ogc-read"
    assert route_group("/v1/terrain3d/i/tiles/1/2/3.png", "GET", _EXPORT_PATH_RE) == "ogc-read"
    assert route_group("/v1/collections/c/tiles/WebMercatorQuad/1/2/3", "GET", _EXPORT_PATH_RE) is None
    assert route_group("/v1/raster/i/zonal-stats", "POST", _EXPORT_PATH_RE) == "zonal"
    assert route_group("/v1/geocode/jobs", "POST", _EXPORT_PATH_RE) == "geocode"
    assert route_group("/v1/geocode/jobs/abc", "GET", _EXPORT_PATH_RE) is None
    assert _BUDGETS["ogc-read"] == 600 and _BUDGETS["zonal"] == 10
```
- [ ] **Step 2:** lancer → FAIL. **Implémenter** :

```python
_GEOCODE_RE = re.compile(r"^/v1/geocode(/batch|/reverse|/jobs)?$")
# AUD-155 : lectures anonymes coûteuses (rendu PIL, count exact, proxy TiTiler).
# ponytail: 600/min par appelant tolère un panoramique rapide ; à resserrer si la
# saturation est mesurée. Les tuiles vecteur du cœur restent hors budget (exclues à dessein).
_OGC_READ_RE = re.compile(r"^/v1/ows/|^/v1/(raster|terrain3d)/[^/]+/tiles/")
_ZONAL_RE = re.compile(r"^/v1/raster/[^/]+/zonal-stats$")
```
`_BUDGETS` : `"ogc-read": 600`, `"zonal": 10`. Dans `route_group`, avant le `REV-299` : `if method == "GET" and _OGC_READ_RE.match(path): return "ogc-read"` ; `if method == "POST" and _ZONAL_RE.match(path): return "zonal"` ; la branche géocodage devient `if _GEOCODE_RE.match(path) and (method != "GET" or not path.endswith("/jobs")): return "geocode"` (seul le POST `/jobs` est budgété ; le sondage `GET /jobs/{id}` ne matche pas la regex). → PASS.
- [ ] **Step 3: WFS `hits` borné** — test (patron des tests WFS existants) : avec `monkeypatch` sur `app.ows.routes.apply_tile_statement_timeout` (espion), `GET /v1/ows/wfs?...&resulttype=hits` appelle l'espion avec `5000` ; une `OperationalError` dont `orig.sqlstate == "57014"` levée par `select_features` → 503. Implémenter : avant le `with rls(...)` de `_get_feature` (l.221), `apply_tile_statement_timeout(session, 5000)` (import depuis `app.features.tiles`, comme `wms_routes.py`) ; capturer 57014 exactement comme `wms_routes._read` (l.139-157, recopier son `except`) → réponse d'exception OWS 503 « query timed out ».
- [ ] **Step 4: Concurrence de rendu WMS** — dans `wms_routes.py` : `_RENDER_SLOTS = threading.BoundedSemaphore(4)  # ponytail: par process` ; dans le handler GetMap, autour de l'appel de rendu : `if not _RENDER_SLOTS.acquire(timeout=5): raise _err("NoApplicableCode", "server busy", 503)` puis `try: … finally: _RENDER_SLOTS.release()`. Test : un sémaphore épuisé (`monkeypatch.setattr(wms_routes, "_RENDER_SLOTS", threading.BoundedSemaphore(0))` + `acquire(timeout=...)` court via monkeypatch d'une constante `_RENDER_WAIT_S = 5` → mettre `0.01`) → 503.
- [ ] **Step 5: Géocodage par lot (AUD-156)** — tests (`test_geocoding_routes.py` / `test_geocode_jobs.py`, patrons existants) : (a) 4e `POST /v1/geocode/jobs` d'un même utilisateur avec 3 jobs `pending|running` → 429 ; (b) `purge_finished_jobs` supprime un job `succeeded` mis à jour il y a 8 jours, garde un job `failed` d'il y a 2 jours et un `running` d'il y a 30 jours. Implémenter dans `geocoding/jobs.py` :

```python
MAX_ACTIVE_JOBS_PER_USER = 3
RETENTION_DAYS = 7  # adresses = donnée personnelle potentielle (AUD-156)


def count_active_jobs(session: Session, *, tenant_id: str, user_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(GeocodeJob).where(
            GeocodeJob.tenant_id == tenant_id,
            GeocodeJob.created_by == user_id,
            GeocodeJob.status.in_(("pending", "running")),
        )
    ) or 0


def purge_finished_jobs(session: Session, *, now: datetime) -> int:
    result = session.execute(
        delete(GeocodeJob).where(
            GeocodeJob.status.in_(("succeeded", "failed")),
            GeocodeJob.updated_at < now - timedelta(days=RETENTION_DAYS),
        )
    )
    return result.rowcount or 0
```
Dans `sweep_geocode_jobs_task`, dans le même `request_scoped_session` : `purged = purge_finished_jobs(session, now=_now())` (journaliser si > 0). Dans `create_geocode_job` (routes.py:122), avant `create_job` : `if geocode_jobs.count_active_jobs(session, tenant_id=user.tenant_id, user_id=user.id) >= geocode_jobs.MAX_ACTIVE_JOBS_PER_USER: raise HTTPException(429, "Trop de lots de géocodage en cours, réessayez plus tard.")`. Remplacer l'appel nu `run_geocode_job.defer(...)` par `defer_resilient(lambda: …)` de `app.jobs.defer` (SP-L1a) **seulement** si L1a ne l'a pas déjà fait (vérifier). Ajouter un commentaire `ponytail:` sur la réécriture complète de `results` par tranche (O(n²) borné par 5000 adresses × 100). Le privilège n'est pas ajouté : `GET /geocode` est ouvert à tout utilisateur connecté par conception, le budget + le plafond de jobs suffisent.
- [ ] **Step 6: Zonal stats (AUD-157)** — test : `zonal_stats` sur un faux raster dont `geometry_window` renvoie 20 M px → `ZonalError` ; la route avec `_ZONAL_SLOTS` épuisé → 503. Implémenter dans `raster/zonal.py` : `MAX_WINDOW_PIXELS = 16_000_000` (message « fenêtre > 16 M pixels ») et

```python
# AUD-157 : ~1,1 Go de RSS mesurés pour 49 M px float64 ; 16 M px × 2 calculs
# simultanés par process bornent la mémoire. ponytail: lecture par fenêtres avec
# accumulateurs si de plus gros polygones deviennent nécessaires.
_ZONAL_SLOTS = threading.BoundedSemaphore(2)
```
et dans la route (`raster/routes.py:303-307`) :

```python
    if not zonal._ZONAL_SLOTS.acquire(timeout=1):
        raise HTTPException(status_code=503, detail="calcul zonal saturé, réessayez")
    try:
        with opener(asset) as ds:
            stats = zonal.zonal_stats(ds, [g for _, g in polys], band=body.band, stats=body.stats)
    except zonal.ZonalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        zonal._ZONAL_SLOTS.release()
```
- [ ] **Step 7: AUD-101** — `docker-compose.yml:449-451` : `- "127.0.0.1:8200:8200"` (le shell de dev appelle `http://localhost:8200`, inchangé ; plus d'exposition sur le réseau local). Test dans `test_deployability.py` : dans le compose de base résolu, le port publié de `core` est lié à `127.0.0.1` ; dans `docker-compose.prod.yml`, `core` ne publie aucun port. Corriger `main.py:605` (« core:8000 » → « core:8200 ») et ajouter au commentaire de `CORE_TRUSTED_PROXIES` (`docker-compose.yml:420`, `.env.example:158`, Helm `values.yaml:118`) : « en production, restreindre au sous-réseau du reverse-proxy ; toute machine de cette plage peut forger X-Forwarded-For ». Limite assumée (à consigner) : en dev, un processus local passant par la passerelle Docker reste « de confiance ».
- [ ] **Step 8:** `uv run pytest tests/test_ratelimit*.py tests/test_deployability.py tests -k "geocod or zonal or wfs or wms or ows" -q` → PASS ; ruff, lint-imports.
- [ ] **Step 9: Commits** — `fix(core): budgets sur WMS/WFS/tuiles proxy et WFS hits borné (AUD-155)`, `fix(core): lots de géocodage budgétés, plafonnés et purgés (AUD-156)`, `fix(core): calcul zonal borné en mémoire et en concurrence (AUD-157)`, `fix(deploy): port du cœur lié à la boucle locale en dev (AUD-101)`.

---

### Task 8: AUD-152 + AUD-081 + AUD-100 — sorties CSV neutralisées, lecteurs SQL/Mongo durcis, erreurs internes masquées

**Files:**
- Create: `core/app/job_errors.py`
- Modify: `core/app/pipelines/ops/cloudfiles.py:856-864`, `core/app/pipelines/connector_runtime.py` (`_timeout_connect_args`, `_stream_sql`, 6 `materialize_*`), `core/app/analytics/sql_sandbox.py`, `core/app/pipelines/ops/dbio2.py:274-281`, `core/app/ingestion/tasks.py:223-244` et les jumelles listées dans « Faits vérifiés » (AUD-100)
- Test: `core/tests/test_pipeline_ops_cloudfiles.py`, `core/tests/test_pipeline_connector_runtime.py`, `core/tests/test_sql_sandbox*.py` (`ls core/tests | grep sandbox`), `core/tests/test_pipeline_ops_secretkinds.py`, `core/tests/test_job_errors.py` (nouveau), `core/tests/test_ingestion_tasks.py`

**Interfaces:**
- Produces: `app.job_errors.INTERNAL_ERROR_MESSAGE: str` ; `public_error(exc: BaseException, *, user_errors: tuple[type[BaseException], ...] = ()) -> str` ; `sql_sandbox.validate_external_select(ast: dict) -> None` ; `_stream_sql(dsn: str, query: str, *, expected_backend: str)`.

Jumelles AUD-152 : `writer.file` CSV via GDAL (`runtime.py:1435`, derrière `CORE_PIPELINE_FILE_IO_ENABLED=false`) : non neutralisable sans réécrire le chemin GDAL, à consigner. Jumelles AUD-081 : les 6 lecteurs SQL (`postgres`, `mssql`, `snowflake`, `oracle`, `databricks`, `bigquery`). Jumelles AUD-100 : liste complète de « Faits vérifiés » ; les messages des branches typées qui embarquent un texte GDAL (`raster/ingest.py:53,88`, `terrain3d/conversion.py:124`, `tileset3d/storage.py:78,109`) et le reçu de purge `compliance/jobs.py:62` (route admin) restent tels quels, à consigner.

- [ ] **Step 1: AUD-152, test** — ajouter à `test_pipeline_ops_cloudfiles.py` (test unitaire de `_serialize`, seul point de sérialisation de `write_ftp`) :

```python
def test_csv_serialization_neutralizes_formulas():
    import pandas as pd

    from app.pipelines.ops.cloudfiles import _serialize

    frame = pd.DataFrame({"=cmd": ['=HYPERLINK("http://evil","x")', "ok"], "n": [-5, 1]})
    lines = _serialize(frame, "csv").decode().splitlines()
    assert lines[0] == "'=cmd,n"
    assert lines[1].startswith('"\'=HYPERLINK(')
    assert lines[1].endswith(",-5")  # un nombre typé négatif reste numérique
    assert lines[2] == "ok,1"
```
Le test de bout en bout `test_ftp_writer_roundtrip_idempotent_and_audited` (l.509) doit rester vert sans modification.
- [ ] **Step 2:** → FAIL. **Implémenter** `_serialize` :

```python
    if fmt == "csv":
        # AUD-152 : même neutralisation que les autres sorties CSV (cell_safety).
        safe = frame.rename(columns=sanitize_cell).map(sanitize_cell)
        out.write(safe.to_csv(index=False).encode())
```
(`from app.cell_safety import sanitize_cell` ; pandas ≥ 2.1 fournit `DataFrame.map`, vérifier `uv run python -c "import pandas; print(pandas.__version__)"`.) → PASS.
- [ ] **Step 3: AUD-081, tests** — ajouter au test du sandbox :

```python
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError, parse_ast, validate_external_select


@pytest.mark.parametrize(
    "sql",
    ["SELECT pg_terminate_backend(1)", "SELECT pg_catalog.lo_export(1, 'x')",
     "SELECT nextval('s')", "SELECT set_config('a','b',false)", "SELECT pg_read_file('/etc/passwd')"],
)
def test_side_effect_functions_are_refused(sql):
    with pytest.raises(SqlSandboxError):
        validate_external_select(parse_ast(duckdb.connect(), sql))


def test_plain_select_still_passes():
    validate_external_select(parse_ast(duckdb.connect(), "SELECT upper(nom), count(*) FROM t GROUP BY 1"))
```
Et à `test_pipeline_connector_runtime.py` : (a) en reprenant le faux `create_engine` de `test_stream_sql_passes_hostaddr_pin_to_the_driver` (l.1812), `_stream_sql("postgresql://u:p@h/db", "SELECT 1", expected_backend="postgresql")` passe `"-c default_transaction_read_only=on"` dans `connect_args["options"]` ; (b) `_stream_sql("sqlite:////tmp/x.db", "SELECT 1", expected_backend="postgresql")` lève `ConnectorRuntimeError` **avant** `create_engine` ; (c) `materialize_postgres_connector` avec `SELECT pg_terminate_backend(1)` → `ConnectorRuntimeError` « rejected » (patron `rejects_non_select`, l.507). À `test_pipeline_ops_secretkinds.py` (fixture `mongo`) : filtre `{"_id": {"$oid": "6500aaaaaaaaaaaaaaaaaaaa"}}` → le `find_args` capturé contient un `bson.ObjectId` ; `{"d": {"$gte": {"$date": "2024-01-01T00:00:00Z"}}}` → un `datetime`.
- [ ] **Step 4:** → FAIL. **Implémenter** :
  - `sql_sandbox.py` :
    ```python
    # AUD-081 : fonctions à effet de bord qu'une requête « SELECT » peut appeler sur
    # une base distante (le type du nœud racine ne suffit pas).
    _FORBIDDEN_FUNCTIONS = frozenset({
        "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "pg_rotate_logfile",
        "lo_import", "lo_export", "lo_unlink", "pg_read_file", "pg_read_binary_file",
        "pg_ls_dir", "pg_stat_file", "set_config", "nextval", "setval", "dblink",
        "dblink_exec", "pg_sleep", "xp_cmdshell",
    })


    def _function_names(node: Any) -> Iterator[str]:
        if isinstance(node, dict):
            if node.get("class") == "FUNCTION" and isinstance(node.get("function_name"), str):
                yield node["function_name"].lower()
            for value in node.values():
                yield from _function_names(value)
        elif isinstance(node, list):
            for value in node:
                yield from _function_names(value)


    def validate_external_select(ast: dict[str, Any]) -> None:
        """SELECT seul ET aucune fonction à effet de bord (lecteurs SQL externes)."""
        validate_select_only(ast)
        bad = sorted({n for n in _function_names(ast) if n in _FORBIDDEN_FUNCTIONS})
        if bad:
            raise SqlSandboxError(f"function not allowed in a connector query: {', '.join(bad)}")
    ```
    (`from collections.abc import Iterator`.) Les 6 `materialize_*` de `connector_runtime.py` appellent `validate_external_select` au lieu de `validate_select_only`.
  - `connector_runtime.py:_timeout_connect_args` : pour Postgres non-Redshift, `pg["options"] = f"-c statement_timeout={q * 1000} -c default_transaction_read_only=on"`. `_stream_sql(dsn, query, *, expected_backend: str)` : juste après le calcul de `backend`,
    ```python
        if backend != expected_backend:  # AUD-081 : le secret fixe le dialecte (sqlite:// refusé)
            raise ConnectorRuntimeError(
                f"DSN de dialecte '{backend}' refusé pour un secret {expected_backend}"
            )
    ```
    et pour Oracle, ajouter au listener existant (l.342) un `@event.listens_for(engine, "begin")` qui exécute `conn.exec_driver_sql("SET TRANSACTION READ ONLY")`. Les 6 appelants passent `expected_backend=` : `"postgresql"`, `"mssql"`, `"snowflake"`, `"oracle"`, `"databricks"`, `"bigquery"` (vérifier chaque nom contre `make_url(...).get_backend_name()` d'un DSN d'exemple de `secrets/schemas.py`). Redshift, MSSQL, Snowflake, BigQuery, Databricks n'ont pas de mode lecture seule de session fiable : ajouter dans la description du kind de secret (`secrets/schemas.py`, `description=` des 5 payloads) « utilisez un compte en lecture seule ».
  - `dbio2.py` avant `find` : `flt = json_util.loads(json.dumps(p.filter))` (`from bson import json_util`, `import json`) et passer `flt` (le contrôle `_check_filter` reste sur le JSON brut en amont).
- [ ] **Step 5:** `uv run pytest tests/test_pipeline_connector_runtime.py tests/test_pipeline_ops_secretkinds.py tests/test_pipeline_ops_cloudfiles.py tests -k sandbox -q` → PASS ; avec `CORE_TEST_DATABASE_URL`, `test_materialize_postgres_connector_round_trips_query` reste vert (lecture seule compatible).
- [ ] **Step 6: AUD-100, test** — `core/tests/test_job_errors.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.job_errors import INTERNAL_ERROR_MESSAGE, public_error


def test_unexpected_error_never_reaches_the_user():
    exc = RuntimeError('(psycopg.errors.DuplicateColumn) [SQL: CREATE TABLE public.ingest_x ...]')
    assert public_error(exc) == INTERNAL_ERROR_MESSAGE
    assert "SQL" not in INTERNAL_ERROR_MESSAGE


def test_declared_user_errors_pass_through_bounded():
    assert public_error(ValueError("trop d'entités"), user_errors=(ValueError,)) == "trop d'entités"
    assert len(public_error(ValueError("x" * 2000), user_errors=(ValueError,))) == 500
```
Et dans `test_ingestion_tasks.py:299`, remplacer `assert "connectivité DB perdue" in fetched.error_message` par `assert fetched.error_message == INTERNAL_ERROR_MESSAGE` (et ajouter `assert "connectivité" not in fetched.error_message`).
- [ ] **Step 7: Implémenter** `core/app/job_errors.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Message d'erreur montré à l'utilisateur pour un job (AUD-100) : le détail
d'une exception inattendue (SQL, schéma, endpoint interne) reste dans les
journaux serveur. Module racine hors contrat de couches (comme app.errors)."""

INTERNAL_ERROR_MESSAGE = "erreur interne : le détail est consigné dans les journaux du serveur"


def public_error(
    exc: BaseException, *, user_errors: tuple[type[BaseException], ...] = ()
) -> str:
    if user_errors and isinstance(exc, user_errors):
        return str(exc)[:500]
    return INTERNAL_ERROR_MESSAGE
```
Puis, en vérifiant que chaque catch-all a déjà un `logger.exception(...)` (sinon l'ajouter, le détail doit survivre dans les logs) :
  - `f"erreur interne : {exc}"` → `INTERNAL_ERROR_MESSAGE` : `ingestion/tasks.py:227,241`, `pipelines/jobs.py:447,450,458`, `pipelines/sidecar/runner.py:51`, `tileset3d/jobs.py:163,165`, `terrain3d/jobs.py:173,175`, `raster/jobs.py:165`, `quality/jobs.py:56`, `reports/jobs.py:295,445`, `alerts/jobs.py:479,549`.
  - `reports/jobs.py:263,269` : `f"mise en file impossible : {exc}"` → `"mise en file impossible"`.
  - `geocoding/jobs.py:99` : `error=str(exc)[:500]` → `error=INTERNAL_ERROR_MESSAGE`.
  - `dataexport/jobs.py:191,193` (AUD-172) et `appexport/jobs.py:190,197` : `str(exc)` → `public_error(exc, user_errors=(ValueError, LookupError))`.
  - `export/jobs.py:424,433` : `msg = str(exc) if str(exc) in (USER_EXPORT_UNAVAILABLE, USER_EXPORT_INCOMPLETE) else public_error(exc, user_errors=(ValueError,))`, puis `msg` aux deux endroits.
  - Tests qui affirmaient le texte brut, à aligner sur `INTERNAL_ERROR_MESSAGE` : `test_report_jobs.py:481`, `test_appexport_jobs.py:313`, `test_export_jobs.py:253,475,574`. Ceux qui affirment un message utilisateur voulu (`test_dataexport_jobs.py:184,216`, `test_dataexport_jobs_pg.py:161`, `test_tileset3d_jobs.py:191,194,258`, `test_raster_jobs.py:115,158`, `test_terrain3d_jobs.py:275`, `test_appexport_jobs.py:108,134,150,190,214`, `test_pipeline_jobs.py:452,557-561`) doivent passer **sans modification**.
- [ ] **Step 8:** `uv run pytest tests/test_job_errors.py tests -k "jobs or tasks or sidecar" -q` → PASS ; `grep -rn 'erreur interne : {exc}\|error=str(exc)\|error_message=str(exc)' core/app` : seules restent les branches typées listées en jumelles.
- [ ] **Step 9: Commits** — `fix(core): writer.ftp neutralise les formules CSV (AUD-152)`, `fix(core): lecteurs SQL externes en lecture seule, fonctions à effet de bord et dialectes refusés, filtre Mongo en Extended JSON (AUD-081)`, `fix(core): les erreurs internes des jobs ne sont plus servies à l'utilisateur (AUD-100, AUD-172)`.

---

### Task 9: clôture

- [ ] Relire les jumelles de chaque tâche (piège n°14) ; `git log --format='%h %s%n%b' <base>..HEAD | grep -c "Co-Authored-By: Claude Sonnet 5.5"` = nombre de commits ; `git show --stat` de chacun.
- [ ] Portes complètes : cœur `uv run pytest` (avec `CORE_TEST_DATABASE_URL` sur la base dédiée), `uv run ruff check . && uv run ruff format --check . && uv run lint-imports`, `uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles app/net_pin.py`, `uv run python scripts/check_coverage.py coverage.xml .coverage-threshold` ; shell `npm run test`, `npm run lint && npm run format:check`, `npm run build` + `node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold` ; **suite E2E complète** `npm run e2e` (piège n°6 : la Task 2 change le contrat `exportToken`, la Task 6 les corps de présignature, la Task 5 l'effacement).
- [ ] OpenAPI + types TS régénérés et commités (Tasks 5, 6) ; `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check` vert (aucune surface nouvelle).
- [ ] Revue finale de branche (opus) : croisements à vérifier en priorité — garde d'egress (Task 1) ↔ Chromium (Task 2) ; `request` ajouté à `get_current_user` (Task 2) ↔ branche clé lecture seule (Task 5) ; middleware de corps (Task 6) ↔ `rate_limit_guard` (ordre) ; `ip_bucket` (Task 6) ↔ groupes de la Task 7 ; `widget_nodes` réutilisé par Tasks 3 et 4.
- [ ] Rapport au contrôleur (pas d'édition de `CLAUDE.md`, `docs/revue/*`, historique) : AUD fermés, AUD reportés et raisons (cf. Périmètre), reliquats à consigner — saisie des `scopes` de clé dans l'UI, scopes MCP (L9), `writer.file` CSV, messages GDAL dans les branches typées, reçu de purge, `tileset3d` multipart sans taille signée, STAC/DCAT anonymes sans budget, XFF de confiance en dev via la passerelle Docker, quotas éteints par défaut (runbook).
