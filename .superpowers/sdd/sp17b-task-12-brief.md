## Task 12: Wire `app.reports` into the worker, the API app, and the layer contract

**Files:**
- Modify: `core/app/jobs.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml`
- Test: none new — this task is pure wiring, verified by the full suite + `lint-imports`.

**Interfaces:**
- No new interfaces; this task makes Tasks 6-11's code reachable at runtime (procrastinate worker, FastAPI app) and satisfies the import-linter contract.

- [ ] **Step 1: Register the periodic task with the worker**

In `core/app/jobs.py`, add `"app.reports.jobs"` to `import_paths`:

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
        "app.export.jobs", "app.reports.jobs",
    ],
```

- [ ] **Step 2: Mount the reports router**

In `core/app/main.py`, add the import next to the other domain route imports:
```python
from app.public import routes as public_routes
from app.reports import routes as reports_routes
from app.secrets import crypto as secrets_crypto
```

And mount it unconditionally, right after `alerts_routes` (no capability flag — mirrors `alerts_routes`, not `pipelines_routes`/`export_routes`; a `ReportSchedule` can be created/listed/inspected even with `CORE_EXPORT_ENABLED=false`, it just fails cleanly at render time per the design's §5):
```python
    app.include_router(alerts_routes.router)
    app.include_router(reports_routes.router)
    if is_etl_enabled():
```

- [ ] **Step 3: Insert `app.reports` into the import-linter layer contract**

In `core/pyproject.toml`, in the `layers` list, insert `"app.reports",` between `"app.pipelines",` and `"app.alerts",`:

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.reports",
    "app.alerts",
    "app.export",
    "app.secrets",
    ...
```

And add a matching `ignore_imports` entry, next to the existing `app.db -> app.export.models` line (same reason as every other domain-models exception in that list — `app.db` is intentionally outside the layer contract, see the comment on `core/app/jobs.py`):
```toml
    "app.db -> app.export.models",
    "app.db -> app.reports.models",
]
```

- [ ] **Step 4: Verify the layer contract holds**

Run: `cd core && uv run lint-imports`
Expected: no violation reported (in particular, no complaint about `app.reports` importing `app.alerts.notify`/`app.export.repository`/`app.export.jobs`/`app.configs`/`app.items`/`app.sharing`/`app.audit`/`app.users`/`app.db`).

If `lint-imports` is not directly on PATH, run it via `uv run python -m importlinter`.

- [ ] **Step 5: Run the worker-registration test**

Run: `cd core && uv run pytest tests/test_jobs.py -v`
Expected: PASS — in particular `test_import_paths_registers_all_domain_tasks` (or equivalent) should now also see `sweep_report_schedules_task` registered.

- [ ] **Step 6: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: PASS (previous count + all new SP-17b tests), no regressions. `postgis`-marked tests will skip unless `CORE_TEST_DATABASE_URL` is set — that's expected locally.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/jobs.py core/app/main.py core/pyproject.toml
git commit -m "feat(core): wire app.reports into worker/app/import-linter contract (SP-17b)"
```

---

