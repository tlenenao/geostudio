## Task 8: Notifier les alertes SLO (3.7)

**Files:**
- Create: `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml`
- Create: `deploy/observability/grafana/provisioning/alerting/policies.yaml`
- Modify: `docker-compose.yml` (wire `GRAFANA_ALERT_WEBHOOK_URL` to the `otel-lgtm` service, add an envsubst step if native `${VAR}` expansion isn't supported — determined empirically in Step 1)
- Modify: `.env.example` (document `GRAFANA_ALERT_WEBHOOK_URL`)
- Test: manual verification via the existing `test-alert-do-not-keep-in-prod` rule already in `rules.yaml`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing consumed by later tasks.

**Context:** `deploy/observability/grafana/provisioning/alerting/rules.yaml` is bind-mounted wholesale into `grafana/otel-lgtm:0.11.4`'s Grafana provisioning path (`docker-compose.yml`'s `otel-lgtm` service, `./deploy/observability/grafana/provisioning/alerting:/otel-lgtm/grafana/conf/provisioning/alerting`) — any file added to the local directory appears in the container automatically, no compose change needed for the files themselves, only for the env var they reference. The file already contains a `test-alert-do-not-keep-in-prod` group with `isPaused: true`, built specifically to prove the notification pipeline end-to-end without depending on real traffic.

- [ ] **Step 1: Determine whether this Grafana version supports native `${VAR}` expansion in provisioning files**

```bash
docker run --rm grafana/otel-lgtm:0.11.4 grafana-server -v 2>&1 | head -5
```

Note the Grafana version. Check Grafana's changelog/docs for when `${...}` expansion in provisioning files landed (this requires either checking Grafana's actual behavior in a running container, or consulting docs — do not guess). Pragmatic empirical check instead of reading changelogs:

```bash
mkdir -p /tmp/grafana-envtest/provisioning/alerting
cat > /tmp/grafana-envtest/provisioning/alerting/contactpoints.yaml <<'EOF'
apiVersion: 1
contactPoints:
  - orgId: 1
    name: test-cp
    receivers:
      - uid: test-cp-webhook
        type: webhook
        settings:
          url: ${TEST_WEBHOOK_URL}
EOF
docker run --rm -e TEST_WEBHOOK_URL=https://example.test/hook \
  -v /tmp/grafana-envtest/provisioning/alerting:/otel-lgtm/grafana/conf/provisioning/alerting \
  -p 13000:3000 -d --name grafana-envtest grafana/otel-lgtm:0.11.4
sleep 15
docker exec grafana-envtest grep -r "url" /otel-lgtm/grafana/conf/provisioning/alerting/ 2>/dev/null
# Si le fichier monté est relu tel quel par ce grep (normal, c'est un bind
# mount côté fichier) — le vrai test est de savoir si GRAFANA a résolu
# ${TEST_WEBHOOK_URL} en interne. Interroger l'API de contact points :
curl -s -u admin:admin http://localhost:13000/api/v1/provisioning/contact-points | grep -o '"url":"[^"]*"'
docker rm -f grafana-envtest
rm -rf /tmp/grafana-envtest
```

If the API response shows the literal string `example.test` (resolved), native expansion works — proceed to Step 2a. If it shows the literal unexpanded `${TEST_WEBHOOK_URL}` string, native expansion is NOT supported at this version — proceed to Step 2b instead.

- [ ] **Step 2a: (if native expansion works) Create the contact point and policy files directly with `${GRAFANA_ALERT_WEBHOOK_URL}`**

Create `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml`:

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: geostudio-webhook
    receivers:
      - uid: geostudio-webhook-receiver
        type: webhook
        settings:
          url: ${GRAFANA_ALERT_WEBHOOK_URL}
```

Create `deploy/observability/grafana/provisioning/alerting/policies.yaml`:

```yaml
apiVersion: 1
policies:
  - orgId: 1
    receiver: geostudio-webhook
    routes:
      - receiver: geostudio-webhook
        object_matchers:
          - ["slo", "=~", ".+"]
        continue: false
```

Edit `docker-compose.yml`'s `otel-lgtm` service to pass the variable through:

```yaml
  otel-lgtm:
    image: grafana/otel-lgtm:0.11.4
    profiles: ["observability"]
    environment:
      GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-}
    ports:
```

- [ ] **Step 2b: (if native expansion does NOT work) Use an envsubst wrapper via a custom entrypoint override**

Create `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml.template`:

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: geostudio-webhook
    receivers:
      - uid: geostudio-webhook-receiver
        type: webhook
        settings:
          url: ${GRAFANA_ALERT_WEBHOOK_URL}
```

Create `deploy/observability/grafana/provisioning/alerting/policies.yaml` (no substitution needed, static content — same as Step 2a's version).

Edit `docker-compose.yml`'s `otel-lgtm` service to render the template before Grafana starts, overriding its default entrypoint:

```yaml
  otel-lgtm:
    image: grafana/otel-lgtm:0.11.4
    profiles: ["observability"]
    environment:
      GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-}
    entrypoint:
      - sh
      - -c
      - |
        apk add --no-cache gettext 2>/dev/null || true
        envsubst < /otel-lgtm/grafana/conf/provisioning/alerting/contactpoints.yaml.template > /otel-lgtm/grafana/conf/provisioning/alerting/contactpoints.yaml
        exec /run-all.sh
    ports:
```

Check the image's real default entrypoint/startup script first — `docker run --rm --entrypoint sh grafana/otel-lgtm:0.11.4 -c "cat /run-all.sh 2>/dev/null || find / -maxdepth 2 -iname '*run*' -o -iname '*entrypoint*' 2>/dev/null"` — replace `/run-all.sh` above with whatever the actual startup script is named; do not guess it blindly, this determines whether the container starts at all.

Do NOT create `contactpoints.yaml` (final, non-template) directly in git in this branch — only the `.yaml.template` is committed; the rendered `.yaml` is generated at container start and should be added to `.gitignore` if it would otherwise land in the bind-mounted host directory (check: does the entrypoint write into the bind-mounted path, meaning the rendered file appears on the host too? If so, add `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml` to `.gitignore`).

- [ ] **Step 3: Document the new variable**

Edit `.env.example`, near the existing observability section (find it with `grep -n "OTEL\|observability" .env.example`):

```
# Point de contact webhook pour les alertes SLO Grafana (SP-26/3.7) — vide
# par défaut, aucune notification tant que l'opérateur ne le renseigne pas.
# Voir deploy/observability/grafana/provisioning/alerting/rules.yaml.
GRAFANA_ALERT_WEBHOOK_URL=
```

- [ ] **Step 4: Verify the deployability guard**

```bash
cd core
uv run pytest tests/test_deployability.py -v
```

Expected: 31/31 still green — `GRAFANA_ALERT_WEBHOOK_URL` is now both a `${...}` substitution in `docker-compose.yml` and documented in `.env.example`.

- [ ] **Step 5: Prove end-to-end delivery using the existing test-alert rule**

```bash
export GRAFANA_ALERT_WEBHOOK_URL=https://webhook.site/<get-a-real-test-url-first>
docker compose --profile observability up -d otel-lgtm
```

Get a real disposable webhook URL first (e.g. from `webhook.site` or `requestbin`, or run a trivial local HTTP listener `python3 -m http.server 9999` and use `http://host.docker.internal:9999` if the CI/dev environment supports host networking — pick whichever is actually reachable in this environment; don't fabricate a URL you can't observe).

Edit `deploy/observability/grafana/provisioning/alerting/rules.yaml`'s `test-alert-do-not-keep-in-prod` group, flip `isPaused: true` to `isPaused: false` **temporarily** (do not commit this flip):

```bash
docker compose --profile observability restart otel-lgtm
sleep 15
# Observe the webhook receiver — expect one delivered notification within ~10-20s
```

Confirm a notification actually arrived at the webhook target. Then revert `isPaused` back to `true` in the file (it must never ship as `false`) and restart again to confirm it stops firing.

```bash
git diff deploy/observability/grafana/provisioning/alerting/rules.yaml
# Expected: empty — isPaused restored to true, no unintended change committed
docker compose --profile observability down
```

- [ ] **Step 6: Commit**

```bash
git add deploy/observability/grafana/provisioning/alerting/ docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(deploy): notifie les alertes SLO Grafana par webhook

Point de contact + politique de routage pour le dossier SLO, URL
fournie par l'opérateur (vide par défaut = pas de notification). Preuve
de bout en bout via la règle test-alert-do-not-keep-in-prod déjà
présente dans rules.yaml pour cet usage (I9, revue de projet
2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

