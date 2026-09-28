"""Géocode data/a_geocoder.csv via Nominatim (1 req/s), reprend sur data/geocode.csv, s'arrête après BUDGET secondes."""
import os, sys, time, csv, requests, pandas as pd
BUDGET = int(os.environ.get("BUDGET", 5 * 3600 + 30 * 60))
LIMIT = int(os.environ.get("LIMIT", 0))          # 0 = pas de limite (utile pour les tests)
INTERVAL = float(os.environ.get("INTERVAL", 1.0))  # écart minimal entre deux requêtes (politique Nominatim : 1 req/s max)
CONTACT = os.environ.get("CONTACT", "carte-sans-gluten")
src = pd.read_csv("data/a_geocoder.csv", dtype=str).fillna("")
cols = ["cle", "lat", "lon", "precision", "place_rank", "requete", "resultat_osm"]
cp = os.environ.get("OUT", "data/geocode.csv")
cache = pd.read_csv(cp, dtype=str).fillna("") if os.path.exists(cp) else pd.DataFrame(columns=cols)
todo = src[~src.cle.isin(set(cache.cle))]
if LIMIT: todo = todo.head(LIMIT)
print(f"{len(src)} adresses · {len(cache)} faites · {len(todo)} à faire", flush=True)
# requêtes déjà résolues (souvent « code postal ville ») : réutilisées sans rappeler Nominatim
memo = {(r.requete, r.cle.split("|")[2]): {"lat": r.lat, "lon": r.lon, "place_rank": r.place_rank, "display_name": r.resultat_osm}
        for r in cache.itertuples() if r.requete and r.lat and r.cle.count("|") >= 3}
S = requests.Session(); S.headers["User-Agent"] = f"CarteSansGluten/1.0 ({CONTACT})"
last, stats = 0.0, {"req": 0, "cache": 0, "t_req": 0.0}
def ask(q, cc, pays):
    global last
    if (q, pays) in memo: stats["cache"] += 1; return memo[(q, pays)]
    res = None
    for i in range(3):
        wait = last + INTERVAL - time.time()
        if wait > 0: time.sleep(wait)
        last = time.time()
        try:
            r = S.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": cc.lower()}, timeout=30)
            stats["req"] += 1; stats["t_req"] += time.time() - last
            if r.status_code == 200: res = (r.json() or [None])[0]; break
            print("HTTP", r.status_code, flush=True); time.sleep(60 * (i + 1))
        except Exception as e:
            print("ERR", e, flush=True); time.sleep(10)
    else:
        return None  # échec réseau : pas mis en mémoire, on réessaiera
    memo[(q, pays)] = res
    return res
prec = lambda k: "exacte" if k >= 28 else "rue" if k >= 26 else "ville" if k >= 12 else "region"
t0, new = time.time(), []
def flush():
    global new
    if not new: return
    exists = os.path.exists(cp)
    with open(cp, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if not exists: w.writeheader()
        w.writerows(new)
    new = []
n = 0
for n, r in enumerate(todo.itertuples(), 1):
    if time.time() - t0 > BUDGET: print("Budget atteint, reprise au prochain passage"); n -= 1; break
    cc = r.pays if len(r.pays) == 2 and r.pays != "XX" else ""
    essais = []
    if r.adresse: essais.append(", ".join(x for x in [r.adresse, f"{r.code_postal} {r.ville}".strip()] if x))
    if r.code_postal or r.ville: essais.append(f"{r.code_postal} {r.ville}".strip())
    res, used = None, ""
    for q in essais:
        res = ask(q, cc, r.pays)
        if res: used = q; break
    new.append({"cle": r.cle, "lat": res["lat"] if res else "", "lon": res["lon"] if res else "",
                "precision": prec(int(res["place_rank"])) if res else "introuvable", "place_rank": res["place_rank"] if res else "",
                "requete": used or (essais[0] if essais else ""), "resultat_osm": (res["display_name"][:200] if res else "")})
    if n % 100 == 0:
        flush(); el = time.time() - t0
        print(f"{n}/{len(todo)} · {el/60:.0f} min · {n/el*3600:.0f} adresses/h · {stats['req']} requêtes, {stats['cache']} évitées", flush=True)
flush()
el = max(time.time() - t0, 1e-9)
print(f"Fin : {n} adresses en {el/60:.1f} min ({n/el*3600:.0f}/h) · {stats['req']} requêtes"
      f" (latence moy. {stats['t_req']/max(stats['req'],1):.2f} s) · {stats['cache']} évitées par le cache", flush=True)
