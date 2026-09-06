# SPDX-License-Identifier: Apache-2.0
"""Migration **ponctuelle** de la matrice SP-42 vers l'inventaire vivant
(SP-61, spec §8). Commité pour documenter la provenance des 304 lignes ; il
n'est pas rejoué en CI et ne doit plus jamais être relancé sur un inventaire
déjà corrigé à la main — il écraserait les corrections.

Ce qu'il migre : domaine, libellé, description, chemins de preuve (chemin nu,
sans `:ligne`), note qualitative datée, et la priorité **amorcée** depuis
`notes.utilite` (≥8 haute, 5-7 moyenne, ≤4 basse), marquée
`priorite_source: "amorcage-sp42"` — un point de départ, jamais une vérité.

Ce qu'il ne migre PAS : les états `livre`/`partiel`/`inerte`/`absent` du
2026-09-04, périmés par SP-43→SP-60. Ils sont **recalculés** par le générateur.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import unicodedata

_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
SOURCE = ".superpowers/sdd/sp42-matrice-notee.jsonl"
TARGET = "docs/revue/inventaire-fonctionnalites.jsonl"
SP42_DATE = "2026-09-04"


def proof_paths(raw: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_PATH_RE.findall(raw or "")))


def bootstrap_priority(utility: int | None) -> str:
    if utility is None:
        return "moyenne"
    if utility >= 8:
        return "haute"
    if utility >= 5:
        return "moyenne"
    return "basse"


def slug_for(domain: str, name: str) -> str:
    text = f"{domain} {name}"
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _SLUG_STRIP_RE.sub("-", ascii_text.lower()).strip("-")[:80]


def unique_slugs(slugs: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    output = []
    for slug in slugs:
        seen[slug] = seen.get(slug, 0) + 1
        output.append(slug if seen[slug] == 1 else f"{slug}-{seen[slug]}")
    return output


def build_rows(source: pathlib.Path) -> list[dict]:
    raw_rows = [
        json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    slugs = unique_slugs([slug_for(row["domaine"], row["fonctionnalite"]) for row in raw_rows])
    rows = []
    for slug, row in zip(slugs, raw_rows, strict=True):
        rows.append(
            {
                "id": slug,
                "domaine": row["domaine"],
                "fonctionnalite": row["fonctionnalite"],
                "description": row.get("description", ""),
                "preuve": list(proof_paths(row.get("preuve"))),
                "surfaces": {"rest": [], "mcp": [], "shell": [], "autre": []},
                "publiques": [],
                "priorite": bootstrap_priority((row.get("notes") or {}).get("utilite")),
                "priorite_source": "amorcage-sp42",
                "note_sp42": row.get("note", ""),
                "note_sp42_date": SP42_DATE,
            }
        )
    return rows


_LAZY_RE = re.compile(r'const (\w+) = lazy\(\(\) =>\s*import\("([^"]+)"\)')
_ROUTE_ELEMENT_RE = re.compile(r'path="([^"]+)"[^>]*element=\{<(\w+)', re.DOTALL)


def _route_pages(repo: pathlib.Path) -> dict[str, str]:
    """Route shell -> fichier de page.

    `routes.tsx` déclare 23 pages en `lazy(() => import("../pages/X"))`
    (SP-60) et rend soit la page elle-même, soit un composant enveloppe défini
    dans le même fichier ; on résout les deux en cherchant, dans le corps de
    l'enveloppe, un nom de composant paresseux."""
    source = (repo / "shell/src/shell/routes.tsx").read_text(encoding="utf-8")
    lazy = dict(_LAZY_RE.findall(source))
    pages: dict[str, str] = {}
    for route, element in _ROUTE_ELEMENT_RE.findall(source):
        target = lazy.get(element)
        if target is None:
            parts = source.split(f"function {element}", 1)
            if len(parts) == 2:
                target = next((lazy[name] for name in lazy if name in parts[1][:400]), None)
        if target:
            pages[route] = "shell/src/" + target.removeprefix("../") + ".tsx"
    return pages


def attach_surfaces(repo: pathlib.Path, rows: list[dict]) -> dict[str, list[str]]:
    """Rattache chaque surface dérivée aux entrées qui citent déjà sa preuve.

    Sur-rattacher est volontaire : une route citée par cinq entrées est
    attachée aux cinq. Le garde-fou (§6.1) exige **au moins un** revendicateur ;
    l'affinage se fait à la main, entrée par entrée, au fil des SP. La valeur de
    retour est la liste des orphelines — la seule liste de travail manuel."""
    from scripts.feature_health.mcp_surface import index_mcp_tools
    from scripts.feature_health.reachability import declared_shell_routes
    from scripts.feature_health.rest_surface import index_rest_routes, surface_id

    text_of = {
        row["id"]: " ".join(
            [
                " ".join(row["preuve"]),
                row["fonctionnalite"],
                row["description"],
                row.get("note_sp42", ""),
            ]
        )
        for row in rows
    }
    for row in rows:
        row["surfaces"] = {"rest": [], "mcp": [], "shell": [], "autre": []}
    by_id = {row["id"]: row for row in rows}
    orphans: dict[str, list[str]] = {"rest": [], "mcp": [], "shell": []}

    for fact in index_rest_routes(repo):
        module = "core/" + fact.module
        claimants = [row for row in rows if module in row["preuve"]]
        if not claimants:
            orphans["rest"].append(surface_id(fact))
        for row in claimants:
            row["surfaces"]["rest"].append(surface_id(fact))

    for tool in index_mcp_tools(repo):
        claimants = [identifier for identifier, text in text_of.items() if tool in text]
        if not claimants:
            orphans["mcp"].append(tool)
        for identifier in claimants:
            by_id[identifier]["surfaces"]["mcp"].append(tool)

    pages = _route_pages(repo)
    for route in declared_shell_routes(repo):
        page = pages.get(route)
        claimants = [row for row in rows if page and page in row["preuve"]]
        if not claimants:
            orphans["shell"].append(route)
        for row in claimants:
            row["surfaces"]["shell"].append(route)

    for row in rows:
        for key in ("rest", "mcp", "shell"):
            row["surfaces"][key] = sorted(set(row["surfaces"][key]))
    return orphans


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--force", action="store_true", help="écrase un inventaire existant")
    parser.add_argument(
        "--attach",
        action="store_true",
        help="ré-écrit seulement le champ surfaces de l'inventaire existant",
    )
    arguments = parser.parse_args(argv)
    target = arguments.repo / TARGET

    if arguments.attach:
        rows = [
            json.loads(line)
            for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        orphans = attach_surfaces(arguments.repo, rows)
        target.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        print(f"{len(rows)} lignes réécrites (surfaces rattachées) dans {target}")
        for kind, orphan_list in orphans.items():
            print(f"orphelines {kind} ({len(orphan_list)}) : {orphan_list}")
        return 0

    if target.exists() and not arguments.force:
        print(f"{target} existe déjà — refus d'écraser (utiliser --force).", file=sys.stderr)
        return 1
    rows = build_rows(arguments.repo / SOURCE)
    target.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} lignes écrites dans {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
