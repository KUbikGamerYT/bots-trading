"""
Bot de PAPER TRADING con acciones españolas y europeas (en euros).

Estrategia "momentum mensual" (validada en validacion_euro.py):
  - Universo: ~90 grandes empresas de la zona euro (IBEX 35 + grandes de Alemania, Francia, Italia, Países Bajos...).
  - Una vez al mes (primer día de mercado del mes) elige las 5 que más han subido en los últimos 12 meses
    (sin contar el último mes) y que además cotizan por encima de su media de 200 sesiones.
  - Vende las que ya no están entre las 5 y compra las nuevas con el mismo peso (20 % cada una).
    Si hay menos de 5 candidatas, la parte que falta queda en liquidez.
  - Coste simulado 0,2 % por compra y por venta (incluye el impuesto español del 0,2 % al comprar).

Guarda su estado aparte de los bots de cripto:
    estado_bot_acciones.json, operaciones_acciones.csv, capital_acciones.csv

Uso:  python paper_bot_acciones.py          (se puede ejecutar cada hora: sólo actúa con velas diarias cerradas)
      python paper_bot_acciones.py --reset
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot_acciones.json")
TRADES = os.path.join(HERE, "operaciones_acciones.csv")
EQUITY = os.path.join(HERE, "capital_acciones.csv")

TOP_N, COST, SMA_N, LOOKBACK, SKIP = 5, 0.002, 200, 252, 21

ESPANA = ("A3M ACS ACX AENA ALM AMS ANA BBVA BKT CABK CIE CLNX COL EBRO ELE ENC ENG FDR FER GAM GRF IAG IBE "
          "IDR ITX LOG MAP MEL MRL MTS NTGY PHM PUIG RED REP ROVI SAB SAN SCYR SLR TEF TRE UNI VIS").split()
EUROPA = ("ASML.AS MC.PA SAP.DE SIE.DE TTE.PA OR.PA AIR.PA ALV.DE SAN.PA SU.PA BNP.PA AI.PA DTE.DE INGA.AS EL.PA "
          "MUV2.DE RMS.PA BAS.DE BAYN.DE BMW.DE MBG.DE VOW3.DE ADS.DE DB1.DE IFX.DE ENEL.MI ENI.MI ISP.MI UCG.MI "
          "RACE.MI STLAM.MI KER.PA CS.PA DG.PA SAF.PA BN.PA RI.PA PHIA.AS AD.AS NOKIA.HE KNEBV.HE DHL.DE RWE.DE "
          "EOAN.DE ABI.BR KBC.BR PRX.AS HEIA.AS").split()
TICKERS = [t + ".MC" for t in ESPANA] + EUROPA


def descargar():
    import yfinance as yf
    d = yf.download(TICKERS, period="2y", interval="1d", auto_adjust=True, progress=False, threads=False)
    c = d["Close"].dropna(how="all")
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    cerradas = c[c.index.date < hoy]            # sólo sesiones ya cerradas
    ultimo = c.ffill().iloc[-1]                 # precio más reciente para simular las órdenes
    return cerradas.ffill(limit=5), ultimo


def load_state(capital):
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return dict(cash=capital, positions={}, last_bar=None, last_rebalance=None,
                start=datetime.now(timezone.utc).isoformat())


def save_state(st):
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)


def append_csv(path, row):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def elegir(c):
    mom = c.iloc[-1 - SKIP] / c.iloc[-1 - LOOKBACK] - 1
    sma = c.iloc[-SMA_N:].mean()
    ok = (c.iloc[-1] > sma) & mom.notna() & (c.iloc[-LOOKBACK:].notna().sum() > LOOKBACK * 0.9)
    return mom[ok].sort_values(ascending=False).head(TOP_N), mom


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
    if len(c) < LOOKBACK + 5:
        sys.exit("No hay suficiente historial de precios.")

    st = load_state(a.capital)
    pos = st["positions"]
    precio = {s: float(ultimo[s]) for s in ultimo.index if pd.notna(ultimo[s])}
    bar = str(c.index[-1].date())
    mes = bar[:7]

    def equity():
        return st["cash"] + sum(p["units"] * precio.get(s, p["entry"]) for s, p in pos.items())

    if st["last_bar"] == bar:
        print(f"La sesión del {bar} ya está procesada. Nada que hacer.")
    else:
        print(f"Procesando sesión del {bar}")
        if st.get("last_rebalance") != mes:
            top, mom = elegir(c)
            print("  Revisión mensual. Las 5 más fuertes: " +
                  (", ".join(f"{s} ({m * 100:+.0f} %)" for s, m in top.items()) or "ninguna cumple las reglas"))
            # 1) ventas
            for s in list(pos):
                if s not in top.index:
                    p = pos.pop(s)
                    px = precio.get(s, p["entry"]) * (1 - COST)
                    st["cash"] += p["units"] * px
                    pnl = p["units"] * (px - p["entry"])
                    append_csv(TRADES, dict(simbolo=s, entrada=p["time"], salida=bar, precio_entrada=p["entry"],
                                            precio_salida=round(px, 4), unidades=p["units"], beneficio=round(pnl, 4),
                                            motivo="ya no está entre las 5 más fuertes"))
                    print(f"  VENTA  {s:<9} a {px:.4g}  resultado {pnl:+.2f} €")
            # 2) compras, 1/5 del capital cada una
            hueco = equity() / TOP_N
            for s in top.index:
                if s in pos or s not in precio:
                    continue
                gasto = min(hueco, st["cash"])
                if gasto < 1:
                    break
                px = precio[s] * (1 + COST)
                pos[s] = dict(units=gasto / px, entry=px, time=bar, stop=0)
                st["cash"] -= gasto
                print(f"  COMPRA {s:<9} a {px:.4g}  por {gasto:.2f} €  (subió {mom[s] * 100:+.0f} % en 12 meses)")
            st["last_rebalance"] = mes
        st["last_bar"] = bar
        append_csv(EQUITY, dict(fecha=bar, capital=round(equity(), 2), liquidez=round(st["cash"], 2),
                                posiciones=len(pos)))
    st["prices"] = {s: precio[s] for s in pos if s in precio}
    save_state(st)
    print(f"Capital simulado (acciones): {equity():.2f} EUR")
    for s, p in pos.items():
        px = precio.get(s, p["entry"])
        print(f"  {s:<9} valor {p['units'] * px:.2f} €  entrada {p['entry']:.4g}  ({(px / p['entry'] - 1) * 100:+.1f} %)")


if __name__ == "__main__":
    main()
