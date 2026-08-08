# Task 2 report — AlertRule payload schema

## What was implemented

`core/app/configs/schemas.py`:
- New top-level imports: `app.analytics.aggregate.AggregateRequestBody`,
  `app.configs.alert_condition.validate_condition_expr`.
- New classes (inserted immediately before `BuilderConfig`, right after
  `PipelinePayload`): `AlertCondition` (wraps `validate_condition_expr` in a
  `model_validator(mode="after")`, wrapping any exception in `ValueError` so
  Pydantic surfaces it as a `ValidationError`), `AlertChannelWebhook`,
  `AlertChannelEmail`, `AlertRulePayload` (references `AggregateRequestBody`,
  `AlertCondition`, `PipelineRefreshPolicy`; two `model_validator(mode="after")`
  checks: at-least-one-channel, and v1 single-scalar-query — rejects
  `groupBy`/`split`/`bucket`/`bins`/more-than-one-measure).
- `BuilderConfig.kind` literal gains `"alert"`; new field
  `alert: AlertRulePayload | None = None`; `_require_kind_payload` gains the
  `alert` branch.

Implementation matches the brief's Step 3 code block verbatim — no
deviation, no extra fields/validation added.

`core/tests/test_alert_config_schema.py`: new file, the 9 tests from the
brief's Step 1, copied verbatim.

## Verification performed before implementing

- Confirmed current `app.configs.alert_condition.validate_condition_expr`
  signature: `validate_condition_expr(conn: duckdb.DuckDBPyConnection, expr:
  str) -> None`, raising `SqlSandboxError` (from
  `app.analytics.sql_sandbox`) on an invalid/table-referencing expression —
  matches what the brief's `_require_valid_expr` example expects (broad
  `except Exception` catches it regardless). Confirmed this is the
  post-two-fix-rounds version (table-function sandbox bypass + compute-bound
  DoS both closed) by reading the full current file, not the plan's Task 1
  text.
- Confirmed `PipelineRefreshPolicy`/`PipelinePayload`/`BuilderConfig`
  region of `schemas.py` matches the brief's assumed structure exactly
  (line numbers shifted slightly but content identical), including the
  exact `kind` literal and `_require_kind_payload` body before my edit.
- Confirmed `app.analytics.aggregate.AggregateRequestBody` fields
  (`groupBy`, `split`, `agg`, `field`, `measures`, `filters`, `bbox`,
  `geomIntersects`, `bucket`, `bins`) — matches the query-shape assertions
  in `_require_single_scalar_query`.
- Checked the import-linter layered-architecture contract
  (`core/pyproject.toml`): `app.analytics` is not part of the `layers` list
  at all, so `app.configs` importing from it is unconstrained — same
  precedent Task 1 already established (`alert_condition.py` already
  imports `app.analytics.sql_sandbox`). Ran `uv run lint-imports` after the
  change: **contract kept** (148 files, 428 dependencies analyzed, 1 kept /
  0 broken).
- Searched for any other place in `app/` duplicating the `BuilderConfig.kind`
  literal (e.g. a hand-mirrored schema) — none found; `schemas.py` is the
  single source.

## TDD evidence

### RED

```
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_config_schema.py
```
```
.F......F                                                                [100%]
=================================== FAILURES ===================================
__________________ test_alert_config_accepts_a_valid_payload ___________________
E       pydantic_core._pydantic_core.ValidationError: 1 validation error for BuilderConfig
E       kind
E         Input should be 'app', 'dashboard', 'map', 'site', 'dataset', 'bookmark' or 'pipeline' [type=literal_error, input_value='alert', input_type=str]
______________ test_alert_email_channel_requires_smtp_secret_name ______________
E       pydantic_core._pydantic_core.ValidationError: 1 validation error for BuilderConfig
E       kind
E         Input should be 'app', 'dashboard', 'map', 'site', 'dataset', 'bookmark' or 'pipeline' [type=literal_error, input_value='alert', input_type=str]
2 failed, 7 passed in 0.12s
```

(The other 7 tests passed "by accident" pre-implementation — they all
expect a `ValidationError`, and rejecting `kind="alert"` as an invalid
literal already raises one. Only the two tests that assert on successful
construction (`config.alert.*`) actually exercise the missing
implementation and failed, as expected per the brief's Step 2 note.)

### GREEN

```
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_config_schema.py
```
```
.........                                                                [100%]
9 passed in 0.53s
```

## Regression suite (brief Step 4)

```
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_bookmark_config_schema.py tests/test_dataset_config_schema.py tests/test_pipeline_config_schema.py
```
```
...................................                                      [100%]
35 passed in 0.19s
```

## Extra verification beyond the brief

- Full core test suite: `uv run pytest -q` → `1231 passed, 131 skipped in
  83.88s` (skips are pre-existing postgis/qgis markers per CLAUDE.md, not
  new).
- `uv run lint-imports` → layered architecture contract kept.

## Files changed

- `core/app/configs/schemas.py` (modified)
- `core/tests/test_alert_config_schema.py` (new)

Commit: `a46882c` — `feat(core): SP-16b — AlertRule payload schema
(BuilderConfig kind="alert")`

(Note: `.superpowers/sdd/progress.md` and `.superpowers/sdd/task-1-brief.md`
showed as modified in `git status` at commit time — not touched by this
task, not staged/committed, presumably owned by the orchestrating process.)

## Self-review

- **Completeness**: all 9 brief tests present and passing; regression suite
  (3 files, 35 tests) passing unchanged; full suite passing.
- **Quality**: validators follow the existing file's style exactly
  (`model_validator(mode="after")` returning `self`, `ValueError` for
  domain errors, comments explaining *why* not just *what*, matching the
  tone of `PipelineRefreshPolicy._require_valid_cron` and
  `PipelinePayload._validate_graph` already in the file). Import ordering
  follows existing convention (stdlib/pydantic first, then `app.*`).
- **Discipline**: implementation is the brief's Step 3 block verbatim —
  no additional fields, no additional validation, no scope creep. Did not
  touch `alert_condition.py`, `AggregateRequestBody`, or
  `PipelineRefreshPolicy` themselves, only referenced them, per
  instructions.
- **Testing**: tests exercise real Pydantic validation (not mocked) —
  invalid expr, table-reference rejection (delegates to the real
  `validate_condition_expr`/DuckDB AST check), empty channels, groupBy/
  measures-count/cron rejection, and a positive path reading back nested
  field values. Output is pristine (no warnings/errors beyond the expected
  test assertions).

## Issues or concerns

None. The current `schemas.py`/`alert_condition.py` state matched the
brief's assumptions exactly; no divergence to reconcile.

## Fix: channels discriminator

### What was found

Task-review flagged an Important finding on `AlertRulePayload.channels:
list[AlertChannelWebhook | AlertChannelEmail] = Field(default_factory=list)`
(line 269 at the time, now 275). Both variant classes give `kind` a default
(`kind: Literal["webhook"] = "webhook"` / `kind: Literal["email"] = "email"`),
so this was a bare (un-discriminated) union: Pydantic's smart-union mode does
not require the tag to be present in raw input when every variant's tag field
has a default. A payload missing `kind` entirely but carrying fields from
both shapes (e.g. `{"url": ..., "to": ..., "smtpSecretName": ...}`) silently
resolved to one variant (confirmed: `AlertChannelEmail`), silently dropping
`url` with no error — same *class* of "un-discriminated union with defaulted
tag" bug as the SP-14n `DatasetCrossFilterLink` precedent already guards
against with `Annotated[..., Field(discriminator="mode")]`.

### The fix

Mirrored the exact `DatasetCrossFilterLink` idiom (`core/app/configs/
schemas.py` lines 111-114) for the channels union: introduced a module-level
`AlertChannel` type alias

```python
AlertChannel = Annotated[
    AlertChannelWebhook | AlertChannelEmail,
    Field(discriminator="kind"),
]
```

placed right after `AlertChannelEmail` and before `AlertRulePayload`, and
changed `channels: list[AlertChannelWebhook | AlertChannelEmail]` to
`channels: list[AlertChannel]`. No other code in the repo references the
bare union type (`grep` for `AlertChannelWebhook\|AlertChannelEmail` outside
`schemas.py` and the test file returned nothing), so the change is fully
contained to the annotation.

### RED evidence

Added `test_alert_channel_missing_kind_is_rejected_not_silently_coerced` to
`core/tests/test_alert_config_schema.py`, constructing a channel payload
with `url`, `to`, and `smtpSecretName` but no `kind`, asserting
`pytest.raises(ValidationError)`. Against the pre-fix code:

```
cd core && uv run pytest tests/test_alert_config_schema.py -v
...
FAILED tests/test_alert_config_schema.py::test_alert_channel_missing_kind_is_rejected_not_silently_coerced
E       Failed: DID NOT RAISE ValidationError
1 failed, 9 passed in 1.14s
```

Confirms the bug reproduces exactly as described (silent coercion, no
error) before the fix.

### GREEN evidence

After applying the `Annotated[..., Field(discriminator="kind")]` fix:

```
cd core && uv run pytest tests/test_alert_config_schema.py tests/test_bookmark_config_schema.py tests/test_dataset_config_schema.py tests/test_pipeline_config_schema.py -v
...
45 passed in 0.59s
```

All 10 tests in `test_alert_config_schema.py` pass, including
`test_alert_email_channel_requires_smtp_secret_name` (channel WITH `kind`
present explicitly) — unaffected by the discriminator, confirming the fix
doesn't regress the legitimate tagged path. The 35 pre-existing tests in the
bookmark/dataset/pipeline config schema files (same regression suite Task 2
already ran) are unchanged.

Full core suite: `uv run pytest -q -m "not postgis"` → `1232 passed, 6
skipped, 125 deselected in 84.68s` — no regressions anywhere else in the
repo from touching `schemas.py` again.

### Files changed

- `core/app/configs/schemas.py` — added `AlertChannel` discriminated-union
  type alias; changed `AlertRulePayload.channels` annotation to use it.
- `core/tests/test_alert_config_schema.py` — added one regression test.

Commit: `fix(core): SP-16b Task 2 — discriminate AlertRulePayload.channels
by kind`

### Self-review

- **Scope**: change is exactly the two files named in the task, nothing
  else touched (verified via `git diff --stat` before commit).
- **Correctness**: the fix is the same idiom already proven correct
  elsewhere in this exact file (`DatasetCrossFilterLink`), not a novel
  pattern — low risk of a subtly-wrong Pydantic v2 discriminated-union
  syntax. Confirmed by the RED→GREEN transition on the new test.
- **No collateral damage**: `test_alert_email_channel_requires_smtp_secret_name`
  (positive case, `kind` present) still passes unchanged, confirming the
  discriminator doesn't break the legitimate authoring path (shell/MCP
  callers presumably always set `kind` when constructing channels — this
  fix only closes the silent-fallback hole for malformed/adversarial input
  missing the tag).
- **Test quality**: the new test asserts on the *absence-of-kind* case
  specifically (not just "any malformed payload"), matching the exact
  scenario in the finding, with a comment explaining why the bug existed
  (defaulted tag fields defeat Pydantic smart-union detection).

### Concerns

None. The fix is minimal, mirrors an established in-file precedent exactly,
and is verified by a real RED→GREEN cycle plus the full test suite with no
regressions.
