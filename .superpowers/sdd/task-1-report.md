# Task 1 report — QGIS algorithm allowlist (generator + frozen schema)

## Status: DONE (supersedes the earlier BLOCKED status below)

The coordinator independently re-verified my two most consequential
findings from the first pass (`grass7:*` vs `grass:*`, and the
nonexistent `native:selectbyattribute`), the human decided the
replacement (`native:polygonstolines`), and the plan document + task
brief were corrected and regenerated. This report covers the completed
run against the corrected brief. The original BLOCKED writeup is kept
below for the record.

## What I implemented (second pass, against the corrected brief)

1. Rewrote `scripts/generate_qgis_algorithm_schemas.py` to match the
   regenerated brief exactly: corrected `ALLOWLIST_IDS` (6 prefix fixes +
   `native:polygonstolines` swap), and the grass7-aware `fetch_schema()`
   that chains `qgis_process plugins enable grassprovider` into the same
   `docker run` invocation as `help` for any `grass7:*` id (verified
   during Task 1's first pass that plugin-enable state does not survive
   across separate `--rm` containers).
2. Ran it for real against the pinned `qgis/qgis:release-3_34` image
   (already present locally, digest
   `sha256:8b976abef2e2f9376612b7597cca8b686338fa064f28d61dada167f8b17690cf`).
   First run hit a **new** shape issue not covered by the brief: for
   `qgis:tininterpolation` and `qgis:idwinterpolation`, the
   `INTERPOLATION_DATA` parameter's `"type"` field is a bare string
   (`"idw_interpolation_data"`) instead of the usual `{"id": ..., ...}`
   dict that every other parameter across all 50 algorithms uses. This
   crashed `fetch_schema()` at `p.get("type", {}).get("id", ...)` with
   `AttributeError: 'str' object has no attribute 'get'`.

   Unlike the allowlist-id problem, I judged this fixable in place rather
   than an escalation: it's a narrow, mechanical, backward-compatible
   normalization (`_type_id()` helper: dict → `.get("id")`, string → the
   string itself, anything else → `"unknown"`) that doesn't change the
   `{"type": str}` output contract Task 2/6 consume, and doesn't touch
   any of the id/decision questions that were the reason for the earlier
   escalation. Added it to `fetch_schema()` and reran clean.
3. Full run: 50/50 `fetching ...` lines, then
   `wrote 50 algorithms to .../qgis_algorithms.json`. Verified no
   `"unknown"` type leaked into the final file (grep across all 50
   entries × their parameters — zero matches).
4. Spot-checks (Step 2), all matched:
   - `native:simplifygeometries` params: `['INPUT', 'METHOD', 'OUTPUT', 'TOLERANCE']`
   - `native:centroids` params: `['ALL_PARTS', 'INPUT', 'OUTPUT']`
   - `native:dissolve.FIELD.optional` = `True`
   - `grass7:r.watershed.name` = `"r.watershed"`, `native:polygonstolines.name` = `"Polygons to lines"`
   - `qgis:tininterpolation.INTERPOLATION_DATA.type` = `"idw_interpolation_data"` (confirms the shape fix produced the intended value, not `"unknown"`)
5. Wrote the thin loader `core/app/pipelines/ops/qgis_algorithms.py`
   exactly as specified (verbatim from the brief).
6. Wrote `core/tests/test_pipeline_qgis_algorithms.py` with the corrected
   `EXPECTED_IDS` set (verbatim from the regenerated brief).

## Testing

```
$ cd core && uv run pytest tests/test_pipeline_qgis_algorithms.py -v
============================= test session starts ==============================
collected 6 items

tests/test_pipeline_qgis_algorithms.py::test_allowlist_has_exactly_fifty_algorithms PASSED [ 16%]
tests/test_pipeline_qgis_algorithms.py::test_allowlist_matches_expected_ids PASSED [ 33%]
tests/test_pipeline_qgis_algorithms.py::test_each_entry_has_name_and_nonempty_parameters PASSED [ 50%]
tests/test_pipeline_qgis_algorithms.py::test_simplify_required_params_match_spike_findings PASSED [ 66%]
tests/test_pipeline_qgis_algorithms.py::test_centroids_required_params_match_spike_findings PASSED [ 83%]
tests/test_pipeline_qgis_algorithms.py::test_dissolve_field_param_is_optional PASSED [100%]

============================== 6 passed in 0.04s ===============================
```

Also ran the full core suite to check for collateral breakage:

```
$ cd core && uv run pytest -q
1013 passed, 122 skipped in 63.99s (0:01:03)
```

(122 skipped are the pre-existing postgis/docker-marked tests, unrelated
to this task.)

## TDD note

This is the one task in the plan where generation precedes the test (per
the brief): the JSON was produced by the offline generator in Step 2,
and the tests written in Step 4 lock in what got generated rather than
driving new production code. There is no RED phase for the test file
itself — it was green on first run. The actual "red" moments in this
task were the two `CalledProcessError`/`AttributeError` crashes during
generation (bad ids, then the string-type shape), both diagnosed and
fixed before the JSON was ever written.

## Files changed (committed: `7c950ac`)

- `scripts/generate_qgis_algorithm_schemas.py` (created) — corrected
  `ALLOWLIST_IDS`, grass7-aware `fetch_schema()`, `_type_id()`
  normalization helper (my addition, beyond the brief's literal text,
  for the tininterpolation/idwinterpolation shape variance).
- `core/app/pipelines/ops/qgis_algorithms.json` (created, generated) — 50
  top-level keys, 1958 lines.
- `core/app/pipelines/ops/qgis_algorithms.py` (created) — thin loader,
  verbatim from brief.
- `core/tests/test_pipeline_qgis_algorithms.py` (created) — 6 tests,
  verbatim `EXPECTED_IDS` from the regenerated brief.

Not touched: any file outside this list (no shell/, no other core/
files). The plan document, progress ledger, and other task briefs shown
as modified in `git status` were edited by the coordinator, not by me —
left uncommitted/untouched on purpose since they're outside this task's
file list.

## Self-review

- Completeness: all 6 steps done, 50/50 algorithms generated for real
  (no mocking/fabrication — every id round-tripped through a real
  `docker run` against the pinned image), all 6 tests pass for real.
- Quality: the one deviation from the brief's literal code
  (`_type_id()`) is minimal, documented inline in French matching the
  file's existing comment style, and doesn't change the public
  `QGIS_ALGORITHMS` shape.
- Discipline: no files touched outside the task's 4-file list; commit
  scoped to exactly those 4 files via `git commit -- <paths>` even though
  `git status` shows many other modified/untracked files from the
  broader plan-correction work.
- Testing: `test_each_entry_has_name_and_nonempty_parameters` asserts
  `param["type"]` is a `str` for every parameter of every one of the 50
  real algorithms — this is what would have caught the tininterpolation
  shape bug had I not caught it manually during generation (since
  `_type_id()` never returns non-str). Ran pristine (no `--lf`/cache
  tricks), plus a full-suite run for collateral-damage detection.

## Concerns

- None blocking. One judgment call worth flagging: I fixed the
  tininterpolation/idwinterpolation type-shape bug myself instead of
  escalating a second time, since it was mechanical and didn't touch the
  id/policy question that caused the first escalation. If the
  coordinator wants that kind of fix escalated too in future tasks, say
  so.
- `native:extractbyattribute` remains in the (corrected) allowlist
  unchanged from the original brief — not part of this correction round,
  just noting it's a real, valid id (confirmed present in `qgis_process
  list` during the first pass's diff).

---

## (Superseded) Original BLOCKED report from the first pass

The task brief's `ALLOWLIST_IDS` (verbatim from
`docs/superpowers/plans/2026-08-06-sp15d-qgis-sidecar.md`) contained 7
algorithm ids that did not exist under the id/prefix given, verified
empirically against the actual pinned image `qgis/qgis:release-3_34`:

| Brief id (ALLOWLIST_IDS) | Problem | Real id (verified) |
|---|---|---|
| `native:minimumboundinggeometry` | wrong provider prefix | `qgis:minimumboundinggeometry` |
| `native:heatmapkerneldensityestimation` | wrong provider prefix | `qgis:heatmapkerneldensityestimation` |
| `native:selectbyattribute` | does not exist at all | (no equivalent found — human decided `native:polygonstolines`) |
| `grass:r.watershed` | wrong provider prefix | `grass7:r.watershed` |
| `grass:r.slope.aspect` | wrong provider prefix | `grass7:r.slope.aspect` |
| `grass:r.fill.dir` | wrong provider prefix | `grass7:r.fill.dir` |
| `grass:r.flow` | wrong provider prefix | `grass7:r.flow` |

The GRASS finding directly contradicted the plan document's explicit
claim that "the real GRASS algorithm namespace is `grass:*`, not
`grass7:*`" — verified via `grep -c grass:` = 0 vs `grep -c grass7:` =
306 against the same pinned image, and also confirmed `grassprovider` is
disabled by default and its enabled state doesn't survive across
separate `docker run --rm` invocations.

I stopped before writing the JSON/loader/tests/commit at that point
because fixing the "frozen" allowlist was a plan-level decision, not
something to silently patch. This has since been resolved as described
above.
