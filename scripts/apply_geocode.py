"""Place sur la carte (etablissements.json) les lieux géocodés à la rue ou au numéro dans data/geocode.csv."""
import json, re, unicodedata, pandas as pd
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
g = pd.read_csv("data/geocode.csv", dtype=str).fillna("")
g = g[g.lat.ne("") & g.precision.isin(["exacte", "rue"])]
geo = {r.cle: (round(float(r.lat), 6), round(float(r.lon), 6), r.precision) for r in g.itertuples()}
D = json.load(open("etablissements.json", encoding="utf-8"))
placed = 0
for e in D["e"]:
    if "y" in e: continue
    k = norm(e.get("n", "")) + "|" + norm(e.get("v", "")) + "|" + e.get("c", "") + "|" + norm(e.get("a", ""))[:40]
    if k in geo:
        e["y"], e["x"], e["q"] = geo[k]; e.pop("k", None); placed += 1
for c in D["cities"]:
    c["ids"] = [i for i in c["ids"] if "y" not in D["e"][i]]
D["cities"] = [c for c in D["cities"] if c["ids"]]
# ids des villes = index dans e : inchangés car l'ordre de e ne bouge pas
json.dump(D, open("etablissements.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
tot = sum(1 for e in D["e"] if "y" in e)
print(f"{placed} lieux placés ce passage · {tot}/{len(D['e'])} placés à l'adresse")
