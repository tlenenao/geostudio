# SPDX-License-Identifier: Apache-2.0
"""AUD-111 : la garde de licences refuse GPL/AGPL et LGPL non déclarée."""

from scripts.check_licenses import violations


def test_gpl_and_undeclared_lgpl_are_refused_but_permissive_pass():
    dists = [
        ("a", "MIT"),
        ("b", "AGPL-3.0-or-later"),
        ("c", "LGPL-3.0-only"),
        ("d", "GNU General Public License v2 (GPLv2)"),
        ("e", "Apache-2.0"),
    ]
    out = violations(dists, {})
    assert [v.split(":")[0] for v in out] == ["b", "c", "d"]
    assert violations(dists, {"c": "lien dynamique"}) == [v for v in out if not v.startswith("c")]
