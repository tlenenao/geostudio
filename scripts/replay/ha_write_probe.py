#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ARC-32 : « 0 écriture perdue » sous perte d'un réplica `core`, MESURÉ par comptage.

N fils écrivent en continu (POST /v1/configs, une app vide par écriture, titre unique) à travers le
LB ; à T+warmup la commande de perte est lancée (ex. `docker kill <réplica>`). Une écriture est
« acquittée » si le client a reçu un 2xx avec un itemId. Après la phase, CHAQUE écriture acquittée
est relue (GET /v1/items/{id}) : toute absence est une écriture perdue. Les écritures en échec
(connexion coupée en vol) sont « incertaines » : présentes ou non, ce n'est pas une perte.

  ha_write_probe.py --base https://localhost:8443/api --kill-cmd "docker kill X" \
      [--threads 4] [--warmup 3] [--after 15] [--max-recovery 30]

Sortie JSON ; code 1 si perdue > 0, si le service ne revient pas, ou si recovery_s > --max-recovery.
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
import uuid
from urllib.parse import urlparse

BODY = {
    "version": 1,
    "kind": "app",
    "theme": {},
    "dataSources": [],
    "messages": [],
    "layout": {"type": "grid", "breakpoints": {}, "items": []},
}


class Client:
    def __init__(self, base: str, timeout: float) -> None:
        self.u, self.timeout = urlparse(base), timeout
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        https = self.u.scheme == "https"
        cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
        kw = {"context": self.ctx} if https else {}
        # connexion neuve à chaque appel : on mesure le routage du LB, pas une connexion collée
        c = cls(self.u.hostname, self.u.port, timeout=self.timeout, **kw)
        try:
            data = json.dumps(body) if body is not None else None
            c.request(
                method,
                self.u.path + path,
                body=data,
                headers={
                    "Authorization": "Bearer ha-write-probe",
                    "Content-Type": "application/json",
                },
            )
            r = c.getresponse()
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else None)
        finally:
            c.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--kill-cmd", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--warmup", type=float, default=3.0)
    ap.add_argument("--after", type=float, default=15.0)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--max-recovery", type=float, default=30.0)
    a = ap.parse_args()
    cli = Client(a.base, a.timeout)
    tag = f"hawrite-{uuid.uuid4().hex[:8]}"
    lock = threading.Lock()
    acked: list[str] = []
    events: list[tuple[float, bool]] = []  # (t, ok)
    stop = threading.Event()

    def writer(n: int) -> None:
        i = 0
        while not stop.is_set():
            i += 1
            item = None
            try:
                st, js = cli.call(
                    "POST", "/v1/configs", {"title": f"{tag}-{n}-{i}", "config": BODY}
                )
                if st in (200, 201) and js and js.get("itemId"):
                    item = js["itemId"]
            except Exception:
                pass
            with lock:
                events.append((time.monotonic(), item is not None))
                if item:
                    acked.append(item)

    ths = [threading.Thread(target=writer, args=(n,)) for n in range(a.threads)]
    t0 = time.monotonic()
    for t in ths:
        t.start()
    time.sleep(a.warmup)
    kt = time.monotonic()
    subprocess.run(shlex.split(a.kill_cmd), check=False, capture_output=True)
    time.sleep(a.after)
    stop.set()
    for t in ths:
        t.join()

    post = sorted(e for e in events if e[0] >= kt)
    errs = [t for t, ok in post if not ok]
    oks = [t for t, ok in post if ok]
    recovered = bool(oks) and (not errs or oks[-1] > errs[-1])
    # bascule = du kill au premier succès suivant le DERNIER échec (0 s s'il n'y a eu aucun échec)
    recovery = 0.0
    if errs:
        after_last = [t for t in oks if t > errs[-1]]
        recovery = (after_last[0] - kt) if after_last else float("inf")

    missing = []
    for item_id in acked:
        for _ in range(3):
            try:
                st, _ = cli.call("GET", f"/v1/items/{item_id}")
                if st == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            missing.append(item_id)
    out = {
        "writes_attempted": len(events),
        "writes_acked": len(acked),
        "writes_failed_in_flight": len(events) - len(acked),
        "acked_missing_after": len(missing),
        "recovered": recovered,
        "recovery_s": round(recovery, 3) if recovery != float("inf") else None,
        "threads": a.threads,
        "duration_s": round(time.monotonic() - t0, 1),
    }
    print(json.dumps(out))
    return 0 if not missing and recovered and recovery <= a.max_recovery else 1


if __name__ == "__main__":
    sys.exit(main())
