"""Second passage : ré-essaie les lieux trouvés seulement à la ville/région (ou introuvables) avec des variantes
de requête (adresse nettoyée, sans code postal, rue sans numéro, nom du lieu) pour les placer à la rue ou à l'adresse.
Met à jour data/geocode.csv ; les clés déjà ré-essayées sont notées dans data/affine_fait.csv (reprise possible)."""
import os, re, time, csv, requests, pandas as pd
BUDGET = int(os.environ.get("BUDGET", 5 * 3600 + 30 * 60))
LIMIT = int(os.environ.get("LIMIT", 0))
INTERVAL = float(os.environ.get("INTERVAL", 1.0))
CONTACT = os.environ.get("CONTACT", "carte-sans-gluten")
GP, FAIT = "data/geocode.csv", "data/affine_fait.csv"
POI = {"amenity", "shop", "tourism", "leisure", "craft", "office"}

ABR = [(r"^(c/|c\.|cl\.|cl/|calle)\s*", "Calle "), (r"^(avda\.?|av\.|av/)\s*", "Avenida "), (r"^(pza\.?|plza\.?|pl\.|pç\.)\s*", "Plaza "),
       (r"^(ctra\.?|crta\.?|cra\.)\s*", "Carretera "), (r"^(pº|p\.º|pso\.?)\s*", "Paseo "), (r"^(rda\.?)\s*", "Ronda "),
       (r"^(ul\.)\s*", "ulica "), (r"^(v\.le)\s*", "Viale ")]
UNIT = re.compile(r"^(suite|ste\.?|unit|units|shop|shops|local|locales?|loc\.?|piso|planta|bajo|bajos|floor|fl\.?|apt\.?|#|kiosk|stall|bay|nº?\s*local)\b.*$|^#\s*\w+$|^\d+(st|nd|rd|th)?\s*(floor|fl)\b.*$", re.I)
NUMERO = re.compile(r"\b\d+[a-zA-Z]?(\s*[-/]\s*\d+[a-zA-Z]?)?\b|\bn[º°o]\.?\s*|\bs/n\b|\bkm\.?\s*[\d.,]+", re.I)

def nettoie(adr, ville, cp):
    """Adresse débarrassée des compléments (suite, local…), abréviations développées, mots collés séparés."""
    adr = re.sub(r"([a-z])([A-Z][a-z])", r"\1, \2", adr)                 # « Lower StreetSalhouse » -> « Lower Street, Salhouse »
    adr = re.sub(r"([a-z]{3})(\d)", r"\1, \2", adr)                        # « Derby Theatre15 Theatre Walk » -> « Derby Theatre, 15 Theatre Walk »
    adr = re.sub(r"\b(\d+)\s*[-/]\s*\d+\b", r"\1", adr)                    # « 16/17 New Road » -> « 16 New Road »
    parts, v = [], ville.lower()
    for p in re.split(r",|;|\s+/\s+", adr):
        p = re.sub(r"\s+(suite|ste\.?|unit|#|local|shop)\s*[\w-]+$", "", p.strip(), flags=re.I)
        if not p or UNIT.match(p): continue
        pl = p.lower()
        if pl == v or pl == cp.lower() or (len(pl) >= 3 and v.startswith(pl)) or cp and cp.lower() in pl and len(pl) <= len(cp) + len(v) + 2: continue
        for a, b in ABR: p = re.sub(a, b, p, flags=re.I)
        parts.append(p)
    return ", ".join(parts[:2])

def variantes(r):
    cp = r.code_postal
    if r.pays == "ES" and re.fullmatch(r"\d{4}", cp): cp = "0" + cp
    ville = re.sub(r"\s*\(.*\)", "", r.ville).strip()
    lieu = " ".join(x for x in [cp, ville] if x)
    q = []
    if r.adresse:
        c = nettoie(r.adresse, ville, cp)
        if c:
            q += [("adr", f"{c}, {lieu}"), ("adr", f"{c}, {ville}")]
            ps = c.split(",")
            base = next((p for p in ps if re.search(r"\d", p) and re.search(r"[^\W\d_]{3}", p)), ps[0])       # la partie avec le numéro est la rue
            rue = NUMERO.sub(" ", base).strip(" ,-:")
            if len(rue) >= 4: q.append(("rue", f"{rue}, {ville}"))
    nom = re.split(r"\s+[–—|-]\s+", r.nom)[0].strip()                     # « Domino's – Saltash » -> « Domino's »
    if nom and ville: q.append(("nom", f"{nom}, {ville}"))
    vus, out = set(), []
    for k, s in q:
        s = re.sub(r"\s+", " ", s).strip(" ,")
        if s.lower() not in vus and s.lower() != (r.requete or "").lower(): vus.add(s.lower()); out.append((k, s))
    return out

S = requests.Session(); S.headers["User-Agent"] = f"CarteSansGluten/1.0 ({CONTACT})"
last, nreq = 0.0, 0
def ask(q, cc):
    global last, nreq
    for i in range(3):
        w = last + INTERVAL - time.time()
        if w > 0: time.sleep(w)
        last = time.time()
        try:
            r = S.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": cc.lower()}, timeout=30)
            nreq += 1
            if r.status_code == 200: return (r.json() or [None])[0]
            print("HTTP", r.status_code, flush=True); time.sleep(60 * (i + 1))
        except Exception as e:
            print("ERR", e, flush=True); time.sleep(10)
    return None

def a_faire():
    src = pd.read_csv("data/a_geocoder.csv", dtype=str).fillna("")
    g = pd.read_csv(GP, dtype=str).fillna("")
    fait = set(pd.read_csv(FAIT, dtype=str).cle) if os.path.exists(FAIT) else set()
    m = src.merge(g[["cle", "precision", "requete"]], on="cle")
    return m[~m.precision.isin(["exacte", "rue"]) & ~m.cle.isin(fait)]

def main():
    todo = a_faire()
    if LIMIT: todo = todo.head(LIMIT)
    print(f"{len(todo)} lieux à affiner", flush=True)
    t0, gains, faits, stats = time.time(), {}, [], {}
    def save():
        nonlocal faits
        if gains:
            g2 = pd.read_csv(GP, dtype=str).fillna("")
            for c in ["lat", "lon", "precision", "place_rank", "requete", "resultat_osm"]:
                g2[c] = g2.apply(lambda x: gains[x.cle][c] if x.cle in gains else x[c], axis=1)
            g2.to_csv(GP, index=False)
        if faits:
            ex = os.path.exists(FAIT)
            with open(FAIT, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not ex: w.writerow(["cle"])
                w.writerows([[k] for k in faits])
            faits = []
    n = 0
    for n, r in enumerate(todo.itertuples(), 1):
        if time.time() - t0 > BUDGET: print("Budget atteint, reprise au prochain passage", flush=True); n -= 1; break
        cc = r.pays if len(r.pays) == 2 and r.pays != "XX" else ""
        for k, q in variantes(r):
            res = ask(q, cc)
            if not res: continue
            rank = int(res["place_rank"])
            if k == "nom" and (res.get("category") not in POI or rank < 28): continue   # nom : seulement un vrai commerce/lieu
            if rank >= 26:
                gains[r.cle] = {"lat": res["lat"], "lon": res["lon"], "precision": "exacte" if rank >= 28 else "rue",
                                "place_rank": str(rank), "requete": q, "resultat_osm": res["display_name"][:200]}
                stats[k] = stats.get(k, 0) + 1
                break
        faits.append(r.cle)
        if n % 100 == 0:
            save(); el = time.time() - t0
            print(f"{n}/{len(todo)} · {el/60:.0f} min · {len(gains)} améliorés ({len(gains)/n:.0%}) {stats} · {nreq} requêtes", flush=True)
    save()
    print(f"Fin : {n} lieux ré-essayés, {len(gains)} placés à la rue ou à l'adresse {stats} · {nreq} requêtes en {(time.time()-t0)/60:.0f} min", flush=True)

if __name__ == "__main__":
    main()
