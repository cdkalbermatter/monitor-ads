# -*- coding: utf-8 -*-
"""Monitor COST-CAP + AISLADAS EN VIVO (anti-rafaga).

- GASTO fresco desde Meta Graph API (poll cada ~60s; se actualiza casi al instante).
- VENTAS / revenue / profit desde Utmify (decision de ventas 100% Utmify; refresco cada ~5 min).
- AISLADAS: decision y lectura a nivel CAMPAÑA (nunca sumando conjuntos).
- COST-CAP: decision a nivel CONJUNTO (adset).
- Regla breakeven sobre el FRONT del mercado, SOLO hasta la 5a venta (6+ = decide el cliente).
- Guardas anti-falso-corte: nunca pausa si revenue(Utmify) > gasto(Meta) [rentable ahora],
  ni si Utmify trae gasto sin ventas (glitch). Ver bug alemana AD-29 (2026-08-15).
- Auto-LOOP ~55 min => cobertura casi continua aunque el cron de GitHub venga atrasado.
  ONESHOT=1 -> una sola pasada (para la tarea local de Windows). DRY_RUN=1 -> no pausa.
"""
import json, os, sys, time, urllib.request, urllib.parse
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

def _cred():
    u = os.environ.get("UTMIFY_URL")
    if not u: u = open(r"C:\Users\ckalb\.utmify\mcp_url.txt", encoding="utf-8").read()
    t = os.environ.get("META_TOKEN")
    if not t: t = json.load(open(r"C:\Users\ckalb\.meta_ads\credentials.json", encoding="utf-8"))["user_access_token"]
    return u.strip().lstrip("\ufeff").strip(), t.strip().lstrip("\ufeff").strip()
UTMIFY_URL, TOKEN = _cred()
DRY     = os.environ.get("DRY_RUN") == "1"
ONESHOT = os.environ.get("ONESHOT") == "1"
DASH    = "69cfdbde070cfeea2ad72c39"
ACCOUNTS = ["act_1225802776185769", "act_884311447637492"]  # MANUALBIDDING(cost-cap) + AUTOBIDDING(aisladas)
LOOP_MIN     = int(os.environ.get("LOOP_MIN", "55"))
SPEND_EVERY  = 120    # s: poll de gasto Meta (subido de 60 para no reventar el token)
SCOPE_EVERY  = 900    # s: refresco ventas Utmify cada 15 min (bien gentil, evita rate-limit)

FRONTS = {"EN":29.00, "ES":19.99, "BR":14.99, "FR":19.90, "DE":28.90, "IT":24.90}
PARTY  = ("KF360","KF 360","FIESTA","FESTA","PARTY","KIT 360","\U0001F389")

def market(name):
    n = name or ""; u = n.upper()
    if "\U0001F7E1\U0001F7E2\U0001F7E1" in n or "BRASIL" in u or "PORTUG" in u: return "BR"
    if "\U0001F534\U0001F534\U0001F534" in n or "INGLES" in u or "ENGLISH" in u: return "EN"
    if "\U0001F535\u26AA\U0001F534" in n or "FRANC" in u: return "FR"
    if "\u26AB\U0001F534\U0001F7E1" in n or "ALEMAN" in u or "GERMAN" in u: return "DE"
    if "\U0001F7E2\u26AA\U0001F534" in n or "ITALIA" in u: return "IT"
    if "\U0001F534\U0001F7E1\U0001F534" in n or "ESPA\u00d1OL" in u or "ESPANOL" in u or "[ESP" in u or "CHILE" in u: return "ES"
    return None

def threshold(front, v):
    if v == 0: return 0.7*front
    if v <= 3: return v*front
    return 3*front + (v-3)*0.5*front   # 4->3.5x, 5->4x

def num(x):
    try: return float(x or 0)
    except Exception: return 0.0
def sales_count(o): return int(o.get("approvedOrdersCount") or 0)   # front+upsells, autoritativo
def rev(o):         return num(o.get("revenue"))/100.0              # revenue neto Utmify (centavos)
def hidden_sales(o):
    return sales_count(o)==0 and (num(o.get("revenue"))>0 or num(o.get("grossRevenue"))>0 or int(o.get("totalOrdersCount") or 0)>0)

class UtmifyEmpty(Exception): pass

def _utm(level):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"get_meta_ad_objects","arguments":{"dashboardId":DASH,"level":level,"orderBy":"greater_loss","limit":600}}}).encode()
    H = {"Content-Type":"application/json","Accept":"application/json, text/event-stream",
         "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}
    raw = urllib.request.urlopen(urllib.request.Request(UTMIFY_URL,data=body,headers=H),timeout=200).read().decode()
    if "data:" in raw:
        for ln in raw.splitlines():
            if ln.startswith("data:"): raw = ln[5:].strip(); break
    return json.loads(json.loads(raw)["result"]["content"][0]["text"]).get("results",[])

def utm_pull(level, minrows):
    for i in range(4):
        try: r = _utm(level)
        except Exception as e:
            print("utmify %s fallo: %s"%(level,str(e)[:80]))
            if i < 3: time.sleep(25)   # ESPERA entre reintentos: no martillar (evita rate-limit)
            continue
        if len(r) >= minrows: return r
        if i < 3: time.sleep(25)
    raise UtmifyEmpty("Utmify sin universo plausible (%s)"%level)

def meta_spend():
    """{adset_id: gasto$} y {campaign_id: gasto$} FRESCOS desde Meta (lifetime)."""
    sp_ad, sp_cp = {}, {}
    for acct in ACCOUNTS:
        q = urllib.parse.urlencode({"level":"adset","fields":"spend,adset_id,campaign_id",
            "date_preset":"maximum","limit":"500","access_token":TOKEN})
        url = "https://graph.facebook.com/v21.0/%s/insights?%s"%(acct,q)
        while url:
            r = json.loads(urllib.request.urlopen(url,timeout=40).read().decode())
            for d in r.get("data",[]):
                s = num(d.get("spend")); aid = d.get("adset_id"); cid = d.get("campaign_id")
                if aid: sp_ad[aid] = sp_ad.get(aid,0.0) + s
                if cid: sp_cp[cid] = sp_cp.get(cid,0.0) + s
            url = (r.get("paging") or {}).get("next")
    return sp_ad, sp_cp

def meta_pause(oid):
    data = urllib.parse.urlencode({"status":"PAUSED","access_token":TOKEN}).encode()
    urllib.request.urlopen(urllib.request.Request(
        "https://graph.facebook.com/v21.0/%s"%oid, data=data), timeout=30).read()

def load_scope():
    """Descubre por nombre (Utmify) y arma ventas por objeto. Devuelve estructuras cacheables."""
    camps = utm_pull("campaign", 50)
    scope_ais, scope_cc, camp_obj = {}, {}, {}
    for c in camps:
        nm = c.get("name","") or ""; nmu = nm.upper()
        if any(p in nmu for p in PARTY) or c.get("status") != "ACTIVE": continue
        mk = market(nm)
        if mk not in FRONTS: continue
        camp_obj[c.get("id")] = c
        if "AISLADA" in nmu: scope_ais[c.get("id")] = (mk, FRONTS[mk], nm)
        elif "COSTCAP" in nmu.replace(" ",""): scope_cc[c.get("id")] = (mk, FRONTS[mk], nm)
    ads_cc = {}
    if scope_cc:
        for a in utm_pull("adset", 300):
            if a.get("campaignId") in scope_cc: ads_cc[a.get("id")] = a
    return scope_ais, scope_cc, camp_obj, ads_cc

def evaluate(scope_ais, scope_cc, camp_obj, ads_cc, sp_ad, sp_cp, done):
    hits = []
    # AISLADAS -> nivel CAMPAÑA
    for cid, (mk, front, cname) in scope_ais.items():
        if cid in done: continue
        c = camp_obj[cid]; sp = sp_cp.get(cid, 0.0); n = sales_count(c)
        if hidden_sales(c) or n >= 6: continue
        if rev(c) > sp: continue                 # rentable AHORA (revenue Utmify > gasto Meta fresco)
        if sp >= threshold(front, n):
            hits.append(("CAMP", cid, mk, sp, n, threshold(front,n), cname))
    # COST-CAP -> nivel CONJUNTO
    for aid, a in ads_cc.items():
        if aid in done or a.get("status") != "ACTIVE": continue
        cid = a.get("campaignId"); mk, front, cname = scope_cc[cid]
        parent = camp_obj.get(cid)
        if parent and sales_count(parent) >= 6: continue   # campaña padre ganadora -> no tocar
        sp = sp_ad.get(aid, 0.0); n = sales_count(a)
        if hidden_sales(a) or n >= 6: continue
        if rev(a) > sp: continue
        if sp >= threshold(front, n):
            hits.append(("adset", aid, mk, sp, n, threshold(front,n), cname))
    return hits

def run_once(state):
    now = time.time()
    if state["scope"] is None or now - state["scope_ts"] > SCOPE_EVERY:
        try:
            state["scope"] = load_scope(); state["scope_ts"] = now
        except UtmifyEmpty as e:
            if state["scope"] is None: raise
            print("  (scope stale, sigo con cache: %s)"%e)
    scope_ais, scope_cc, camp_obj, ads_cc = state["scope"]
    sp_ad, sp_cp = meta_spend()
    hits = evaluate(scope_ais, scope_cc, camp_obj, ads_cc, sp_ad, sp_cp, state["done"])
    stamp = time.strftime("%H:%M:%S", time.gmtime())
    for lvl, oid, mk, sp, n, gate, cname in hits:
        if not DRY:
            try: meta_pause(oid)
            except Exception as e: print("  ERROR pausando %s %s: %s"%(lvl,oid,str(e)[:70])); continue
        state["done"].add(oid)
        print("  %s %s PAUSADO %-3s %-5s $%.2f  %dv (gate $%.2f) | %s"%(
            stamp, "[DRY]" if DRY else ">>>", mk, lvl, sp, n, gate, (cname or "")[:36]))
    print("%s UTC | ais:%d cc-adsets:%d | pausados-acum:%d | hits:%d"%(
        stamp, len(scope_ais), len(ads_cc), len(state["done"]), len(hits)))

def main():
    state = {"scope": None, "scope_ts": 0.0, "done": set()}
    if ONESHOT:
        run_once(state); return
    end = time.time() + LOOP_MIN*60
    while time.time() < end:
        try:
            run_once(state)
        except UtmifyEmpty as e:
            print("scope inicial vacio (%s); reintento en 30s"%e); time.sleep(30); continue
        except Exception as e:
            print("iteracion error: %s"%str(e)[:120]); time.sleep(20); continue
        time.sleep(SPEND_EVERY)

if __name__ == "__main__":
    try:
        main()
    except UtmifyEmpty as e:
        print("salida limpia (Utmify vacio persistente): %s"%e)
