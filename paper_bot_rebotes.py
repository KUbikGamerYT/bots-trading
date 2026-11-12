"""
Bot de PAPER TRADING "Rebotes en índices" (RSI 2), valorado en euros.

Estrategia (validada en acciones/validacion_rsi2_indices.py):
  - 9 índices / ETF: S&P 500, Nasdaq 100, pequeñas EE. UU., desarrollados ex-EE. UU., emergentes, oro,
    bonos EE. UU. 20+ años, IBEX 35 y Euro Stoxx 50 (los de EE. UU. pasados a euros).
  - COMPRA al cierre si el RSI de 2 sesiones baja de 10 (caída fuerte de 2-3 días) y el precio sigue
    por encima de su media de 200 sesiones (tendencia alcista).
  - VENTA al cierre en cuanto el precio cierra por encima de su media de 5 sesiones (el rebote).
  - Hasta 3 posiciones a la vez, 1/3 del capital cada una; si hay más candidatos, los más sobrevendidos.
  - Coste simulado 0,05 % por lado.
Backtest 2010–2026: ~70 % de aciertos, +7 % al año, peor caída −14 %, unas 3 operaciones al mes.

Archivos: estado_bot_rebotes.json, operaciones_rebotes.csv, capital_rebotes.csv
Uso:  python paper_bot_rebotes.py          python paper_bot_rebotes.py --reset
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot_rebotes.json")
TRADES = os.path.join(HERE, "operaciones_rebotes.csv")
EQUITY = os.path.join(HERE, "capital_rebotes.csv")
MAX_POS, COST, RSI_MAX = 3, 0.0005, 10

NOMBRE = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Pequeñas EE.UU.", "EFA": "Desarrollados ex-EE.UU.",
          "EEM": "Emergentes", "GLD": "Oro", "TLT": "Bonos EE.UU. 20+", "^IBEX": "IBEX 35", "^STOXX50E": "Euro Stoxx 50"}
USD = ["SPY", "QQQ", "IWM", "EFA", "EEM", "GLD", "TLT"]
TICKERS = list(NOMBRE)


def descargar():
    import yfinance as yf
    d = yf.download(TICKERS + ["EURUSD=X"], period="2y", interval="1d", auto_adjust=True, progress=False, threads=False)
    c = d["Close"].dropna(how="all").ffill()
    p = c[TICKERS].copy()
    p[USD] = p[USD].div(c["EURUSD=X"], axis=0)     # precios en euros
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    return p[p.index.date < hoy], p.iloc[-1]


def rsi(c, n=2):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def load_state(capital):
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return dict(cash=capital, positions={}, last_bar=None, start=datetime.now(timezone.utc).isoformat())


def append_csv(path, row):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def paso(st, c, fecha, log=print):
    """Procesa el cierre de la sesión 'fecha' (precios c = histórico hasta esa sesión)."""
    pos = st["positions"]
    px = c.iloc[-1]
    r2 = c.apply(rsi).iloc[-1]
    s5 = c.iloc[-5:].mean()
    s200 = c.iloc[-200:].mean()

    def equity():
        return st["cash"] + sum(p["units"] * float(px.get(s, p["entry"])) for s, p in pos.items())

    for s in list(pos):
        if pd.notna(px[s]) and px[s] > s5[s]:
            p = pos.pop(s)
            fill = float(px[s]) * (1 - COST)
            st["cash"] += p["units"] * fill
            pnl = p["units"] * (fill - p["entry"])
            append_csv(TRADES, dict(simbolo=s, entrada=p["time"], salida=fecha, precio_entrada=round(p["entry"], 4),
                                    precio_salida=round(fill, 4), beneficio=round(pnl, 4), motivo="rebote: cierra sobre su media de 5"))
            log(f"  VENTA  {NOMBRE[s]:<22} a {fill:.2f}  resultado {pnl:+.2f} €")
    cand = [s for s in TICKERS if s not in pos and pd.notna(r2[s]) and r2[s] < RSI_MAX and px[s] > s200[s]]
    cand.sort(key=lambda s: r2[s])
    tot = equity()
    for s in cand:
        if len(pos) >= MAX_POS:
            break
        gasto = min(tot / MAX_POS, st["cash"])
        if gasto < 1:
            break
        fill = float(px[s]) * (1 + COST)
        pos[s] = dict(units=gasto / fill, entry=fill, time=fecha, stop=0)
        st["cash"] -= gasto
        log(f"  COMPRA {NOMBRE[s]:<22} a {fill:.2f}  por {gasto:.2f} €  (RSI2 {r2[s]:.1f}: caída fuerte en tendencia alcista)")
    return equity()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (STATE, TRADES, EQUITY):
            if os.path.exists(f):
                os.remove(f)
    try:
        c, ultimo = descargar()
    except Exception as e:
        sys.exit(f"Error al descargar precios: {e}")
    if len(c) < 210:
        sys.exit("No hay suficiente historial de precios.")
    st = load_state(a.capital)
    bar = str(c.index[-1].date())
    if st["last_bar"] == bar:
        print(f"La sesión del {bar} ya está procesada. Nada que hacer.")
    else:
        print(f"Procesando cierre del {bar}")
        eq = paso(st, c, bar)
        st["last_bar"] = bar
        append_csv(EQUITY, dict(fecha=bar, capital=round(eq, 2), liquidez=round(st["cash"], 2), posiciones=len(st["positions"])))
    st["prices"] = {s: float(ultimo[s]) for s in st["positions"] if pd.notna(ultimo[s])}
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)
    vivo = st["cash"] + sum(p["units"] * st["prices"].get(s, p["entry"]) for s, p in st["positions"].items())
    print(f"Capital simulado (rebotes): {vivo:.2f} €")
    for s, p in st["positions"].items():
        pr = st["prices"].get(s, p["entry"])
        print(f"  {NOMBRE[s]:<22} valor {p['units'] * pr:.2f} €  ({(pr / p['entry'] - 1) * 100:+.1f} %)")


if __name__ == "__main__":
    main()
