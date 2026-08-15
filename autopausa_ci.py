# -*- coding: utf-8 -*-
"""Auto-pausa de ads de TESTEO (24/7). Decision 100% Utmify; ejecucion en Meta.
Regla breakeven sobre el FRONT, POR ANUNCIO. Descubre las campañas de testeo por NOMBRE
(no hardcodeadas): "ABO TESTEO"/"TESTEO" activas, mercado por bandera/pais, excluye party-kit.
Credenciales: env (UTMIFY_URL, META_TOKEN) o, si faltan, archivos locales."""
import json, os, sys, urllib.request, urllib.parse, datetime
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
DASH = "69cfdbde070cfeea2ad72c39"
TS   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

FRONTS = {"EN":29.00, "ES":19.99, "BR":14.99, "FR":19.90, "DE":28.90, "IT":24.90}
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

def _pull(level):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"get_meta_ad_objects","arguments":{"dashboardId":DASH,"level":level,"orderBy":"greater_loss","limit":600}}}).encode()
    H = {"Content-Type":"application/json","Accept":"application/json, text/event-stream",
         "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}
    raw = urllib.request.urlopen(urllib.request.Request(UTMIFY_URL,data=body,headers=H),timeout=250).read().decode()
    if "data:" in raw:
        for ln in raw.splitlines():
            if ln.startswith("data:"): raw = ln[5:].strip(); break
    return json.loads(json.loads(raw)["result"]["content"][0]["text"]).get("results",[])

class UtmifyEmpty(Exception): pass

def pull(level, minrows):
    for i in range(8):
        try: r = _pull(level)
        except Exception as e: print("pull %s intento %d fallo: %s"%(level,i+1,str(e)[:100])); continue
        if len(r) >= minrows: return r
        print("pull %s intento %d incompleto: %d filas"%(level,i+1,len(r)))
    raise UtmifyEmpty("Utmify no devolvio universo plausible (%s). NO se pausa nada (salida limpia)."%level)

def meta_pause(ad_id):
    data = urllib.parse.urlencode({"status":"PAUSED","access_token":TOKEN}).encode()
    urllib.request.urlopen(urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s"%ad_id, data=data), timeout=30).read()

def main():
    # 1) DESCUBRIR campañas de testeo activas por nombre -> {campaignId: (mercado, front)}
    camps = pull("campaign", 50)
    scope = {}
    for c in camps:
        nm = c.get("name","") or ""
        if c.get("status") == "ACTIVE" and is_testeo(nm):
            mk = market(nm)
            if mk in FRONTS: scope[c.get("id")] = (mk, FRONTS[mk])
    print("%s | campañas de testeo activas: %d"%(TS, len(scope)))
    if not scope:
        print("no hay campañas de testeo activas."); return
    # 2) ads -> pausar POR ANUNCIO el que cruzo su breakeven
    ads = {a["id"]: a for a in pull("ad", 100)}.values()
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
    print("%s | %s=%d"%(TS, "SE PAUSARIAN" if DRY else "apagados", len(paused)))
    for mkt,name,sp,fs,g in sorted(paused, key=lambda x:-x[2]):
        print("  PAUSED %-3s %-18s $%6.2f %dv (gate $%.2f)"%(mkt,name,sp,fs,g))

if __name__ == "__main__":
    try:
        main()
    except UtmifyEmpty as e:
        print(e)   # salida limpia (exit 0): la intermitencia de Utmify no es un fallo real
