# SPDX-License-Identifier: Apache-2.0
"""AUD-118 : les liens relatifs du README, des guides et de la doc supply-chain existent
(le README avait dérivé jusqu'à citer une matrice gelée et des nombres faux)."""

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCS = [
    REPO / "README.md",
    REPO / "docs/supply-chain.md",
    *sorted((REPO / "docs/guides").glob("*.md")),
]
LINK = re.compile(r"\]\(([^)\s]+)\)")


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_relative_links_resolve(doc):
    broken = []
    for target in LINK.findall(doc.read_text(encoding="utf-8")):
        if re.match(r"^(https?:|mailto:|#)", target):
            continue
        if not (doc.parent / target.split("#")[0]).exists():
            broken.append(target)
    assert not broken, f"{doc.name} : liens cassés {broken}"


def test_readme_does_not_freeze_counts_or_frozen_matrix():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "57 opérations" not in text and "huit images" not in text
    assert "matrice-fonctionnalites" not in text  # matrice gelée : le bilan généré fait foi
