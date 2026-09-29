# Carte Sans Gluten

Carte interactive des établissements sans gluten (niveaux A à D), publiée avec GitHub Pages.

- `index.html` + `etablissements.json` : la carte (MapLibre GL + fond OpenFreeMap / © OpenStreetMap contributors).
- `data/a_geocoder.csv` : adresses à géocoder · `data/geocode.csv` : résultats (créé par l'action).
- `.github/workflows/geocode.yml` : géocode via Nominatim (1 req/s, ~2 700 adresses/h, soit ~15 000 par lot de 5 h 30) toutes les 6 h, place les lieux sur la carte et enregistre. Les villes déjà trouvées ne sont pas redemandées. S'arrête tout seul quand tout est fait.
- `.github/workflows/affine.yml` : second passage sur les lieux trouvés seulement à la ville (adresse nettoyée, sans code postal, rue sans numéro, nom du commerce) pour les placer à la rue. Suivi dans `data/affine_fait.csv`.

## Mise en route (une fois)
1. Settings → Pages → Source : « Deploy from a branch », branche `main`, dossier `/ (root)`.
2. Actions → « Géocodage de la carte » → Run workflow.
La carte est alors en ligne à `https://<utilisateur>.github.io/<repo>/` et se met à jour à chaque lot.
