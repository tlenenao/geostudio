## Task 6: Core — docker-compose.yml + .env.example wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Why this is its own task:** `CORE_EMBEDDING_PROVIDER` (SP-7) is documented in `.env.example` but was never wired into `docker-compose.yml`'s `core:` service — the packaged stack silently always runs embeddings in `fake` mode regardless of `.env`. This is the same bug class CLAUDE.md flags as recurring 3-4 times (SP-17a/17b/tileset3d/appexport): a capability that works when run directly but is dead in the packaged stack because compose only forwards env vars it explicitly lists. Do not repeat it here.

- [ ] **Step 1: docker-compose.yml**

In the `core:` service's `environment:` block, insert right after `CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}`:

Change:
```yaml
      CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
```
to:
```yaml
      CORE_MCP_AUDIENCE: ${CORE_MCP_AUDIENCE:-geostudio-mcp}
      CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
      CORE_LLM_PROVIDER: ${CORE_LLM_PROVIDER:-}
      CORE_LLM_API_URL: ${CORE_LLM_API_URL:-}
      CORE_LLM_API_KEY: ${CORE_LLM_API_KEY:-}
      CORE_LLM_MODEL: ${CORE_LLM_MODEL:-gpt-4o-mini}
```

- [ ] **Step 2: .env.example**

Insert a new section right after the existing MCP section (after `CORE_BASE_URL=http://localhost:8200` and its trailing blank line, before `# ─── Cœur : stockage des vignettes (MinIO / S3) ──────────`):

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

- [ ] **Step 3: Verify the compose file still parses**

Run: `docker compose config --quiet`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(deploy): variables du copilote IA dans la stack packagée (SP-20)

CORE_LLM_PROVIDER/API_URL/API_KEY/MODEL explicitement transmis au service
core — sans ça la capacité serait inactivable dans docker-compose.yml même
avec .env correctement renseigné (même classe de bug que CORE_EMBEDDING_*,
jamais câblé pour SP-7).
EOF
)"
```

---

