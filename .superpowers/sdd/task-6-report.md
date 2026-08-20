# Task 6 Report: Core — docker-compose.yml + .env.example wiring

## What Was Implemented

Wired the four LLM configuration environment variables (`CORE_LLM_PROVIDER`, `CORE_LLM_API_URL`, `CORE_LLM_API_KEY`, `CORE_LLM_MODEL`) into the packaged Docker Compose stack, preventing the same recurring bug class that affected `CORE_EMBEDDING_PROVIDER` (documented in CLAUDE.md as occurring 3-4 times across SP-17a/17b/tileset3d/appexport).

### Step 1: docker-compose.yml

Inserted 4 lines after `CORE_BASE_URL` (line 134) in the `core:` service's `environment:` block:
- `CORE_LLM_PROVIDER: ${CORE_LLM_PROVIDER:-}`
- `CORE_LLM_API_URL: ${CORE_LLM_API_URL:-}`
- `CORE_LLM_API_KEY: ${CORE_LLM_API_KEY:-}`
- `CORE_LLM_MODEL: ${CORE_LLM_MODEL:-gpt-4o-mini}`

**Location verified:** Lines 135–138, right after `CORE_BASE_URL` (line 134), before `CORE_READ_ONLY_MODE` (line 139).

### Step 2: .env.example

Inserted a new section (lines 40–50) immediately after `CORE_BASE_URL=http://localhost:8200` (line 38) and before the S3 storage section (line 51):

```
# ─── Cœur : copilote IA embarqué (SP-20) ─────────────────
# Vide (défaut) : le copilote est désactivé, le routeur POST /copilot/turn
# n'est pas monté, l'onglet n'apparaît pas dans le builder. "openai" active
# le fournisseur HTTP compatible OpenAI (chat completions + tool calling
# standard — vLLM/Ollama/LM Studio et la plupart des passerelles locales
# l'exposent aussi).
CORE_LLM_PROVIDER=
CORE_LLM_API_URL=
CORE_LLM_API_KEY=
CORE_LLM_MODEL=gpt-4o-mini
```

**Location verified:** Inserted at the correct position between MCP section end (line 38) and S3 storage section start (line 51).

## Verification

### Compose File Parsing

Command: `docker compose config --quiet`

Result: **PASS** — No output, exit code 0. The docker-compose.yml file is syntactically valid.

### Git Commit

```
Commit: a656a80 (short SHA)
Subject: feat(deploy): variables du copilote IA dans la stack packagée (SP-20)
Files changed: 2 (.env.example, docker-compose.yml)
Insertions: +15
```

Commit created successfully with the exact message specified in the brief.

## Files Changed

1. **docker-compose.yml** — 4 new lines (135–138) in `core:` service environment block
2. **.env.example** — 11 new lines (40–50) LLM configuration section with documentation

## Self-Review

**No issues found.** The implementation exactly matches the brief:
- Insertion points verified against actual file content
- Variables match exact names and default values from brief
- Documentation string in .env.example matches the brief exactly (character-for-character)
- Compose file validates after modification
- Commit message is exact match to brief
- Both edits are scoped correctly (no unrelated changes)
- No accidental formatting or whitespace issues

This addresses the recurring bug class in the codebase where capability env vars are documented in `.env.example` but never forwarded in `docker-compose.yml`, making the feature silently inert in the packaged stack regardless of `.env` configuration.
