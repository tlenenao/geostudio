# 0028 — Fermeture de la matrice FME : statuts terminaux, secrets OAuth2/MongoDB, writers externes non rejoués

Statut: acceptée
Source : plan `docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md` (décisions D1-D5 de Tanguy, 2026-10-15) ; ADR 0012 (connecteurs), ADR 0027 (webhooks).

## Décision

- **D2** — `TCPIP*`/`JMS*` : `out_of_scope` (protocoles à connexion longue, hors modèle batch ; messagerie couverte par RabbitMQ/Service Bus/Kinesis/SNS).
- **D4** — pas de PDAL (nuages de points) : les 16 lignes `planned_pdal` passent `out_of_scope` ; aucune dépendance native ajoutée au worker.
- **D5** — transformer/lecteur dont le driver GDAL est absent de l'image : `out_of_scope` motivé, pas de build GDAL maison. CityGML et `TextureCoordinateSetter` (aucun modèle de maillage) idem.
- **D1 (différée)** — OTB, PythonCaller, NLPClassifier/Trainer, Autodesk, TrimbleConnect/Unity restent `planned_*`/`unknown` : décision produit ultérieure. HDFS reste `planned_duckdb` (datanodes internes bloqués par l'egress ; passerelle Knox à arbitrer).
- **Secrets** : nouveaux kinds `oauth2_client` (client_credentials / refresh_token, jeton rafraîchi sous verrou, `tokenUrl` https seul) et `mongodb_uri`, soumis à la garde d'egress.
- **Writers à effet externe** (`EXTERNAL_EFFECT_WRITER_OPS` dans `configs/schemas.py`) : jamais rejoués par le retry automatique (un message ou une ligne distante ne s'annule pas).
- **SRID 0** : « sans système de coordonnées » est un état explicite ; `writer.export`/`writer.topojson` le refusent.
- Dépendances ajoutées : `pika`, `mgrs`, `pymongo`, `dnspython`.

## Conséquences

Formes d'API de plusieurs connecteurs (Trello, Service Bus, Kinesis, MCP, Dropbox/Box/Graph…) testées contre des doubles, jamais contre les vrais services. ARC-31 (hors ligne) et ARC-35 (temps réel) restent ouverts (ADR 0023/0026 réservés).
