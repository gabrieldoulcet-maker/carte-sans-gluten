"""Intègre data/corrections/*.csv (un fichier par contributeur) dans data/geocode.csv.
statut « trouve » : coordonnées lat/lon si fournies, sinon l'adresse corrigée est géocodée (Nominatim, 1 req/s)
et retenue si elle tombe au moins à la rue. Les autres statuts (ferme, introuvable) sont seulement conservés.
Chaque ligne traitée est notée dans data/corrections_faites.csv avec son résultat."""
import csv, glob, os, time, requests, pandas as pd
CONTACT = os.environ.get("CONTACT", "carte-sans-gluten")
SRC, GP, LOG = "data/corrections/*.csv", "data/geocode.csv", "data/corrections_faites.csv"
COLS = ["cle", "statut", "adresse_corrigee", "code_postal", "ville", "lat", "lon", "source_url", "auteur", "note"]
S = requests.Session(); S.headers["User-Agent"] = f"CarteSansGluten/1.0 ({CONTACT})"
last = 0.0
def ask(q, cc):
    global last
    w = last + 1.0 - time.time()
    if w > 0: time.sleep(w)
    last = time.time()
    r = S.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": cc.lower()}, timeout=30)
    return (r.json() or [None])[0] if r.status_code == 200 else None

def main():
    parts = []
    for fn in sorted(glob.glob(SRC)):
        d = pd.read_csv(fn, dtype=str).fillna("")
        d.columns = [x.strip().lower() for x in d.columns]
        manque = [k for k in ["cle", "statut"] if k not in d.columns]
        if manque: print(f"{fn} ignoré : colonnes manquantes {manque}"); continue
        parts.append(d)
    if not parts: print("pas de corrections"); return
    c = pd.concat(parts).reindex(columns=COLS).fillna("").drop_duplicates("cle", keep="last")
    fait = pd.read_csv(LOG, dtype=str).fillna("") if os.path.exists(LOG) else pd.DataFrame(columns=["cle", "resultat"])
    todo = c[~c.cle.isin(set(fait.cle))]
    g = pd.read_csv(GP, dtype=str).fillna("").set_index("cle")
    log = []
    for r in todo.itertuples():
        st = r.statut.strip().lower()
        if r.cle not in g.index: log.append((r.cle, "cle inconnue")); continue
        if st != "trouve": log.append((r.cle, st or "statut vide")); continue
        pays = r.cle.split("|")[2] if r.cle.count("|") >= 3 else ""
        lat, lon = getattr(r, "lat", ""), getattr(r, "lon", "")
        try:
            ok = lat and lon and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
        except ValueError:
            ok = False
        if ok:
            maj = {"lat": lat, "lon": lon, "precision": "exacte", "place_rank": "30", "requete": "correction manuelle", "resultat_osm": getattr(r, "source_url", "")[:200]}
        else:
            q = ", ".join(x for x in [getattr(r, "adresse_corrigee", ""), " ".join(x for x in [getattr(r, "code_postal", ""), getattr(r, "ville", "")] if x)] if x)
            res = ask(q, pays) if q else None
            if not res or int(res["place_rank"]) < 26: log.append((r.cle, f"adresse non trouvee : {q}")); continue
            rank = int(res["place_rank"])
            maj = {"lat": res["lat"], "lon": res["lon"], "precision": "exacte" if rank >= 28 else "rue", "place_rank": str(rank), "requete": q, "resultat_osm": res["display_name"][:200]}
        for k, v in maj.items(): g.at[r.cle, k] = v
        log.append((r.cle, f"place ({maj['precision']})"))
    g.reset_index().to_csv(GP, index=False)
    ex = os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not ex: w.writerow(["cle", "resultat"])
        w.writerows(log)
    n = sum(1 for _, x in log if x.startswith("place"))
    print(f"{len(log)} corrections traitees, {n} lieux places")

if __name__ == "__main__":
    main()
