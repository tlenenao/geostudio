"""Rotation ponctuelle de la clé maître AES-GCM des secrets connecteurs
(GAP-75, design SP-59 §3.1.1 — procédure complète dans
docs/runbooks/2026-09-06-rotation-cle-secrets.md).

Ni ce script ni `CORE_SECRETS_MASTER_KEY_NEW` ne sont câblés dans
`docker-compose.yml`/`.env.example` : ce n'est pas une capacité de service
instance-wide (contrairement à `CORE_QUOTAS_ENABLED` et consorts), c'est un
paramètre d'une commande ponctuelle que l'opérateur fournit lui-même au
moment de l'exécuter — exactement comme `DATABASE_URL` pour `seed_demo.py`.

Usage :
    DATABASE_URL=postgresql+psycopg://… \\
    CORE_SECRETS_MASTER_KEY=<ancienne clé b64> \\
    CORE_SECRETS_MASTER_KEY_NEW=<nouvelle clé b64> \\
    uv run python -m scripts.rotate_secrets_master_key [--dry-run]

Ce script ne redémarre JAMAIS le service `core` lui-même (il tourne comme un
processus ponctuel, séparé du service vivant) — le résumé affiché rappelle
explicitement les étapes opérationnelles restantes."""

import argparse
import os

from app.db import make_engine, make_session_factory
from app.secrets.crypto import decode_key_material
from app.secrets.rotation import rotate_all_secrets


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Rotation de la clé maître des secrets connecteurs (GAP-75)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Déchiffre tout avec l'ancienne clé et valide la nouvelle, n'écrit rien.",
    )
    args = parser.parse_args(argv)

    old_key = decode_key_material(
        os.environ["CORE_SECRETS_MASTER_KEY"], source="CORE_SECRETS_MASTER_KEY"
    )
    try:
        new_key_raw = os.environ["CORE_SECRETS_MASTER_KEY_NEW"]
    except KeyError:
        raise SystemExit(
            "CORE_SECRETS_MASTER_KEY_NEW est requis (nouvelle clé, base64, 32 octets)."
        ) from None
    new_key = decode_key_material(new_key_raw, source="CORE_SECRETS_MASTER_KEY_NEW")

    engine = make_engine(os.environ["DATABASE_URL"])
    Session = make_session_factory(engine)

    if args.dry_run:
        with Session() as session:
            from app.secrets import repository as repo
            from app.secrets.crypto import decrypt

            secrets = repo.list_all_secrets(session)
            for secret in secrets:
                decrypt(secret.ciphertext, secret.nonce, key=old_key)
            print(
                f"[dry-run] {len(secrets)} secret(s) déchiffré(s) avec succès avec "
                "l'ancienne clé — la nouvelle clé décode correctement. Aucune écriture."
            )
        engine.dispose()
        return

    with Session() as session:
        try:
            result = rotate_all_secrets(session, old_key=old_key, new_key=new_key)
        except Exception:
            session.rollback()
            raise
        session.commit()

    engine.dispose()

    print(f"Rotation terminée : {result.total} secret(s) rechiffré(s).")
    for tenant_id, count in sorted(result.rotated_by_tenant.items()):
        print(f"  - tenant {tenant_id} : {count} secret(s)")
    print()
    print("Étapes opérationnelles restantes (ce script ne les exécute jamais) :")
    print("  1. Remplacer CORE_SECRETS_MASTER_KEY par la nouvelle clé dans .env,")
    print("     retirer CORE_SECRETS_MASTER_KEY_NEW.")
    print("  2. Redémarrer le service core (docker compose up -d core / restart).")
    print(
        "  3. Vérifier en consommant réellement un secret existant "
        "(GET /secrets seul ne déchiffre jamais)."
    )
    print(
        "  Fenêtre de risque assumée : tout pipeline qui consommerait un secret "
        "entre l'étape 1 (déjà faite ci-dessus, en base) et le redémarrage du "
        "service échouerait en déchiffrement — effectuer cette rotation hors "
        "d'une fenêtre d'exécution planifiée de pipelines."
    )


if __name__ == "__main__":
    main()
