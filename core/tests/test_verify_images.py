# SPDX-License-Identifier: Apache-2.0
"""AUD-113 : scripts/verify-images.sh vérifie chaque image du compose de production."""

import pathlib
import re
import stat
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/verify-images.sh"


def _run(tmp_path, cosign_exit: int):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    cosign = bin_dir / "cosign"
    cosign.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit {cosign_exit}\n')
    cosign.chmod(cosign.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    res = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), "v9.9.9"], cwd=REPO, env=env, capture_output=True, text=True
    )
    return res, log


def test_every_prod_image_is_verified_with_the_workflow_identity(tmp_path):
    res, log = _run(tmp_path, 0)
    assert res.returncode == 0, res.stderr
    calls = log.read_text().splitlines()
    prod = (REPO / "docker-compose.prod.yml").read_text()
    expected = set(re.findall(r"ghcr\.io/tlenenao/geostudio-[a-z0-9-]+", prod))
    assert {c.split()[-1] for c in calls} == {f"{i}:v9.9.9" for i in expected}
    issuer = "https://token.actions.githubusercontent.com"
    assert all(any(tok == issuer for tok in c.split()) for c in calls)


def test_a_failed_verification_fails_the_script(tmp_path):
    res, _ = _run(tmp_path, 1)
    assert res.returncode == 1 and "FAIL" in res.stderr
