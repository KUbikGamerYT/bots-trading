"""
Bot EXPERIMENTO "loco": muchas operaciones al día en Bitcoin con velas de 5 minutos.

Usa las mismas reglas que el bot de oro (indicador "Buy Sell Signal": EMA 5/13 con vela de confirmación,
stop en la vela ± 0,5 ATR, objetivo 3:1, cierre con señal contraria, largos y cortos, 1 % de riesgo),
pero en BTC/USDT a 5 minutos, con la comisión real de Binance (0,1 % por lado).
Se espera que haga ~15-25 operaciones al día. En el backtest del oro a 5 minutos perdía casi todo:
es un experimento para verlo en directo, no cuenta en la cartera combinada.

Como GitHub lo ejecuta cada hora, en cada pasada procesa todas las velas de 5 minutos nuevas.
Archivos: estado_bot_loco.json, operaciones_loco.csv, capital_loco.csv
"""
import argparse, json, os, sys
from datetime import datetime, timezone
import pandas as pd
import paper_bot as pb
import paper_bot_oro as ob

HERE = os.path.dirname(os.path.abspath(__file__))
ob.STATE = os.path.join(HERE, "estado_bot_loco.json")
ob.TRADES = os.path.join(HERE, "operaciones_loco.csv")
ob.EQUITY = os.path.join(HERE, "capital_loco.csv")
ob.SYM, ob.COST = "BTC", 0.001


def descargar():
    ex = pb.BinanceVision()
    rows = ex.fetch_ohlcv("BTC/USDT", timeframe="5m", limit=1000)
    d = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    d.index = pd.to_datetime(d.ts, unit="ms", utc=True)
    ahora = pd.Timestamp(datetime.now(timezone.utc))
    d = d[d.index + pd.Timedelta(minutes=5) <= ahora][["Open", "High", "Low", "Close"]]
    return d, float(ex.fetch_ticker("BTC/USDT")["last"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (ob.STATE, ob.TRADES, ob.EQUITY):
            if os.path.exists(f):
                os.remove(f)
    try:
        d, ultimo = descargar()
    except Exception as e:
        sys.exit(f"Error al descargar BTC 5m: {e}")
    d = ob.senales(d)
    st = ob.load_state(a.capital)
    nuevas = d.iloc[-1:] if st["last_bar"] is None else d[d.index > pd.Timestamp(st["last_bar"])]
    n0 = len(pd.read_csv(ob.TRADES)) if os.path.exists(ob.TRADES) else 0
    for ts, row in nuevas.iterrows():
        ob.procesar(st, row, ts.strftime("%Y-%m-%d %H:%M"))
        st["last_bar"] = str(ts)
        if ts.minute == 0 or ts == nuevas.index[-1]:   # un punto de capital por hora (y el último)
            t = st["trade"]
            marcado = st["equity"] + (t["notional"] * (float(row.Close) / t["entry"] - 1) * t["dir"] if t else 0)
            ob.append_csv(ob.EQUITY, dict(fecha=ts.strftime("%Y-%m-%d %H:%M"), capital=round(marcado, 2),
                                          posiciones=int(t is not None)))
    n1 = len(pd.read_csv(ob.TRADES)) if os.path.exists(ob.TRADES) else 0
    print(f"Velas de 5 min procesadas: {len(nuevas)} · operaciones cerradas en esta pasada: {n1 - n0}")
    t = st["trade"]
    if t:
        u = t["dir"] * t["notional"] / t["entry"]
        st["cash"] = st["equity"] - u * t["entry"]
        st["positions"] = {"BTC": dict(units=u, entry=t["entry"], stop=t["sl"], time=t["time"])}
        st["prices"] = {"BTC": ultimo}
    else:
        st["cash"], st["positions"], st["prices"] = st["equity"], {}, {}
    ob.analisis(st, d, nombre="Bitcoin", vela="5 minutos")
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(ob.STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)
    vivo = st["cash"] + sum(p["units"] * ultimo for p in st["positions"].values())
    print(f"Capital simulado (loco): {vivo:.2f} USDT")


if __name__ == "__main__":
    main()
