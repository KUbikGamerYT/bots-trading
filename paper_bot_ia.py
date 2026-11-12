"""
Bot de PAPER TRADING "Agente IA" (TradingAgents), valorado en euros.

Usa el proyecto TradingAgents (github.com/TauricResearch/TradingAgents): un equipo de IAs
(analistas de gráfico, noticias y redes sociales, un debate alcista/bajista, un trader y un
equipo de riesgo) que da una nota por activo: Buy, Overweight, Hold, Underweight o Sell.

Reglas del bot:
  - 3 activos: Bitcoin (BTC-USD), S&P 500 (SPY) y oro (GLD), pasados a euros.
  - Una vez por semana la IA analiza cada uno con la información hasta el cierre anterior.
  - Buy u Overweight -> tener 1/3 del capital en ese activo.  Underweight o Sell -> vender.
    Hold -> no tocar.  Si la IA falla (cuota gratis agotada), se reintenta al día siguiente.
  - Coste simulado 0,1 % por lado.
  - Cada hora solo se valora la cartera con los precios actuales (no gasta IA).
SIN BACKTEST: la IA "recuerda" el pasado, así que solo vale probarla de hoy en adelante.

Necesita la clave GOOGLE_API_KEY (Gemini). Sin clave, el modo --decidir no hace nada.
Archivos: estado_bot_ia.json, operaciones_ia.csv, capital_ia.csv, decisiones_ia.csv
Uso:  python paper_bot_ia.py             (valorar)
      python paper_bot_ia.py --decidir   (decisión semanal con IA; --forzar para repetir en la semana)
"""
import argparse, json, os, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot_ia.json")
TRADES = os.path.join(HERE, "operaciones_ia.csv")
EQUITY = os.path.join(HERE, "capital_ia.csv")
DECISIONES = os.path.join(HERE, "decisiones_ia.csv")
COST = 0.001
NOMBRE = {"BTC-USD": "Bitcoin", "SPY": "S&P 500", "GLD": "Oro"}
TIPO = {"BTC-USD": "crypto", "SPY": "stock", "GLD": "stock"}
TICKERS = list(NOMBRE)
COMPRAR, VENDER = {"Buy", "Overweight"}, {"Underweight", "Sell"}
MADRID = ZoneInfo("Europe/Madrid")


def precios():
    """Últimos precios en euros y fecha de la última sesión cerrada (de bolsa)."""
    import yfinance as yf
    d = yf.download(TICKERS + ["EURUSD=X"], period="1mo", interval="1d", auto_adjust=True,
                    progress=False, threads=False)
    c = d["Close"].dropna(how="all").ffill()
    eur = c[TICKERS].div(c["EURUSD=X"], axis=0)
    hoy = datetime.now(MADRID).date()
    cerradas = c["SPY"].dropna()
    cerradas = cerradas[cerradas.index.date < hoy]
    return eur.iloc[-1], str(cerradas.index[-1].date())


def load_state(capital):
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return dict(cash=capital, positions={}, last_bar=None, ultima_decision=None,
                start=datetime.now(timezone.utc).isoformat())


def append_csv(path, row):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def equity(st, px):
    return st["cash"] + sum(p["units"] * float(px.get(s, p["entry"])) for s, p in st["positions"].items())


def preguntar_ia(ticker, fecha):
    """Ejecuta TradingAgents y devuelve (nota, resumen)."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"] = "google"
    cfg["quick_think_llm"] = os.environ.get("IA_MODELO_RAPIDO", "gemini-3.5-flash-lite")
    cfg["deep_think_llm"] = os.environ.get("IA_MODELO_PROFUNDO", "gemini-3.5-flash-lite")  # el 3.8 agota la cuota gratis
    cfg["max_debate_rounds"] = 1
    cfg["max_risk_discuss_rounds"] = 1
    cfg["llm_max_retries"] = 8          # el plan gratuito limita llamadas por minuto
    cfg["output_language"] = "Spanish"
    ta = TradingAgentsGraph(selected_analysts=("market", "social", "news"), config=cfg)
    state, nota = ta.propagate(ticker, fecha, asset_type=TIPO[ticker])
    texto = str(state.get("final_trade_decision", "") or "").strip()
    return nota, texto


ACCION = {"Buy": "compra / mantiene 1/3", "Overweight": "compra / mantiene 1/3", "Hold": "no toca nada",
          "Underweight": "vende / no compra", "Sell": "vende / no compra"}


def guardar_analisis(st, s, nota, texto, fecha):
    """Guarda el último análisis de la IA por activo para mostrarlo en el panel."""
    a = st.setdefault("analisis", dict(resumen="", filas=[]))
    filas = [f for f in a.get("filas", []) if f[0] != NOMBRE[s]]
    estado = "si" if nota in COMPRAR else ("cerca" if nota == "Hold" else "no")
    if s in st["positions"] and nota not in VENDER:
        estado = "cartera"
    acc = ACCION.get(nota, "error: se reintenta mañana")
    filas.append([NOMBRE[s], estado, f"Nota de la IA: {nota} ({acc}). Análisis del {fecha}:\n\n{texto[:2500]}"])
    filas.sort(key=lambda f: [NOMBRE[x] for x in TICKERS].index(f[0]))
    a.update(filas=filas, fecha=datetime.now(timezone.utc).isoformat(timespec="seconds"),
             resumen="Último análisis del equipo de IAs para cada activo (se renueva una vez por semana).")


def pendientes(st, forzar=False):
    """Activos sin decisión válida en los últimos 6 días (si falló por cuota, se reintenta al día siguiente)."""
    hace6 = datetime.now(timezone.utc) - timedelta(days=6)
    hechos = st.get("decididos", {})
    return [s for s in TICKERS if forzar or s not in hechos or datetime.fromisoformat(hechos[s]) < hace6]


def decidir(st, px, fecha, activos, log=print):
    pos = st["positions"]
    tot = equity(st, px)
    for s in activos:
        try:
            nota, resumen = preguntar_ia(s, fecha)
        except Exception as e:
            nota, resumen = "ERROR", f"{type(e).__name__}: {e}"[:300]
        log(f"  {NOMBRE[s]:<8} nota de la IA: {nota}")
        if resumen:
            log(f"           {' '.join(resumen.split())[:250]}")
        append_csv(DECISIONES, dict(fecha=fecha, simbolo=s, nota=nota, resumen=" ".join(resumen.split())[:400]))
        guardar_analisis(st, s, nota, resumen, fecha)
        if nota in ("ERROR", "REVIEW"):
            log("           (se reintentará en la próxima ejecución diaria)")
            continue
        st.setdefault("decididos", {})[s] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        precio = float(px[s])
        if nota in VENDER and s in pos:
            p = pos.pop(s)
            fill = precio * (1 - COST)
            st["cash"] += p["units"] * fill
            pnl = p["units"] * (fill - p["entry"])
            append_csv(TRADES, dict(simbolo=s, entrada=p["time"], salida=fecha, precio_entrada=round(p["entry"], 4),
                                    precio_salida=round(fill, 4), beneficio=round(pnl, 4), motivo=f"IA: {nota}"))
            log(f"  VENTA  {NOMBRE[s]:<8} a {fill:.2f} €  resultado {pnl:+.2f} €")
        elif nota in COMPRAR and s not in pos:
            gasto = min(tot / len(TICKERS), st["cash"])
            if gasto >= 1:
                fill = precio * (1 + COST)
                pos[s] = dict(units=gasto / fill, entry=fill, time=fecha, stop=0)
                st["cash"] -= gasto
                log(f"  COMPRA {NOMBRE[s]:<8} a {fill:.2f} €  por {gasto:.2f} €")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--decidir", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (STATE, TRADES, EQUITY, DECISIONES):
            if os.path.exists(f):
                os.remove(f)
    try:
        px, fecha = precios()
    except Exception as e:
        sys.exit(f"Error al descargar precios: {e}")
    st = load_state(a.capital)

    if a.decidir:
        if not os.environ.get("GOOGLE_API_KEY"):
            print("Falta la clave GOOGLE_API_KEY (secret de GitHub). No se consulta a la IA.")
        else:
            activos = pendientes(st, a.forzar)
            if not activos:
                print("Los 3 activos ya tienen decisión esta semana. Nada que hacer.")
            else:
                print(f"Decisión semanal con datos hasta el {fecha}: {', '.join(NOMBRE[x] for x in activos)}")
                decidir(st, px, fecha, activos)
                st["ultima_decision"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    hoy = str(datetime.now(MADRID).date())
    eq = equity(st, px)
    if st.get("last_bar") != hoy:
        append_csv(EQUITY, dict(fecha=hoy, capital=round(eq, 2), liquidez=round(st["cash"], 2),
                                posiciones=len(st["positions"])))
        st["last_bar"] = hoy
    st["prices"] = {s: float(px[s]) for s in st["positions"]}
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)
    print(f"Capital simulado (agente IA): {eq:.2f} €")
    for s, p in st["positions"].items():
        pr = st["prices"][s]
        print(f"  {NOMBRE[s]:<8} valor {p['units'] * pr:.2f} €  ({(pr / p['entry'] - 1) * 100:+.1f} %)")


if __name__ == "__main__":
    main()
