# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
import sys
import time

import httpx


def test_entrypoint_prints_port_and_serves_ops(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "scripts/pipeline_sidecar.py", "--base-uri", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=".",
    )
    try:
        first_line = proc.stdout.readline()
        match = re.match(r"PORT=(\d+)\n", first_line)
        assert match, f"unexpected first line: {first_line!r}, stderr={proc.stderr.read()}"
        port = int(match.group(1))

        deadline = time.monotonic() + 5.0
        last_exc = None
        while time.monotonic() < deadline:
            try:
                res = httpx.get(f"http://127.0.0.1:{port}/pipelines/ops", timeout=1.0)
                assert res.status_code == 200
                assert "reader.file" in res.json()
                return
            except httpx.TransportError as exc:
                last_exc = exc
                time.sleep(0.1)
        raise AssertionError(f"sidecar never became reachable: {last_exc}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_entrypoint_requires_token_when_env_var_set(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOSTUDIO_SIDECAR_TOKEN", "s3cr3t")
    proc = subprocess.Popen(
        [sys.executable, "scripts/pipeline_sidecar.py", "--base-uri", str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=".",
        env={**__import__("os").environ, "GEOSTUDIO_SIDECAR_TOKEN": "s3cr3t"},
    )
    try:
        first_line = proc.stdout.readline()
        match = re.match(r"PORT=(\d+)\n", first_line)
        assert match, f"unexpected first line: {first_line!r}, stderr={proc.stderr.read()}"
        port = int(match.group(1))

        deadline = time.monotonic() + 5.0
        last_status = None
        while time.monotonic() < deadline:
            try:
                res = httpx.get(f"http://127.0.0.1:{port}/pipelines/ops", timeout=1.0)
                last_status = res.status_code
                break
            except httpx.TransportError:
                time.sleep(0.1)
        assert last_status == 401, "unauthenticated request should be rejected once a token is set"

        authed = httpx.get(
            f"http://127.0.0.1:{port}/pipelines/ops",
            headers={"Authorization": "Bearer s3cr3t"},
            timeout=1.0,
        )
        assert authed.status_code == 200
    finally:
        proc.terminate()
        proc.wait(timeout=5)
