# -*- coding: utf-8 -*-
"""AUDITOR DEL AUTO-PAUSA (vigila al vigilante).

Nacio el 23/09/2026 porque el cliente encontro a mano un ad gastando sin vender que el monitor
dejaba pasar (ordenes no cobradas daban inmunidad eterna). El fix tapo ESE agujero; este script
existe para cazar CUALQUIER otro agujero futuro sin depender de que alguien mire el dashboard.

Regla simple e independiente de la logica del monitor: un ad de TESTEO que esta ACTIVE,
no tiene ventas aprobadas y ya gasto mas de 1x el front, NO deberia seguir vivo. Si aparece
alguno, algo se escapo.

Uso:  python auditar_autopausa.py          -> solo informa
      PAUSAR=1 python auditar_autopausa.py -> ademas los apaga
"""
import sys, io, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import autopausa_ci as A

PAUSAR = os.environ.get("PAUSAR") == "1"
FUGAS = []

for label, dash, resolver, fronts in (
        ("TELAS", A.DASH, A.market, A.FRONTS),
        ("GERIACTIVA", A.DASH_GA, A.market_ga, A.FRONTS_GA)):
    # Zentro NO se audita: esta en el test del metodo de campana unica, donde no se pausan creativos.
    try:
        camps = A.pull("campaign", 1, dash)
    except A.UtmifyEmpty as e:
        print("%s | %s: %s" % (A.TS, label, e)); continue
    scope = {}
    for c in camps:
        nm = c.get("name", "") or ""
        if c.get("status") == "ACTIVE" and A.is_testeo(nm):
            if label == "TELAS" and "GERIACTIV" in nm.upper(): continue
            mk = resolver(nm)
            if mk in fronts: scope[c.get("id")] = (mk, fronts[mk])
    filtros = ([{"adObjectStatuses": ["ACTIVE"], "nameContains": "AD TELAS"},
                {"adObjectStatuses": ["ACTIVE"], "nameContains": "AD IMG"}]
               if label == "TELAS" else [{"adObjectStatuses": ["ACTIVE"]}])
    rows = []
    for k, f in enumerate(filtros):
        try: rows += A.pull("ad", 1, dash, f)
        except A.UtmifyEmpty: pass
    if not rows:
        print("%s | %s | sin universo, no se audita" % (A.TS, label)); continue
    for a in {x["id"]: x for x in rows}.values():
        cid = a.get("campaignId")
        if cid not in scope or a.get("status") != "ACTIVE": continue
        mkt, front = scope[cid]
        sp = (a.get("spend") or 0) / 100.0
        if A.sales_count(a) > 0: continue          # vendio: no es fuga
        if A.is_profitable(a): continue            # rentable: jamas se toca
        if sp < front: continue                    # todavia no gasto ni 1x el front
        FUGAS.append((label, mkt, a.get("name"), sp, front, a.get("id"),
                      int(a.get("totalOrdersCount") or 0), A.num(a.get("revenue")) / 100.0))

if not FUGAS:
    print("%s | AUDITORIA OK: ningun ad de testeo activo gastando sin vender por encima del front." % A.TS)
    sys.exit(0)

print("%s | *** %d FUGA(S): ads ACTIVOS sin ventas que ya pasaron 1x el front ***" % (A.TS, len(FUGAS)))
for label, mkt, nm, sp, front, aid, ords, rev in sorted(FUGAS, key=lambda x: -x[3]):
    print("   %-10s %-6s %-30s $%7.2f (front $%.2f) ordenes=%d rev=$%.2f  id=%s"
          % (label, mkt, str(nm)[:30], sp, front, ords, rev, aid))
    if PAUSAR:
        try:
            A.meta_pause(aid); print("        -> PAUSADO")
        except Exception as e:
            print("        -> ERROR al pausar: %s" % str(e)[:120])
print("\nSi aparecen fugas, el monitor tiene un agujero: revisar hidden_sales/unapproved_only/is_profitable.")
sys.exit(1)
