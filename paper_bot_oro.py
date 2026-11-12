"""
Bot de PAPER TRADING para el ORO en velas de 4 horas con el indicador "Buy Sell Signal" de TradingView
(ajustes 5, 13, 14, 0,5, 3), replicado y probado en acciones/validacion_oro_buysell.py.

Reglas:
  - COMPRA cuando la EMA 5 cruza por encima de la EMA 13 y la vela cierra verde.
    VENTA (corto) cuando la EMA 5 cruza por debajo de la EMA 13 y la vela cierra roja.
  - Entrada al cierre de la vela de señal.
  - Stop: mínimo de la vela de señal menos 0,5 x ATR(14) (al revés en cortos).
  - Objetivos: TP1 = 1:1, TP2 = 2:1, TP3 = 3:1. La posición se cierra entera en TP3
    (en el backtest daba más que cerrar 1/3 en cada TP); TP1 y TP2 sólo se anotan.
  - Si sale la señal contraria antes, se cierra la operación (y se abre la contraria).
  - Tamaño: se arriesga el 1 % del capital por operación, sin apalancamiento (como mucho el 100 % del capital).
  - Coste simulado 0,02 % por lado (spread).
Backtest jun 2024 – nov 2026: +40 % en total, peor caída −7 %. Pocos datos y el oro subió mucho: hay que confirmarlo.

Archivos: estado_bot_oro.json, operaciones_oro.csv, capital_oro.csv
Uso:  python paper_bot_oro.py          python paper_bot_oro.py --reset
"""
import argparse, json, os, sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot_oro.json")
TRADES = os.path.join(HERE, "operaciones_oro.csv")
EQUITY = os.path.join(HERE, "capital_oro.csv")
FAST, SLOW, ATR_N, SL_MULT, RR = 5, 13, 14, 0.5, 3.0
RISK, COST, SYM = 0.01, 0.0002, "ORO"


def descargar():
    import yfinance as yf
    d = yf.download("GC=F", period="60d", interval="1h", auto_adjust=False, progress=False, threads=False)
    d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
    d.index = pd.to_datetime(d.index, utc=True)
    d = d[["Open", "High", "Low", "Close"]].dropna()
    d4 = d.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    ahora = pd.Timestamp(datetime.now(timezone.utc))
    return d4[d4.index + pd.Timedelta(hours=4) <= ahora], float(d.Close.iloc[-1])


def senales(d):
    c, o, h, l = d.Close, d.Open, d.High, d.Low
    ef = c.ewm(span=FAST, adjust=False).mean(); es = c.ewm(span=SLOW, adjust=False).mean()
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / ATR_N, adjust=False).mean()
    buy = (ef > es) & (ef.shift(1) <= es.shift(1)) & (c > o)
    sell = (ef < es) & (ef.shift(1) >= es.shift(1)) & (c < o)
    return d.assign(buy=buy, sell=sell, atr=atr)


def load_state(capital):
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return dict(equity=capital, trade=None, last_bar=None, start=datetime.now(timezone.utc).isoformat())


def append_csv(path, row):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def cerrar(st, px, cuando, motivo):
    t = st["trade"]
    pct = (px / t["entry"] - 1) * t["dir"] - 2 * COST
    pnl = t["notional"] * pct
    st["equity"] += pnl
    append_csv(TRADES, dict(simbolo=f"{SYM} {'largo' if t['dir'] > 0 else 'corto'}", entrada=t["time"], salida=cuando,
                            precio_entrada=round(t["entry"], 2), precio_salida=round(px, 2), beneficio=round(pnl, 4),
                            r=round(pct / t["risk_pct"], 2), motivo=motivo))
    print(f"  CIERRE {'largo' if t['dir'] > 0 else 'corto'} a {px:.2f} ({motivo})  resultado {pnl:+.2f} €")
    st["trade"] = None


def abrir(st, row, cuando, d):
    e = float(row.Close)
    if d > 0:
        sl = float(row.Low - SL_MULT * row.atr)
    else:
        sl = float(row.High + SL_MULT * row.atr)
    risk_pct = abs(e - sl) / e
    if risk_pct <= 0:
        return
    notional = st["equity"] * min(RISK / risk_pct, 1.0)
    tps = [e + d * abs(e - sl) * k for k in (1, 2, RR)]
    st["trade"] = dict(dir=d, entry=e, sl=sl, tps=tps, hit=[False, False, False], notional=notional,
                       risk_pct=risk_pct, time=cuando)
    print(f"  {'COMPRA' if d > 0 else 'VENTA (corto)'} oro a {e:.2f}  SL {sl:.2f}  TP1 {tps[0]:.2f}  TP2 {tps[1]:.2f}  "
          f"TP3 {tps[2]:.2f}  (posición {notional:.2f} €)")


def procesar(st, row, cuando):
    t = st["trade"]
    if t:
        d = t["dir"]
        if (d > 0 and row.Low <= t["sl"]) or (d < 0 and row.High >= t["sl"]):
            px = min(row.Open, t["sl"]) if d > 0 else max(row.Open, t["sl"])
            cerrar(st, px, cuando, "stop loss")
        else:
            for k in range(3):
                if not t["hit"][k] and ((d > 0 and row.High >= t["tps"][k]) or (d < 0 and row.Low <= t["tps"][k])):
                    t["hit"][k] = True
                    print(f"  TP{k + 1} alcanzado ({t['tps'][k]:.2f})")
            if t["hit"][2]:
                cerrar(st, t["tps"][2], cuando, "TP3 (3:1)")
            elif (d > 0 and row.sell) or (d < 0 and row.buy):
                cerrar(st, float(row.Close), cuando, "señal contraria")
    if st["trade"] is None:
        if row.buy:
            abrir(st, row, cuando, 1)
        elif row.sell:
            abrir(st, row, cuando, -1)


def analisis(st, d, nombre="Oro", vela="4h"):
    r = d.iloc[-1]
    c = d.Close
    ef = c.ewm(span=FAST, adjust=False).mean().iloc[-1]
    es = c.ewm(span=SLOW, adjust=False).mean().iloc[-1]
    t = st["trade"]
    if t:
        lado = "largo (apuesta a que sube)" if t["dir"] > 0 else "corto (apuesta a que baja)"
        txt = (f"Posición en {lado} desde {t['entry']:.2f}. Stop {t['sl']:.2f}, objetivo final {t['tps'][2]:.2f}. "
               f"Cierra antes si sale la señal contraria.")
        filas = [[nombre, "cartera", txt]]
    else:
        arriba = ef > es
        txt = (f"Media rápida (EMA 5) {ef:.2f} {'por encima' if arriba else 'por debajo'} de la lenta (EMA 13) {es:.2f}. "
               f"Necesita que se crucen {'hacia abajo con vela roja para ponerse corto' if arriba else 'hacia arriba con vela verde para comprar'}. "
               f"Diferencia {abs(ef / es - 1) * 100:.2f} %.")
        filas = [[nombre, "cerca" if abs(ef / es - 1) < 0.002 else "no", txt]]
    st["analisis"] = dict(fecha=datetime.now(timezone.utc).isoformat(timespec="seconds"), filas=filas,
                          resumen=f"Opera cuando las medias de 5 y 13 velas de {vela} se cruzan con una vela que lo confirma. "
                                  f"Última vela cerrada: {d.index[-1].strftime('%d/%m %H:%M')} UTC, cierre {float(r.Close):.2f}.")


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
        d, ultimo = descargar()
    except Exception as e:
        sys.exit(f"Error al descargar precios del oro: {e}")
    d = senales(d)
    st = load_state(a.capital)
    nuevas = d if st["last_bar"] is None else d[d.index > pd.Timestamp(st["last_bar"])]
    if st["last_bar"] is None:
        nuevas = d.iloc[-1:]          # al empezar, sólo la última vela cerrada
    if nuevas.empty:
        print("No hay velas de 4h nuevas. Nada que hacer.")
    for ts, row in nuevas.iterrows():
        cuando = ts.strftime("%Y-%m-%d %H:%M")
        print(f"Vela 4h de {cuando} UTC: cierre {row.Close:.2f}")
        procesar(st, row, cuando)
        st["last_bar"] = str(ts)
        t = st["trade"]
        marcado = st["equity"] + (t["notional"] * (float(row.Close) / t["entry"] - 1) * t["dir"] if t else 0)
        append_csv(EQUITY, dict(fecha=cuando, capital=round(marcado, 2), posiciones=int(t is not None)))

    # campos para el panel (formato común): valor = cash + units * precio
    t = st["trade"]
    if t:
        u = t["dir"] * t["notional"] / t["entry"]
        st["cash"] = st["equity"] - u * t["entry"]
        st["positions"] = {SYM: dict(units=u, entry=t["entry"], stop=t["sl"], time=t["time"])}
        st["prices"] = {SYM: ultimo}
    else:
        st["cash"], st["positions"], st["prices"] = st["equity"], {}, {}
    analisis(st, d)
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)
    vivo = st["cash"] + sum(p["units"] * ultimo for p in st["positions"].values())
    print(f"Capital simulado (oro): {vivo:.2f} €  | oro ahora {ultimo:.2f} $")


if __name__ == "__main__":
    main()
