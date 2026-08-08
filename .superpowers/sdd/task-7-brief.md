### Task 7: `SmtpCredentialsPayload` secret kind

**Files:**
- Modify: `core/app/secrets/schemas.py`
- Modify: `core/tests/test_secrets_schemas.py`

**Interfaces:**
- Produces: `SmtpCredentialsPayload` variant added to the `SecretPayload` union, consumed by Task 8 (`app.alerts.notify`).

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_secrets_schemas.py` (open the file first to match its existing style — it parametrizes over the 5 existing kinds; add a 6th case rather than a new file, since this is additive to the existing union test suite):

```python
def test_smtp_credentials_payload_round_trips():
    from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SmtpCredentialsPayload

    payload = SmtpCredentialsPayload(
        host="smtp.example.test", port=587, username="alerts@example.test",
        password="s3cret", useTls=True, fromAddress="alerts@example.test",
    )
    dumped = SECRET_PAYLOAD_ADAPTER.dump_python(payload)
    assert dumped["kind"] == "smtp"
    restored = SECRET_PAYLOAD_ADAPTER.validate_python(dumped)
    assert isinstance(restored, SmtpCredentialsPayload)
    assert restored.host == "smtp.example.test"
    assert restored.useTls is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_secrets_schemas.py -k smtp`
Expected: FAIL with `ImportError: cannot import name 'SmtpCredentialsPayload'`

- [ ] **Step 3: Write the implementation**

```python
# Add to core/app/secrets/schemas.py, alongside PostgresDsnPayload:
class SmtpCredentialsPayload(BaseModel):
    """SMTP credentials for AlertRule email delivery (SP-16b §5). Unlike
    the webhook channel's URL, this comes from an admin-only secret
    (POST /secrets is admin-only, SP-15e) rather than arbitrary per-rule
    user input — no egress guard applies to it (Global Constraints,
    SP-16b plan), same trust model as postgres_dsn."""
    kind: Literal["smtp"] = "smtp"
    host: str
    port: int
    username: str
    password: str
    useTls: bool = True
    fromAddress: str
```

```python
# Change the SecretPayload union:
SecretPayload = Annotated[
    ApiKeyPayload | BearerTokenPayload | BasicAuthPayload
    | OAuth2ClientCredentialsPayload | PostgresDsnPayload | SmtpCredentialsPayload,
    Field(discriminator="kind"),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_secrets_schemas.py`
Expected: all passing, including the new `test_smtp_credentials_payload_round_trips`.

Also run the full secrets suite to confirm the union change doesn't break existing routes/repository tests:

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_secrets_routes.py tests/test_secrets_repository.py tests/test_secrets_models.py`
Expected: unchanged, all passing.

- [ ] **Step 5: Commit**

```bash
git add core/app/secrets/schemas.py core/tests/test_secrets_schemas.py
git commit -m "feat(core): SP-16b — SmtpCredentialsPayload secret kind (additive)"
```

---

