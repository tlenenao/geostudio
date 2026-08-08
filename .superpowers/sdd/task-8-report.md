# Task 8 Report — `app/alerts/notify.py` (webhook + SMTP email delivery)

## What I implemented

`core/app/alerts/notify.py` (new), consumed by Task 9 (`app.alerts.jobs`):

- `NotifyError` — always raised on delivery failure, never a raw
  `requests`/`smtplib`/`EgressBlockedError` exception escaping to the caller.
- `send_webhook(channel: AlertChannelWebhook, *, payload: dict) -> None` —
  posts JSON to the channel's user-supplied URL, egress-guarded.
- `send_email(session, *, tenant_id, channel: AlertChannelEmail, subject, body) -> None`
  — delivers via SMTP using the admin-configured secret named by
  `channel.smtpSecretName` (Task 7's `SmtpCredentialsPayload`), implemented
  exactly as dictated in the brief (no issues found there).

### The webhook-session correction (and why)

The brief's Step 3 code called `assert_egress_allowed(channel.url)` once,
then delivered via plain `requests.post(channel.url, json=payload,
timeout=10)`. `requests.post` follows HTTP redirects by default, and each
redirect hop is **not** re-checked against the egress guard — only the
one-time check on the original URL happens. A webhook URL that looks
public but 302-redirects to an internal address (e.g. the cloud metadata
endpoint `http://169.254.169.254/...`) would pass the one-time check and
then get followed anyway, defeating the guard.

Fix (per the task instructions, using Task 6's already-merged
`app/alerts/egress.py`):

```python
def send_webhook(channel: AlertChannelWebhook, *, payload: dict) -> None:
    try:
        assert_egress_allowed(channel.url)          # fail fast, upfront
    except EgressBlockedError as exc:
        raise NotifyError(f"webhook egress blocked: {exc}") from exc

    session = build_guarded_session()                # Task 6
    try:
        resp = session.post(channel.url, json=payload, timeout=10)
        resp.raise_for_status()
    except EgressBlockedError as exc:                 # raised on a redirect hop
        raise NotifyError(f"webhook egress blocked: {exc}") from exc
    except requests.RequestException as exc:
        raise NotifyError(f"webhook delivery failed: {exc}") from exc
```

`build_guarded_session()`'s `_GuardedHTTPAdapter.send()` calls
`assert_egress_allowed(request.url)` on every hop `requests`'
`resolve_redirects()` sends through it (not just the first), so a
redirect to an internal target now raises `EgressBlockedError`, which is
caught and wrapped in `NotifyError` just like the upfront check.

## What I verified before finalizing the tests

- `core/app/secrets/crypto.py`: `load_master_key()` re-reads
  `os.environ["CORE_SECRETS_MASTER_KEY"]` on **every call** — there is no
  `_MASTER_KEY` module attribute (the brief's dictated test referenced a
  phantom `secrets_crypto._MASTER_KEY` / `load_master_key()`-if-not-loaded
  pattern that doesn't exist in the real module). `encrypt()`/`decrypt()`
  are the real function names, matching the brief's guess.
- `core/tests/test_secrets_repository.py`'s own round-trip test sets up a
  decryptable secret via `monkeypatch.setenv("CORE_SECRETS_MASTER_KEY",
  TEST_KEY_B64)` before calling `crypto.encrypt(...)`. I copied this exact
  pattern into a `smtp_secret_session` pytest fixture (taking `monkeypatch`
  as a parameter) instead of the brief's free-standing helper function
  that couldn't call `monkeypatch.setenv` at all.
- `core/app/secrets/repository.py`: `create_secret(session, *, tenant_id,
  created_by, name, kind, ciphertext, nonce)` and `get_secret_payload(...)`
  signatures match the brief's usage verbatim.
- `AlertChannelWebhook`/`AlertChannelEmail` (`app/configs/schemas.py`) and
  `SmtpCredentialsPayload` (`app/secrets/schemas.py`) field names all match
  the brief's usage verbatim (`url`; `to`, `smtpSecretName`; `host`, `port`,
  `username`, `password`, `useTls`, `fromAddress`).
- A second, independent latent bug in the brief's dictated tests (separate
  from the known SSRF issue): `test_send_webhook_posts_json_to_the_url` /
  `test_send_webhook_wraps_a_request_failure` used
  `AlertChannelWebhook(url="https://example.test/hook")` with no DNS
  mocking. `example.test` is an RFC 2606 reserved TLD that never resolves
  (confirmed directly: `socket.getaddrinfo("example.test", None)` raises
  `gaierror` in this sandbox) — `assert_egress_allowed` would raise
  `EgressBlockedError` ("hôte non résoluble") before ever reaching the
  webhook-post logic the tests meant to exercise. Fixed by adding the same
  `getaddrinfo` monkeypatch the sister guard test suites already use
  (`test_alert_egress.py::test_allows_a_public_https_url`,
  `test_pipeline_egress.py`, `test_harvest_egress.py`).

## Tests written (`core/tests/test_alert_notify.py`)

1. `test_send_webhook_blocks_an_internal_url` — as dictated, unchanged (IP
   literal, no DNS needed).
2. `test_send_webhook_posts_json_to_the_url` — adapted: DNS-mocked, patches
   `app.alerts.notify.build_guarded_session` to return a `MagicMock()`
   session instead of patching `requests.post` (which is no longer called).
3. `test_send_webhook_wraps_a_request_failure` — same adaptation, mock
   session's `.post` raises `requests.ConnectionError`.
4. **New** `test_send_webhook_rechecks_egress_on_redirect_hops` — the
   redirect-based-bypass regression test. Fakes only the network I/O layer
   (`requests.adapters.HTTPAdapter.send`, the real base class method that
   would otherwise open a socket) to return a crafted 302 response pointing
   at `http://169.254.169.254/latest/meta-data/`; everything above that
   (`Session.send()`, `resolve_redirects()`, and the real
   `_GuardedHTTPAdapter.send()`'s egress check) runs for real via a real
   `build_guarded_session()`. Asserts `NotifyError` is raised **and** that
   its `__cause__` is specifically `EgressBlockedError` (not some unrelated
   failure).
5. **New** `test_guarded_session_used_by_send_webhook_blocks_before_connection`
   — minimal no-mocking sanity check mirroring
   `test_pipeline_egress.py::test_guarded_session_blocks_before_connection`.
6. `test_send_email_delivers_via_smtp_secret` — adapted only in the fixture
   plumbing (real crypto/repository APIs via `monkeypatch.setenv`), SMTP
   assertions unchanged from the brief.
7. `test_send_email_raises_when_secret_is_missing` — same fixture fix,
   unchanged assertions.

### Proof the redirect regression test actually catches the bug

I temporarily reverted `send_webhook` to the brief's naive
`requests.post(channel.url, ...)` implementation and re-ran
`test_send_webhook_rechecks_egress_on_redirect_hops` in isolation:

```
E       AssertionError: assert False
E        +  where False = isinstance(TooManyRedirects('Exceeded 30 redirects.'), EgressBlockedError)
E        +    where TooManyRedirects('Exceeded 30 redirects.') = NotifyError('webhook delivery failed: Exceeded 30 redirects.').__cause__
```

This confirms the test is discriminating: the naive implementation still
raises *some* `NotifyError` (because the plain `requests.Session` used by
`requests.post` keeps following the same 302 forever and eventually hits
`TooManyRedirects`), but the `__cause__` assertion proves it was **not**
the egress guard that stopped it — i.e., without the fix, an internal
redirect target is followed, not blocked. Restored the guarded-session fix
immediately after, and re-ran the full file to confirm green again.

## TDD Evidence

**RED** (before `app/alerts/notify.py` existed):
```
ImportError while importing test module '.../tests/test_alert_notify.py'.
E   ModuleNotFoundError: No module named 'app.alerts.notify'
1 error in 0.19s
```

**GREEN** (after implementation):
```
tests/test_alert_notify.py .......                                       [100%]
7 passed in 0.29s
```

**Full core suite** (regression check):
```
1255 passed, 131 skipped in 84.65s (0:01:24)
```
(131 skipped are the pre-existing `postgis`/`qgis`-marked tests requiring
docker, unrelated to this task.)

**Import-boundary lint** (`uv run lint-imports`):
```
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

`ruff` was not available in this environment (`error: Failed to spawn:
'ruff': No such file or directory`) — pre-existing environment gap, not
introduced by this task.

## Files changed

- `core/app/alerts/notify.py` (new)
- `core/tests/test_alert_notify.py` (new)

Commit: `9efab00` — `feat(core): SP-16b — app.alerts.notify (webhook via
guarded session + SMTP email delivery)`

## Self-review

- **Completeness**: all 7 tests pass, including the new redirect
  regression test and the SMTP tests using verified-real crypto/repository
  APIs. Full suite green, no regressions.
- **Quality**: webhook delivery genuinely re-checks egress on redirects —
  proven by reverting to the naive implementation and watching the
  regression test fail for a distinguishing reason (`TooManyRedirects`
  instead of `EgressBlockedError`), not just fail generically.
- **Discipline**: no extra retry logic, no extra channels, no scope creep.
  `send_email` implemented exactly as dictated (verified correct, no
  changes needed beyond the test fixture's crypto API names). Only the two
  files named in Code Organization were touched (confirmed via `git
  status` before commit — several unrelated pre-existing modifications to
  `.superpowers/sdd/*.md` files were left untouched/unstaged).
- **Testing**: the redirect test exercises the real `requests.Session` /
  `resolve_redirects()` machinery and the real `_GuardedHTTPAdapter.send()`
  — only the network I/O boundary (`HTTPAdapter.send`) is faked. This is
  not mocks-testing-mocks: it's a real integration test of the actual
  mechanism, independently confirmed to fail against the vulnerable
  implementation.

## Issues or concerns

None. The guarded-session approach worked exactly as Task 6 designed it
to; no conflicts encountered. No dependency on `responses`/`requests-mock`
was needed (neither is a project dependency, confirmed via `pyproject.toml`
grep) — the `HTTPAdapter.send`-level fake was sufficient and arguably more
faithful to the real mechanism than a mocking library would have been.
