"""Géocode data/a_geocoder.csv via Nominatim (1 req/s), reprend sur data/geocode.csv, s'arrête après BUDGET secondes."""
import os, time, csv, requests, pandas as pd
BUDGET = int(os.environ.get("BUDGET", 5 * 3600 + 30 * 60))
CONTACT = os.environ.get("CONTACT", "carte-sans-gluten")
src = pd.read_csv("data/a_geocoder.csv", dtype=str).fillna("")
cols = ["cle", "lat", "lon", "precision", "place_rank", "requete", "resultat_osm"]
cp = "data/geocode.csv"
cache = pd.read_csv(cp, dtype=str).fillna("") if os.path.exists(cp) else pd.DataFrame(columns=cols)
todo = src[~src.cle.isin(set(cache.cle))]
print(f"{len(src)} adresses · {len(cache)} faites · {len(todo)} à faire")
S = requests.Session(); S.headers["User-Agent"] = f"CarteSansGluten/1.0 ({CONTACT})"
def ask(q, cc):
    for i in range(3):
        try:
            r = S.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": cc.lower()}, timeout=30)
            time.sleep(1.1)
            if r.status_code == 200: return (r.json() or [None])[0]
            print("HTTP", r.status_code); time.sleep(60 * (i + 1))
        except Exception as e:
            print("ERR", e); time.sleep(10)
    return None
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
for n, r in enumerate(todo.itertuples(), 1):
    if time.time() - t0 > BUDGET: print("Budget atteint, reprise au prochain passage"); break
    cc = r.pays if len(r.pays) == 2 and r.pays != "XX" else ""
    essais = []
    if r.adresse: essais.append(", ".join(x for x in [r.adresse, f"{r.code_postal} {r.ville}".strip()] if x))
    if r.code_postal or r.ville: essais.append(f"{r.code_postal} {r.ville}".strip())
    res, used = None, ""
    for q in essais:
        res = ask(q, cc)
        if res: used = q; break
    new.append({"cle": r.cle, "lat": res["lat"] if res else "", "lon": res["lon"] if res else "",
                "precision": prec(int(res["place_rank"])) if res else "introuvable", "place_rank": res["place_rank"] if res else "",
                "requete": used or (essais[0] if essais else ""), "resultat_osm": (res["display_name"][:200] if res else "")})
    if n % 100 == 0: flush(); print(f"{n}/{len(todo)}")
flush()
