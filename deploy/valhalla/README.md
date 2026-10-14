# Routage et isochrones — Valhalla (ARC-34, ADR 0025)

Service **externe et optionnel** : profil compose `routing` / `valhalla.enabled=true` (Helm).
GeoStudio ne fournit **aucune donnée de réseau** : l'opérateur apporte son extrait OpenStreetMap
(licence ODbL, attribution à sa charge). Valhalla (MIT) n'est joignable que par le cœur et le worker.

## Préparer les données

1. Choisir un extrait **le plus petit possible** (région/département, pas la France entière :
   la construction des tuiles prend de quelques minutes à plusieurs heures et la RAM suit) —
   par exemple depuis Geofabrik (`limousin-latest.osm.pbf`).
2. Le déposer dans le volume `valhalla-data` (monté sur `/custom_files`) :
   `docker compose --profile routing run --rm --entrypoint sh valhalla -c 'cp /x.pbf /custom_files/'`
   ou, plus simple, renseigner `VALHALLA_TILE_URLS` (URL(s) de `.pbf`, séparées par des espaces) :
   l'image les télécharge au premier démarrage.
3. Démarrer : `docker compose --profile routing up -d valhalla` puis régler `CORE_ROUTING_URL=http://valhalla:8002`
   dans `.env` et recréer `core` et `worker`. La sonde `/status` passe `healthy` une fois les tuiles construites.

Les tuiles survivent dans le volume : un redémarrage ne reconstruit rien tant que le `.pbf` ne change pas.

## Garde-fous côté cœur

- `CORE_ROUTING_URL` vide = `POST /v1/routing/*` répond **503** (RFC 7807), jamais un crash.
- Egress : seul l'hôte de `CORE_ROUTING_URL` est joignable (plage privée admise pour lui seul ;
  link-local/métadonnées cloud bloqués), pas de redirection suivie.
- Plafonds : itinéraire 20 points, isochrone 4 contours de 60 min, zone de service 10 origines,
  matrice 50×50 et 1 000 cellules ; 100 appels/min/utilisateur (429) ; privilège `analytics.view` ;
  une ligne d'audit par appel (nombre de points et profil, jamais les coordonnées).
- Ops de pipeline `transform.isochrone` / `transform.route` : 500 lignes max par nœud.

Mesure de performance (isochrone 10 min < 2 s) : à faire sur l'extrait réel de l'opérateur ;
elle dépend de la machine et de la taille du graphe.
