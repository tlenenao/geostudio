# SPDX-License-Identifier: Apache-2.0
"""Fait tourner un binaire sidecar gelé (frozen, n'importe lequel — chemin
donné en argv[1]) à travers un cycle réel reader.file -> writer.file, sur
HTTP loopback, pour prouver que le freeze n'a rien perdu. Utilisé en CI
(Tâche 2) et à la main sur la VM Windows de développement."""

import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pipeline_sidecar_freeze_smoke.py <path-to-frozen-binary>", file=sys.stderr)
        return 2
    binary_path = sys.argv[1]
    # Jeton requis : sans lui, ce smoke test ne valide le binaire gelé que
    # dans la configuration token=None, qui n'est jamais celle de
    # production (Tauri passe toujours GEOSTUDIO_SIDECAR_TOKEN, cf. Tâche 3)
    # — trouvé en revue finale de branche (Tâche 8).
    token = secrets.token_hex(16)
    auth_headers = {"Authorization": f"Bearer {token}"}

    with tempfile.TemporaryDirectory(prefix="geostudio-freeze-smoke-") as tmp:
        in_path = Path(tmp) / "in.geojson"
        in_path.write_text(
            '{"type":"FeatureCollection","features":['
            '{"type":"Feature","properties":{"label":"a"},'
            '"geometry":{"type":"Point","coordinates":[1,2]}}]}'
        )
        out_path = Path(tmp) / "out.gpkg"

        proc = subprocess.Popen(
            [binary_path, "--base-uri", tmp],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "GEOSTUDIO_SIDECAR_TOKEN": token},
        )
        try:
            first_line = proc.stdout.readline()
            match = re.match(r"PORT=(\d+)\n", first_line)
            if not match:
                print(f"FAIL: unexpected first line {first_line!r}", file=sys.stderr)
                print(proc.stderr.read(), file=sys.stderr)
                return 1
            port = int(match.group(1))
            base = f"http://127.0.0.1:{port}"

            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    httpx.get(f"{base}/pipelines/ops", headers=auth_headers, timeout=1.0)
                    break
                except httpx.TransportError:
                    time.sleep(0.2)
            else:
                print("FAIL: sidecar never became reachable", file=sys.stderr)
                return 1

            payload = {
                "nodes": [
                    {
                        "id": "r1",
                        "kind": "reader",
                        "op": "reader.file",
                        "params": {"path": str(in_path)},
                    },
                    {
                        "id": "w1",
                        "kind": "writer",
                        "op": "writer.file",
                        "params": {"path": str(out_path)},
                    },
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            }
            put_res = httpx.put(
                f"{base}/pipelines/smoke", json=payload, headers=auth_headers, timeout=5.0
            )
            if put_res.status_code != 204:
                print(f"FAIL: PUT returned {put_res.status_code}: {put_res.text}", file=sys.stderr)
                return 1

            run_res = httpx.post(f"{base}/pipelines/smoke/run", headers=auth_headers, timeout=5.0)
            if run_res.status_code != 202:
                print(f"FAIL: run returned {run_res.status_code}: {run_res.text}", file=sys.stderr)
                return 1

            deadline = time.monotonic() + 15.0
            status = None
            while time.monotonic() < deadline:
                runs = httpx.get(
                    f"{base}/pipelines/smoke/runs", headers=auth_headers, timeout=2.0
                ).json()
                status = runs[0]["status"] if runs else None
                if status in ("succeeded", "failed"):
                    break
                time.sleep(0.2)

            if status != "succeeded" or not out_path.exists():
                print(
                    f"FAIL: run status={status}, output exists={out_path.exists()}", file=sys.stderr
                )
                return 1

            print(f"OK: frozen sidecar ran reader.file -> writer.file, output at {out_path}")
            return 0
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
