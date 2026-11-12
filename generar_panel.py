"""
Genera panel.html: el panel profesional de los bots de paper trading.

Lee lo que dejan los bots en esta carpeta (estado_*.json, capital_*.csv, operaciones_*.csv, registro_*.txt)
y escribe panel.html, una página autónoma (no necesita internet) con:
  - la cartera combinada (suma de todos los bots) y su evolución,
  - la tabla "real vs esperado" de cada bot frente a su backtest,
  - una ficha por bot con posiciones, operaciones y registro.

Uso:  python generar_panel.py
"""
from __future__ import annotations
import csv, html, json, os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "panel.html")
MADRID = ZoneInfo("Europe/Madrid")

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
    dict(id="oro", nombre="Bot oro 4h · Buy Sell Signal (€)", estado="estado_bot_oro.json",
         capital="capital_oro.csv", ops="operaciones_oro.csv", registro="registro_bot_oro.txt",
         esperado="Tu indicador de TradingView (EMA 5/13, SL 0,5 ATR, TP 1:1, 2:1 y 3:1), compras y cortos, "
                  "arriesgando un 1 % por operación. Backtest jun 2024–nov 2026: +40 % en total, peor caída −7 %, "
                  "unas 7 operaciones al mes. Pocos datos y con el oro muy alcista: hay que confirmarlo.",
         ret_anual=0.15, dd=-0.10, moneda="€", activo="Activo"),
    dict(id="rebotes", nombre="Bot rebotes en índices · RSI 2 (€)", estado="estado_bot_rebotes.json",
         capital="capital_rebotes.csv", ops="operaciones_rebotes.csv", registro="registro_bot_rebotes.txt",
         esperado="Compra caídas fuertes de 2-3 días en 9 índices (S&P 500, Nasdaq, IBEX, Euro Stoxx, oro...) "
                  "que siguen en tendencia alcista y vende en el rebote. Backtest 2010–2026: ~70 % de aciertos, "
                  "+6 a +7 % al año, peor caída −14 %, unas 3–4 operaciones al mes.",
         ret_anual=0.065, dd=-0.15, moneda="€", activo="Índice"),
    dict(id="loco", nombre="Experimento · BTC 5 minutos", estado="estado_bot_loco.json",
         capital="capital_loco.csv", ops="operaciones_loco.csv", registro="registro_bot_loco.txt",
         esperado="EXPERIMENTO: el Buy Sell Signal en velas de 5 minutos de Bitcoin, con la comisión real de Binance "
                  "(0,1 %). Unas 15–25 operaciones al día. En el backtest del oro a 5 minutos perdía casi todo en "
                  "2 meses. No cuenta en la cartera combinada: es para ver en directo qué pasa al operar tanto.",
         ret_anual=-0.90, dd=-0.95, experimento=True, activo="Activo"),
    dict(id="ia", nombre="Agente IA · TradingAgents (€)", estado="estado_bot_ia.json",
         capital="capital_ia.csv", ops="operaciones_ia.csv", registro="registro_bot_ia.txt",
         esperado="EXPERIMENTO: un equipo de IAs (Gemini) lee gráficos, noticias y redes cada lunes y da una nota "
                  "a Bitcoin, S&P 500 y oro; si es Buy u Overweight compra 1/3 del capital, si es Underweight o Sell "
                  "vende. SIN BACKTEST posible (la IA recuerda el pasado): solo vale lo que haga de hoy en adelante. "
                  "No cuenta en la cartera combinada hasta tener unos meses de resultados.",
         ret_anual=0.0, dd=-0.30, experimento=True, moneda="€", activo="Activo"),
]


CORTO = {"diario": ("12 criptos", "Cripto · diario"), "4h": ("BTC 4h", "Cripto · 4 horas"),
         "acciones": ("Acciones €", "Bolsa · mensual"), "etf": ("ETF 12 mercados", "Multiactivo · mensual"),
         "oro": ("Oro 4h", "Materias primas · 4 horas"),
         "rebotes": ("Rebotes índices", "Índices · RSI 2 diario"),
         "loco": ("Experimento 5 min", "BTC · 5 minutos · no cuenta"),
         "ia": ("Agente IA", "BTC, S&P 500, oro · semanal · no cuenta")}
INICIAL = 100.0


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


def tail(name, n=14):
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


def pct(x, signo=True, dec=1):
    x = round(x * 100, dec) / 100 or 0.0
    s = f"{x * 100:+.{dec}f} %" if signo else f"{x * 100:.{dec}f} %"
    return s.replace(".", ",").replace("-", "−")


def num(x):
    """Precio legible: 40.430 / 1.365,2 / 29,71 / 0,1735"""
    a = abs(x)
    dec = 0 if a >= 10000 else 1 if a >= 1000 else 2 if a >= 1 else 4
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def esc(x):
    return html.escape(str(x))


def fecha_iso(s):
    """Convierte cualquier fecha de los CSV/JSON a datetime con zona (UTC si no trae)."""
    try:
        d = datetime.fromisoformat(str(s).strip().replace("T", " "))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def resumen(bot, ahora):
    st = read_json(bot["estado"]) or {}
    cap = read_csv(bot["capital"])
    ops = read_csv(bot["ops"])
    serie = {}
    for r in cap:
        d = fecha_iso(r.get("fecha", ""))
        if d:
            serie[d] = fnum(r.get("capital"), INICIAL)
    puntos = sorted(serie.items())
    actual = puntos[-1][1] if puntos else fnum(st.get("cash"), INICIAL)
    pos_, px_ = st.get("positions") or {}, st.get("prices") or {}
    if st and all(s in px_ for s in pos_):
        actual = fnum(st.get("cash"), INICIAL) + sum(fnum(p.get("units")) * fnum(px_[s]) for s, p in pos_.items())
        upd = fecha_iso(st.get("actualizado", ""))
        if upd and (not puntos or upd > puntos[-1][0]) and (not puntos or abs(actual - puntos[-1][1]) > 0.004):
            puntos.append((upd, round(actual, 2)))
    inicio = fecha_iso(st.get("start", "")) or (puntos[0][0] if puntos else ahora)
    if not puntos or puntos[0][0] > inicio:
        puntos.insert(0, (inicio, INICIAL))
    pico, dd = INICIAL, 0.0
    for _, v in puntos:
        pico = max(pico, v)
        dd = min(dd, v / pico - 1)
    dias = max((ahora - inicio).total_seconds() / 86400, 0.0)
    esperado = (1 + bot["ret_anual"]) ** (dias / 365.25) - 1
    rent = actual / INICIAL - 1
    ganadas = [o for o in ops if fnum(o.get("beneficio")) > 0]
    upd = fecha_iso(st.get("actualizado", ""))
    return dict(bot=bot, st=st, puntos=puntos, ops=ops, actual=actual, rent=rent, dd=dd, dias=dias,
                esperado=esperado, n_ops=len(ops), aciertos=(len(ganadas) / len(ops)) if ops else None,
                posiciones=pos_, precios=px_, inicio=inicio, ultima=st.get("last_bar") or "—",
                actualizado=upd, registro=tail(bot["registro"]))


def estado(r):
    """Semáforo frente al backtest: (clase, icono, texto, explicación)."""
    b = r["bot"]
    if b.get("experimento"):
        return ("neutro", "⚗", "Experimento", "No cuenta en la cartera combinada")
    if r["dd"] < b["dd"] * 1.15:
        return ("crit", "▲", "Revisar", "La caída supera la peor del backtest")
    if r["dias"] < 30:
        return ("neutro", "●", "Muy pronto", "Menos de 30 días: aún no se puede juzgar")
    dif = r["rent"] - r["esperado"]
    margen = 0.5 * abs(b["dd"]) * min(1.0, (r["dias"] / 365.25) ** 0.5) + 0.02
    if dif >= -margen:
        return ("ok", "✓", "En línea", "Dentro de lo normal según el backtest")
    return ("warn", "!", "Por debajo", "Va peor de lo esperado, vigilar")


def tabla_real_vs(rs):
    filas = ""
    for i, r in enumerate(rs):
        b = r["bot"]
        corto, mercado = CORTO.get(b["id"], (b["nombre"], ""))
        cls, ico, txt, expl = estado(r)
        dif = r["rent"] - r["esperado"]
        uso = (r["dd"] / b["dd"]) if b["dd"] else 0
        filas += f"""<tr>
  <td><span class="sw s{i + 1}"></span><b>{esc(corto)}</b><small>{esc(mercado)}</small></td>
  <td class="num">{r["dias"]:.0f}</td>
  <td class="num {'pos' if r['rent'] > 0.0005 else 'neg' if r['rent'] < -0.0005 else ''}">{pct(r["rent"])}</td>
  <td class="num">{pct(r["esperado"])}<small>{pct(b["ret_anual"], False, 0)}/año</small></td>
  <td class="num {'pos' if dif > 0.0005 else 'neg' if dif < -0.0005 else ''}">{pct(dif)}</td>
  <td class="num">{pct(r["dd"]) if r["dd"] < -0.0005 else "0,0 %"}<small>límite {pct(b["dd"], True, 0)}</small>
    <span class="barra" title="{uso * 100:.0f} % del límite"><i style="width:{min(uso, 1) * 100:.0f}%"></i></span></td>
  <td class="num">{r["n_ops"]}<small>{'aciertos ' + pct(r["aciertos"], False, 0) if r["aciertos"] is not None else 'sin cerrar'}</small></td>
  <td><span class="badge {cls}" title="{esc(expl)}"><span aria-hidden="true">{ico}</span> {esc(txt)}</span></td>
</tr>"""
    return f"""<div class="tabla"><table class="rve">
<thead><tr><th>Bot</th><th class="num">Días</th><th class="num">Real</th><th class="num">Esperado</th>
<th class="num">Diferencia</th><th class="num">Peor caída</th><th class="num">Operaciones</th><th>Estado</th></tr></thead>
<tbody>{filas}</tbody></table></div>
<p class="nota">“Esperado” es lo que habría ganado el bot en estos días si rindiera exactamente como en su backtest.
En pocas semanas es normal desviarse mucho: el semáforo tiene en cuenta el tiempo transcurrido y la caída máxima histórica.</p>"""


def serie_json(puntos):
    return [[d.astimezone(MADRID).strftime("%Y-%m-%d %H:%M"), round(v, 2)] for d, v in puntos]


def combinada(rs):
    """Cartera combinada: suma de todos los bots, cada uno valorado con su último dato conocido."""
    eventos = sorted({d for r in rs for d, _ in r["puntos"]})
    out = []
    for t in eventos:
        tot = 0.0
        for r in rs:
            v = INICIAL
            for d, x in r["puntos"]:
                if d <= t:
                    v = x
                else:
                    break
            tot += v
        out.append((t, tot))
    # un punto por hora como mucho (el último de cada hora)
    porhora = {}
    for t, v in out:
        porhora[t.strftime("%Y-%m-%d %H")] = (t, v)
    return sorted(porhora.values())


def ficha(i, r):
    b = r["bot"]
    corto, mercado = CORTO.get(b["id"], (b["nombre"], ""))
    mon = b.get("moneda", "USDT")
    cls, ico, txt, _ = estado(r)
    act = b.get("activo", "Moneda")
    if r["posiciones"]:
        filas = ""
        for s, p in r["posiciones"].items():
            ent, stop, uds = fnum(p.get("entry")), fnum(p.get("stop")), fnum(p.get("units"))
            px = fnum(r["precios"].get(s), ent)
            res = (px / ent - 1) * (1 if uds >= 0 else -1) if ent else 0
            filas += (f"<tr><td><b>{esc(s)}</b>{' <small>corto</small>' if uds < 0 else ''}</td>"
                      f"<td>{esc(str(p.get('time', ''))[:16])}</td><td class='num'>{num(ent)}</td><td class='num'>{num(px)}</td>"
                      f"<td class='num'>{num(stop) if stop else '—'}</td><td class='num'>{eur(abs(uds * px))}</td>"
                      f"<td class='num {'pos' if res >= 0 else 'neg'}'>{pct(res)}</td></tr>")
        pos = (f"<div class='tabla'><table><thead><tr><th>{esc(act)}</th><th>Desde</th><th class='num'>Entrada</th>"
               f"<th class='num'>Precio</th><th class='num'>Stop</th><th class='num'>Valor</th><th class='num'>Resultado</th>"
               f"</tr></thead><tbody>{filas}</tbody></table></div>")
    else:
        pos = '<div class="vacio">Sin posiciones abiertas: en liquidez, esperando señal.</div>'
    if r["ops"]:
        filas = ""
        for o in reversed(r["ops"][-12:]):
            bf = fnum(o.get("beneficio"))
            filas += (f"<tr><td><b>{esc(o.get('simbolo', ''))}</b></td><td>{esc(str(o.get('entrada', ''))[:16])}</td>"
                      f"<td>{esc(str(o.get('salida', ''))[:16])}</td><td class='num {'pos' if bf > 0 else 'neg'}'>{bf:+.2f}</td>"
                      f"<td>{esc(o.get('motivo', ''))}</td></tr>")
        ops = (f"<div class='tabla'><table><thead><tr><th>{esc(act)}</th><th>Entrada</th><th>Salida</th>"
               f"<th class='num'>Resultado</th><th>Motivo</th></tr></thead><tbody>{filas}</tbody></table></div>")
    else:
        ops = '<div class="vacio">Todavía no ha cerrado ninguna operación.</div>'
    reg = esc("\n".join(r["registro"])) or "Sin registro todavía."
    color = "pos" if r["rent"] > 0.0005 else ("neg" if r["rent"] < -0.0005 else "")
    datos = esc(json.dumps(serie_json(r["puntos"])))
    return f"""
<details class="bot" id="bot-{esc(b['id'])}">
<summary>
  <span class="sw s{i + 1}"></span>
  <span class="tit"><b>{esc(corto)}</b><small>{esc(mercado)}</small></span>
  <span class="spark" data-pts="{datos}" data-s="{i + 1}" aria-hidden="true"></span>
  <span class="val"><b>{eur(r["actual"])} <small>{esc(mon)}</small></b><em class="{color}">{pct(r["rent"])}</em></span>
  <span class="badge {cls}"><span aria-hidden="true">{ico}</span> {esc(txt)}</span>
  <span class="chev" aria-hidden="true"></span>
</summary>
<div class="cuerpo">
  <p class="desc">{esc(b["esperado"])}</p>
  <div class="kpis">
    <div class="kpi"><span>Capital</span><b>{eur(r["actual"])} <small>{esc(mon)}</small></b><em class="{color}">{pct(r["rent"])} desde el inicio</em></div>
    <div class="kpi"><span>Peor caída</span><b>{pct(r["dd"]) if r["dd"] < -0.0005 else "0,0 %"}</b><em>límite backtest {pct(b["dd"], True, 0)}</em></div>
    <div class="kpi"><span>Operaciones cerradas</span><b>{r["n_ops"]}</b><em>aciertos {pct(r["aciertos"], False, 0) if r["aciertos"] is not None else "—"}</em></div>
    <div class="kpi"><span>Posiciones abiertas</span><b>{len(r["posiciones"])}</b><em>liquidez {eur(fnum(r["st"].get("cash"), INICIAL))}</em></div>
  </div>
  <div class="graf" data-pts="{datos}" data-s="{i + 1}" data-m="{esc(mon)}" role="img"
       aria-label="Evolución del capital de {esc(corto)}"></div>
  <h3>Posiciones abiertas</h3>{pos}
  <h3>Últimas operaciones</h3>{ops}
  <details class="log"><summary>Registro del bot · funcionando desde {esc(r["inicio"].astimezone(MADRID).strftime("%d/%m/%Y"))}
    · última vela {esc(r["ultima"])}</summary><pre>{reg}</pre></details>
</div>
</details>"""


CSS = """
:root{color-scheme:light;
--bg:#f4f3f0;--card:#fcfcfb;--card2:#f7f6f3;--ink:#0b0b0b;--ink2:#52514e;--ink3:#7d7c77;--line:#e4e2dc;--line2:#efede8;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#9a5b13;--tot:#0b0b0b;
--pos:#0f7b3f;--neg:#c2361b;--ok-bg:#e3f4ea;--ok:#0f6b37;--warn-bg:#fff1d6;--warn:#7a5200;--crit-bg:#fde6e1;--crit:#a52a12;
--neu-bg:#ecebe7;--neu:#52514e;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--bg:#0f0f0e;--card:#1a1a19;--card2:#151514;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8d8c85;--line:#2c2b29;--line2:#232321;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#d08a3c;--tot:#f0efec;
--pos:#3fbf73;--neg:#ff7a5c;--ok-bg:#12301f;--ok:#6fd99a;--warn-bg:#33270a;--warn:#f2c661;--crit-bg:#3a1710;--crit:#ff9b82;
--neu-bg:#262624;--neu:#c3c2b7;--accent:#3987e5}}
:root[data-theme="dark"]{color-scheme:dark;
--bg:#0f0f0e;--card:#1a1a19;--card2:#151514;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8d8c85;--line:#2c2b29;--line2:#232321;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#d08a3c;--tot:#f0efec;
--pos:#3fbf73;--neg:#ff7a5c;--ok-bg:#12301f;--ok:#6fd99a;--warn-bg:#33270a;--warn:#f2c661;--crit-bg:#3a1710;--crit:#ff9b82;
--neu-bg:#262624;--neu:#c3c2b7;--accent:#3987e5}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1120px;margin:0 auto;padding:20px 16px 56px}
.num,.kpi b,.hero b,td.num{font-variant-numeric:tabular-nums}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.marca{display:flex;align-items:center;gap:10px}
.logo{width:34px;height:34px;border-radius:9px;background:var(--ink);display:grid;place-items:center}
.logo svg{width:20px;height:20px}
.marca h1{margin:0;font-size:18px;letter-spacing:-.01em}.marca p{margin:0;color:var(--ink3);font-size:12px}
.chips{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--card);border-radius:999px;padding:4px 10px;font-size:12px;color:var(--ink2)}
.vivo{width:8px;height:8px;border-radius:50%;background:var(--pos);box-shadow:0 0 0 3px color-mix(in srgb,var(--pos) 25%,transparent)}
button.chip{cursor:pointer;font:inherit;font-size:12px}
.aviso{margin:0 0 16px;padding:10px 14px;border-radius:10px;background:var(--warn-bg);color:var(--warn);border:1px solid color-mix(in srgb,var(--warn) 35%,transparent)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}
.hero{display:grid;grid-template-columns:minmax(240px,1fr) 2.2fr;gap:24px}
@media (max-width:820px){.hero{grid-template-columns:1fr}}
.hero .lab{color:var(--ink2);font-size:13px;display:flex;align-items:center;gap:6px}
.hero .grande{font-size:40px;font-weight:650;letter-spacing:-.02em;line-height:1.1;margin:6px 0 2px}
.hero .grande small{font-size:16px;color:var(--ink2);font-weight:500}
.delta{display:inline-flex;gap:6px;align-items:center;font-weight:600;font-size:14px}
.mini{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}
.mini div{background:var(--card2);border:1px solid var(--line2);border-radius:10px;padding:8px 10px}
.mini span{display:block;color:var(--ink3);font-size:12px}.mini b{font-size:17px}
.leyenda{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0 0 8px;font-size:12px;color:var(--ink2)}
.leyenda button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:6px;padding:2px 4px;border-radius:6px}
.leyenda button[aria-pressed="false"]{opacity:.4}
.leyenda button:focus-visible{outline:2px solid var(--accent)}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px;flex:none;vertical-align:middle;margin-right:8px}
.sw.s1{background:var(--s1)}.sw.s2{background:var(--s2)}.sw.s3{background:var(--s3)}.sw.s4{background:var(--s4)}.sw.s5{background:var(--s5)}.sw.s6{background:var(--s6)}.sw.s7{background:var(--s7)}.sw.s8{background:var(--s8)}
.sw.tot{background:var(--tot);height:3px;width:14px;border-radius:2px}
.leyenda .sw{margin:0}
h2{font-size:15px;margin:28px 0 10px;display:flex;align-items:baseline;justify-content:space-between;gap:8px}
h2 small{font-weight:400;color:var(--ink3);font-size:12px}
.tabla{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--ink3);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line);padding:8px 10px;white-space:nowrap}
td{border-bottom:1px solid var(--line2);padding:10px;vertical-align:middle}
tbody tr:last-child td{border-bottom:0}
th.num,td.num{text-align:right;white-space:nowrap}
td small{display:block;color:var(--ink3);font-size:11px;font-weight:400}
td b+small{display:block}
.rve td:first-child{white-space:nowrap}.rve td:first-child small{margin-left:18px}
.barra{display:block;height:4px;border-radius:2px;background:var(--line);margin-top:4px;margin-left:auto;width:72px;overflow:hidden}
.barra i{display:block;height:100%;background:var(--ink3);border-radius:2px}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}
.badge.crit{background:var(--crit-bg);color:var(--crit)}.badge.neutro{background:var(--neu-bg);color:var(--neu)}
.nota{color:var(--ink3);font-size:12px;margin:10px 2px 0}
.pos{color:var(--pos)!important}.neg{color:var(--neg)!important}
details.bot{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-top:10px;overflow:hidden}
details.bot>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:auto minmax(120px,1.2fr) minmax(80px,1fr) auto auto 18px;
  gap:14px;align-items:center;padding:14px 16px}
details.bot>summary::-webkit-details-marker{display:none}
details.bot>summary:hover{background:var(--card2)}
details.bot>summary:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.tit b{display:block;font-size:14px}.tit small{color:var(--ink3);font-size:12px}
.spark svg{width:100%;height:32px;display:block}
.val{text-align:right}.val b{display:block;font-size:15px}.val small{font-size:11px;color:var(--ink3);font-weight:500}.val em{font-style:normal;font-size:12px;font-weight:600}
.chev{width:8px;height:8px;border-right:2px solid var(--ink3);border-bottom:2px solid var(--ink3);transform:rotate(45deg);justify-self:center;transition:transform .15s}
details.bot[open] .chev{transform:rotate(-135deg)}
@media (max-width:700px){details.bot>summary{grid-template-columns:auto 1fr auto 18px}.spark,details.bot>summary .badge{display:none}}
.cuerpo{border-top:1px solid var(--line);padding:16px}
.desc{color:var(--ink2);font-size:13px;margin:0 0 14px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
@media (max-width:700px){.kpis{grid-template-columns:1fr 1fr}}
.kpi{background:var(--card2);border:1px solid var(--line2);border-radius:10px;padding:10px 12px}
.kpi span{display:block;color:var(--ink3);font-size:12px}.kpi b{font-size:19px}.kpi b small{font-size:12px;color:var(--ink3);font-weight:500}
.kpi em{display:block;font-style:normal;font-size:12px;color:var(--ink3)}
h3{font-size:13px;margin:18px 0 6px;color:var(--ink2)}
.vacio{color:var(--ink3);font-size:13px;padding:12px;border:1px dashed var(--line);border-radius:10px}
details.log{margin-top:14px}details.log summary{cursor:pointer;color:var(--ink3);font-size:12px}
pre{white-space:pre-wrap;font:12px/1.5 ui-monospace,Consolas,monospace;background:var(--card2);padding:12px;border-radius:8px;color:var(--ink2);max-height:280px;overflow:auto;margin:8px 0 0}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.grid line{stroke:var(--line2);stroke-width:1}.cero{stroke:var(--ink3);stroke-width:1;stroke-dasharray:3 4}
.eje{fill:var(--ink3);font-size:11px}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ln.tot{stroke:var(--tot);stroke-width:2.5}
.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}.ln.s3{stroke:var(--s3)}.ln.s4{stroke:var(--s4)}.ln.s5{stroke:var(--s5)}.ln.s6{stroke:var(--s6)}.ln.s7{stroke:var(--s7)}.ln.s8{stroke:var(--s8)}
.ar{opacity:.12}.ar.s1{fill:var(--s1)}.ar.s2{fill:var(--s2)}.ar.s3{fill:var(--s3)}.ar.s4{fill:var(--s4)}.ar.s5{fill:var(--s5)}.ar.s6{fill:var(--s6)}.ar.s7{fill:var(--s7)}.ar.s8{fill:var(--s8)}
.dot{stroke:var(--card);stroke-width:2}
.dot.tot{fill:var(--tot)}.dot.s1{fill:var(--s1)}.dot.s2{fill:var(--s2)}.dot.s3{fill:var(--s3)}.dot.s4{fill:var(--s4)}.dot.s5{fill:var(--s5)}.dot.s6{fill:var(--s6)}.dot.s7{fill:var(--s7)}.dot.s8{fill:var(--s8)}
.cruz{stroke:var(--ink3);stroke-width:1}
.tip{position:absolute;pointer-events:none;display:none;background:var(--card);color:var(--ink);border:1px solid var(--line);
  box-shadow:0 6px 20px rgba(0,0,0,.12);padding:8px 10px;border-radius:8px;font-size:12px;min-width:150px;z-index:2}
.tip .f{color:var(--ink3);margin-bottom:4px}.tip .r{white-space:nowrap;display:flex;justify-content:space-between;gap:12px;font-variant-numeric:tabular-nums}
.tip .r span{display:inline-flex;align-items:center;gap:6px;color:var(--ink2)}
.vacio-graf{color:var(--ink3);font-size:13px;padding:30px 12px;text-align:center;border:1px dashed var(--line);border-radius:10px}
footer{margin-top:28px;color:var(--ink3);font-size:12px;line-height:1.6}
"""

JS = r"""
(function(){
var NS='http://www.w3.org/2000/svg';
function el(t,a,p){var e=document.createElementNS(NS,t);for(var k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e;}
function fmtP(v){return (v>=0?'+':'−')+Math.abs(v).toFixed(1).replace('.',',')+' %';}
function fmtE(v){return v.toFixed(2).replace('.',',');}
function fecha(s){return new Date(s.replace(' ','T'));}
function fechaCorta(d){return d.toLocaleDateString('es-ES',{day:'2-digit',month:'short'});}
/* ---- gráfico multiserie en % (una sola escala) ---- */
function multi(box,series,opt){
  box.innerHTML='';
  var vis=series.filter(function(s){return !s.off&&s.pts.length>0;});
  var all=[];vis.forEach(function(s){s.pts.forEach(function(p){all.push(p);});});
  if(all.length<2){box.innerHTML='<div class="vacio-graf">El gráfico aparecerá cuando los bots lleven unas horas funcionando.</div>';return;}
  var W=box.clientWidth||700,H=opt.h||260,L=46,R=12,T=12,B=26;
  var t0=Math.min.apply(null,all.map(function(p){return p.t;})),t1=Math.max.apply(null,all.map(function(p){return p.t;}));
  if(t1===t0)t1=t0+3600e3;
  var lo=Math.min(0,Math.min.apply(null,all.map(function(p){return p.v;}))),hi=Math.max(0,Math.max.apply(null,all.map(function(p){return p.v;})));
  var pad=Math.max((hi-lo)*.12,.5);lo-=pad;hi+=pad;
  var X=function(t){return L+(W-L-R)*(t-t0)/(t1-t0);},Y=function(v){return T+(H-T-B)*(1-(v-lo)/(hi-lo));};
  var svg=el('svg',{viewBox:'0 0 '+W+' '+H,width:W,height:H},box);
  var g=el('g',{'class':'grid'},svg);
  for(var k=0;k<=4;k++){var v=lo+(hi-lo)*k/4;el('line',{x1:L,x2:W-R,y1:Y(v),y2:Y(v)},g);
    var tx=el('text',{x:L-8,y:Y(v)+4,'class':'eje','text-anchor':'end'},svg);var dd=Math.abs(hi-lo)<4?1:0,av=Math.abs(v).toFixed(dd);tx.textContent=parseFloat(av)===0?'0%':(v>=0?'+':'−')+av.replace('.',',')+'%';}
  el('line',{x1:L,x2:W-R,y1:Y(0),y2:Y(0),'class':'cero'},svg);
  var nt=Math.min(5,Math.max(2,Math.floor((W-L-R)/120)));
  for(k=0;k<nt;k++){var tt=t0+(t1-t0)*k/(nt-1);var e2=el('text',{x:X(tt),y:H-6,'class':'eje','text-anchor':k===0?'start':(k===nt-1?'end':'middle')},svg);e2.textContent=fechaCorta(new Date(tt));}
  vis.forEach(function(s){
    var d=s.pts.map(function(p,i){return (i?'L':'M')+X(p.t).toFixed(1)+','+Y(p.v).toFixed(1);}).join('');
    if(opt.area&&s.cls!=='tot'){el('path',{d:d+'L'+X(s.pts[s.pts.length-1].t)+','+Y(lo)+'L'+X(s.pts[0].t)+','+Y(lo)+'Z','class':'ar '+s.cls},svg);}
    el('path',{d:d,'class':'ln '+s.cls},svg);
    var lp=s.pts[s.pts.length-1];el('circle',{cx:X(lp.t),cy:Y(lp.v),r:4,'class':'dot '+s.cls},svg);
  });
  var cruz=el('line',{x1:-10,x2:-10,y1:T,y2:H-B,'class':'cruz',visibility:'hidden'},svg);
  var marks=vis.map(function(s){var c=el('circle',{r:4,cx:-20,cy:-20,'class':'dot '+s.cls,visibility:'hidden'},svg);return c;});
  var tip=document.createElement('div');tip.className='tip';box.appendChild(tip);
  function near(s,t){var b=null;for(var i=0;i<s.pts.length;i++){if(s.pts[i].t<=t)b=s.pts[i];else break;}return b;}
  svg.addEventListener('pointermove',function(ev){
    var r=svg.getBoundingClientRect(),x=(ev.clientX-r.left)*W/r.width;x=Math.max(L,Math.min(W-R,x));
    var t=t0+(x-L)/(W-L-R)*(t1-t0);cruz.setAttribute('x1',x);cruz.setAttribute('x2',x);cruz.setAttribute('visibility','visible');
    var h='<div class="f">'+new Date(t).toLocaleString('es-ES',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})+'</div>';
    vis.forEach(function(s,i){var p=near(s,t);if(!p){marks[i].setAttribute('visibility','hidden');return;}marks[i].setAttribute('visibility','visible');
      marks[i].setAttribute('cx',X(p.t));marks[i].setAttribute('cy',Y(p.v));
      h+='<div class="r"><span><i class="sw '+s.cls+'" style="margin:0"></i>'+s.name+'</span><b>'+(opt.eur?fmtE(p.e)+' '+opt.m:fmtP(p.v))+'</b></div>';});
    tip.innerHTML=h;tip.style.display='block';
    var px=x*r.width/W;tip.style.left=Math.min(px+12,r.width-170)+'px';tip.style.top='8px';
  });
  svg.addEventListener('pointerleave',function(){tip.style.display='none';cruz.setAttribute('visibility','hidden');marks.forEach(function(m){m.setAttribute('visibility','hidden');});});
}
function conv(pts){return pts.map(function(p){return {t:fecha(p[0]).getTime(),v:(p[1]/100-1)*100,e:p[1]};});}
/* gráfico principal */
var D=JSON.parse(document.getElementById('datos').textContent);
var main=document.getElementById('graf-main');
var series=[{name:'Cartera combinada',cls:'tot',pts:D.total.map(function(p){return {t:fecha(p[0]).getTime(),v:(p[1]/D.inicial-1)*100};})}]
  .concat(D.bots.map(function(b,i){return {name:b.n,cls:'s'+(i+1),pts:conv(b.p)};}));
function draw(){multi(main,series,{h:280});}
document.querySelectorAll('.leyenda button').forEach(function(btn,i){btn.addEventListener('click',function(){
  series[i].off=!series[i].off;btn.setAttribute('aria-pressed',series[i].off?'false':'true');draw();});});
/* mini y fichas */
function spark(box){var pts=conv(JSON.parse(box.dataset.pts));if(pts.length<2)return;var W=160,H=32;
  var lo=Math.min.apply(null,pts.map(function(p){return p.v;})),hi=Math.max.apply(null,pts.map(function(p){return p.v;}));if(hi-lo<.2){hi+=.1;lo-=.1;}
  var t0=pts[0].t,t1=pts[pts.length-1].t||t0+1;var svg=el('svg',{viewBox:'0 0 '+W+' '+H,preserveAspectRatio:'none'},box);
  el('path',{d:pts.map(function(p,i){return (i?'L':'M')+(2+(W-4)*(p.t-t0)/Math.max(1,t1-t0)).toFixed(1)+','+(3+(H-6)*(1-(p.v-lo)/(hi-lo))).toFixed(1);}).join(''),'class':'ln s'+box.dataset.s,'vector-effect':'non-scaling-stroke'},svg);}
document.querySelectorAll('.spark').forEach(spark);
function ficha(box){multi(box,[{name:'Capital',cls:'s'+box.dataset.s,pts:conv(JSON.parse(box.dataset.pts))}],{h:200,area:true,eur:true,m:box.dataset.m});}
document.querySelectorAll('details.bot').forEach(function(d){d.addEventListener('toggle',function(){if(d.open){var g=d.querySelector('.graf');ficha(g);}});});
/* recordar lo que tenías abierto entre recargas */
var KEY='panel-vista';
function guardar(){try{sessionStorage.setItem(KEY,JSON.stringify({
  open:[].map.call(document.querySelectorAll('details.bot[open]'),function(d){return d.id;}),
  logs:[].map.call(document.querySelectorAll('details.bot details.log[open]'),function(d){return d.closest('details.bot').id;}),
  off:series.map(function(s){return !!s.off;}),y:window.scrollY}));}catch(e){}}
try{var v=JSON.parse(sessionStorage.getItem(KEY)||'null');
  if(v){(v.off||[]).forEach(function(o,i){if(o&&series[i]){series[i].off=true;var bt=document.querySelectorAll('.leyenda button')[i];if(bt)bt.setAttribute('aria-pressed','false');}});
    (v.open||[]).forEach(function(id){var d=document.getElementById(id);if(d){d.open=true;ficha(d.querySelector('.graf'));}});
    (v.logs||[]).forEach(function(id){var d=document.getElementById(id);if(d){var l=d.querySelector('details.log');if(l)l.open=true;}});
    if(v.y)requestAnimationFrame(function(){window.scrollTo(0,v.y);});}}catch(e){}
document.addEventListener('toggle',guardar,true);
document.querySelectorAll('.leyenda button').forEach(function(b){b.addEventListener('click',guardar);});
window.addEventListener('scroll',function(){clearTimeout(window._sg);window._sg=setTimeout(guardar,200);});
/* recarga automática cada 2 minutos, guardando antes la vista (y sin recargar si estás mirando el gráfico) */
setInterval(function(){if(document.querySelector('.tip[style*="block"]'))return;guardar();location.reload();},120000);
draw();
var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(function(){draw();document.querySelectorAll('details.bot[open] .graf').forEach(ficha);},150);});
/* tema */
var tb=document.getElementById('tema');
function setT(t){try{localStorage.setItem('tema',t);}catch(e){}if(t==='auto')document.documentElement.removeAttribute('data-theme');else document.documentElement.setAttribute('data-theme',t);
  tb.textContent=t==='dark'?'Tema: oscuro':t==='light'?'Tema: claro':'Tema: automático';}
var cur='auto';try{cur=localStorage.getItem('tema')||'auto';}catch(e){}setT(cur);
tb.addEventListener('click',function(){cur=cur==='auto'?'dark':cur==='dark'?'light':'auto';setT(cur);});
})();
"""

LOGO = ('<svg viewBox="0 0 24 24" fill="none" stroke="var(--bg)" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true"><path d="M3 17l5-5 4 3 8-9"/><path d="M15 6h5v5"/></svg>')


def main():
    ahora = datetime.now(MADRID)
    todos = [resumen(b, ahora) for b in BOTS]
    rs = [r for r in todos if not r["bot"].get("experimento")]
    avisos = []
    for r in todos:
        if r["actualizado"]:
            horas = (ahora - r["actualizado"]).total_seconds() / 3600
            if horas > 8:
                avisos.append(f"{CORTO.get(r['bot']['id'], (r['bot']['nombre'],))[0]} no se actualiza desde hace "
                              f"{horas:.0f} horas. Puede ser un fallo puntual al descargar precios; si dura más de un día, avisa a Claude.")
    total = sum(r["actual"] for r in rs)
    inicial = INICIAL * len(rs)
    rent = total / inicial - 1
    comb = combinada(rs)
    esperado_tot = sum(INICIAL * (1 + r["esperado"]) for r in rs) / inicial - 1
    n_pos = sum(len(r["posiciones"]) for r in rs)
    n_ops = sum(r["n_ops"] for r in rs)
    ganadas = sum(1 for r in rs for o in r["ops"] if fnum(o.get("beneficio")) > 0)
    pico, dd_tot = inicial, 0.0
    for _, v in comb:
        pico = max(pico, v)
        dd_tot = min(dd_tot, v / pico - 1)
    datos = dict(inicial=inicial, total=serie_json(comb),
                 bots=[dict(n=CORTO.get(r["bot"]["id"], (r["bot"]["nombre"],))[0], p=serie_json(r["puntos"])) for r in todos])
    leyenda = '<button type="button" aria-pressed="true"><span class="sw tot"></span>Cartera combinada</button>' + "".join(
        f'<button type="button" aria-pressed="true"><span class="sw s{i + 1}"></span>{esc(CORTO.get(r["bot"]["id"], (r["bot"]["nombre"],))[0])}</button>'
        for i, r in enumerate(todos))
    color = "pos" if rent > 0.0005 else ("neg" if rent < -0.0005 else "")
    flecha = "▲" if rent > 0.0005 else ("▼" if rent < -0.0005 else "■")
    aviso = "".join(f'<div class="aviso" role="status">⚠ {esc(a)}</div>' for a in avisos)
    ult = max((r["actualizado"] for r in todos if r["actualizado"]), default=None)
    ult_txt = ult.astimezone(MADRID).strftime("%d/%m %H:%M") if ult else "—"
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel de trading</title><meta name="description" content="Bots de paper trading: cartera combinada, real frente a esperado y detalle por bot.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect width='24' height='24' rx='6' fill='%230b0b0b'/%3E%3Cpath d='M4 16l4-4 3 2 7-7' stroke='white' stroke-width='2' fill='none' stroke-linecap='round'/%3E%3C/svg%3E">
<script>try{{var t=localStorage.getItem('tema');if(t&&t!=='auto')document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}</script>
<style>{CSS}</style></head><body><main>
<div class="top">
  <div class="marca"><div class="logo">{LOGO}</div><div><h1>Panel de trading</h1><p>Dinero simulado · paper trading</p></div></div>
  <div class="chips"><span class="chip"><span class="vivo"></span>Actualizado {esc(ult_txt)}</span>
    <span class="chip">{len(todos)} bots activos</span><button class="chip" id="tema" type="button">Tema</button></div>
</div>
{aviso}
<section class="panel hero" aria-label="Cartera combinada">
  <div>
    <div class="lab">Cartera combinada · {len(rs)} bots</div>
    <div class="grande">{eur(total)} <small>de {eur(inicial)}</small></div>
    <div class="delta {color}"><span aria-hidden="true">{flecha}</span> {pct(rent, True, 2)} desde el inicio</div>
    <div class="mini">
      <div><span>Esperado a hoy</span><b>{pct(esperado_tot, True, 2)}</b></div>
      <div><span>Peor caída</span><b>{pct(dd_tot) if dd_tot < -0.0005 else "0,0 %"}</b></div>
      <div><span>Posiciones abiertas</span><b>{n_pos}</b></div>
      <div><span>Operaciones cerradas</span><b>{n_ops}{f' · {ganadas / n_ops * 100:.0f} % ✓' if n_ops else ''}</b></div>
    </div>
  </div>
  <div>
    <div class="leyenda" role="group" aria-label="Mostrar u ocultar series">{leyenda}</div>
    <div class="chart" id="graf-main" role="img" aria-label="Rentabilidad acumulada de la cartera y de cada bot"></div>
  </div>
</section>
<h2>Real vs esperado <small>comparación con el backtest de cada bot</small></h2>
<section class="panel" style="padding:6px 8px">{tabla_real_vs(todos)}</section>
<h2>Bots <small>pulsa en uno para ver el detalle</small></h2>
{''.join(ficha(i, r) for i, r in enumerate(todos))}
<footer>Los bots funcionan solos en la nube (GitHub): cada hora, y cada ~10 minutos con la bolsa europea abierta. Esta página se recarga sola cada 2 minutos.
Todo es dinero simulado (100 por bot; cripto en USDT y el resto en euros, sumados como si fueran lo mismo). Revisión prevista hacia febrero de 2027:
si los resultados se parecen al backtest, hablamos de dinero real.</footer>
</main>
<script type="application/json" id="datos">{json.dumps(datos).replace("</", "<\\/")}</script>
<script>{JS}</script></body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Panel actualizado: {OUT}")


if __name__ == "__main__":
    main()
