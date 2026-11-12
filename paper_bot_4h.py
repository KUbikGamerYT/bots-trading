"""
Bot de PAPER TRADING en velas de 4 horas para BTC (la estrategia de "corto-medio plazo").

Reglas (las de validacion_corto_plazo.py, variante 55/10/3):
  - COMPRA si el cierre de 4h supera el máximo de las últimas 55 velas y SMA50 > SMA200.
  - Stop dinámico a 3 x ATR(20); venta también si el cierre rompe el mínimo de las últimas 10 velas.
  - Riesgo 2 % por operación, hasta el 100 % del capital, sin apalancamiento. Coste 0,15 % por lado.

Guarda su propio estado, separado del bot diario:
    estado_bot_4h.json, operaciones_4h.csv, capital_4h.csv

Uso:  python paper_bot_4h.py        (ejecútalo cada hora: sólo actúa cuando cierra una vela de 4h)
      python paper_bot_4h.py --reset
"""
import argparse, os, sys
from datetime import datetime, timezone
import pandas as pd
import paper_bot as pb

pb.P.update(entry_n=55, exit_n=10, fast=50, slow=200, atr_n=20, atr_mult=3.0,
            risk=0.02, max_total_risk=0.02, max_pos_weight=1.0, max_gross=1.0, cost=0.0015)
pb.STATE = os.path.join(pb.HERE, "estado_bot_4h.json")
pb.TRADES = os.path.join(pb.HERE, "operaciones_4h.csv")
pb.EQUITY = os.path.join(pb.HERE, "capital_4h.csv")
SYMBOLS = ["BTC"]


def fetch_4h(exchange, sym, quote):
    rows = exchange.fetch_ohlcv(f"{sym}/{quote}", timeframe="4h", limit=300)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df.ts, unit="ms")
    df = df.set_index("time")[["open", "high", "low", "close"]]
    now = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    return df[df.index + pd.Timedelta(hours=4) <= now]  # sólo velas cerradas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--quote", default="USDT")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (pb.STATE, pb.TRADES, pb.EQUITY):
            if os.path.exists(f):
                os.remove(f)

    ex = pb.make_exchange(a.exchange)
    st = pb.load_state(a.capital)
    ind, price = {}, {}
    for s in SYMBOLS:
        try:
            d = fetch_4h(ex, s, a.quote)
            ind[s] = pb.indicators(d)
            price[s] = ex.fetch_ticker(f"{s}/{a.quote}")["last"]
        except Exception as e:
            sys.exit(f"{s}: error al descargar datos ({e}). Prueba con --exchange kraken")

    bar = str(max(r.time for r in ind.values()))
    if st["last_bar"] == bar:
        print(f"La vela de 4h de {bar} ya está procesada. Nada que hacer.")
    else:
        print(f"Procesando vela de 4h de {bar} UTC")
        pb.step(st, ind, price)
        st["last_bar"] = bar
        eq = st["cash"] + sum(p["units"] * price[s] for s, p in st["positions"].items())
        pb.append_csv(pb.EQUITY, dict(fecha=bar, capital=round(eq, 2), liquidez=round(st["cash"], 2),
                                      posiciones=len(st["positions"])))
    st["prices"] = {k: float(v) for k, v in price.items()}  # para el panel
    pb.analisis(st, ind, price, unidad="velas de 4h")
    pb.save_state(st)
    eq = st["cash"] + sum(p["units"] * price[s] for s, p in st["positions"].items())
    print(f"Capital simulado (4h): {eq:.2f} {a.quote}")
    for s, p in st["positions"].items():
        print(f"  {s} valor {p['units'] * price[s]:.2f}  entrada {p['entry']:.6g}  stop {p['stop']:.6g}")


if __name__ == "__main__":
    main()
