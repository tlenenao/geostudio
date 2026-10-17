# SPDX-License-Identifier: Apache-2.0
"""Génère le fragment de configuration dynamique Traefik (provider
fichier) portant la CSP calculée. Gabarit de chaîne plutôt que pyyaml : ce
module tourne en production (worker), et pyyaml n'est aujourd'hui qu'une
dépendance de développement (core/pyproject.toml, [dependency-groups]) —
faire glisser une dépendance nouvelle vers la production pour ce seul
usage n'a pas été jugé justifié (spec SP-48 §2.4). Les origines sont
filtrées par `csp_hosts._origin` (hôte `[a-z0-9.-]`, port valide, AUD-089) et
chaque valeur est émise via `json.dumps` (une chaîne JSON est un scalaire
YAML double-quoté valide) — vérifié par les tests via yaml.safe_load (import
réservé aux tests). Deux middlewares : `csp-dynamic` (avec
`frame-ancestors 'self'`) et `csp-dynamic-embed` (routeur `/embed/`, sans
`frame-ancestors` : ces pages sont faites pour être intégrées)."""

import json

from app.security.service import CspAllowlist

_HEADER_NAMES = {
    "enforce": "Content-Security-Policy",
    "report-only": "Content-Security-Policy-Report-Only",
}


def _build_csp_value(allowlist: CspAllowlist, *, frame_ancestors: bool) -> str:
    img = " ".join(sorted({"'self'", "data:", "blob:", *allowlist.img_hosts}))
    connect = " ".join(sorted({"'self'", *allowlist.connect_hosts}))
    # Blocage 3 (spec SP-48 §4) tranché par Tanguy : Option A retenue —
    # script-src s'élargit à l'origine déclarée de chaque extension
    # (Extension.module_url, écriture gardée par
    # Privilege.ADMIN_EXTENSIONS_MANAGE), même patron que connect-src/img-src
    # ci-dessus. Coût marginal quasi nul : extract_extension_hosts() était
    # déjà calculé (§2.2), seul le branchement sur cette directive manquait.
    # Limite de sécurité assumée (spec §4, Option A) : ceci protège contre
    # un hôte non déclaré (une extension compromise servie depuis une autre
    # origine que celle enregistrée), mais NE protège PAS contre un fichier
    # malveillant substitué sur l'origine déclarée elle-même après coup —
    # confiance à la granularité de l'hôte, pas du contenu. Cohérent avec le
    # niveau de confiance déjà accordé à Extension.module_url aujourd'hui
    # (n'importe quel ADMIN_EXTENSIONS_MANAGE peut déjà y pointer vers
    # n'importe quel JS exécuté avec les mêmes droits DOM que le shell) :
    # cette option ne réduit aucune confiance existante, elle empêche
    # seulement qu'un attaquant hors du cercle des administrateurs de
    # l'instance ajoute une origine non voulue par une autre voie.
    script = " ".join(sorted({"'self'", *allowlist.script_hosts}))
    return (
        "default-src 'self'; "
        f"script-src {script}; "
        "style-src 'self' 'unsafe-inline'; "
        f"connect-src {connect}; "
        f"img-src {img}; "
        "worker-src 'self' blob:; "
        "base-uri 'self'; "
        "form-action 'self'; "
        + ("frame-ancestors 'self'; " if frame_ancestors else "")
        + "object-src 'none'"
    )


def render_dynamic_conf(allowlist: CspAllowlist, *, mode: str) -> str:
    if mode not in _HEADER_NAMES:
        raise ValueError(f"mode CSP inconnu : {mode!r} (attendu enforce|report-only)")
    header = json.dumps(_HEADER_NAMES[mode])
    lines = ["http:", "  middlewares:"]
    for name, frame in (("csp-dynamic", True), ("csp-dynamic-embed", False)):
        value = json.dumps(_build_csp_value(allowlist, frame_ancestors=frame))
        lines += [
            f"    {name}:",
            "      headers:",
            "        customResponseHeaders:",
            f"          {header}: {value}",
        ]
    return "\n".join(lines) + "\n"
