# -*- coding: utf-8 -*-
"""Auto-pausa de ads de TESTEO (24/7). Decision 100% Utmify; ejecucion en Meta.
Regla breakeven sobre el FRONT, POR ANUNCIO. Descubre las campañas de testeo por NOMBRE
(no hardcodeadas): "ABO TESTEO"/"TESTEO" activas, mercado por bandera/pais, excluye party-kit.
Credenciales: env (UTMIFY_URL, META_TOKEN) o, si faltan, archivos locales."""
import json, time, os, sys, urllib.request, urllib.parse, datetime
import time
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # nunca crashear por emojis
except Exception: pass

def _cred():
    u = os.environ.get("UTMIFY_URL")
    if not u: u = open(r"C:\Users\ckalb\.utmify\mcp_url.txt", encoding="utf-8").read()
    t = os.environ.get("META_TOKEN")
    if not t: t = json.load(open(r"C:\Users\ckalb\.meta_ads\credentials.json", encoding="utf-8"))["user_access_token"]
    return u.strip().lstrip("\ufeff").strip(), t.strip().lstrip("\ufeff").strip()
UTMIFY_URL, TOKEN = _cred()
DRY  = os.environ.get("DRY_RUN") == "1"
DASH = "69cfdbde070cfeea2ad72c39"      # TELAS (tejido)
DASH_GA = "6a3efe2e78421ff586fc4853"   # GeriActiva (comun LATAM, Argentina, Cognitiva, GeriActive EN)
DASH_ZP = "6aaa84b404e276a6cd132545"   # Zentro (Pilates)
TS   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

FRONTS = {"EN":29.00, "ES":19.99, "BR":14.99, "FR":19.90, "DE":28.90, "IT":24.90}
# Fronts GeriActiva (USD, verificados 17/09/2026 con landing en vivo + revenue/orden de Utmify)
FRONTS_GA = {"GA-COG":18.00, "GA-EN":27.00, "GA-AR":16.99, "GA-ES":16.99}
FRONTS_ZP = {"ZENTRO":27.00}   # landing zentropilates US$27 (17/09/2026)
FRONT_NAMES = {"The Ultimate Knitting Library","LA BIBLIOTECA DEFINITIVA DE TEJIDO",
 "A Biblioteca Definitiva do Trico","La Biblioteca Definitiva del Tricot",
 "Die Ultimative Strickbibliothek","La Biblioteca Definitiva della Maglia"}
PARTY = ("KF360","KF 360","FIESTA","FESTA","PARTY","\U0001F389")

def market(name):
    n = name or ""; u = n.upper()
    if "\U0001F7E1\U0001F7E2\U0001F7E1" in n or "BRASIL" in u or "PORTUG" in u: return "BR"
    if "\U0001F534\U0001F534\U0001F534" in n or "INGLES" in u or "ENGLISH" in u: return "EN"
    if "\U0001F535\u26AA\U0001F534" in n or "FRANC" in u: return "FR"
    if "\u26AB\U0001F534\U0001F7E1" in n or "ALEMAN" in u or "GERMAN" in u: return "DE"
    if "\U0001F7E2\u26AA\U0001F534" in n or "ITALIA" in u: return "IT"
    if "\U0001F534\U0001F7E1\U0001F534" in n or "ESPA\u00d1OL" in u or "[ESP" in u or "CHILE" in u: return "ES"
    return None

def market_ga(name):
    n = name or ""; u = n.upper()
    if "GERIACTIV" not in u: return None
    if "COGNITIVA" in u: return "GA-COG"
    if "ARGENTINA" in u: return "GA-AR"
    if "\U0001F534\U0001F534\U0001F534" in n or "[INGLES]" in u or "ENGLISH" in u: return "GA-EN"
    if "\U0001F534\U0001F7E1\U0001F534" in n or "ESPAÑOL" in u: return "GA-ES"
    return None   # IT/DE/FR u otros: sin front verificado -> no se tocan

def market_zp(name):
    return "ZENTRO" if "ZENTRO" in (name or "").upper() or "PILATES" in (name or "").upper() else None

def is_testeo(name):
    u = (name or "").upper()
    if any(p in name.upper() for p in PARTY): return False
    return "ABO TESTEO" in u or "TESTEO" in u

def threshold(front, v):
    if v == 0: return 0.7*front
    if v <= 3: return v*front
    return 3*front + (v-3)*0.5*front

def num(x):
    try: return float(x or 0)
    except: return 0.0

def sales_count(o):
    # ordenes aprobadas AUTORITATIVAS (front+upsells) del propio objeto; mas confiable que
    # sumar approvedOrdersByProductId (Utmify atribuye tarde -> subconteo -> pausaba ganadores)
    return int(o.get("approvedOrdersCount") or 0)

def hidden_sales(o):
    return sales_count(o)==0 and (num(o.get("revenue"))>0 or num(o.get("grossRevenue"))>0 or int(o.get("totalOrdersCount") or 0)>0)

def is_profitable(o):
    return num(o.get("profit")) > 0

def _pull(level, dash=DASH, extra=None):
    args = {"dashboardId":dash,"level":level,"orderBy":"greater_loss","limit":600}
    if extra: args.update(extra)   # ej. solo ACTIVE + nameContains (TELAS a nivel ad sin filtro da error en Utmify)
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"get_meta_ad_objects","arguments":args}}).encode()
    H = {"Content-Type":"application/json","Accept":"application/json, text/event-stream",
         "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}
    raw = urllib.request.urlopen(urllib.request.Request(UTMIFY_URL,data=body,headers=H),timeout=250).read().decode()
    if "data:" in raw:
        for ln in raw.splitlines():
            if ln.startswith("data:"): raw = ln[5:].strip(); break
    return json.loads(json.loads(raw)["result"]["content"][0]["text"]).get("results",[])

class UtmifyEmpty(Exception): pass

def pull(level, minrows, dash=DASH, extra=None):
    for i in range(4):
        try: r = _pull(level, dash, extra)
        except Exception as e:
            print("pull %s intento %d fallo: %s"%(level,i+1,str(e)[:100]))
            if i < 3: time.sleep(25)   # ESPERA entre reintentos (evita rate-limit)
            continue
        if len(r) >= minrows: return r
        print("pull %s intento %d incompleto: %d filas"%(level,i+1,len(r)))
        if i < 3: time.sleep(25)
    raise UtmifyEmpty("Utmify no devolvio universo plausible (%s). NO se pausa nada (salida limpia)."%level)

def meta_pause(ad_id):
    data = urllib.parse.urlencode({"status":"PAUSED","access_token":TOKEN}).encode()
    urllib.request.urlopen(urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s"%ad_id, data=data), timeout=30).read()

def main():
    # Tejido (TELAS) + GeriActiva (comun LATAM, Argentina, Cognitiva, EN). Cada tablero por separado:
    # si Utmify falla en uno, el otro igual se procesa.
    total = []
    for label, dash, resolver, fronts, mincamp, minads in (
            ("TELAS", DASH, market, FRONTS, 50, 30),
            ("GERIACTIVA", DASH_GA, market_ga, FRONTS_GA, 10, 30),
            ("ZENTRO", DASH_ZP, market_zp, FRONTS_ZP, 1, 1)):
        # TELAS a nivel ad: sin nameContains Utmify devuelve error/vacio -> pedir por prefijos de nombre y unir
        adfilter = ([{"adObjectStatuses":["ACTIVE"],"nameContains":"AD TELAS"},{"adObjectStatuses":["ACTIVE"],"nameContains":"AD IMG"}]
                    if label == "TELAS" else [{"adObjectStatuses":["ACTIVE"]}])
        try:
            total += run_dash(label, dash, resolver, fronts, mincamp, minads, adfilter)
        except UtmifyEmpty as e:
            print("%s | %s: %s"%(TS, label, e))
    print("%s | TOTAL %s=%d"%(TS, "SE PAUSARIAN" if DRY else "apagados", len(total)))

def run_dash(label, dash, resolver, fronts, mincamp, minads, adfilter=None):
    # 1) DESCUBRIR campañas de testeo activas por nombre -> {campaignId: (mercado, front)}
    camps = pull("campaign", mincamp, dash)
    scope = {}
    for c in camps:
        nm = c.get("name","") or ""
        if c.get("status") == "ACTIVE" and is_testeo(nm):
            if label == "TELAS" and "GERIACTIV" in nm.upper(): continue
            mk = resolver(nm)
            if mk in fronts: scope[c.get("id")] = (mk, fronts[mk])
    print("%s | %s | campañas de testeo activas: %d %s"%(TS, label, len(scope), sorted(set(m for m,_ in scope.values()))))
    if not scope:
        return []
    # 2) ads -> pausar POR ANUNCIO el que cruzo su breakeven
    rows = []
    for k, f in enumerate(adfilter or [None]):
        try: rows += pull("ad", minads if k == 0 else 1, dash, f)
        except UtmifyEmpty:
            if k == 0: raise          # el pull principal es obligatorio; los extra son opcionales
            print("%s | %s | pull extra %s vacio (se sigue con el principal)"%(TS, label, f))
    ads = {a["id"]: a for a in rows}.values()
    paused = []
    for a in ads:
        cid = a.get("campaignId")
        if cid not in scope or a.get("status") != "ACTIVE": continue
        mkt, front = scope[cid]
        sp = (a.get("spend") or 0)/100.0
        n  = sales_count(a)
        if hidden_sales(a): continue          # glitch Utmify: gasto sin ventas -> no tocar
        if is_profitable(a): continue         # rentable ahora -> JAMAS pausar
        if sp < threshold(front, n): continue
        try:
            if not DRY: meta_pause(a["id"])
            paused.append((mkt, a.get("name"), round(sp,2), n, round(threshold(front,n),2)))
        except Exception as e:
            print("ERROR pausando %s: %s"%(a.get("name"), str(e)[:100]))
    print("%s | %s | %s=%d"%(TS, label, "SE PAUSARIAN" if DRY else "apagados", len(paused)))
    for mkt,name,sp,fs,g in sorted(paused, key=lambda x:-x[2]):
        print("  PAUSED %-6s %-28s $%7.2f %dv (gate $%.2f)"%(mkt,name,sp,fs,g))
    return paused

if __name__ == "__main__":
    try:
        main()
    except UtmifyEmpty as e:
        print(e)   # salida limpia (exit 0): la intermitencia de Utmify no es un fallo real
