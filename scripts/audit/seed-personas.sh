#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Personas de rôle de l'audit (spec 2026-09-29 §5), realm Keycloak `geostudio`.
#
#   scripts/audit/seed-personas.sh              crée audit-{admin,creator,analyst,reader}
#                                               et écrit .audit-snapshot/personas.env
#   scripts/audit/seed-personas.sh --set-roles  pose role_id creator/reader en base
#
# Ordre requis : seed-personas.sh (stack en marche) -> stack-reset.sh snapshot ->
# stack-reset.sh reset --auth oidc -> première connexion de chaque persona ->
# seed-personas.sh --set-roles -> stack-reset.sh snapshot (les rôles survivent).
#
# CORE_ADMIN_SUBS / CORE_ANALYST_SUBS (lus dans personas.env) ne s'appliquent qu'à
# la CRÉATION de la ligne `users` (core/app/auth/dependency.py, bootstrap_admin /
# bootstrap_analyst) : le reset --auth oidc doit donc précéder la première
# connexion. Un nouvel utilisateur OIDC reçoit par défaut le rôle `creator`.
# Course connue du cœur : la première connexion peut produire un 500 sur une
# requête (get_or_create_user, UniqueViolation, core/app/users/repository.py:58) ;
# se reconnecter / réessayer avant de lancer --set-roles.
# Idempotent : un utilisateur existant est conservé, son mot de passe réaffirmé.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
SNAP="${AUDIT_SNAPSHOT_DIR:-$PWD/.audit-snapshot}"
mkdir -p "$SNAP"

# --set-roles : les lignes `users` n'existent qu'après la première connexion de
# chaque persona. admin/analyst passent par CORE_*_SUBS (logique de rôle,
# is_admin synchronisé) ; creator/reader sont posés ici par leur slug.
if [ "${1:-}" = "--set-roles" ]; then
  psql_q() {
    docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis \
      psql -h localhost -U gis -d gis -tA -c "$1" 2>&1 \
      | { grep -v -e 'collation version' -e '^DETAIL:' -e '^HINT:' || true; }
  }
  for pair in "audit-creator:creator" "audit-reader:reader"; do
    u="${pair%%:*}"; slug="${pair##*:}"
    n=$(psql_q "UPDATE users SET role_id=(SELECT id FROM roles WHERE slug='$slug' AND tenant_id='default') WHERE username='$u' AND tenant_id='default' RETURNING 1" | grep -c '^1$' || true)
    [ "$n" -ge 1 ] || { echo "[audit] $u introuvable en base : se connecter une première fois" >&2; exit 1; }
  done
  for pair in "audit-admin:admin" "audit-analyst:analyst"; do
    u="${pair%%:*}"; slug="${pair##*:}"
    got=$(psql_q "SELECT r.slug FROM users u JOIN roles r ON r.id=u.role_id WHERE u.username='$u' AND u.tenant_id='default'" | tr -d '[:space:]')
    if [ "$got" != "$slug" ]; then
      echo "[audit] $u a le rôle '${got:-<aucune ligne en base>}' au lieu de '$slug'." >&2
      echo "[audit] CORE_ADMIN_SUBS/CORE_ANALYST_SUBS ne s'appliquent qu'à la création de la ligne :" >&2
      echo "[audit] lancer scripts/audit/stack-reset.sh reset --auth oidc AVANT la première connexion des personas, puis se reconnecter, et relancer --set-roles." >&2
      exit 1
    fi
  done
  psql_q "SELECT u.username || '|' || r.slug FROM users u JOIN roles r ON r.id=u.role_id WHERE u.username LIKE 'audit-%' ORDER BY 1"
  exit 0
fi

K="docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh"
$K config credentials --server http://localhost:8080 --realm master \
  --user admin --password "$KC_PASSWORD" >/dev/null

sub_of() { $K get users -r geostudio -q exact=true -q "username=$1" --fields id --format csv --noquotes | tr -d '\r'; }

for u in audit-admin audit-creator audit-analyst audit-reader; do
  if [ -z "$(sub_of "$u")" ]; then
    $K create users -r geostudio -s "username=$u" -s enabled=true \
      -s "email=$u@audit.local" -s emailVerified=true -s firstName=Audit -s "lastName=$u"
  fi
  $K set-password -r geostudio --username "$u" --new-password 'Demo1234!'
done

ADMIN_SUB=$(sub_of audit-admin); ANALYST_SUB=$(sub_of audit-analyst)
if [ -z "$ADMIN_SUB" ] || [ -z "$ANALYST_SUB" ]; then
  echo "[audit] sub Keycloak vide (audit-admin='$ADMIN_SUB', audit-analyst='$ANALYST_SUB') : personas.env non écrit" >&2
  exit 1
fi
cat > "$SNAP/personas.env" <<EOT
CORE_ADMIN_SUBS=$ADMIN_SUB
CORE_ANALYST_SUBS=$ANALYST_SUB
EOT
echo "[audit] personas créées ; $SNAP/personas.env écrit"
echo "[audit] suite : stack-reset.sh snapshot && reset --auth oidc, connexions, puis --set-roles"
