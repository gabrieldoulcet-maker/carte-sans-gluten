# Carte Sans Gluten

Carte interactive des établissements sans gluten (niveaux A à D), publiée avec GitHub Pages.

- `index.html` + `etablissements.json` : la carte (MapLibre GL + fond OpenFreeMap / © OpenStreetMap contributors).
- `data/a_geocoder.csv` : adresses à géocoder · `data/geocode.csv` : résultats (créé par l'action).
- `.github/workflows/geocode.yml` : géocode ~3 000 adresses toutes les 6 h via Nominatim (1 req/s), place les lieux sur la carte et enregistre. S'arrête tout seul quand tout est fait (~1 à 2 jours pour ~17 000 adresses).

## Mise en route (une fois)
1. Settings → Pages → Source : « Deploy from a branch », branche `main`, dossier `/ (root)`.
2. Actions → « Géocodage de la carte » → Run workflow.
La carte est alors en ligne à `https://<utilisateur>.github.io/<repo>/` et se met à jour à chaque lot.
