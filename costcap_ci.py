# -*- coding: utf-8 -*-
"""Auto-pausa de COST-CAP a nivel CONJUNTO DE ANUNCIO (adset). Cada 30 min.
Regla breakeven sobre el FRONT, SOLO hasta la 5a venta (6+ = decide el cliente).
Decision 100% Utmify; ejecucion en Meta (pausa el adset). Secrets env: UTMIFY_URL, META_TOKEN.
DRY_RUN=1 -> no pausa, solo reporta."""
import json, os, urllib.request, urllib.parse, datetime
from collections import defaultdict

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
    from collections import defaultdict
    # 1) descubrir por nombre: COST-CAP (se cortan a nivel CONJUNTO) y AISLADAS (a nivel CAMPAÑA)
    camps = pull("campaign", 50)
    scope_cc = {}   # cost-cap  -> corte por adset
    scope_ais = {}  # aisladas  -> corte por campaña
    PARTY = ("KF360","FIESTA","FESTA","PARTY","KIT 360","🎉","KF 360")
    for c in camps:
        nm = c.get("name","") or ""; nmu = nm.upper()
        if any(p in nmu for p in PARTY) or c.get("status") != "ACTIVE": continue
        mk = market(nm)
        if mk not in FRONTS: continue
        if "AISLADA" in nmu: scope_ais[c.get("id")] = (mk, FRONTS[mk], nm)
        elif "COSTCAP" in nmu.replace(" ",""): scope_cc[c.get("id")] = (mk, FRONTS[mk], nm)
    print("%s | cost-cap: %d | aisladas: %d"%(TS, len(scope_cc), len(scope_ais)))
    if not scope_cc and not scope_ais:
        print("nada activo."); return

    adsets = pull("adset", 300)
    def front_sales(a):
        return sum(p.get("approvedOrdersCount",0) for p in (a.get("approvedOrdersByProductId") or {}).values()
                   if p.get("name") in FRONT_NAMES)
    paused, informar = [], []

    # 2a) COST-CAP: nivel CONJUNTO (solo conjuntos ACTIVE)
    for a in adsets:
        cid = a.get("campaignId")
        if cid not in scope_cc or a.get("status") != "ACTIVE": continue
        mk, front, cname = scope_cc[cid]
        sp = (a.get("spend") or 0)/100.0; fs = front_sales(a)
        if fs >= 6:
            informar.append((mk,"adset",a.get("id"),sp,fs,cname)); continue
        if sp >= threshold(front, fs):
            if not DRY:
                try: meta_pause(a.get("id"))
                except Exception as e: print("ERROR pausando adset %s: %s"%(a.get("id"),str(e)[:80])); continue
            paused.append((mk,"adset",a.get("id"),sp,fs,round(threshold(front,fs),2),cname))

    # 2b) AISLADAS: nivel CAMPAÑA (agregar TODOS los conjuntos de la campaña -> pausar la CAMPAÑA)
    agg = defaultdict(lambda:{"sp":0.0,"fs":0})
    for a in adsets:
        cid = a.get("campaignId")
        if cid not in scope_ais: continue
        g = agg[cid]; g["sp"] += (a.get("spend") or 0)/100.0; g["fs"] += front_sales(a)
    for cid, g in agg.items():
        mk, front, cname = scope_ais[cid]
        sp, fs = g["sp"], g["fs"]
        if fs >= 6:
            informar.append((mk,"CAMP",cid,sp,fs,cname)); continue
        if sp >= threshold(front, fs):
            if not DRY:
                try: meta_pause(cid)              # pausa la CAMPAÑA entera
                except Exception as e: print("ERROR pausando campaña %s: %s"%(cid,str(e)[:80])); continue
            paused.append((mk,"CAMP",cid,sp,fs,round(threshold(front,fs),2),cname))

    print("%s %s (%d):"%("[DRY] " if DRY else "", "SE PAUSARIAN" if DRY else "PAUSADOS", len(paused)))
    for mk,lvl,oid,sp,fs,gate,cn in sorted(paused, key=lambda x:-x[3]):
        print("   %-3s %-5s %s  $%7.2f  %dv  (gate $%.2f)  | %s"%(mk,lvl,oid,sp,fs,gate,cn[:38]))
    if informar:
        print(">> con 6+ ventas (NO se tocan, decidis vos): %d"%len(informar))
        for mk,lvl,oid,sp,fs,cn in sorted(informar,key=lambda x:-x[3])[:10]:
            print("   %-3s %-5s %s  $%7.2f  %dv  | %s"%(mk,lvl,oid,sp,fs,cn[:38]))

if __name__ == "__main__":
    try:
        main()
    except UtmifyEmpty as e:
        print(e)   # salida limpia (exit 0)
