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

## What this document does not change

`secret_scanning` and `dependabot_security_updates` are currently disabled
on this repository (cf. `CLAUDE.md`) — this file does not imply otherwise,
and does not itself enable them.
