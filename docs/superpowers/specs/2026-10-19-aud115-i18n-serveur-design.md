# AUD-115 : i18n du cœur et fuseaux (spec courte)

Cadrage : `docs/revue/audit-2026-10-16/101-reliquats-L-cadrage.md`. Le shell a déjà fr/en (L11) ;
ce lot donne au cœur une langue et un fuseau par utilisateur, et localise ses sorties.

## Périmètre livré (sous-lots a et b)

1. **Préférences** : `users.locale` (`fr`|`en`, NULL = défaut d'instance) et `users.timezone`
   (nom IANA, NULL = UTC). Migration 0180 (nullable, sans reprise). `GET/PUT /v1/me/preferences`.
   Création JIT : le claim OIDC `locale` (préfixe de langue) alimente `users.locale` s'il est
   pris en charge.
2. **Module feuille `app/i18n_core.py`** : `normalize_locale`, `negotiate_locale(Accept-Language)`,
   catalogue `tr(clé, locale, **vars)` pour les e-mails, `translate_detail(detail, locale)` pour
   les erreurs. Défaut d'instance `CORE_DEFAULT_LOCALE` (`fr`).
3. **Erreurs RFC 7807** : ajout du membre `code` (slug stable dérivé du `detail` source anglais,
   ex. `tile_not_found`) ; `title` et `detail` traduits quand `Accept-Language` demande une langue
   prise en charge ET que le message est au catalogue. Sans en-tête, ou langue `en` : texte source
   inchangé (contrat actuel). Le shell envoie `Accept-Language` = langue active.
4. **E-mails** d'alertes et de rapports : sujet et corps par défaut dans la langue du propriétaire
   de l'item (`users.locale`), sinon défaut d'instance.
5. **Fuseau** : le rendu de dates des e-mails de rapport/alerte utilise `users.timezone` du
   propriétaire ; `ReportSchedule`/`AlertRule` ont déjà `refreshPolicy.timezone` (AUD-084).

## Hors périmètre (reste ouvert)

- Sous-lot c : DCAT/STAC multilingues (`dct:title@en`), libellés XLSForm `label::en`, RTL : dépend
  de D8 (contenu utilisateur traduisible, décision de Tanguy).
- Catalogue des erreurs : seuls les messages les plus fréquents (≈ 40) sont traduits ; la longue
  traîne (≈ 300 chaînes) reste en source anglaise, sans régression.
- `timeZone` des exports CSV/XLSX : les dates y restent en UTC ISO (contrat de fichier).

## Risques

- Tests qui assertent `detail` : inchangés (pas d'en-tête dans `TestClient`).
- `code` est un ajout de membre : compatible RFC 7807.
