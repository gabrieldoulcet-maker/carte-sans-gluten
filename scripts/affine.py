"""Second passage : ré-essaie les lieux trouvés seulement à la ville/région (ou introuvables) avec des variantes
de requête (adresse nettoyée, sans code postal, rue sans numéro, nom du lieu) pour les placer à la rue ou à l'adresse.
Met à jour data/geocode.csv ; les clés déjà ré-essayées sont notées dans data/affine_fait.csv (reprise possible)."""
import os, re, time, csv, unicodedata, requests, pandas as pd
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

GENERIQUES = set("road street lane avenue unit units shop centre center retail park shopping mall high the and calle plaza carrer avenida paseo via rue place square drive suite local market".split())
def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()).strip()
def mots(t):
    return {w for w in norm(t).split() if len(w) >= 4 and w not in GENERIQUES}
def base_nom(nom):
    return re.split(r"\s+[–—|-]\s+", nom)[0].strip()                     # « Domino's – Saltash » -> « Domino's »

def chaines_de(noms):
    """Noms présents 3 fois ou plus, et débuts de nom de 2 mots présents 5 fois ou plus (« pizza hut » dans « Pizza Hut Lincoln »)."""
    n1 = noms.value_counts()
    n2 = noms.map(lambda n: " ".join(n.split()[:2]) if len(n.split()) > 2 else "").value_counts()
    return set(n1[n1 >= 3].index) | set(n2[(n2 >= 5) & (n2.index != "")].index)

def valide(k, res, r, chaines):
    """Refuse les résultats douteux vus sur l'échantillon témoin (mauvaise succursale, homonyme, route mal lue)."""
    rank = int(res["place_rank"])
    if rank < 26: return False
    if k == "rue": return res.get("category") == "highway"               # la variante « rue » doit tomber sur une rue
    if k == "nom":
        if res.get("category") not in POI or rank < 28: return False
        trouve, cherche = norm(res["display_name"].split(",")[0]), norm(base_nom(r.nom))
        if not trouve or not set(trouve.split()) <= set(cherche.split()) | set(norm(r.nom).split()): return False  # « Casita Andina » ≠ « Andina »
        n = norm(base_nom(r.nom))
        chaine = next((c for c in chaines if n == c or n.startswith(c + " ")), None)  # « Pizza Hut Warrington » -> chaîne « pizza hut »
        if chaine:                                                        # chaîne : la succursale doit correspondre à l'adresse
            indices = (mots(r.adresse) | mots(norm(r.nom)[len(chaine):])) - mots(r.ville)  # la ville ne distingue pas les succursales
            return bool(indices & mots(res["display_name"]))
    return True

def variantes(r):
    cp = r.code_postal
    if r.pays == "ES" and re.fullmatch(r"\d{4}", cp): cp = "0" + cp
    ville = re.sub(r"\s*\(.*\)", "", r.ville).strip()
    lieu = " ".join(x for x in [cp, ville] if x)
    q = []
    if r.adresse:
        c = nettoie(r.adresse, ville, cp)
        if c and not ville:                                               # sans ville, « High Street » tomberait n'importe où
            if cp: q.append(("adr", f"{c}, {cp}"))
        elif c:
            q += [("adr", f"{c}, {lieu}"), ("adr", f"{c}, {ville}")]
            ps = c.split(",")
            base = next((p for p in ps if re.search(r"\d", p) and re.search(r"[^\W\d_]{3}", p)), None)  # la partie avec le numéro est la rue
            if base is None:                                              # « Plaza Catalunya, 21 » : numéro à part, la rue le précède
                base = next((ps[i - 1] for i, p in enumerate(ps) if i and re.fullmatch(r"\s*\d+\w?\s*", p)), None)
            if base and not re.search(r"\b[A-Z]{1,3}\s?-?\s?\d", base):    # pas « Carretera CV 213 » / « AP-7 »
                rue = NUMERO.sub(" ", re.sub(r"\(.*?\)", "", base)).strip(" ,-:")
                if mots(rue): q.append(("rue", f"{rue}, {ville}"))
    nom = base_nom(r.nom)
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
    noms = pd.read_csv("data/a_geocoder.csv", dtype=str).fillna("").nom.map(lambda n: norm(base_nom(n)))
    chaines = chaines_de(noms)
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
            if valide(k, res, r, chaines):
                gains[r.cle] = {"lat": res["lat"], "lon": res["lon"], "precision": "exacte" if rank >= 28 and k != "rue" else "rue",
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
