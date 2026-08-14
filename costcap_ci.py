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
    for k,m in [("INGLES","EN"),("PORTUG","BR"),("BRASIL","BR"),("ESPAÑOL","ES"),("[ESP","ES"),
                ("CHILE","ES"),("FRANC","FR"),("ALEMAN","DE"),("ITALIA","IT")]:
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

def pull(level, minrows):
    for _ in range(6):
        try: r = _pull(level)
        except Exception as e: print("pull %s fallo: %s"%(level,str(e)[:80])); continue
        if len(r) >= minrows: return r
        print("pull %s incompleto: %d filas"%(level,len(r)))
    raise RuntimeError("Utmify no devolvio universo plausible (%s). NO se toca nada."%level)

def meta_pause(adset_id):
    data = urllib.parse.urlencode({"status":"PAUSED","access_token":TOKEN}).encode()
    urllib.request.urlopen(urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s"%adset_id, data=data), timeout=30).read()

def main():
    # 1) campañas cost-cap TELAS ACTIVAS -> {campaignId: (market, front, nombre)}
    camps = pull("campaign", 50)
    scope = {}
    for c in camps:
        nm = c.get("name","") or ""
        if "COST CAP" in nm.upper() and "TELAS" in nm.upper() and c.get("status") == "ACTIVE":
            mk = market(nm)
            if mk in FRONTS:
                scope[c.get("id")] = (mk, FRONTS[mk], nm)
    print("%s | cost-cap TELAS activas: %d"%(TS, len(scope)))
    if not scope:
        print("no hay cost-cap activas. nada que hacer."); return

    # 2) NIVEL CONJUNTO directo (nunca agregar desde ads: el status del ad miente)
    adsets = pull("adset", 300)
    paused, informar = [], []
    for a in adsets:
        cid = a.get("campaignId")
        if cid not in scope: continue
        if a.get("status") != "ACTIVE": continue          # estado REAL del conjunto
        mk, front, cname = scope[cid]
        sp = (a.get("spend") or 0)/100.0
        fs = sum(p.get("approvedOrdersCount",0) for p in (a.get("approvedOrdersByProductId") or {}).values()
                 if p.get("name") in FRONT_NAMES)
        if fs >= 6:
            informar.append((mk, a.get("id"), sp, fs, cname)); continue   # 6+ ventas -> decide el cliente
        if sp >= threshold(front, fs):
            gate = threshold(front, fs)
            if not DRY:
                try: meta_pause(a.get("id"))
                except Exception as e: print("ERROR pausando adset %s: %s"%(a.get("id"),str(e)[:80])); continue
            paused.append((mk, a.get("id"), sp, fs, round(gate,2), cname))

    print("%s CONJUNTOS %s (%d):"%("[DRY] " if DRY else "", "que se pausarian" if DRY else "PAUSADOS", len(paused)))
    for mk,asid,sp,fs,gate,cn in sorted(paused, key=lambda x:-x[2]):
        print("   %-3s adset %s  $%7.2f  %dv  (gate $%.2f)  | %s"%(mk,asid,sp,fs,gate,cn[:40]))
    if informar:
        print(">> con 6+ ventas (NO se tocan, decidis vos): %d"%len(informar))
        for mk,asid,sp,fs,cn in sorted(informar,key=lambda x:-x[2])[:10]:
            print("   %-3s adset %s  $%7.2f  %dv  | %s"%(mk,asid,sp,fs,cn[:40]))

if __name__ == "__main__":
    main()
