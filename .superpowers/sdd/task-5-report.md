# Task 5 Report: `app/alerts/repository.py`

## What was implemented

`core/app/alerts/repository.py` — CRUD for `AlertEvaluation` (Task 4's model) plus
`list_due_rules(session)`, modeled explicitly on `app.pipelines.repository.list_due_pipelines`
(SP-15h):

- `create_evaluation(session, *, tenant_id, alert_rule_item_id) -> AlertEvaluation` — inserts a
  `state="pending"` row.
- `mark_evaluated(session, *, evaluation_id, value, state, transitioned, error=None) -> None`.
- `get_evaluation(session, *, tenant_id, evaluation_id) -> AlertEvaluation | None` (not required by
  the brief's public interface list, but present in the brief's dictated code — kept, tenant-scoped
  lookup by id, symmetrical with the rest of the module).
- `get_latest_evaluation(session, *, tenant_id, alert_rule_item_id) -> AlertEvaluation | None`.
- `list_evaluations(session, *, tenant_id, alert_rule_item_id) -> list[AlertEvaluation]` (most
  recent first).
- `list_due_rules(session) -> list[tuple[str, str]]` — cross-tenant sweep over
  `configs_repo.list_configs_by_kind(session, kind="alert")`, same reclaim-by-age discipline as
  pipelines (`_PENDING_RECLAIM_MINUTES = 60`), never exposed via a route.

Implemented the brief's dictated code as-is after verifying it against the real codebase (see
Self-review below) — no changes were needed to the dictated implementation.

## What was tested and test results

`core/tests/test_alert_repository.py`, the 6 tests specified in the brief:

1. `test_create_and_mark_evaluated_round_trip`
2. `test_list_due_rules_includes_a_rule_with_no_prior_evaluation`
3. `test_list_due_rules_excludes_a_disabled_rule`
4. `test_list_due_rules_excludes_a_rule_evaluated_within_its_cron_interval`
5. `test_list_due_rules_reclaims_a_stuck_pending_evaluation`
6. `test_list_evaluations_orders_most_recent_first`

Result: `6 passed`.

Full repo suite after the change: `1242 passed, 131 skipped` (the skipped are the pre-existing
`postgis`-marked tests requiring docker, per CLAUDE.md's documented baseline) — no regressions.

## TDD Evidence

**RED** — before creating `app/alerts/repository.py`:

```
$ PYTHONPATH=. CORE_SECRETS_MASTER_KEY=... uv run pytest -q tests/test_alert_repository.py
ImportError while importing test module '.../tests/test_alert_repository.py'.
E   ImportError: cannot import name 'repository' from 'app.alerts' (.../app/alerts/__init__.py)
1 error in 0.10s
```

**GREEN** — after implementing `app/alerts/repository.py`:

```
$ PYTHONPATH=. CORE_SECRETS_MASTER_KEY=... uv run pytest -q tests/test_alert_repository.py
......                                                                   [100%]
6 passed in 0.98s
```

## Files changed

- `core/app/alerts/repository.py` (new)
- `core/tests/test_alert_repository.py` (new)

Commit: `0c283d8 feat(core): SP-16b — app.alerts.repository (evaluations CRUD, list_due_rules)`
(only these two files staged/committed — verified with `git status --short` before commit that no
other tracked/untracked files were swept in; pre-existing uncommitted modifications to
`.superpowers/sdd/*` from earlier tasks in this session were left untouched).

## Self-review

### Verification against the real codebase (before trusting the brief's dictated code)

Per the task's explicit instruction to treat every prior task's plan-dictated code as suspect
(Tasks 1 and 2 each had real bugs), I read the actual current implementations rather than assuming
the brief's descriptions were accurate:

- **`app.pipelines.repository.list_due_pipelines`** (real code read in full): confirms the same
  `_RUNNING_RECLAIM_MINUTES = 60` reclaim-by-age pattern, the same tz-guard
  (`if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=timezone.utc)`), and the
  same `croniter.croniter(policy.cron, created_at).get_next(datetime)` cron-tick call. One
  meaningful difference: pipelines have a three-state non-terminal lifecycle (`queued` → `running`
  → terminal) and use `started_at` (when present) as the reclaim anchor for `running` rather than
  `created_at`, with an explicit comment explaining why (a run queued a long time before actually
  starting shouldn't be reclaimed the instant it starts running). Alerts have only a two-state
  lifecycle (`pending` → terminal, no separate "started" mark) — there is no `started_at` column on
  `AlertEvaluation` at all — so the brief's simpler single-anchor (`created_at`) reclaim check for
  `pending` is the *correct* mirror, not a regression or an omitted case. This is a real, understood
  divergence from the mirrored function, not an unnoticed one.
- **`app.configs.repository.list_configs_by_kind`** (real code read): signature and behavior match
  exactly what the brief and the task instructions assumed —
  `(session, kind: str) -> list[tuple[str, str, BuilderConfig]]`, cross-tenant, skips items with a
  corrupted/unparseable stored config rather than raising.
- **`app.alerts.models.AlertEvaluation`** (Task 4, real code read): fields
  `id, tenant_id, alert_rule_item_id, value, state, transitioned, error, created_at` match every
  field the brief's repository code and tests reference.
- **`app.configs.schemas.AlertRulePayload.refreshPolicy`** (real code read): typed
  `PipelineRefreshPolicy` (non-optional, unlike `PipelinePayload.refreshPolicy` which is
  `| None`), with fields `enabled: bool` and `cron: str` (validated by croniter at parse time via a
  `model_validator`). The brief's `if not policy.enabled` check (no `None` guard) is correct given
  the field is required on the alert payload.
- **`croniter` API**: confirmed `croniter.croniter(cron_str, start_dt).get_next(datetime)` is the
  exact call signature already used by `list_due_pipelines`, and the installed version
  (`croniter>=6.2`, `uv.lock` pins `6.2.4`) supports it.

No drift found between the brief's assumptions and the real code. No changes to the brief's
dictated implementation were necessary.

### Hand-trace of `list_due_rules` against each of the 6 test scenarios

1. **`test_create_and_mark_evaluated_round_trip`** — no cron/reclaim logic exercised; plain CRUD.
   `create_evaluation` inserts `state="pending"`; `mark_evaluated` overwrites
   `value/state/transitioned/error`; `get_latest_evaluation` orders by `created_at desc limit 1`.
   Traced: passes trivially.

2. **`test_list_due_rules_includes_a_rule_with_no_prior_evaluation`** — `get_latest_evaluation`
   returns `None` for a freshly-seeded rule → `list_due_rules` hits the `if latest is None:
   due.append(...); continue` branch unconditionally. Traced: `(rule_id, tenant.id)` is added.
   Matches assertion.

3. **`test_list_due_rules_excludes_a_disabled_rule`** — `refreshPolicy.enabled=False` →
   `if not policy.enabled: continue` fires before any evaluation lookup. Traced: never added,
   `list_due_rules(s) == []`. Matches assertion.

4. **`test_list_due_rules_excludes_a_rule_evaluated_within_its_cron_interval`** — one evaluation
   created and immediately `mark_evaluated(..., state="ok", ...)` (terminal, not `"pending"`), so
   the `pending`-branch is skipped and control falls to
   `next_tick = croniter.croniter(policy.cron, created_at).get_next(datetime)`. `created_at` is
   ~"now" (just inserted) and `cron = "*/5 * * * *"`. `croniter.get_next` returns the next tick
   strictly *after* the start time, i.e. at most 5 minutes in the future — always `> now` (evaluated
   microseconds later in the same test). So `next_tick <= now` is `False` → not added. Traced:
   `list_due_rules(s) == []`. Matches assertion. (This is the scenario that genuinely exercises the
   cron-interval arithmetic, not a tautology — it depends on `croniter` correctly computing "more
   than 0 and up to 5 minutes from now.")

5. **`test_list_due_rules_reclaims_a_stuck_pending_evaluation`** — an evaluation is created
   (`state="pending"`) and then its `created_at` is *directly mutated* on the ORM object to
   `now - 120min` and committed, without ever calling `mark_evaluated` (simulating a worker that
   died mid-evaluation). In `list_due_rules`: `latest.state == "pending"` is true, so
   `(now - created_at) < timedelta(minutes=60)` is evaluated: `now - created_at ≈ 120min`, which is
   *not* `< 60min` → falls through to `due.append(...)`. Traced: `(rule_id, tenant.id)` is in the
   result. Matches assertion. This genuinely exercises the age-based reclaim threshold (120min stuck
   vs. the 60min cutoff), not a tautology.

6. **`test_list_evaluations_orders_most_recent_first`** — two evaluations created and marked in
   sequence; `list_evaluations` orders by `created_at desc`. Traced: `[second.id, first.id]`.
   Matches assertion (no cron logic involved).

### Timezone-guard verification (not just read, actually probed)

The task instructions specifically asked to confirm the `if created_at.tzinfo is None: ...
replace(tzinfo=timezone.utc)` guard is necessary and correctly placed rather than assumed. I did
not just read it — I empirically probed it:

- Confirmed `make_session_factory` uses `sessionmaker(bind=engine, expire_on_commit=False)`
  (`core/app/db.py`). This means within the *same* SQLAlchemy session, an ORM object's Python
  attributes are never expired/reloaded after `commit()`, so the in-memory `datetime` objects
  created in these tests keep whatever `tzinfo` they were constructed with — the unit tests
  therefore do **not** by themselves force a true DB round-trip of the timestamp's timezone
  representation within a single session.
- I then temporarily removed the guard and re-ran the affected tests in isolation: they still
  passed, confirming point above (same-session identity-map reuse masks the naive/aware
  distinction in this specific test harness).
- I separately confirmed, via a raw insert probe, that the bound SQL parameter for a `DateTime`
  column (no `timezone=True`) on `created_at` is rendered as a plain string with no UTC offset
  (`'2026-08-07 23:42:31.460260'`) — i.e., on a genuinely fresh read (a different session/process,
  such as a periodic worker task calling `list_due_rules` against Postgres or a freshly-opened
  SQLite connection), the column comes back **naive**. `_now()` always writes
  `datetime.now(timezone.utc)`, so a naive value read back is implicitly UTC.
- Conclusion: the guard is not exercised as load-bearing by *this specific* in-memory,
  single-session unit test, but it is **necessary** for the real production path — `list_due_rules`
  is invoked by a periodic sweep job (`app.alerts.jobs`, Task 9) in a separate session/process from
  whatever wrote the evaluation, where the naive-on-read behavior is real and would otherwise raise
  `TypeError: can't subtract offset-naive and offset-aware datetimes` the first time `now -
  created_at` executes with a genuinely fresh read. It is placed correctly: applied once,
  immediately after fetching `latest.created_at`, before it is used by either the `pending`-reclaim
  arithmetic or the `croniter` call, so both consumers of `created_at` are covered by the same
  guard. No case is missing and it is not redundant — it is dormant-but-correct in the unit-test
  harness and load-bearing in production, exactly mirroring `list_due_pipelines`'s identical guard
  for its `created_at`.

### Discipline / scope

Touched only `core/app/alerts/repository.py` and `core/tests/test_alert_repository.py`, per the
Code Organization constraint. Did not add anything beyond the brief (kept `get_evaluation`, which
is in the brief's dictated code even though not listed in the "Produces" interface list — it's a
natural, harmless CRUD primitive consistent with the module's style, not scope creep beyond what
was dictated).

## Issues or concerns

None. The brief's dictated code was verified correct against the real
`list_due_pipelines`/`list_configs_by_kind`/`AlertEvaluation`/`AlertRulePayload`/`croniter`
implementations, all 6 tests were confirmed RED then GREEN, the reclaim and cron-interval tests
were hand-traced and confirmed to genuinely exercise time-based logic, the timezone guard was
empirically probed (not just assumed) and confirmed necessary for the real cross-session/process
production path even though dormant in this specific same-session test harness, and the full
1242-test suite passes with no regressions.
