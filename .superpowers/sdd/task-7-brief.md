## Task 7: Docker Compose wiring

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `qgis-worker` service (profile `etl`), `etl-scratch` named
  volume shared with `worker`, `worker`'s new `QGIS_WORKER_URL`/
  `QGIS_WORKER_TIMEOUT_SECONDS` env vars + volume mount.

- [ ] **Step 1: Add the named volume**

Modify `docker-compose.yml`'s top-level `volumes:` section (currently
`pg-data:` and `minio-data:`, around line 5-8):

```yaml
volumes:
  pg-data:
  minio-data:
  etl-scratch:
```

- [ ] **Step 2: Add the `qgis-worker` service**

Add a new service block near `worker` (after the `worker:` block, around
line 176, before the `cdc-worker:` comment):

```yaml
  # Sidecar QGIS Processing étage 2 (SP-15d, arbitrage A39 — GPL en
  # sous-processus isolé, cœur Apache-2.0 intact). Profil `etl` : un
  # `docker compose up` par défaut ne le démarre pas, même porte que
  # CORE_ETL_ENABLED. Aucune credential DB, aucun accès réseau externe —
  # ne voit que le volume scratch partagé avec `worker` (garde
  # anti-confused-deputy, patron SP-6a).
  qgis-worker:
    build: ./deploy/qgis-worker
    profiles: ["etl"]
    environment:
      QT_QPA_PLATFORM: offscreen
    volumes:
      - etl-scratch:/scratch
    networks: [gis-net]
    restart: unless-stopped
```

- [ ] **Step 3: Wire `worker`'s env vars + volume**

Modify `docker-compose.yml`'s `worker:` service block — add to its
`environment:` section:

```yaml
      QGIS_WORKER_URL: http://qgis-worker:8000
      QGIS_WORKER_TIMEOUT_SECONDS: "600"
```

`worker:` (`docker-compose.yml:156-176`) has no `volumes:` key today —
add one, right after its `environment:` block and before `networks:
[gis-net]`:

```yaml
    volumes:
      - etl-scratch:/scratch
```

- [ ] **Step 4: Validate the compose file**

Run: `docker compose config --quiet`
Expected: no output, exit code 0 (valid YAML + valid compose schema).

Run: `docker compose --profile etl config --services`
Expected: includes `qgis-worker` in the service list (confirms the profile
gate works as intended — omit `--profile etl` and re-run to confirm
`qgis-worker` is absent from the default service list).

- [ ] **Step 5: Smoke-test the full compose service (manual, not automated)**

Run: `docker compose --profile etl build qgis-worker && docker compose --profile etl up -d qgis-worker`
Expected: service starts, `docker compose --profile etl logs qgis-worker`
shows no crash loop (the `ThreadingHTTPServer` from Task 4 blocks forever
on `serve_forever()`, so "no output, still running" after a few seconds is
the success signal).

Run: `docker compose --profile etl down`

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(deploy): wire qgis-worker into compose behind the etl profile"
```

---

