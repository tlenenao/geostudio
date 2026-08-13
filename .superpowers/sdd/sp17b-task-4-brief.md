## Task 4: `render_export_task` builds the URL with `page_id`/`ctx`

**Files:**
- Modify: `core/app/export/jobs.py`
- Test: `core/tests/test_export_jobs.py` (extended)

**Interfaces:**
- Consumes: `ExportJob.page_id`/`ctx` (Task 3).
- Produces: no signature change — `render_export_task(job_id, tenant_id)` behavior only.

- [ ] **Step 1: Write the failing test**

Read `core/tests/test_export_jobs.py` first to find its existing fixture for asserting the navigated URL (it monkeypatches `_launch_and_navigate` — reuse that exact pattern). Add:

```python
def test_render_export_task_builds_url_with_page_id_and_ctx(monkeypatch, ...):  # reuse this file's existing fixture args
    captured_urls = []

    def fake_launch_and_navigate(url):
        captured_urls.append(url)
        return _FakePage()  # reuse this file's existing fake page helper

    monkeypatch.setattr(export_jobs, "_launch_and_navigate", fake_launch_and_navigate)
    # ... reuse this file's existing setup to create a job, but pass page_id/ctx:
    job = export_repo.create_job(
        session, tenant_id=tenant_id, item_id=item_id, user_id=user_id, format="pdf",
        page_id="page-2", ctx="abc123",
    )
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant_id)

    assert len(captured_urls) == 1
    assert f"/apps/{item_id}/page-2?exportToken=" in captured_urls[0]
    assert captured_urls[0].endswith("&ctx=abc123")


def test_render_export_task_url_unchanged_when_page_id_and_ctx_absent(monkeypatch, ...):
    captured_urls = []
    monkeypatch.setattr(export_jobs, "_launch_and_navigate", lambda url: captured_urls.append(url) or _FakePage())
    job = export_repo.create_job(session, tenant_id=tenant_id, item_id=item_id, user_id=user_id, format="pdf")
    session.commit()

    export_jobs.render_export_task(job_id=job.id, tenant_id=tenant_id)

    assert f"/apps/{item_id}?exportToken=" in captured_urls[0]
    assert "ctx=" not in captured_urls[0]
```

Adapt variable names (`session`, `tenant_id`, `item_id`, `user_id`, `_FakePage`) to whatever this file's existing tests actually call — do not invent new fixture names that collide with the file's conventions.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_export_jobs.py -k page_id -v`
Expected: FAIL — URL has no `/page-2` segment or `&ctx=`.

- [ ] **Step 3: Extend `render_export_task`**

In `core/app/export/jobs.py`, the job-fetch block currently reads:
```python
        job = export_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        export_repo.mark_running(session, job_id=job_id)
        item_id, user_id, export_format = job.item_id, job.user_id, job.format
```
Change the last line to also capture the two new columns:
```python
        item_id, user_id, export_format = job.item_id, job.user_id, job.format
        page_id, ctx = job.page_id, job.ctx
```

And the URL-building block:
```python
        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        target_url = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}?exportToken={token}&exportRender=1"
```
becomes:
```python
        from urllib.parse import quote

        token = mint_export_token(tenant_id=tenant_id, user_id=user_id, job_id=job_id)
        route = "maps" if config.kind == "map" else "apps"
        base = f"{os.environ['SHELL_BASE_URL']}/{route}/{item_id}"
        if page_id:
            base = f"{base}/{quote(page_id, safe='')}"
        target_url = f"{base}?exportToken={token}&exportRender=1"
        if ctx:
            target_url = f"{target_url}&ctx={ctx}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_export_jobs.py -v`
Expected: PASS, including the two new tests and all pre-existing ones.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/export/jobs.py core/tests/test_export_jobs.py
git commit -m "feat(core): render_export_task navigates to page_id/ctx when set (SP-17b)"
```

---

