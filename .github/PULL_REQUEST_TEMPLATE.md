<!--
See CONTRIBUTING.md ("Pull request process") for the full checklist this
mirrors.
-->

## What & why

<!-- What does this change, and why? -->

## Related spec/plan

<!-- Link the relevant docs/superpowers/specs/*.md and docs/superpowers/plans/*.md
     if this change follows one. Otherwise, delete this section. -->

## Checklist

- [ ] Branched from `dev` (not `main`)
- [ ] Commits follow the `type(scope): summary` convention, one subject each
- [ ] `cd shell && npm run test && npm run e2e && npm run build` are green
- [ ] `cd core && uv run pytest && uv run lint-imports` are green
- [ ] OpenAPI spec + generated TS types regenerated if a core route/model changed
      (`cd core && ... uv run python scripts/export_openapi.py openapi.json`,
      `cd shell && npm run gen:api-types` — see CONTRIBUTING.md)
