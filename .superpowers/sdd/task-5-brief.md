## Task 5: Arrêt propre `cdc-worker` (3.5b)

**Files:**
- Modify: `core/app/cdc/main.py` (`run()` gains a `should_stop` flag + `SIGTERM` handler + final flush)
- Test: `core/tests/test_cdc_main.py` (new, or extend an existing `test_cdc_*.py` if one already exercises `run()`-adjacent helpers — check first)

**Interfaces:**
- Consumes: nothing from Tasks 1-4.
- Produces: nothing consumed by later tasks.

**Context:** `core/app/cdc/consumer.py:227-235`'s `stream_changes(...)` already accepts a `should_stop: Callable[[], bool] = lambda: False` parameter and a `poll_timeout_s` — this is the hook. `core/app/cdc/main.py:97-205`'s `run()` currently calls `stream_changes(raw_dsn, on_message=_on_message, is_flush_due=..., do_flush=_do_flush)` without passing `should_stop`, so the loop never exits on its own. `_do_flush` (a closure inside `run()`, `main.py:148-151`) is exactly the function to call once more after the loop exits, to flush any buffered-but-unflushed rows before the process dies.

- [ ] **Step 1: Check for existing `cdc/main.py` test coverage**

```bash
cd core
find tests -iname "*cdc_main*" -o -iname "*test_cdc*"
grep -l "cdc.main\|cdc\.main" tests/*.py
```

If a `test_cdc_main.py` exists, read it fully before writing new tests — extend it rather than creating a duplicate file. If nothing tests `main.py`'s `run()` function or its helpers directly (likely, since `run()` requires a real `CDC_DATABASE_URL`/S3 client per its docstring/`_write_and_upload`'s own comment "extrait de _flush_table pour rester testable indépendamment de run() (qui exige DB/S3 réels)"), create a new file testing only the signal-handling mechanism in isolation — not `run()` itself.

- [ ] **Step 2: Write the failing test**

Create `core/tests/test_cdc_shutdown.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Teste uniquement le mécanisme d'arrêt (signal -> flag -> should_stop),
pas run() en entier — qui exige un DSN CDC_DATABASE_URL et un client S3
réels (cf. main.py::_write_and_upload, testée séparément pour la même
raison)."""
import signal

from app.cdc import main as cdc_main


def test_sigterm_sets_the_stop_flag():
    state = cdc_main._ShutdownState()
    assert state.should_stop() is False
    state.handle_sigterm(signal.SIGTERM, None)
    assert state.should_stop() is True
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd core
uv run pytest tests/test_cdc_shutdown.py -v
```

Expected: FAILS with `AttributeError: module 'app.cdc.main' has no attribute '_ShutdownState'`.

- [ ] **Step 4: Implement the shutdown state + wire it into `run()`**

Edit `core/app/cdc/main.py`, add near the top (after the `_WorkerState` class, before `build_s3_key`):

```python
class _ShutdownState:
    """État du signal SIGTERM (SP-26/3.5b) — séparé de _WorkerState (données
    métier) : ce flag n'a qu'un rôle, dire à stream_changes() de sortir de
    sa boucle proprement (cf. consumer.stream_changes's `should_stop`
    param, déjà prévu pour ça mais jamais branché avant ce chantier)."""

    def __init__(self) -> None:
        self._stop = False

    def should_stop(self) -> bool:
        return self._stop

    def handle_sigterm(self, signum, frame) -> None:
        self._stop = True
```

Edit `run()` — add the import (`import signal` at the top of the file, next to the existing `import os`/`import threading`/etc.), instantiate the state, register the handler, and pass `should_stop` + do a final flush after the loop returns:

```python
def run() -> None:
    raw_dsn = os.environ["CDC_DATABASE_URL"]
    engine = make_engine(raw_dsn.replace("postgresql://", "postgresql+psycopg://"))
    session_factory = make_session_factory(engine)
    s3_bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    s3_client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(s3_client, s3_bucket)

    state = _WorkerState()
    shutdown = _ShutdownState()
    signal.signal(signal.SIGTERM, shutdown.handle_sigterm)
    observability.register_cdc_lag_gauge(state.get_lag_seconds)

    consumer.ensure_replication_slot(raw_dsn)

    # ... (backfill loop unchanged) ...

    # ... (_flush_table, _do_flush, _on_message closures unchanged) ...

    consumer.stream_changes(
        raw_dsn,
        on_message=_on_message,
        is_flush_due=lambda: bool(buffer.tables_due_for_flush()),
        do_flush=_do_flush,
        should_stop=shutdown.should_stop,
    )
    # stream_changes() ne flushe que quand is_flush_due() est vrai PENDANT
    # la boucle — un SIGTERM peut arriver avec des lignes déjà bufferisées
    # mais pas encore dues à l'âge (30s). Flush final explicite avant
    # sortie, même mécanisme que _do_flush, appelé une dernière fois.
    _do_flush()
```

Do not restructure the closures (`_flush_table`, `_do_flush`, `_on_message`, the backfill loop) — only add the 3 lines shown (`shutdown = _ShutdownState()`, `signal.signal(...)`, `should_stop=shutdown.should_stop` in the `stream_changes` call) and the final `_do_flush()` call after it returns. Leave everything else in `run()` exactly as-is.

- [ ] **Step 5: Run the new test and the full suite**

```bash
cd core
uv run pytest tests/test_cdc_shutdown.py -v
uv run pytest -x -q
```

Expected: new test passes; full suite unaffected (no existing test calls `run()` directly, confirmed in Step 1).

- [ ] **Step 6: Commit**

```bash
git add core/app/cdc/main.py core/tests/test_cdc_shutdown.py
git commit -m "$(cat <<'EOF'
feat(core): arrêt propre du cdc-worker sur SIGTERM

stream_changes() acceptait déjà un paramètre should_stop, jamais
branché — SIGTERM positionne un flag vérifié à chaque itération, puis
un flush final avant sortie pour ne pas perdre les lignes bufferisées
non encore dues à l'âge (I11, revue de projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

