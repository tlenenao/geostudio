# Administration, rôles et partage

## Rôles et privilèges

L'accès repose sur des **privilèges** (une vingtaine) regroupés en **rôles** par
tenant. Quatre rôles prédéfinis, immuables :

| Rôle | En bref |
|---|---|
| Administrateur | tout, sauf la conformité (`compliance.manage`, volontairement séparée) |
| Créateur | crée et édite cartes, apps, collections, automatisations |
| Analyste | lit + SQL Lab et requêtes analytiques |
| Lecteur | consulte ce qui lui est partagé |

Des rôles sur mesure se composent à partir du catalogue de privilèges.
*Administration → Utilisateurs* (`/admin/users`) : changer le rôle d'un compte,
rechercher, paginer.

Toute décision passe par **une seule porte**, `can(utilisateur, action, objet)` :
privilège du rôle + droit sur l'objet (propriétaire, partage, publication). Le
shell n'affiche que ce que le cœur autorise, mais c'est toujours le cœur qui
tranche.

## Partager un objet

Depuis la fiche : lecture/écriture/gestion pour un **groupe** (les groupes sont
gérés par GeoStudio, pas par Keycloak — ils peuvent être alimentés par des claims
OIDC), **publication** pour un accès anonyme, **lien de partage** avec échéance.

## Données sensibles

- Une collection peut **masquer des champs** par rôle (protection au niveau
  colonne : lecture, tuiles, STAC, exports et MCP).
- **Limites géographiques** : découpage des données lues selon une emprise.
- Les **secrets** (connecteurs) sont chiffrés ; leur usage est audité.

## Exploitation

- **Audit** : toute écriture est tracée (`audit_log` append-only) ; *Usage* (`/tasks`)
  résume l'activité.
- **Quotas** par tenant (items, collections, stockage, utilisateurs).
- **Sauvegardes** chiffrées planifiées et restauration scriptée :
  [runbooks](../runbooks/).
- **Conformité (RGPD)** : anonymisation d'un utilisateur, export de ses données,
  purge complète d'un tenant — réservées à `compliance.manage`.
- **Paramètres** : profil, langue (fr/en), préférence de notifications.
