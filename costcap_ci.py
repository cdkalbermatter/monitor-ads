# -*- coding: utf-8 -*-
"""Auto-pausa de COST-CAP a nivel CONJUNTO DE ANUNCIO (adset). Cada 30 min.
Regla breakeven sobre el FRONT, SOLO hasta la 5a venta (6+ = decide el cliente).
Decision 100% Utmify; ejecucion en Meta (pausa el adset). Secrets env: UTMIFY_URL, META_TOKEN.
DRY_RUN=1 -> no pausa, solo reporta."""
import json, os, sys, urllib.request, urllib.parse, datetime
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # nunca crashear por emojis
except Exception: pass

UTMIFY_URL = os.environ["UTMIFY_URL"].strip().lstrip("﻿").strip()
TOKEN      = os.environ["META_TOKEN"].strip().lstrip("﻿").strip()
DASH       = "69cfdbde070cfeea2ad72c39"
DRY        = os.environ.get("DRY_RUN") == "1"
TS         = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

FRONTS = {"EN":29.00, "ES":19.99, "BR":14.99, "FR":19.90, "DE":28.90, "IT":24.90}
FRONT_NAMES = {"The Ultimate Knitting Library","LA BIBLIOTECA DEFINITIVA DE TEJIDO",
 "A Biblioteca Definitiva do Trico","La Biblioteca Definitiva del Tricot",
 "Die Ultimative Strickbibliothek","La Biblioteca Definitiva della Maglia"}

def market(name):
    n = (name or "").upper()
    # orden: mas especifico primero. Cubre nombres largos (ES/PT) y codigos cortos entre corchetes.
    for k,m in [("INGLES","EN"),("INGLÊS","EN"),("ENGLISH","EN"),("[EN]","EN"),("[UK]","EN"),("[US]","EN"),
                ("PORTUG","BR"),("BRASIL","BR"),("[BR]","BR"),("[PT]","BR"),
                ("ESPAÑOL","ES"),("ESPANOL","ES"),("[ESP","ES"),("[ES]","ES"),("CHILE","ES"),("MEXICO","ES"),
                ("FRANC","FR"),("[FR]","FR"),
                ("ALEMAN","DE"),("ALEMÁN","DE"),("GERMAN","DE"),("[DE]","DE"),
                ("ITALIA","IT"),("ITALIAN","IT"),("[IT]","IT")]:
        if k in n: return m
    return None

def threshold(front, v):
    if v == 0: return 0.7*front
    if v <= 3: return v*front
    return 3*front + (v-3)*0.5*front   # 4->3.5x, 5->4x

def num(x):
    try: return float(x or 0)
    except: return 0.0

def sales_count(o):
    # numero AUTORITATIVO de ordenes aprobadas (front+upsells) del propio objeto.
    # Mas confiable que sumar approvedOrdersByProductId conjunto por conjunto (Utmify atribuye
    # tarde a nivel adset -> subconteo -> pausaba ganadores). Ver bug alemana AD-29 (2026-08-15).
    return int(o.get("approvedOrdersCount") or 0)

def hidden_sales(o):
    # gasto>0 pero el lado de ventas vino en 0 con revenue/ordenes >0 -> glitch de Utmify: NO confiar en "0 ventas"
    return sales_count(o)==0 and (num(o.get("revenue"))>0 or num(o.get("grossRevenue"))>0 or int(o.get("totalOrdersCount") or 0)>0)

def is_profitable(o):
    return num(o.get("profit")) > 0   # ya rentable -> JAMAS pausar

def _pull(level):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"get_meta_ad_objects","arguments":{"dashboardId":DASH,"level":level,"orderBy":"greater_loss","limit":500}}}).encode()
    H = {"Content-Type":"application/json","Accept":"application/json, text/event-stream",
         "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}
    raw = urllib.request.urlopen(urllib.request.Request(UTMIFY_URL,data=body,headers=H),timeout=250).read().decode()
    if "data:" in raw:
        for ln in raw.splitlines():
            if ln.startswith("data:"): raw = ln[5:].strip(); break
    return json.loads(json.loads(raw)["result"]["content"][0]["text"]).get("results",[])

class UtmifyEmpty(Exception): pass

def pull(level, minrows):
    for _ in range(8):
        try: r = _pull(level)
        except Exception as e: print("pull %s fallo: %s"%(level,str(e)[:80])); continue
        if len(r) >= minrows: return r
        print("pull %s incompleto: %d filas"%(level,len(r)))
    raise UtmifyEmpty("Utmify no devolvio universo plausible (%s). NO se toca nada (salida limpia)."%level)

def meta_pause(adset_id):
    data = urllib.parse.urlencode({"status":"PAUSED","access_token":TOKEN}).encode()
    urllib.request.urlopen(urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s"%adset_id, data=data), timeout=30).read()

def main():
    # 1) descubrir por nombre: COST-CAP (se cortan a nivel CONJUNTO) y AISLADAS (a nivel CAMPAÑA)
    camps = pull("campaign", 50)
    scope_cc = {}       # cost-cap  -> corte por adset
    scope_ais = {}      # aisladas  -> corte por campaña
    camp_by_id = {}     # objeto campaña completo (para leer ventas/revenue/profit autoritativos)
    PARTY = ("KF360","FIESTA","FESTA","PARTY","KIT 360","🎉","KF 360")
    for c in camps:
        nm = c.get("name","") or ""; nmu = nm.upper()
        if any(p in nmu for p in PARTY) or c.get("status") != "ACTIVE": continue
        mk = market(nm)
        if mk not in FRONTS: continue
        camp_by_id[c.get("id")] = c
        if "AISLADA" in nmu: scope_ais[c.get("id")] = (mk, FRONTS[mk], nm)
        elif "COSTCAP" in nmu.replace(" ",""): scope_cc[c.get("id")] = (mk, FRONTS[mk], nm)
    print("%s | cost-cap: %d | aisladas: %d"%(TS, len(scope_cc), len(scope_ais)))
    if not scope_cc and not scope_ais:
        print("nada activo."); return

    paused, informar, saved = [], [], []

    # 2a) AISLADAS: nivel CAMPAÑA, leyendo del OBJETO CAMPAÑA directo (NO sumando adsets)
    for cid, (mk, front, cname) in scope_ais.items():
        c = camp_by_id[cid]
        sp = num(c.get("spend"))/100.0
        n  = sales_count(c)
        if hidden_sales(c):                       # glitch Utmify: gasto sin ventas -> no tocar
            saved.append((mk,"CAMP",cid,sp,"glitch",cname)); continue
        if n >= 6:
            informar.append((mk,"CAMP",cid,sp,n,cname)); continue
        if is_profitable(c):                      # rentable ahora -> JAMAS pausar
            saved.append((mk,"CAMP",cid,sp,"profit+",cname)); continue
        if sp >= threshold(front, n):
            if not DRY:
                try: meta_pause(cid)              # pausa la CAMPAÑA entera
                except Exception as e: print("ERROR pausando campaña %s: %s"%(cid,str(e)[:80])); continue
            paused.append((mk,"CAMP",cid,sp,n,round(threshold(front,n),2),cname))

    # 2b) COST-CAP: nivel CONJUNTO (solo conjuntos ACTIVE)
    adsets = pull("adset", 300)
    for a in adsets:
        cid = a.get("campaignId")
        if cid not in scope_cc or a.get("status") != "ACTIVE": continue
        mk, front, cname = scope_cc[cid]
        parent = camp_by_id.get(cid)
        if parent and sales_count(parent) >= 6:   # campaña padre ya ganadora -> no tocar sus conjuntos
            continue
        sp = num(a.get("spend"))/100.0
        n  = sales_count(a)
        if hidden_sales(a):                        # glitch Utmify -> no tocar
            saved.append((mk,"adset",a.get("id"),sp,"glitch",cname)); continue
        if n >= 6:
            informar.append((mk,"adset",a.get("id"),sp,n,cname)); continue
        if is_profitable(a):                       # rentable ahora -> JAMAS pausar
            saved.append((mk,"adset",a.get("id"),sp,"profit+",cname)); continue
        if sp >= threshold(front, n):
            if not DRY:
                try: meta_pause(a.get("id"))
                except Exception as e: print("ERROR pausando adset %s: %s"%(a.get("id"),str(e)[:80])); continue
            paused.append((mk,"adset",a.get("id"),sp,n,round(threshold(front,n),2),cname))

    print("%s %s (%d):"%("[DRY] " if DRY else "", "SE PAUSARIAN" if DRY else "PAUSADOS", len(paused)))
    for mk,lvl,oid,sp,fs,gate,cn in sorted(paused, key=lambda x:-x[3]):
        print("   %-3s %-5s %s  $%7.2f  %dv  (gate $%.2f)  | %s"%(mk,lvl,oid,sp,fs,gate,cn[:38]))
    if informar:
        print(">> con 6+ ventas (NO se tocan, decidis vos): %d"%len(informar))
        for mk,lvl,oid,sp,fs,cn in sorted(informar,key=lambda x:-x[3])[:10]:
            print("   %-3s %-5s %s  $%7.2f  %dv  | %s"%(mk,lvl,oid,sp,fs,cn[:38]))
    if saved:
        print(">> PROTEGIDAS por guarda (rentable/glitch, NO se tocan): %d"%len(saved))
        for mk,lvl,oid,sp,why,cn in sorted(saved,key=lambda x:-x[3])[:15]:
            print("   %-3s %-5s %s  $%7.2f  [%s]  | %s"%(mk,lvl,oid,sp,why,cn[:36]))

if __name__ == "__main__":
    try:
        main()
    except UtmifyEmpty as e:
        print(e)   # salida limpia (exit 0)
