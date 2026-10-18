# L11 — i18n et accessibilité (audit 2026-10-16)

Périmètre : AUD-019, 115, 116, 114, 119, 126 (`docs/revue/audit-2026-10-16/99-synthese.md`,
fiches d26/d27/d29/d33). Décision D8 : mécanisme de langue d'abord, anglais ensuite ; D11/D12 :
audit RGAA tiers hors périmètre logiciel.

## Décisions de scope (tranchées, pas rediscutées)

- **AUD-019 (fermé)** : locale active `fr | en`, préférence `localStorage` (`gs.locale`) > claim OIDC
  `locale` (1er login, jamais contre un choix explicite) > `navigator.language` > `fr`. Le catalogue
  français reste la source et le repli. Le catalogue anglais (`shell/src/i18n/en/*`, typé
  `Record<keyof typeof domaine, string>`) est un chunk **chargé à la demande** (import dynamique),
  hors charge initiale. `t()` n'est pas réactif : changer de langue recharge la page. Boot : attente
  au niveau module dans `i18n/index.ts` (les tables de libellés évaluées au chargement des modules
  lisent la bonne locale) ; `build.target = es2022`. Les tests restent en `fr` (`MODE === "test"`).
- **AUD-115 (partiel)** : fermés = formats `Intl`/fuseau centralisés dans `lib/format.ts` (locale
  `fr-FR`/`en-GB`, fuseau préférence ou Europe/Paris, `compareText` collation) + règle ESLint
  interdisant les littéraux de locale ailleurs ; bug des buckets UTC vs affichage (`timeZone` IANA
  dans `AggregateRequestBody`, transmis par le shell) ; libellé XLSForm traduit déterministe ;
  `<html lang/dir>` posés. **Reportés** : RTL réel (plugin MapLibre, utilitaires logiques Tailwind),
  erreurs/copilote/e-mails/DCAT du cœur localisés, `users.locale`/`timezone` en base (migration),
  i18n Keycloak, `timeZone` pour alertes/rapports/exports, stockage des traductions XLSForm.
- **AUD-116 (reporté)** : contenu utilisateur traduisible — D8 le place « en second temps » ; touche
  `AppConfig`/`MapConfig`/SSR/export, hors de ce lot.
- **AUD-114 (fermé)** : graphiques (aria ECharts + motifs, `role=img`, tableau alternatif et
  équivalent clavier du cross-filter) ; carte (liste « Entités de la vue » ouvrant le popup).
- **AUD-119 (partiel)** : palette ⌘K (message « Aucun résultat », `aria-controls`/`activedescendant`,
  libellé du raccourci selon la plateforme). Reportés : recherche d'items et récents dans la palette,
  `HelpHint`/aide CEL, parcours de première utilisation.
- **AUD-126 (partiel)** : polices d'identité appliquées au `body`, états sémantiques de l'app qui
  suivent le fond de l'app (constat 3). Reportés : fonds de carte thémés (`--gs-map-*`), thème d'app
  étendu, migration des 127 contrôles vers le kit.

## Contrats

- `activateLocale(locale)`, `detectLocale()`, `setLocalePreference(locale)`, `getLocale()` dans
  `i18n/index.ts` ; `plural()` suit `Intl.PluralRules` hors français.
- `lib/format.ts` : `intlLocale`, `getTimeZone`, `numberFormat`, `dateFormat`, `compareText`.
- Cœur : `POST /v1/collections/{id}/aggregate` accepte `timeZone` (IANA, 422 sinon) ; UTC par défaut.
