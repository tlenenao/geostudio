# SPDX-License-Identifier: Apache-2.0
import yaml  # import de test uniquement — jamais en production, cf. spec §2.4

from app.db import init_db, make_engine, make_session_factory
from app.security import jobs as security_jobs
from app.security.service import CspAllowlist
from app.security.traefik_render import render_dynamic_conf


def _csp_directives(header_value: str) -> dict[str, list[str]]:
    """Découpe un en-tête CSP en {directive: [sources]}.

    Assertion par SOURCE et non par sous-chaîne : `"https://tiles.example.com"
    in header` passait aussi bien si l'hôte n'apparaissait que dans la
    mauvaise directive (ou comme fragment d'un hôte plus long, par exemple
    `https://tiles.example.com.evil.test`) — le test ne prouvait donc pas ce
    qu'il annonçait. C'est aussi ce que CodeQL signalait ici sous
    py/incomplete-url-substring-sanitization."""
    directives: dict[str, list[str]] = {}
    for chunk in header_value.split(";"):
        parts = chunk.split()
        if parts:
            directives[parts[0]] = parts[1:]
    return directives


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_render_dynamic_conf_produces_parseable_yaml_enforce_mode():
    allowlist = CspAllowlist(
        img_hosts={"https://tiles.example.com"},
        connect_hosts={"https://tiles.example.com"},
        script_hosts=set(),
    )
    rendered = render_dynamic_conf(allowlist, mode="enforce")
    parsed = yaml.safe_load(rendered)
    header_name = "Content-Security-Policy"
    headers = parsed["http"]["middlewares"]["csp-dynamic"]["headers"]["customResponseHeaders"]
    assert header_name in headers
    directives = _csp_directives(headers[header_name])
    # Égalité exacte de la liste de sources, et non une appartenance : elle
    # attrape à la fois l'hôte manquant ET une directive élargie par
    # inadvertance, ce qu'un `in` laisse passer. Écarte au passage le motif
    # `"<url>" in <expr>` que CodeQL signale
    # (py/incomplete-url-substring-sanitization) — il ne distingue pas une
    # appartenance exacte d'une recherche de sous-chaîne.
    assert directives["img-src"] == ["'self'", "blob:", "data:", "https://tiles.example.com"]
    assert directives["connect-src"] == ["'self'", "https://tiles.example.com"]
    # jamais élargi (blocage 3 non tranché) : script-src n'a que 'self'.
    assert directives["script-src"] == ["'self'"]


def test_render_dynamic_conf_report_only_mode_uses_report_only_header_name():
    allowlist = CspAllowlist()
    rendered = render_dynamic_conf(allowlist, mode="report-only")
    parsed = yaml.safe_load(rendered)
    headers = parsed["http"]["middlewares"]["csp-dynamic"]["headers"]["customResponseHeaders"]
    assert "Content-Security-Policy-Report-Only" in headers
    assert "Content-Security-Policy" not in headers


def test_render_dynamic_conf_rejects_unknown_mode():
    import pytest

    with pytest.raises(ValueError):
        render_dynamic_conf(CspAllowlist(), mode="bogus")


def test_render_dynamic_conf_empty_allowlist_still_has_self():
    rendered = render_dynamic_conf(CspAllowlist(), mode="enforce")
    parsed = yaml.safe_load(rendered)
    headers = parsed["http"]["middlewares"]["csp-dynamic"]["headers"]["customResponseHeaders"]
    assert "default-src 'self'" in headers["Content-Security-Policy"]


def test_refresh_csp_dynamic_conf_task_writes_the_rendered_file(tmp_path, monkeypatch):
    """Reprend le patron exact de test_report_sweep.py
    (monkeypatch.setattr(module, "_session_factory", lambda: Session)) —
    pas de marqueur postgis : la tâche ne fait qu'agréger des tables
    relationnelles simples (cf. test_security_service.py) et écrire un
    fichier, aucune fonctionnalité spécifique à PostGIS."""
    Session = _make_session()
    monkeypatch.setattr(security_jobs, "_session_factory", lambda: Session)
    target = tmp_path / "dynamic-conf.yml"
    monkeypatch.setenv("CORE_CSP_MODE", "enforce")
    monkeypatch.setattr(security_jobs, "CSP_DYNAMIC_CONF_PATH", str(target))

    security_jobs.refresh_csp_dynamic_conf_task(timestamp=0)

    assert target.exists()
    assert "csp-dynamic" in target.read_text()
    assert "Content-Security-Policy" in target.read_text()


def test_script_src_never_widened_by_computed_extension_hosts():
    """SP-48/GAP-72 blocage 3 : le sandboxing des widgets d'extension
    tiers est une décision produit non tranchée (spec §4, 4 options
    évaluées, aucune retenue sans accord explicite de Tanguy). Ce test
    échoue intentionnellement si script_hosts est un jour branché sur
    script-src sans qu'on ait d'abord retiré ce test — c'est le signal
    que la décision a été prise ailleurs (ledger de session, CLAUDE.md)
    avant de le faire. Déjà vert avec le code des Tasks 1-5 (rien ne câble
    jamais script_hosts sur script-src) : test de non-régression
    intentionnelle, committé séparément pour apparaître comme une décision
    explicite dans l'historique, pas comme un sous-produit accidentel de
    Task 3."""
    allowlist = CspAllowlist(script_hosts={"https://cdn.example.com"})
    rendered = render_dynamic_conf(allowlist, mode="enforce")
    assert "cdn.example.com" not in rendered
    assert "script-src 'self'" in rendered
