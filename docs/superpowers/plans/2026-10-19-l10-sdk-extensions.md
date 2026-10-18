# L10 SDK et extensions — plan d'exécution

Spec : `docs/superpowers/specs/2026-10-19-l10-sdk-extensions-design.md`. TDD, un commit par tâche.

1. **Cœur : manifeste v1** — migration 0171 (`sdk_version`, `integrity`, `connect_hosts`, `img_hosts`),
   `ExtensionCreate/Patch` (`sdkVersion: Literal[1]`, `integrity` regex SRI, hôtes https d'origine),
   modèle, dépôt, routes (`_extension_json`). Tests : `test_extensions_routes.py`, migration up/down sur base non vide.
2. **Cœur : CSP** — `extract_extension_connect_hosts/img_hosts`, agrégation dans `compute_csp_allowlist`
   (+ origine du module en connect/img). Tests : `test_security_csp_hosts.py`, `test_security_service.py`.
3. **Shell : types + client** — `ExtensionManifest`/`ExtensionCreateInput` étendus, mapping des 3 lectures,
   `updateExtension` (PATCH), hook.
4. **Shell : AUD-107 + réconciliation** — `unregisterWidget`, `useRegisterExtensions`, branchement des 6 pages
   (Runtime, Builder, Embed, SitePublic, PublicItem, Dataset), tests unitaires + E2E embed.
5. **Shell : chargement** — `moduleCache` (rejet non mis en cache, clé url+integrity), chargeur `<script integrity>`,
   `whenDefined`.
6. **Shell : contrat DOM v1** — `WcHost` : variables/theme/mode/breakpoint/sdkVersion, `setVariable`, `setFilter`,
   `gs:ready` ; inertie en `edit`. Test de contrat.
7. **Shell : admin** — import JSON + édition (PATCH), badge intégrité, i18n fr+en, E2E, axe.
8. **Doc/exemples** — guide réécrit (frontière, contrat v1, CSP, intégrité), `sdk.d.ts`, manifeste d'exemple.
9. **Revue finale** — jumelles de garde (`/extensions` : POST/PATCH symétriques ; staticExport ; MCP `tools/configs`),
   OpenAPI + types TS, portes complètes.
