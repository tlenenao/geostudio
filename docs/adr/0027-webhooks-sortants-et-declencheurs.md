# 0027 — Webhooks sortants et déclencheurs fichier/S3 : outbox transactionnelle, egress gardé

Statut: acceptée
Source : rang 6 du comparatif FME/ArcGIS Enterprise (2026-10-11 §6, B15) ; ADR 0001 (`can()`), ADR 0012 (connecteurs), garde d'egress SSRF (`net_pin.py`), livraison d'alertes (SP-16b).

## Contexte

Le cœur n'émet aucun événement vers l'extérieur et ne déclenche aucun pipeline sur dépôt de fichier. Il faut une ouverture sortante sans perte, sans nouvelle surface SSRF et sans broker.

## Décision

- **Outbox transactionnelle** : l'événement (`item.created/updated`, `pipeline.run.finished`, `submission.pending`) est inséré dans la table `outbox` **dans la même transaction** que l'écriture qui l'émet ; un worker procrastinate livre ensuite. Un balayage de reprise relivre les lignes `pending` (piège n°14).
- Destinations `outbound_webhooks` (tenant-scoped, `audit_log`) ; secret de signature dans le coffre ; en-tête `X-GeoStudio-Signature` HMAC-SHA256 ; retries exponentiels ; événement abandonné après 24 h ou sur refus de son contenu (400/409/413/415/422) ; désactivation + notification seulement après 5 échecs consécutifs **et** une panne d'au moins 24 h, événements `pending` gardés pour la réactivation (AUD-085/170).
- **Egress gardé** : toute URL passe par la garde SSRF existante (IP privées/RFC1918 refusées, épinglage DNS).
- Le payload ne contient **jamais** de champ masqué (GAP-22) ni de ligne `pending` (ADR 0017) ; il porte des identifiants, pas les données complètes.
- **Déclencheur S3 par sondage borné** d'un préfixe (secret de connexion lié, ADR 0012) ; aucune écoute d'événements MinIO exposée. Un fichier = exactement un run (clé d'idempotence = etag).

## Conséquences

- Pas de broker. Latence de livraison = période du worker. Le déclencheur S3 est périodique, pas temps réel (cf. ARC-35 pour le push).
