"""Liste pour les contributeurs : lieux encore placés seulement à la ville (sans « y » dans etablissements.json).
Écrit data/a_verifier.csv, trié par pays puis ville. La colonne « cle » sert à renvoyer les corrections."""
import csv, json, re, unicodedata, urllib.parse
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
D = json.load(open("etablissements.json", encoding="utf-8"))
faites = set()
try:  # lieux déjà traités par une correction (fermé, introuvable…) : on ne les redemande pas
    faites = {r["cle"] for r in csv.DictReader(open("data/corrections_faites.csv", encoding="utf-8"))}
except FileNotFoundError:
    pass
rows = []
for e in D["e"]:
    if "y" in e: continue
    cle = norm(e.get("n", "")) + "|" + norm(e.get("v", "")) + "|" + e.get("c", "") + "|" + norm(e.get("a", ""))[:40]
    if cle in faites: continue
    q = ", ".join(x for x in [e.get("n", ""), e.get("a", ""), e.get("v", "")] if x)
    rows.append({"pays": e.get("c", ""), "ville": e.get("v", ""), "nom": e.get("n", ""), "adresse_actuelle": e.get("a", ""),
                 "code_postal": e.get("z", ""), "telephone": e.get("ph", ""), "site": e.get("w", ""), "page_source": e.get("p", ""),
                 "recherche_osm": "https://www.openstreetmap.org/search?query=" + urllib.parse.quote(q), "cle": cle})
rows.sort(key=lambda r: (r["pays"], norm(r["ville"]), norm(r["nom"])))
with open("data/a_verifier.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["cle"]); w.writeheader(); w.writerows(rows)
print(f"{len(rows)} lieux à vérifier -> data/a_verifier.csv")
