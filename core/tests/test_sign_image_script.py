# SPDX-License-Identifier: Apache-2.0
"""AUD-177 : sign-image.sh ne re-signe pas un digest déjà signé (409 Rekor sinon)."""

import os
import pathlib
import subprocess

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts/ci/sign-image.sh"


def _run(tmp_path, verify_ok: bool):
    log = tmp_path / "calls"
    fake = tmp_path / "cosign"
    verdict = "exit 0" if verify_ok else "exit 1"
    fake.write_text(
        f'#!/usr/bin/env bash\necho "$1" >> {log}\n[ "$1" = sign ] && exit 0\n{verdict}\n'
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    res = subprocess.run([str(SCRIPT), "ghcr.io/x/y@sha256:abc"], env=env, capture_output=True)
    return res.returncode, log.read_text().split()


def test_already_signed_digest_is_not_signed_again(tmp_path):
    code, calls = _run(tmp_path, verify_ok=True)
    assert code == 0
    assert calls == ["verify"]


def test_unsigned_digest_is_signed(tmp_path):
    code, calls = _run(tmp_path, verify_ok=False)
    assert code == 0
    assert calls == ["verify", "sign"]
