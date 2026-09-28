"""Test de vitesse Photon (komoot) sur les mêmes adresses que le banc Nominatim : latence et précision."""
import time, requests, pandas as pd
s = pd.read_csv("data/a_geocoder.csv", dtype=str).fillna("").head(60)
S = requests.Session(); S.headers["User-Agent"] = "CarteSansGluten/1.0 (bench)"
lat, types, last = [], {}, 0.0
for r in s.itertuples():
    q = ", ".join(x for x in [r.adresse, f"{r.code_postal} {r.ville}".strip()] if x)
    w = last + 1.0 - time.time()
    if w > 0: time.sleep(w)
    last = time.time()
    try:
        j = S.get("https://photon.komoot.io/api/", params={"q": q, "limit": 1}, timeout=30).json()
        f = (j.get("features") or [{}])[0].get("properties", {})
        t = f.get("type", "introuvable")
    except Exception as e:
        t = "erreur"
    lat.append(time.time() - last); types[t] = types.get(t, 0) + 1
print(f"Photon : {len(lat)} requêtes · latence moy. {sum(lat)/len(lat):.2f} s · max {max(lat):.2f} s · types {types}")
