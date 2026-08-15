# -*- coding: utf-8 -*-
"""Renombra campañas activas de TEJIDO: antepone bandera de color, saca 🧶 y la palabra TELAS.
Deja el nombre del país (el detector sigue leyendolo). DRY_RUN=1 = solo muestra."""
import json, os, re, sys, urllib.request, urllib.parse
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

UTMIFY_URL = os.environ["UTMIFY_URL"].strip().lstrip("﻿").strip()
TOKEN      = os.environ["META_TOKEN"].strip().lstrip("﻿").strip()
DASH       = "69cfdbde070cfeea2ad72c39"
DRY        = os.environ.get("DRY_RUN") == "1"

FLAG = {"EN":"🔴🔴🔴","ES":"🔴🟡🔴","BR":"🟡🟢🟡","FR":"🔵⚪🔴","DE":"⚫🔴🟡","IT":"🟢⚪🔴"}
ALLFLAGS = tuple(FLAG.values())
PARTY = ("KF360","FIESTA","FESTA","PARTY","KIT 360","🎉","KF 360")

def market(name):
    n=(name or "").upper()
    for k,m in [("INGLES","EN"),("INGLÊS","EN"),("ENGLISH","EN"),("[EN]","EN"),
                ("PORTUG","BR"),("BRASIL","BR"),("[BR]","BR"),("[PT]","BR"),
                ("ESPAÑOL","ES"),("ESPANOL","ES"),("[ESP","ES"),("[ES]","ES"),("CHILE","ES"),("MEXICO","ES"),
                ("FRANC","FR"),("[FR]","FR"),("ALEMAN","DE"),("ALEMÁN","DE"),("GERMAN","DE"),("[DE]","DE"),
                ("ITALIA","IT"),("ITALIAN","IT"),("[IT]","IT")]:
        if k in n: return m
    return None

def is_knitting(name):
    n=(name or "").upper()
    if any(p in n for p in PARTY): return False      # excluir party-kit
    return market(name) is not None

def newname(name):
    if not name or name.startswith(ALLFLAGS): return None   # ya tiene bandera
    mk=market(name)
    if not mk or not is_knitting(name): return None
    base=name.replace("🧶","")
    base=re.sub(r'\bTELAS\b','',base,flags=re.I)     # saca la palabra TELAS
    base=re.sub(r'\s{2,}',' ',base).strip()
    return FLAG[mk]+base

class UtmifyEmpty(Exception): pass

def pull_campaigns():
    r=[]
    for _ in range(8):
        body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_meta_ad_objects","arguments":{"dashboardId":DASH,"level":"campaign","orderBy":"greater_loss","limit":500}}}).encode()
        H={"Content-Type":"application/json","Accept":"application/json, text/event-stream","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}
        raw=urllib.request.urlopen(urllib.request.Request(UTMIFY_URL,data=body,headers=H),timeout=200).read().decode()
        if "data:" in raw:
            for ln in raw.splitlines():
                if ln.startswith("data:"): raw=ln[5:].strip();break
        r=json.loads(json.loads(raw)["result"]["content"][0]["text"]).get("results",[])
        if len(r)>=50: return r
    raise UtmifyEmpty("Utmify no devolvio campañas. Nada que hacer (salida limpia).")

def rename(cid, name):
    data=urllib.parse.urlencode({"name":name,"access_token":TOKEN}).encode("utf-8")
    urllib.request.urlopen(urllib.request.Request("https://graph.facebook.com/v21.0/%s"%cid, data=data), timeout=30).read()

def main():
    camps=pull_campaigns()
    active=[c for c in camps if c.get("status")=="ACTIVE"]
    done=0
    for c in active:
        nm=c.get("name",""); nn=newname(nm)
        if not nn: continue
        if DRY:
            print("  %s\n   -> %s\n"%(nm, nn))
        else:
            try: rename(c.get("id"), nn); print("OK %s"%nn)
            except Exception as e: print("ERR %s: %s"%(nm[:40], str(e)[:100])); continue
        done+=1
    print("%s %d campañas activas de tejido"%("[DRY] a renombrar:" if DRY else "RENOMBRADAS:", done))

if __name__=="__main__":
    try:
        main()
    except UtmifyEmpty as e:
        print(e)   # salida limpia (exit 0)
