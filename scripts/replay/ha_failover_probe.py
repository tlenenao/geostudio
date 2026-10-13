#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ARC-18 : mesure (pas d'assertion de durée) de l'indisponibilité vue d'un client pendant la
perte d'un réplica `core`. Un client séquentiel sonde l'URL à cadence fixe ; à T+warmup, la
commande de perte (ex. `docker kill <conteneur>`) est lancée ; on relève les horodatages réels.

  ha_failover_probe.py --url https://localhost:8443/api/health --kill-cmd "docker kill X" \
      [--warmup 3] [--after 15] [--interval 0.02] [--timeout 1.0] [--max-window 5.0]

Sortie : un JSON (stdout) avec
  error_window_s     : dernier échec - premier échec après la perte (fenêtre où AU MOINS une requête échoue)
  max_gap_s          : plus long intervalle sans succès (= indisponibilité totale vue du client)
  errors / requests  : comptes bruts ;  recovered : un succès existe après le dernier échec
Code de sortie 1 si error_window_s > --max-window ou si le service n'est pas revenu à 100 % de succès.
"""

import argparse
import http.client
import json
import shlex
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse


def request_ok(u, timeout: float, ctx) -> bool:
    try:
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        kw = {"context": ctx} if u.scheme == "https" else {}
        # connexion neuve à chaque requête : on mesure le routage du LB, pas une connexion collée
        # à un réplica mort.
        c = cls(u.hostname, u.port, timeout=timeout, **kw)
        c.request("GET", u.path or "/", headers={"Host": u.hostname})
        r = c.getresponse()
        r.read()
        c.close()
        return 200 <= r.status < 400
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--kill-cmd", required=True)
    ap.add_argument("--warmup", type=float, default=3.0)
    ap.add_argument("--after", type=float, default=15.0)
    ap.add_argument("--interval", type=float, default=0.02)
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--max-window", type=float, default=5.0)
    a = ap.parse_args()
    u = urlparse(a.url)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    samples: list[tuple[float, bool]] = []
    kill_t: list[float] = []

    def kill() -> None:
        kill_t.append(time.monotonic())
        subprocess.run(shlex.split(a.kill_cmd), check=False, capture_output=True)

    t0 = time.monotonic()
    killer = None
    while time.monotonic() - t0 < a.warmup + a.after:
        now = time.monotonic()
        if killer is None and now - t0 >= a.warmup:
            killer = threading.Thread(target=kill)
            killer.start()
            time.sleep(0.01)
        samples.append((now, request_ok(u, a.timeout, ctx)))
        time.sleep(a.interval)
    if killer:
        killer.join()

    kt = kill_t[0] if kill_t else t0 + a.warmup
    pre_errors = sum(1 for t, ok in samples if t < kt and not ok)
    post = [(t, ok) for t, ok in samples if t >= kt]
    errs = [t for t, ok in post if not ok]
    oks = [t for t, ok in post if ok]
    window = (errs[-1] - errs[0]) if errs else 0.0
    # indisponibilité totale : plus long trou entre deux succès consécutifs (bornes : kill et fin)
    marks = [kt] + oks + [post[-1][0] if post else kt]
    max_gap = max((b - a_ for a_, b in zip(marks, marks[1:], strict=False)), default=0.0)
    recovered = bool(oks) and (not errs or oks[-1] > errs[-1])
    out = {
        "url": a.url,
        "kill_cmd": a.kill_cmd,
        "requests": len(samples),
        "errors_before_kill": pre_errors,
        "errors_after_kill": len(errs),
        "first_error_after_kill_s": round(errs[0] - kt, 3) if errs else None,
        "error_window_s": round(window, 3),
        "max_gap_s": round(max_gap, 3),
        "recovered": recovered,
        "interval_s": a.interval,
        "timeout_s": a.timeout,
    }
    print(json.dumps(out))
    return 0 if window <= a.max_window and recovered and pre_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
