# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Équivalent de `test_deployability.py` pour le chart Helm (ARC-29).

Piège n°2 (« livré ≠ câblé ») : on vérifie la **valeur rendue** par `helm template`, jamais la simple
présence d'un nom dans un template. Chaque variable d'environnement d'un service du compose a sa contrepartie
dans le workload homonyme, avec la même valeur par défaut (exceptions justifiées ci-dessous) ; les secrets ne
passent que par `secretKeyRef` ; tout conteneur est non-root, sondé, et ses commandes de sonde sont celles du
healthcheck du compose.

Nécessite le binaire `helm`. Sans lui : skip, sauf si GEOSTUDIO_REQUIRE_HELM=1 (CI) — un skip silencieux
est exactement le piège SP-43.
"""

import os
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "deploy/helm/geostudio"
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]

HELM = os.environ.get("HELM_BIN") or shutil.which("helm")
if not HELM and os.environ.get("GEOSTUDIO_REQUIRE_HELM") == "1":
    raise RuntimeError("GEOSTUDIO_REQUIRE_HELM=1 mais `helm` est introuvable")
pytestmark = pytest.mark.skipif(not HELM, reason="helm absent")

SECRET_NAME = re.compile(r"(SECRET|PASSWORD|_API_KEY|MASTER_KEY|ACCESS_KEY|DATABASE_URL)")
# Écarts volontaires compose → chart, avec la raison.
ALLOWED_DIFF = {
    "CORE_AUTH_MODE": "core refuse mock hors CORE_ENV=development ; défaut oidc en cluster",
    "CORE_ADMIN_TOOLS_GATEWAY_URL": "passerelle admin = Traefik compose uniquement (https://${DOMAIN})",
    "SHELL_BASE_URL": "calculé : service shell du release",
    "EXPORT_CORE_INTERNAL_URL": "calculé : service core du release",
    "VITE_AUTH_MODE": "idem CORE_AUTH_MODE",
    "CORE_CORS_ALLOWED_ORIGINS": "compose : shell :8300 du démarrage rapide ; cluster : même hôte",
    "GEOSTUDIO_VERSION": "calculé : tag d'image du release (compose : variable d'opérateur)",
}
# compose service -> (workload suffixe, valeurs --set pour l'activer)
WORKLOADS = {
    "core": ("core", []),
    "worker": ("worker", []),
    "cdc-worker": ("cdc-worker", []),
    "export-worker": ("export-worker", ["exportWorker.enabled=true"]),
    "shell": ("shell", []),
}


def render(*sets: str, secret: bool = True) -> list[dict]:
    args = [HELM, "template", "rel", str(CHART)]
    if secret:
        args += ["--set", "secrets.existingSecret=gs-secrets"]
    for s in sets:
        args += ["--set", s]
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


@pytest.fixture(scope="module")
def docs() -> list[dict]:
    return render("exportWorker.enabled=true")


def _deployment(docs: list[dict], suffix: str) -> dict:
    (d,) = [
        d
        for d in docs
        if d["kind"] == "Deployment" and d["metadata"]["name"] == f"rel-geostudio-{suffix}"
    ]
    return d


def _container(docs: list[dict], suffix: str) -> dict:
    return _deployment(docs, suffix)["spec"]["template"]["spec"]["containers"][0]


def _compose_default(raw: object) -> str:
    raw = str(raw)
    m = re.fullmatch(r"\$\{[A-Z_0-9]+(?::-(.*))?\}", raw)
    return (m.group(1) or "") if m else raw


def _rendered_env(docs: list[dict], suffix: str) -> tuple[dict[str, str], dict[str, dict]]:
    """(valeurs en clair = ConfigMap + env littéraux, secretKeyRef par nom)."""
    c = _container(docs, suffix)
    plain: dict[str, str] = {}
    for ef in c.get("envFrom", []):
        cm = next(
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == ef["configMapRef"]["name"]
        )
        plain.update(cm["data"])
    refs: dict[str, dict] = {}
    for e in c.get("env", []):
        if "value" in e:
            plain[e["name"]] = e["value"]
        else:
            refs[e["name"]] = e["valueFrom"]["secretKeyRef"]
    return plain, refs


@pytest.mark.parametrize("service", list(WORKLOADS))
def test_every_compose_env_var_has_its_rendered_counterpart(docs, service):
    suffix = WORKLOADS[service][0]
    plain, refs = _rendered_env(docs, suffix)
    for name, raw in COMPOSE[service].get("environment", {}).items():
        if SECRET_NAME.search(name):
            assert name in refs, f"{service}: secret {name} absent du chart (secretKeyRef)"
            assert refs[name]["key"] == name and refs[name]["name"] == "gs-secrets"
            assert name not in plain, f"{service}: secret {name} rendu en clair"
            continue
        assert name in plain, f"{service}: {name} du compose n'est pas rendu"
        if name not in ALLOWED_DIFF:
            assert plain[name] == _compose_default(raw), (
                f"{service}: {name} = {plain[name]!r} (chart) vs {_compose_default(raw)!r} (compose)"
            )


def test_secrets_never_in_values_and_required():
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    flat = list(values["config"]) + list(values["shell"]["env"])
    assert not [k for k in flat if SECRET_NAME.search(k)], "un secret est défini dans values.yaml"
    assert values["secrets"]["existingSecret"] == ""
    failed = subprocess.run([HELM, "template", "rel", str(CHART)], capture_output=True, text=True)
    assert failed.returncode != 0 and "existingSecret" in failed.stderr


def test_every_workload_is_non_root_hardened_and_probed(docs):
    for kind_suffix in ["core", "worker", "cdc-worker", "export-worker", "shell"]:
        c = _container(docs, kind_suffix)
        sc = c["securityContext"]
        assert (
            sc["runAsNonRoot"] is True and isinstance(sc["runAsUser"], int) and sc["runAsUser"] > 0
        )
        assert sc["allowPrivilegeEscalation"] is False and sc["capabilities"] == {"drop": ["ALL"]}
        assert "livenessProbe" in c, kind_suffix
        assert "readinessProbe" in c or "startupProbe" in c, kind_suffix


@pytest.mark.parametrize("service", ["worker", "cdc-worker", "export-worker"])
def test_exec_probes_run_the_compose_healthcheck_command(docs, service):
    compose_test = COMPOSE[service]["healthcheck"]["test"]
    expected = compose_test[1:] if compose_test[0] == "CMD" else ["sh", "-c", compose_test[1]]
    probe = _container(docs, service)["livenessProbe"]["exec"]["command"]
    assert probe == expected


def test_http_probes_target_the_compose_healthcheck_endpoints(docs):
    core = _container(docs, "core")
    assert "localhost:8200/health" in COMPOSE["core"]["healthcheck"]["test"][-1]
    assert core["livenessProbe"]["httpGet"]["path"] == "/health"
    # start_period 180s (migrations) du compose : le startupProbe tolère au moins autant
    sp = core["startupProbe"]
    assert sp["periodSeconds"] * sp["failureThreshold"] >= 180
    assert "127.0.0.1:8300/" in " ".join(COMPOSE["shell"]["healthcheck"]["test"])
    assert _container(docs, "shell")["livenessProbe"]["httpGet"]["path"] == "/"


def test_commands_match_the_compose(docs):
    worker_cmd = " ".join(_container(docs, "worker")["command"])
    queues = re.search(r"-q ([a-z0-9,]+)", COMPOSE["worker"]["command"]).group(1)
    assert f"-q {queues}" in worker_cmd and "-c 4" in worker_cmd
    assert "scripts.ensure_procrastinate_schema" in worker_cmd
    assert " ".join(_container(docs, "export-worker")["command"]) == re.sub(
        r"\$\{[A-Z_]+:-([^}]*)\}", r"\1", COMPOSE["export-worker"]["command"]
    )
    assert " ".join(_container(docs, "cdc-worker")["command"]) == COMPOSE["cdc-worker"]["command"]
    # Compose : alembic puis uvicorn ; chart : uvicorn seul, alembic dans le Job hook (AUD-033).
    assert COMPOSE["core"]["command"].endswith(
        'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8200"'
    )
    core_cmd = _container(docs, "core")["command"]
    assert core_cmd == ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]


def test_migrations_run_once_in_a_pre_upgrade_hook_with_secret_only_env(docs):
    """AUD-033 : le hook passe avant le ConfigMap (pré-install) — aucune
    référence à celui-ci, sinon le Job reste bloqué en CreateContainerConfigError."""
    (job,) = [d for d in docs if d["kind"] == "Job"]
    assert job["metadata"]["name"] == "rel-geostudio-migrations"
    assert job["metadata"]["annotations"]["helm.sh/hook"] == "pre-install,pre-upgrade"
    c = job["spec"]["template"]["spec"]["containers"][0]
    assert c["command"] == ["alembic", "upgrade", "head"]
    assert "envFrom" not in c
    assert {e["name"] for e in c["env"]} == {"DATABASE_URL", "CORE_MIGRATION_DATABASE_URL"}
    assert all(e["valueFrom"]["secretKeyRef"]["name"] == "gs-secrets" for e in c["env"])
    assert c["securityContext"]["runAsNonRoot"] is True


def test_shell_security_headers_follow_the_csp_mode():
    """AUD-030 : sans Traefik, nginx pose HSTS, X-Frame-Options et la CSP ;
    /embed/ reste encadrable (GAP-19)."""

    def headers(*sets: str) -> dict:
        docs = render(*sets)
        (cm,) = [d for d in docs if d["metadata"]["name"] == "rel-geostudio-shell-headers"]
        shell = _deployment(docs, "shell")["spec"]["template"]["spec"]
        assert {
            "name": "security-headers",
            "mountPath": "/etc/nginx/snippets",
            "readOnly": True,
        } in (shell["containers"][0]["volumeMounts"])
        return cm["data"]

    data = headers()
    main, embed = data["security-headers.conf"], data["security-headers-embed.conf"]
    assert "Strict-Transport-Security" in main and "Strict-Transport-Security" in embed
    assert "add_header X-Frame-Options DENY always;" in main
    assert "add_header Content-Security-Policy-Report-Only " in main
    assert "frame-ancestors 'none'" in main
    assert "X-Frame-Options" not in embed and "frame-ancestors" not in embed
    enforced = headers("config.CORE_CSP_MODE=enforce")["security-headers.conf"]
    assert "add_header Content-Security-Policy " in enforced
    # Les deux snippets nommés par shell/nginx.conf existent dans le ConfigMap.
    nginx = (REPO / "shell/nginx.conf").read_text()
    for name in set(re.findall(r"snippets/([\w-]+\.conf)", nginx)):
        assert name in data, name


def test_images_are_released_multiarch_images_pinned_to_the_env_version(docs):
    env_version = re.search(
        r"^GEOSTUDIO_VERSION=(.+)$", (REPO / ".env.example").read_text(), re.M
    ).group(1)
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    assert chart["appVersion"] == env_version, "Chart.appVersion doit suivre GEOSTUDIO_VERSION"
    prod = (REPO / "docker-compose.prod.yml").read_text()
    for suffix, img in [
        ("core", "core"),
        ("worker", "core"),
        ("cdc-worker", "core"),
        ("export-worker", "export-worker"),
        ("shell", "shell"),
    ]:
        image = _container(docs, suffix)["image"]
        assert image == f"ghcr.io/tlenenao/geostudio-{img}:{env_version}"
        assert f"ghcr.io/tlenenao/geostudio-{img}:" in prod


def test_optional_workloads_render_only_when_enabled():
    base = render()
    names = {d["metadata"]["name"] for d in base if d["kind"] == "Deployment"}
    assert names == {f"rel-geostudio-{s}" for s in ("core", "worker", "cdc-worker", "shell")}
    full = render(
        "exportWorker.enabled=true", "observability.enabled=true", "cdcWorker.enabled=false"
    )
    names = {d["metadata"]["name"] for d in full if d["kind"] == "Deployment"}
    assert "rel-geostudio-export-worker" in names and "rel-geostudio-otel-lgtm" in names
    assert "rel-geostudio-cdc-worker" not in names
    plain, _ = _rendered_env(full, "core")
    assert plain["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://rel-geostudio-otel-lgtm:4318"


def test_otel_lgtm_data_volume_and_version_wiring():
    """AUD-038 : /data monté (PVC si existingClaim) ; AUD-040 : la version des
    traces suit le tag d'image."""
    spec = _deployment(render("observability.enabled=true"), "otel-lgtm")["spec"]["template"]
    assert {"name": "data", "mountPath": "/data"} in spec["spec"]["containers"][0]["volumeMounts"]
    assert spec["spec"]["volumes"] == [{"name": "data", "emptyDir": {}}]
    claimed = render("observability.enabled=true", "observability.existingClaim=lgtm")
    vol = _deployment(claimed, "otel-lgtm")["spec"]["template"]["spec"]["volumes"][0]
    assert vol["persistentVolumeClaim"] == {"claimName": "lgtm"}
    assert _rendered_env(render("image.tag=v7.7.7"), "worker")[0]["GEOSTUDIO_VERSION"] == "v7.7.7"


def test_cors_allows_the_shell_host_when_core_has_its_own_api_host():
    """AUD-132 : l'Ingress sert le shell (host) et le cœur (apiHost) sur deux
    origines ; sans CORS, le navigateur bloque tout appel au cœur."""
    ingress = ("ingress.enabled=true", "ingress.host=geo.example", "ingress.apiHost=api.example")
    env = _rendered_env(render(*ingress, "ingress.tlsSecretName=tls"), "core")[0]
    assert env["CORE_CORS_ALLOWED_ORIGINS"] == "https://geo.example"
    assert (
        _rendered_env(render(*ingress), "core")[0]["CORE_CORS_ALLOWED_ORIGINS"]
        == "http://geo.example"
    )
    assert _rendered_env(render(), "core")[0]["CORE_CORS_ALLOWED_ORIGINS"] == ""


def test_shell_csp_connect_src_allows_the_core_and_oidc_origins():
    """Revue finale SP-L3 (M5) : `connect-src 'self'` seul bloquait, en mode
    enforce, tout appel du shell au cœur (apiHost) et à Keycloak."""
    docs = render(
        "ingress.enabled=true",
        "ingress.host=geo.example",
        "ingress.apiHost=api.example",
        "ingress.tlsSecretName=tls",
        "config.CORE_OIDC_ISSUER=https://sso.example/realms/geostudio",
    )
    (cm,) = [d for d in docs if d["metadata"]["name"] == "rel-geostudio-shell-headers"]
    for conf in cm["data"].values():
        connect = re.search(r"connect-src ([^;]+);", conf).group(1).split()
        assert {"'self'", "https://api.example", "https://sso.example"} <= set(connect), connect


def _bytes(size: str) -> int:
    """'512MB', '2Gi', '2GB' -> octets (préfixes binaires dans les deux cas)."""
    m = re.fullmatch(r"(\d+)\s*([A-Za-z]*)", size.strip())
    assert m, size
    return int(m.group(1)) * {"": 1, "k": 2**10, "m": 2**20, "g": 2**30}[m.group(2)[:1].lower()]


@pytest.mark.parametrize("suffix", ["core", "worker"])
def test_duckdb_memory_limit_is_well_below_the_pod_limit(docs, suffix):
    """Revue finale SP-L3 (I2) : DuckDB à 2GB par connexion dans un pod borné à
    2Gi = OOMKilled avant tout débordement sur disque."""
    duck = _rendered_env(docs, suffix)[0]["CORE_DUCKDB_MEMORY_LIMIT"]
    limit = _container(docs, suffix)["resources"]["limits"]["memory"]
    assert _bytes(duck) * 2 <= _bytes(limit), (duck, limit)


def test_valhalla_renders_only_when_enabled_and_wires_core_url():
    """ARC-34 : sous-chart optionnel ; CORE_ROUTING_URL pointe le service du release."""
    base = render()
    assert not [d for d in base if "valhalla" in d["metadata"]["name"]]
    assert _rendered_env(base, "core")[0]["CORE_ROUTING_URL"] == ""
    full = render("valhalla.enabled=true")
    kinds = {d["kind"] for d in full if d["metadata"]["name"] == "rel-geostudio-valhalla"}
    assert kinds == {"Deployment", "Service"}
    for service in ("core", "worker"):
        plain, _ = _rendered_env(full, service)
        assert plain["CORE_ROUTING_URL"] == "http://rel-geostudio-valhalla:8002"


def test_worker_checkpoints_live_on_its_scratch_volume(docs):
    """F5 : les points de reprise vont sur le volume scratch monté du worker, jamais
    sur la racine du conteneur (readOnlyRootFilesystem) ni sous un tmp non monté."""
    plain, _ = _rendered_env(docs, "worker")
    path = plain["CORE_PIPELINE_CHECKPOINT_DIR"]
    mounts = [m["mountPath"] for m in _container(docs, "worker").get("volumeMounts", [])]
    assert any(path.startswith(m.rstrip("/") + "/") for m in mounts), (path, mounts)


def test_cdc_worker_replicas_are_safe_thanks_to_leader_election():
    """ARC-32 : le mono-writer n'est plus garanti par replicas=1 mais par l'élection
    (app.cdc.election) ; la mise à jour ne surcharge jamais (maxSurge 0)."""
    d = _deployment(render("cdcWorker.replicas=3"), "cdc-worker")
    assert d["spec"]["replicas"] == 3
    assert d["spec"]["strategy"]["rollingUpdate"]["maxSurge"] == 0


def test_core_ha_defaults_two_replicas_with_pdb_and_shared_limiter():
    docs = render()
    assert _deployment(docs, "core")["spec"]["replicas"] == 2
    (pdb,) = [d for d in docs if d["kind"] == "PodDisruptionBudget"]
    assert pdb["spec"]["minAvailable"] == 1
    plain, _ = _rendered_env(docs, "core")
    assert plain["CORE_RATELIMIT_BACKEND"] == "postgres"
    assert not [d for d in render("core.replicas=1") if d["kind"] == "PodDisruptionBudget"]


def test_ingress_requires_hosts():
    ok = render("ingress.enabled=true", "ingress.host=a.example", "ingress.apiHost=api.example")
    (ing,) = [d for d in ok if d["kind"] == "Ingress"]
    assert [r["host"] for r in ing["spec"]["rules"]] == ["a.example", "api.example"]
    bad = subprocess.run(
        [
            HELM,
            "template",
            "rel",
            str(CHART),
            "--set",
            "secrets.existingSecret=s",
            "--set",
            "ingress.enabled=true",
        ],
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0


@pytest.mark.parametrize("suffix", ["worker", "export-worker"])
def test_workers_render_a_termination_grace_period_above_the_graceful_timeout(docs, suffix):
    """AUD-027 : arrêt gracieux (SIGTERM puis attente des jobs) avant SIGKILL."""
    spec = _deployment(docs, suffix)["spec"]["template"]["spec"]
    grace = spec["terminationGracePeriodSeconds"]
    assert grace >= 300
    cmd = " ".join(spec["containers"][0]["command"])
    graceful = int(re.search(r"--shutdown-graceful-timeout (\d+)", cmd).group(1))
    assert graceful < grace


def test_worker_sh_c_execs_procrastinate_so_sigterm_reaches_it(docs):
    """AUD-027 : `sh -c "a && python -m procrastinate …"` laisse sh en PID 1 (SIGTERM ignoré)."""
    cmd = _container(docs, "worker")["command"]
    assert cmd[:2] == ["sh", "-c"] and "&& exec python -m procrastinate" in cmd[2]
