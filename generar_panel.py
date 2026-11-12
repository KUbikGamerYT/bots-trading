"""
Genera panel.html: un resumen visual de los bots de paper trading.

Lee los archivos que dejan los bots en esta misma carpeta:
    estado_bot.json, capital_diario.csv, operaciones.csv        (bot diario, 12 criptos)
    estado_bot_4h.json, capital_4h.csv, operaciones_4h.csv      (bot 4h, solo BTC)
y escribe panel.html, que se abre con doble clic en cualquier navegador (no necesita internet).

Se ejecuta solo al final de ejecutar_bot.bat y ejecutar_bot_4h.bat.
También a mano:  python generar_panel.py
"""
from __future__ import annotations
import csv, html, json, os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "panel.html")

BOTS = [
    dict(id="diario", nombre="Bot diario · 12 criptos", estado="estado_bot.json",
         capital="capital_diario.csv", ops="operaciones.csv", registro="registro_bot.txt",
         esperado="Backtest 2021–2026: +20 % al año, peor caída −26 %. Puede pasar semanas sin operar.",
         ret_anual=0.20, dd=-0.26),
    dict(id="4h", nombre="Bot 4 horas · BTC", estado="estado_bot_4h.json",
         capital="capital_4h.csv", ops="operaciones_4h.csv", registro="registro_bot_4h.txt",
         esperado="Backtest 2022–2026: +9 % al año, peor caída −16 %. Unas 1–2 operaciones al mes.",
         ret_anual=0.09, dd=-0.16),
    dict(id="acciones", nombre="Bot acciones · España y Europa (€)", estado="estado_bot_acciones.json",
         capital="capital_acciones.csv", ops="operaciones_acciones.csv", registro="registro_bot_acciones.txt",
         esperado="Cada mes se queda con las 5 empresas que más han subido en 12 meses. Backtest 2010–2026: "
                  "+14 a +20 % al año, peor caída −44 %; en 2003–2009 lo hizo peor que comprar todas. "
                  "Números algo inflados (faltan empresas que quebraron). 1–2 cambios al mes.",
         ret_anual=0.15, dd=-0.44, moneda="€", activo="Empresa"),
    dict(id="etf", nombre="Bot ETF · tendencias en 12 mercados (€)", estado="estado_bot_etf.json",
         capital="capital_etf.csv", ops="operaciones_etf.csv", registro="registro_bot_etf.txt",
         esperado="Cada mes se queda con los 3 mercados más fuertes (bolsas, bonos, oro, materias primas...). "
                  "Backtest 2007–2026: +10 a +12 % al año, peor caída −15 a −18 %. Unos 1–2 cambios al mes.",
         ret_anual=0.11, dd=-0.18, moneda="€", activo="ETF"),
]


def read_csv(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def read_json(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def tail(name, n=12):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip() for l in f if l.strip()]
    return lines[-n:]


def fnum(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def eur(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, signo=True):
    s = f"{x * 100:+.1f} %" if signo else f"{x * 100:.1f} %"
    return s.replace(".", ",")


def resumen(bot):
    st = read_json(bot["estado"]) or {}
    cap = read_csv(bot["capital"])
    ops = read_csv(bot["ops"])
    # una fila por fecha/hora (el bot diario puede escribir varias el mismo día)
    serie = {}
    for r in cap:
        serie[r.get("fecha", "")] = fnum(r.get("capital"))
    puntos = sorted(serie.items())
    inicial = 100.0
    actual = puntos[-1][1] if puntos else fnum(st.get("cash"), inicial)
    # valor "en vivo" con los últimos precios que guardó el bot (si los tiene todos)
    pos_, px_ = st.get("positions") or {}, st.get("prices") or {}
    if st and all(s in px_ for s in pos_):
        actual = fnum(st.get("cash"), inicial) + sum(fnum(p.get("units")) * fnum(px_[s]) for s, p in pos_.items())
        if puntos and abs(actual - puntos[-1][1]) > 0.005 and st.get("actualizado"):
            puntos.append((str(st["actualizado"])[:16].replace("T", " "), round(actual, 2)))
    pico, dd = inicial, 0.0
    for _, v in puntos:
        pico = max(pico, v)
        dd = min(dd, v / pico - 1)
    ganadas = [o for o in ops if fnum(o.get("beneficio")) > 0]
    return dict(
        bot=bot, st=st, puntos=puntos, ops=ops, inicial=inicial, actual=actual,
        rent=actual / inicial - 1, dd=dd, n_ops=len(ops),
        aciertos=(len(ganadas) / len(ops)) if ops else None,
        beneficio=sum(fnum(o.get("beneficio")) for o in ops),
        posiciones=st.get("positions", {}) or {}, precios=st.get("prices", {}) or {},
        inicio=(st.get("start") or "")[:10], ultima=st.get("last_bar") or "—",
        registro=tail(bot["registro"]),
    )


def grafico(r):
    pts = r["puntos"]
    if len(pts) < 2:
        return ('<div class="vacio">Aún no hay suficientes datos para el gráfico. '
                'Aparecerá en cuanto el bot lleve unos días funcionando.</div>')
    W, H, L, R, T, B = 640, 220, 48, 12, 14, 26
    vals = [v for _, v in pts] + [r["inicial"]]
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * 0.1, 1.0)
    lo, hi = lo - pad, hi + pad
    n = len(pts)
    X = lambda i: L + (W - L - R) * i / (n - 1)
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    path = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = path + f" L{X(n - 1):.1f},{H - B} L{X(0):.1f},{H - B} Z"
    ticks = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        ticks += (f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                  f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" class="eje" text-anchor="end">{v:.0f}</text>')
    base = (f'<line x1="{L}" x2="{W - R}" y1="{Y(r["inicial"]):.1f}" y2="{Y(r["inicial"]):.1f}" class="base"/>'
            f'<text x="{W - R}" y="{Y(r["inicial"]) - 5:.1f}" class="eje" text-anchor="end">inicio 100</text>')
    fechas = (f'<text x="{L}" y="{H - 6}" class="eje">{html.escape(pts[0][0][:10])}</text>'
              f'<text x="{W - R}" y="{H - 6}" class="eje" text-anchor="end">{html.escape(pts[-1][0][:10])}</text>')
    data = json.dumps([[f, round(v, 2)] for f, v in pts])
    return f'''<div class="graf" data-pts='{html.escape(data)}' data-l="{L}" data-r="{R}" data-w="{W}" data-m="{html.escape(r['bot'].get('moneda', 'USDT'))}">
<svg viewBox="0 0 {W} {H}" role="img" aria-label="Evolución del capital simulado">
{ticks}{base}<path d="{area}" class="area"/><path d="{path}" class="linea"/>
<circle r="5" class="punto" cx="{X(n - 1):.1f}" cy="{Y(pts[-1][1]):.1f}"/>{fechas}
<line class="cruz" y1="{T}" y2="{H - B}" x1="-10" x2="-10"/></svg><div class="tip"></div></div>'''


def tarjeta(r):
    b = r["bot"]
    color = "pos" if r["rent"] > 0.0001 else ("neg" if r["rent"] < -0.0001 else "neu")
    acierto = pct(r["aciertos"], False) if r["aciertos"] is not None else "—"
    # posiciones abiertas
    if r["posiciones"]:
        filas = ""
        for s, p in r["posiciones"].items():
            ent, stop, uds = fnum(p.get("entry")), fnum(p.get("stop")), fnum(p.get("units"))
            px = fnum(r["precios"].get(s), ent)
            filas += (f"<tr><td><b>{html.escape(s)}</b></td><td>{html.escape(str(p.get('time', '')))}</td>"
                      f"<td>{ent:.6g}</td><td>{px:.6g}</td><td>{f'{stop:.6g}' if stop else '—'}</td>"
                      f"<td>{eur(uds * px)}</td><td class='{'pos' if px >= ent else 'neg'}'>{pct(px / ent - 1)}</td></tr>")
        pos = (f"<div class='tabla'><table><thead><tr><th>{b.get('activo', 'Moneda')}</th><th>Desde</th><th>Entrada</th><th>Precio</th>"
               f"<th>Stop</th><th>Valor</th><th>Resultado</th></tr></thead><tbody>{filas}</tbody></table></div>")
    else:
        pos = '<div class="vacio">Sin posiciones abiertas: todo en liquidez, esperando señal.</div>'
    # operaciones cerradas
    if r["ops"]:
        filas = ""
        for o in reversed(r["ops"][-10:]):
            bf = fnum(o.get("beneficio"))
            filas += (f"<tr><td><b>{html.escape(o.get('simbolo', ''))}</b></td>"
                      f"<td>{html.escape(str(o.get('entrada', ''))[:10])}</td><td>{html.escape(str(o.get('salida', ''))[:10])}</td>"
                      f"<td class='{'pos' if bf > 0 else 'neg'}'>{bf:+.2f}</td><td>{html.escape(o.get('motivo', ''))}</td></tr>")
        ops = (f"<div class='tabla'><table><thead><tr><th>{b.get('activo', 'Moneda')}</th><th>Entrada</th><th>Salida</th><th>Resultado</th>"
               f"<th>Motivo</th></tr></thead><tbody>{filas}</tbody></table></div>")
    else:
        ops = '<div class="vacio">Todavía no ha cerrado ninguna operación.</div>'
    reg = html.escape("\n".join(r["registro"])) or "Sin registro todavía."
    return f'''
<section class="bot">
  <div class="cab"><h2>{html.escape(b["nombre"])}</h2>
    <span class="meta">Funcionando desde {html.escape(r["inicio"] or "—")} · última vela {html.escape(str(r["ultima"]))}</span></div>
  <div class="kpis">
    <div class="kpi grande"><span>Capital simulado</span><b>{eur(r["actual"])} <small>{b.get("moneda", "USDT")}</small></b>
      <em class="{color}">{pct(r["rent"])} desde el inicio</em></div>
    <div class="kpi"><span>Peor caída</span><b>{pct(r["dd"]) if r["dd"] < -0.0005 else "0,0 %"}</b><em>límite esperado {pct(b["dd"])}</em></div>
    <div class="kpi"><span>Operaciones cerradas</span><b>{r["n_ops"]}</b><em>aciertos {acierto}</em></div>
    <div class="kpi"><span>Posiciones abiertas</span><b>{len(r["posiciones"])}</b><em>liquidez {eur(fnum(r["st"].get("cash"), 100))}</em></div>
  </div>
  <p class="esperado">{html.escape(b["esperado"])}</p>
  {grafico(r)}
  <h3>Posiciones abiertas</h3>{pos}
  <h3>Últimas operaciones</h3>{ops}
  <details><summary>Ver últimas líneas del registro</summary><pre>{reg}</pre></details>
</section>'''


CSS = """
:root{--bg:#f4f3f0;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--ink3:#8a8984;--line:#e4e2dc;
--s1:#2a78d6;--s1a:rgba(42,120,214,.12);--pos:#0f7b3f;--neg:#c2361b;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8d8c85;
--line:#2c2b29;--s1:#3987e5;--s1a:rgba(57,135,229,.18);--pos:#3fbf73;--neg:#ff7a5c;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}
header h1{margin:0;font-size:24px}header p{margin:4px 0 0;color:var(--ink2)}
.aviso{margin:16px 0;padding:10px 14px;border-radius:10px;background:#fff4d6;color:#5a4300;border:1px solid #f0d58a}
@media (prefers-color-scheme:dark){.aviso{background:#3a2f0c;color:#f6dc8f;border-color:#6b5617}}
.bot{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-top:20px}
.cab{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline;justify-content:space-between}
.cab h2{margin:0;font-size:19px}.meta{color:var(--ink3);font-size:13px}
.kpis{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:12px;margin:16px 0 8px}
@media (max-width:700px){.kpis{grid-template-columns:1fr 1fr}.kpi.grande{grid-column:1/-1}}
.kpi{border:1px solid var(--line);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:2px}
.kpi span{color:var(--ink2);font-size:13px}.kpi b{font-size:22px;font-variant-numeric:tabular-nums}
.kpi.grande b{font-size:30px}.kpi small{font-size:14px;color:var(--ink2);font-weight:500}
.kpi em{font-style:normal;font-size:13px;color:var(--ink3)}
.pos{color:var(--pos)!important}.neg{color:var(--neg)!important}.neu{color:var(--ink2)}
.esperado{color:var(--ink2);font-size:13px;margin:4px 0 12px}
.graf{position:relative}svg{width:100%;height:auto;display:block}
.grid{stroke:var(--line);stroke-width:1}.base{stroke:var(--ink3);stroke-width:1;stroke-dasharray:4 4}
.eje{fill:var(--ink3);font-size:11px}.linea{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round}
.area{fill:var(--s1a)}.punto{fill:var(--s1);stroke:var(--card);stroke-width:2}
.cruz{stroke:var(--ink3);stroke-width:1}
.tip{position:absolute;pointer-events:none;display:none;background:var(--ink);color:var(--card);padding:4px 8px;border-radius:6px;font-size:12px;white-space:nowrap;transform:translate(-50%,-110%)}
h3{font-size:15px;margin:18px 0 6px}
.tabla{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--ink2);font-weight:600;border-bottom:1px solid var(--line);padding:6px 6px}
td{border-bottom:1px solid var(--line);padding:6px 6px}
.vacio{color:var(--ink3);font-size:13px;padding:10px 12px;border:1px dashed var(--line);border-radius:10px}
details{margin-top:14px}summary{cursor:pointer;color:var(--ink2);font-size:13px}
pre{white-space:pre-wrap;font-size:12px;background:var(--bg);padding:10px;border-radius:8px;color:var(--ink2);max-height:260px;overflow:auto}
footer{margin-top:24px;color:var(--ink3);font-size:12px}
"""

JS = """
document.querySelectorAll('.graf').forEach(function(g){
  var pts=JSON.parse(g.dataset.pts),L=+g.dataset.l,R=+g.dataset.r,W=+g.dataset.w,svg=g.querySelector('svg'),
      tip=g.querySelector('.tip'),cruz=g.querySelector('.cruz');
  svg.addEventListener('mousemove',function(e){
    var b=svg.getBoundingClientRect(),x=(e.clientX-b.left)*W/b.width,
        i=Math.round((x-L)/(W-L-R)*(pts.length-1));i=Math.max(0,Math.min(pts.length-1,i));
    var px=L+(W-L-R)*i/Math.max(1,pts.length-1);
    cruz.setAttribute('x1',px);cruz.setAttribute('x2',px);
    tip.style.display='block';tip.style.left=(px*b.width/W)+'px';tip.style.top=(e.clientY-b.top)+'px';
    tip.textContent=pts[i][0]+' · '+pts[i][1].toFixed(2).replace('.',',')+' '+(g.dataset.m||'USDT');
  });
  svg.addEventListener('mouseleave',function(){tip.style.display='none';cruz.setAttribute('x1',-10);cruz.setAttribute('x2',-10);});
});
"""


def main():
    rs = [resumen(b) for b in BOTS]
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    # aviso si los bots llevan tiempo sin ejecutarse bien
    avisos = []
    for r in rs:
        try:
            ult = datetime.fromisoformat(r["st"]["actualizado"])
        except Exception:
            continue
        horas = (ahora - ult).total_seconds() / 3600
        if horas > 8:
            avisos.append(f"{r['bot']['nombre']} no se actualiza desde hace {horas:.0f} horas. "
                          "Puede ser un fallo puntual al descargar precios; si dura más de un día, avisa a Claude.")
    total = sum(r["actual"] for r in rs)
    aviso = "".join(f'<div class="aviso">⚠ {html.escape(a)}</div>' for a in avisos)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel de los bots</title><meta http-equiv="refresh" content="120">
<style>{CSS}</style></head><body><main>
<header><h1>Panel de los bots de trading</h1>
<p>Dinero simulado, no real. <b>Cartera combinada</b> (los {len(rs)} bots juntos, la opción más estable en el backtest): <b>{eur(total)}</b> de {100 * len(rs)} iniciales
({pct(total / (100 * len(rs)) - 1)}), sumando USDT y euros como si fueran lo mismo. Actualizado el {ahora.strftime('%d/%m/%Y a las %H:%M')}.</p></header>
{aviso}{''.join(tarjeta(r) for r in rs)}
<footer>Los bots funcionan solos en la nube (GitHub) y este panel se actualiza cada hora (cada ~10 minutos con la bolsa abierta) y se recarga solo cada 2 minutos.
Revisión prevista hacia febrero de 2027: si los resultados se parecen al backtest, hablamos de dinero real.</footer>
</main><script>{JS}</script></body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Panel actualizado: {OUT}")


if __name__ == "__main__":
    main()
