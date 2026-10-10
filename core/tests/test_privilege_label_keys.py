# SPDX-License-Identifier: Apache-2.0
"""REV-306 : parité PRIVILEGE_METADATA <-> catalogue i18n du shell."""

import re
from pathlib import Path

from app.roles.privileges import PRIVILEGE_METADATA

SHELL_I18N = Path(__file__).resolve().parents[2] / "shell" / "src" / "i18n"
_KEY = re.compile(r'"(roles\.privilege\.\w+)"')


def _keys(*names: str) -> set[str]:
    return {k for n in names for k in _KEY.findall((SHELL_I18N / n).read_text(encoding="utf-8"))}


def test_core_label_keys_match_shell_mirror_and_catalog() -> None:
    core = {label for _, label in PRIVILEGE_METADATA.values()}
    assert core
    assert _keys("corePrivilegeLabelKeys.ts") == core
    # le catalogue fr (noyau + domaines) porte exactement ces libellés (hors clé de repli)
    assert (
        _keys(
            "catalog.fr.ts", *(f"domains/{f.name}" for f in (SHELL_I18N / "domains").glob("*.ts"))
        )
        - {"roles.privilege.unknown"}
        == core
    )
