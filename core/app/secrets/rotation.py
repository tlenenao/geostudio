# SPDX-License-Identifier: Apache-2.0
"""Rotation atomique de la clé maître AES-GCM des secrets connecteurs (GAP-75,
design SP-59 §3.1). Réservé au script CLI ponctuel
`scripts/rotate_secrets_master_key.py` — jamais exposé par une route HTTP ni
un outil MCP (§2.2 : aucune route ne peut faire redémarrer le service `core`
avec une nouvelle valeur d'environnement, cf. limite documentée §1.1).

La garantie centrale : toutes les lignes sont déchiffrées avec succès AVANT
qu'aucune ne soit réécrite. Un échec de déchiffrement (mauvaise ancienne
clé, ligne corrompue) lève avant toute mutation en base — jamais un mélange
ancienne-clé/nouvelle-clé."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.secrets import repository as repo
from app.secrets.crypto import decrypt, encrypt


@dataclass
class RotationResult:
    rotated_by_tenant: dict[str, int] = field(default_factory=dict)
    total: int = 0


def rotate_all_secrets(session: Session, *, old_key: bytes, new_key: bytes) -> RotationResult:
    secrets = repo.list_all_secrets(session)

    # Passe 1 — déchiffrement intégral avec l'ancienne clé AVANT toute
    # écriture. Si un seul secret échoue (mauvaise ancienne clé, ligne
    # corrompue), l'exception se propage ici : aucune ligne n'a encore été
    # modifiée.
    decrypted = [
        (secret, decrypt(secret.ciphertext, secret.nonce, key=old_key)) for secret in secrets
    ]

    # Passe 2 — re-chiffrement avec la nouvelle clé, mutation en mémoire
    # seulement (pas de flush intermédiaire) : si cette passe échouait à
    # mi-chemin (ce qui ne devrait jamais arriver, encrypt() ne validant
    # rien côté base), aucune ligne ne serait encore persistée non plus.
    counts: dict[str, int] = {}
    for secret, payload in decrypted:
        ciphertext, nonce = encrypt(payload, key=new_key)
        secret.ciphertext = ciphertext
        secret.nonce = nonce
        counts[secret.tenant_id] = counts.get(secret.tenant_id, 0) + 1

    session.flush()

    for tenant_id, count in counts.items():
        write_audit(
            session,
            tenant_id=tenant_id,
            actor_id=None,
            actor_kind="system",
            action="secret.rotate_master_key",
            object_type="tenant",
            object_id=tenant_id,
            payload={"count": count},
        )

    return RotationResult(rotated_by_tenant=counts, total=len(secrets))
