# SPDX-License-Identifier: Apache-2.0
"""Génère le fragment de configuration dynamique Traefik (provider
fichier) portant la CSP calculée. Gabarit de chaîne plutôt que pyyaml : ce
module tourne en production (worker), et pyyaml n'est aujourd'hui qu'une
dépendance de développement (core/pyproject.toml, [dependency-groups]) —
faire glisser une dépendance nouvelle vers la production pour ce seul
usage n'a pas été jugé justifié (spec SP-48 §2.4). Les seuls éléments
variables du gabarit sont des origines issues d'urlparse (schéma+hôte+port
optionnel) : elles ne peuvent contenir ni guillemet ni retour à la ligne,
donc aucun risque d'échappement YAML mal formé — vérifié par les tests de
ce fichier via yaml.safe_load (import réservé aux tests)."""

from app.security.service import CspAllowlist

_HEADER_NAMES = {
    "enforce": "Content-Security-Policy",
    "report-only": "Content-Security-Policy-Report-Only",
}


def _build_csp_value(allowlist: CspAllowlist) -> str:
    img = " ".join(sorted({"'self'", "data:", "blob:", *allowlist.img_hosts}))
    connect = " ".join(sorted({"'self'", *allowlist.connect_hosts}))
    # script-src reste 'self', jamais élargi à allowlist.script_hosts tant
    # que le blocage 3 (spec §4) n'est pas tranché par Tanguy — cf. Task 6
    # (test de garde dédié, tests/test_security_jobs.py).
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        f"connect-src {connect}; "
        f"img-src {img}; "
        "worker-src 'self' blob:; "
        "object-src 'none'"
    )


def render_dynamic_conf(allowlist: CspAllowlist, *, mode: str) -> str:
    if mode not in _HEADER_NAMES:
        raise ValueError(f"mode CSP inconnu : {mode!r} (attendu enforce|report-only)")
    header_name = _HEADER_NAMES[mode]
    csp_value = _build_csp_value(allowlist)
    return (
        "http:\n"
        "  middlewares:\n"
        "    csp-dynamic:\n"
        "      headers:\n"
        "        customResponseHeaders:\n"
        f'          "{header_name}": "{csp_value}"\n'
    )
