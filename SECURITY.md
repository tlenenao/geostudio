# Security Policy

## Supported versions

GeoStudio is a pre-1.0 product (`v0.1.x`) developed on a single active
branch (`dev`, merged into `main` for stable states). There is no long-term
support policy across multiple release lines yet — only the latest tagged
release and `main` are considered supported. If a fix is needed, it lands on
`dev`/`main` and ships in the next tag; there is no backport process to
older `v0.x` tags.

## Scope

This covers the code in this repository: the `core/` (Python/FastAPI) and
`shell/` (React/TypeScript) applications, their Dockerfiles, and the
`docker-compose*.yml` deployment files. It does not cover third-party
services referenced by the stack (Keycloak, MinIO, Traefik, PostGIS, etc.)
— report issues in those upstream.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability** — use a
private channel instead, so the issue isn't disclosed before a fix is
available.

GitHub's private vulnerability reporting feature is **not currently enabled**
on this repository (this document won't pretend otherwise). Until it is,
please report vulnerabilities by email to the maintainer:
**lenenaon.tanguy@gmail.com** (the address already associated with every
commit in this repository's public history).

Include what you'd include in a bug report (see `CONTRIBUTING.md`): the
affected component, steps to reproduce, and the potential impact.

There is no formal SLA on response time — this is a project with a single
active maintainer. A best-effort acknowledgment and, if the report is
confirmed, a fix and coordinated disclosure timeline, is the realistic
expectation. There is no bug bounty program.

## Known limitations

Accepted and documented trade-offs, not vulnerabilities to report:

- **Extension `script-src` is instance-wide (ADR 0013, accepted with a known
  limit).** The CSP is a single Traefik configuration, so `script-src` is
  `'self'` plus the origins of the enabled extensions of **all** tenants.
  Per-tenant isolation is not implemented because the widget SDK is not open
  to third parties. Do not delegate `admin.extensions.manage` to a tenant you
  do not control. The allowlist protects against an undeclared origin, not
  against a file swapped on a declared one.
- **GDPR erasure tombstone is conditional (ADR 0015).** An erased account keeps
  an `erased:` + SHA-256 pseudonym of its OIDC `sub` (unsalted, deterministic).
  No tombstone change ships without a written opinion of the DPO; the full
  `purge_tenant` erasure (irreversible, whole tenant) is the only delivered
  route.
- **SMTP egress guard does not pin the IP (REV-338).** The alert e-mail guard
  validates the resolved address, but `smtplib` resolves the host itself when
  connecting: a DNS-rebinding window remains on that one path (the other
  egress paths are IP-pinned).
- **Blob secrets (Azure/GCS) stored before the stricter format must be
  recreated (REV-341).** They become unreadable instead of being migrated.
- **Offline field collection stores entries unencrypted on the device (ADR
  0029).** Pending entries and photos live in the browser's IndexedDB until
  sent; anyone with access to the unlocked browser profile can read them.
  The service worker is a strict allowlist (shell navigations and `/assets/`
  only) and never caches API or authenticated responses. Public submissions
  now require a proof of work; its used-challenge registry is per core process.
- **No real screen reader or touch device in the test suite.** Accessibility
  and touch behaviour are verified through automated Playwright specs
  (accessibility tree, emulated touch events); NVDA/JAWS/VoiceOver and real
  devices are not exercised.

## What this document does not change

`secret_scanning` and `dependabot_security_updates` are currently disabled
on this repository (cf. `CLAUDE.md`) — this file does not imply otherwise,
and does not itself enable them.
