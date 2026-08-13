# -*- coding: utf-8 -*-
"""Auto-pausa de ads de TESTEO para GitHub Actions (corre 24/7 sin depender de la PC).
Decision 100% Utmify; ejecucion en Meta. Regla breakeven sobre el FRONT.
Secrets requeridos (env): UTMIFY_URL, META_TOKEN."""
import json, os, urllib.request, urllib.parse, datetime, sys

UTMIFY_URL = os.environ["UTMIFY_URL"].strip().lstrip("﻿").strip()
TOKEN      = os.environ["META_TOKEN"].strip().lstrip("﻿").strip()
DASH       = "69cfdbde070cfeea2ad72c39"          # TELAS (ESPANOL) - contiene la cuenta TESTEO
TS         = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

# campaignId -> (mercado, front)
CAMP = {
 "120253176614960231": ("BR", 14.99),
 "120252574168510231": ("ES", 19.99),
 "120253333066970231": ("EN", 29.00),
 "120253640267520231": ("FR", 19.90),
 "120253672325010231": ("DE", 28.90),
 "120253672337700231": ("IT", 24.90),
}
CAMP_IDS = set(CAMP)
FRONT_NAMES = {"The Ultimate Knitting Library","LA BIBLIOTECA DEFINITIVA DE TEJIDO",
 "A Biblioteca Definitiva do Trico","La Biblioteca Definitiva del Tricot",
 "Die Ultimative Strickbibliothek","La Biblioteca Definitiva della Maglia"}
MIN_KNITTING = 50

def threshold(front, ventas):
    if ventas == 0: return 0.7 * front
    if ventas <= 3: return ventas * front
    return 3 * front + (ventas - 3) * 0.5 * front

def _one_pull(order):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"get_meta_ad_objects","arguments":{"dashboardId":DASH,"level":"ad","orderBy":order,"limit":500}}}).encode()
    H = {"Content-Type":"application/json","Accept":"application/json, text/event-stream",
         "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}
    raw = urllib.request.urlopen(urllib.request.Request(UTMIFY_URL,data=body,headers=H),timeout=250).read().decode()
    if "data:" in raw:
        for ln in raw.splitlines():
            if ln.startswith("data:"): raw = ln[5:].strip(); break
    return json.loads(json.loads(raw)["result"]["content"][0]["text"]).get("results",[])

def utmify(order):
    last = []
    for intento in range(5):
        try:
            r = _one_pull(order)
        except Exception as e:
            print("pull intento %d fallo: %s" % (intento+1, str(e)[:120])); continue
        kn = sum(1 for a in r if a.get("campaignId") in CAMP_IDS)
        if kn >= MIN_KNITTING:
            return r
        print("pull intento %d incompleto: total=%d knitting=%d" % (intento+1, len(r), kn)); last = r
    raise RuntimeError("Utmify no devolvio universo plausible tras 5 intentos. NO se pausa nada.")

def meta_pause(ad_id):
    data = urllib.parse.urlencode({"status":"PAUSED","access_token":TOKEN}).encode()
    urllib.request.urlopen(urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s" % ad_id, data=data), timeout=30).read()

def main():
    ads = {a["id"]: a for a in utmify("greater_loss")}.values()
    paused = []
    for a in ads:
        cid = a.get("campaignId")
        if cid not in CAMP or a.get("status") != "ACTIVE": continue
        mkt, front = CAMP[cid]
        sp = (a.get("spend") or 0) / 100.0
        fs = sum(p.get("approvedOrdersCount",0) for p in (a.get("approvedOrdersByProductId") or {}).values()
                 if p.get("name") in FRONT_NAMES)
        if sp < threshold(front, fs): continue
        try:
            meta_pause(a["id"])
            paused.append((mkt, a.get("name"), round(sp,2), fs, round(threshold(front,fs),2)))
        except Exception as e:
            print("ERROR pausando %s: %s" % (a.get("name"), str(e)[:120]))
    print("%s | apagados=%d" % (TS, len(paused)))
    for mkt,name,sp,fs,g in sorted(paused, key=lambda x:-x[2]):
        print("  PAUSED %-3s %-16s $%6.2f %dv (gate $%.2f)" % (mkt,name,sp,fs,g))

if __name__ == "__main__":
    main()
